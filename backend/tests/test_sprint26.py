"""Sprint 26 — the masterplan features no earlier sprint had picked up.

Utility and behavioural analytics, the owner-agency management agreement,
editable message templates, the wider importer, tenant magic links, demo data,
account suspension, the breach register, dual approval for cash, the
concurrent-session cap and per-organisation encryption keys.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentStatus
from app.models.organization import Organization, OrganizationEncryptionKey
from app.models.session import Invitation, UserSession
from app.models.user import User
from app.services import notification_service
from tests.conftest import Actor, fresh_password, unique_phone
from tests.test_portfolio import make_property, make_unit
from tests.test_tenancy import make_tenancy, make_tenant

# --------------------------------------------------------------------- helpers


async def invite_staff(
    owner: Actor, client: AsyncClient, db, *, role: str = "property_manager", name: str = "Sam Kip"
) -> Actor:
    """Invite a second staff member and accept on their behalf.

    The raw invitation token only ever leaves by SMS, so the hash is rewritten
    here the same way `test_tenancy.py` does it.
    """
    from app.core.security import generate_url_token, hash_token

    invited = await owner.post(
        "/api/v1/team/invitations",
        json={"full_name": name, "phone_number": unique_phone(), "role": role},
    )
    assert invited.status_code == 201, invited.text

    invitation = await db.scalar(select(Invitation).where(Invitation.id == uuid.UUID(invited.json()["id"])))
    raw = generate_url_token()
    invitation.token_hash = hash_token(raw)
    await db.commit()

    accepted = await client.post(
        "/api/v1/invitations/accept", json={"token": raw, "password": fresh_password()}
    )
    assert accepted.status_code == 200, accepted.text
    return Actor(client, accepted.json()["tokens"], accepted.json()["user"])


async def occupied_unit(owner: Actor, **unit_overrides) -> dict:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"], **unit_overrides)
    tenant = await make_tenant(owner)
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"])
    return {"property": prop, "unit": unit, "tenant": tenant, "tenancy": tenancy}


async def set_org(owner: Actor, **fields) -> None:
    response = await owner.patch("/api/v1/organizations/me", json=fields)
    assert response.status_code == 200, response.text


# ------------------------------------------------------------------- analytics


async def test_utility_analytics_reports_trend_and_billing_efficiency(
    owner: Actor, client: AsyncClient
) -> None:
    """Consumption was computed at reading time and then never aggregated —
    which is how utility revenue leaks (Module 12)."""
    from tests.test_operations import upload_photo

    setup = await occupied_unit(owner)
    photo = await upload_photo(owner, client)
    recorded = await owner.post(
        "/api/v1/meter-readings",
        json={
            "unit_id": setup["unit"]["id"],
            "meter_type": "water",
            "current_reading": "40.00",
            "reading_date": date.today().isoformat(),
            "photo_file_id": photo,
        },
    )
    assert recorded.status_code == 201, recorded.text

    response = await owner.get("/api/v1/analytics/utilities")
    assert response.status_code == 200, response.text
    body = response.json()

    assert len(body["trend"]) == 6
    assert body["trend"][-1]["water_consumption"] == 40.0
    efficiency = body["billing_efficiency"]
    assert efficiency["readings_taken"] == 1
    # Recorded but not yet rolled into an invoice — money measured, not charged.
    assert efficiency["readings_billed"] == 0
    assert efficiency["amount_unbilled"] == 6000.0


async def test_utility_analytics_flags_a_unit_consuming_well_above_its_peers(
    owner: Actor, client: AsyncClient
) -> None:
    from tests.test_operations import upload_photo

    prop = await make_property(owner, water_rate_per_unit="100.00")
    readings = {"A1": "10.00", "A2": "11.00", "A3": "9.00", "A4": "80.00"}
    for number, value in readings.items():
        unit = await make_unit(owner, prop["id"], unit_number=number)
        photo = await upload_photo(owner, client)
        await owner.post(
            "/api/v1/meter-readings",
            json={
                "unit_id": unit["id"],
                "meter_type": "water",
                "current_reading": value,
                "reading_date": date.today().isoformat(),
                "photo_file_id": photo,
            },
        )

    body = (await owner.get("/api/v1/analytics/utilities")).json()

    flagged = body["high_consumption_units"]
    assert [row["unit_number"] for row in flagged] == ["A4"]
    assert flagged[0]["percent_above_average"] > 100


async def test_payment_behaviour_segments_a_tenant_who_has_never_been_billed(
    owner: Actor,
) -> None:
    """A brand-new tenancy is 'no history', not 'on time' — claiming a clean
    record for someone who has never been asked to pay is a lie the report
    would then be built on."""
    await occupied_unit(owner)

    body = (await owner.get("/api/v1/analytics/payment-behaviour")).json()

    assert body["segments"]["no_history"] == 1
    assert body["tenancies"][0]["invoices_assessed"] == 0


async def test_payment_behaviour_separates_prompt_from_chronically_late(owner: Actor, db) -> None:
    prompt = await occupied_unit(owner)
    late = await occupied_unit(owner)

    today = date.today()
    for setup, days_late in ((prompt, 0), (late, 20)):
        for months_back in (2, 1):
            period = (today.replace(day=1) - timedelta(days=32 * months_back)).replace(day=1)
            invoice = Invoice(
                organization_id=uuid.UUID(setup["tenancy"]["organization_id"]),
                tenancy_id=uuid.UUID(setup["tenancy"]["id"]),
                reference_code=f"INV-{uuid.uuid4().hex[:10]}",
                period_start=period,
                period_end=period + timedelta(days=27),
                issue_date=period,
                due_date=period,
                status=InvoiceStatus.PAID,
                total=Decimal("25000.00"),
                amount_paid=Decimal("25000.00"),
            )
            db.add(invoice)
            await db.flush()
            db.add(
                Payment(
                    organization_id=invoice.organization_id,
                    reference_code=f"PMT-{uuid.uuid4().hex[:10]}",
                    tenancy_id=invoice.tenancy_id,
                    invoice_id=invoice.id,
                    amount=Decimal("25000.00"),
                    method="mpesa",
                    status=PaymentStatus.CONFIRMED,
                    payment_date=period + timedelta(days=days_late),
                    paid_at=datetime.now(UTC),
                )
            )
    await db.commit()

    body = (await owner.get("/api/v1/analytics/payment-behaviour")).json()
    by_tenancy = {row["tenancy_id"]: row for row in body["tenancies"]}

    assert by_tenancy[prompt["tenancy"]["id"]]["segment"] == "on_time"
    chronic = by_tenancy[late["tenancy"]["id"]]
    assert chronic["segment"] == "chronically_late"
    assert chronic["paid_late"] == 2
    assert chronic["average_days_late"] == 20.0


async def test_turnover_reports_rate_and_average_tenancy_length(owner: Actor) -> None:
    """`property_performance` returned occupancy and collection only — how often
    tenants leave, and how long they stay, was never computed (Module 12)."""
    staying = await occupied_unit(owner)
    leaving = await occupied_unit(owner)

    vacated = await owner.post(
        f"/api/v1/tenancies/{leaving['tenancy']['id']}/vacate",
        json={"move_out_date": date.today().isoformat()},
    )
    assert vacated.status_code == 200, vacated.text

    body = (await owner.get("/api/v1/analytics/turnover")).json()

    assert body["active_tenancies"] == 1
    assert body["moved_out"] == 1
    assert body["turnover_rate_percent"] == 50.0
    assert body["average_tenancy_months"] is not None
    assert staying["tenancy"]["id"]


async def test_analytics_are_scoped_to_the_organization(owner: Actor, other_owner: Actor) -> None:
    await occupied_unit(owner)

    body = (await other_owner.get("/api/v1/analytics/payment-behaviour")).json()

    assert body["tenancies"] == []


# ---------------------------------------------------------- dual cash approval


async def test_large_cash_is_held_until_a_second_person_approves(
    owner: Actor, client: AsyncClient, db
) -> None:
    """One person must not be able to both take the money and declare it banked."""
    manager = await invite_staff(owner, client, db)
    await set_org(owner, cash_dual_approval_threshold="10000")
    setup = await occupied_unit(owner)

    recorded = await manager.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "25000.00",
            "method": "cash",
            "payment_date": date.today().isoformat(),
        },
    )
    assert recorded.status_code == 201, recorded.text
    payment = recorded.json()
    assert payment["requires_approval"] is True
    assert payment["status"] == "pending"
    # Nothing is banked yet: no receipt, and the invoice is untouched.
    assert payment["receipt"] is None

    queue = await owner.get("/api/v1/payments/pending-approval")
    assert [row["id"] for row in queue.json()] == [payment["id"]]

    approved = await owner.post(f"/api/v1/payments/{payment['id']}/approve", json={"note": "Counted"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "confirmed"
    assert approved.json()["requires_approval"] is False
    assert approved.json()["receipt"] is not None


async def test_the_person_who_recorded_the_cash_cannot_approve_it(
    owner: Actor, client: AsyncClient, db
) -> None:
    manager = await invite_staff(owner, client, db)
    await set_org(owner, cash_dual_approval_threshold="10000")
    setup = await occupied_unit(owner)

    payment = (
        await manager.post(
            "/api/v1/payments",
            json={
                "tenancy_id": setup["tenancy"]["id"],
                "amount": "25000.00",
                "method": "cash",
                "payment_date": date.today().isoformat(),
            },
        )
    ).json()

    refused = await manager.post(f"/api/v1/payments/{payment['id']}/approve", json={})
    assert refused.status_code == 403
    assert "cannot approve a payment you recorded" in refused.json()["detail"]


async def test_rejecting_held_cash_never_credits_the_tenancy(owner: Actor, client: AsyncClient, db) -> None:
    manager = await invite_staff(owner, client, db)
    await set_org(owner, cash_dual_approval_threshold="10000")
    setup = await occupied_unit(owner)

    payment = (
        await manager.post(
            "/api/v1/payments",
            json={
                "tenancy_id": setup["tenancy"]["id"],
                "amount": "25000.00",
                "method": "cash",
                "payment_date": date.today().isoformat(),
            },
        )
    ).json()

    rejected = await owner.post(
        f"/api/v1/payments/{payment['id']}/reject", json={"reason": "Cash never handed in"}
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "cancelled"

    stored = await db.scalar(select(Payment).where(Payment.id == uuid.UUID(payment["id"])))
    assert stored.invoice_id is None


async def test_cash_below_the_threshold_is_banked_immediately(owner: Actor) -> None:
    await set_org(owner, cash_dual_approval_threshold="50000")
    setup = await occupied_unit(owner)

    recorded = await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "25000.00",
            "method": "cash",
            "payment_date": date.today().isoformat(),
        },
    )

    assert recorded.json()["requires_approval"] is False
    assert recorded.json()["status"] == "confirmed"


async def test_a_solo_landlord_is_not_locked_out_by_their_own_threshold(owner: Actor) -> None:
    """Nobody else can approve, so holding the payment would strand it in a
    queue only the person who recorded it could clear."""
    await set_org(owner, cash_dual_approval_threshold="1000")
    setup = await occupied_unit(owner)

    recorded = await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "25000.00",
            "method": "cash",
            "payment_date": date.today().isoformat(),
        },
    )

    assert recorded.json()["requires_approval"] is False
    assert recorded.json()["status"] == "confirmed"


async def test_mpesa_above_the_threshold_is_not_held(owner: Actor, client: AsyncClient, db) -> None:
    """M-Pesa carries Safaricom's own confirmation — cash is the only channel
    where one person's word is the whole evidence."""
    await invite_staff(owner, client, db)
    await set_org(owner, cash_dual_approval_threshold="1000")
    setup = await occupied_unit(owner)

    recorded = await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "25000.00",
            "method": "mpesa",
            "reference": f"REF{uuid.uuid4().hex[:8].upper()}",
            "payment_date": date.today().isoformat(),
        },
    )

    assert recorded.json()["requires_approval"] is False


