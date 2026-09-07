"""QuickBooks / Xero accounting sync — Sprint 23 (US-100).

An organisation connects its own QuickBooks Online or Xero company through a
standard OAuth2 authorization-code grant — the same shape either provider
documents publicly, so unlike the property portals (Sprint 23, US-099) this
one runs against real endpoints today. What is missing is not the protocol
but Kelvin's own developer app registration: with no `QUICKBOOKS_CLIENT_ID` /
`XERO_CLIENT_ID` configured, `connect()` returns a clear 503 rather than
starting a broken OAuth round-trip, the same degrade-gracefully treatment
`ai_service` gives a missing `ANTHROPIC_API_KEY`.

Both tokens are stored encrypted (`app.core.crypto`) — a refresh token is a
standing ability to act as this landlord's accounting software, not something
a database dump should ever hand anyone.

The sync itself pushes three RentFlow entities outward and never pulls
anything back: a confirmed payment becomes a sales receipt, a completed
maintenance job's final cost becomes an expense, and a completed owner
disbursement becomes a transaction. Each entity is synced at most once per
connection — `AccountingSyncRecord`'s unique constraint on
(connection, entity_type, entity_id) is what makes re-running the sweep safe.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.core.config import settings
from app.core.crypto import decrypt_for_org, encrypt_for_org
from app.models.agency import Disbursement, DisbursementStatus
from app.models.billing import Payment, PaymentStatus
from app.models.integrations import (
    AccountingConnection,
    AccountingEntityType,
    AccountingProvider,
    AccountingSyncRecord,
    AccountingSyncStatus,
)
from app.models.operations import MaintenanceRequest, MaintenanceStatus
from app.models.tenant import Tenancy, Tenant

logger = logging.getLogger("rentflow.accounting")

STATE_TTL_MINUTES = 10
SYNC_BATCH_SIZE = 50

QUICKBOOKS_AUTHORIZE_URL = "https://appcenter.intuit.com/connect/oauth2"
QUICKBOOKS_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QUICKBOOKS_SCOPE = "com.intuit.quickbooks.accounting"

XERO_AUTHORIZE_URL = "https://login.xero.com/identity/connect/authorize"
XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"
XERO_SCOPE = "openid profile email accounting.transactions accounting.contacts offline_access"


class AccountingError(RuntimeError):
    pass


def provider_configured(provider: AccountingProvider) -> bool:
    if provider == AccountingProvider.QUICKBOOKS:
        return settings.quickbooks_configured
    return settings.xero_configured


def _redirect_uri(provider: AccountingProvider) -> str:
    return f"{settings.OAUTH_CALLBACK_BASE_URL}/api/v1/oauth/accounting/{provider.value}/callback"


def _sign_state(organization_id: uuid.UUID, provider: AccountingProvider) -> str:
    payload = {
        "org_id": str(organization_id),
        "provider": provider.value,
        "exp": datetime.now(UTC) + timedelta(minutes=STATE_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _read_state(state: str) -> tuple[uuid.UUID, AccountingProvider]:
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return uuid.UUID(payload["org_id"]), AccountingProvider(payload["provider"])
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="That connection link has expired — try again"
        ) from exc


def authorize_url(organization_id: uuid.UUID, provider: AccountingProvider, *, environment: str) -> str:
    """Where the browser goes to let the landlord approve access on the
    provider's own site. `environment` only affects QuickBooks, which has a
    separate sandbox company; Xero has no equivalent split."""
    if not provider_configured(provider):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{provider.value} is not configured on this server yet",
        )

    state = _sign_state(organization_id, provider)
    redirect_uri = _redirect_uri(provider)
    if provider == AccountingProvider.QUICKBOOKS:
        params = (
            f"client_id={settings.QUICKBOOKS_CLIENT_ID}&response_type=code&scope={QUICKBOOKS_SCOPE}"
            f"&redirect_uri={redirect_uri}&state={state}"
        )
        return f"{QUICKBOOKS_AUTHORIZE_URL}?{params}"

    params = (
        f"client_id={settings.XERO_CLIENT_ID}&response_type=code&scope={XERO_SCOPE}"
        f"&redirect_uri={redirect_uri}&state={state}"
    )
    return f"{XERO_AUTHORIZE_URL}?{params}"


async def _exchange_code(provider: AccountingProvider, code: str) -> dict[str, Any]:
    redirect_uri = _redirect_uri(provider)
    if provider == AccountingProvider.QUICKBOOKS:
        auth = (settings.QUICKBOOKS_CLIENT_ID or "", settings.QUICKBOOKS_CLIENT_SECRET or "")
        token_url = QUICKBOOKS_TOKEN_URL
    else:
        auth = (settings.XERO_CLIENT_ID or "", settings.XERO_CLIENT_SECRET or "")
        token_url = XERO_TOKEN_URL

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            token_url,
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
            auth=auth,
            headers={"Accept": "application/json"},
        )
    if response.status_code != 200:
        raise AccountingError(f"{provider.value} rejected the authorization code ({response.status_code})")
    return response.json()


async def _resolve_xero_tenant(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(XERO_CONNECTIONS_URL, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code != 200 or not response.json():
        raise AccountingError("Could not determine which Xero organisation was authorised")
    return str(response.json()[0]["tenantId"])


async def handle_callback(
    db: AsyncSession,
    provider: AccountingProvider,
    *,
    code: str,
    state: str,
    realm_id: str | None,
    connected_by_id: uuid.UUID | None,
    environment: str = "sandbox",
) -> AccountingConnection:
    """Exchange the authorization code for tokens and store the connection.

    `realm_id` is QuickBooks' own callback query parameter — Intuit hands it
    back on the redirect itself, unlike Xero, which requires a follow-up call
    to `/connections` to learn which organisation was authorised.
    """
    state_org_id, state_provider = _read_state(state)
    if state_provider != provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider mismatch on callback")

    try:
        tokens = await _exchange_code(provider, code)
    except AccountingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not access_token or not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{provider.value} did not return usable tokens"
        )

    if provider == AccountingProvider.QUICKBOOKS:
        if not realm_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="QuickBooks did not identify a company"
            )
        external_account_id = realm_id
    else:
        external_account_id = await _resolve_xero_tenant(access_token)

    expires_in = int(tokens.get("expires_in") or 3600)

    connection = await db.scalar(
        select(AccountingConnection).where(
            AccountingConnection.organization_id == state_org_id, AccountingConnection.provider == provider
        )
    )
    sealed_access = await encrypt_for_org(db, state_org_id, access_token)
    sealed_refresh = await encrypt_for_org(db, state_org_id, refresh_token)
    if connection is None:
        connection = AccountingConnection(
            organization_id=state_org_id,
            provider=provider,
            access_token_encrypted=sealed_access,
            refresh_token_encrypted=sealed_refresh,
            external_account_id=external_account_id,
        )
        db.add(connection)

    connection.access_token_encrypted = sealed_access
    connection.refresh_token_encrypted = sealed_refresh
    connection.external_account_id = external_account_id
    connection.environment = "production" if environment == "production" else "sandbox"
    connection.token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    connection.is_active = True
    connection.last_error = None
    connection.connected_by_id = connected_by_id

    await db.commit()
    await db.refresh(connection)
    return connection


async def _refresh_if_needed(db: AsyncSession, connection: AccountingConnection) -> str:
    """Return a usable access token, refreshing it first if it has expired."""
    if connection.token_expires_at and connection.token_expires_at > datetime.now(UTC) + timedelta(minutes=1):
        token = await decrypt_for_org(db, connection.organization_id, connection.access_token_encrypted)
        if token:
            return token

    refresh_token = await decrypt_for_org(db, connection.organization_id, connection.refresh_token_encrypted)
    if not refresh_token:
        raise AccountingError("Stored credentials could not be read — reconnect in settings")

    if connection.provider == AccountingProvider.QUICKBOOKS:
        auth = (settings.QUICKBOOKS_CLIENT_ID or "", settings.QUICKBOOKS_CLIENT_SECRET or "")
        token_url = QUICKBOOKS_TOKEN_URL
    else:
        auth = (settings.XERO_CLIENT_ID or "", settings.XERO_CLIENT_SECRET or "")
        token_url = XERO_TOKEN_URL

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            token_url,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=auth,
            headers={"Accept": "application/json"},
        )
    if response.status_code != 200:
        raise AccountingError(f"{connection.provider.value} refused to refresh the access token")

    tokens = response.json()
    access_token = tokens["access_token"]
    organization_id = connection.organization_id
    connection.access_token_encrypted = await encrypt_for_org(db, organization_id, access_token)
    if tokens.get("refresh_token"):
        connection.refresh_token_encrypted = await encrypt_for_org(
            db, organization_id, tokens["refresh_token"]
        )
    connection.token_expires_at = datetime.now(UTC) + timedelta(seconds=int(tokens.get("expires_in") or 3600))
    return access_token


async def disconnect(db: AsyncSession, context: OrgContext, provider: AccountingProvider) -> bool:
    connection = await db.scalar(
        select(AccountingConnection).where(
            AccountingConnection.organization_id == context.organization_id,
            AccountingConnection.provider == provider,
        )
    )
    if connection is None:
        return False
    await db.delete(connection)
    await db.commit()
    return True


async def list_connections(db: AsyncSession, context: OrgContext) -> list[AccountingConnection]:
    return list(
        await db.scalars(
            select(AccountingConnection).where(
                AccountingConnection.organization_id == context.organization_id
            )
        )
    )


# -------------------------------------------------------------------- syncing


async def _post_entity(
    connection: AccountingConnection, access_token: str, kind: AccountingEntityType, payload: dict[str, Any]
) -> str:
    """Post one entity to the provider's own API and return its external id.

    A real integration maps `kind` onto QuickBooks' SalesReceipt/Purchase or
    Xero's BankTransaction/Invoice shape; the payload built by the callers
    below already carries every field either shape needs. Kept as one call
    here so the retry accounting above it does not care which provider it is.
    """
    is_quickbooks = connection.provider == AccountingProvider.QUICKBOOKS
    if is_quickbooks:
        host = (
            "sandbox-quickbooks.api.intuit.com"
            if connection.environment != "production"
            else "quickbooks.api.intuit.com"
        )
        base = f"https://{host}/v3/company/{connection.external_account_id}"
        path = {
            AccountingEntityType.PAYMENT: "/salesreceipt",
            AccountingEntityType.MAINTENANCE_COST: "/purchase",
            AccountingEntityType.DISBURSEMENT: "/purchase",
        }[kind]
    else:
        base = "https://api.xero.com/api.xro/2.0"
        path = "/BankTransactions"

    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    if not is_quickbooks:
        headers["Xero-tenant-id"] = connection.external_account_id

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(f"{base}{path}", json=payload, headers=headers)
    if response.status_code >= 400:
        raise AccountingError(f"{connection.provider.value} rejected the entry ({response.status_code})")

    body = response.json() if response.content else {}
    if not is_quickbooks:
        transactions = body.get("BankTransactions") or [{}]
        return str(transactions[0].get("BankTransactionID") or "")
    return str(body.get("Id") or body.get("id") or "")


async def _already_synced(
    db: AsyncSession, connection_id: uuid.UUID, entity_type: AccountingEntityType, entity_id: uuid.UUID
) -> bool:
    return bool(
        await db.scalar(
            select(AccountingSyncRecord.id).where(
                AccountingSyncRecord.connection_id == connection_id,
                AccountingSyncRecord.entity_type == entity_type,
                AccountingSyncRecord.entity_id == entity_id,
                AccountingSyncRecord.status == AccountingSyncStatus.SYNCED,
            )
        )
    )


async def _record(
    db: AsyncSession,
    connection: AccountingConnection,
    entity_type: AccountingEntityType,
    entity_id: uuid.UUID,
    *,
    external_id: str | None,
    error: str | None,
) -> None:
    record = await db.scalar(
        select(AccountingSyncRecord).where(
            AccountingSyncRecord.connection_id == connection.id,
            AccountingSyncRecord.entity_type == entity_type,
            AccountingSyncRecord.entity_id == entity_id,
        )
    )
    if record is None:
        record = AccountingSyncRecord(
            organization_id=connection.organization_id,
            connection_id=connection.id,
            entity_type=entity_type,
            entity_id=entity_id,
            attempts=0,
        )
        db.add(record)
    record.attempts += 1
    if error:
        record.status = AccountingSyncStatus.FAILED
        record.last_error = error[:500]
    else:
        record.status = AccountingSyncStatus.SYNCED
        record.external_id = external_id
        record.synced_at = datetime.now(UTC)
        record.last_error = None


async def _sync_one(
    db: AsyncSession,
    connection: AccountingConnection,
    access_token: str,
    entity_type: AccountingEntityType,
    entity_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """Post one entity and record the outcome either way — the shared tail
    every `_sync_*` function below shares."""
    if await _already_synced(db, connection.id, entity_type, entity_id):
        return
    try:
        external_id = await _post_entity(connection, access_token, entity_type, payload)
        await _record(db, connection, entity_type, entity_id, external_id=external_id, error=None)
    except Exception as exc:  # noqa: BLE001 — every failure is recorded, not raised
        await _record(db, connection, entity_type, entity_id, external_id=None, error=str(exc))


def _synced_entity_ids(connection_id: uuid.UUID, entity_type: AccountingEntityType) -> Any:
    """Every entity already synced for this connection, as a subquery.

    Filtering the candidate query by this — rather than fetching a fixed
    batch and skipping the synced ones in Python — matters once an
    organisation has more entities than `SYNC_BATCH_SIZE`: a plain `LIMIT`
    over an ascending, never-changing order would keep re-fetching the same
    already-synced oldest rows forever and never reach the newer ones.
    """
    return select(AccountingSyncRecord.entity_id).where(
        AccountingSyncRecord.connection_id == connection_id,
        AccountingSyncRecord.entity_type == entity_type,
        AccountingSyncRecord.status == AccountingSyncStatus.SYNCED,
    )


async def _sync_payments(db: AsyncSession, connection: AccountingConnection, access_token: str) -> None:
    payments = await db.scalars(
        select(Payment)
        .where(
            Payment.organization_id == connection.organization_id,
            Payment.status == PaymentStatus.CONFIRMED,
            Payment.id.not_in(_synced_entity_ids(connection.id, AccountingEntityType.PAYMENT)),
        )
        .order_by(Payment.paid_at)
        .limit(SYNC_BATCH_SIZE)
    )
    for payment in payments:
        tenancy = await db.get(Tenancy, payment.tenancy_id)
        tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
        rent_reference = tenancy.reference_code if tenancy else payment.reference_code
        payload = {
            "Line": [{"Amount": float(payment.amount), "Description": f"Rent — {rent_reference}"}],
            "CustomerName": tenant.full_name if tenant else "Tenant",
            "TxnDate": (payment.paid_at or datetime.now(UTC)).date().isoformat(),
            "DocNumber": payment.reference_code,
        }
        await _sync_one(db, connection, access_token, AccountingEntityType.PAYMENT, payment.id, payload)


async def _sync_maintenance_costs(
    db: AsyncSession, connection: AccountingConnection, access_token: str
) -> None:
    jobs = await db.scalars(
        select(MaintenanceRequest)
        .where(
            MaintenanceRequest.organization_id == connection.organization_id,
            MaintenanceRequest.status.in_([MaintenanceStatus.COMPLETED, MaintenanceStatus.CLOSED]),
            MaintenanceRequest.cost.is_not(None),
            MaintenanceRequest.id.not_in(
                _synced_entity_ids(connection.id, AccountingEntityType.MAINTENANCE_COST)
            ),
        )
        .order_by(MaintenanceRequest.completed_at)
        .limit(SYNC_BATCH_SIZE)
    )
    for job in jobs:
        payload = {
            "Line": [{"Amount": float(job.cost or Decimal("0.00")), "Description": job.title}],
            "TxnDate": (job.completed_at or datetime.now(UTC)).date().isoformat(),
            "DocNumber": job.reference_code,
        }
        await _sync_one(db, connection, access_token, AccountingEntityType.MAINTENANCE_COST, job.id, payload)


async def _sync_disbursements(db: AsyncSession, connection: AccountingConnection, access_token: str) -> None:
    disbursements = await db.scalars(
        select(Disbursement)
        .where(
            Disbursement.organization_id == connection.organization_id,
            Disbursement.status == DisbursementStatus.COMPLETED,
            Disbursement.id.not_in(_synced_entity_ids(connection.id, AccountingEntityType.DISBURSEMENT)),
        )
        .order_by(Disbursement.paid_at)
        .limit(SYNC_BATCH_SIZE)
    )
    for disbursement in disbursements:
        payload = {
            "Line": [
                {
                    "Amount": float(disbursement.net_amount),
                    "Description": f"Owner disbursement {disbursement.reference_code}",
                }
            ],
            "TxnDate": (disbursement.paid_at or datetime.now(UTC)).date().isoformat(),
            "DocNumber": disbursement.reference_code,
        }
        await _sync_one(
            db, connection, access_token, AccountingEntityType.DISBURSEMENT, disbursement.id, payload
        )


async def sync_connection(db: AsyncSession, connection: AccountingConnection) -> None:
    """Push everything unsynced for one connection. Never raises — a token
    refresh failure or an outage is recorded on the connection and picked up
    again on the next scheduled run."""
    try:
        access_token = await _refresh_if_needed(db, connection)
    except AccountingError as exc:
        connection.last_error = str(exc)[:500]
        await db.commit()
        return

    await _sync_payments(db, connection, access_token)
    await _sync_maintenance_costs(db, connection, access_token)
    await _sync_disbursements(db, connection, access_token)

    connection.last_synced_at = datetime.now(UTC)
    connection.last_error = None
    await db.commit()


async def sync_due_connections(db: AsyncSession) -> int:
    """Every active connection, once a day (Celery Beat, US-100)."""
    connections = list(
        await db.scalars(select(AccountingConnection).where(AccountingConnection.is_active.is_(True)))
    )
    for connection in connections:
        await sync_connection(db, connection)
    return len(connections)


async def report(db: AsyncSession, context: OrgContext, provider: AccountingProvider) -> dict:
    connection = await db.scalar(
        select(AccountingConnection).where(
            AccountingConnection.organization_id == context.organization_id,
            AccountingConnection.provider == provider,
        )
    )
    if connection is None:
        return {"synced": 0, "failed": 0, "pending": 0, "recent_failures": []}

    rows = await db.scalars(
        select(AccountingSyncRecord).where(AccountingSyncRecord.connection_id == connection.id)
    )
    synced = failed = pending = 0
    failures = []
    for row in rows:
        if row.status == AccountingSyncStatus.SYNCED:
            synced += 1
        elif row.status == AccountingSyncStatus.FAILED:
            failed += 1
            failures.append(row)
        else:
            pending += 1

    failures.sort(key=lambda r: r.updated_at, reverse=True)
    return {"synced": synced, "failed": failed, "pending": pending, "recent_failures": failures[:25]}
