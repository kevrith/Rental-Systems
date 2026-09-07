"""Document vault — Phase 2 (US-045, US-046, US-048).

Every document RentFlow generates is already filed against the entity it belongs
to. The vault is the read model over that: one organised, searchable view per
tenant and per property, plus the write side agencies need to put their own
paperwork in — title deeds, insurance and compliance certificates.

Two rules shape the design:

  * Nothing is ever deleted. Replacing a document supersedes it, which archives
    the old row and links the new one to it, so a vault can always answer "what
    did this look like in March?".
  * Reads are handed out as signed URLs that expire in an hour (US-045). No
    object in the vault is publicly addressable.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import Text, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.file import FileCategory, StoredFile, UploadStatus
from app.models.inspection import InspectionReport
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, Tenant
from app.services import audit_service, file_service, notification_service

# What belongs in each vault, in the order a person expects to see it.
TENANT_VAULT_CATEGORIES: tuple[FileCategory, ...] = (
    FileCategory.LEASE,
    FileCategory.SIGNED_DOCUMENT,
    FileCategory.RECEIPT,
    FileCategory.INVOICE,
    FileCategory.INSPECTION_REPORT,
    FileCategory.NOTICE,
    FileCategory.DEMAND_LETTER,
    FileCategory.RENEWAL_AGREEMENT,
    FileCategory.TENANT_ID,
    FileCategory.TENANT_PASSPORT_PHOTO,
    FileCategory.OTHER,
)

PROPERTY_VAULT_CATEGORIES: tuple[FileCategory, ...] = (
    FileCategory.TITLE_DEED,
    FileCategory.INSURANCE_CERTIFICATE,
    FileCategory.COMPLIANCE_CERTIFICATE,
    FileCategory.LEASE,
    FileCategory.SIGNED_DOCUMENT,
    FileCategory.INSPECTION_REPORT,
    FileCategory.MAINTENANCE,
    FileCategory.PROPERTY_PHOTO,
    FileCategory.UNIT_PHOTO,
    FileCategory.METER_READING,
    FileCategory.OTHER,
)

# Categories an agency uploads itself, as opposed to ones RentFlow generates.
UPLOADABLE_CATEGORIES: frozenset[FileCategory] = frozenset(
    {
        FileCategory.TITLE_DEED,
        FileCategory.INSURANCE_CERTIFICATE,
        FileCategory.COMPLIANCE_CERTIFICATE,
        FileCategory.LEASE,
        FileCategory.NOTICE,
        FileCategory.MAINTENANCE,
        FileCategory.TENANT_ID,
        FileCategory.TENANT_PASSPORT_PHOTO,
        FileCategory.PROPERTY_PHOTO,
        FileCategory.UNIT_PHOTO,
        FileCategory.OTHER,
    }
)


def _clean_tags(tags: list[str] | None) -> list[str]:
    """Lower-cased, de-duplicated, order preserved — so search stays predictable."""
    if not tags:
        return []
    seen: dict[str, None] = {}
    for tag in tags:
        cleaned = tag.strip().lower()[:48]
        if cleaned:
            seen.setdefault(cleaned, None)
    return list(seen)[:20]


def serialize(record: StoredFile) -> dict:
    """One vault row, with a signed URL good for the next hour."""
    return {
        "id": str(record.id),
        "filename": record.filename,
        "content_type": record.content_type,
        "size_bytes": record.size_bytes,
        "category": record.category.value,
        "tags": list(record.tags or []),
        "description": record.description,
        "version": record.version,
        "supersedes_id": str(record.supersedes_id) if record.supersedes_id else None,
        "entity_type": record.entity_type,
        "entity_id": str(record.entity_id) if record.entity_id else None,
        "is_archived": record.is_archived,
        "uploaded_at": (record.uploaded_at or record.created_at).isoformat(),
        "url": file_service.to_url(record),
    }


def group_by_category(records: list[StoredFile], order: tuple[FileCategory, ...]) -> list[dict]:
    """Bucket documents into the sections a vault screen renders."""
    buckets: dict[str, list[dict]] = {}
    for record in records:
        buckets.setdefault(record.category.value, []).append(serialize(record))

    ranked = [c.value for c in order]
    sections = []
    for name in ranked + sorted(set(buckets) - set(ranked)):
        rows = buckets.get(name)
        if not rows:
            continue
        rows.sort(key=lambda r: r["uploaded_at"], reverse=True)
        sections.append({"category": name, "count": len(rows), "documents": rows})
    return sections


async def _query(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    entity_pairs: list[tuple[str, uuid.UUID]],
    category: FileCategory | None = None,
    search: str | None = None,
    include_archived: bool = False,
) -> list[StoredFile]:
    if not entity_pairs:
        return []

    conditions = [
        and_(StoredFile.entity_type == entity_type, StoredFile.entity_id == entity_id)
        for entity_type, entity_id in entity_pairs
    ]
    query = select(StoredFile).where(
        StoredFile.organization_id == organization_id,
        StoredFile.status == UploadStatus.UPLOADED,
        or_(*conditions),
    )
    if not include_archived:
        query = query.where(StoredFile.is_archived.is_(False))
    if category is not None:
        query = query.where(StoredFile.category == category)
    if search:
        term = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(StoredFile.filename).like(term),
                func.lower(func.coalesce(StoredFile.description, "")).like(term),
                func.lower(func.cast(StoredFile.tags, Text)).like(term),
            )
        )
    rows = await db.scalars(query.order_by(StoredFile.created_at.desc()))
    return list(rows)


# ----------------------------------------------------------------- tenant vault (US-045)


async def _tenant_entity_pairs(
    db: AsyncSession, organization_id: uuid.UUID, tenant_id: uuid.UUID
) -> list[tuple[str, uuid.UUID]]:
    """Every (entity_type, entity_id) a tenant's documents can be filed
    against: their own record, their tenancies, and the inspection reports of
    units they've occupied (US-045). Shared by the in-app vault and the
    data-export bundle (US-106) so the two can never disagree about what
    counts as "this tenant's documents"."""
    pairs: list[tuple[str, uuid.UUID]] = [("tenant", tenant_id)]

    tenancy_ids = list(
        await db.scalars(
            select(Tenancy.id).where(
                Tenancy.organization_id == organization_id, Tenancy.tenant_id == tenant_id
            )
        )
    )
    pairs.extend(("tenancy", tenancy_id) for tenancy_id in tenancy_ids)

    if tenancy_ids:
        report_ids = list(
            await db.scalars(
                select(InspectionReport.id).where(
                    InspectionReport.organization_id == organization_id,
                    InspectionReport.tenancy_id.in_(tenancy_ids),
                )
            )
        )
        pairs.extend(("inspection_report", report_id) for report_id in report_ids)

    return pairs


async def documents_for_tenant(
    db: AsyncSession, organization_id: uuid.UUID, tenant_id: uuid.UUID
) -> list[StoredFile]:
    """Every uploaded, non-archived document filed against one tenant — used
    by the data-export bundle (US-106)."""
    pairs = await _tenant_entity_pairs(db, organization_id, tenant_id)
    return await _query(db, organization_id, entity_pairs=pairs)


async def tenant_vault(
    db: AsyncSession,
    context: OrgContext,
    tenant_id: uuid.UUID,
    *,
    category: FileCategory | None = None,
    search: str | None = None,
    include_archived: bool = False,
) -> dict:
    """Everything filed against one tenant, plus the inspections of their units."""
    tenant = assert_in_org(await db.get(Tenant, tenant_id), context, label="tenant")

    pairs = await _tenant_entity_pairs(db, context.organization_id, tenant.id)
    records = await _query(
        db,
        context.organization_id,
        entity_pairs=pairs,
        category=category,
        search=search,
        include_archived=include_archived,
    )
    return {
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.full_name,
        "reference_code": tenant.reference_code,
        "document_count": len(records),
        "total_bytes": sum(r.size_bytes for r in records),
        "sections": group_by_category(records, TENANT_VAULT_CATEGORIES),
    }


# ----------------------------------------------------------------- property vault (US-046)


async def property_vault(
    db: AsyncSession,
    context: OrgContext,
    property_id: uuid.UUID,
    *,
    category: FileCategory | None = None,
    search: str | None = None,
    include_archived: bool = False,
) -> dict:
    """Everything filed against a property, its units, and the tenancies in them."""
    record = assert_in_org(await db.get(Property, property_id), context, label="property")

    pairs: list[tuple[str, uuid.UUID]] = [("property", record.id)]

    unit_ids = list(
        await db.scalars(
            select(Unit.id).where(
                Unit.organization_id == context.organization_id, Unit.property_id == record.id
            )
        )
    )
    pairs.extend(("unit", unit_id) for unit_id in unit_ids)

    if unit_ids:
        tenancy_ids = list(
            await db.scalars(
                select(Tenancy.id).where(
                    Tenancy.organization_id == context.organization_id,
                    Tenancy.unit_id.in_(unit_ids),
                )
            )
        )
        pairs.extend(("tenancy", tenancy_id) for tenancy_id in tenancy_ids)

        report_ids = list(
            await db.scalars(
                select(InspectionReport.id).where(
                    InspectionReport.organization_id == context.organization_id,
                    InspectionReport.unit_id.in_(unit_ids),
                )
            )
        )
        pairs.extend(("inspection_report", report_id) for report_id in report_ids)

    records = await _query(
        db,
        context.organization_id,
        entity_pairs=pairs,
        category=category,
        search=search,
        include_archived=include_archived,
    )
    return {
        "property_id": str(record.id),
        "property_name": record.name,
        "reference_code": record.reference_code,
        "unit_count": len(unit_ids),
        "document_count": len(records),
        "total_bytes": sum(r.size_bytes for r in records),
        "sections": group_by_category(records, PROPERTY_VAULT_CATEGORIES),
    }


# ----------------------------------------------------------------- write side


VALID_ENTITY_TYPES = {"tenant", "tenancy", "property", "unit", "inspection_report", "owner_profile"}


async def _assert_entity_exists(
    db: AsyncSession, context: OrgContext, entity_type: str, entity_id: uuid.UUID
) -> None:
    """A document must hang off something this organisation actually owns."""
    models = {
        "tenant": Tenant,
        "tenancy": Tenancy,
        "property": Property,
        "unit": Unit,
        "inspection_report": InspectionReport,
    }
    model = models.get(entity_type)
    if model is None:
        return
    assert_in_org(await db.get(model, entity_id), context, label=entity_type)


async def file_document(
    db: AsyncSession,
    context: OrgContext,
    file_id: uuid.UUID,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    category: FileCategory,
    tags: list[str] | None = None,
    description: str | None = None,
) -> StoredFile:
    """Move an uploaded file into a vault, categorised and tagged."""
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A vault document cannot be filed against '{entity_type}'",
        )
    if category not in UPLOADABLE_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"'{category.value}' documents are generated by RentFlow and cannot be uploaded"),
        )
    await _assert_entity_exists(db, context, entity_type, entity_id)

    record = await file_service.get_file(db, context, file_id)
    if record.status != UploadStatus.UPLOADED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm the upload before filing it in a vault",
        )

    record.entity_type = entity_type
    record.entity_id = entity_id
    record.category = category
    record.tags = _clean_tags(tags)
    record.description = description

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="vault.document_filed",
        entity_type=entity_type,
        entity_id=entity_id,
        actor=context.user,
        summary=f"Filed {record.filename} as {category.value}",
    )
    await db.commit()
    await db.refresh(record)
    return record


async def update_document(
    db: AsyncSession,
    context: OrgContext,
    file_id: uuid.UUID,
    *,
    category: FileCategory | None = None,
    tags: list[str] | None = None,
    description: str | None = None,
    filename: str | None = None,
) -> StoredFile:
    """Recategorise, retag or rename — the bytes are never touched."""
    record = await file_service.get_file(db, context, file_id)

    if category is not None:
        if category not in UPLOADABLE_CATEGORIES and category != record.category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A document cannot be recategorised as '{category.value}'",
            )
        record.category = category
    if tags is not None:
        record.tags = _clean_tags(tags)
    if description is not None:
        record.description = description or None
    if filename:
        record.filename = filename[:255]

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="vault.document_updated",
        entity_type=record.entity_type or "stored_file",
        entity_id=record.entity_id or record.id,
        actor=context.user,
        summary=f"Updated vault document {record.filename}",
    )
    await db.commit()
    await db.refresh(record)
    return record


async def add_version(
    db: AsyncSession,
    context: OrgContext,
    previous_id: uuid.UUID,
    new_file_id: uuid.UUID,
    *,
    description: str | None = None,
) -> StoredFile:
    """Supersede a document with a newer upload (US-048).

    The old row is archived, not deleted, and the new one carries version + 1 and
    a link back — so the history is walkable in both directions.
    """
    previous = await file_service.get_file(db, context, previous_id)
    replacement = await file_service.get_file(db, context, new_file_id)

    if replacement.status != UploadStatus.UPLOADED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm the upload before it can supersede a document",
        )
    if previous.id == replacement.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A document cannot supersede itself"
        )
    if previous.is_archived:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That document has already been superseded — replace the current version instead",
        )

    replacement.entity_type = previous.entity_type
    replacement.entity_id = previous.entity_id
    replacement.category = previous.category
    replacement.tags = list(previous.tags or [])
    replacement.description = description if description is not None else previous.description
    replacement.version = previous.version + 1
    replacement.supersedes_id = previous.id
    previous.is_archived = True

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="vault.document_versioned",
        entity_type=previous.entity_type or "stored_file",
        entity_id=previous.entity_id or previous.id,
        actor=context.user,
        summary=f"{replacement.filename} replaced {previous.filename} (v{replacement.version})",
    )
    await db.commit()
    await db.refresh(replacement)
    return replacement


async def version_history(db: AsyncSession, context: OrgContext, file_id: uuid.UUID) -> list[StoredFile]:
    """The full chain for a document, newest version first."""
    record = await file_service.get_file(db, context, file_id)

    # Walk forward to the newest version, then back down the supersedes chain.
    newest = record
    seen: set[uuid.UUID] = {record.id}
    while True:
        successor = await db.scalar(
            select(StoredFile).where(
                StoredFile.organization_id == context.organization_id,
                StoredFile.supersedes_id == newest.id,
            )
        )
        if successor is None or successor.id in seen:
            break
        seen.add(successor.id)
        newest = successor

    chain = [newest]
    cursor = newest
    while cursor.supersedes_id is not None:
        previous = await db.get(StoredFile, cursor.supersedes_id)
        if previous is None or previous.organization_id != context.organization_id:
            break
        if previous.id in {c.id for c in chain}:
            break
        chain.append(previous)
        cursor = previous
    return chain


async def archive_document(db: AsyncSession, context: OrgContext, file_id: uuid.UUID) -> StoredFile:
    """Remove a document from the vault view. The bytes and the row both remain."""
    record = await file_service.get_file(db, context, file_id)
    record.is_archived = True
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="vault.document_archived",
        entity_type=record.entity_type or "stored_file",
        entity_id=record.entity_id or record.id,
        actor=context.user,
        summary=f"Archived vault document {record.filename}",
    )
    await db.commit()
    await db.refresh(record)
    return record


# ----------------------------------------------------------------- storage usage (US-046)


async def storage_usage(db: AsyncSession, context: OrgContext) -> dict:
    """How much the account is holding, and where it is going."""
    rows = await db.execute(
        select(
            StoredFile.category,
            func.count(StoredFile.id),
            func.coalesce(func.sum(StoredFile.size_bytes), 0),
        )
        .where(
            StoredFile.organization_id == context.organization_id,
            StoredFile.status == UploadStatus.UPLOADED,
        )
        .group_by(StoredFile.category)
    )
    by_category = [
        {"category": category.value, "document_count": count, "bytes": int(total)}
        for category, count, total in rows
    ]
    by_category.sort(key=lambda row: row["bytes"], reverse=True)
    return {
        "total_documents": sum(row["document_count"] for row in by_category),
        "total_bytes": sum(row["bytes"] for row in by_category),
        "by_category": by_category,
    }


# ----------------------------------------------------------------- WhatsApp delivery (US-047)


async def deliver_document(
    db: AsyncSession,
    context: OrgContext,
    file_id: uuid.UUID,
    *,
    phone_number: str | None = None,
    tenant_id: uuid.UUID | None = None,
    message: str | None = None,
) -> dict:
    """Send a vault document to someone on WhatsApp, as a PDF attachment.

    The recipient is either a tenant on file — who then gets the in-app record
    against their name — or a bare phone number for a one-off send.
    """
    record = await file_service.get_file(db, context, file_id)
    if record.status != UploadStatus.UPLOADED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="That document is not available to send"
        )

    tenant: Tenant | None = None
    if tenant_id is not None:
        tenant = assert_in_org(await db.get(Tenant, tenant_id), context, label="tenant")
        recipient = notification_service.Recipient.for_tenant(tenant)
    elif phone_number:
        recipient = notification_service.Recipient(
            phone_number=phone_number, organization_id=context.organization_id
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Say who to send it to — a tenant or a phone number",
        )

    body = message or f"{context.organization.name} has sent you a document: {record.filename}"
    sent = await notification_service.send(
        db,
        recipient=recipient,
        notification_type=NotificationType.ACCOUNT,
        title=record.filename,
        body=body,
        channels=[NotificationChannel.WHATSAPP],
        attachment=notification_service.Attachment(url=file_service.to_url(record), filename=record.filename),
        entity_type="stored_file",
        entity_id=record.id,
        organization_id=context.organization_id,
    )

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="vault.document_sent",
        entity_type="stored_file",
        entity_id=record.id,
        actor=context.user,
        summary=(
            f"Sent {record.filename} to "
            f"{tenant.full_name if tenant else recipient.phone_number} on WhatsApp"
        ),
    )
    await db.commit()

    delivery = sent[0] if sent else None
    return {
        "document_id": str(record.id),
        "filename": record.filename,
        "recipient": recipient.phone_number,
        "status": delivery.status.value if delivery else "queued",
        "error": delivery.error if delivery else None,
    }


async def notify_new_document(
    db: AsyncSession, tenant: Tenant, record: StoredFile, *, organization_id: uuid.UUID
) -> None:
    """Tell a tenant their vault has something new in it (US-045)."""
    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_tenant(tenant),
        notification_type=NotificationType.ACCOUNT,
        title="A new document is in your vault",
        body=(
            f"{record.filename} has been added to your RentFlow document vault. "
            f"You can view or download it any time from the tenant portal."
        ),
        channels=[NotificationChannel.WHATSAPP],
        link_path="/portal/documents",
        entity_type="stored_file",
        entity_id=record.id,
        organization_id=organization_id,
    )