# ------------------------------------------------------- concurrent sessions


async def test_the_oldest_session_is_revoked_once_the_cap_is_reached(
    owner: Actor, client: AsyncClient, db
) -> None:
    """Driven through `session_service` rather than `/auth/login`, which returns
    an OTP challenge for an untrusted device — the cap is what is under test
    here, not the second factor in front of it."""
    from app.models.user import User
    from app.services import session_service

    await set_org(owner, max_concurrent_sessions=2)
    user = await db.get(User, uuid.UUID(owner.user["id"]))

    opened = []
    for _ in range(3):
        session, tokens = await session_service.create_session(db, user)
        await db.commit()
        opened.append((session, tokens))

    live = list(
        await db.scalars(
            select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        )
    )
    # Three logins, a cap of two: the newest survives and the oldest is cut.
    assert len(live) == 2
    assert opened[0][0].id not in {session.id for session in live}
    assert opened[-1][0].id in {session.id for session in live}

    # Signing in must never fail because you already had too many sessions.
    newest = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {opened[-1][1].access_token}"},
    )
    assert newest.status_code == 200


# ----------------------------------------------------------- tenant magic link


async def test_magic_link_signs_a_tenant_in_without_their_password(
    owner: Actor, client: AsyncClient, db
) -> None:
    from app.core.security import generate_url_token, hash_token
    from app.models.session import TokenPurpose, VerificationToken

    setup = await occupied_unit(owner)
    invited = await owner.post("/api/v1/portal/invite", json={"tenant_id": setup["tenant"]["id"]})
    assert invited.status_code == 200, invited.text

    # Accept the invitation so a portal login exists to sign back into. The
    # scratch database is shared across the run, so the token is found by its
    # own hash rather than by taking the first invite of this purpose.
    invite_token = await db.scalar(
        select(VerificationToken)
        .where(VerificationToken.purpose == TokenPurpose.TENANT_PORTAL_INVITE)
        .order_by(VerificationToken.created_at.desc())
        .limit(1)
    )
    raw_invite = generate_url_token()
    invite_token.token_hash = hash_token(f"{setup['tenant']['id']}:{raw_invite}")
    await db.commit()
    setup_response = await client.post(
        f"/api/v1/portal/setup?tenant_id={setup['tenant']['id']}",
        json={"token": raw_invite, "password": fresh_password()},
    )
    assert setup_response.status_code == 200, setup_response.text

    # The magic-link token is keyed to this tenant's portal login, which is what
    # keeps the lookup below unambiguous in a shared database.
    from app.models.tenant import Tenant

    tenant_row = await db.get(Tenant, uuid.UUID(setup["tenant"]["id"]))
    await db.refresh(tenant_row)
    portal_user_id = str(tenant_row.portal_user_id)

    requested = await client.post(
        "/api/v1/portal/magic-link", json={"phone_number": setup["tenant"]["phone_number"]}
    )
    assert requested.status_code == 200

    magic = await db.scalar(
        select(VerificationToken)
        .where(
            VerificationToken.purpose == TokenPurpose.TENANT_PORTAL_MAGIC_LINK,
            VerificationToken.user_id == uuid.UUID(portal_user_id),
        )
        .order_by(VerificationToken.created_at.desc())
        .limit(1)
    )
    assert magic is not None
    raw = generate_url_token()
    magic.token_hash = hash_token(f"{setup['tenant']['id']}:{raw}")
    await db.commit()

    signed_in = await client.post(
        "/api/v1/portal/magic-link/verify", json={"token": raw, "tenant_id": setup["tenant"]["id"]}
    )
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["tenant_id"] == setup["tenant"]["id"]

    # Single use.
    replayed = await client.post(
        "/api/v1/portal/magic-link/verify", json={"token": raw, "tenant_id": setup["tenant"]["id"]}
    )
    assert replayed.status_code == 400


