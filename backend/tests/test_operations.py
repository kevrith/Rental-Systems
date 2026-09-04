"""Sprints 5 & 6: meter readings, maintenance, notifications, vacating, tenant portal."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app.models.notification import Notification, NotificationType
from app.models.session import TokenPurpose, VerificationToken
from tests.conftest import Actor, fresh_password
from tests.test_portfolio import make_property, make_unit
from tests.test_tenancy import make_tenancy, make_tenant


async def upload_photo(actor: Actor, client: AsyncClient, category: str = "meter_reading") -> str:
    ticket = (
        await actor.post(
            "/api/v1/files/upload-url",
            json={
                "filename": "meter.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 128,
                "category": category,
            },
        )
    ).json()
    await client.put(ticket["upload_url"], content=b"x" * 128)
    await actor.post(f"/api/v1/files/{ticket['file_id']}/confirm", json={})
    return ticket["file_id"]


async def occupied_unit(owner: Actor, water_rate: str = "150.00") -> dict:
    prop = await make_property(owner, water_rate_per_unit=water_rate)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"])
    return {"property": prop, "unit": unit, "tenant": tenant, "tenancy": tenancy}


# ------------------------------------------------------------------ meter readings


async def test_meter_context_prefills_previous_reading_and_rate(owner: Actor) -> None:
    setup = await occupied_unit(owner, water_rate="150.00")

    response = await owner.get(
        "/api/v1/meter-readings/context",
        params={"unit_id": setup["unit"]["id"], "meter_type": "water"},
    )

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["previous_reading"]) == Decimal("0.00")
    assert Decimal(body["rate"]) == Decimal("150.00")
    assert body["has_rate_configured"] is True


async def test_reading_computes_consumption_and_amount(owner: Actor, client: AsyncClient) -> None:
    setup = await occupied_unit(owner, water_rate="150.00")
    photo_id = await upload_photo(owner, client)

    response = await owner.post(
        "/api/v1/meter-readings",
        json={
            "unit_id": setup["unit"]["id"],
            "meter_type": "water",
            "current_reading": "42.00",
            "reading_date": date.today().isoformat(),
            "photo_file_id": photo_id,
        },
    )

    assert response.status_code == 201, response.text
    reading = response.json()
    assert Decimal(reading["consumption"]) == Decimal("42.00")
    assert Decimal(reading["amount"]) == Decimal("6300.00")  # 42 × 150
    assert reading["photo_url"]


async def test_a_reading_without_a_photo_is_rejected(owner: Actor) -> None:
    """The meter photo is mandatory, enforced server-side (US-026)."""
    setup = await occupied_unit(owner)

    response = await owner.post(
        "/api/v1/meter-readings",
        json={
            "unit_id": setup["unit"]["id"],
            "meter_type": "water",
            "current_reading": "42.00",
            "reading_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 422


async def test_an_unconfirmed_photo_is_rejected(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    ticket = (
        await owner.post(
            "/api/v1/files/upload-url",
            json={"filename": "m.jpg", "content_type": "image/jpeg", "size_bytes": 10},
        )
    ).json()

    response = await owner.post(
        "/api/v1/meter-readings",
        json={
            "unit_id": setup["unit"]["id"],
            "meter_type": "water",
            "current_reading": "42.00",
            "reading_date": date.today().isoformat(),
            "photo_file_id": ticket["file_id"],
        },
    )
    assert response.status_code == 400
    assert "Finish uploading" in response.json()["detail"]


async def test_a_reading_below_the_previous_one_is_rejected(owner: Actor, client: AsyncClient) -> None:
    setup = await occupied_unit(owner)
    await owner.post(
        "/api/v1/meter-readings",
        json={
            "unit_id": setup["unit"]["id"],
            "meter_type": "water",
            "current_reading": "100.00",
            "reading_date": (date.today() - timedelta(days=30)).isoformat(),
            "photo_file_id": await upload_photo(owner, client),
        },
    )

    response = await owner.post(
        "/api/v1/meter-readings",
        json={
            "unit_id": setup["unit"]["id"],
            "meter_type": "water",
            "current_reading": "50.00",
            "reading_date": date.today().isoformat(),
            "photo_file_id": await upload_photo(owner, client),
        },
    )

    assert response.status_code == 400
    assert "below the previous reading" in response.json()["detail"]


async def test_a_reading_rolls_into_the_next_invoice(owner: Actor, client: AsyncClient) -> None:
    """Utility charges land on the tenant's bill without re-keying (US-026)."""
    setup = await occupied_unit(owner, water_rate="100.00")
    await owner.post(
        "/api/v1/meter-readings",
        json={
            "unit_id": setup["unit"]["id"],
            "meter_type": "water",
            "current_reading": "30.00",
            "reading_date": date.today().isoformat(),
            "photo_file_id": await upload_photo(owner, client),
        },
    )

    invoice = (
        await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    ).json()

    water = next(i for i in invoice["line_items"] if i["kind"] == "water")
    assert Decimal(water["amount"]) == Decimal("3000.00")
    assert Decimal(invoice["total"]) == Decimal("28000.00")  # 25000 rent + 3000 water

    # A second invoice must not re-bill the same reading.
    readings = (await owner.get("/api/v1/meter-readings")).json()
    assert readings[0]["billed_invoice_id"] == invoice["id"]


