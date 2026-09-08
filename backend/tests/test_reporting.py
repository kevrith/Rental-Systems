"""Sprint 21: the custom report builder, scheduled report delivery, the
automatic monthly summary, and the vacancy-risk / rent-review predictive
widgets built on top of Sprint 11's analytics and Sprint 12's renewals.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.api.deps import OrgContext
from app.models.billing import Payment, PaymentMethod, PaymentStatus
from app.models.file import StoredFile
from app.models.organization import Organization, ReportDeliveryChannel
from app.models.property import Property, PropertyType, Unit
from app.models.renewal import LeaseRenewal, RenewalStatus
from app.models.reporting import MonthlyReport, ReportDefinition, ReportSchedule
from app.models.tenant import PaymentMethodPreference, Tenancy, TenancyStatus, Tenant
from app.models.user import User
from app.models.vacancy import ExportKind
from app.services import analytics_service, reporting_service
from tests.conftest import Actor

BASE = "/api/v1/reports"


async def _seed_tenancy_with_payment(db, org_id: uuid.UUID, *, rent: Decimal = Decimal("25000.00")):
    """One property -> unit -> tenant -> tenancy -> confirmed payment."""
    suffix = uuid.uuid4().hex[:8]
    prop = Property(
        organization_id=org_id,
        reference_code=f"PRP-{suffix}",
        name=f"Block {suffix}",
        property_type=PropertyType.RESIDENTIAL,
        address="1 Test Road, Nairobi",
        grace_period_days=5,
    )
    db.add(prop)
    await db.flush()

    unit = Unit(
        organization_id=org_id,
        property_id=prop.id,
        reference_code=f"UNT-{suffix}",
        unit_number="A1",
        bedrooms=2,
        monthly_rent=rent,
        deposit_amount=rent,
    )
    db.add(unit)
    await db.flush()

    tenant = Tenant(
        organization_id=org_id,
        reference_code=f"TNT-{suffix}",
        full_name="Test Tenant",
        phone_number=f"+2547{uuid.uuid4().int % 100000000:08d}",
    )
    db.add(tenant)
    await db.flush()

    tenancy = Tenancy(
        organization_id=org_id,
        reference_code=f"TCY-{suffix}",
        tenant_id=tenant.id,
        unit_id=unit.id,
        start_date=date.today() - timedelta(days=400),
        is_open_ended=True,
        monthly_rent=rent,
        deposit_amount=rent,
        billing_day=1,
        payment_method=PaymentMethodPreference.MPESA,
        status=TenancyStatus.ACTIVE,
    )
    db.add(tenancy)
    await db.flush()

    payment = Payment(
        organization_id=org_id,
        reference_code=f"PMT-{suffix}",
        tenancy_id=tenancy.id,
        amount=rent,
        payment_date=date.today(),
        method=PaymentMethod.MPESA,
        status=PaymentStatus.CONFIRMED,
    )
    db.add(payment)
    await db.commit()
    return prop, unit, tenant, tenancy, payment


async def _org_context(db, actor: Actor) -> OrgContext:
    user = await db.get(User, uuid.UUID(actor.user["id"]))
    organization = await db.get(Organization, uuid.UUID(actor.user["organization_id"]))
    return OrgContext(user=user, organization=organization)


# ------------------------------------------------------------- datasets/fields


async def test_datasets_and_fields_are_listable(owner: Actor) -> None:
    datasets = (await owner.get(f"{BASE}/datasets")).json()
    assert any(row["dataset"] == "payments" for row in datasets)

    fields = (await owner.get(f"{BASE}/datasets/payments/fields")).json()
    keys = {row["key"] for row in fields}
    assert {"Reference", "Amount", "Status"} <= keys


# ------------------------------------------------------------------------ CRUD


async def test_create_list_get_update_delete_definition(owner: Actor) -> None:
    created = await owner.post(
        f"{BASE}/definitions",
        json={"name": "Rent collected", "dataset": "payments", "fields": ["Reference", "Amount"]},
    )
    assert created.status_code == 201, created.text
    definition_id = created.json()["id"]
    assert created.json()["schedule"] == "none"

    listed = await owner.get(f"{BASE}/definitions")
    assert any(row["id"] == definition_id for row in listed.json())

    fetched = await owner.get(f"{BASE}/definitions/{definition_id}")
    assert fetched.status_code == 200
    assert fetched.json()["fields"] == ["Reference", "Amount"]

    updated = await owner.patch(f"{BASE}/definitions/{definition_id}", json={"name": "Rent collected v2"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Rent collected v2"

    deleted = await owner.delete(f"{BASE}/definitions/{definition_id}")
    assert deleted.status_code == 204
    assert (await owner.get(f"{BASE}/definitions/{definition_id}")).status_code == 404


async def test_cross_tenant_isolation_on_definitions(owner: Actor, other_owner: Actor) -> None:
    created = await owner.post(
        f"{BASE}/definitions",
        json={"name": "Owner-only report", "dataset": "tenants", "fields": ["Reference"]},
    )
    definition_id = created.json()["id"]

    # Each request is issued outside the assert: a call inside `assert (...).x`
    # never runs under `python -O`, which strips asserts entirely — this test
    # would then silently stop exercising the authorization check at all.
    patch_response = await other_owner.patch(f"{BASE}/definitions/{definition_id}", json={"name": "Hijacked"})
    get_response = await other_owner.get(f"{BASE}/definitions/{definition_id}")
    delete_response = await other_owner.delete(f"{BASE}/definitions/{definition_id}")
    run_response = await other_owner.post(f"{BASE}/definitions/{definition_id}/run")

    assert get_response.status_code == 403
    assert patch_response.status_code == 403
    assert delete_response.status_code == 403
    assert run_response.status_code == 403

    other_listed = await other_owner.get(f"{BASE}/definitions")
    assert all(row["id"] != definition_id for row in other_listed.json())


# ------------------------------------------------------------- preview & run


async def test_preview_and_run_reflect_seeded_payment(owner: Actor, db) -> None:
    org_id = uuid.UUID(owner.user["organization_id"])
    _, _, _, _, payment = await _seed_tenancy_with_payment(db, org_id)

    preview = await owner.post(
        f"{BASE}/preview",
        json={"dataset": "payments", "fields": ["Reference", "Amount", "Status"]},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["row_count"] == 1
    assert body["rows"][0]["Reference"] == payment.reference_code
    assert body["rows"][0]["Amount"] == 25000.0
    assert set(body["rows"][0].keys()) == {"Reference", "Amount", "Status"}

    created = await owner.post(
        f"{BASE}/definitions",
        json={
            "name": "Payments CSV",
            "dataset": "payments",
            "fields": ["Reference", "Amount"],
            "export_format": "csv",
        },
    )
    definition_id = created.json()["id"]

    run = await owner.post(f"{BASE}/definitions/{definition_id}/run")
    assert run.status_code == 200
    assert run.headers["x-row-count"] == "1"
    assert payment.reference_code in run.content.decode("utf-8-sig")

    run_pdf = await owner.post(f"{BASE}/definitions/{definition_id}/run", params={"format": "pdf"})
    assert run_pdf.status_code == 200
    assert run_pdf.headers["content-type"] == "application/pdf"
    assert run_pdf.content.startswith(b"%PDF")


async def test_filters_narrow_preview_rows(owner: Actor, db) -> None:
    org_id = uuid.UUID(owner.user["organization_id"])
    await _seed_tenancy_with_payment(db, org_id, rent=Decimal("10000.00"))
    _, _, _, _, second_payment = await _seed_tenancy_with_payment(db, org_id, rent=Decimal("30000.00"))

    context = await _org_context(db, owner)
    rows = await reporting_service.execute(
        db,
        context,
        dataset=ExportKind.PAYMENTS,
        fields=["Reference", "Amount"],
        filters={"Reference": [second_payment.reference_code]},
    )
    assert rows == [{"Reference": second_payment.reference_code, "Amount": 30000.0}]


# -------------------------------------------------------------- scheduling


async def test_run_scheduled_custom_reports_only_runs_due_definitions(owner: Actor, db) -> None:
    org_id = uuid.UUID(owner.user["organization_id"])
    await _seed_tenancy_with_payment(db, org_id)
    today_weekday = date.today().weekday()
    tomorrow_weekday = (today_weekday + 1) % 7

    due = ReportDefinition(
        organization_id=org_id,
        created_by_id=uuid.UUID(owner.user["id"]),
        name="Weekly payments",
        dataset=ExportKind.PAYMENTS,
        fields=["Reference", "Amount"],
        schedule=ReportSchedule.WEEKLY,
        schedule_day=today_weekday,
        delivery_channels=["in_app"],
    )
    not_due = ReportDefinition(
        organization_id=org_id,
        created_by_id=uuid.UUID(owner.user["id"]),
        name="Not due yet",
        dataset=ExportKind.PAYMENTS,
        fields=["Reference"],
        schedule=ReportSchedule.WEEKLY,
        schedule_day=tomorrow_weekday,
        delivery_channels=["in_app"],
    )
    db.add_all([due, not_due])
    await db.commit()

    sent = await reporting_service.run_scheduled_custom_reports(db)
    assert sent == 1

    await db.refresh(due)
    await db.refresh(not_due)
    assert due.last_run_at is not None
    assert not_due.last_run_at is None


# ------------------------------------------------------------- monthly report


async def test_monthly_report_generation_is_idempotent(owner: Actor, db) -> None:
    org_id = uuid.UUID(owner.user["organization_id"])
    await _seed_tenancy_with_payment(db, org_id)
    context = await _org_context(db, owner)

    period_start = date.today().replace(day=1) - timedelta(days=1)
    period_start = period_start.replace(day=1)
    period_end = date.today().replace(day=1) - timedelta(days=1)

    first = await reporting_service.generate_monthly_report(
        db, context.organization, context, period_start, period_end
    )
    await db.commit()
    second = await reporting_service.generate_monthly_report(
        db, context.organization, context, period_start, period_end
    )
    await db.commit()

    assert first is not None
    assert second is not None
    assert first.id == second.id

    count = await db.scalar(
        select(func.count(MonthlyReport.id)).where(
            MonthlyReport.organization_id == org_id, MonthlyReport.period_start == period_start
        )
    )
    assert count == 1


async def test_monthly_report_respects_whatsapp_only_preference(owner: Actor, db) -> None:
    org_id = uuid.UUID(owner.user["organization_id"])
    await _seed_tenancy_with_payment(db, org_id)
    context = await _org_context(db, owner)
    context.organization.report_delivery_channel = ReportDeliveryChannel.WHATSAPP

    period_start = date.today().replace(day=1) - timedelta(days=1)
    period_start = period_start.replace(day=1)
    period_end = date.today().replace(day=1) - timedelta(days=1)

    report = await reporting_service.generate_monthly_report(
        db, context.organization, context, period_start, period_end
    )
    assert report is not None
    await db.commit()
    stored = await db.get(StoredFile, report.file_id)
    await reporting_service.deliver_monthly_report(db, context.organization, context.user, report, stored)
    await db.commit()

    assert report.delivered_channels == ["whatsapp"]


# ------------------------------------------------------------ vacancy risk


async def test_vacancy_risk_excludes_tenancies_with_a_live_renewal_offer(owner: Actor, db) -> None:
    org_id = uuid.UUID(owner.user["organization_id"])
    _, _, _, at_risk_tenancy, _ = await _seed_tenancy_with_payment(db, org_id)
    at_risk_tenancy.status = TenancyStatus.EXPIRING_SOON
    at_risk_tenancy.end_date = date.today() + timedelta(days=30)

    _, _, _, offered_tenancy, _ = await _seed_tenancy_with_payment(db, org_id)
    offered_tenancy.status = TenancyStatus.EXPIRING_SOON
    offered_tenancy.end_date = date.today() + timedelta(days=45)
    await db.flush()

    renewal = LeaseRenewal(
        organization_id=org_id,
        reference_code=f"REN-{uuid.uuid4().hex[:8]}",
        tenancy_id=offered_tenancy.id,
        current_rent=offered_tenancy.monthly_rent,
        proposed_rent=offered_tenancy.monthly_rent,
        new_start_date=offered_tenancy.end_date,
        new_end_date=offered_tenancy.end_date + timedelta(days=365),
        status=RenewalStatus.OFFERED,
        respond_by=date.today() + timedelta(days=14),
        token_hash=uuid.uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(days=3),
    )
    db.add(renewal)
    await db.commit()

    at_risk = await analytics_service.vacancy_risk_forecast(db, org_id)
    tenancy_ids = {row["tenancy_id"] for row in at_risk}
    assert str(at_risk_tenancy.id) in tenancy_ids
    assert str(offered_tenancy.id) not in tenancy_ids


# --------------------------------------------------------- rent review


async def test_rent_review_flags_only_stale_tenancies(owner: Actor, db) -> None:
    org_id = uuid.UUID(owner.user["organization_id"])
    _, stale_unit, _, stale_tenancy, _ = await _seed_tenancy_with_payment(
        db, org_id, rent=Decimal("20000.00")
    )
    stale_tenancy.start_date = date.today() - timedelta(days=800)

    _, fresh_unit, _, fresh_tenancy, _ = await _seed_tenancy_with_payment(
        db, org_id, rent=Decimal("30000.00")
    )
    fresh_tenancy.start_date = date.today() - timedelta(days=30)
    stale_unit.bedrooms = fresh_unit.bedrooms = 2
    await db.commit()

    suggestions = await analytics_service.rent_review_suggestions(db, org_id)
    tenancy_ids = {row["tenancy_id"] for row in suggestions}
    assert str(stale_tenancy.id) in tenancy_ids
    assert str(fresh_tenancy.id) not in tenancy_ids