async def test_magic_link_does_not_reveal_whether_a_number_is_a_tenant(
    client: AsyncClient,
) -> None:
    """Otherwise the endpoint is a directory: walk a range of Kenyan mobile
    numbers and learn which belong to tenants of which landlord."""
    unknown = await client.post("/api/v1/portal/magic-link", json={"phone_number": unique_phone()})

    assert unknown.status_code == 200
    assert "on its way" in unknown.json()["message"]


# ------------------------------------------------------------------ demo data


async def test_demo_data_fills_the_account_and_removes_exactly_what_it_added(
    owner: Actor,
) -> None:
    before = await owner.get("/api/v1/properties")
    assert before.json() == []

    loaded = await owner.post("/api/v1/organizations/demo-data")
    assert loaded.status_code == 201, loaded.text
    assert loaded.json()["row_count"] > 20

    properties = (await owner.get("/api/v1/properties")).json()
    assert len(properties) == 1
    tenants = (await owner.get("/api/v1/tenants")).json()
    assert len(tenants) == 4

    # The sample portfolio has to make the reports look like a real one.
    behaviour = (await owner.get("/api/v1/analytics/payment-behaviour")).json()
    assert behaviour["segments"]["on_time"] >= 1
    assert behaviour["segments"]["non_paying"] >= 1

    removed = await owner.delete("/api/v1/organizations/demo-data")
    assert removed.status_code == 200, removed.text
    assert (await owner.get("/api/v1/properties")).json() == []
    assert (await owner.get("/api/v1/organizations/demo-data")).json()["loaded"] is False


async def test_demo_data_does_not_touch_a_real_property(owner: Actor) -> None:
    """Teardown walks a recorded ledger of ids, so it cannot match a real row
    by name or by heuristic."""
    mine = await make_property(owner, name="My Actual Building")
    await owner.post("/api/v1/organizations/demo-data")

    await owner.delete("/api/v1/organizations/demo-data")

    remaining = (await owner.get("/api/v1/properties")).json()
    assert [p["id"] for p in remaining] == [mine["id"]]


async def test_sample_data_cannot_be_loaded_twice(owner: Actor) -> None:
    await owner.post("/api/v1/organizations/demo-data")
    again = await owner.post("/api/v1/organizations/demo-data")

    assert again.status_code == 409


# ------------------------------------------------------- communication templates


async def test_a_custom_template_replaces_the_built_in_wording(owner: Actor, db) -> None:
    from app.models.notification import Notification, NotificationType

    saved = await owner.put(
        "/api/v1/message-templates",
        json={
            "notification_type": "payment_confirmed",
            "channel": "any",
            "body": "Asante {{tenant_name}}. We received KES {{amount}}. Balance: KES {{balance}}.",
        },
    )
    assert saved.status_code == 200, saved.text

    setup = await occupied_unit(owner)
    await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "25000.00",
            "method": "cash",
            "payment_date": date.today().isoformat(),
        },
    )

    notification = await db.scalar(
        select(Notification)
        .where(Notification.notification_type == NotificationType.PAYMENT_CONFIRMED)
        .order_by(Notification.created_at.desc())
    )
    assert notification.body.startswith("Asante ")
    assert "25,000.00" in notification.body


async def test_a_template_using_an_unknown_placeholder_is_refused(owner: Actor) -> None:
    """A template that silently never renders would leave the landlord thinking
    they had rewritten a message when every send still used the default."""
    response = await owner.put(
        "/api/v1/message-templates",
        json={
            "notification_type": "rent_reminder",
            "channel": "sms",
            "body": "Hi {{tenant_name}}, you owe {{made_up_field}}.",
        },
    )

    assert response.status_code == 400
    assert "made_up_field" in response.json()["detail"]


async def test_deleting_a_template_restores_the_built_in_wording(owner: Actor) -> None:
    saved = await owner.put(
        "/api/v1/message-templates",
        json={"notification_type": "welcome", "channel": "any", "body": "Karibu {{full_name}}."},
    )
    template_id = saved.json()["id"]

    removed = await owner.delete(f"/api/v1/message-templates/{template_id}")
    assert removed.status_code == 200

    assert (await owner.get("/api/v1/message-templates")).json() == []


