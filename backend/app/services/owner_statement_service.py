"""Owner monthly statement generation and delivery — Phase 2 (US-042).

Every disbursement gets an agency-branded PDF showing exactly what was collected
on each unit, what was deducted and why, what was paid out, and what tenants
still owe. The statement is filed in the owner's document vault and delivered to
them on WhatsApp (as an attachment) and by email.

The numbers on the statement are read back off the `Disbursement` row rather than
recalculated, so the PDF can never disagree with the money that actually moved.
The per-unit and per-job breakdowns are re-derived for the same period, which is
what turns "KES 27,000" into something an owner can audit.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agency import Disbursement, DisbursementStatus, OwnerProfile
from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentStatus
from app.models.file import FileCategory, StoredFile
from app.models.notification import NotificationChannel, NotificationType
from app.models.operations import BILLABLE_STATUSES, MaintenanceRequest
from app.models.organization import Organization
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, Tenant
from app.services import file_service, notification_service, pdf_service, storage_service

ZERO = Decimal("0.00")


def _day_bounds(period_start: date, period_end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(period_start, datetime.min.time()).replace(tzinfo=UTC),
        datetime.combine(period_end, datetime.max.time()).replace(tzinfo=UTC),
    )


async def _logo_url(db: AsyncSession, file_id: uuid.UUID | None) -> str | None:
    """WeasyPrint fetches this while rendering, so it must resolve without auth."""
    if file_id is None:
        return None
    record = await db.get(StoredFile, file_id)
    if record is None:
        return None
    return storage_service.download_url(record.storage_key, record.filename)


async def build_context(db: AsyncSession, disbursement: Disbursement) -> dict:
    """Assemble everything the statement template renders."""
    owner = await db.get(OwnerProfile, disbursement.owner_profile_id)
    organization = await db.get(Organization, disbursement.organization_id)
    if owner is None or organization is None:
        raise ValueError("Disbursement is missing the records needed to build a statement")

    properties = list(
        await db.scalars(
            select(Property).where(
                Property.organization_id == disbursement.organization_id,
                Property.owner_profile_id == owner.id,
                Property.is_archived.is_(False),
            )
        )
    )
    property_name = {p.id: p.name for p in properties}

    units = (
        list(
            await db.scalars(
                select(Unit).where(
                    Unit.property_id.in_([p.id for p in properties]), Unit.is_archived.is_(False)
                )
            )
        )
        if properties
        else []
    )
    unit_by_id = {u.id: u for u in units}

    # Who is (or was) in each unit, for the tenant column.
    tenant_of_unit: dict[uuid.UUID, str] = {}
    if units:
        rows = await db.execute(
            select(Tenancy.unit_id, Tenant.full_name)
            .join(Tenant, Tenant.id == Tenancy.tenant_id)
            .where(Tenancy.unit_id.in_(list(unit_by_id)))
            .order_by(Tenancy.start_date.desc())
        )
        for unit_id, full_name in rows:
            tenant_of_unit.setdefault(unit_id, full_name)

    # --- rent collected, per unit ---
    per_unit: dict[uuid.UUID, dict] = {}
    if units:
        payment_rows = await db.execute(
            select(Tenancy.unit_id, Payment.amount)
            .join(Tenancy, Tenancy.id == Payment.tenancy_id)
            .where(
                Payment.organization_id == disbursement.organization_id,
                Payment.status == PaymentStatus.CONFIRMED,
                Tenancy.unit_id.in_(list(unit_by_id)),
                Payment.payment_date >= disbursement.period_start,
                Payment.payment_date <= disbursement.period_end,
            )
        )
        for unit_id, amount in payment_rows:
            unit = unit_by_id.get(unit_id)
            if unit is None:
                continue
            row = per_unit.setdefault(
                unit_id,
                {
                    "property_name": property_name.get(unit.property_id, "—"),
                    "unit_number": unit.unit_number,
                    "tenant_name": tenant_of_unit.get(unit_id),
                    "payment_count": 0,
                    "gross_rent": ZERO,
                },
            )
            row["payment_count"] += 1
            row["gross_rent"] += Decimal(amount)

    unit_rows = sorted(per_unit.values(), key=lambda r: (r["property_name"], r["unit_number"]))

    # --- maintenance deductions, itemised ---
    maintenance: list[dict] = []
    if units:
        start_at, end_at = _day_bounds(disbursement.period_start, disbursement.period_end)
        jobs = await db.scalars(
            select(MaintenanceRequest).where(
                MaintenanceRequest.organization_id == disbursement.organization_id,
                MaintenanceRequest.unit_id.in_(list(unit_by_id)),
                MaintenanceRequest.status.in_(BILLABLE_STATUSES),
                MaintenanceRequest.completed_at >= start_at,
                MaintenanceRequest.completed_at <= end_at,
                MaintenanceRequest.cost.is_not(None),
            )
        )
        for job in jobs:
            unit = unit_by_id.get(job.unit_id)
            maintenance.append(
                {
                    "title": job.title,
                    "reference_code": job.reference_code,
                    "property_name": property_name.get(unit.property_id, "—") if unit else "—",
                    "unit_number": unit.unit_number if unit else None,
                    "completed_at": job.completed_at.date() if job.completed_at else None,
                    "cost": Decimal(job.cost or ZERO),
                }
            )
        maintenance.sort(key=lambda item: item["cost"], reverse=True)

    # --- arrears still outstanding on this owner's units ---
    arrears: list[dict] = []
    total_arrears = ZERO
    if units:
        invoice_rows = await db.execute(
            select(Tenancy.unit_id, Tenant.full_name, Invoice.total, Invoice.amount_paid)
            .join(Tenancy, Tenancy.id == Invoice.tenancy_id)
            .join(Tenant, Tenant.id == Tenancy.tenant_id)
            .where(
                Invoice.organization_id == disbursement.organization_id,
                Invoice.status.notin_([InvoiceStatus.CANCELLED, InvoiceStatus.PAID]),
                Tenancy.unit_id.in_(list(unit_by_id)),
                Invoice.issue_date <= disbursement.period_end,
            )
        )
        by_unit: dict[uuid.UUID, dict] = {}
        for unit_id, tenant_name, total, amount_paid in invoice_rows:
            balance = Decimal(total) - Decimal(amount_paid)
            if balance <= ZERO:
                continue
            unit = unit_by_id.get(unit_id)
            if unit is None:
                continue
            row = by_unit.setdefault(
                unit_id,
                {
                    "property_name": property_name.get(unit.property_id, "—"),
                    "unit_number": unit.unit_number,
                    "tenant_name": tenant_name,
                    "balance": ZERO,
                },
            )
            row["balance"] += balance
            total_arrears += balance
        arrears = sorted(by_unit.values(), key=lambda r: r["balance"], reverse=True)

    # --- year to date, across every statement issued this calendar year ---
    year_start = date(disbursement.period_end.year, 1, 1)
    ytd_rows = list(
        await db.scalars(
            select(Disbursement).where(
                Disbursement.organization_id == disbursement.organization_id,
                Disbursement.owner_profile_id == owner.id,
                Disbursement.period_start >= year_start,
                Disbursement.period_end <= disbursement.period_end,
                Disbursement.status != DisbursementStatus.REJECTED,
            )
        )
    )
    ytd = {
        "year": disbursement.period_end.year,
        "count": len(ytd_rows),
        "gross_rent": sum((Decimal(d.gross_rent) for d in ytd_rows), ZERO),
        "management_fee": sum((Decimal(d.management_fee) for d in ytd_rows), ZERO),
        "maintenance_costs": sum((Decimal(d.maintenance_costs) for d in ytd_rows), ZERO),
        "net_amount": sum((Decimal(d.net_amount) for d in ytd_rows), ZERO),
    }

    destination = owner.mpesa_phone or (
        f"{owner.bank_name} {owner.bank_account_number}"
        if owner.bank_name and owner.bank_account_number
        else owner.phone_number
    )

    return {
        "organization": organization,
        "logo_url": await _logo_url(db, organization.logo_file_id),
        "owner": owner,
        "disbursement": disbursement,
        "units": unit_rows,
        "maintenance": maintenance,
        "total_deductions": (
            Decimal(disbursement.management_fee)
            + Decimal(disbursement.maintenance_costs)
            + Decimal(disbursement.other_deductions)
        ),
        "arrears": arrears,
        "total_arrears": total_arrears,
        "ytd": ytd,
        "payout_destination": destination,
        "generated_at": datetime.now(UTC).date(),
    }


async def render_statement_pdf(db: AsyncSession, disbursement: Disbursement) -> bytes:
    return pdf_service.render_pdf("owner_statement.html", await build_context(db, disbursement))


async def generate_statement(
    db: AsyncSession, disbursement: Disbursement, *, force: bool = False
) -> StoredFile | None:
    """Render the statement and file it in the owner's vault.

    Returns the existing file unless `force`, so re-running the disbursement
    scheduler does not litter the vault with duplicates. A PDF backend that is
    not installed must not take the payout down with it, so a rendering failure
    is logged and swallowed — the money has already moved by this point.
    """
    if disbursement.statement_document_id and not force:
        return await db.get(StoredFile, disbursement.statement_document_id)

    try:
        pdf_bytes = await render_statement_pdf(db, disbursement)
    except Exception:  # noqa: BLE001 — a missing PDF backend must not fail a payout
        import logging

        logging.getLogger("rentflow.agency").exception(
            "Owner statement rendering failed for %s", disbursement.reference_code
        )
        return None

    record = await file_service.register_generated(
        db,
        disbursement.organization_id,
        data=pdf_bytes,
        filename=f"Statement-{disbursement.reference_code}.pdf",
        category=FileCategory.OWNER_STATEMENT,
        entity_type="owner_profile",
        entity_id=disbursement.owner_profile_id,
    )
    disbursement.statement_document_id = record.id
    return record


async def deliver_statement(
    db: AsyncSession, disbursement: Disbursement, statement: StoredFile | None
) -> None:
    """Send the statement to the owner on WhatsApp (PDF) and by email."""
    owner = await db.get(OwnerProfile, disbursement.owner_profile_id)
    if owner is None:
        return

    attachment = None
    if statement is not None:
        attachment = notification_service.Attachment(
            url=file_service.to_url(statement), filename=statement.filename
        )

    period = f"{disbursement.period_start.strftime('%b %Y')}"
    body = (
        f"Dear {owner.full_name}, your statement for {period} is ready.\n"
        f"Gross rent collected: KES {pdf_service.format_kes(disbursement.gross_rent)}\n"
        f"Management fee: KES {pdf_service.format_kes(disbursement.management_fee)}\n"
        f"Maintenance: KES {pdf_service.format_kes(disbursement.maintenance_costs)}\n"
        f"Net disbursed: KES {pdf_service.format_kes(disbursement.net_amount)}\n"
        f"Reference: {disbursement.reference_code}"
    )

    channels = [NotificationChannel.WHATSAPP]
    recipient = notification_service.Recipient(
        phone_number=owner.mpesa_phone or owner.phone_number,
        organization_id=disbursement.organization_id,
    )
    # Email goes out only when the owner has a portal user carrying the address —
    # the email channel reads it off the user, not off the profile.
    if owner.portal_user_id:
        from app.models.user import User

        portal_user = await db.get(User, owner.portal_user_id)
        if portal_user and portal_user.email:
            recipient = notification_service.Recipient(
                user=portal_user,
                phone_number=owner.mpesa_phone or owner.phone_number,
                organization_id=disbursement.organization_id,
            )
            channels.append(NotificationChannel.EMAIL)

    await notification_service.send(
        db,
        recipient=recipient,
        notification_type=NotificationType.DISBURSEMENT_SENT,
        title=f"Owner statement — {period}",
        body=body,
        channels=channels,
        attachment=attachment,
        entity_type="disbursement",
        entity_id=disbursement.id,
        organization_id=disbursement.organization_id,
    )
