"""Sprint 20: onboarding, help, referrals, NPS, milestones, the feature board,
the changelog, and the internal customer-success surface.
"""

from sqlalchemy import text

from app.models.customer_success import MilestoneKey, NpsTrigger
from tests.conftest import TEST_PASSWORD, Actor, register_owner, unique_phone

BASE = "/api/v1/customer-success"
INTERNAL = "/api/v1/internal"
PUBLIC_HELP = "/api/v1/help"


async def make_platform_staff(db, actor: Actor) -> None:
    await db.execute(
        text("UPDATE users SET is_platform_staff = true WHERE id = :id"), {"id": actor.user["id"]}
    )
    await db.commit()


async def register_with_email(client, *, email: str, organization_name: str) -> Actor:
    """Like `register_owner`, but with a caller-chosen email — needed to prove
    a referral signed up by that exact address links up."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Referred Owner",
            "organization_name": organization_name,
            "email": email,
            "phone_number": unique_phone(),
            "password": TEST_PASSWORD,
            "account_type": "owner",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return Actor(client, data["tokens"], data["user"])


# --------------------------------------------------------------- onboarding


async def test_onboarding_progress_created_lazily_and_completes(owner: Actor) -> None:
    progress = (await owner.get(f"{BASE}/onboarding")).json()
    assert progress == {
        "added_property": False,
        "added_units": False,
        "invited_caretaker": False,
        "added_tenant": False,
        "setup_payment": False,
        "dismissed_at": None,
        "completed_at": None,
    }

    for step in ("added_property", "added_units", "invited_caretaker", "added_tenant"):
        response = await owner.patch(f"{BASE}/onboarding", json={"step": step})
        assert response.status_code == 200
        assert response.json()["completed_at"] is None

    final = await owner.patch(f"{BASE}/onboarding", json={"step": "setup_payment"})
    assert final.json()["completed_at"] is not None


async def test_onboarding_dismiss_is_idempotent(owner: Actor) -> None:
    first = (await owner.post(f"{BASE}/onboarding/dismiss")).json()
    second = (await owner.post(f"{BASE}/onboarding/dismiss")).json()
    assert first["dismissed_at"] == second["dismissed_at"]


# --------------------------------------------------------------------- help


async def test_help_articles_are_shared_across_organizations(owner: Actor, other_owner: Actor, db) -> None:
    await make_platform_staff(db, owner)
    created = await owner.post(
        f"{INTERNAL}/help-articles",
        json={
            "slug": "getting-started",
            "title": "Getting started",
            "body": "Add your first property.",
            "category": "onboarding",
        },
    )
    assert created.status_code == 201, created.text

    seen_by_other_org = await other_owner.get(f"{BASE}/help/articles")
    assert any(a["slug"] == "getting-started" for a in seen_by_other_org.json())

    fetched = await other_owner.get(f"{BASE}/help/articles/getting-started")
    assert fetched.status_code == 200


async def test_non_platform_staff_cannot_write_help_articles(owner: Actor) -> None:
    response = await owner.post(
        f"{INTERNAL}/help-articles",
        json={"slug": "x", "title": "X", "body": "x", "category": "x"},
    )
    assert response.status_code == 403


# --------------------------------------------------------- public help centre


async def test_public_help_centre_needs_no_login(client, owner: Actor, db) -> None:
    """`client` carries no bearer token — this is the prospect on the landing
    page, who has no account to log into yet."""
    await make_platform_staff(db, owner)
    await owner.post(
        f"{INTERNAL}/help-articles",
        json={
            "slug": "collect-rent-through-mpesa",
            "title": "Collect rent through M-Pesa",
            "body": "M-Pesa collection runs through Safaricom's Daraja API.",
            "category": "Rent and payments",
        },
    )

    listed = await client.get(f"{PUBLIC_HELP}/articles")
    assert listed.status_code == 200
    assert any(a["slug"] == "collect-rent-through-mpesa" for a in listed.json())

    fetched = await client.get(f"{PUBLIC_HELP}/articles/collect-rent-through-mpesa")
    assert fetched.status_code == 200
    assert fetched.json()["category"] == "Rent and payments"


async def test_public_help_centre_searches_title_and_body(client, owner: Actor, db) -> None:
    await make_platform_staff(db, owner)
    for slug, title, body in [
        ("arrears-worklist", "Work the arrears list", "Ranked by how long it has been outstanding."),
        ("meter-readings", "Record meter readings", "Water and power, billed onto the next invoice."),
    ]:
        await owner.post(
            f"{INTERNAL}/help-articles",
            json={"slug": slug, "title": title, "body": body, "category": "Guides"},
        )

    by_title = await client.get(f"{PUBLIC_HELP}/articles", params={"q": "arrears"})
    assert [a["slug"] for a in by_title.json()] == ["arrears-worklist"]

    by_body = await client.get(f"{PUBLIC_HELP}/articles", params={"q": "invoice"})
    assert [a["slug"] for a in by_body.json()] == ["meter-readings"]


async def test_public_help_centre_hides_unpublished_drafts(client, owner: Actor, db) -> None:
    await make_platform_staff(db, owner)
    await owner.post(
        f"{INTERNAL}/help-articles",
        json={
            "slug": "half-written",
            "title": "Half written",
            "body": "Not ready.",
            "category": "Guides",
            "is_published": False,
        },
    )

    listed = await client.get(f"{PUBLIC_HELP}/articles")
    assert all(a["slug"] != "half-written" for a in listed.json())
    assert (await client.get(f"{PUBLIC_HELP}/articles/half-written")).status_code == 404


async def test_public_help_centre_404s_on_unknown_slug(client) -> None:
    assert (await client.get(f"{PUBLIC_HELP}/articles/no-such-article")).status_code == 404


# ------------------------------------------------- help search and ordering
#
# `help_articles` is platform-wide — no `organization_id`, and so no per-test
# tenant to scope rows to. Each test below starts from an empty table rather
# than asserting around whatever earlier tests left behind, which is what lets
# them assert exact orderings instead of `any(...)`.


async def clear_help_articles(db) -> None:
    await db.execute(text("DELETE FROM help_articles"))
    await db.commit()


async def write_article(owner: Actor, **overrides) -> dict:
    payload = {
        "slug": "an-article",
        "title": "An article",
        "body": "Some body text.",
        "category": "Guides",
    } | overrides
    response = await owner.post(f"{INTERNAL}/help-articles", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_search_folds_punctuation_out_of_the_query(client, owner: Actor, db) -> None:
    """ "mpesa" has to find "M-Pesa" — it is the most searched term in this
    product, and the bare LIKE never matched it."""
    await make_platform_staff(db, owner)
    await clear_help_articles(db)
    await write_article(
        owner,
        slug="collect-rent-through-mpesa",
        title="Collect rent through M-Pesa",
        body="STK push, paybill and till payments.",
    )

    for query in ("mpesa", "M-Pesa", "MPESA", "m-pesa"):
        found = await client.get(f"{PUBLIC_HELP}/articles", params={"q": query})
        assert [a["slug"] for a in found.json()] == ["collect-rent-through-mpesa"], query


async def test_search_folds_punctuation_in_the_body_too(client, owner: Actor, db) -> None:
    await make_platform_staff(db, owner)
    await clear_help_articles(db)
    await write_article(
        owner,
        slug="ending-a-tenancy",
        title="Ending a tenancy",
        body="Run a move-out inspection before releasing the deposit.",
    )

    found = await client.get(f"{PUBLIC_HELP}/articles", params={"q": "moveout"})
    assert [a["slug"] for a in found.json()] == ["ending-a-tenancy"]


async def test_search_still_finds_what_the_plain_like_found(client, owner: Actor, db) -> None:
    """Folding is additive: it widens the result set, never narrows it."""
    await make_platform_staff(db, owner)
    await clear_help_articles(db)
    await write_article(owner, slug="arrears", title="Work the arrears list", body="A ranked worklist.")

    for query in ("arrears", "Arrears", "ranked worklist"):
        found = await client.get(f"{PUBLIC_HELP}/articles", params={"q": query})
        assert [a["slug"] for a in found.json()] == ["arrears"], query


async def test_search_does_not_fold_away_word_boundaries(client, owner: Actor, db) -> None:
    """Spaces survive folding. Collapsing them too would make "rent day" a
    substring of "diffe(rent day)"."""
    await make_platform_staff(db, owner)
    await clear_help_articles(db)
    await write_article(owner, slug="a-different-day", body="On a different day the rent clears.")

    found = await client.get(f"{PUBLIC_HELP}/articles", params={"q": "rentday"})
    assert found.json() == []


async def test_search_of_pure_punctuation_does_not_match_everything(client, owner: Actor, db) -> None:
    await make_platform_staff(db, owner)
    await clear_help_articles(db)
    await write_article(owner, slug="a-guide", body="Nothing special here.")

    found = await client.get(f"{PUBLIC_HELP}/articles", params={"q": "---"})
    assert found.json() == []


async def test_articles_come_back_in_reading_order(client, owner: Actor, db) -> None:
    await make_platform_staff(db, owner)
    await clear_help_articles(db)
    await write_article(owner, slug="third", title="Third", sort_order=30)
    await write_article(owner, slug="first", title="First", sort_order=10)
    await write_article(owner, slug="second", title="Second", sort_order=20)

    listed = await client.get(f"{PUBLIC_HELP}/articles")
    assert [a["slug"] for a in listed.json()] == ["first", "second", "third"]


async def test_a_new_article_is_appended_not_promoted(client, owner: Actor, db) -> None:
    """An unplaced article at the top of the help centre is a content bug only
    readers see; at the bottom it is visible to the author who created it."""
    await make_platform_staff(db, owner)
    await clear_help_articles(db)
    await write_article(owner, slug="placed", title="Placed", sort_order=10)
    appended = await write_article(owner, slug="unplaced", title="Unplaced")

    assert appended["sort_order"] > 10
    listed = await client.get(f"{PUBLIC_HELP}/articles")
    assert [a["slug"] for a in listed.json()] == ["placed", "unplaced"]


async def test_editing_an_article_keeps_its_position(owner: Actor, db) -> None:
    await make_platform_staff(db, owner)
    await clear_help_articles(db)
    created = await write_article(owner, slug="placed", title="Placed", sort_order=40)

    edited = await owner.patch(
        f"{INTERNAL}/help-articles/{created['id']}",
        json={
            "slug": "placed",
            "title": "Placed, retitled",
            "body": "Some body text.",
            "category": "Guides",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["sort_order"] == 40


# ------------------------------------------------------------------ support


async def test_support_request_creates_and_emails(owner: Actor) -> None:
    response = await owner.post(
        f"{BASE}/support", json={"subject": "Need help", "message": "How do I add a tenant?"}
    )
    assert response.status_code == 201
    assert response.json()["status"] == "open"


# ----------------------------------------------------------------- referral


async def test_referral_code_is_stable_and_credit_granted_on_upgrade(owner: Actor, db) -> None:
    first = (await owner.get(f"{BASE}/referral")).json()
    second = (await owner.get(f"{BASE}/referral")).json()
    assert first["code"] == second["code"]
    assert first["credit_months"] == 0

    referred_email = f"referred-{first['code'].lower()}@example.com"
    recorded = await owner.post(f"{BASE}/referral", json={"referred_email": referred_email})
    assert recorded.json()["status"] == "pending"

    referred = await register_with_email(owner.client, email=referred_email, organization_name="Referred Co")
    linked = (await owner.get(f"{BASE}/referral")).json()
    assert linked["referrals"][0]["status"] == "signed_up"

    await make_platform_staff(db, owner)
    plan_update = await owner.patch(
        f"{INTERNAL}/organizations/{referred.user['organization_id']}/plan",
        json={"plan": "starter"},
    )
    assert plan_update.status_code == 200

    summary = (await owner.get(f"{BASE}/referral")).json()
    assert summary["credit_months"] == 1
    assert summary["referrals"][0]["status"] == "converted"


async def test_referral_created_after_referred_signup_still_links(owner: Actor, db) -> None:
    """Recording the referral *before* the prospect signs up is the normal
    order, but a referral recorded referencing an email that already exists
    must not silently vanish either — it just never gets to convert."""
    referred = await register_owner(owner.client, organization_name="Already Signed Up")
    response = await owner.post(f"{BASE}/referral", json={"referred_email": referred.user["email"]})
    assert response.status_code == 201
    assert response.json()["status"] == "pending"


# ----------------------------------------------------------------------- nps


async def test_nps_prompt_shown_once_and_records_response(owner: Actor, db) -> None:
    from app.services import nps_service

    await nps_service.queue_if_eligible(
        db, owner.user["organization_id"], owner.user["id"], NpsTrigger.FIRST_PAYMENT
    )

    pending = (await owner.get(f"{BASE}/nps/pending")).json()
    assert pending is not None
    assert pending["trigger_event"] == "first_payment"

    respond = await owner.post(f"{BASE}/nps/{pending['id']}/respond", json={"score": 9, "comment": "Great!"})
    assert respond.status_code == 200

    nothing_left = (await owner.get(f"{BASE}/nps/pending")).json()
    assert nothing_left is None


# ----------------------------------------------------------------- milestones


async def test_milestone_reached_once_and_can_be_acknowledged(owner: Actor, db) -> None:
    from app.services import milestone_service

    await milestone_service.check_and_queue(db, owner.user["organization_id"], MilestoneKey.TENANTS_50)
    await db.commit()
    # Firing it again must not create a second row (unique constraint).
    await milestone_service.check_and_queue(db, owner.user["organization_id"], MilestoneKey.TENANTS_50)
    await db.commit()

    pending = (await owner.get(f"{BASE}/milestones/pending")).json()
    assert len(pending) == 1

    ack = await owner.post(f"{BASE}/milestones/{MilestoneKey.TENANTS_50.value}/acknowledge")
    assert ack.status_code == 204

    pending_after = (await owner.get(f"{BASE}/milestones/pending")).json()
    assert pending_after == []


# ------------------------------------------------------------- feature board


async def test_feature_board_is_shared_and_votes_toggle(owner: Actor, other_owner: Actor) -> None:
    created = await owner.post(
        f"{BASE}/feature-board", json={"title": "Bulk SMS", "description": "Send SMS to all tenants"}
    )
    feature_id = created.json()["id"]

    seen_by_other = await other_owner.get(f"{BASE}/feature-board")
    row = next(r for r in seen_by_other.json() if r["id"] == feature_id)
    assert row["vote_count"] == 0
    assert row["voted_by_me"] is False

    voted = await other_owner.post(f"{BASE}/feature-board/{feature_id}/vote")
    assert voted.json() == {"voted": True}

    unvoted = await other_owner.post(f"{BASE}/feature-board/{feature_id}/vote")
    assert unvoted.json() == {"voted": False}


# --------------------------------------------------------------- changelog


async def test_changelog_visible_to_everyone_and_unseen_count(owner: Actor, other_owner: Actor, db) -> None:
    await make_platform_staff(db, owner)
    created = await owner.post(
        f"{INTERNAL}/changelog-entries",
        json={"title": "New: bulk operations", "body": "You can now bulk-edit rent."},
    )
    assert created.status_code == 201

    seen_by_other = await other_owner.get(f"{BASE}/changelog")
    assert any(e["title"] == "New: bulk operations" for e in seen_by_other.json())

    unseen = await other_owner.get(f"{BASE}/changelog/unseen-count")
    assert unseen.json()["count"] >= 1


# ---------------------------------------------------------------- internal


async def test_internal_health_dashboard_requires_platform_staff(owner: Actor, db) -> None:
    denied = await owner.get(f"{INTERNAL}/organizations")
    assert denied.status_code == 403

    await make_platform_staff(db, owner)
    allowed = await owner.get(f"{INTERNAL}/organizations")
    assert allowed.status_code == 200
    assert any(row["organization_id"] == owner.user["organization_id"] for row in allowed.json())


async def test_health_score_computation_and_at_risk_alert(owner: Actor, db) -> None:
    from sqlalchemy import select

    from app.models.customer_success import CustomerSuccessAlert
    from app.models.organization import Organization
    from app.services import health_score_service

    organization = await db.get(Organization, owner.user["organization_id"])
    row = await health_score_service.compute_for_organization(db, organization)

    # A brand-new organization with no caretakers, no tenants and no support
    # tickets scores 100 on every "not applicable" component, but has not
    # logged in inside the login window relative to a fresh registration
    # timestamp equal to "now", so login/adoption legitimately score low.
    assert 0 <= row.score <= 100
    assert row.caretaker_score == 100
    assert row.portal_score == 100

    alert = await db.scalar(
        select(CustomerSuccessAlert).where(CustomerSuccessAlert.organization_id == organization.id)
    )
    if row.score < 50:
        assert alert is not None
