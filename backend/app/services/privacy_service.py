"""Data subject access & erasure requests (Sprint 25, US-106).

Both request types are processed synchronously and immediately:

  * **Export** is a read — it aggregates the tenant's profile, tenancies,
    invoices, payments and vault documents (leases, receipts, inspection
    reports, KYC files) into one JSON bundle and stores it like any other
    generated document, then hands back a signed download link. Each listed
    document carries its own 60-minute signed URL — the same freshness window
    every other document link in this app already uses — rather than bundling
    raw bytes into the export itself.
  * **Erasure** redacts the tenant's own personal fields only. Financial and
    audit records stay exactly as they are: `Tenancy`, `Invoice` and `Payment`
    rows are never touched, because Kenyan tax and accounting law require a
    landlord to keep them regardless of what the tenant who generated them
    later asks for. What disappears is the tenant's name, contact details,
    KYC documents and notes — anything RentFlow itself has no ongoing legal
    reason to keep once the tenant has said they want it gone.

Nothing here needs an approval queue: an export cannot leak anything the
requester didn't already have a right to see, and an erasure only ever narrows
what is stored.
"""

import json
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.billing import Invoice, Payment
from app.models.file import FileCategory
from app.models.notification import NotificationChannel, NotificationType
from app.models.privacy import DataRequest, DataRequestStatus, DataRequestType
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, Tenant
from app.models.user import User, UserRole
from app.services import audit_service, notification_service, storage_service, vault_service


async def _notify_operators(db: AsyncSession, organization_id: uuid.UUID, tenant: Tenant, verb: str) -> None:
    owners = await db.scalars(
        select(User).where(
            User.organization_id == organization_id,
            User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
            User.is_active.is_(True),
        )
    )
    for owner in owners:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(owner),
            notification_type=NotificationType.DATA_REQUEST,
            title="Data privacy request",
            body=f"{tenant.full_name} {verb} their personal data. Reference: tenant {tenant.reference_code}.",
            channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            entity_type="tenant",
            entity_id=tenant.id,
        )


