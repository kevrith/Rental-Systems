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
from typing import Any

import httpx

from app.core.config import settings
from app.core.redis import redis_client
from app.services.notifications import normalize_phone

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


def is_configured() -> bool:
    return bool(
        settings.DARAJA_CONSUMER_KEY
        and settings.DARAJA_CONSUMER_SECRET
        and settings.DARAJA_SHORTCODE
        and settings.DARAJA_PASSKEY
    )


async def _access_token() -> str:
    cached = await redis_client.get(_TOKEN_KEY)
    if cached:
        return cached

    credentials = base64.b64encode(
        f"{settings.DARAJA_CONSUMER_KEY}:{settings.DARAJA_CONSUMER_SECRET}".encode()
    ).decode()

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{settings.daraja_base_url}/oauth/v1/generate?grant_type=client_credentials",
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
    await redis_client.set(_TOKEN_KEY, token, ex=ttl)
    return token


def _password(timestamp: str) -> str:
    raw = f"{settings.DARAJA_SHORTCODE}{settings.DARAJA_PASSKEY}{timestamp}"
    return base64.b64encode(raw.encode()).decode()


def _daraja_phone(phone_number: str) -> str:
    """Daraja wants 2547XXXXXXXX — no plus, no leading zero."""
    return normalize_phone(phone_number).lstrip("+")


async def initiate_stk_push(
    *, phone_number: str, amount: Decimal, account_reference: str, description: str, payment_id: uuid.UUID
) -> StkPushResult:
    if not is_configured():
        # Sandbox stub: deterministic ids so the callback can be simulated in tests.
        logger.info("Daraja not configured — simulating STK push for %s", phone_number)
        return StkPushResult(
            checkout_request_id=f"ws_CO_SIM_{payment_id.hex[:16]}",
            merchant_request_id=f"SIM-{payment_id.hex[:12]}",
            customer_message="Simulated STK push (Daraja credentials not configured)",
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    payload: dict[str, Any] = {
        "BusinessShortCode": settings.DARAJA_SHORTCODE,
        "Password": _password(timestamp),
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        # Daraja rejects fractional amounts on paybill.
        "Amount": int(Decimal(amount).quantize(Decimal("1"))),
        "PartyA": _daraja_phone(phone_number),
        "PartyB": settings.DARAJA_SHORTCODE,
        "PhoneNumber": _daraja_phone(phone_number),
        "CallBackURL": f"{settings.DARAJA_CALLBACK_BASE_URL}{settings.API_V1_PREFIX}/mpesa/callback",
        "AccountReference": account_reference[:12],
        "TransactionDesc": description[:13],
    }

    token = await _access_token()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.daraja_base_url}/mpesa/stkpush/v1/processrequest",
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


async def query_status(checkout_request_id: str) -> dict[str, Any]:
    """Ask Daraja what actually happened — used to verify a confirmation before we
    trust it, and to recover payments whose callback never arrived."""
    if not is_configured():
        return {"ResultCode": "0", "ResultDesc": "Simulated success (Daraja not configured)"}

    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    token = await _access_token()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.daraja_base_url}/mpesa/stkpushquery/v1/query",
            json={
                "BusinessShortCode": settings.DARAJA_SHORTCODE,
                "Password": _password(timestamp),
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


def is_b2c_configured() -> bool:
    return bool(
        settings.DARAJA_CONSUMER_KEY
        and settings.DARAJA_CONSUMER_SECRET
        and settings.DARAJA_B2C_SHORTCODE
        and settings.DARAJA_B2C_INITIATOR_NAME
        and settings.DARAJA_B2C_SECURITY_CREDENTIAL
    )


async def initiate_b2c_payment(
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

    if not is_b2c_configured():
        logger.info("Daraja B2C not configured — simulating payout to %s", phone_number)
        return B2CRequestResult(
            conversation_id=f"AG_SIM_{disbursement_id.hex[:16]}",
            originator_conversation_id=f"SIM-B2C-{disbursement_id.hex[:12]}",
            response_description="Simulated B2C payout (Daraja B2C credentials not configured)",
            simulated=True,
        )

    base = f"{settings.DARAJA_CALLBACK_BASE_URL}{settings.API_V1_PREFIX}/mpesa"
    payload: dict[str, Any] = {
        "InitiatorName": settings.DARAJA_B2C_INITIATOR_NAME,
        "SecurityCredential": settings.DARAJA_B2C_SECURITY_CREDENTIAL,
        # BusinessPayment is the right category for a supplier/landlord payout;
        # SalaryPayment and PromotionPayment carry different limits and charges.
        "CommandID": "BusinessPayment",
        # Daraja rejects fractional amounts.
        "Amount": int(Decimal(amount).quantize(Decimal("1"))),
        "PartyA": settings.DARAJA_B2C_SHORTCODE,
        "PartyB": _daraja_phone(phone_number),
        "Remarks": remarks[:100],
        "QueueTimeOutURL": f"{base}/b2c/timeout",
        "ResultURL": f"{base}/b2c/result",
        "Occasion": occasion[:100],
    }

    token = await _access_token()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.daraja_base_url}/mpesa/b2c/v1/paymentrequest",
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
