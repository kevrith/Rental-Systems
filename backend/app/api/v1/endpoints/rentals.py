"""Vehicle and equipment hire (US-082, US-083)."""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.asset import AgreementStatus, AssetKind, AssetStatus, RentalAgreement, RentalAsset
from app.models.file import StoredFile
from app.models.tenant import Tenant
from app.schemas.asset import (
    AgreementCancel,
    AgreementCreate,
    AgreementDetail,
    AgreementRead,
    AssetCreate,
    AssetDetail,
    AssetRead,
    AssetUpdate,
    AvailabilityRow,
    CheckIn,
    CheckOut,
    FleetOverview,
)
from app.services import file_service, rental_service

assets_router = APIRouter()
agreements_router = APIRouter()


async def _urls(db: AsyncSession, file_ids: list) -> list[str]:
    urls = []
    for file_id in file_ids:
        record = await db.get(StoredFile, uuid.UUID(str(file_id)))
        if record:
            urls.append(file_service.to_url(record))
    return urls


async def _asset_detail(db: AsyncSession, asset: RentalAsset) -> AssetDetail:
    live = await rental_service._live_agreement(db, asset.id)
    hirer = await db.get(Tenant, live.tenant_id) if (live and live.tenant_id) else None

    return AssetDetail(
        **AssetRead.model_validate(asset).model_dump(),
        photo_urls=await _urls(db, asset.photo_file_ids),
        current_hire=live.reference_code if live else None,
        current_hirer=hirer.full_name if hirer else (live.hirer_name if live else None),
    )


async def _agreement_detail(db: AsyncSession, agreement: RentalAgreement) -> AgreementDetail:
    asset = await db.get(RentalAsset, agreement.asset_id)
    tenant = await db.get(Tenant, agreement.tenant_id) if agreement.tenant_id else None

    return AgreementDetail(
        **AgreementRead.model_validate(agreement).model_dump(),
        asset_name=asset.name if asset else None,
        asset_kind=asset.kind if asset else None,
        registration_number=asset.registration_number if asset else None,
        hirer_name=tenant.full_name if tenant else agreement.hirer_name,
        hirer_phone=tenant.phone_number if tenant else agreement.hirer_phone,
        photos_out_urls=await _urls(db, agreement.photos_out),
        photos_in_urls=await _urls(db, agreement.photos_in),
    )


# ---------------------------------------------------------------------- assets


@assets_router.get("/overview", response_model=FleetOverview)
async def fleet_overview(
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> FleetOverview:
    """What is out, what is free, and what is not legal to hire out today."""
    return FleetOverview(**await rental_service.fleet_overview(db, context))


@assets_router.get("", response_model=list[AssetDetail])
async def list_assets(
    kind: AssetKind | None = None,
    asset_status: AssetStatus | None = None,
    search: str | None = None,
    available_from: date | None = None,
    available_to: date | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[AssetDetail]:
    window = (available_from, available_to) if available_from and available_to else None
    rows = await rental_service.list_assets(
        db,
        context,
        kind=kind,
        asset_status=asset_status,
        search=search,
        available_between=window,
        limit=limit,
    )
    return [await _asset_detail(db, asset) for asset in rows]


@assets_router.post("", response_model=AssetDetail, status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: AssetCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AssetDetail:
    asset = await rental_service.create_asset(db, context, payload, request)
    return await _asset_detail(db, asset)


@assets_router.get("/{asset_id}", response_model=AssetDetail)
async def get_asset(
    asset_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> AssetDetail:
    from app.api.deps import assert_in_org

    asset = assert_in_org(await db.get(RentalAsset, asset_id), context, label="asset")
    return await _asset_detail(db, asset)


@assets_router.patch("/{asset_id}", response_model=AssetDetail)
async def update_asset(
    asset_id: uuid.UUID,
    payload: AssetUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AssetDetail:
    asset = await rental_service.update_asset(db, context, asset_id, payload, request)
    return await _asset_detail(db, asset)


@assets_router.get("/{asset_id}/availability", response_model=list[AvailabilityRow])
async def availability(
    asset_id: uuid.UUID,
    day_from: date | None = None,
    day_to: date | None = None,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[AvailabilityRow]:
    """The booked windows, so the counter can see the gaps."""
    start = day_from or date.today()
    rows = await rental_service.availability(
        db, context, asset_id, day_from=start, day_to=day_to or start + timedelta(days=90)
    )
    return [AvailabilityRow(**row) for row in rows]


# ------------------------------------------------------------------ agreements


@agreements_router.get("", response_model=list[AgreementDetail])
async def list_agreements(
    asset_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    agreement_status: AgreementStatus | None = None,
    overdue_only: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[AgreementDetail]:
    rows = await rental_service.list_agreements(
        db,
        context,
        asset_id=asset_id,
        tenant_id=tenant_id,
        agreement_status=agreement_status,
        overdue_only=overdue_only,
        limit=limit,
    )
    return [await _agreement_detail(db, agreement) for agreement in rows]


@agreements_router.post("", response_model=AgreementDetail, status_code=status.HTTP_201_CREATED)
async def book(
    payload: AgreementCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AgreementDetail:
    agreement = await rental_service.book(db, context, payload, request)
    return await _agreement_detail(db, agreement)


@agreements_router.get("/{agreement_id}", response_model=AgreementDetail)
async def get_agreement(
    agreement_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> AgreementDetail:
    from app.api.deps import assert_in_org

    agreement = assert_in_org(await db.get(RentalAgreement, agreement_id), context, label="agreement")
    return await _agreement_detail(db, agreement)


@agreements_router.post("/{agreement_id}/check-out", response_model=AgreementDetail)
async def check_out(
    agreement_id: uuid.UUID,
    payload: CheckOut,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AgreementDetail:
    """Hand it over, recording its condition as it leaves."""
    agreement = await rental_service.check_out(db, context, agreement_id, payload, request)
    return await _agreement_detail(db, agreement)


@agreements_router.post("/{agreement_id}/check-in", response_model=AgreementDetail)
async def check_in(
    agreement_id: uuid.UUID,
    payload: CheckIn,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AgreementDetail:
    """Take it back and price the difference between the two snapshots."""
    agreement = await rental_service.check_in(db, context, agreement_id, payload, request)
    return await _agreement_detail(db, agreement)


@agreements_router.post("/{agreement_id}/cancel", response_model=AgreementDetail)
async def cancel(
    agreement_id: uuid.UUID,
    payload: AgreementCancel,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AgreementDetail:
    agreement = await rental_service.cancel(db, context, agreement_id, payload.reason, request)
    return await _agreement_detail(db, agreement)
