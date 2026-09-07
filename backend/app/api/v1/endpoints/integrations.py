"""Property portal and accounting software integrations — Sprint 23 (US-099, US-100).

`router` holds everything an operator manages from Settings. The two routes
partners themselves call carry no RentFlow session, so — like every other
public surface in this API (`/mpesa`, `/sign`, `/listings`) — each gets its
own distinct top-level prefix rather than sharing `/integrations`, so the
public/authenticated boundary stays a path prefix, not a per-route judgement
call: `portal_webhook_router` (a connected portal reporting an inbound
enquiry) and `oauth_callback_router` (Intuit/Xero redirecting the landlord's
browser back after they approve access).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.integrations import AccountingProvider, PortalName
from app.schemas.integrations import (
    AccountingAuthorizeUrl,
    AccountingConnectionRead,
    AccountingSyncReport,
    PortalConnectionUpsert,
    PortalListingSyncRead,
)
from app.services import accounting_service, portal_integration_service

router = APIRouter()
portal_webhook_router = APIRouter()
oauth_callback_router = APIRouter()


# --------------------------------------------------------------- property portals


@router.get("/portals", response_model=list[dict])
async def list_portal_connections(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    connections = await portal_integration_service.list_connections(db, context)
    return [portal_integration_service.describe_connection(c) for c in connections]


@router.put("/portals/{portal}", response_model=dict)
async def save_portal_connection(
    portal: PortalName,
    body: PortalConnectionUpsert,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    connection = await portal_integration_service.save_connection(
        db, context, portal, api_key=body.api_key, account_id=body.account_id
    )
    return portal_integration_service.describe_connection(connection)


@router.delete("/portals/{portal}")
async def delete_portal_connection(
    portal: PortalName,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    removed = await portal_integration_service.delete_connection(db, context, portal)
    return {"removed": removed}


@router.get("/portals/listings/{listing_id}", response_model=list[PortalListingSyncRead])
async def portal_sync_status(
    listing_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    from app.models.integrations import PortalConnection

    rows = await portal_integration_service.sync_status_for_listing(db, context, listing_id)
    connections = {c.id: c for c in await portal_integration_service.list_connections(db, context)}
    result = []
    for row in rows:
        connection = connections.get(row.connection_id) or await db.get(PortalConnection, row.connection_id)
        if connection is None:
            continue
        result.append(
            PortalListingSyncRead(
                id=row.id,
                listing_id=row.listing_id,
                portal=connection.portal,
                external_listing_id=row.external_listing_id,
                status=row.status,
                attempts=row.attempts,
                last_attempt_at=row.last_attempt_at,
                last_error=row.last_error,
            )
        )
    return result


class PortalInquiryPayload(BaseModel):
    external_listing_id: str = Field(max_length=128)
    full_name: str = Field(max_length=255)
    phone_number: str = Field(max_length=32)
    email: str | None = None
    message: str | None = None


@portal_webhook_router.post("/{connection_id}/inquiries", status_code=status.HTTP_202_ACCEPTED)
async def receive_portal_inquiry(
    connection_id: uuid.UUID,
    body: PortalInquiryPayload,
    db: AsyncSession = Depends(get_db),
):
    """A connected portal telling us someone enquired about one of its
    listings. `connection_id` is an unguessable id, the same capability-URL
    approach `/listings/{slug}` already uses for the public listing page."""
    inquiry = await portal_integration_service.capture_portal_inquiry(
        db,
        connection_id,
        body.external_listing_id,
        full_name=body.full_name,
        phone_number=body.phone_number,
        email=body.email,
        message=body.message,
    )
    return {"accepted": inquiry is not None}


# ------------------------------------------------------------ accounting software


@router.get("/accounting", response_model=list[AccountingConnectionRead])
async def list_accounting_connections(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    return await accounting_service.list_connections(db, context)


@router.get("/accounting/{provider}/connect", response_model=AccountingAuthorizeUrl)
async def connect_accounting(
    provider: AccountingProvider,
    environment: str = Query(default="sandbox", pattern="^(sandbox|production)$"),
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
):
    url = accounting_service.authorize_url(context.organization_id, provider, environment=environment)
    return AccountingAuthorizeUrl(authorize_url=url)


@oauth_callback_router.get("/accounting/{provider}/callback")
async def accounting_callback(
    provider: AccountingProvider,
    code: str,
    state: str,
    realmId: str | None = None,  # noqa: N803 — QuickBooks' own query parameter name
    db: AsyncSession = Depends(get_db),
):
    """Intuit/Xero redirect the landlord's browser here after they approve
    access on the provider's own site — this request carries no RentFlow
    session, only what `state` proves (see `accounting_service._sign_state`)."""
    try:
        await accounting_service.handle_callback(
            db, provider, code=code, state=state, realm_id=realmId, connected_by_id=None
        )
        return RedirectResponse(f"{settings.FRONTEND_URL}/settings/accounting?connected={provider.value}")
    except HTTPException as exc:
        return RedirectResponse(f"{settings.FRONTEND_URL}/settings/accounting?error={exc.detail}")


@router.delete("/accounting/{provider}")
async def disconnect_accounting(
    provider: AccountingProvider,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    removed = await accounting_service.disconnect(db, context, provider)
    return {"removed": removed}


@router.get("/accounting/{provider}/report", response_model=AccountingSyncReport)
async def accounting_sync_report(
    provider: AccountingProvider,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await accounting_service.report(db, context, provider)


@router.post("/accounting/{provider}/sync")
async def sync_accounting_now(
    provider: AccountingProvider,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from app.models.integrations import AccountingConnection

    connection = await db.scalar(
        select(AccountingConnection).where(
            AccountingConnection.organization_id == context.organization_id,
            AccountingConnection.provider == provider,
        )
    )
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not connected")
    await accounting_service.sync_connection(db, connection)
    return await accounting_service.report(db, context, provider)
