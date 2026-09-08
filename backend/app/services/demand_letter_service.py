"""Demand letter generation — Phase 2 (US-055).

A formal, dated demand for rent arrears, generated from the invoice ledger and
filed in the tenant's vault. The letter is the document a landlord needs before
the Rent Restriction Tribunal will hear anything, so it has to state the exact
sum, itemise where it comes from, and give a deadline.

Escalation is by age of the oldest overdue invoice:

  * 60 days  — first demand, 14 days to pay
  * 90 days  — final demand, 7 days to pay

The nightly task issues at most one letter per tenancy per escalation level, so
a tenant who ignores the first demand gets a final one, not the same one daily.
"""

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.billing import Invoice, InvoiceStatus
from app.models.file import FileCategory, StoredFile
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import Organization
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, Tenant
from app.services import audit_service, file_service, notification_service, pdf_service

logger = logging.getLogger("rentflow.demand")

ZERO = Decimal("0.00")

# Days overdue -> (label, days given to pay). Ordered most severe first so the
# escalation picks the strongest level the arrears have reached.
ESCALATIONS: list[tuple[int, str, int]] = [
    (90, "Final demand", 7),
    (60, "First demand", 14),
]


def escalation_for(days_overdue: int) -> tuple[str, int] | None:
    for threshold, label, deadline_days in ESCALATIONS:
        if days_overdue >= threshold:
            return label, deadline_days
    return None


async def arrears_for_tenancy(db: AsyncSession, tenancy: Tenancy, as_at: date) -> dict:
    """Every unpaid invoice on a tenancy, oldest first, with the totals."""
    invoices = list(
        await db.scalars(
            select(Invoice)
            .where(
                Invoice.organization_id == tenancy.organization_id,
                Invoice.tenancy_id == tenancy.id,
                Invoice.status.notin_([InvoiceStatus.CANCELLED, InvoiceStatus.PAID]),
                Invoice.due_date < as_at,
            )
            .order_by(Invoice.due_date)
        )
    )

    rows = []
    total = ZERO
    # Carried alongside the rows rather than read back out of them: the rows are
    # heterogeneous dicts, so their values are only `object` to a type checker
    # and nothing there proves the age is a number you can compare.
    oldest_days_overdue = 0
    for invoice in invoices:
        balance = Decimal(invoice.total) - Decimal(invoice.amount_paid)
        if balance <= ZERO:
            continue
        total += balance
        days_overdue = (as_at - invoice.due_date).days
        oldest_days_overdue = max(oldest_days_overdue, days_overdue)
        rows.append(
            {
                "id": invoice.id,
                "reference_code": invoice.reference_code,
                "period_start": invoice.period_start,
                "due_date": invoice.due_date,
                "days_overdue": days_overdue,
                "balance": balance,
            }
        )

    return {
        "invoices": rows,
        "total_owed": total,
        "days_overdue": oldest_days_overdue,
    }


async def render_letter(
    db: AsyncSession,
    tenancy: Tenancy,
    *,
    as_at: date | None = None,
    escalation_label: str | None = None,
    deadline_days: int | None = None,
) -> tuple[bytes, dict]:
    """Render the demand PDF and return it with the facts it was built from."""
    as_at = as_at or date.today()
    arrears = await arrears_for_tenancy(db, tenancy, as_at)
    if arrears["total_owed"] <= ZERO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This tenancy has no overdue balance to demand",
        )

    if escalation_label is None or deadline_days is None:
        chosen = escalation_for(arrears["days_overdue"])
        # A letter can be issued by hand before 60 days; it is just a first demand.
        escalation_label, deadline_days = chosen or ("First demand", 14)

    tenant = await db.get(Tenant, tenancy.tenant_id)
    unit = await db.get(Unit, tenancy.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    organization = await db.get(Organization, tenancy.organization_id)
    if not (tenant and unit and property_record and organization):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The tenancy is missing records needed to build a demand letter",
        )

    reference_code = f"DEM-{tenancy.reference_code}-{as_at:%Y%m%d}"
    context = {
        "organization": organization,
        "logo_url": None,
        "reference_code": reference_code,
        "tenant": tenant,
        "tenancy": tenancy,
        "unit": unit,
        "property": property_record,
        "invoices": arrears["invoices"],
        "total_owed": arrears["total_owed"],
        "days_overdue": arrears["days_overdue"],
        "escalation_label": escalation_label,
        "deadline_days": deadline_days,
        "deadline": as_at + timedelta(days=deadline_days),
        "as_at": as_at,
        "payment_instructions": organization.letterhead_note,
        "generated_at": as_at,
    }
    return pdf_service.render_pdf("demand_letter.html", context), context


