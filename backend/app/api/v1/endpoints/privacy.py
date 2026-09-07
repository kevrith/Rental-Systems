"""Data subject access & erasure requests — operator side (Sprint 25, US-106).

The tenant-facing self-service equivalents live in `app.api.v1.endpoints.portal`
(a tenant can only ever act on their own record); this router is for an owner
or agency raising a request on a tenant's behalf, or reviewing the history of
requests already made.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.file import StoredFile
from app.models.legal_hold import LegalHold
from app.models.privacy import DataRequest
from app.models.tenant import Tenant
from app.schemas.privacy import (
    DataRequestDetail,
    DataRequestRead,
    LegalHoldCreate,
    LegalHoldRead,
    LegalHoldRelease,
)
from app.services import file_service, legal_hold_service, privacy_service

router = APIRouter()


@router.post("/tenants/{tenant_id}/export", response_model=DataRequestDetail)
async def request_tenant_export(
    tenant_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.DATA_REQUEST_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> DataRequestDetail:
    tenant = await privacy_service.get_tenant_for_operator(db, context, tenant_id)
    data_request = await privacy_service.export_tenant_data(
        db,
        organization_id=context.organization_id,
        tenant=tenant,
        requested_by_id=context.user.id,
        request=request,
    )
    return await _to_detail(db, data_request, tenant_name=tenant.full_name)


@router.post("/tenants/{tenant_id}/erase", response_model=DataRequestDetail)
async def request_tenant_erasure(
    tenant_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.DATA_REQUEST_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> DataRequestDetail:
    tenant = await privacy_service.get_tenant_for_operator(db, context, tenant_id)
    data_request = await privacy_service.erase_tenant_data(
        db,
        organization_id=context.organization_id,
        tenant=tenant,
        requested_by_id=context.user.id,
        request=request,
    )
    return await _to_detail(db, data_request, tenant_name=tenant.full_name)


@router.get("/data-requests", response_model=list[DataRequestDetail])
async def list_data_requests(
    tenant_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require(Permission.DATA_REQUEST_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[DataRequestDetail]:
    rows = await privacy_service.list_data_requests(db, context, tenant_id)
    return [await _to_detail(db, row) for row in rows]


@router.post("/legal-holds", response_model=LegalHoldRead, status_code=status.HTTP_201_CREATED)
async def place_legal_hold(
    payload: LegalHoldCreate,
    context: OrgContext = Depends(require_write(Permission.DATA_REQUEST_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> LegalHold:
    if payload.requires_entity_id and payload.entity_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"entity_id is required for a '{payload.entity_type}' hold",
        )
    hold = await legal_hold_service.place_hold(
        db,
        organization_id=context.organization_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        reason=payload.reason,
        placed_by_id=context.user.id,
        placed_by_name=context.user.full_name,
    )
    await db.commit()
    await db.refresh(hold)
    return hold


@router.get("/legal-holds", response_model=list[LegalHoldRead])
async def list_legal_holds(
    include_released: bool = False,
    context: OrgContext = Depends(require(Permission.DATA_REQUEST_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[LegalHold]:
    return await legal_hold_service.list_holds(db, context.organization_id, include_released=include_released)


@router.post("/legal-holds/{hold_id}/release", response_model=LegalHoldRead)
async def release_legal_hold(
    hold_id: uuid.UUID,
    payload: LegalHoldRelease,
    context: OrgContext = Depends(require_write(Permission.DATA_REQUEST_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> LegalHold:
    hold = await db.get(LegalHold, hold_id)
    if hold is None or hold.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal hold not found")
    if hold.released_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This hold was already released")
    await legal_hold_service.release_hold(
        db,
        hold,
        released_by_id=context.user.id,
        released_by_name=context.user.full_name,
        note=payload.note,
    )
    await db.commit()
    await db.refresh(hold)
    return hold


async def _to_detail(
    db: AsyncSession, data_request: DataRequest, tenant_name: str | None = None
) -> DataRequestDetail:
    export_url = None
    if data_request.export_file_id:
        stored = await db.get(StoredFile, data_request.export_file_id)
        if stored:
            export_url = file_service.to_url(stored)
    if tenant_name is None:
        tenant = await db.get(Tenant, data_request.tenant_id)
        tenant_name = tenant.full_name if tenant else None

    return DataRequestDetail(
        **DataRequestRead.model_validate(data_request).model_dump(),
        tenant_name=tenant_name,
        export_url=export_url,
    )