async def test_template_preview_fills_in_sample_values_and_counts_sms_segments(
    owner: Actor,
) -> None:
    response = await owner.post(
        "/api/v1/message-templates/preview",
        json={"notification_type": "rent_reminder", "body": "Hi {{tenant_name}}, KES {{amount}} due."},
    )

    body = response.json()
    assert body["body"] == "Hi Jane Wanjiru, KES 25,000.00 due."
    assert body["sms_segments"] == 1
    assert "tenant_name" in body["available_variables"]


async def test_templates_are_isolated_per_organization(owner: Actor, other_owner: Actor) -> None:
    await owner.put(
        "/api/v1/message-templates",
        json={"notification_type": "welcome", "channel": "any", "body": "Karibu {{full_name}}."},
    )

    assert (await other_owner.get("/api/v1/message-templates")).json() == []


# ------------------------------------------------------ account suspension


async def test_suspending_an_account_locks_it_out_and_says_why(owner: Actor, client: AsyncClient, db) -> None:
    staff_user = owner.user
    organization_id = staff_user["organization_id"]

    # Promote this owner to platform staff so they can drive the internal API.
    from app.models.user import User

    user = await db.get(User, uuid.UUID(staff_user["id"]))
    user.is_platform_staff = True
    await db.commit()

    victim = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Ann Mumbi",
            "organization_name": f"Suspendable {uuid.uuid4().hex[:6]}",
            "email": f"ann-{uuid.uuid4().hex[:8]}@example.com",
            "phone_number": unique_phone(),
            "password": fresh_password(),
            "account_type": "owner",
        },
    )
    victim_actor = Actor(client, victim.json()["tokens"], victim.json()["user"])
    victim_org = victim.json()["user"]["organization_id"]

    assert (await victim_actor.get("/api/v1/properties")).status_code == 200

    suspended = await owner.post(
        f"/api/v1/internal/organizations/{victim_org}/suspend",
        json={"reason": "Subscription unpaid for 60 days"},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["is_active"] is False

    blocked = await victim_actor.get("/api/v1/properties")
    assert blocked.status_code in (401, 403)

    reactivated = await owner.post(f"/api/v1/internal/organizations/{victim_org}/reactivate")
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["is_active"] is True
    assert organization_id


async def test_only_platform_staff_can_suspend_an_account(owner: Actor) -> None:
    response = await owner.post(
        f"/api/v1/internal/organizations/{owner.user['organization_id']}/suspend",
        json={"reason": "Trying it on"},
    )

    assert response.status_code == 403


# ------------------------------------------------------------- breach register


@pytest.fixture
async def platform_staff(owner: Actor, db) -> Actor:
    from app.models.user import User

    user = await db.get(User, uuid.UUID(owner.user["id"]))
    user.is_platform_staff = True
    await db.commit()
    return owner


async def test_reporting_a_breach_starts_the_72_hour_clock(platform_staff: Actor) -> None:
    response = await platform_staff.post(
        "/api/v1/internal/breaches",
        json={
            "category": "unauthorised_access",
            "severity": "high",
            "summary": "A former employee's account was used after they left",
            "affected_organization_ids": [platform_staff.user["organization_id"]],
            "affected_subject_count": 40,
        },
    )

    assert response.status_code == 201, response.text
    breach = response.json()
    assert breach["reference_code"].startswith("BR-")
    assert breach["status"] == "detected"
    # 72 hours from detection, per Kenya DPA s.43.
    assert 71 < breach["hours_remaining"] <= 72


async def test_a_notifiable_breach_cannot_be_closed_before_the_regulator_is_told(
    platform_staff: Actor,
) -> None:
    breach = (
        await platform_staff.post(
            "/api/v1/internal/breaches",
            json={
                "category": "data_exfiltration",
                "severity": "critical",
                "summary": "Tenant records were copied out of the export endpoint",
            },
        )
    ).json()

    refused = await platform_staff.post(
        f"/api/v1/internal/breaches/{breach['id']}/advance",
        json={"new_status": "closed", "note": "Nothing to see here"},
    )
    assert refused.status_code == 409
    assert "Data Commissioner" in refused.json()["detail"]


async def test_marking_a_breach_notified_requires_the_regulator_reference(
    platform_staff: Actor,
) -> None:
    breach = (
        await platform_staff.post(
            "/api/v1/internal/breaches",
            json={
                "category": "credential_compromise",
                "severity": "high",
                "summary": "Credential stuffing succeeded against two accounts",
            },
        )
    ).json()

    without = await platform_staff.post(
        f"/api/v1/internal/breaches/{breach['id']}/advance", json={"new_status": "notified"}
    )
    assert without.status_code == 400

    with_reference = await platform_staff.post(
        f"/api/v1/internal/breaches/{breach['id']}/advance",
        json={"new_status": "notified", "regulator_reference": "ODPC/2026/0091"},
    )
    assert with_reference.status_code == 200, with_reference.text
    assert with_reference.json()["regulator_notified_at"] is not None


async def test_dismissing_a_breach_demands_a_reason_on_the_record(
    platform_staff: Actor,
) -> None:
    breach = (
        await platform_staff.post(
            "/api/v1/internal/breaches",
            json={
                "category": "accidental_disclosure",
                "severity": "low",
                "summary": "A statement email listed one tenant twice",
            },
        )
    ).json()

    without = await platform_staff.post(
        f"/api/v1/internal/breaches/{breach['id']}/advance", json={"new_status": "dismissed"}
    )
    assert without.status_code == 400

    with_reason = await platform_staff.post(
        f"/api/v1/internal/breaches/{breach['id']}/advance",
        json={"new_status": "dismissed", "note": "No personal data left the account"},
    )
    assert with_reason.status_code == 200
    assert with_reason.json()["no_notification_reason"]


async def test_the_breach_dashboard_counts_what_is_overdue(platform_staff: Actor, db) -> None:
    """The register is platform-wide, and the scratch database is shared across
    the run, so this asserts on the delta rather than on absolute counts."""
    from app.models.security import SecurityBreach

    before = (await platform_staff.get("/api/v1/internal/breaches/dashboard")).json()

    created = await platform_staff.post(
        "/api/v1/internal/breaches",
        json={
            "category": "system_compromise",
            "severity": "critical",
            "summary": "Unexplained superuser query against the tenants table",
        },
    )
    assert created.status_code == 201, created.text

    breach = await db.scalar(
        select(SecurityBreach).where(SecurityBreach.id == uuid.UUID(created.json()["id"]))
    )
    breach.notification_due_at = datetime.now(UTC) - timedelta(hours=1)
    await db.commit()

    after = (await platform_staff.get("/api/v1/internal/breaches/dashboard")).json()

    assert after["open"] == before["open"] + 1
    assert after["awaiting_notification"] == before["awaiting_notification"] + 1
    assert after["overdue"] == before["overdue"] + 1
    assert after["window_hours"] == 72


async def test_a_tenant_organisation_cannot_read_the_breach_register(owner: Actor) -> None:
    assert (await owner.get("/api/v1/internal/breaches")).status_code == 403


# ---------------------------------------------------- per-organisation keys


async def test_each_organisation_gets_its_own_encryption_key(owner: Actor, other_owner: Actor, db) -> None:
    for actor in (owner, other_owner):
        saved = await actor.put(
            "/api/v1/etims/credentials",
            json={
                "kra_pin": "A012345678Z",
                "device_serial": "KRACU0300000001",
                "api_key": "cmc-key",
            },
        )
        assert saved.status_code == 200, saved.text

    # Scoped to these two organisations: the scratch database is shared across
    # the run, and every other test that saves a credential mints a key too.
    mine = uuid.UUID(owner.user["organization_id"])
    theirs = uuid.UUID(other_owner.user["organization_id"])
    keys = list(
        await db.scalars(
            select(OrganizationEncryptionKey).where(
                OrganizationEncryptionKey.organization_id.in_([mine, theirs])
            )
        )
    )
    assert {key.organization_id for key in keys} == {mine, theirs}
    assert all(key.version == 1 and key.is_active for key in keys)


async def test_rotating_a_key_leaves_older_ciphertext_readable(owner: Actor, db) -> None:
    """Rotation without a coordinated re-encryption pass is the whole point:
    one customer's key can be replaced after a scare without every other
    customer having to re-enter their credentials."""
    from app.core.crypto import decrypt_for_org, encrypt_for_org, rotate_org_key

    organization_id = uuid.UUID(owner.user["organization_id"])
    sealed_v1 = await encrypt_for_org(db, organization_id, "first-secret")
    await db.commit()

    await rotate_org_key(db, organization_id)
    sealed_v2 = await encrypt_for_org(db, organization_id, "second-secret")
    await db.commit()

    assert sealed_v1.startswith("orgk:1:")
    assert sealed_v2.startswith("orgk:2:")
    assert await decrypt_for_org(db, organization_id, sealed_v1) == "first-secret"
    assert await decrypt_for_org(db, organization_id, sealed_v2) == "second-secret"


async def test_one_organisations_ciphertext_is_inert_against_another(
    owner: Actor, other_owner: Actor, db
) -> None:
    from app.core.crypto import decrypt_for_org, encrypt_for_org

    mine = uuid.UUID(owner.user["organization_id"])
    theirs = uuid.UUID(other_owner.user["organization_id"])
    sealed = await encrypt_for_org(db, mine, "my-secret")
    await db.commit()

    # Their key exists but cannot open it.
    await encrypt_for_org(db, theirs, "their-secret")
    await db.commit()

    assert await decrypt_for_org(db, theirs, sealed) is None


# ---------------------------------------------------------- management agreement


async def agency_actor(client: AsyncClient) -> Actor:
    from tests.conftest import TEST_PASSWORD

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Agnes Kariuki",
            "organization_name": f"Kariuki Agency {uuid.uuid4().hex[:6]}",
            "email": f"agnes-{uuid.uuid4().hex[:8]}@example.com",
            "phone_number": unique_phone(),
            "password": TEST_PASSWORD,
            "account_type": "agency",
        },
    )
    assert response.status_code == 201, response.text
    return Actor(client, response.json()["tokens"], response.json()["user"])


