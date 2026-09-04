"""Document vault API — Phase 2 (US-045, US-046, US-047, US-048).

One organised view per tenant and per property, the write side for an agency's
own paperwork, version history, storage usage, and WhatsApp delivery.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.file import FileCategory
from app.services import vault_service

router = APIRouter()


# ----------------------------------------------------------------- schemas


class FileDocument(BaseModel):
    file_id: uuid.UUID
    entity_type: str = Field(max_length=64)
    entity_id: uuid.UUID
    category: FileCategory
    tags: list[str] = Field(default_factory=list, max_length=20)
    description: str | None = Field(default=None, max_length=2000)


class UpdateDocument(BaseModel):
    category: FileCategory | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=2000)
    filename: str | None = Field(default=None, min_length=1, max_length=255)


class NewVersion(BaseModel):
    file_id: uuid.UUID
    description: str | None = Field(default=None, max_length=2000)


class DeliverDocument(BaseModel):
    tenant_id: uuid.UUID | None = None
    phone_number: str | None = Field(default=None, max_length=32)
    message: str | None = Field(default=None, max_length=1000)


# ----------------------------------------------------------------- vault views


@router.get("/tenants/{tenant_id}")
async def tenant_vault(
    tenant_id: uuid.UUID,
    category: FileCategory | None = None,
    search: str | None = Query(default=None, max_length=120),
    include_archived: bool = False,
    context: OrgContext = Depends(require(Permission.FILE_VIEW, Permission.TENANT_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Every document belonging to one tenant, grouped by type and dated."""
    return await vault_service.tenant_vault(
        db,
        context,
        tenant_id,
        category=category,
        search=search,
        include_archived=include_archived,
    )


@router.get("/properties/{property_id}")
async def property_vault(
    property_id: uuid.UUID,
    category: FileCategory | None = None,
    search: str | None = Query(default=None, max_length=120),
    include_archived: bool = False,
    context: OrgContext = Depends(require(Permission.FILE_VIEW, Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Every document belonging to a property, its units and their tenancies."""
    return await vault_service.property_vault(
        db,
        context,
        property_id,
        category=category,
        search=search,
        include_archived=include_archived,
    )


@router.get("/usage")
async def storage_usage(
    context: OrgContext = Depends(require(Permission.FILE_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """How much storage the account is using, broken down by document type."""
    return await vault_service.storage_usage(db, context)


@router.get("/categories")
async def vault_categories(context: OrgContext = Depends(require(Permission.FILE_VIEW))):
    """Which categories a person may upload into, and the order each vault renders."""
    return {
        "uploadable": sorted(c.value for c in vault_service.UPLOADABLE_CATEGORIES),
        "tenant_order": [c.value for c in vault_service.TENANT_VAULT_CATEGORIES],
        "property_order": [c.value for c in vault_service.PROPERTY_VAULT_CATEGORIES],
    }


# ----------------------------------------------------------------- documents


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def file_document(
    body: FileDocument,
    context: OrgContext = Depends(require_write(Permission.FILE_UPLOAD)),
    db: AsyncSession = Depends(get_db),
):
    """File a confirmed upload into a vault, categorised and tagged."""
    record = await vault_service.file_document(
        db,
        context,
        body.file_id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        category=body.category,
        tags=body.tags,
        description=body.description,
    )
    return vault_service.serialize(record)


@router.patch("/documents/{file_id}")
async def update_document(
    file_id: uuid.UUID,
    body: UpdateDocument,
    context: OrgContext = Depends(require_write(Permission.FILE_UPLOAD)),
    db: AsyncSession = Depends(get_db),
):
    record = await vault_service.update_document(
        db,
        context,
        file_id,
        category=body.category,
        tags=body.tags,
        description=body.description,
        filename=body.filename,
    )
    return vault_service.serialize(record)


@router.post("/documents/{file_id}/versions", status_code=status.HTTP_201_CREATED)
async def add_version(
    file_id: uuid.UUID,
    body: NewVersion,
    context: OrgContext = Depends(require_write(Permission.FILE_UPLOAD)),
    db: AsyncSession = Depends(get_db),
):
    """Replace a document with a newer upload. The old one is archived, not lost."""
    record = await vault_service.add_version(db, context, file_id, body.file_id, description=body.description)
    return vault_service.serialize(record)


@router.get("/documents/{file_id}/versions")
async def version_history(
    file_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.FILE_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """The full chain for a document, newest version first."""
    chain = await vault_service.version_history(db, context, file_id)
    return [vault_service.serialize(record) for record in chain]


@router.delete("/documents/{file_id}")
async def archive_document(
    file_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.FILE_UPLOAD)),
    db: AsyncSession = Depends(get_db),
):
    """Take a document out of the vault view. Nothing is deleted."""
    record = await vault_service.archive_document(db, context, file_id)
    return vault_service.serialize(record)


@router.post("/documents/{file_id}/send")
async def send_document(
    file_id: uuid.UUID,
    body: DeliverDocument,
    context: OrgContext = Depends(require_write(Permission.FILE_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Send a vault document to a tenant or a phone number on WhatsApp."""
    return await vault_service.deliver_document(
        db,
        context,
        file_id,
        tenant_id=body.tenant_id,
        phone_number=body.phone_number,
        message=body.message,
    )
