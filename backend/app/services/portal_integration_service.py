"""Property portal integrations — Sprint 23 (US-099).

An organisation connects its own BuyRentKenya or PigiaMe account — an API key
and account id, stored encrypted like every other partner credential in this
codebase (see `app.core.crypto`, `app.services.etims_service`) — and from then
on a vacancy listing's own lifecycle drives what the portal sees: publishing a
listing publishes it there, closing a listing deactivates it there. Nothing
about the existing opt-in `VacancyListing` model changes; a landlord who never
lists a unit never sends it anywhere.

Neither portal publishes a self-serve developer API today, so the adapter
below posts to the base URL each one is expected to give a partner
(`settings.BUYRENTKENYA_API_BASE_URL` / `PIGIAME_API_BASE_URL`) using the
smallest REST contract a listings API is ever likely to expose: create/update
a listing, and delete one. When a real partnership exists, only the payload
shape here needs to change — the credential storage, retry accounting and
lead capture around it stay the same, the same way `etims_service` was ready
to work the moment real KRA sandbox credentials existed.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.core.config import settings
from app.core.crypto import decrypt_for_org, encrypt_for_org
from app.models.integrations import PortalConnection, PortalListingSync, PortalName, PortalSyncStatus
from app.models.property import Property, Unit
from app.models.vacancy import Inquiry, ListingStatus, VacancyListing

logger = logging.getLogger("rentflow.portals")


class PortalError(RuntimeError):
    pass


def _base_url(portal: PortalName) -> str:
    return (
        settings.BUYRENTKENYA_API_BASE_URL
        if portal == PortalName.BUYRENTKENYA
        else settings.PIGIAME_API_BASE_URL
    )


def describe_connection(record: PortalConnection | None) -> dict:
    if record is None:
        return {"configured": False}
    return {
        "configured": True,
        "portal": record.portal.value,
        "account_id": record.account_id,
        "is_active": record.is_active,
        "last_synced_at": record.last_synced_at.isoformat() if record.last_synced_at else None,
        "last_error": record.last_error,
    }


# ------------------------------------------------------------------ connections


async def get_connection(
    db: AsyncSession, organization_id: uuid.UUID, portal: PortalName
) -> PortalConnection | None:
    return await db.scalar(
        select(PortalConnection).where(
            PortalConnection.organization_id == organization_id, PortalConnection.portal == portal
        )
    )


async def list_connections(db: AsyncSession, context: OrgContext) -> list[PortalConnection]:
    return list(
        await db.scalars(
            select(PortalConnection).where(PortalConnection.organization_id == context.organization_id)
        )
    )


async def save_connection(
    db: AsyncSession,
    context: OrgContext,
    portal: PortalName,
    *,
    api_key: str,
    account_id: str | None,
) -> PortalConnection:
    connection = await get_connection(db, context.organization_id, portal)
    sealed = await encrypt_for_org(db, context.organization_id, api_key)
    if connection is None:
        connection = PortalConnection(
            organization_id=context.organization_id, portal=portal, api_key_encrypted=sealed
        )
        db.add(connection)

    connection.api_key_encrypted = sealed
    connection.account_id = account_id
    connection.is_active = True
    connection.last_error = None
    await db.commit()
    await db.refresh(connection)
    return connection


async def delete_connection(db: AsyncSession, context: OrgContext, portal: PortalName) -> bool:
    connection = await get_connection(db, context.organization_id, portal)
    if connection is None:
        return False
    await db.delete(connection)
    await db.commit()
    return True


# ------------------------------------------------------------------- publishing


async def _listing_payload(db: AsyncSession, listing: VacancyListing) -> dict[str, Any]:
    unit = await db.get(Unit, listing.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    return {
        "external_ref": str(listing.id),
        "title": listing.headline or (f"Unit {unit.unit_number}" if unit else "Vacant unit"),
        "description": listing.description or (property_record.description if property_record else ""),
        "rent": float(unit.monthly_rent) if unit else None,
        "bedrooms": unit.bedrooms if unit else None,
        "county": property_record.county if property_record else None,
        "contact_phone": listing.contact_phone,
        "listing_url": f"{settings.FRONTEND_URL}/listings/{listing.slug}",
    }


async def _call_portal(
    db: AsyncSession,
    connection: PortalConnection,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key = await decrypt_for_org(db, connection.organization_id, connection.api_key_encrypted)
    if not api_key:
        raise PortalError("Stored portal credentials could not be read — re-enter them in settings")

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.request(
            method,
            f"{_base_url(connection.portal)}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
    if response.status_code >= 400:
        raise PortalError(f"{connection.portal.value} rejected the request ({response.status_code})")
    return response.json() if response.content else {}


async def _sync_row(
    db: AsyncSession, listing: VacancyListing, connection: PortalConnection
) -> PortalListingSync:
    row = await db.scalar(
        select(PortalListingSync).where(
            PortalListingSync.listing_id == listing.id, PortalListingSync.connection_id == connection.id
        )
    )
    if row is None:
        row = PortalListingSync(
            organization_id=listing.organization_id, listing_id=listing.id, connection_id=connection.id
        )
        db.add(row)
        await db.flush()
    return row


async def publish_listing(db: AsyncSession, listing: VacancyListing) -> None:
    """Push a published listing to every connected, active portal (US-099).

    Called from `vacancy_service` whenever a listing's status becomes
    published. Never raises — a portal outage must never block the
    landlord's own listing page from working; the failure just sits on the
    sync row for the settings page to show.
    """
    connections = list(
        await db.scalars(
            select(PortalConnection).where(
                PortalConnection.organization_id == listing.organization_id,
                PortalConnection.is_active.is_(True),
            )
        )
    )
    for connection in connections:
        row = await _sync_row(db, listing, connection)
        row.attempts += 1
        row.last_attempt_at = datetime.now(UTC)
        try:
            payload = await _listing_payload(db, listing)
            result = await _call_portal(db, connection, "POST", "/listings", payload)
            row.external_listing_id = str(
                result.get("id") or result.get("listing_id") or row.external_listing_id or ""
            )
            row.status = PortalSyncStatus.PUBLISHED
            row.last_error = None
            connection.last_synced_at = datetime.now(UTC)
            connection.last_error = None
        except Exception as exc:  # noqa: BLE001 — every failure mode is recorded, not raised
            message = str(exc)[:500]
            logger.warning(
                "Portal publish failed for listing %s on %s: %s", listing.id, connection.portal.value, message
            )
            row.status = PortalSyncStatus.FAILED
            row.last_error = message
            connection.last_error = message
    await db.flush()


async def deactivate_listing(db: AsyncSession, listing: VacancyListing) -> None:
    """Tell every portal that published this listing it is no longer available
    (US-099). Called when the unit becomes occupied."""
    rows = list(await db.scalars(select(PortalListingSync).where(PortalListingSync.listing_id == listing.id)))
    for row in rows:
        if row.status != PortalSyncStatus.PUBLISHED:
            continue
        connection = await db.get(PortalConnection, row.connection_id)
        if connection is None or not connection.is_active:
            continue
        row.attempts += 1
        row.last_attempt_at = datetime.now(UTC)
        try:
            await _call_portal(db, connection, "DELETE", f"/listings/{row.external_listing_id or listing.id}")
            row.status = PortalSyncStatus.DEACTIVATED
            row.last_error = None
        except Exception as exc:  # noqa: BLE001
            message = str(exc)[:500]
            logger.warning(
                "Portal deactivate failed for listing %s on %s: %s",
                listing.id,
                connection.portal.value,
                message,
            )
            row.last_error = message
    await db.flush()


async def sync_status_for_listing(
    db: AsyncSession, context: OrgContext, listing_id: uuid.UUID
) -> list[PortalListingSync]:
    return list(
        await db.scalars(
            select(PortalListingSync).where(
                PortalListingSync.listing_id == listing_id,
                PortalListingSync.organization_id == context.organization_id,
            )
        )
    )


# --------------------------------------------------------------- inbound leads


async def capture_portal_inquiry(
    db: AsyncSession,
    connection_id: uuid.UUID,
    external_listing_id: str,
    *,
    full_name: str,
    phone_number: str,
    email: str | None,
    message: str | None,
) -> Inquiry | None:
    """A portal is telling us someone enquired about a listing it is carrying
    (US-099). Returns None for anything that cannot be matched to a live
    listing — a stale or unrecognised `external_listing_id` is silently
    dropped rather than raised, since the caller is a partner's server, not a
    person who can act on an error.
    """
    from app.services import vacancy_service

    row = await db.scalar(
        select(PortalListingSync).where(
            PortalListingSync.connection_id == connection_id,
            PortalListingSync.external_listing_id == external_listing_id,
        )
    )
    if row is None:
        return None
    listing = await db.get(VacancyListing, row.listing_id)
    if listing is None or listing.status != ListingStatus.PUBLISHED:
        return None

    connection = await db.get(PortalConnection, connection_id)
    source = connection.portal.value if connection else "portal"
    return await vacancy_service.capture_inquiry_for_listing(
        db,
        listing,
        full_name=full_name,
        phone_number=phone_number,
        email=email,
        message=message,
        source=source,
    )
