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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.core.config import settings
from app.models.file import FileCategory, StoredFile, UploadStatus
from app.services import storage_service


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