async def issue(
    db: AsyncSession,
    tenancy: Tenancy,
    *,
    as_at: date | None = None,
    escalation_label: str | None = None,
    deadline_days: int | None = None,
    notify: bool = True,
    actor_id: uuid.UUID | None = None,
) -> tuple[StoredFile, dict]:
    """Render, file in the tenant's vault, and send it to them on WhatsApp."""
    pdf_bytes, context = await render_letter(
        db,
        tenancy,
        as_at=as_at,
        escalation_label=escalation_label,
        deadline_days=deadline_days,
    )

    record = await file_service.register_generated(
        db,
        tenancy.organization_id,
        data=pdf_bytes,
        filename=f"{context['reference_code']}.pdf",
        category=FileCategory.DEMAND_LETTER,
        entity_type="tenant",
        entity_id=context["tenant"].id,
    )
    record.description = (
        f"{context['escalation_label']} for KES "
        f"{pdf_service.format_kes(context['total_owed'])} — reply by "
        f"{context['deadline']:%d %b %Y}"
    )
    record.tags = ["demand letter", context["escalation_label"].lower()]

    audit_service.record(
        db,
        organization_id=tenancy.organization_id,
        action="demand_letter.issued",
        entity_type="tenancy",
        entity_id=tenancy.id,
        summary=(
            f"{context['escalation_label']} issued to {context['tenant'].full_name} for KES "
            f"{pdf_service.format_kes(context['total_owed'])} "
            f"({context['days_overdue']} days overdue)"
        ),
    )

    if notify:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_tenant(context["tenant"]),
            notification_type=NotificationType.ACCOUNT,
            title=context["escalation_label"],
            body=(
                f"Dear {context['tenant'].full_name}, rent of KES "
                f"{pdf_service.format_kes(context['total_owed'])} is outstanding on unit "
                f"{context['unit'].unit_number}. Please pay in full by "
                f"{context['deadline']:%d %b %Y}. The attached letter sets out the detail. "
                f"If you cannot pay it all, contact us to agree a payment plan."
            ),
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
            attachment=notification_service.Attachment(
                url=file_service.to_url(record), filename=record.filename
            ),
            entity_type="tenancy",
            entity_id=tenancy.id,
            organization_id=tenancy.organization_id,
        )

    return record, context


async def issue_for_tenancy(db: AsyncSession, context: OrgContext, tenancy_id: uuid.UUID) -> dict:
    """The manual path — a manager issuing a demand from the arrears screen."""
    tenancy = assert_in_org(await db.get(Tenancy, tenancy_id), context, label="tenancy")
    record, facts = await issue(db, tenancy, actor_id=context.user.id)
    await db.commit()
    return {
        "reference_code": facts["reference_code"],
        "escalation": facts["escalation_label"],
        "total_owed": str(facts["total_owed"]),
        "days_overdue": facts["days_overdue"],
        "deadline": facts["deadline"].isoformat(),
        "document_id": str(record.id),
        "filename": record.filename,
        "url": file_service.to_url(record),
    }


async def preview_for_tenancy(db: AsyncSession, context: OrgContext, tenancy_id: uuid.UUID) -> bytes:
    """Render without filing or sending — so a manager can read it before it goes."""
    tenancy = assert_in_org(await db.get(Tenancy, tenancy_id), context, label="tenancy")
    pdf_bytes, _ = await render_letter(db, tenancy)
    return pdf_bytes


async def _already_issued(
    db: AsyncSession, tenant_id: uuid.UUID, organization_id: uuid.UUID, escalation_label: str
) -> bool:
    """One letter per escalation level per tenant, not one per night."""
    tag = escalation_label.lower()
    rows = await db.scalars(
        select(StoredFile).where(
            StoredFile.organization_id == organization_id,
            StoredFile.entity_type == "tenant",
            StoredFile.entity_id == tenant_id,
            StoredFile.category == FileCategory.DEMAND_LETTER,
        )
    )
    return any(tag in (record.tags or []) for record in rows)


async def issue_due_letters(db: AsyncSession) -> dict[str, int]:
    """Nightly sweep: escalate every tenancy whose arrears have aged past a threshold.

    Runs across all organisations, so it takes no `OrgContext`.
    """
    today = date.today()
    issued = 0
    skipped = 0

    # Only tenancies with something genuinely overdue are worth loading.
    cutoff = today - timedelta(days=ESCALATIONS[-1][0])
    tenancy_ids = list(
        await db.scalars(
            select(Invoice.tenancy_id)
            .where(
                Invoice.status.notin_([InvoiceStatus.CANCELLED, InvoiceStatus.PAID]),
                Invoice.due_date <= cutoff,
            )
            .distinct()
        )
    )

    for tenancy_id in tenancy_ids:
        tenancy = await db.get(Tenancy, tenancy_id)
        if tenancy is None:
            continue

        arrears = await arrears_for_tenancy(db, tenancy, today)
        if arrears["total_owed"] <= ZERO:
            continue
        chosen = escalation_for(arrears["days_overdue"])
        if chosen is None:
            continue
        label, deadline_days = chosen

        if await _already_issued(db, tenancy.tenant_id, tenancy.organization_id, label):
            skipped += 1
            continue

        try:
            await issue(
                db,
                tenancy,
                as_at=today,
                escalation_label=label,
                deadline_days=deadline_days,
            )
            # Committed per tenancy, not per sweep: a rollback for one bad tenancy
            # would otherwise discard every letter already written in this run.
            await db.commit()
            issued += 1
        except Exception:  # noqa: BLE001 — one bad tenancy must not stop the sweep
            logger.exception("Demand letter failed for tenancy %s", tenancy_id)
            await db.rollback()

    logger.info("Issued %s demand letter(s), %s already on file", issued, skipped)
    return {"issued": issued, "skipped": skipped}
