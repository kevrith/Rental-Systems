"""Upload lifecycle for user-supplied files (US-012).

Three steps, so bytes never touch the API:

  1. `request_upload` records intent and returns a pre-signed PUT.
  2. The client uploads straight to R2.
  3. `confirm_upload` flips the row to UPLOADED with the real size.

Rows stuck in PENDING are simply abandoned uploads and are ignored everywhere.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.core.config import settings
from app.models.file import FileCategory, ScanStatus, StoredFile, UploadStatus
from app.models.organization import Organization, SubscriptionPlan
from app.services import audit_service, storage_service, virus_scan_service

GIGABYTE = 1024 * 1024 * 1024

# Document vault storage cap per plan, in GB. Enterprise has no platform-wide
# figure — its cap, if any, lives on `Organization.storage_limit_bytes`
# (a negotiated, platform-staff-set override), not here.
PLAN_STORAGE_LIMITS_GB: dict[SubscriptionPlan, int] = {
    SubscriptionPlan.TRIAL: 5,
    SubscriptionPlan.STARTER: 5,
    SubscriptionPlan.PROFESSIONAL: 20,
    SubscriptionPlan.BUSINESS: 100,
}


def effective_storage_limit_bytes(organization: Organization) -> int | None:
    """None means unlimited — true only for Enterprise with no override set."""
    if organization.storage_limit_bytes is not None:
        return organization.storage_limit_bytes
    plan_gb = PLAN_STORAGE_LIMITS_GB.get(organization.subscription_plan)
    return plan_gb * GIGABYTE if plan_gb is not None else None


async def total_storage_bytes(db: AsyncSession, organization_id: uuid.UUID) -> int:
    total = await db.scalar(
        select(func.coalesce(func.sum(StoredFile.size_bytes), 0)).where(
            StoredFile.organization_id == organization_id, StoredFile.status == UploadStatus.UPLOADED
        )
    )
    return int(total or 0)


async def request_upload(
    db: AsyncSession,
    context: OrgContext,
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    category: FileCategory,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> tuple[StoredFile, storage_service.PresignedUpload]:
    storage_service.validate_upload(content_type, size_bytes)

    limit = effective_storage_limit_bytes(context.organization)
    if limit is not None:
        used = await total_storage_bytes(db, context.organization_id)
        if used + size_bytes > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"This would take document storage past your plan's {limit // GIGABYTE}GB limit. "
                    "Delete something you no longer need, or upgrade your plan."
                ),
            )

    storage_key = storage_service.build_storage_key(
        context.organization_id, category.value, filename, content_type
    )
    record = StoredFile(
        organization_id=context.organization_id,
        storage_key=storage_key,
        filename=filename[:255],
        content_type=content_type,
        size_bytes=size_bytes,
        category=category,
        status=UploadStatus.PENDING,
        entity_type=entity_type,
        entity_id=entity_id,
        uploaded_by_id=context.user.id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    presigned = storage_service.get_storage().presign_upload(storage_key, content_type)
    return record, presigned


async def request_upload_batch(
    db: AsyncSession, context: OrgContext, requests: list[dict]
) -> list[tuple[StoredFile, storage_service.PresignedUpload]]:
    total = sum(int(item["size_bytes"]) for item in requests)
    if total > settings.MAX_UPLOAD_BATCH_BYTES:
        limit_mb = settings.MAX_UPLOAD_BATCH_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Batch exceeds the {limit_mb}MB total upload limit",
        )
    return [await request_upload(db, context, **item) for item in requests]


async def confirm_upload(
    db: AsyncSession, context: OrgContext, file_id: uuid.UUID, size_bytes: int | None = None
) -> StoredFile:
    record = await get_file(db, context, file_id)

    if not storage_service.get_storage().exists(record.storage_key):
        record.status = UploadStatus.FAILED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No object found at the upload location — the upload did not complete",
        )

    record.status = UploadStatus.UPLOADED
    record.uploaded_at = datetime.now(UTC)
    if size_bytes:
        record.size_bytes = size_bytes

    outcome = virus_scan_service.scan_bytes(storage_service.get_storage().read(record.storage_key))
    record.scan_status = outcome.status
    record.scan_detail = outcome.detail
    record.scanned_at = datetime.now(UTC)

    if outcome.status == ScanStatus.INFECTED:
        # Never confirmed as UPLOADED, so it never becomes visible or attachable
        # anywhere in the app — the file exists on disk/R2 only long enough to be
        # scanned, then removed.
        storage_service.get_storage().delete(record.storage_key)
        record.status = UploadStatus.FAILED
        audit_service.record(
            db,
            organization_id=context.organization_id,
            action="file.infected_upload_rejected",
            entity_type="stored_file",
            entity_id=record.id,
            actor=context.user,
            summary=f"Rejected infected upload '{record.filename}' ({outcome.detail})",
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This file failed a virus scan and was not stored.",
        )

    await db.commit()
    await db.refresh(record)
    return record


async def get_file(db: AsyncSession, context: OrgContext, file_id: uuid.UUID) -> StoredFile:
    record = await db.get(StoredFile, file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if record.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access this file")
    return record


async def attach(
    db: AsyncSession,
    context: OrgContext,
    file_ids: list[uuid.UUID],
    entity_type: str,
    entity_id: uuid.UUID,
    *,
    replace: bool = False,
) -> list[StoredFile]:
    """Point a set of already-uploaded files at an entity.

    With `replace=True`, files previously attached to this entity but absent from
    `file_ids` are archived rather than deleted — history never loses a document.
    """
    attached: list[StoredFile] = []
    for file_id in file_ids:
        record = await get_file(db, context, file_id)
        record.entity_type = entity_type
        record.entity_id = entity_id
        attached.append(record)

    if replace:
        keep = set(file_ids)
        existing = await db.scalars(
            select(StoredFile).where(
                StoredFile.organization_id == context.organization_id,
                StoredFile.entity_type == entity_type,
                StoredFile.entity_id == entity_id,
                StoredFile.is_archived.is_(False),
            )
        )
        for record in existing:
            if record.id not in keep:
                record.is_archived = True

    return attached


async def list_for_entity(
    db: AsyncSession, organization_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> list[StoredFile]:
    rows = await db.scalars(
        select(StoredFile)
        .where(
            StoredFile.organization_id == organization_id,
            StoredFile.entity_type == entity_type,
            StoredFile.entity_id == entity_id,
            StoredFile.is_archived.is_(False),
            StoredFile.status == UploadStatus.UPLOADED,
        )
        .order_by(StoredFile.created_at)
    )
    return list(rows)


async def list_for_entities(
    db: AsyncSession, organization_id: uuid.UUID, entity_type: str, entity_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[StoredFile]]:
    """Batched variant — avoids an N+1 when rendering a list of property cards."""
    if not entity_ids:
        return {}
    rows = await db.scalars(
        select(StoredFile)
        .where(
            StoredFile.organization_id == organization_id,
            StoredFile.entity_type == entity_type,
            StoredFile.entity_id.in_(entity_ids),
            StoredFile.is_archived.is_(False),
            StoredFile.status == UploadStatus.UPLOADED,
        )
        .order_by(StoredFile.created_at)
    )
    grouped: dict[uuid.UUID, list[StoredFile]] = {}
    for record in rows:
        if record.entity_id:
            grouped.setdefault(record.entity_id, []).append(record)
    return grouped


async def register_generated(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    data: bytes,
    filename: str,
    category: FileCategory,
    entity_type: str,
    entity_id: uuid.UUID,
    content_type: str = "application/pdf",
) -> StoredFile:
    """Store a PDF the server produced (lease, receipt, invoice) and record it."""
    storage_key = storage_service.store_generated_document(
        organization_id, category.value, filename, data, content_type
    )
    record = StoredFile(
        organization_id=organization_id,
        storage_key=storage_key,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        category=category,
        status=UploadStatus.UPLOADED,
        entity_type=entity_type,
        entity_id=entity_id,
        uploaded_at=datetime.now(UTC),
    )
    db.add(record)
    await db.flush()
    return record


def to_url(record: StoredFile) -> str:
    return storage_service.download_url(record.storage_key, record.filename)
