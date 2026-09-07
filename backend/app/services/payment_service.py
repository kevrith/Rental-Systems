"""Payment capture and reconciliation (US-019, US-020, US-023).

Money enters the system two ways — an M-Pesa STK push the tenant approves on
their phone, or cash a caretaker hands in. Both converge on `_confirm`, which
allocates the money against the oldest open invoices, issues the receipt, and
notifies the tenant. Doing it in one place is what keeps the two channels
consistent.
"""

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import OrgContext, accessible_property_ids, assert_in_org
from app.core.permissions import Permission, role_has
from app.models.billing import (
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.customer_success import MilestoneKey, NpsTrigger
from app.models.developer import WebhookEvent
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import CaretakerAssignment, Property, Unit
from app.models.tenant import Tenancy, Tenant
from app.models.user import User, UserRole
from app.services import (
    audit_service,
    invoice_service,
    milestone_service,
    mpesa_service,
    notification_service,
    nps_service,
    receipt_service,
    reference_service,
    webhook_service,
)
from app.services.notifications import normalize_phone
from app.services.pdf_service import format_kes

logger = logging.getLogger("rentflow.payments")

ZERO = Decimal("0.00")


async def _load_tenancy(db: AsyncSession, context: OrgContext, tenancy_id: uuid.UUID) -> Tenancy:
    tenancy = assert_in_org(await db.get(Tenancy, tenancy_id), context, label="tenancy")
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        unit = await db.get(Unit, tenancy.unit_id)
        if unit is None or unit.property_id not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this property"
            )
    return tenancy


async def _caretaker_cash_limit(db: AsyncSession, context: OrgContext, tenancy: Tenancy) -> Decimal | None:
    """The cash ceiling this caretaker may record on this property, if any."""
    if context.role != UserRole.CARETAKER:
        return None
    unit = await db.get(Unit, tenancy.unit_id)
    if unit is None:
        return None
    assignment = await db.scalar(
        select(CaretakerAssignment).where(
            CaretakerAssignment.user_id == context.user.id,
            CaretakerAssignment.property_id == unit.property_id,
            CaretakerAssignment.is_active.is_(True),
        )
    )
    if assignment and assignment.cash_limit is not None:
        return Decimal(assignment.cash_limit)
    return (
        Decimal(context.organization.default_caretaker_cash_limit)
        if context.organization.default_caretaker_cash_limit is not None
        else None
    )


async def record_cash_payment(
    db: AsyncSession,
    context: OrgContext,
    *,
    tenancy_id: uuid.UUID,
    amount: Decimal,
    payment_date: date,
    method: PaymentMethod = PaymentMethod.CASH,
    notes: str | None = None,
    reference: str | None = None,
    request: Request | None = None,
) -> Payment:
    """Record money collected off-platform (US-020)."""
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive")

    tenancy = await _load_tenancy(db, context, tenancy_id)

    over_limit = False
    limit = await _caretaker_cash_limit(db, context, tenancy)
    if limit is not None and amount > limit:
        over_limit = True

    needs_approval = await _needs_dual_approval(db, context, amount, method)

    code = await reference_service.generate_reference(db, Payment, context.organization_id, "PMT")
    payment = Payment(
        organization_id=context.organization_id,
        reference_code=code,
        tenancy_id=tenancy.id,
        amount=amount,
        method=method,
        status=PaymentStatus.PENDING,
        payment_date=payment_date,
        recorded_by_id=context.user.id,
        notes=notes,
        requires_approval=needs_approval,
        mpesa_receipt=reference if method == PaymentMethod.MPESA and reference else None,
        # Bank and cheque references are not globally unique like an M-Pesa
        # code, so they get their own column rather than sharing `mpesa_receipt`
        # (US-101).
        bank_reference=(
            reference if method in (PaymentMethod.BANK_TRANSFER, PaymentMethod.CHEQUE) and reference else None
        ),
    )
    db.add(payment)
    await db.flush()

    if not needs_approval:
        await _confirm(db, payment, confirmed_at=datetime.now(UTC))

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="payment.recorded",
        entity_type="payment",
        entity_id=payment.id,
        actor=context.user,
        summary=(
            f"Recorded KES {format_kes(amount)} ({method.value}) for {tenancy.reference_code}"
            + (" — held for approval" if needs_approval else "")
        ),
        changes={
            "over_cash_limit": over_limit,
            "cash_limit": str(limit) if limit else None,
            "requires_approval": needs_approval,
        },
        request=request,
    )

    if over_limit:
        await _alert_owners_over_limit(db, context, payment, tenancy, limit or ZERO)
    if needs_approval:
        await _request_approval(db, context, payment, tenancy)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That M-Pesa reference has already been recorded",
        ) from exc

    await db.refresh(payment)
    return payment


