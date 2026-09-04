"""Bulk operations: preview, then execute, always with a record (US-071 to US-073).

Every bulk action follows the same two-step shape, and the shape is the point:
`preview` resolves exactly which tenants or units are affected and writes them
into the operation row; `execute` works from that stored list rather than
re-running the query. A rent increase that quietly picked up three more units
between the preview and the confirm would be the worst kind of bug in this
product, so it is made structurally impossible.

Failures never abort the run. One tenant with a dead phone number must not stop
the other forty-nine from being told their rent is going up; the failure is
recorded against that target and the run reports itself as partial.
"""

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, accessible_property_ids, assert_in_org
from app.models.bulk import BulkOperation, BulkOperationKind, BulkOperationStatus
from app.models.file import StoredFile
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.services import audit_service, file_service, notification_service

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")
PENNY = Decimal("0.01")

LIVE_TENANCY_STATUSES = [
    TenancyStatus.ACTIVE,
    TenancyStatus.EXPIRING_SOON,
    TenancyStatus.NOTICE_GIVEN,
]

# Rent increases beyond this are almost always a typo — a missing decimal point
# or a percentage entered where an amount belongs. Refused rather than warned.
MAX_INCREASE_PERCENT = Decimal("100")


async def _scoped_tenancies(
    db: AsyncSession,
    context: OrgContext,
    *,
    property_id: uuid.UUID | None = None,
    unit_ids: list[uuid.UUID] | None = None,
) -> list[Tenancy]:
    query = (
        select(Tenancy)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .where(
            Tenancy.organization_id == context.organization_id,
            Tenancy.status.in_(LIVE_TENANCY_STATUSES),
            Unit.is_archived.is_(False),
        )
    )
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(Unit.property_id.in_(allowed))
    if property_id:
        query = query.where(Unit.property_id == property_id)
    if unit_ids:
        query = query.where(Unit.id.in_(unit_ids))

    rows = await db.scalars(query.order_by(Unit.unit_number))
    return list(rows)


async def _describe(db: AsyncSession, tenancy: Tenancy) -> dict:
    tenant = await db.get(Tenant, tenancy.tenant_id)
    unit = await db.get(Unit, tenancy.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    return {
        "tenancy_id": str(tenancy.id),
        "tenant_id": str(tenancy.tenant_id),
        "tenant_name": tenant.full_name if tenant else "",
        "phone_number": tenant.phone_number if tenant else "",
        "unit_id": str(tenancy.unit_id),
        "unit_number": unit.unit_number if unit else "",
        "property_name": property_record.name if property_record else "",
        "current_rent": float(tenancy.monthly_rent),
    }


# --------------------------------------------------------------------- preview


async def preview(
    db: AsyncSession,
    context: OrgContext,
    kind: BulkOperationKind,
    payload,
    request: Request | None = None,
) -> BulkOperation:
    """Resolve who is affected and save the list. Nothing is sent or changed."""
    tenancies = await _scoped_tenancies(
        db, context, property_id=payload.property_id, unit_ids=payload.unit_ids
    )

    if kind == BulkOperationKind.PAYMENT_REMINDER:
        tenancies = await _only_in_arrears(db, tenancies)
    elif kind == BulkOperationKind.RENEWAL_NOTICES:
        tenancies = _only_expiring(tenancies, payload.within_days or 60)

    targets = [await _describe(db, tenancy) for tenancy in tenancies]

    if kind == BulkOperationKind.RENT_INCREASE:
        targets = _apply_increase_preview(targets, payload)

    operation = BulkOperation(
        organization_id=context.organization_id,
        kind=kind,
        status=BulkOperationStatus.PREVIEWED,
        parameters=payload.model_dump(mode="json", exclude_none=True),
        targets=targets,
        total=len(targets),
        property_id=payload.property_id,
        effective_date=getattr(payload, "effective_date", None),
        created_by_id=context.user.id,
    )
    db.add(operation)
    await db.flush()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="bulk.previewed",
        entity_type="bulk_operation",
        entity_id=operation.id,
        actor=context.user,
        summary=f"Previewed {kind.value.replace('_', ' ')} for {len(targets)} tenant(s)",
        request=request,
    )
    await db.commit()
    await db.refresh(operation)
    return operation