async def test_a_management_agreement_is_drafted_from_the_owner_profile(
    client: AsyncClient,
) -> None:
    agency = await agency_actor(client)
    profile = await agency.post(
        "/api/v1/agency/owner-profiles",
        json={
            "full_name": "Peter Njenga",
            "phone_number": unique_phone(),
            "management_fee_percent": "9.50",
            "disbursement_day": 7,
        },
    )
    assert profile.status_code == 201, profile.text

    created = await agency.post(
        "/api/v1/agency/management-agreements",
        json={"owner_profile_id": profile.json()["id"], "start_date": date.today().isoformat()},
    )

    assert created.status_code == 201, created.text
    agreement = created.json()
    assert agreement["reference_code"].startswith("MGT-")
    assert agreement["status"] == "draft"
    # The terms are frozen as agreed, not read live off the profile.
    assert Decimal(agreement["management_fee_percent"]) == Decimal("9.50")
    assert agreement["disbursement_day"] == 7
    assert agreement["document_id"] is not None


async def test_editing_the_owner_profile_does_not_rewrite_a_signed_agreement(
    client: AsyncClient,
) -> None:
    agency = await agency_actor(client)
    profile = (
        await agency.post(
            "/api/v1/agency/owner-profiles",
            json={
                "full_name": "Peter Njenga",
                "phone_number": unique_phone(),
                "management_fee_percent": "9.50",
            },
        )
    ).json()
    agreement = (
        await agency.post(
            "/api/v1/agency/management-agreements",
            json={"owner_profile_id": profile["id"], "start_date": date.today().isoformat()},
        )
    ).json()

    await agency.patch(
        f"/api/v1/agency/owner-profiles/{profile['id']}", json={"management_fee_percent": "12.00"}
    )

    reloaded = await agency.get(f"/api/v1/agency/management-agreements/{agreement['id']}")
    assert Decimal(reloaded.json()["management_fee_percent"]) == Decimal("9.50")