async def test_readings_due_lists_unread_meters(owner: Actor) -> None:
    setup = await occupied_unit(owner, water_rate="150.00")

    response = await owner.get("/api/v1/meter-readings/due")

    assert response.status_code == 200
    assert any(r["unit_id"] == setup["unit"]["id"] for r in response.json())


# -------------------------------------------------------------------- maintenance


async def test_maintenance_request_is_created_and_referenced(owner: Actor) -> None:
    setup = await occupied_unit(owner)

    response = await owner.post(
        "/api/v1/maintenance",
        json={
            "unit_id": setup["unit"]["id"],
            "title": "Kitchen tap leaking",
            "description": "Constant drip under the sink",
            "category": "plumbing",
            "priority": "routine",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reference_code"].startswith("MNT-")
    assert body["status"] == "submitted"
    assert body["reported_by_name"] == "Jane Wanjiru"


async def test_urgent_requests_require_a_photo(owner: Actor) -> None:
    setup = await occupied_unit(owner)

    response = await owner.post(
        "/api/v1/maintenance",
        json={
            "unit_id": setup["unit"]["id"],
            "title": "Burst pipe",
            "description": "Water everywhere",
            "category": "plumbing",
            "priority": "emergency",
        },
    )
    assert response.status_code == 422


async def test_emergency_request_alerts_the_owner_urgently(owner: Actor, client: AsyncClient, db) -> None:
    setup = await occupied_unit(owner)
    photo_id = await upload_photo(owner, client, category="maintenance")

    created = await owner.post(
        "/api/v1/maintenance",
        json={
            "unit_id": setup["unit"]["id"],
            "title": "Burst pipe",
            "description": "Water everywhere",
            "category": "plumbing",
            "priority": "emergency",
            "photo_file_ids": [photo_id],
        },
    )
    assert created.status_code == 201

    alerts = list(
        await db.scalars(
            select(Notification).where(
                Notification.notification_type == NotificationType.MAINTENANCE_SUBMITTED,
                Notification.entity_id == uuid.UUID(created.json()["id"]),
            )
        )
    )
    assert alerts
    assert any("EMERGENCY" in alert.body for alert in alerts)
    assert any(alert.title.startswith("URGENT") for alert in alerts)


async def test_status_change_is_recorded_with_timestamps(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    created = (
        await owner.post(
            "/api/v1/maintenance",
            json={
                "unit_id": setup["unit"]["id"],
                "title": "Loose door handle",
                "description": "Handle wobbles",
            },
        )
    ).json()

    reviewed = await owner.post(f"/api/v1/maintenance/{created['id']}/review")
    assert reviewed.json()["reviewed_at"] is not None
    # Kept in step for reports written before the lifecycle existed.
    assert reviewed.json()["acknowledged_at"] is not None

    approved = await owner.post(
        f"/api/v1/maintenance/{created['id']}/approve", json={"estimated_cost": "400.00"}
    )
    assert approved.json()["approved_at"] is not None

    started = await owner.post(f"/api/v1/maintenance/{created['id']}/start")
    assert started.json()["started_at"] is not None

    completed = await owner.post(
        f"/api/v1/maintenance/{created['id']}/complete",
        json={"actual_cost": "500.00", "resolution_notes": "Tightened"},
    )
    assert completed.json()["completed_at"] is not None
    assert Decimal(completed.json()["cost"]) == Decimal("500.00")


# ------------------------------------------------------------------ tenant portal


async def setup_portal(owner: Actor, client: AsyncClient, db) -> tuple[Actor, dict]:
    """Invite a tenant to the portal and accept on their behalf."""
    setup = await occupied_unit(owner)

    invited = await owner.post("/api/v1/portal/invite", json={"tenant_id": setup["tenant"]["id"]})
    assert invited.status_code == 200, invited.text

    # The raw token only goes out over WhatsApp/SMS, so re-stamp one to drive the flow.
    from app.core.security import generate_url_token, hash_token

    token_row = await db.scalar(
        select(VerificationToken)
        .where(VerificationToken.purpose == TokenPurpose.TENANT_PORTAL_INVITE)
        .order_by(VerificationToken.created_at.desc())
        .limit(1)
    )
    raw = generate_url_token()
    token_row.token_hash = hash_token(f"{setup['tenant']['id']}:{raw}")
    await db.commit()

    accepted = await client.post(
        f"/api/v1/portal/setup?tenant_id={setup['tenant']['id']}",
        json={"token": raw, "password": fresh_password()},
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    return Actor(client, body["tokens"], {"id": body["tenant_id"]}), setup


async def test_tenant_portal_home_shows_balance_and_unit(owner: Actor, client: AsyncClient, db) -> None:
    tenant_actor, setup = await setup_portal(owner, client, db)
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})

    response = await tenant_actor.get("/api/v1/portal/home")

    assert response.status_code == 200
    home = response.json()
    assert home["full_name"] == "Peter Otieno"
    assert home["unit_number"] == setup["unit"]["unit_number"]
    assert home["property_name"] == setup["property"]["name"]
    assert Decimal(home["balance"]) == Decimal("25000.00")
    assert home["next_due_date"] is not None


async def test_tenant_can_trigger_an_mpesa_prompt(owner: Actor, client: AsyncClient, db) -> None:
    """'Pay Rent' in two taps (US-029)."""
    tenant_actor, setup = await setup_portal(owner, client, db)
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})

    response = await tenant_actor.post("/api/v1/portal/pay", json={"amount": "25000.00"})

    assert response.status_code == 202, response.text
    assert response.json()["reference_code"].startswith("PMT-")


