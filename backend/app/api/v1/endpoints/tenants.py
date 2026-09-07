import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from jinja2 import TemplateError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.ai_analysis import LeaseAnalysis, LeaseSuggestion
from app.models.billing import Invoice, InvoiceStatus
from app.models.file import StoredFile
from app.models.property import Property, Unit
from app.models.tenant import LeaseTemplate, Tenancy, TenancyStatus, Tenant
from app.schemas.ai import LeaseAnalysisRead, LeaseSuggestionRead, ResolveSuggestionRequest
from app.schemas.tenant import (
    CoTenantAdd,
    CoTenantRead,
    LeaseTemplateCreate,
    LeaseTemplatePreview,
    LeaseTemplateRead,
    LeaseTemplateUpdate,
    TenancyCreate,
    TenancyDetail,
    TenancyRead,
    TenancyUpdate,
    TenantCreate,
    TenantListItem,
    TenantRead,
    TenantUpdate,
    VacateTenancyRequest,
)
from app.services import ai_service, audit_service, file_service, lease_service, tenant_service
from app.services.ai_service import AiServiceError

router = APIRouter()
tenancies_router = APIRouter()
lease_templates_router = APIRouter()


def _list_item(row: dict) -> TenantListItem:
    tenancy, unit, property_record = row["tenancy"], row["unit"], row["property"]
    return TenantListItem(
        **TenantRead.model_validate(row["tenant"]).model_dump(),
        unit_number=unit.unit_number if unit else None,
        property_name=property_record.name if property_record else None,
        tenancy_id=tenancy.id if tenancy else None,
        tenancy_status=tenancy.status if tenancy else None,
        monthly_rent=tenancy.monthly_rent if tenancy else None,
        lease_end_date=tenancy.end_date if tenancy else None,
        balance=row["balance"],
        payment_status=row["payment_status"],
    )


@router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    return await tenant_service.create_tenant(db, context, payload, request)


