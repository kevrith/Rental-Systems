"""Safaricom Daraja (M-Pesa) integration (US-019).

STK Push asks the tenant's phone for a PIN; the result arrives asynchronously on
the callback URL. Because callbacks can be duplicated, delayed or spoofed, the
confirmation path here is deliberately defensive:

  * the OAuth token is cached in Redis just short of its real lifetime;
  * every callback is matched to a payment by `CheckoutRequestID`;
  * a Redis lock makes concurrent deliveries of the same callback a no-op;
  * the M-Pesa receipt number is unique in the database, so the same money can
    never be banked twice even if every other guard is bypassed.

With no Daraja credentials configured the sandbox stub returns a deterministic
fake checkout id so the whole flow is exercisable offline.
"""

import base64
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import httpx

from app.core import crypto
from app.core.config import settings
from app.core.crypto import mask
from app.core.redis import redis_client
from app.models.organization import MpesaCollectionMode
from app.services.notifications import normalize_phone

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.organization import Organization

logger = logging.getLogger("rentflow.mpesa")

_TOKEN_KEY = "mpesa:access_token"
_CALLBACK_LOCK_TTL = 300


class MpesaError(RuntimeError):
    pass


@dataclass(slots=True)
class StkPushResult:
    checkout_request_id: str
    merchant_request_id: str
    customer_message: str


@dataclass(slots=True)
class CallbackResult:
    checkout_request_id: str
    merchant_request_id: str | None
    success: bool
    result_code: int
    result_description: str
    mpesa_receipt: str | None = None
    amount: Decimal | None = None
    phone_number: str | None = None
    transaction_date: datetime | None = None


@dataclass(slots=True)
class DarajaCredentials:
    """One organisation's own Daraja app.

    Every call here is made *as the landlord*, against the landlord's shortcode,
    so their tenants' rent lands in their till and never in RentFlow's. The
    organisation id rides along so cached tokens cannot be shared between two
    customers' Safaricom apps.
    """

    organization_id: uuid.UUID
    consumer_key: str
    consumer_secret: str
    shortcode: str
    passkey: str
    environment: str = "sandbox"
    initiator_name: str | None = None
    security_credential: str | None = None

    @property
    def base_url(self) -> str:
        return (
            "https://api.safaricom.co.ke"
            if self.environment == "production"
            else "https://sandbox.safaricom.co.ke"
        )

    @property
    def can_pay_out(self) -> bool:
        return bool(self.initiator_name and self.security_credential)


async def credentials_for(db: "AsyncSession", organization: "Organization") -> DarajaCredentials | None:
    """This organisation's Daraja credentials, decrypted, or None.

    None is an ordinary answer, not a failure: most landlords are on PAYBILL or
    MANUAL and have no API app at all. Callers fall back to recording payments
    rather than pushing them.
    """
    if organization.mpesa_collection_mode != MpesaCollectionMode.AUTOMATED:
        return None
    if not (
        organization.daraja_consumer_key_encrypted
        and organization.daraja_consumer_secret_encrypted
        and organization.daraja_passkey_encrypted
        and organization.mpesa_shortcode
    ):
        return None

    consumer_key = await crypto.decrypt_for_org(
        db, organization.id, organization.daraja_consumer_key_encrypted
    )
    consumer_secret = await crypto.decrypt_for_org(
        db, organization.id, organization.daraja_consumer_secret_encrypted
    )
    passkey = await crypto.decrypt_for_org(db, organization.id, organization.daraja_passkey_encrypted)
    if not (consumer_key and consumer_secret and passkey):
        return None

    initiator = (
        await crypto.decrypt_for_org(db, organization.id, organization.daraja_initiator_name_encrypted)
        if organization.daraja_initiator_name_encrypted
        else None
    )
    security = (
        await crypto.decrypt_for_org(db, organization.id, organization.daraja_security_credential_encrypted)
        if organization.daraja_security_credential_encrypted
        else None
    )

    return DarajaCredentials(
        organization_id=organization.id,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        shortcode=organization.mpesa_shortcode,
        passkey=passkey,
        environment=organization.daraja_environment,
        initiator_name=initiator,
        security_credential=security,
    )