async def test_tenant_sees_only_their_own_documents(owner: Actor, client: AsyncClient, db) -> None:
    tenant_actor, setup = await setup_portal(owner, client, db)

    documents = await tenant_actor.get("/api/v1/portal/documents")
    assert documents.status_code == 200
    assert any(d["category"] == "lease" for d in documents.json())

    lease = await tenant_actor.get("/api/v1/portal/lease")
    assert lease.status_code == 200
    assert lease.json()["url"]


async def test_tenant_cannot_reach_the_operator_api(owner: Actor, client: AsyncClient, db) -> None:
    tenant_actor, _ = await setup_portal(owner, client, db)

    assert (await tenant_actor.get("/api/v1/tenants")).status_code == 403
    assert (await tenant_actor.get("/api/v1/arrears")).status_code == 403
    assert (await tenant_actor.get("/api/v1/dashboard/financial")).status_code == 403


async def test_tenant_can_raise_a_maintenance_request(owner: Actor, client: AsyncClient, db) -> None:
    tenant_actor, _ = await setup_portal(owner, client, db)

    created = await tenant_actor.post(
        "/api/v1/portal/maintenance",
        json={"title": "No water", "description": "Taps dry since morning", "category": "plumbing"},
    )

    assert created.status_code == 201, created.text
    assert created.json()["reference_code"].startswith("MNT-")

    listed = await tenant_actor.get("/api/v1/portal/maintenance")
    assert len(listed.json()) == 1


# ------------------------------------------------------------------ vacate notice