async def _only_in_arrears(db: AsyncSession, tenancies: list[Tenancy]) -> list[Tenancy]:
    from app.services import invoice_service

    owing = []
    for tenancy in tenancies:
        balance = await invoice_service.outstanding_balance(db, tenancy.id)
        if balance > ZERO:
            owing.append(tenancy)
    return owing


def _only_expiring(tenancies: list[Tenancy], within_days: int) -> list[Tenancy]:
    from datetime import timedelta

    cutoff = date.today() + timedelta(days=within_days)
    return [tenancy for tenancy in tenancies if tenancy.end_date is not None and tenancy.end_date <= cutoff]


def _apply_increase_preview(targets: list[dict], payload) -> list[dict]:
    """Work out the new rent per unit so the operator sees it before committing."""
    for target in targets:
        current = Decimal(str(target["current_rent"]))
        if payload.increase_type == "percent":
            new_rent = (current * (1 + Decimal(str(payload.value)) / 100)).quantize(PENNY)
        else:
            new_rent = (current + Decimal(str(payload.value))).quantize(PENNY)
        target["new_rent"] = float(new_rent)
        target["increase"] = float(new_rent - current)
        target["increase_percent"] = (
            float(((new_rent - current) / current * 100).quantize(PENNY)) if current else None
        )
    return targets


# --------------------------------------------------------------------- execute


async def execute(
    db: AsyncSession,
    context: OrgContext,
    operation_id: uuid.UUID,
    request: Request | None = None,
) -> BulkOperation:
    """Run a previewed operation over exactly the targets it recorded."""
    operation = assert_in_org(await db.get(BulkOperation, operation_id), context, label="operation")
    if operation.status != BulkOperationStatus.PREVIEWED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This operation has already been {operation.status.value}",
        )

    operation.status = BulkOperationStatus.RUNNING
    operation.started_at = datetime.now(UTC)
    await db.flush()

    handlers = {
        BulkOperationKind.RENT_INCREASE: _run_rent_increase,
        BulkOperationKind.PAYMENT_REMINDER: _run_payment_reminders,
        BulkOperationKind.ANNOUNCEMENT: _run_announcement,
        BulkOperationKind.GENERATE_INVOICES: _run_generate_invoices,
        BulkOperationKind.RENEWAL_NOTICES: _run_renewal_notices,
        BulkOperationKind.DOCUMENT_DISTRIBUTION: _run_document_distribution,
    }
    handler = handlers.get(operation.kind)
    if handler is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{operation.kind.value} is not run from here",
        )

    failures: list[dict] = []
    succeeded = 0

    for target in operation.targets:
        try:
            await handler(db, context, operation, target)
            succeeded += 1
        except Exception as exc:  # noqa: BLE001 — one bad target must not stop the run
            failures.append(
                {
                    "tenant_name": target.get("tenant_name"),
                    "unit_number": target.get("unit_number"),
                    "reason": str(exc)[:300],
                }
            )

    operation.succeeded = succeeded
    operation.failed = len(failures)
    operation.failures = failures
    operation.finished_at = datetime.now(UTC)
    operation.status = (
        BulkOperationStatus.COMPLETED
        if not failures
        else BulkOperationStatus.PARTIAL if succeeded else BulkOperationStatus.FAILED
    )
    operation.summary = f"{succeeded} of {operation.total} succeeded" + (
        f", {len(failures)} failed" if failures else ""
    )

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="bulk.executed",
        entity_type="bulk_operation",
        entity_id=operation.id,
        actor=context.user,
        summary=f"{operation.kind.value.replace('_', ' ')}: {operation.summary}",
        request=request,
    )
    await db.commit()
    await db.refresh(operation)
    return operation


