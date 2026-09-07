"""Cross-entity search (Sprint 26A, item 10) — the backend for the command palette.

108 routes and no way to jump straight to "that tenant" or "that invoice"
without knowing which list screen it lives on was the gap. One endpoint,
`GET /api/v1/search`, fans a query out across the entity types people
actually go looking for by name/reference/number, respects the same
caretaker property-scoping every list endpoint already enforces
(`app.api.deps.accessible_property_ids`), and skips any entity type the
caller's role cannot view rather than 403ing the whole request over one type.

Five entity types today — tenants, properties, units, invoices, maintenance
requests — chosen as the ones a landlord or caretaker actually types a name
or reference code into a search box to find. Payments, vendors and the rest
follow the same `_search_x` shape and are a mechanical addition each, not a
design change, whenever they turn out to be worth the extra query per search.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, accessible_property_ids
from app.core.permissions import Permission
from app.models.billing import Invoice
from app.models.operations import MaintenanceRequest
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, Tenant

RESULTS_PER_TYPE = 6


@dataclass(slots=True)
class SearchResult:
    type: str
    id: uuid.UUID
    title: str
    subtitle: str
    url: str


async def _property_scope(db: AsyncSession, context: OrgContext, query: Select, property_id_column) -> Select:
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(property_id_column.in_(allowed))
    return query


async def _search_tenants(db: AsyncSession, context: OrgContext, pattern: str) -> list[SearchResult]:
    query = (
        select(Tenant)
        .outerjoin(Tenancy, Tenancy.tenant_id == Tenant.id)
        .outerjoin(Unit, Unit.id == Tenancy.unit_id)
        .where(
            Tenant.organization_id == context.organization_id,
            Tenant.is_archived.is_(False),
            (Tenant.full_name.ilike(pattern))
            | (Tenant.phone_number.ilike(pattern))
            | (Tenant.reference_code.ilike(pattern)),
        )
        .distinct()
    )
    query = await _property_scope(db, context, query, Unit.property_id)
    rows = (await db.scalars(query.limit(RESULTS_PER_TYPE))).all()
    return [
        SearchResult(
            type="tenant",
            id=tenant.id,
            title=tenant.full_name,
            subtitle=f"{tenant.reference_code} · {tenant.phone_number}",
            url=f"/tenants/{tenant.id}",
        )
        for tenant in rows
    ]


async def _search_properties(db: AsyncSession, context: OrgContext, pattern: str) -> list[SearchResult]:
    query = select(Property).where(
        Property.organization_id == context.organization_id,
        Property.is_archived.is_(False),
        (Property.name.ilike(pattern)) | (Property.reference_code.ilike(pattern)),
    )
    query = await _property_scope(db, context, query, Property.id)
    rows = (await db.scalars(query.limit(RESULTS_PER_TYPE))).all()
    return [
        SearchResult(
            type="property",
            id=prop.id,
            title=prop.name,
            subtitle=prop.reference_code,
            url=f"/properties/{prop.id}",
        )
        for prop in rows
    ]


async def _search_units(db: AsyncSession, context: OrgContext, pattern: str) -> list[SearchResult]:
    query = (
        select(Unit, Property.name)
        .join(Property, Property.id == Unit.property_id)
        .where(
            Unit.organization_id == context.organization_id,
            Unit.is_archived.is_(False),
            (Unit.unit_number.ilike(pattern)) | (Unit.reference_code.ilike(pattern)),
        )
    )
    query = await _property_scope(db, context, query, Unit.property_id)
    rows = (await db.execute(query.limit(RESULTS_PER_TYPE))).all()
    return [
        SearchResult(
            type="unit",
            id=unit.id,
            title=f"Unit {unit.unit_number}",
            subtitle=property_name,
            url=f"/properties/{unit.property_id}/units/{unit.id}",
        )
        for unit, property_name in rows
    ]


async def _search_invoices(db: AsyncSession, context: OrgContext, pattern: str) -> list[SearchResult]:
    query = (
        select(Invoice, Tenant.full_name)
        .join(Tenancy, Tenancy.id == Invoice.tenancy_id)
        .join(Tenant, Tenant.id == Tenancy.tenant_id)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .where(Invoice.organization_id == context.organization_id, Invoice.reference_code.ilike(pattern))
    )
    query = await _property_scope(db, context, query, Unit.property_id)
    rows = (await db.execute(query.limit(RESULTS_PER_TYPE))).all()
    return [
        SearchResult(
            type="invoice",
            id=invoice.id,
            title=invoice.reference_code,
            subtitle=tenant_name,
            url=f"/invoices/{invoice.id}",
        )
        for invoice, tenant_name in rows
    ]


async def _search_maintenance(db: AsyncSession, context: OrgContext, pattern: str) -> list[SearchResult]:
    query = (
        select(MaintenanceRequest)
        .join(Unit, Unit.id == MaintenanceRequest.unit_id)
        .where(
            MaintenanceRequest.organization_id == context.organization_id,
            (MaintenanceRequest.reference_code.ilike(pattern)) | (MaintenanceRequest.title.ilike(pattern)),
        )
    )
    query = await _property_scope(db, context, query, Unit.property_id)
    rows = (await db.scalars(query.limit(RESULTS_PER_TYPE))).all()
    return [
        SearchResult(
            type="maintenance_request",
            id=request.id,
            title=request.title,
            subtitle=request.reference_code,
            url=f"/maintenance/{request.id}",
        )
        for request in rows
    ]


async def search(db: AsyncSession, context: OrgContext, query: str) -> list[SearchResult]:
    trimmed = query.strip()
    if len(trimmed) < 2:
        return []
    pattern = f"%{trimmed}%"

    results: list[SearchResult] = []
    if context.can(Permission.TENANT_VIEW):
        results += await _search_tenants(db, context, pattern)
    if context.can(Permission.PROPERTY_VIEW):
        results += await _search_properties(db, context, pattern)
    if context.can(Permission.UNIT_VIEW):
        results += await _search_units(db, context, pattern)
    if context.can(Permission.INVOICE_VIEW):
        results += await _search_invoices(db, context, pattern)
    if context.can(Permission.MAINTENANCE_VIEW):
        results += await _search_maintenance(db, context, pattern)
    return results