@router.get("", response_model=list[TenantListItem])
async def list_tenants(
    search: str | None = Query(default=None, max_length=255),
    tenancy_status: TenancyStatus | None = None,
    property_id: uuid.UUID | None = None,
    include_archived: bool = False,
    context: OrgContext = Depends(require(Permission.TENANT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[TenantListItem]:
    rows = await tenant_service.list_tenants(
        db,
        context,
        search=search,
        tenancy_status=tenancy_status,
        property_id=property_id,
        include_archived=include_archived,
    )
    return [_list_item(row) for row in rows]


@router.get("/export.csv")
async def export_tenants_csv(
    search: str | None = Query(default=None, max_length=255),
    tenancy_status: TenancyStatus | None = None,
    property_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require(Permission.TENANT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    rows = await tenant_service.list_tenants(
        db, context, search=search, tenancy_status=tenancy_status, property_id=property_id
    )
    filename = f"tenants-{date.today().isoformat()}.csv"
    return Response(
        content=tenant_service.to_csv(rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{tenant_id}", response_model=TenantRead)
async def get_tenant(
    tenant_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.TENANT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    return await tenant_service.get_tenant(db, context, tenant_id)


@router.patch("/{tenant_id}", response_model=TenantRead)
async def update_tenant(
    tenant_id: uuid.UUID,
    payload: TenantUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    return await tenant_service.update_tenant(db, context, tenant_id, payload, request)


@router.delete("/{tenant_id}", response_model=TenantRead)
async def archive_tenant(
    tenant_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    return await tenant_service.archive_tenant(db, context, tenant_id, request)


@router.get("/{tenant_id}/documents", response_model=list[dict])
async def tenant_documents(
    tenant_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.FILE_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """The tenant's document vault — lease, receipts, notices."""
    await tenant_service.get_tenant(db, context, tenant_id)
    records = await file_service.list_for_entity(db, context.organization_id, "tenant", tenant_id)
    return [
        {
            "id": str(record.id),
            "filename": record.filename,
            "category": record.category.value,
            "size_bytes": record.size_bytes,
            "created_at": record.created_at.isoformat(),
            "url": file_service.to_url(record),
        }
        for record in records
    ]


# ---------------------------------------------------------------------- tenancies


async def _detail(db: AsyncSession, tenancy: Tenancy) -> TenancyDetail:
    tenant = await db.get(Tenant, tenancy.tenant_id)
    unit = await db.get(Unit, tenancy.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None

    lease_url = None
    if tenancy.lease_document_id:
        record = await db.get(StoredFile, tenancy.lease_document_id)
        if record:
            lease_url = file_service.to_url(record)

    balance = await db.scalar(
        select(Invoice.total - Invoice.amount_paid)
        .where(
            Invoice.tenancy_id == tenancy.id,
            Invoice.status.notin_([InvoiceStatus.PAID, InvoiceStatus.CANCELLED]),
        )
        .limit(1)
    )

    days_to_expiry = (tenancy.end_date - date.today()).days if tenancy.end_date else None

    return TenancyDetail(
        **TenancyRead.model_validate(tenancy).model_dump(),
        tenant_name=tenant.full_name if tenant else None,
        tenant_phone=tenant.phone_number if tenant else None,
        unit_number=unit.unit_number if unit else None,
        property_name=property_record.name if property_record else None,
        property_id=property_record.id if property_record else None,
        lease_url=lease_url,
        days_to_expiry=days_to_expiry,
        balance=Decimal(balance or 0),
    )


async def _details(db: AsyncSession, tenancies: list[Tenancy]) -> list[TenancyDetail]:
    """The list view, batched.

    Building each row with `_detail` cost seven round trips per tenancy, so a
    thirty-unit portfolio opened the tenancies screen with two hundred queries.
    Each related set is fetched once here and looked up in memory.
    """
    if not tenancies:
        return []

    tenants = {
        row.id: row
        for row in await db.scalars(select(Tenant).where(Tenant.id.in_({t.tenant_id for t in tenancies})))
    }
    units = {
        row.id: row
        for row in await db.scalars(select(Unit).where(Unit.id.in_({t.unit_id for t in tenancies})))
    }
    properties = (
        {
            row.id: row
            for row in await db.scalars(
                select(Property).where(Property.id.in_({u.property_id for u in units.values()}))
            )
        }
        if units
        else {}
    )

    document_ids = {t.lease_document_id for t in tenancies if t.lease_document_id}
    documents = (
        {row.id: row for row in await db.scalars(select(StoredFile).where(StoredFile.id.in_(document_ids)))}
        if document_ids
        else {}
    )

    # One row per tenancy carrying its outstanding balance, rather than a query
    # per tenancy that returned only the first unpaid invoice.
    balance_rows = await db.execute(
        select(
            Invoice.tenancy_id,
            func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0),
        )
        .where(
            Invoice.tenancy_id.in_([t.id for t in tenancies]),
            Invoice.status.notin_([InvoiceStatus.PAID, InvoiceStatus.CANCELLED]),
        )
        .group_by(Invoice.tenancy_id)
    )
    balances = {tenancy_id: Decimal(total) for tenancy_id, total in balance_rows}

    today = date.today()
    result = []
    for tenancy in tenancies:
        tenant = tenants.get(tenancy.tenant_id)
        unit = units.get(tenancy.unit_id)
        property_record = properties.get(unit.property_id) if unit else None
        document = documents.get(tenancy.lease_document_id) if tenancy.lease_document_id else None

        result.append(
            TenancyDetail(
                **TenancyRead.model_validate(tenancy).model_dump(),
                tenant_name=tenant.full_name if tenant else None,
                tenant_phone=tenant.phone_number if tenant else None,
                unit_number=unit.unit_number if unit else None,
                property_name=property_record.name if property_record else None,
                property_id=property_record.id if property_record else None,
                lease_url=file_service.to_url(document) if document else None,
                days_to_expiry=(tenancy.end_date - today).days if tenancy.end_date else None,
                balance=balances.get(tenancy.id, Decimal("0")),
            )
        )
    return result


@tenancies_router.post("", response_model=TenancyDetail, status_code=status.HTTP_201_CREATED)
async def create_tenancy(
    payload: TenancyCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TenancyDetail:
    tenancy = await tenant_service.create_tenancy(db, context, payload, request)
    return await _detail(db, tenancy)


@tenancies_router.get("", response_model=list[TenancyDetail])
async def list_tenancies(
    tenancy_status: TenancyStatus | None = None,
    unit_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    expiring_within_days: int | None = Query(default=None, ge=0, le=365),
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[TenancyDetail]:
    rows = await tenant_service.list_tenancies(
        db,
        context,
        tenancy_status=tenancy_status,
        unit_id=unit_id,
        tenant_id=tenant_id,
        expiring_within_days=expiring_within_days,
    )
    return await _details(db, rows)


@tenancies_router.get("/{tenancy_id}", response_model=TenancyDetail)
async def get_tenancy(
    tenancy_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> TenancyDetail:
    tenancy = await tenant_service.get_tenancy(db, context, tenancy_id)
    return await _detail(db, tenancy)


@tenancies_router.patch("/{tenancy_id}", response_model=TenancyDetail)
async def update_tenancy(
    tenancy_id: uuid.UUID,
    payload: TenancyUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TenancyDetail:
    tenancy = await tenant_service.update_tenancy(db, context, tenancy_id, payload, request)
    return await _detail(db, tenancy)


@tenancies_router.post("/{tenancy_id}/vacate", response_model=TenancyDetail)
async def vacate_tenancy(
    tenancy_id: uuid.UUID,
    payload: VacateTenancyRequest,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TenancyDetail:
    tenancy = await tenant_service.vacate_tenancy(
        db, context, tenancy_id, payload.move_out_date, payload.notes, request
    )
    return await _detail(db, tenancy)


@tenancies_router.get("/{tenancy_id}/co-tenants", response_model=list[CoTenantRead])
async def list_co_tenants(
    tenancy_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[CoTenantRead]:
    rows = await tenant_service.list_co_tenants(db, context, tenancy_id)
    return [
        CoTenantRead(
            **CoTenantRead.model_validate(co_tenant).model_dump(exclude={"tenant_name", "tenant_phone"}),
            tenant_name=tenant.full_name if tenant else None,
            tenant_phone=tenant.phone_number if tenant else None,
        )
        for co_tenant, tenant in rows
    ]


@tenancies_router.post(
    "/{tenancy_id}/co-tenants", response_model=CoTenantRead, status_code=status.HTTP_201_CREATED
)
async def add_co_tenant(
    tenancy_id: uuid.UUID,
    payload: CoTenantAdd,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.CO_TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CoTenantRead:
    co_tenant = await tenant_service.add_co_tenant(db, context, tenancy_id, payload.tenant_id, request)
    tenant = await db.get(Tenant, co_tenant.tenant_id)
    return CoTenantRead(
        **CoTenantRead.model_validate(co_tenant).model_dump(exclude={"tenant_name", "tenant_phone"}),
        tenant_name=tenant.full_name if tenant else None,
        tenant_phone=tenant.phone_number if tenant else None,
    )


@tenancies_router.delete("/{tenancy_id}/co-tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_co_tenant(
    tenancy_id: uuid.UUID,
    tenant_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.CO_TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    await tenant_service.remove_co_tenant(db, context, tenancy_id, tenant_id, request)


@tenancies_router.post("/{tenancy_id}/co-tenants/{tenant_id}/promote", response_model=TenancyDetail)
async def promote_co_tenant(
    tenancy_id: uuid.UUID,
    tenant_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.CO_TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TenancyDetail:
    """Swap the primary tenant to a co-tenant — the partial-turnover case
    where the current primary is moving out and a co-tenant is staying."""
    tenancy = await tenant_service.promote_co_tenant(db, context, tenancy_id, tenant_id, request)
    return await _detail(db, tenancy)


@tenancies_router.post("/{tenancy_id}/lease", response_model=dict)
async def regenerate_lease(
    tenancy_id: uuid.UUID,
    request: Request,
    template_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenancy = await tenant_service.get_tenancy(db, context, tenancy_id)
    record = await lease_service.generate_and_store_lease(db, tenancy, template_id)
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="tenancy.lease_regenerated",
        entity_type="tenancy",
        entity_id=tenancy.id,
        actor=context.user,
        summary=f"Regenerated the lease for {tenancy.reference_code}",
        request=request,
    )
    await db.commit()
    return {"file_id": str(record.id), "filename": record.filename, "url": file_service.to_url(record)}


@tenancies_router.get("/{tenancy_id}/lease/preview")
async def preview_lease(
    tenancy_id: uuid.UUID,
    template_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the lease on the fly without storing it — powers in-browser preview."""
    tenancy = await tenant_service.get_tenancy(db, context, tenancy_id)
    pdf_bytes = await lease_service.generate_lease_pdf(db, tenancy, template_id=template_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="Lease-{tenancy.reference_code}.pdf"'},
    )


# ----------------------------------------------------------------- lease templates


@lease_templates_router.get("", response_model=list[LeaseTemplateRead])
async def list_lease_templates(
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[LeaseTemplate]:
    rows = await db.scalars(
        select(LeaseTemplate)
        .where(
            LeaseTemplate.organization_id == context.organization_id,
            LeaseTemplate.is_archived.is_(False),
        )
        .order_by(LeaseTemplate.created_at.desc())
    )
    return list(rows)


@lease_templates_router.get("/starter", response_model=dict)
async def starter_template(
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
) -> dict:
    """The built-in body, offered as a starting point in the template editor."""
    return {
        "body_html": lease_service.STARTER_TEMPLATE_HTML,
        # Derived from the sample set, so the editor's variable list can never
        # drift from what a lease actually substitutes.
        "variables": lease_service.TEMPLATE_VARIABLES,
        "sample_values": lease_service.SAMPLE_VARIABLES,
    }


@lease_templates_router.post("/preview")
async def preview_lease_template(
    payload: LeaseTemplatePreview,
    context: OrgContext = Depends(require_write(Permission.LEASE_TEMPLATE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render a template body as a PDF filled with sample data.

    Takes the body from the request rather than the database so unsaved edits in
    the template editor can be previewed before they are committed.
    """
    from app.api.deps import assert_in_org

    body_html = payload.body_html
    letterhead_text = payload.letterhead_text
    logo_file_id = payload.logo_file_id

    if payload.template_id is not None:
        template = assert_in_org(await db.get(LeaseTemplate, payload.template_id), context, label="template")
        body_html = body_html or template.body_html
        letterhead_text = letterhead_text or template.letterhead_text
        logo_file_id = logo_file_id or template.logo_file_id

    if not body_html:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Send a template body, or the id of a saved template, to preview",
        )

    try:
        pdf_bytes = await lease_service.preview_template_pdf(
            db,
            context.organization,
            body_html=body_html,
            letterhead_text=letterhead_text,
            logo_file_id=logo_file_id,
        )
    except TemplateError as exc:
        # A malformed placeholder is the author's mistake, not a server fault —
        # tell them which one so the editor can point at it.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The template could not be rendered: {exc}",
        ) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="lease-template-preview.pdf"'},
    )


@lease_templates_router.post("", response_model=LeaseTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_lease_template(
    payload: LeaseTemplateCreate,
    context: OrgContext = Depends(require_write(Permission.LEASE_TEMPLATE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> LeaseTemplate:
    if payload.is_default:
        await _clear_default(db, context.organization_id)

    template = LeaseTemplate(organization_id=context.organization_id, **payload.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@lease_templates_router.patch("/{template_id}", response_model=LeaseTemplateRead)
async def update_lease_template(
    template_id: uuid.UUID,
    payload: LeaseTemplateUpdate,
    context: OrgContext = Depends(require_write(Permission.LEASE_TEMPLATE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> LeaseTemplate:
    from app.api.deps import assert_in_org

    template = assert_in_org(await db.get(LeaseTemplate, template_id), context, label="template")
    fields = payload.model_dump(exclude_unset=True)

    if fields.get("is_default"):
        await _clear_default(db, context.organization_id)
    for field, value in fields.items():
        setattr(template, field, value)
    if "body_html" in fields:
        # Bump the version so already-generated leases stay attributable to the
        # wording that produced them (US-047).
        template.version += 1

    await db.commit()
    await db.refresh(template)
    return template


async def _clear_default(db: AsyncSession, organization_id: uuid.UUID) -> None:
    for template in await db.scalars(
        select(LeaseTemplate).where(
            LeaseTemplate.organization_id == organization_id, LeaseTemplate.is_default.is_(True)
        )
    ):
        template.is_default = False


# ------------------------------------------------------- AI lease analysis (US-096)


@lease_templates_router.post("/{template_id}/analyze", response_model=LeaseAnalysisRead)
async def analyze_lease_template(
    template_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.LEASE_TEMPLATE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> LeaseAnalysis:
    from app.api.deps import assert_in_org

    template = assert_in_org(await db.get(LeaseTemplate, template_id), context, label="template")
    try:
        return await ai_service.analyze_template(db, context, template, request)
    except AiServiceError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@lease_templates_router.get("/{template_id}/analyses", response_model=list[LeaseAnalysisRead])
async def list_lease_analyses(
    template_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.LEASE_TEMPLATE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[LeaseAnalysis]:
    from app.api.deps import assert_in_org

    assert_in_org(await db.get(LeaseTemplate, template_id), context, label="template")
    return await ai_service.list_analyses(db, context, template_id)


@lease_templates_router.patch("/suggestions/{suggestion_id}", response_model=LeaseSuggestionRead)
async def resolve_lease_suggestion(
    suggestion_id: uuid.UUID,
    payload: ResolveSuggestionRequest,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.LEASE_TEMPLATE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> LeaseSuggestion:
    return await ai_service.resolve_suggestion(
        db, context, suggestion_id, new_status=payload.status, request=request
    )