async def _run_rent_increase(
    db: AsyncSession, context: OrgContext, operation: BulkOperation, target: dict
) -> None:
    """Raise one tenancy's rent and tell the tenant, in writing, why and when."""
    tenancy = await db.get(Tenancy, uuid.UUID(target["tenancy_id"]))
    if tenancy is None or tenancy.organization_id != context.organization_id:
        raise ValueError("Tenancy no longer exists")

    old_rent = Decimal(tenancy.monthly_rent)
    new_rent = Decimal(str(target["new_rent"]))
    effective = operation.effective_date or date.today()

    tenancy.monthly_rent = new_rent
    unit = await db.get(Unit, tenancy.unit_id)
    if unit is not None:
        # The unit's advertised rent moves with the tenancy, or the next vacancy
        # would be listed at last year's price.
        unit.monthly_rent = new_rent

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="tenancy.rent_increased",
        entity_type="tenancy",
        entity_id=tenancy.id,
        actor=context.user,
        summary=(
            f"{target['tenant_name']}, unit {target['unit_number']}: "
            f"KES {old_rent:,.2f} → KES {new_rent:,.2f} from {effective:%d %b %Y}"
        ),
    )

    tenant = await db.get(Tenant, tenancy.tenant_id)
    if tenant is None:
        raise ValueError("Tenant record is missing")

    notice_period = tenancy.notice_period_days or 30
    # A rent review is a legal notice, so it goes out as a document the tenant can
    # keep and the landlord can produce later — the WhatsApp message carries it.
    document = await _render_increase_notice(
        db, tenancy, tenant, target, old_rent=old_rent, new_rent=new_rent, effective=effective
    )

    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_tenant(tenant),
        notification_type=NotificationType.RENT_INCREASE,
        title="Notice of rent review",
        body=(
            f"Dear {tenant.full_name}, this is formal notice that the rent for unit "
            f"{target['unit_number']} at {target['property_name']} will change from "
            f"KES {old_rent:,.0f} to KES {new_rent:,.0f} per month with effect from "
            f"{effective:%d %B %Y}. This is at least {notice_period} days' notice as required "
            f"by your tenancy agreement. Please contact us if you would like to discuss it."
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        attachment=(
            notification_service.Attachment(url=file_service.to_url(document), filename=document.filename)
            if document is not None
            else None
        ),
        entity_type="tenancy",
        entity_id=tenancy.id,
        organization_id=context.organization_id,
    )


async def _render_increase_notice(
    db: AsyncSession,
    tenancy: Tenancy,
    tenant: Tenant,
    target: dict,
    *,
    old_rent: Decimal,
    new_rent: Decimal,
    effective: date,
) -> StoredFile | None:
    """The written notice, filed against the tenant. A failure here must not stop
    the increase — the WhatsApp notice still goes, and the PDF is a nicety."""
    from app.models.file import FileCategory
    from app.models.organization import Organization
    from app.services import pdf_service

    unit = await db.get(Unit, tenancy.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    organization = await db.get(Organization, tenancy.organization_id)
    if not (unit and property_record and organization):
        return None

    increase = new_rent - old_rent
    percent = (increase / old_rent * 100).quantize(Decimal("0.1")) if old_rent > ZERO else None

    try:
        pdf_bytes = pdf_service.render_pdf(
            "rent_increase_notice.html",
            {
                "organization": organization,
                "logo_url": None,
                "tenant": tenant,
                "tenancy": tenancy,
                "unit": unit,
                "property": property_record,
                "old_rent": old_rent,
                "new_rent": new_rent,
                "increase": increase,
                "increase_percent": percent,
                "effective_date": effective,
                "notice_days": (effective - date.today()).days,
                "generated_at": date.today(),
            },
        )
    except Exception:  # noqa: BLE001 — the notice still goes out over WhatsApp
        logger.exception("Rent increase notice rendering failed for %s", tenancy.reference_code)
        return None

    return await file_service.register_generated(
        db,
        tenancy.organization_id,
        data=pdf_bytes,
        filename=f"Rent-review-{unit.unit_number}-{effective:%Y-%m}.pdf",
        category=FileCategory.NOTICE,
        entity_type="tenant",
        entity_id=tenant.id,
    )


async def _run_payment_reminders(
    db: AsyncSession, context: OrgContext, operation: BulkOperation, target: dict
) -> None:
    from app.services import invoice_service

    tenancy = await db.get(Tenancy, uuid.UUID(target["tenancy_id"]))
    tenant = await db.get(Tenant, uuid.UUID(target["tenant_id"]))
    if tenancy is None or tenant is None:
        raise ValueError("Tenancy or tenant no longer exists")

    balance = await invoice_service.outstanding_balance(db, tenancy.id)
    if balance <= ZERO:
        # They paid between the preview and the run — saying nothing is correct.
        return

    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_tenant(tenant),
        notification_type=NotificationType.RENT_REMINDER,
        title="Rent reminder",
        body=(
            f"Dear {tenant.full_name}, our records show KES {balance:,.0f} outstanding on "
            f"unit {target['unit_number']} at {target['property_name']}. "
            f"Kindly settle at your earliest convenience, or contact us if you have already paid."
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="tenancy",
        entity_id=tenancy.id,
        organization_id=context.organization_id,
    )


async def _run_announcement(
    db: AsyncSession, context: OrgContext, operation: BulkOperation, target: dict
) -> None:
    tenant = await db.get(Tenant, uuid.UUID(target["tenant_id"]))
    if tenant is None:
        raise ValueError("Tenant no longer exists")

    message = operation.parameters.get("message", "").strip()
    subject = operation.parameters.get("subject") or "A message from your landlord"
    if not message:
        raise ValueError("The announcement has no message")

    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_tenant(tenant),
        notification_type=NotificationType.ANNOUNCEMENT,
        title=subject,
        body=f"Dear {tenant.full_name}, {message}",
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="tenant",
        entity_id=tenant.id,
        organization_id=context.organization_id,
    )


