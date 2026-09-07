"""The public REST API (US-085): read-only access to an organization's core
resources for an integrator holding an API key.

Every route shares one envelope (`{"status", "data", "errors"}`) and one
pagination shape (keyset on `created_at, id` — see `app.schemas.pagination`).
Field selection (`?fields=id,name`) is why routes build plain dicts and hand
them to `jsonable_encoder` themselves instead of declaring a `response_model`:
a response model can't drop keys a caller didn't ask for.
"""

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.external_deps import ApiKeyContext, require_scope
from app.core.config import settings
from app.core.database import get_db
from app.models.billing import Invoice, Payment
from app.models.developer import ApiKeyScope
from app.models.property import Property, Unit
from app.models.tenant import Tenant
from app.schemas.pagination import decode_cursor, encode_cursor
from app.services import tenant_pii

router = APIRouter()


def _ok(data: Any, *, next_cursor: str | None = None, has_more: bool | None = None) -> JSONResponse:
    meta = None
    if has_more is not None:
        meta = {"next_cursor": next_cursor, "has_more": has_more}
    envelope = {"status": "ok", "data": data, "errors": None, "meta": meta}
    return JSONResponse(content=jsonable_encoder(envelope))


def _select_fields(row: dict[str, Any], fields: str | None) -> dict[str, Any]:
    if not fields:
        return row
    wanted = {f.strip() for f in fields.split(",") if f.strip()}
    return {key: value for key, value in row.items() if key in wanted}