# ------------------------------------------------------------ dual approval


async def _needs_dual_approval(
    db: AsyncSession, context: OrgContext, amount: Decimal, method: PaymentMethod
) -> bool:
    """Whether this payment must be signed off by a second person.

    Cash only. An M-Pesa payment already carries Safaricom's own confirmation
    and a bank transfer shows up on a statement, so neither depends on one
    person's word — cash is the only channel where the person who takes the
    money is the only evidence it was taken.

    Off by default (`cash_dual_approval_threshold` is null), and skipped
    entirely when nobody else in the organisation could approve it. A solo
    landlord who sets a threshold and then finds their own payments stuck in a
    queue only they can clear has been given a worse product, not a safer one.
    """
    threshold = context.organization.cash_dual_approval_threshold
    if method != PaymentMethod.CASH or threshold is None or amount <= Decimal(threshold):
        return False

    approver_roles = [role for role in UserRole if role_has(role, Permission.PAYMENT_APPROVE)]
    other_approver = await db.scalar(
        select(User.id).where(
            User.organization_id == context.organization_id,
            User.id != context.user.id,
            User.role.in_(approver_roles),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    return other_approver is not None


async def _request_approval(
    db: AsyncSession, context: OrgContext, payment: Payment, tenancy: Tenancy
) -> None:
    tenant = await db.get(Tenant, tenancy.tenant_id)
    approvers = await db.scalars(
        select(User).where(
            User.organization_id == context.organization_id,
            User.id != context.user.id,
            User.role.in_([role for role in UserRole if role_has(role, Permission.PAYMENT_APPROVE)]),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    for approver in approvers:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(approver),
            notification_type=NotificationType.PAYMENT_APPROVAL,
            title="Cash payment needs your approval",
            body=(
                f"{context.user.full_name} recorded KES {format_kes(payment.amount)} in cash for "
                f"{tenant.full_name if tenant else tenancy.reference_code}. It is held pending your "
                f"approval. Reference {payment.reference_code}."
            ),
            channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH, NotificationChannel.WHATSAPP],
            entity_type="payment",
            entity_id=payment.id,
        )


async def list_pending_approval(db: AsyncSession, context: OrgContext) -> list[Payment]:
    """Cash held for a second signature, oldest first."""
    query = (
        select(Payment)
        # The list serialiser reads `payment.receipt`; a lazy load on an async
        # session raises `MissingGreenlet` rather than quietly fetching.
        .options(selectinload(Payment.receipt)).where(
            Payment.organization_id == context.organization_id,
            Payment.requires_approval.is_(True),
            Payment.status == PaymentStatus.PENDING,
        )
    )
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(
            Payment.tenancy_id.in_(
                select(Tenancy.id).join(Unit, Unit.id == Tenancy.unit_id).where(Unit.property_id.in_(allowed))
            )
        )
    rows = await db.scalars(query.order_by(Payment.created_at))
    return list(rows)


async def approve_payment(
    db: AsyncSession,
    context: OrgContext,
    payment_id: uuid.UUID,
    *,
    note: str | None = None,
    request: Request | None = None,
) -> Payment:
    """Sign off held cash, which is what actually banks it.

    Only now does the payment allocate against invoices, generate a receipt and
    reach the tenant — everything `_confirm` does for an ordinary payment. Up
    to this point the money was recorded but not counted, which is the whole
    point of holding it.
    """
    payment = assert_in_org(await db.get(Payment, payment_id), context, label="payment")
    _assert_approvable(payment, context)

    payment.requires_approval = False
    payment.approved_by_id = context.user.id
    payment.approved_at = datetime.now(UTC)
    payment.approval_note = note

    await _confirm(db, payment, confirmed_at=datetime.now(UTC))

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="payment.approved",
        entity_type="payment",
        entity_id=payment.id,
        actor=context.user,
        summary=f"Approved cash payment {payment.reference_code} of KES {format_kes(payment.amount)}",
        changes={"note": note},
        request=request,
    )
    await db.commit()
    await db.refresh(payment)
    return payment


async def reject_payment(
    db: AsyncSession,
    context: OrgContext,
    payment_id: uuid.UUID,
    *,
    reason: str,
    request: Request | None = None,
) -> Payment:
    """Refuse held cash. Nothing is allocated and the tenant is never told it
    was received — because as far as the books are concerned, it was not."""
    payment = assert_in_org(await db.get(Payment, payment_id), context, label="payment")
    _assert_approvable(payment, context)

    payment.requires_approval = False
    payment.status = PaymentStatus.CANCELLED
    payment.failure_reason = reason[:512]
    payment.approved_by_id = context.user.id
    payment.approved_at = datetime.now(UTC)
    payment.approval_note = reason

    recorder = await db.get(User, payment.recorded_by_id) if payment.recorded_by_id else None
    if recorder is not None:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(recorder),
            notification_type=NotificationType.PAYMENT_APPROVAL,
            title="Cash payment rejected",
            body=(
                f"{context.user.full_name} rejected the KES {format_kes(payment.amount)} cash "
                f"payment you recorded ({payment.reference_code}). Reason: {reason}"
            ),
            channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH],
            entity_type="payment",
            entity_id=payment.id,
        )

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="payment.rejected",
        entity_type="payment",
        entity_id=payment.id,
        actor=context.user,
        summary=f"Rejected cash payment {payment.reference_code}: {reason}",
        request=request,
    )
    await db.commit()
    await db.refresh(payment)
    return payment