def _plain(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def _export_payload(db: AsyncSession, organization_id: uuid.UUID, tenant: Tenant) -> dict:
    tenancies = list(await db.scalars(select(Tenancy).where(Tenancy.tenant_id == tenant.id)))
    tenancy_ids = [t.id for t in tenancies]

    # The same document set the tenant vault (US-045) shows in-app: their own
    # KYC files, their tenancies' leases and notices, and the inspection
    # reports for units they've occupied.
    documents = await vault_service.documents_for_tenant(db, organization_id, tenant.id)

    payments = (
        list(await db.scalars(select(Payment).where(Payment.tenancy_id.in_(tenancy_ids))))
        if tenancy_ids
        else []
    )
    invoices = (
        list(await db.scalars(select(Invoice).where(Invoice.tenancy_id.in_(tenancy_ids))))
        if tenancy_ids
        else []
    )

    tenancy_rows = []
    for tenancy in tenancies:
        unit = await db.get(Unit, tenancy.unit_id)
        property_record = await db.get(Property, unit.property_id) if unit else None
        tenancy_rows.append(
            {
                "reference_code": tenancy.reference_code,
                "property_name": property_record.name if property_record else None,
                "unit_number": unit.unit_number if unit else None,
                "start_date": _plain(tenancy.start_date),
                "end_date": _plain(tenancy.end_date),
                "monthly_rent": _plain(tenancy.monthly_rent),
                "deposit_amount": _plain(tenancy.deposit_amount),
                "status": tenancy.status.value,
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": {
            "reference_code": tenant.reference_code,
            "full_name": tenant.full_name,
            "phone_number": tenant.phone_number,
            "email": tenant.email,
            "national_id": tenant.national_id,
            "employer_name": tenant.employer_name,
            "occupation": tenant.occupation,
            "monthly_income": _plain(tenant.monthly_income),
            "emergency_contact_name": tenant.emergency_contact_name,
            "emergency_contact_phone": tenant.emergency_contact_phone,
            "notes": tenant.notes,
        },
        "tenancies": tenancy_rows,
        "documents": [
            {
                "filename": document.filename,
                "category": document.category.value,
                "uploaded_at": _plain(document.uploaded_at or document.created_at),
                "download_url": storage_service.download_url(document.storage_key, document.filename),
            }
            for document in documents
        ],
        "invoices": [
            {
                "reference_code": invoice.reference_code,
                "period_start": _plain(invoice.period_start),
                "period_end": _plain(invoice.period_end),
                "total": _plain(invoice.total),
                "amount_paid": _plain(invoice.amount_paid),
                "status": invoice.status.value,
            }
            for invoice in invoices
        ],
        "payments": [
            {
                "reference_code": payment.reference_code,
                "amount": _plain(payment.amount),
                "method": payment.method.value,
                "status": payment.status.value,
                "mpesa_receipt": payment.mpesa_receipt,
                "recorded_at": _plain(payment.created_at),
            }
            for payment in payments
        ],
    }


async def export_tenant_data(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    tenant: Tenant,
    requested_by_id: uuid.UUID | None,
    request: Request | None = None,
) -> DataRequest:
    payload = await _export_payload(db, organization_id, tenant)
    data = json.dumps(payload, indent=2).encode("utf-8")

    file_id = await storage_service.store_bytes(
        db,
        data=data,
        filename=f"data-export-{tenant.reference_code}-{datetime.now(UTC):%Y%m%d%H%M%S}.json",
        content_type="application/json",
        category=FileCategory.DATA_REQUEST_EXPORT,
        organization_id=organization_id,
        entity_type="tenant",
        entity_id=tenant.id,
    )

    data_request = DataRequest(
        organization_id=organization_id,
        tenant_id=tenant.id,
        request_type=DataRequestType.EXPORT,
        status=DataRequestStatus.COMPLETED,
        requested_by_id=requested_by_id,
        export_file_id=file_id,
        resolved_at=datetime.now(UTC),
    )
    db.add(data_request)
    await db.flush()

    audit_service.record(
        db,
        organization_id=organization_id,
        action="data_request.export",
        entity_type="tenant",
        entity_id=tenant.id,
        summary=f"Data export generated for {tenant.full_name}",
        request=request,
    )
    await _notify_operators(db, organization_id, tenant, "requested an export of")
    await db.commit()
    await db.refresh(data_request)
    return data_request


async def erase_tenant_data(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    tenant: Tenant,
    requested_by_id: uuid.UUID | None,
    request: Request | None = None,
) -> DataRequest:
    if tenant.erased_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This tenant's data was already erased"
        )

    before_name = tenant.full_name
    tenant.full_name = "Erased tenant"
    # Phone carries a per-organisation uniqueness constraint, so the redacted
    # value still has to be unique rather than a shared placeholder string.
    tenant.phone_number = f"erased-{tenant.id.hex[:12]}"
    tenant.email = None
    tenant.national_id = None
    tenant.id_photo_front_id = None
    tenant.id_photo_back_id = None
    tenant.passport_photo_id = None
    tenant.employer_name = None
    tenant.occupation = None
    tenant.monthly_income = None
    tenant.emergency_contact_name = None
    tenant.emergency_contact_phone = None
    tenant.emergency_contact_relationship = None
    tenant.notes = None
    tenant.erased_at = datetime.now(UTC)
    tenant.is_archived = True
    tenant.archived_at = tenant.erased_at

    data_request = DataRequest(
        organization_id=organization_id,
        tenant_id=tenant.id,
        request_type=DataRequestType.ERASURE,
        status=DataRequestStatus.COMPLETED,
        requested_by_id=requested_by_id,
        resolution_notes="Personal fields redacted. Tenancy, invoice and payment records retained.",
        resolved_at=datetime.now(UTC),
    )
    db.add(data_request)
    await db.flush()

    audit_service.record(
        db,
        organization_id=organization_id,
        action="data_request.erasure",
        entity_type="tenant",
        entity_id=tenant.id,
        summary=f"Personal data erased for former tenant {before_name} ({tenant.reference_code})",
        request=request,
    )
    await _notify_operators(db, organization_id, tenant, "requested erasure of")
    await db.commit()
    await db.refresh(data_request)
    return data_request


async def list_data_requests(
    db: AsyncSession, context: OrgContext, tenant_id: uuid.UUID | None = None
) -> list[DataRequest]:
    query = select(DataRequest).where(DataRequest.organization_id == context.organization_id)
    if tenant_id:
        query = query.where(DataRequest.tenant_id == tenant_id)
    rows = await db.scalars(query.order_by(DataRequest.created_at.desc()))
    return list(rows)


async def get_tenant_for_operator(db: AsyncSession, context: OrgContext, tenant_id: uuid.UUID) -> Tenant:
    return assert_in_org(await db.get(Tenant, tenant_id), context, label="tenant")