async def _paginate(
    db: AsyncSession,
    model: Any,
    filters: list[Any],
    *,
    cursor: str | None,
    limit: int,
    sort: str,
    serialize: Callable[[Any], dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None, bool]:
    ascending = sort == "asc"
    query: Any = select(model).where(*filters)
    query = query.order_by(
        model.created_at.asc() if ascending else model.created_at.desc(),
        model.id.asc() if ascending else model.id.desc(),
    )

    if cursor:
        pos = decode_cursor(cursor)
        same_moment = model.created_at == pos.created_at
        if ascending:
            query = query.where(or_(model.created_at > pos.created_at, and_(same_moment, model.id > pos.id)))
        else:
            query = query.where(or_(model.created_at < pos.created_at, and_(same_moment, model.id < pos.id)))

    rows = list(await db.scalars(query.limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    return [serialize(row) for row in rows], next_cursor, has_more


def _property_row(row: Property) -> dict[str, Any]:
    return {
        "id": row.id,
        "reference_code": row.reference_code,
        "name": row.name,
        "property_type": row.property_type.value,
        "address": row.address,
        "county": row.county,
        "sub_county": row.sub_county,
        "description": row.description,
        "amenities": row.amenities,
        "is_archived": row.is_archived,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _unit_row(row: Unit) -> dict[str, Any]:
    return {
        "id": row.id,
        "property_id": row.property_id,
        "reference_code": row.reference_code,
        "unit_number": row.unit_number,
        "unit_type": row.unit_type,
        "size_sqm": row.size_sqm,
        "floor": row.floor,
        "bedrooms": row.bedrooms,
        "bathrooms": row.bathrooms,
        "monthly_rent": row.monthly_rent,
        "deposit_amount": row.deposit_amount,
        "status": row.status.value,
        "is_archived": row.is_archived,
        "created_at": row.created_at,
    }


def _tenant_row(row: Tenant) -> dict[str, Any]:
    # `national_id` here is whatever `row.national_id` currently holds — the
    # masked last-4 hint by default (list view, below), or the fully
    # decrypted value if a caller set it first (the single-tenant endpoint).
    return {
        "id": row.id,
        "reference_code": row.reference_code,
        "full_name": row.full_name,
        "phone_number": row.phone_number,
        "email": row.email,
        "national_id": getattr(row, "national_id", None) or tenant_pii.masked_national_id(row),
        "is_archived": row.is_archived,
        "created_at": row.created_at,
    }


def _invoice_row(row: Invoice) -> dict[str, Any]:
    return {
        "id": row.id,
        "reference_code": row.reference_code,
        "tenancy_id": row.tenancy_id,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "issue_date": row.issue_date,
        "due_date": row.due_date,
        "total": row.total,
        "amount_paid": row.amount_paid,
        "status": row.status.value,
        "created_at": row.created_at,
    }


def _payment_row(row: Payment) -> dict[str, Any]:
    return {
        "id": row.id,
        "reference_code": row.reference_code,
        "tenancy_id": row.tenancy_id,
        "invoice_id": row.invoice_id,
        "amount": row.amount,
        "method": row.method.value,
        "status": row.status.value,
        "mpesa_receipt": row.mpesa_receipt,
        "paid_at": row.paid_at,
        "payment_date": row.payment_date,
        "created_at": row.created_at,
    }


def _page_size(limit: int) -> int:
    return min(limit, settings.API_MAX_PAGE_SIZE)


@router.get("/properties")
async def list_properties(
    property_type: str | None = None,
    county: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    fields: str | None = None,
    context: ApiKeyContext = Depends(require_scope(ApiKeyScope.PROPERTIES_READ)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    filters: list[Any] = [Property.organization_id == context.organization_id]
    if property_type:
        filters.append(Property.property_type == property_type)
    if county:
        filters.append(Property.county == county)
    data, next_cursor, has_more = await _paginate(
        db, Property, filters, cursor=cursor, limit=_page_size(limit), sort=sort, serialize=_property_row
    )
    return _ok([_select_fields(row, fields) for row in data], next_cursor=next_cursor, has_more=has_more)


@router.get("/properties/{property_id}")
async def get_property(
    property_id: uuid.UUID,
    fields: str | None = None,
    context: ApiKeyContext = Depends(require_scope(ApiKeyScope.PROPERTIES_READ)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    row = await db.scalar(
        select(Property).where(
            Property.id == property_id, Property.organization_id == context.organization_id
        )
    )
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "data": None, "errors": ["Property not found"]},
        )
    return _ok(_select_fields(_property_row(row), fields))


@router.get("/units")
async def list_units(
    property_id: uuid.UUID | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    fields: str | None = None,
    context: ApiKeyContext = Depends(require_scope(ApiKeyScope.UNITS_READ)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    filters: list[Any] = [Unit.organization_id == context.organization_id]
    if property_id:
        filters.append(Unit.property_id == property_id)
    if status:
        filters.append(Unit.status == status)
    data, next_cursor, has_more = await _paginate(
        db, Unit, filters, cursor=cursor, limit=_page_size(limit), sort=sort, serialize=_unit_row
    )
    return _ok([_select_fields(row, fields) for row in data], next_cursor=next_cursor, has_more=has_more)


@router.get("/units/{unit_id}")
async def get_unit(
    unit_id: uuid.UUID,
    fields: str | None = None,
    context: ApiKeyContext = Depends(require_scope(ApiKeyScope.UNITS_READ)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    row = await db.scalar(
        select(Unit).where(Unit.id == unit_id, Unit.organization_id == context.organization_id)
    )
    if row is None:
        return JSONResponse(
            status_code=404, content={"status": "error", "data": None, "errors": ["Unit not found"]}
        )
    return _ok(_select_fields(_unit_row(row), fields))


@router.get("/tenants")
async def list_tenants(
    search: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    fields: str | None = None,
    context: ApiKeyContext = Depends(require_scope(ApiKeyScope.TENANTS_READ)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    filters: list[Any] = [Tenant.organization_id == context.organization_id]
    if search:
        needle = f"%{search}%"
        filters.append(or_(Tenant.full_name.ilike(needle), Tenant.phone_number.ilike(needle)))
    data, next_cursor, has_more = await _paginate(
        db, Tenant, filters, cursor=cursor, limit=_page_size(limit), sort=sort, serialize=_tenant_row
    )
    return _ok([_select_fields(row, fields) for row in data], next_cursor=next_cursor, has_more=has_more)


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: uuid.UUID,
    fields: str | None = None,
    context: ApiKeyContext = Depends(require_scope(ApiKeyScope.TENANTS_READ)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    row = await db.scalar(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.organization_id == context.organization_id)
    )
    if row is None:
        return JSONResponse(
            status_code=404, content={"status": "error", "data": None, "errors": ["Tenant not found"]}
        )
    row.national_id = await tenant_pii.decrypt_national_id(db, row)
    return _ok(_select_fields(_tenant_row(row), fields))


@router.get("/invoices")
async def list_invoices(
    status: str | None = None,
    tenancy_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    fields: str | None = None,
    context: ApiKeyContext = Depends(require_scope(ApiKeyScope.INVOICES_READ)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    filters: list[Any] = [Invoice.organization_id == context.organization_id]
    if status:
        filters.append(Invoice.status == status)
    if tenancy_id:
        filters.append(Invoice.tenancy_id == tenancy_id)
    data, next_cursor, has_more = await _paginate(
        db, Invoice, filters, cursor=cursor, limit=_page_size(limit), sort=sort, serialize=_invoice_row
    )
    return _ok([_select_fields(row, fields) for row in data], next_cursor=next_cursor, has_more=has_more)


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: uuid.UUID,
    fields: str | None = None,
    context: ApiKeyContext = Depends(require_scope(ApiKeyScope.INVOICES_READ)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    row = await db.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.organization_id == context.organization_id)
    )
    if row is None:
        return JSONResponse(
            status_code=404, content={"status": "error", "data": None, "errors": ["Invoice not found"]}
        )
    return _ok(_select_fields(_invoice_row(row), fields))


@router.get("/payments")
async def list_payments(
    status: str | None = None,
    tenancy_id: uuid.UUID | None = None,
    method: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    fields: str | None = None,
    context: ApiKeyContext = Depends(require_scope(ApiKeyScope.PAYMENTS_READ)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    filters: list[Any] = [Payment.organization_id == context.organization_id]
    if status:
        filters.append(Payment.status == status)
    if tenancy_id:
        filters.append(Payment.tenancy_id == tenancy_id)
    if method:
        filters.append(Payment.method == method)
    data, next_cursor, has_more = await _paginate(
        db, Payment, filters, cursor=cursor, limit=_page_size(limit), sort=sort, serialize=_payment_row
    )
    return _ok([_select_fields(row, fields) for row in data], next_cursor=next_cursor, has_more=has_more)


@router.get("/payments/{payment_id}")
async def get_payment(
    payment_id: uuid.UUID,
    fields: str | None = None,
    context: ApiKeyContext = Depends(require_scope(ApiKeyScope.PAYMENTS_READ)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    row = await db.scalar(
        select(Payment).where(Payment.id == payment_id, Payment.organization_id == context.organization_id)
    )
    if row is None:
        return JSONResponse(
            status_code=404, content={"status": "error", "data": None, "errors": ["Payment not found"]}
        )
    return _ok(_select_fields(_payment_row(row), fields))
