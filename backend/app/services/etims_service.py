"""KRA eTIMS submission — Phase 2 (US-053).

Every receipt issued by a VAT-registered landlord has to be declared to KRA,
which signs it and returns a control unit serial plus an invoice number. Those,
encoded into a QR code on the receipt, are what makes it a valid tax invoice.

The whole thing is best-effort by design. KRA's endpoint is not reliable enough
to sit in the payment path, and a tenant who has paid is entitled to a receipt
whether or not the tax authority is answering. So:

  * a submission is recorded first, then attempted;
  * a failure schedules a retry with exponential backoff rather than surfacing;
  * the receipt renders without the eTIMS block until a submission succeeds;
  * after `MAX_ATTEMPTS` the row is ABANDONED and the landlord is told, because
    at that point it is a compliance problem a person has to deal with.

An organisation with no credentials is simply not an eTIMS filer, and nothing
here runs for them.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_for_org, encrypt_for_org, mask
from app.models.billing import Invoice, Payment, Receipt
from app.models.customer_success import MilestoneKey
from app.models.etims import EtimsCredential, EtimsStatus, EtimsSubmission
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import Organization
from app.models.tenant import Tenancy, Tenant
from app.services import milestone_service, notification_service

logger = logging.getLogger("rentflow.etims")

MAX_ATTEMPTS = 5
# 2, 8, 32, 128 minutes — long enough to ride out a KRA outage without hammering.
_BACKOFF_BASE_MINUTES = 2
_BACKOFF_FACTOR = 4

SANDBOX_BASE_URL = "https://etims-api-sbx.kra.go.ke/etims-api"
PRODUCTION_BASE_URL = "https://etims-api.kra.go.ke/etims-api"


class EtimsError(RuntimeError):
    pass


def base_url(environment: str) -> str:
    return PRODUCTION_BASE_URL if environment == "production" else SANDBOX_BASE_URL


def _backoff(attempts: int) -> timedelta:
    return timedelta(minutes=_BACKOFF_BASE_MINUTES * (_BACKOFF_FACTOR ** max(0, attempts - 1)))


# ----------------------------------------------------------------- credentials


async def get_credential(db: AsyncSession, organization_id: uuid.UUID) -> EtimsCredential | None:
    return await db.scalar(select(EtimsCredential).where(EtimsCredential.organization_id == organization_id))


async def save_credential(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    kra_pin: str,
    device_serial: str,
    api_key: str,
    branch_id: str = "00",
    environment: str = "sandbox",
) -> EtimsCredential:
    """Store (or replace) a landlord's eTIMS registration, encrypted at rest."""
    # Sealed under this organisation's own key, not the platform master key
    # (see `app.core.crypto`). Re-saving an existing credential is what
    # migrates it off the legacy master-key ciphertext.
    #
    # Encrypted *before* the row is added to the session: minting a first-time
    # organisation key flushes, and a flush with a half-built credential row
    # already attached fails that row's NOT NULL constraints.
    sealed_serial = await encrypt_for_org(db, organization_id, device_serial.strip())
    sealed_api_key = await encrypt_for_org(db, organization_id, api_key.strip())

    record = await get_credential(db, organization_id)
    if record is None:
        record = EtimsCredential(organization_id=organization_id, kra_pin=kra_pin)
        db.add(record)

    record.kra_pin = kra_pin.strip().upper()
    record.device_serial_encrypted = sealed_serial
    record.api_key_encrypted = sealed_api_key
    record.branch_id = branch_id.strip() or "00"
    record.environment = "production" if environment == "production" else "sandbox"
    record.is_active = True
    record.last_error = None

    await db.commit()
    await db.refresh(record)
    return record