def _assert_approvable(payment: Payment, context: OrgContext) -> None:
    """The dual in dual approval — a different person, on a payment still held."""
    if not payment.requires_approval or payment.status != PaymentStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This payment is not waiting for approval",
        )
    if payment.recorded_by_id == context.user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot approve a payment you recorded yourself",
        )


async def _alert_owners_over_limit(
    db: AsyncSession, context: OrgContext, payment: Payment, tenancy: Tenancy, limit: Decimal
) -> None:
    owners = await db.scalars(
        select(User).where(
            User.organization_id == context.organization_id,
            User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
            User.is_active.is_(True),
        )
    )
    for owner in owners:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(owner),
            notification_type=NotificationType.ACCOUNT,
            title="Cash payment above caretaker limit",
            body=(
                f"{context.user.full_name} recorded KES {format_kes(payment.amount)} in cash for "
                f"tenancy {tenancy.reference_code}, above their KES {format_kes(limit)} limit. "
                f"Reference {payment.reference_code}."
            ),
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.PUSH],
            entity_type="payment",
            entity_id=payment.id,
        )


# ------------------------------------------------------------------- allocation


async def _confirm(db: AsyncSession, payment: Payment, confirmed_at: datetime) -> None:
    """Mark a payment confirmed, allocate it to invoices, receipt it, notify."""
    payment.status = PaymentStatus.CONFIRMED
    payment.paid_at = confirmed_at
    if payment.payment_date is None:
        payment.payment_date = confirmed_at.date()

    await _allocate(db, payment)
    # Autoflush is off on our sessions, so the allocation must be pushed to the
    # database before the balance aggregate below can see it.
    await db.flush()

    balance = await invoice_service.outstanding_balance(db, payment.tenancy_id)
    receipt = await receipt_service.issue_receipt(db, payment, balance)
    await db.flush()

    await receipt_service.deliver(db, receipt, payment)
    await _notify_payment_confirmed(db, payment, balance)

    try:
        from app.services import fraud_detection_service

        tenancy_for_fraud = await db.get(Tenancy, payment.tenancy_id)
        if tenancy_for_fraud is not None:
            await fraud_detection_service.evaluate_payment(db, payment, tenancy_for_fraud)
    except Exception:  # noqa: BLE001 — a detector bug must never block a payment
        logger.exception("Fraud detection failed for payment %s", payment.id)

    await webhook_service.dispatch(
        db,
        payment.organization_id,
        WebhookEvent.PAYMENT_RECEIVED,
        {
            "id": str(payment.id),
            "reference_code": payment.reference_code,
            "tenancy_id": str(payment.tenancy_id),
            "amount": str(payment.amount),
            "method": payment.method.value,
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        },
    )

    confirmed_count = await db.scalar(
        select(func.count(Payment.id)).where(
            Payment.organization_id == payment.organization_id, Payment.status == PaymentStatus.CONFIRMED
        )
    )
    if (confirmed_count or 0) >= 100:
        await milestone_service.check_and_queue(db, payment.organization_id, MilestoneKey.PAYMENTS_100)
    if confirmed_count == 1:
        owners = await db.scalars(
            select(User).where(
                User.organization_id == payment.organization_id,
                User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
                User.is_active.is_(True),
            )
        )
        for owner in owners:
            await nps_service.queue_if_eligible(
                db, payment.organization_id, owner.id, NpsTrigger.FIRST_PAYMENT
            )


