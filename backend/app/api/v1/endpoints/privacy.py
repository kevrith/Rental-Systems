"""Data subject access & erasure requests — operator side (Sprint 25, US-106).

The tenant-facing self-service equivalents live in `app.api.v1.endpoints.portal`
(a tenant can only ever act on their own record); this router is for an owner
or agency raising a request on a tenant's behalf, or reviewing the history of
requests already made.
"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.file import StoredFile
from app.models.privacy import DataRequest
from app.models.tenant import Tenant
from app.schemas.privacy import DataRequestDetail, DataRequestRead
from app.services import file_service, privacy_service

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