async def describe_credential(db: AsyncSession, record: EtimsCredential | None) -> dict:
    """Safe to return over the API — proves a credential is set without leaking it."""
    if record is None:
        return {"configured": False}
    return {
        "configured": True,
        "kra_pin": record.kra_pin,
        "branch_id": record.branch_id,
        "environment": record.environment,
        "is_active": record.is_active,
        "device_serial_hint": mask(
            await decrypt_for_org(db, record.organization_id, record.device_serial_encrypted)
        ),
        "last_verified_at": record.last_verified_at.isoformat() if record.last_verified_at else None,
        "last_error": record.last_error,
    }


async def delete_credential(db: AsyncSession, organization_id: uuid.UUID) -> bool:
    record = await get_credential(db, organization_id)
    if record is None:
        return False
    await db.delete(record)
    await db.commit()
    return True


# ----------------------------------------------------------------- submission


async def queue_receipt(db: AsyncSession, receipt: Receipt) -> EtimsSubmission | None:
    """Record intent to declare a receipt. Returns None if the org is not a filer.

    Called from the payment path, so it must never raise: it only writes a row.
    """
    credential = await get_credential(db, receipt.organization_id)
    if credential is None or not credential.is_active:
        return None

    existing = await db.scalar(select(EtimsSubmission).where(EtimsSubmission.receipt_id == receipt.id))
    if existing is not None:
        return existing

    submission = EtimsSubmission(
        organization_id=receipt.organization_id,
        receipt_id=receipt.id,
        status=EtimsStatus.PENDING,
        next_attempt_at=datetime.now(UTC),
    )
    db.add(submission)
    await db.flush()
    return submission


async def _build_payload(db: AsyncSession, receipt: Receipt, credential: EtimsCredential) -> dict:
    """The tax invoice as eTIMS wants it.

    Rent is an exempt supply in Kenya for residential lettings, so the tax rate is
    zero and the taxable amount equals the gross — but the line still has to be
    declared. Commercial lettings are the landlord's own VAT question; we declare
    what we were paid either way.
    """
    payment = await db.get(Payment, receipt.payment_id)
    if payment is None:
        raise EtimsError("Receipt has no payment")

    tenancy = await db.get(Tenancy, payment.tenancy_id)
    tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
    invoice = await db.get(Invoice, payment.invoice_id) if payment.invoice_id else None
    amount = Decimal(payment.amount)

    return {
        "tin": credential.kra_pin,
        "bhfId": credential.branch_id,
        "invcNo": receipt.reference_code,
        "orgInvcNo": invoice.reference_code if invoice else receipt.reference_code,
        "custTin": None,
        "custNm": tenant.full_name if tenant else "Walk-in customer",
        "salesTyCd": "N",
        "rcptTyCd": "S",
        "pmtTyCd": "01" if payment.method.value == "cash" else "05",
        "salesDt": receipt.issued_at.strftime("%Y%m%d"),
        "totItemCnt": 1,
        "taxblAmtA": float(amount),
        "taxAmtA": 0.0,
        "totTaxblAmt": float(amount),
        "totTaxAmt": 0.0,
        "totAmt": float(amount),
        "itemList": [
            {
                "itemSeq": 1,
                "itemNm": "Residential rent",
                "pkgQty": 1,
                "qty": 1,
                "prc": float(amount),
                "splyAmt": float(amount),
                "taxTyCd": "A",
                "taxblAmt": float(amount),
                "taxAmt": 0.0,
                "totAmt": float(amount),
            }
        ],
    }


async def _call_kra(db: AsyncSession, credential: EtimsCredential, payload: dict) -> dict[str, Any]:
    organization_id = credential.organization_id
    device_serial = await decrypt_for_org(db, organization_id, credential.device_serial_encrypted)
    api_key = await decrypt_for_org(db, organization_id, credential.api_key_encrypted)
    if not device_serial or not api_key:
        raise EtimsError("Stored eTIMS credentials could not be read — re-enter them in settings")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{base_url(credential.environment)}/saveTrnsSalesOsdc",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "cmcKey": api_key,
                "tin": credential.kra_pin,
                "bhfId": credential.branch_id,
                "dvcSrlNo": device_serial,
            },
        )

    body: dict[str, Any] = response.json() if response.content else {}
    if response.status_code != 200 or str(body.get("resultCd", "")) != "000":
        raise EtimsError(str(body.get("resultMsg") or f"eTIMS rejected the invoice ({response.status_code})"))
    return body