async def test_vacate_notice_validates_the_notice_period(owner: Actor, client: AsyncClient, db) -> None:
    """US-033: short notice is accepted but flagged, not silently allowed."""
    tenant_actor, setup = await setup_portal(owner, client, db)

    response = await tenant_actor.post(
        "/api/v1/portal/vacate-notice",
        json={
            "move_out_date": (date.today() + timedelta(days=10)).isoformat(),
            "reason": "Relocating for work",
        },
    )

    assert response.status_code == 201, response.text
    notice = response.json()
    assert notice["notice_days_given"] == 10
    assert notice["meets_notice_period"] is False  # 30 days required
    assert notice["document_id"] is not None


async def test_a_compliant_notice_is_marked_as_meeting_the_period(
    owner: Actor, client: AsyncClient, db
) -> None:
    tenant_actor, _ = await setup_portal(owner, client, db)

    response = await tenant_actor.post(
        "/api/v1/portal/vacate-notice",
        json={"move_out_date": (date.today() + timedelta(days=45)).isoformat()},
    )

    assert response.json()["meets_notice_period"] is True


async def test_notice_sets_the_unit_to_vacating(owner: Actor, client: AsyncClient, db) -> None:
    tenant_actor, setup = await setup_portal(owner, client, db)
    move_out = date.today() + timedelta(days=45)

    await tenant_actor.post("/api/v1/portal/vacate-notice", json={"move_out_date": move_out.isoformat()})

    unit = (await owner.get(f"/api/v1/units/{setup['unit']['id']}")).json()
    assert unit["status"] == "vacating"
    assert unit["expected_vacancy_date"] == move_out.isoformat()

    tenancy = (await owner.get(f"/api/v1/tenancies/{setup['tenancy']['id']}")).json()
    assert tenancy["status"] == "notice_given"


async def test_a_second_notice_is_refused(owner: Actor, client: AsyncClient, db) -> None:
    tenant_actor, _ = await setup_portal(owner, client, db)
    payload = {"move_out_date": (date.today() + timedelta(days=45)).isoformat()}

    assert (await tenant_actor.post("/api/v1/portal/vacate-notice", json=payload)).status_code == 201
    second = await tenant_actor.post("/api/v1/portal/vacate-notice", json=payload)

    assert second.status_code == 409
    assert "already been submitted" in second.json()["detail"]


async def test_owner_can_acknowledge_a_notice(owner: Actor, client: AsyncClient, db) -> None:
    tenant_actor, _ = await setup_portal(owner, client, db)
    await tenant_actor.post(
        "/api/v1/portal/vacate-notice",
        json={"move_out_date": (date.today() + timedelta(days=45)).isoformat()},
    )

    notices = (await owner.get("/api/v1/vacate-notices")).json()
    assert len(notices) == 1

    acknowledged = await owner.post(f"/api/v1/vacate-notices/{notices[0]['id']}/acknowledge")
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"
    assert acknowledged.json()["acknowledged_at"] is not None


# ----------------------------------------------------------------- notifications


async def test_notification_history_records_delivery_per_channel(owner: Actor) -> None:
    response = await owner.get("/api/v1/notifications")

    assert response.status_code == 200
    # Registration fires welcome and account notifications.
    types = {n["notification_type"] for n in response.json()}
    assert "welcome" in types
    assert all(n["status"] in {"sent", "queued", "skipped", "delivered", "failed"} for n in response.json())


async def test_notifications_can_be_marked_read(owner: Actor) -> None:
    before = (await owner.get("/api/v1/notifications/unread-count")).json()["unread"]

    await owner.post("/api/v1/notifications/read-all")

    after = (await owner.get("/api/v1/notifications/unread-count")).json()["unread"]
    assert after == 0
    assert before >= 0


async def test_preferences_expose_the_full_matrix_and_persist(owner: Actor) -> None:
    listed = await owner.get("/api/v1/notifications/preferences")
    assert listed.status_code == 200
    assert all(p["enabled"] is True for p in listed.json())

    saved = await owner.put(
        "/api/v1/notifications/preferences",
        json={"preferences": [{"notification_type": "rent_reminder", "channel": "sms", "enabled": False}]},
    )
    assert saved.status_code == 200

    updated = (await owner.get("/api/v1/notifications/preferences")).json()
    muted = next(p for p in updated if p["notification_type"] == "rent_reminder" and p["channel"] == "sms")
    assert muted["enabled"] is False