async def _allocate(db: AsyncSession, payment: Payment) -> None:
    """Apply the payment to open invoices, oldest first.

    Overpayment is deliberately left unallocated rather than parked on a future
    invoice — it shows as a credit against the balance and settles the next
    invoice when one is generated.
    """
    remaining = Decimal(payment.amount)
    invoices = await invoice_service.open_invoices_for_tenancy(db, payment.tenancy_id)

    for invoice in invoices:
        if remaining <= 0:
            break
        owed = Decimal(invoice.total) - Decimal(invoice.amount_paid)
        if owed <= 0:
            continue
        applied = min(owed, remaining)
        invoice.amount_paid = Decimal(invoice.amount_paid) + applied
        invoice.status = invoice_service.recalculate_status(invoice)
        remaining -= applied
        if payment.invoice_id is None:
            payment.invoice_id = invoice.id


async def _notify_payment_confirmed(db: AsyncSession, payment: Payment, balance: Decimal) -> None:
    tenancy = await db.get(Tenancy, payment.tenancy_id)
    tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
    if tenant is None:
        return

    recorded_by = await db.get(User, payment.recorded_by_id) if payment.recorded_by_id else None
    unit = await db.get(Unit, tenancy.unit_id) if tenancy else None
    property_record = await db.get(Property, unit.property_id) if unit else None
    where = f"{property_record.name} unit {unit.unit_number}" if property_record and unit else "your unit"

    if payment.method == PaymentMethod.CASH and recorded_by:
        body = (
            f"Your cash payment of KES {format_kes(payment.amount)} has been recorded by "
            f"{recorded_by.full_name} for {where}. Reference: {payment.reference_code}. "
            f"Outstanding balance: KES {format_kes(balance)}."
        )
    else:
        body = (
            f"Payment of KES {format_kes(payment.amount)} received for {where}. "
            f"Reference: {payment.reference_code}. "
            f"Outstanding balance: KES {format_kes(balance)}."
        )

    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_tenant(tenant),
        notification_type=NotificationType.PAYMENT_CONFIRMED,
        title="Payment confirmed",
        body=body,
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="payment",
        entity_id=payment.id,
        organization_id=payment.organization_id,
        # For an organisation that has rewritten this message (Module 21).
        variables={
            "tenant_name": tenant.full_name,
            "amount": format_kes(payment.amount),
            "reference_code": payment.reference_code,
            "balance": format_kes(balance),
            "property_name": property_record.name if property_record else "",
            "unit_number": unit.unit_number if unit else "",
        },
    )


# ----------------------------------------------------------------------- M-Pesa


async def initiate_stk_push(
    db: AsyncSession,
    context: OrgContext,
    *,
    tenancy_id: uuid.UUID,
    amount: Decimal,
    phone_number: str | None = None,
    request: Request | None = None,
) -> tuple[Payment, str]:
    """Create a pending payment and ask Safaricom to prompt the tenant."""
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive")

    tenancy = await _load_tenancy(db, context, tenancy_id)
    tenant = await db.get(Tenant, tenancy.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    target_phone = normalize_phone(phone_number or tenant.phone_number)

    code = await reference_service.generate_reference(db, Payment, context.organization_id, "PMT")
    payment = Payment(
        organization_id=context.organization_id,
        reference_code=code,
        tenancy_id=tenancy.id,
        amount=amount,
        method=PaymentMethod.MPESA,
        status=PaymentStatus.PENDING,
        phone_number=target_phone,
        recorded_by_id=context.user.id,
    )
    db.add(payment)
    await db.flush()

    try:
        result = await mpesa_service.initiate_stk_push(
            phone_number=target_phone,
            amount=amount,
            account_reference=tenancy.reference_code,
            description=f"Rent {tenancy.reference_code}",
            payment_id=payment.id,
        )
    except mpesa_service.MpesaError as exc:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = str(exc)[:500]
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"M-Pesa request failed: {exc}"
        ) from exc

    payment.mpesa_checkout_request_id = result.checkout_request_id
    payment.mpesa_merchant_request_id = result.merchant_request_id

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="payment.stk_push_sent",
        entity_type="payment",
        entity_id=payment.id,
        actor=context.user,
        summary=f"STK push for KES {format_kes(amount)} to {target_phone}",
        request=request,
    )
    await db.commit()
    await db.refresh(payment)
    return payment, result.customer_message