async def verify_credentials(creds: DarajaCredentials) -> tuple[bool, str]:
    """Check a landlord's Daraja keys against Safaricom, right now.

    Deliberately bypasses the token cache: after someone corrects a mistyped
    secret, a token cached under the old one would report success and the first
    real payment would still fail.

    What this proves is bounded, and the caller should say so rather than
    overclaim — OAuth authenticates the consumer key and secret only. The
    passkey and shortcode are not exercised until an actual STK push, because
    they are only used to build that request's password.
    """
    credentials = base64.b64encode(f"{creds.consumer_key}:{creds.consumer_secret}".encode()).decode()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{creds.base_url}/oauth/v1/generate?grant_type=client_credentials",
                headers={"Authorization": f"Basic {credentials}"},
            )
    except httpx.HTTPError as exc:
        return False, f"Could not reach Safaricom: {exc}"

    if response.status_code == 200 and (response.json() or {}).get("access_token"):
        return True, "Your API key and secret are working."
    if response.status_code in (400, 401, 403):
        return False, "Safaricom rejected these credentials. Check the consumer key and secret."
    return False, f"Safaricom returned an unexpected response ({response.status_code})."


async def _access_token(creds: DarajaCredentials) -> str:
    key = f"{_TOKEN_KEY}:{creds.organization_id}"
    cached = await redis_client.get(key)
    if cached:
        return cached

    credentials = base64.b64encode(f"{creds.consumer_key}:{creds.consumer_secret}".encode()).decode()

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{creds.base_url}/oauth/v1/generate?grant_type=client_credentials",
            headers={"Authorization": f"Basic {credentials}"},
        )
        if response.status_code != 200:
            raise MpesaError(f"Daraja auth failed ({response.status_code})")
        data = response.json()

    token = data.get("access_token")
    if not token:
        raise MpesaError("Daraja returned no access token")

    # Daraja tokens last 3599s; expire ours a minute early to avoid a race.
    ttl = max(60, int(data.get("expires_in", 3599)) - 60)
    await redis_client.set(key, token, ex=ttl)
    return token


def _password(creds: DarajaCredentials, timestamp: str) -> str:
    raw = f"{creds.shortcode}{creds.passkey}{timestamp}"
    return base64.b64encode(raw.encode()).decode()


def _daraja_phone(phone_number: str) -> str:
    """Daraja wants 2547XXXXXXXX — no plus, no leading zero."""
    return normalize_phone(phone_number).lstrip("+")


async def initiate_stk_push(
    creds: DarajaCredentials | None,
    *,
    phone_number: str,
    amount: Decimal,
    account_reference: str,
    description: str,
    payment_id: uuid.UUID,
) -> StkPushResult:
    """Prompt a tenant to pay, into `creds`' own shortcode.

    With no credentials the stub keeps the whole flow exercisable offline, and
    in development.
    """
    if creds is None:
        # Sandbox stub: deterministic ids so the callback can be simulated in tests.
        logger.info("Daraja not configured — simulating STK push for %s", mask(normalize_phone(phone_number)))
        return StkPushResult(
            checkout_request_id=f"ws_CO_SIM_{payment_id.hex[:16]}",
            merchant_request_id=f"SIM-{payment_id.hex[:12]}",
            customer_message="Simulated STK push (Daraja credentials not configured)",
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    payload: dict[str, Any] = {
        "BusinessShortCode": creds.shortcode,
        "Password": _password(creds, timestamp),
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        # Daraja rejects fractional amounts on paybill.
        "Amount": int(Decimal(amount).quantize(Decimal("1"))),
        "PartyA": _daraja_phone(phone_number),
        "PartyB": creds.shortcode,
        "PhoneNumber": _daraja_phone(phone_number),
        "CallBackURL": f"{settings.DARAJA_CALLBACK_BASE_URL}{settings.API_V1_PREFIX}/mpesa/callback",
        "AccountReference": account_reference[:12],
        "TransactionDesc": description[:13],
    }

    token = await _access_token(creds)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{creds.base_url}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )

    data = response.json() if response.content else {}
    if response.status_code != 200 or str(data.get("ResponseCode")) != "0":
        message = data.get("errorMessage") or data.get("ResponseDescription") or "STK push rejected"
        raise MpesaError(str(message))

    return StkPushResult(
        checkout_request_id=data["CheckoutRequestID"],
        merchant_request_id=data.get("MerchantRequestID", ""),
        customer_message=data.get("CustomerMessage", "Check your phone for the M-Pesa prompt"),
    )