async def submit(db: AsyncSession, submission: EtimsSubmission) -> EtimsSubmission:
    """Attempt one submission, recording the outcome either way.

    Never raises for a KRA-side failure — the point of the row is to hold that
    state so the retry task can pick it up again.
    """
    receipt = await db.get(Receipt, submission.receipt_id)
    credential = await get_credential(db, submission.organization_id)
    submission.attempts += 1

    if receipt is None or credential is None or not credential.is_active:
        submission.status = EtimsStatus.ABANDONED
        submission.last_error = "No active eTIMS credential for this organisation"
        submission.next_attempt_at = None
        await db.commit()
        return submission

    try:
        payload = await _build_payload(db, receipt, credential)
        body = await _call_kra(db, credential, payload)
    except Exception as exc:  # noqa: BLE001 — every failure mode is a retry decision
        message = str(exc)[:512]
        logger.warning(
            "eTIMS submission %s failed on attempt %s: %s", submission.id, submission.attempts, message
        )
        submission.last_error = message
        if submission.attempts >= MAX_ATTEMPTS:
            submission.status = EtimsStatus.ABANDONED
            submission.next_attempt_at = None
            await _notify_abandoned(db, submission, receipt, message)
        else:
            submission.status = EtimsStatus.FAILED
            submission.next_attempt_at = datetime.now(UTC) + _backoff(submission.attempts)
        await db.commit()
        return submission

    data = body.get("data") or {}
    submission.status = EtimsStatus.SUBMITTED
    submission.submitted_at = datetime.now(UTC)
    submission.invoice_number = str(data.get("curRcptNo") or receipt.reference_code)
    submission.control_unit_serial = data.get("sdcId") or data.get("intrlData")
    submission.control_unit_signature = data.get("rcptSign")
    submission.verification_url = verification_url(credential, data, receipt)
    submission.response_payload = body
    submission.last_error = None
    submission.next_attempt_at = None

    credential.last_verified_at = submission.submitted_at
    credential.last_error = None

    await milestone_service.check_and_queue(db, submission.organization_id, MilestoneKey.FIRST_ETIMS_RECEIPT)

    await db.commit()
    await db.refresh(submission)
    return submission


def verification_url(credential: EtimsCredential, data: dict, receipt: Receipt) -> str:
    """What the QR code encodes — KRA's own checker page for this invoice."""
    explicit = data.get("qrCodeUrl") or data.get("intrlData")
    if isinstance(explicit, str) and explicit.startswith("http"):
        return explicit[:512]
    signature = data.get("rcptSign") or receipt.signature
    host = "etims-sbx.kra.go.ke" if credential.environment != "production" else "etims.kra.go.ke"
    return f"https://{host}/common/link/etims/receipt/indexEtimsReceiptData?Data={credential.kra_pin}{signature}"[
        :512
    ]


async def submit_receipt_now(db: AsyncSession, receipt: Receipt) -> EtimsSubmission | None:
    """Queue and immediately attempt — the path taken when a receipt is issued."""
    submission = await queue_receipt(db, receipt)
    if submission is None:
        return None
    return await submit(db, submission)


async def due_submissions(db: AsyncSession, limit: int = 100) -> list[EtimsSubmission]:
    """Everything the retry task should pick up, across all organisations."""
    rows = await db.scalars(
        select(EtimsSubmission)
        .where(
            EtimsSubmission.status.in_([EtimsStatus.PENDING, EtimsStatus.FAILED]),
            EtimsSubmission.next_attempt_at.is_not(None),
            EtimsSubmission.next_attempt_at <= datetime.now(UTC),
        )
        .order_by(EtimsSubmission.next_attempt_at)
        .limit(limit)
    )
    return list(rows)


# ----------------------------------------------------------------- QR + receipt data