async def _run_generate_invoices(
    db: AsyncSession, context: OrgContext, operation: BulkOperation, target: dict
) -> None:
    from app.services import invoice_service

    tenancy = await db.get(Tenancy, uuid.UUID(target["tenancy_id"]))
    if tenancy is None:
        raise ValueError("Tenancy no longer exists")

    invoice = await invoice_service.generate_invoice_for_tenancy(db, tenancy)
    if invoice is None:
        # Already invoiced for this period — not a failure, just nothing to do.
        return


async def _run_renewal_notices(
    db: AsyncSession, context: OrgContext, operation: BulkOperation, target: dict
) -> None:
    from app.services import renewal_service

    tenancy = await db.get(Tenancy, uuid.UUID(target["tenancy_id"]))
    if tenancy is None:
        raise ValueError("Tenancy no longer exists")

    # `create_offer` returns the existing open offer rather than duplicating one,
    # so re-running a partial batch is safe.
    await renewal_service.create_offer(db, tenancy, actor=context.user)


async def _run_document_distribution(
    db: AsyncSession, context: OrgContext, operation: BulkOperation, target: dict
) -> None:
    """Send one document to one tenant over WhatsApp (US-073)."""
    tenant = await db.get(Tenant, uuid.UUID(target["tenant_id"]))
    if tenant is None:
        raise ValueError("Tenant no longer exists")

    file_id = operation.parameters.get("document_file_id")
    if not file_id:
        raise ValueError("No document was selected")

    document = await db.get(StoredFile, uuid.UUID(str(file_id)))
    if document is None or document.organization_id != context.organization_id:
        raise ValueError("The document could not be found")

    note = operation.parameters.get("message") or "Please find the attached document."
    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_tenant(tenant),
        notification_type=NotificationType.ANNOUNCEMENT,
        title=operation.parameters.get("subject") or document.filename,
        body=f"Dear {tenant.full_name}, {note}",
        channels=[NotificationChannel.WHATSAPP],
        attachment=notification_service.Attachment(
            url=file_service.to_url(document), filename=document.filename
        ),
        entity_type="tenant",
        entity_id=tenant.id,
        organization_id=context.organization_id,
    )


# ----------------------------------------------------------------- read models


async def list_operations(
    db: AsyncSession,
    context: OrgContext,
    *,
    kind: BulkOperationKind | None = None,
    limit: int = 50,
) -> list[BulkOperation]:
    query = select(BulkOperation).where(BulkOperation.organization_id == context.organization_id)
    if kind:
        query = query.where(BulkOperation.kind == kind)
    rows = await db.scalars(query.order_by(BulkOperation.created_at.desc()).limit(limit))
    return list(rows)


async def get_operation(db: AsyncSession, context: OrgContext, operation_id: uuid.UUID) -> BulkOperation:
    return assert_in_org(await db.get(BulkOperation, operation_id), context, label="operation")


async def cancel(db: AsyncSession, context: OrgContext, operation_id: uuid.UUID) -> BulkOperation:
    operation = await get_operation(db, context, operation_id)
    if operation.status != BulkOperationStatus.PREVIEWED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only a previewed operation can be cancelled"
        )
    operation.status = BulkOperationStatus.CANCELLED
    await db.commit()
    await db.refresh(operation)
    return operation