async def test_an_agreement_activates_only_once_both_parties_have_signed(client: AsyncClient, db) -> None:
    from app.models.signature import DigitalSignature
    from app.services import management_agreement_service, signature_service

    agency = await agency_actor(client)
    profile = (
        await agency.post(
            "/api/v1/agency/owner-profiles",
            json={"full_name": "Peter Njenga", "phone_number": unique_phone()},
        )
    ).json()
    agreement = (
        await agency.post(
            "/api/v1/agency/management-agreements",
            json={"owner_profile_id": profile["id"], "start_date": date.today().isoformat()},
        )
    ).json()

    sent = await agency.post(
        f"/api/v1/agency/management-agreements/{agreement['id']}/send",
        json={"agency_signatory_name": "Agnes Kariuki", "agency_signatory_phone": unique_phone()},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "pending_signatures"

    signatures = list(
        await db.scalars(
            select(DigitalSignature).where(
                DigitalSignature.id.in_(
                    [
                        uuid.UUID(sent.json()["owner_signature_id"]),
                        uuid.UUID(sent.json()["agency_signature_id"]),
                    ]
                )
            )
        )
    )
    assert len(signatures) == 2

    # Sign the first: still not in force. An agreement one party has signed
    # binds nobody.
    signatures[0].status = "signed"
    signatures[0].signed_at = datetime.now(UTC)
    await db.commit()
    await management_agreement_service.activate_if_fully_signed(db, signatures[0])
    await db.commit()

    still_pending = await agency.get(f"/api/v1/agency/management-agreements/{agreement['id']}")
    assert still_pending.json()["status"] == "pending_signatures"

    signatures[1].status = "signed"
    signatures[1].signed_at = datetime.now(UTC)
    await db.commit()
    await management_agreement_service.activate_if_fully_signed(db, signatures[1])
    await db.commit()

    active = await agency.get(f"/api/v1/agency/management-agreements/{agreement['id']}")
    assert active.json()["status"] == "active"
    assert active.json()["activated_at"] is not None
    assert signature_service.SIGNING_LINK_EXPIRY_HOURS == 72


async def test_termination_notice_keeps_the_agreement_live_until_the_effective_date(
    client: AsyncClient, db
) -> None:
    from app.models.agency import ManagementAgreement, ManagementAgreementStatus
    from app.services import management_agreement_service

    agency = await agency_actor(client)
    profile = (
        await agency.post(
            "/api/v1/agency/owner-profiles",
            json={"full_name": "Peter Njenga", "phone_number": unique_phone()},
        )
    ).json()
    created = (
        await agency.post(
            "/api/v1/agency/management-agreements",
            json={
                "owner_profile_id": profile["id"],
                "start_date": date.today().isoformat(),
                "notice_period_days": 30,
            },
        )
    ).json()

    stored = await db.get(ManagementAgreement, uuid.UUID(created["id"]))
    stored.status = ManagementAgreementStatus.ACTIVE
    await db.commit()

    terminated = await agency.post(
        f"/api/v1/agency/management-agreements/{created['id']}/terminate",
        json={"requested_by": "owner", "reason": "Selling the building"},
    )
    assert terminated.status_code == 200, terminated.text
    assert terminated.json()["status"] == "termination_notice"
    effective = date.fromisoformat(terminated.json()["termination_effective_date"])
    assert effective == date.today() + timedelta(days=30)

    # Still live while the notice runs — obligations continue until the date.
    completed = await management_agreement_service.complete_due_terminations(db)
    assert completed == 0

    # And closed out once it passes.
    stored = await db.get(ManagementAgreement, uuid.UUID(created["id"]))
    stored.termination_effective_date = date.today() - timedelta(days=1)
    await db.commit()
    assert await management_agreement_service.complete_due_terminations(db) == 1

    ended = await agency.get(f"/api/v1/agency/management-agreements/{created['id']}")
    assert ended.json()["status"] == "terminated"


async def test_a_withdrawn_notice_returns_the_agreement_to_active(client: AsyncClient, db) -> None:
    from app.models.agency import ManagementAgreement, ManagementAgreementStatus

    agency = await agency_actor(client)
    profile = (
        await agency.post(
            "/api/v1/agency/owner-profiles",
            json={"full_name": "Peter Njenga", "phone_number": unique_phone()},
        )
    ).json()
    created = (
        await agency.post(
            "/api/v1/agency/management-agreements",
            json={"owner_profile_id": profile["id"], "start_date": date.today().isoformat()},
        )
    ).json()
    stored = await db.get(ManagementAgreement, uuid.UUID(created["id"]))
    stored.status = ManagementAgreementStatus.ACTIVE
    await db.commit()

    await agency.post(
        f"/api/v1/agency/management-agreements/{created['id']}/terminate",
        json={"requested_by": "agency"},
    )
    withdrawn = await agency.post(
        f"/api/v1/agency/management-agreements/{created['id']}/withdraw-termination"
    )

    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "active"
    assert withdrawn.json()["termination_effective_date"] is None


async def test_an_owner_mode_account_has_no_management_agreements(owner: Actor) -> None:
    """The agreement exists between an agency and its clients. In owner mode the
    account holder is the owner, and there is no second party."""
    response = await owner.post(
        "/api/v1/agency/management-agreements",
        json={"owner_profile_id": str(uuid.uuid4()), "start_date": date.today().isoformat()},
    )

    assert response.status_code == 400


# ---------------------------------------------------------------- meter OCR


async def test_a_reading_records_whether_the_operator_accepted_the_ocr_suggestion(
    owner: Actor, client: AsyncClient
) -> None:
    """`current_reading` stays what a person asserted; the OCR figure sits
    beside it as evidence of what the machine proposed."""
    from tests.test_operations import upload_photo

    setup = await occupied_unit(owner)
    photo = await upload_photo(owner, client)

    corrected = await owner.post(
        "/api/v1/meter-readings",
        json={
            "unit_id": setup["unit"]["id"],
            "meter_type": "water",
            "current_reading": "42.00",
            "reading_date": date.today().isoformat(),
            "photo_file_id": photo,
            "ocr_reading": "47.00",
            "ocr_confidence": "62.50",
        },
    )

    assert corrected.status_code == 201, corrected.text
    body = corrected.json()
    assert Decimal(body["current_reading"]) == Decimal("42.00")
    assert Decimal(body["ocr_reading"]) == Decimal("47.00")
    assert body["ocr_accepted"] is False


async def test_a_reading_with_no_ocr_records_no_verdict_at_all(owner: Actor, client: AsyncClient) -> None:
    """None, not False: 'the caretaker overrode the machine' and 'the machine
    never spoke' are different facts."""
    from tests.test_operations import upload_photo

    setup = await occupied_unit(owner)
    photo = await upload_photo(owner, client)

    recorded = await owner.post(
        "/api/v1/meter-readings",
        json={
            "unit_id": setup["unit"]["id"],
            "meter_type": "water",
            "current_reading": "42.00",
            "reading_date": date.today().isoformat(),
            "photo_file_id": photo,
        },
    )

    assert recorded.json()["ocr_accepted"] is None


async def test_meter_ocr_degrades_to_a_typed_reading_when_unconfigured(
    owner: Actor, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings as app_settings
    from tests.test_operations import upload_photo

    monkeypatch.setattr(app_settings, "ANTHROPIC_API_KEY", None)
    await occupied_unit(owner)
    photo = await upload_photo(owner, client)

    response = await owner.post("/api/v1/meter-readings/read-photo", json={"photo_file_id": photo})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reading"] is None
    assert body["high_confidence"] is False
    assert "not switched on" in body["message"]


# ------------------------------------------------------------------ importing


def _workbook(sheet_name: str, headers: list[str], rows: list[list]) -> bytes:
    import io

    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def _import(owner: Actor, kind: str, data: bytes) -> dict:
    preview = await owner.post(
        f"/api/v1/bulk/import/preview?kind={kind}",
        files={"file": ("import.xlsx", data, "application/vnd.ms-excel")},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    if body["ready"]:
        committed = await owner.post(f"/api/v1/bulk/import/commit?kind={kind}", json={"rows": body["ready"]})
        assert committed.status_code == 200, committed.text
        body["result"] = committed.json()
    return body


async def test_properties_import_from_a_spreadsheet(owner: Actor) -> None:
    """Until now the importer had one sheet — tenants — and the property had to
    exist already, which made a first migration impossible (Module 20)."""
    data = _workbook(
        "Properties",
        ["Property name", "Type", "Address", "County", "Water rate"],
        [
            ["Acacia Court", "residential", "Kiambu Road", "Nairobi", 150],
            ["Riverside Plaza", "commercial", "Riverside Drive", "Nairobi", None],
        ],
    )

    body = await _import(owner, "properties", data)

    assert body["ready_count"] == 2
    assert body["result"]["created"] == 2
    names = sorted(p["name"] for p in (await owner.get("/api/v1/properties")).json())
    assert names == ["Acacia Court", "Riverside Plaza"]


async def test_importing_a_property_that_already_exists_is_reported_not_duplicated(
    owner: Actor,
) -> None:
    await make_property(owner, name="Acacia Court")
    data = _workbook("Properties", ["Property name", "Address"], [["Acacia Court", "Kiambu Road"]])

    body = await _import(owner, "properties", data)

    assert body["ready_count"] == 0
    assert "already exists" in body["errors"][0]["reason"]


async def test_units_import_against_an_existing_property(owner: Actor) -> None:
    await make_property(owner, name="Acacia Court")
    data = _workbook(
        "Units",
        ["Property name", "Unit number", "Bedrooms", "Monthly rent", "Deposit"],
        [["Acacia Court", "B1", 2, 35000, 35000], ["Acacia Court", "B2", 1, 22000, 22000]],
    )

    body = await _import(owner, "units", data)

    assert body["result"]["created"] == 2
    units = (await owner.get("/api/v1/units")).json()
    assert sorted(u["unit_number"] for u in units) == ["B1", "B2"]


async def test_a_unit_row_for_an_unknown_property_says_which_sheet_to_run_first(
    owner: Actor,
) -> None:
    data = _workbook("Units", ["Property name", "Unit number", "Monthly rent"], [["Nowhere", "B1", 22000]])

    body = await _import(owner, "units", data)

    assert "import properties first" in body["errors"][0]["reason"]


async def test_units_cannot_be_imported_as_occupied(owner: Actor) -> None:
    """Occupancy is a consequence of a tenancy. A unit imported as occupied with
    nobody in it breaks every occupancy figure on the dashboard."""
    await make_property(owner, name="Acacia Court")
    data = _workbook(
        "Units",
        ["Property name", "Unit number", "Monthly rent", "Status"],
        [["Acacia Court", "B1", 22000, "occupied"]],
    )

    body = await _import(owner, "units", data)

    assert body["ready_count"] == 0
    assert "becomes occupied when its tenant is imported" in body["errors"][0]["reason"]


async def test_historical_payments_import_and_settle_open_invoices(owner: Actor, db) -> None:
    """Without this an imported tenant's history starts at zero, and every
    statement understates what they have actually paid."""
    setup = await occupied_unit(owner)
    period = date.today().replace(day=1)
    invoice = Invoice(
        organization_id=uuid.UUID(setup["tenancy"]["organization_id"]),
        tenancy_id=uuid.UUID(setup["tenancy"]["id"]),
        reference_code=f"INV-{uuid.uuid4().hex[:10]}",
        period_start=period,
        period_end=period + timedelta(days=27),
        issue_date=period,
        due_date=period,
        status=InvoiceStatus.PENDING,
        total=Decimal("25000.00"),
    )
    db.add(invoice)
    await db.commit()

    data = _workbook(
        "Payments",
        ["Tenant phone", "Amount", "Payment date", "Method", "Reference"],
        [[setup["tenant"]["phone_number"], 25000, date.today().isoformat(), "mpesa", "OLD-REF-1"]],
    )

    body = await _import(owner, "payments", data)

    assert body["ready"][0]["tenant_name"] == setup["tenant"]["full_name"]
    assert body["result"]["created"] == 1

    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PAID
    assert Decimal(invoice.amount_paid) == Decimal("25000.00")


async def test_a_payment_reference_already_in_rentflow_is_never_banked_twice(
    owner: Actor,
) -> None:
    setup = await occupied_unit(owner)
    reference = f"REF{uuid.uuid4().hex[:8].upper()}"
    await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "5000.00",
            "method": "mpesa",
            "reference": reference,
            "payment_date": date.today().isoformat(),
        },
    )

    data = _workbook(
        "Payments",
        ["Tenant phone", "Amount", "Payment date", "Method", "Reference"],
        [[setup["tenant"]["phone_number"], 5000, date.today().isoformat(), "mpesa", reference]],
    )
    body = await _import(owner, "payments", data)

    assert body["ready_count"] == 0
    assert "already recorded" in body["errors"][0]["reason"]


async def test_a_payment_for_an_unknown_tenant_is_reported_by_row(owner: Actor) -> None:
    data = _workbook(
        "Payments",
        ["Tenant phone", "Amount", "Payment date"],
        [["+254799999999", 5000, date.today().isoformat()]],
    )

    body = await _import(owner, "payments", data)

    assert body["errors"][0]["row"] == 2
    assert "import tenants first" in body["errors"][0]["reason"]


async def test_a_future_dated_payment_is_refused(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    data = _workbook(
        "Payments",
        ["Tenant phone", "Amount", "Payment date"],
        [
            [
                setup["tenant"]["phone_number"],
                5000,
                (date.today() + timedelta(days=1)).isoformat(),
            ]
        ],
    )

    body = await _import(owner, "payments", data)

    assert "payments already received" in body["errors"][0]["reason"]


async def test_each_import_kind_has_its_own_template(owner: Actor) -> None:
    for kind in ("properties", "units", "tenants", "payments"):
        response = await owner.get("/api/v1/bulk/import/template", params={"kind": kind})
        assert response.status_code == 200, response.text
        assert response.headers["content-disposition"].endswith(f'"rentflow-{kind}-import.xlsx"')


# ------------------------------------------------------------ video tutorials


async def test_help_articles_can_carry_a_tutorial_video(owner: Actor, client: AsyncClient, db) -> None:
    from app.models.user import User

    user = await db.get(User, uuid.UUID(owner.user["id"]))
    user.is_platform_staff = True
    await db.commit()

    created = await owner.post(
        "/api/v1/internal/help-articles",
        json={
            "slug": "record-a-payment",
            "title": "Recording a payment",
            "body": "Open the tenancy and press Record payment.",
            "category": "Payments",
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "video_provider": "youtube",
            "video_duration_seconds": 95,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["has_video"] is True

    videos = await owner.get("/api/v1/customer-success/help/articles", params={"video_only": True})
    assert [row["slug"] for row in videos.json()] == ["record-a-payment"]


async def test_a_video_url_must_be_https_and_from_a_known_provider(owner: Actor, db) -> None:
    """The frontend picks an embed player from `video_provider`; an arbitrary
    provider would mean an arbitrary iframe source."""
    from app.models.user import User

    user = await db.get(User, uuid.UUID(owner.user["id"]))
    user.is_platform_staff = True
    await db.commit()

    response = await owner.post(
        "/api/v1/internal/help-articles",
        json={
            "slug": "bad-video",
            "title": "Bad video",
            "body": "Body",
            "category": "Payments",
            "video_url": "http://example.com/clip.mp4",
            "video_provider": "youtube",
        },
    )

    assert response.status_code == 422


# ------------------------------------------------------------------ isolation


async def test_management_agreements_are_invisible_across_organizations(
    client: AsyncClient,
) -> None:
    first = await agency_actor(client)
    second = await agency_actor(client)

    profile = (
        await first.post(
            "/api/v1/agency/owner-profiles",
            json={"full_name": "Peter Njenga", "phone_number": unique_phone()},
        )
    ).json()
    agreement = (
        await first.post(
            "/api/v1/agency/management-agreements",
            json={"owner_profile_id": profile["id"], "start_date": date.today().isoformat()},
        )
    ).json()

    assert (await second.get("/api/v1/agency/management-agreements")).json() == []
    stolen = await second.get(f"/api/v1/agency/management-agreements/{agreement['id']}")
    assert stolen.status_code == 403


async def test_demo_data_is_scoped_to_the_organization_that_loaded_it(
    owner: Actor, other_owner: Actor
) -> None:
    await owner.post("/api/v1/organizations/demo-data")

    assert (await other_owner.get("/api/v1/properties")).json() == []
    assert (await other_owner.get("/api/v1/organizations/demo-data")).json()["loaded"] is False


async def test_the_organization_settings_carry_the_new_policy_fields(owner: Actor) -> None:
    await set_org(owner, cash_dual_approval_threshold="15000", max_concurrent_sessions=3)

    body = (await owner.get("/api/v1/organizations/me")).json()

    assert Decimal(body["cash_dual_approval_threshold"]) == Decimal("15000")
    assert body["max_concurrent_sessions"] == 3
    assert body["is_demo"] is False
    assert Organization  # imported for the type it documents


# ------------------------------------------------ regression: edge cases


async def test_a_zero_total_invoice_is_not_counted_as_unpaid(owner: Actor, db) -> None:
    """A tenant who owes nothing must not land in the non-paying segment because
    an invoice happened to total zero."""
    setup = await occupied_unit(owner)
    period = (date.today().replace(day=1) - timedelta(days=32)).replace(day=1)
    db.add(
        Invoice(
            organization_id=uuid.UUID(setup["tenancy"]["organization_id"]),
            tenancy_id=uuid.UUID(setup["tenancy"]["id"]),
            reference_code=f"INV-{uuid.uuid4().hex[:10]}",
            period_start=period,
            period_end=period + timedelta(days=27),
            issue_date=period,
            due_date=period,
            status=InvoiceStatus.PAID,
            total=Decimal("0.00"),
        )
    )
    await db.commit()

    body = (await owner.get("/api/v1/analytics/payment-behaviour")).json()
    row = next(r for r in body["tenancies"] if r["tenancy_id"] == setup["tenancy"]["id"])

    assert row["still_unpaid"] == 0
    assert row["segment"] == "on_time"


async def test_one_bad_payment_row_does_not_discard_the_rows_before_it(owner: Actor, db) -> None:
    """A savepoint per row. Without one, a failure late in the file would roll
    back everything already written in the same session."""
    first = await occupied_unit(owner)
    second = await occupied_unit(owner)

    # The second row's tenancy is removed between preview and commit, so its
    # insert fails on the foreign key while the first row's has already landed.
    rows = [
        {
            "row": 2,
            "phone_number": first["tenant"]["phone_number"],
            "amount": "5000.00",
            "payment_date": date.today().isoformat(),
            "method": "cash",
            "reference": None,
            "notes": None,
            "tenant_name": first["tenant"]["full_name"],
            "tenancy_id": first["tenancy"]["id"],
            "tenancy_reference": first["tenancy"]["reference_code"],
        },
        {
            "row": 3,
            "phone_number": second["tenant"]["phone_number"],
            "amount": "5000.00",
            "payment_date": date.today().isoformat(),
            "method": "cash",
            # A tenancy id that does not exist — the insert fails on the key.
            "reference": None,
            "notes": None,
            "tenant_name": second["tenant"]["full_name"],
            "tenancy_id": str(uuid.uuid4()),
            "tenancy_reference": "TCY-GONE",
        },
    ]

    committed = await owner.post("/api/v1/bulk/import/commit?kind=payments", json={"rows": rows})

    assert committed.status_code == 200, committed.text
    result = committed.json()
    assert result["created"] == 1
    assert result["failed"] == 1
    assert result["failures"][0]["row"] == 3

    banked = await db.scalars(select(Payment).where(Payment.tenancy_id == uuid.UUID(first["tenancy"]["id"])))
    assert len(list(banked)) == 1


async def test_a_custom_template_cannot_inject_markup_into_an_email(owner: Actor, db) -> None:
    """The body is plain text everywhere else; a landlord's own wording must not
    be the one path that reaches an email as raw HTML."""
    from app.models.notification import Notification, NotificationChannel, NotificationType

    await owner.put(
        "/api/v1/message-templates",
        json={
            "notification_type": "welcome",
            "channel": "email",
            "body": "Karibu {{full_name}} <script>alert(1)</script> & welcome.",
        },
    )

    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_user(await db.get(User, uuid.UUID(owner.user["id"]))),
        notification_type=NotificationType.WELCOME,
        title="Welcome",
        body="Built-in copy.",
        channels=[NotificationChannel.EMAIL],
        variables={"full_name": "Jane Wanjiru"},
    )
    await db.commit()

    stored = await db.scalar(
        select(Notification)
        .where(
            Notification.notification_type == NotificationType.WELCOME,
            Notification.channel == NotificationChannel.EMAIL,
        )
        .order_by(Notification.created_at.desc())
        .limit(1)
    )
    # The stored body is the landlord's text verbatim — the record stays
    # readable, and escaping happens on the way out to the provider.
    assert stored.body.startswith("Karibu Jane Wanjiru")
    assert "<script>" in stored.body

    rendered = notification_service.to_email_html(stored.body)
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&amp; welcome" in rendered
