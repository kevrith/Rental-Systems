"""Sprint 14: tenant applications, scoring, guarantors and reference checks."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.models.application import Guarantor, ReferenceCheck
from app.models.notification import Notification, NotificationType
from tests.conftest import Actor, unique_phone
from tests.test_portfolio import make_property, make_unit


async def vacant_unit(owner: Actor, rent: str = "30000.00") -> dict:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"], monthly_rent=rent)
    return {"property": prop, "unit": unit}


def application_payload(unit_id: str, **overrides) -> dict:
    return {
        "unit_id": unit_id,
        "full_name": "Amina Hassan",
        "phone_number": unique_phone(),
        "national_id": "31234567",
        "current_address": "Kileleshwa, Nairobi",
        "employment_status": "employed",
        "employer_name": "Safaricom",
        "job_title": "Analyst",
        "monthly_income": "150000.00",
        "months_in_employment": 36,
        "occupants": 2,
        **overrides,
    }


async def apply_publicly(client: AsyncClient, unit_id: str, **overrides) -> dict:
    response = await client.post(f"/api/v1/apply/{unit_id}", json=application_payload(unit_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


async def make_application(owner: Actor, unit_id: str, **overrides) -> dict:
    response = await owner.post("/api/v1/applications", json=application_payload(unit_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------- the public form


async def test_the_public_listing_only_answers_for_a_lettable_unit(owner: Actor, client: AsyncClient) -> None:
    setup = await vacant_unit(owner)

    listing = await client.get(f"/api/v1/apply/{setup['unit']['id']}")
    assert listing.status_code == 200
    body = listing.json()
    assert body["unit_number"] == setup["unit"]["unit_number"]
    assert body["accepting_applications"] is True
    # The public payload carries no ids that would expose the portfolio.
    assert "organization_id" not in body


async def test_anyone_can_apply_without_logging_in(owner: Actor, client: AsyncClient) -> None:
    setup = await vacant_unit(owner)

    body = await apply_publicly(client, setup["unit"]["id"])

    assert body["reference_code"].startswith("APP-")
    assert body["status"] == "submitted"

    listed = await owner.get("/api/v1/applications")
    assert listed.status_code == 200
    assert [row["reference_code"] for row in listed.json()] == [body["reference_code"]]


async def test_the_same_person_cannot_apply_twice_for_one_unit(owner: Actor, client: AsyncClient) -> None:
    setup = await vacant_unit(owner)
    phone = unique_phone()
    await apply_publicly(client, setup["unit"]["id"], phone_number=phone)

    again = await client.post(
        f"/api/v1/apply/{setup['unit']['id']}",
        json=application_payload(setup["unit"]["id"], phone_number=phone),
    )

    assert again.status_code == 409
    assert "already have an application open" in again.json()["detail"]


async def test_an_application_needs_a_stated_income(owner: Actor, client: AsyncClient) -> None:
    setup = await vacant_unit(owner)

    response = await client.post(
        f"/api/v1/apply/{setup['unit']['id']}",
        json=application_payload(setup["unit"]["id"], monthly_income=None),
    )

    assert response.status_code == 422


# --------------------------------------------------------------------- scoring


async def test_a_comfortable_income_scores_better_than_a_stretched_one(owner: Actor) -> None:
    setup = await vacant_unit(owner, rent="30000.00")

    comfortable = await make_application(owner, setup["unit"]["id"], monthly_income="150000.00")
    # 20% of income vs 75% of income, same everything else.
    stretched = await make_application(
        owner,
        setup["unit"]["id"],
        phone_number=unique_phone(),
        national_id="39999999",
        monthly_income="40000.00",
    )

    assert comfortable["score"] > stretched["score"]
    assert comfortable["score_breakdown"]["income_ratio"] == 20.0
    assert comfortable["score_breakdown"]["income_ratio_exceeded"] is False
    assert stretched["score_breakdown"]["income_ratio_exceeded"] is True


async def test_the_score_breaks_down_into_four_explainable_components(owner: Actor) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(owner, setup["unit"]["id"])

    labels = [c["label"] for c in application["score_breakdown"]["components"]]
    assert labels == [
        "Application completeness",
        "Affordability",
        "Guarantor",
        "Landlord reference",
    ]
    assert sum(c["max"] for c in application["score_breakdown"]["components"]) == 100
    assert application["band"] in {"green", "amber", "red"}


async def test_unemployed_applicants_are_discounted_for_income_stability(owner: Actor) -> None:
    setup = await vacant_unit(owner, rent="10000.00")

    employed = await make_application(owner, setup["unit"]["id"], monthly_income="100000.00")
    unemployed = await make_application(
        owner,
        setup["unit"]["id"],
        phone_number=unique_phone(),
        national_id="38888888",
        employment_status="unemployed",
        employer_name="None",
        monthly_income="100000.00",
    )

    # Same ratio, but income that cannot be verified is worth less.
    assert employed["score"] > unemployed["score"]


# ------------------------------------------------------------------ guarantors


async def test_a_guarantor_is_asked_to_confirm_over_whatsapp(owner: Actor, client: AsyncClient, db) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(
        owner,
        setup["unit"]["id"],
        guarantors=[
            {
                "full_name": "Joseph Kariuki",
                "relationship_to_applicant": "Father",
                "phone_number": unique_phone(),
                "monthly_income": "200000.00",
            }
        ],
    )

    assert len(application["guarantors"]) == 1
    assert application["guarantors"][0]["status"] == "pending"

    rows = list(
        await db.scalars(
            select(Notification).where(Notification.notification_type == NotificationType.GUARANTOR_REQUEST)
        )
    )
    assert rows, "the guarantor should have been messaged"


async def test_a_guarantor_confirming_raises_the_score(owner: Actor, client: AsyncClient, db) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(
        owner,
        setup["unit"]["id"],
        guarantors=[
            {
                "full_name": "Joseph Kariuki",
                "relationship_to_applicant": "Father",
                "phone_number": unique_phone(),
            }
        ],
    )
    before = application["score"]

    # The raw token only exists in the WhatsApp message, so re-stamp one.
    from app.services.screening_service import _hash_token

    guarantor = await db.scalar(select(Guarantor).where(Guarantor.application_id == application["id"]))
    raw = "test-guarantor-token"
    guarantor.token_hash = _hash_token(raw)
    await db.commit()

    invite = await client.get(f"/api/v1/guarantee/{raw}")
    assert invite.status_code == 200
    assert invite.json()["applicant_name"] == "Amina Hassan"
    assert invite.json()["already_answered"] is False

    accepted = await client.post(f"/api/v1/guarantee/{raw}", json={"accepted": True})
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "acknowledged"

    after = (await owner.get(f"/api/v1/applications/{application['id']}")).json()
    assert after["score"] > before
    assert after["guarantors"][0]["status"] == "acknowledged"


async def test_a_guarantor_cannot_answer_twice(owner: Actor, client: AsyncClient, db) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(
        owner,
        setup["unit"]["id"],
        guarantors=[
            {
                "full_name": "Joseph Kariuki",
                "relationship_to_applicant": "Father",
                "phone_number": unique_phone(),
            }
        ],
    )

    from app.services.screening_service import _hash_token

    guarantor = await db.scalar(select(Guarantor).where(Guarantor.application_id == application["id"]))
    raw = "second-answer-token"
    guarantor.token_hash = _hash_token(raw)
    await db.commit()

    await client.post(f"/api/v1/guarantee/{raw}", json={"accepted": True})
    again = await client.post(f"/api/v1/guarantee/{raw}", json={"accepted": False})

    assert again.status_code == 409


async def test_the_deed_of_guarantee_only_goes_out_after_acknowledgement(
    owner: Actor, client: AsyncClient, db
) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(
        owner,
        setup["unit"]["id"],
        guarantors=[
            {
                "full_name": "Joseph Kariuki",
                "relationship_to_applicant": "Father",
                "phone_number": unique_phone(),
                "national_id": "22334455",
            }
        ],
    )
    guarantor_id = application["guarantors"][0]["id"]

    too_early = await owner.post(f"/api/v1/applications/{application['id']}/guarantors/{guarantor_id}/sign")
    assert too_early.status_code == 409
    assert "confirm before" in too_early.json()["detail"]

    from app.services.screening_service import _hash_token

    guarantor = await db.scalar(select(Guarantor).where(Guarantor.application_id == application["id"]))
    raw = "sign-flow-token"
    guarantor.token_hash = _hash_token(raw)
    await db.commit()
    await client.post(f"/api/v1/guarantee/{raw}", json={"accepted": True})

    signed = await owner.post(f"/api/v1/applications/{application['id']}/guarantors/{guarantor_id}/sign")
    assert signed.status_code == 200, signed.text
    assert signed.json()["guarantors"][0]["signature_id"] is not None

    # A signed guarantee is worth the full component; an acknowledged one is not.
    guarantor_component = signed.json()["score_breakdown"]["components"][2]
    assert guarantor_component["points"] == guarantor_component["max"]


# ------------------------------------------------------------ reference checks


async def test_the_previous_landlord_is_asked_automatically(owner: Actor, db) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(
        owner,
        setup["unit"]["id"],
        current_landlord_name="Mary Njeri",
        current_landlord_phone=unique_phone(),
    )

    assert len(application["references"]) == 1
    assert application["references"][0]["status"] == "sent"

    rows = list(
        await db.scalars(
            select(Notification).where(Notification.notification_type == NotificationType.REFERENCE_REQUEST)
        )
    )
    assert rows


async def test_a_negative_reference_zeroes_that_component(owner: Actor, client: AsyncClient, db) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(
        owner,
        setup["unit"]["id"],
        current_landlord_name="Mary Njeri",
        current_landlord_phone=unique_phone(),
    )

    from app.services.screening_service import _hash_token

    check = await db.scalar(select(ReferenceCheck).where(ReferenceCheck.application_id == application["id"]))
    raw = "reference-token"
    check.token_hash = _hash_token(raw)
    await db.commit()

    answered = await client.post(
        f"/api/v1/reference/{raw}",
        json={"paid_on_time": False, "would_rent_again": False, "note": "Left owing two months"},
    )
    assert answered.status_code == 200
    assert answered.json()["status"] == "negative"

    after = (await owner.get(f"/api/v1/applications/{application['id']}")).json()
    reference_component = after["score_breakdown"]["components"][3]
    assert reference_component["points"] == 0
    assert "negative" in reference_component["note"]


async def test_would_not_rent_again_is_negative_even_if_rent_arrived(
    owner: Actor, client: AsyncClient, db
) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(
        owner,
        setup["unit"]["id"],
        current_landlord_name="Mary Njeri",
        current_landlord_phone=unique_phone(),
    )

    from app.services.screening_service import _hash_token

    check = await db.scalar(select(ReferenceCheck).where(ReferenceCheck.application_id == application["id"]))
    raw = "mixed-reference-token"
    check.token_hash = _hash_token(raw)
    await db.commit()

    answered = await client.post(
        f"/api/v1/reference/{raw}", json={"paid_on_time": True, "would_rent_again": False}
    )

    assert answered.json()["status"] == "negative"


async def test_unanswered_references_are_swept_closed(owner: Actor, db) -> None:
    from app.services import screening_service

    setup = await vacant_unit(owner)
    application = await make_application(
        owner,
        setup["unit"]["id"],
        current_landlord_name="Mary Njeri",
        current_landlord_phone=unique_phone(),
    )

    check = await db.scalar(select(ReferenceCheck).where(ReferenceCheck.application_id == application["id"]))
    check.sent_at = datetime.now(UTC) - timedelta(days=9)
    await db.commit()

    assert await screening_service.sweep_stale_references(db) == 1
    after = (await owner.get(f"/api/v1/applications/{application['id']}")).json()
    assert after["references"][0]["status"] == "no_response"


# ------------------------------------------------------------------- decisions


async def test_approval_creates_a_tenant_and_reserves_the_unit(owner: Actor) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(owner, setup["unit"]["id"])

    await owner.post(f"/api/v1/applications/{application['id']}/review")
    approved = await owner.post(
        f"/api/v1/applications/{application['id']}/approve", json={"note": "Strong applicant"}
    )

    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved"
    assert body["tenant_id"] is not None
    assert body["decided_by_name"] == owner.user["full_name"]

    unit = (await owner.get(f"/api/v1/units/{setup['unit']['id']}")).json()
    assert unit["status"] == "reserved"

    tenant = (await owner.get(f"/api/v1/tenants/{body['tenant_id']}")).json()
    assert tenant["full_name"] == "Amina Hassan"


async def test_approving_one_applicant_closes_out_the_rest(owner: Actor) -> None:
    setup = await vacant_unit(owner)
    winner = await make_application(owner, setup["unit"]["id"])
    runner_up = await make_application(
        owner,
        setup["unit"]["id"],
        phone_number=unique_phone(),
        national_id="37777777",
        full_name="Brian Otieno",
    )

    await owner.post(f"/api/v1/applications/{winner['id']}/approve", json={})

    other = (await owner.get(f"/api/v1/applications/{runner_up['id']}")).json()
    assert other["status"] == "rejected"
    assert other["rejection_reason"] == "unit_taken"


async def test_the_waiting_list_ranks_by_score(owner: Actor) -> None:
    setup = await vacant_unit(owner, rent="30000.00")
    await make_application(owner, setup["unit"]["id"], monthly_income="40000.00", full_name="Weak")
    await make_application(
        owner,
        setup["unit"]["id"],
        phone_number=unique_phone(),
        national_id="36666666",
        monthly_income="200000.00",
        full_name="Strong",
    )

    ranked = (await owner.get(f"/api/v1/applications/waiting-list/{setup['unit']['id']}")).json()

    assert [row["full_name"] for row in ranked] == ["Strong", "Weak"]
    assert ranked[0]["rank"] == 1


async def test_rejection_records_a_reason_and_requires_a_note_for_other(owner: Actor) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(owner, setup["unit"]["id"])

    vague = await owner.post(f"/api/v1/applications/{application['id']}/reject", json={"reason": "other"})
    assert vague.status_code == 422

    rejected = await owner.post(
        f"/api/v1/applications/{application['id']}/reject",
        json={"reason": "insufficient_income", "note": "Rent is over half of stated income"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["rejection_reason"] == "insufficient_income"
    assert rejected.json()["decided_at"] is not None


async def test_a_decided_application_is_terminal(owner: Actor) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(owner, setup["unit"]["id"])
    await owner.post(f"/api/v1/applications/{application['id']}/approve", json={})

    again = await owner.post(
        f"/api/v1/applications/{application['id']}/reject", json={"reason": "unit_taken"}
    )

    assert again.status_code == 409


async def test_an_interview_cannot_be_scheduled_in_the_past(owner: Actor) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(owner, setup["unit"]["id"])

    response = await owner.post(
        f"/api/v1/applications/{application['id']}/interview",
        json={"scheduled_for": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
    )

    assert response.status_code == 422


async def test_applications_are_not_visible_across_organizations(owner: Actor, other_owner: Actor) -> None:
    setup = await vacant_unit(owner)
    application = await make_application(owner, setup["unit"]["id"])

    response = await other_owner.get(f"/api/v1/applications/{application['id']}")

    assert response.status_code == 403


async def test_an_occupied_unit_refuses_applications(owner: Actor, client: AsyncClient) -> None:
    from tests.test_operations import occupied_unit

    setup = await occupied_unit(owner)

    listing = await client.get(f"/api/v1/apply/{setup['unit']['id']}")
    assert listing.status_code == 404

    submitted = await client.post(
        f"/api/v1/apply/{setup['unit']['id']}", json=application_payload(setup["unit"]["id"])
    )
    assert submitted.status_code == 404