def parse_callback(body: dict[str, Any]) -> CallbackResult:
    """Flatten Daraja's nested callback into something usable."""
    try:
        stk = body["Body"]["stkCallback"]
    except (KeyError, TypeError) as exc:
        raise MpesaError("Unrecognised callback payload") from exc

    result_code = int(stk.get("ResultCode", -1))
    result = CallbackResult(
        checkout_request_id=stk.get("CheckoutRequestID", ""),
        merchant_request_id=stk.get("MerchantRequestID"),
        success=result_code == 0,
        result_code=result_code,
        result_description=stk.get("ResultDesc", ""),
    )

    for item in stk.get("CallbackMetadata", {}).get("Item", []):
        name, value = item.get("Name"), item.get("Value")
        if value is None:
            continue
        if name == "MpesaReceiptNumber":
            result.mpesa_receipt = str(value)
        elif name == "Amount":
            result.amount = Decimal(str(value))
        elif name == "PhoneNumber":
            result.phone_number = normalize_phone(str(value))
        elif name == "TransactionDate":
            try:
                result.transaction_date = datetime.strptime(str(value), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            except ValueError:
                result.transaction_date = None

    return result


async def query_status(creds: DarajaCredentials | None, checkout_request_id: str) -> dict[str, Any]:
    """Ask Daraja what actually happened — used to verify a confirmation before we
    trust it, and to recover payments whose callback never arrived."""
    if creds is None:
        return {"ResultCode": "0", "ResultDesc": "Simulated success (Daraja not configured)"}

    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    token = await _access_token(creds)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{creds.base_url}/mpesa/stkpushquery/v1/query",
            json={
                "BusinessShortCode": creds.shortcode,
                "Password": _password(creds, timestamp),
                "Timestamp": timestamp,
                "CheckoutRequestID": checkout_request_id,
            },
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    return response.json() if response.content else {}


async def claim_callback(checkout_request_id: str) -> bool:
    """First caller for a given checkout id wins; duplicates are dropped.

    Redis `SET NX` is the idempotency gate for retried webhook deliveries.
    """
    key = f"mpesa:callback:{checkout_request_id}"
    return bool(await redis_client.set(key, "1", ex=_CALLBACK_LOCK_TTL, nx=True))


# ------------------------------------------------------------------ B2C payouts (US-041)
#
# Collections (STK push) pull money in; B2C pushes it out. Different credentials,
# different endpoint, and a fundamentally different response shape: Daraja
# acknowledges the *request* synchronously and reports the actual outcome later on
# the result URL, correlated only by the two conversation ids below.


@dataclass(slots=True)
class B2CRequestResult:
    conversation_id: str
    originator_conversation_id: str
    response_description: str
    simulated: bool = False


@dataclass(slots=True)
class B2CResult:
    conversation_id: str
    originator_conversation_id: str
    success: bool
    result_code: int
    result_description: str
    transaction_id: str | None = None
    amount: Decimal | None = None
    receiver_name: str | None = None
    completed_at: datetime | None = None


async def initiate_b2c_payment(
    creds: DarajaCredentials | None,
    *,
    phone_number: str,
    amount: Decimal,
    remarks: str,
    occasion: str,
    disbursement_id: uuid.UUID,
) -> B2CRequestResult:
    """Send money to an owner's M-Pesa number.

    Without B2C credentials this returns a deterministic simulated pair of ids so
    the whole approval → payout → result flow is exercisable offline; the caller
    is told via `simulated` so it can settle the payout immediately instead of
    waiting for a callback that will never arrive.
    """
    if amount <= Decimal("0"):
        raise MpesaError("A payout must be for a positive amount")

    if creds is None or not creds.can_pay_out:
        logger.info(
            "Daraja B2C not configured — simulating payout to %s", mask(normalize_phone(phone_number))
        )
        return B2CRequestResult(
            conversation_id=f"AG_SIM_{disbursement_id.hex[:16]}",
            originator_conversation_id=f"SIM-B2C-{disbursement_id.hex[:12]}",
            response_description="Simulated B2C payout (Daraja B2C credentials not configured)",
            simulated=True,
        )

    base = f"{settings.DARAJA_CALLBACK_BASE_URL}{settings.API_V1_PREFIX}/mpesa"
    payload: dict[str, Any] = {
        "InitiatorName": creds.initiator_name,
        "SecurityCredential": creds.security_credential,
        # BusinessPayment is the right category for a supplier/landlord payout;
        # SalaryPayment and PromotionPayment carry different limits and charges.
        "CommandID": "BusinessPayment",
        # Daraja rejects fractional amounts.
        "Amount": int(Decimal(amount).quantize(Decimal("1"))),
        "PartyA": creds.shortcode,
        "PartyB": _daraja_phone(phone_number),
        "Remarks": remarks[:100],
        "QueueTimeOutURL": f"{base}/b2c/timeout",
        "ResultURL": f"{base}/b2c/result",
        "Occasion": occasion[:100],
    }

    token = await _access_token(creds)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{creds.base_url}/mpesa/b2c/v1/paymentrequest",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )

    data = response.json() if response.content else {}
    if response.status_code != 200 or str(data.get("ResponseCode")) != "0":
        message = data.get("errorMessage") or data.get("ResponseDescription") or "B2C payout rejected"
        raise MpesaError(str(message))

    return B2CRequestResult(
        conversation_id=str(data.get("ConversationID", "")),
        originator_conversation_id=str(data.get("OriginatorConversationID", "")),
        response_description=str(data.get("ResponseDescription", "Payout accepted for processing")),
    )


def parse_b2c_result(body: dict[str, Any]) -> B2CResult:
    """Flatten Daraja's B2C result callback.

    Note the shape differs from the STK callback: parameters live under
    `ResultParameters.ResultParameter` and the amount arrives as a float.
    """
    try:
        result = body["Result"]
    except (KeyError, TypeError) as exc:
        raise MpesaError("Unrecognised B2C result payload") from exc

    result_code = int(result.get("ResultCode", -1))
    parsed = B2CResult(
        conversation_id=str(result.get("ConversationID", "")),
        originator_conversation_id=str(result.get("OriginatorConversationID", "")),
        success=result_code == 0,
        result_code=result_code,
        result_description=str(result.get("ResultDesc", "")),
        transaction_id=result.get("TransactionID") or None,
    )

    parameters = result.get("ResultParameters", {}).get("ResultParameter", [])
    if isinstance(parameters, dict):  # Daraja collapses a single parameter to an object.
        parameters = [parameters]
    for item in parameters:
        name, value = item.get("Key"), item.get("Value")
        if value is None:
            continue
        if name == "TransactionAmount":
            parsed.amount = Decimal(str(value))
        elif name == "TransactionReceipt":
            parsed.transaction_id = str(value)
        elif name == "ReceiverPartyPublicName":
            parsed.receiver_name = str(value)
        elif name == "TransactionCompletedDateTime":
            for fmt in ("%d.%m.%Y %H:%M:%S", "%Y%m%d%H%M%S"):
                try:
                    parsed.completed_at = datetime.strptime(str(value), fmt).replace(tzinfo=UTC)
                    break
                except ValueError:
                    continue

    return parsed


async def claim_b2c_result(conversation_id: str) -> bool:
    """Idempotency gate for retried B2C result deliveries — first caller wins."""
    key = f"mpesa:b2c:{conversation_id}"
    return bool(await redis_client.set(key, "1", ex=_CALLBACK_LOCK_TTL, nx=True))