def qr_data_uri(url: str) -> str:
    """An SVG data URI WeasyPrint can render inline — no network fetch at print time."""
    import segno

    return segno.make(url, error="m").svg_data_uri(scale=4, dark="#0f172a")


async def receipt_stamp(db: AsyncSession, receipt: Receipt) -> dict | None:
    """The eTIMS block a receipt PDF prints, or None when there is nothing to show."""
    submission = await db.scalar(select(EtimsSubmission).where(EtimsSubmission.receipt_id == receipt.id))
    if submission is None or submission.status != EtimsStatus.SUBMITTED:
        return None
    if not submission.verification_url:
        return None

    return {
        "invoice_number": submission.invoice_number,
        "control_unit_serial": submission.control_unit_serial,
        "signature": submission.control_unit_signature,
        "verification_url": submission.verification_url,
        "qr_data_uri": qr_data_uri(submission.verification_url),
        "submitted_at": submission.submitted_at,
    }


# ----------------------------------------------------------------- reporting


async def report(
    db: AsyncSession,
    organization_id: uuid.UUID,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict:
    """Submitted, failed and outstanding counts for a period (US-053)."""
    query = select(EtimsSubmission.status, func.count(EtimsSubmission.id)).where(
        EtimsSubmission.organization_id == organization_id
    )
    if period_start is not None:
        query = query.where(EtimsSubmission.created_at >= period_start)
    if period_end is not None:
        query = query.where(EtimsSubmission.created_at <= period_end)

    counts = {status.value: 0 for status in EtimsStatus}
    for status, count in await db.execute(query.group_by(EtimsSubmission.status)):
        counts[status.value] = count

    total = sum(counts.values())
    failures_query = (
        select(EtimsSubmission)
        .where(
            EtimsSubmission.organization_id == organization_id,
            EtimsSubmission.status.in_([EtimsStatus.FAILED, EtimsStatus.ABANDONED]),
        )
        .order_by(EtimsSubmission.updated_at.desc())
        .limit(25)
    )
    failures = []
    for row in await db.scalars(failures_query):
        receipt = await db.get(Receipt, row.receipt_id)
        failures.append(
            {
                "submission_id": str(row.id),
                "receipt_reference": receipt.reference_code if receipt else None,
                "status": row.status.value,
                "attempts": row.attempts,
                "last_error": row.last_error,
                "next_attempt_at": row.next_attempt_at.isoformat() if row.next_attempt_at else None,
            }
        )

    return {
        "total": total,
        "submitted": counts[EtimsStatus.SUBMITTED.value],
        "pending": counts[EtimsStatus.PENDING.value],
        "failed": counts[EtimsStatus.FAILED.value],
        "abandoned": counts[EtimsStatus.ABANDONED.value],
        "success_rate": (round(counts[EtimsStatus.SUBMITTED.value] / total * 100, 1) if total else 0.0),
        "recent_failures": failures,
    }


async def _notify_abandoned(
    db: AsyncSession, submission: EtimsSubmission, receipt: Receipt, reason: str
) -> None:
    """Tell the landlord — an undeclared receipt is their compliance exposure."""
    from app.models.user import User, UserRole

    organization = await db.get(Organization, submission.organization_id)
    owners = await db.scalars(
        select(User).where(
            User.organization_id == submission.organization_id,
            User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
            User.is_active.is_(True),
        )
    )
    for owner in owners:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(owner),
            notification_type=NotificationType.ACCOUNT,
            title="A receipt could not be filed with KRA",
            body=(
                f"Receipt {receipt.reference_code} was not accepted by eTIMS after "
                f"{MAX_ATTEMPTS} attempts: {reason}. "
                f"{organization.name if organization else 'Your account'} may need to declare it "
                f"manually. Check Settings → eTIMS."
            ),
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.IN_APP],
            link_path="/settings/etims",
            entity_type="etims_submission",
            entity_id=submission.id,
            organization_id=submission.organization_id,
        )