async def handle_callback(db: AsyncSession, body: dict) -> str:
    """Process a Daraja STK callback. Always returns a message; never raises, so
    Safaricom always sees a 200 and stops retrying."""
    try:
        result = mpesa_service.parse_callback(body)
    except mpesa_service.MpesaError as exc:
        return f"Ignored: {exc}"

    if not await mpesa_service.claim_callback(result.checkout_request_id):
        return "Duplicate callback ignored"

    payment = await db.scalar(
        select(Payment)
        .options(selectinload(Payment.receipt), selectinload(Payment.invoice))
        .where(Payment.mpesa_checkout_request_id == result.checkout_request_id)
    )
    if payment is None:
        return "No matching payment"
    if payment.status == PaymentStatus.CONFIRMED:
        return "Payment already confirmed"

    if not result.success:
        payment.status = PaymentStatus.CANCELLED if result.result_code == 1032 else PaymentStatus.FAILED
        payment.failure_reason = result.result_description[:500]
        await db.commit()
        return f"Payment marked {payment.status.value}"

    if result.mpesa_receipt:
        already = await db.scalar(
            select(Payment.id).where(Payment.mpesa_receipt == result.mpesa_receipt, Payment.id != payment.id)
        )
        if already:
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = "Duplicate M-Pesa receipt"
            await db.commit()
            return "Duplicate M-Pesa receipt ignored"

    # Confirm against Daraja before banking it — the callback alone is not proof.
    verification = await mpesa_service.query_status(result.checkout_request_id)
    if str(verification.get("ResultCode", "0")) not in ("0", ""):
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = str(verification.get("ResultDesc", "Verification failed"))[:500]
        await db.commit()
        return "Verification against Daraja failed"

    payment.mpesa_receipt = result.mpesa_receipt
    if result.amount is not None:
        payment.amount = result.amount
    if result.phone_number:
        payment.phone_number = result.phone_number

    confirmed_at = result.transaction_date or datetime.now(UTC)
    await _confirm(db, payment, confirmed_at)

    audit_service.record(
        db,
        organization_id=payment.organization_id,
        action="payment.confirmed",
        entity_type="payment",
        entity_id=payment.id,
        summary=f"M-Pesa {result.mpesa_receipt} confirmed KES {format_kes(payment.amount)}",
    )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return "Duplicate M-Pesa receipt ignored"
    return "Payment confirmed"


async def poll_status(db: AsyncSession, context: OrgContext, payment_id: uuid.UUID) -> Payment:
    """Client-side polling fallback for when the callback is slow or lost."""
    payment = assert_in_org(await db.get(Payment, payment_id), context, label="payment")
    if payment.status != PaymentStatus.PENDING or not payment.mpesa_checkout_request_id:
        return payment

    response = await mpesa_service.query_status(payment.mpesa_checkout_request_id)
    code = str(response.get("ResultCode", ""))
    if code == "0":
        await _confirm(db, payment, datetime.now(UTC))
        await db.commit()
    elif code and code != "1037":  # 1037 = still waiting for the user
        payment.status = PaymentStatus.CANCELLED if code == "1032" else PaymentStatus.FAILED
        payment.failure_reason = str(response.get("ResultDesc", ""))[:500]
        await db.commit()

    await db.refresh(payment)
    return payment


# ------------------------------------------------------------------------ query


async def list_payments(
    db: AsyncSession,
    context: OrgContext,
    *,
    tenancy_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    payment_status: PaymentStatus | None = None,
    limit: int = 100,
) -> list[Payment]:
    query = select(Payment).where(Payment.organization_id == context.organization_id)

    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(
            Payment.tenancy_id.in_(
                select(Tenancy.id).join(Unit, Unit.id == Tenancy.unit_id).where(Unit.property_id.in_(allowed))
            )
        )
    if tenancy_id:
        query = query.where(Payment.tenancy_id == tenancy_id)
    if property_id:
        query = query.where(
            Payment.tenancy_id.in_(
                select(Tenancy.id)
                .join(Unit, Unit.id == Tenancy.unit_id)
                .where(Unit.property_id == property_id)
            )
        )
    if payment_status:
        query = query.where(Payment.status == payment_status)

    rows = await db.scalars(
        query.options(selectinload(Payment.receipt)).order_by(Payment.created_at.desc()).limit(limit)
    )
    return list(rows)