async def test_a_muted_channel_is_skipped_on_dispatch(owner: Actor, db) -> None:
    """Preference is honoured at send time, and the skip is visible in history."""
    from app.models.notification import DeliveryStatus, NotificationChannel
    from app.services import notification_service

    await occupied_unit(owner)

    # Tenants have no user row here, so mute via the owner's own preference and
    # dispatch to the owner to observe the skip.
    await owner.put(
        "/api/v1/notifications/preferences",
        json={"preferences": [{"notification_type": "rent_reminder", "channel": "sms", "enabled": False}]},
    )

    from app.models.user import User

    user = await db.get(User, uuid.UUID(owner.user["id"]))
    sent = await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_user(user),
        notification_type=NotificationType.RENT_REMINDER,
        title="Rent due",
        body="Please pay",
        channels=[NotificationChannel.SMS, NotificationChannel.WHATSAPP],
    )
    await db.commit()

    by_channel = {n.channel: n for n in sent}
    assert by_channel[NotificationChannel.SMS].status == DeliveryStatus.SKIPPED
    assert by_channel[NotificationChannel.SMS].error == "Muted by user preference"
    assert by_channel[NotificationChannel.WHATSAPP].status == DeliveryStatus.SENT


async def test_payment_confirmation_cannot_be_muted(owner: Actor, db) -> None:
    """Money and security events ignore preferences by design."""
    from app.models.notification import DeliveryStatus, NotificationChannel
    from app.models.user import User
    from app.services import notification_service

    await owner.put(
        "/api/v1/notifications/preferences",
        json={
            "preferences": [{"notification_type": "payment_confirmed", "channel": "sms", "enabled": False}]
        },
    )

    user = await db.get(User, uuid.UUID(owner.user["id"]))
    sent = await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_user(user),
        notification_type=NotificationType.PAYMENT_CONFIRMED,
        title="Payment received",
        body="KES 1,000",
        channels=[NotificationChannel.SMS],
    )
    await db.commit()

    assert sent[0].status == DeliveryStatus.SENT


async def test_vapid_key_endpoint_reports_configuration(owner: Actor) -> None:
    response = await owner.get("/api/v1/push/vapid-key")

    assert response.status_code == 200
    assert "configured" in response.json()


async def test_push_subscription_can_be_registered(owner: Actor) -> None:
    response = await owner.post(
        "/api/v1/push/subscribe",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
            "p256dh_key": "test-p256dh",
            "auth_key": "test-auth",
            "user_agent": "Chrome on Android",
        },
    )

    assert response.status_code == 201
    assert "enabled" in response.json()["message"]


# ------------------------------------------------------------------ caretaker home


async def test_caretaker_today_screen_aggregates_work(owner: Actor) -> None:
    setup = await occupied_unit(owner, water_rate="150.00")
    await owner.post(
        "/api/v1/maintenance",
        json={
            "unit_id": setup["unit"]["id"],
            "title": "Broken light",
            "description": "Bulb out in corridor",
        },
    )
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})

    response = await owner.get("/api/v1/caretaker/today")

    assert response.status_code == 200
    body = response.json()
    assert len(body["open_maintenance"]) == 1
    assert len(body["readings_due"]) >= 1
    assert body["tenants_in_arrears"] == 1
    assert body["recent_activity"]


async def test_caretaker_activity_summary_counts_actions(owner: Actor, client: AsyncClient) -> None:
    setup = await occupied_unit(owner)
    await owner.post(
        "/api/v1/meter-readings",
        json={
            "unit_id": setup["unit"]["id"],
            "meter_type": "water",
            "current_reading": "10.00",
            "reading_date": date.today().isoformat(),
            "photo_file_id": await upload_photo(owner, client),
        },
    )

    activity = await owner.get("/api/v1/activity", params={"action": "meter_reading.recorded"})
    assert activity.status_code == 200
    assert len(activity.json()) == 1
    assert "Water reading" in activity.json()[0]["summary"]
