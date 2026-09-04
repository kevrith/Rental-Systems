import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import OrgContext, assert_in_org, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentStatus
from app.models.file import StoredFile
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, Tenant
from app.models.user import User
from app.schemas.billing import (
    AgingBuckets,
    ArrearsReport,
    ArrearsRowRead,
    GenerateInvoiceRequest,
    InvoiceDetail,
    InvoiceRead,
    LineItemRead,
    PaymentDetail,
    PaymentRead,
    ReceiptRead,
    RecordPaymentRequest,
    SendRemindersRequest,
    SendRemindersResponse,
    StkPushRequest,
    StkPushResponse,
)
from app.services import (
    agency_service,
    arrears_service,
    demand_letter_service,
    file_service,
    invoice_service,
    mpesa_service,
    notification_service,
    payment_service,
    tenant_service,
)
from app.services.pdf_service import format_kes

invoices_router = APIRouter()
payments_router = APIRouter()
arrears_router = APIRouter()
mpesa_router = APIRouter()


async def _invoice_detail(db: AsyncSession, invoice: Invoice) -> InvoiceDetail:
    tenancy = await db.get(Tenancy, invoice.tenancy_id)
    tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
    unit = await db.get(Unit, tenancy.unit_id) if tenancy else None
    property_record = await db.get(Property, unit.property_id) if unit else None

    document_url = None
    if invoice.document_id:
        record = await db.get(StoredFile, invoice.document_id)
        if record:
            document_url = file_service.to_url(record)

    return InvoiceDetail(
        **InvoiceRead.model_validate(invoice).model_dump(),
        balance=invoice.balance,
        line_items=[LineItemRead.model_validate(item) for item in invoice.line_items],
        tenant_name=tenant.full_name if tenant else None,
        unit_number=unit.unit_number if unit else None,
        property_name=property_record.name if property_record else None,
        document_url=document_url,
    )


async def _payment_detail(db: AsyncSession, payment: Payment) -> PaymentDetail:
    tenancy = await db.get(Tenancy, payment.tenancy_id)
    tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
    unit = await db.get(Unit, tenancy.unit_id) if tenancy else None
    property_record = await db.get(Property, unit.property_id) if unit else None
    recorded_by = await db.get(User, payment.recorded_by_id) if payment.recorded_by_id else None

    receipt = payment.receipt
    receipt_url = None
    if receipt and receipt.document_id:
        record = await db.get(StoredFile, receipt.document_id)
        if record:
            receipt_url = file_service.to_url(record)

    return PaymentDetail(
        **PaymentRead.model_validate(payment).model_dump(),
        tenant_name=tenant.full_name if tenant else None,
        unit_number=unit.unit_number if unit else None,
        property_name=property_record.name if property_record else None,
        receipt=ReceiptRead.model_validate(receipt) if receipt else None,
        receipt_url=receipt_url,
        recorded_by_name=recorded_by.full_name if recorded_by else None,
    )


async def _payment_details(db: AsyncSession, payments: list[Payment]) -> list[PaymentDetail]:
    """The list view, batched — `_payment_detail` costs six round trips per row."""
    if not payments:
        return []

    tenancies = {
        row.id: row
        for row in await db.scalars(select(Tenancy).where(Tenancy.id.in_({p.tenancy_id for p in payments})))
    }
    tenants = (
        {
            row.id: row
            for row in await db.scalars(
                select(Tenant).where(Tenant.id.in_({t.tenant_id for t in tenancies.values()}))
            )
        }
        if tenancies
        else {}
    )
    units = (
        {
            row.id: row
            for row in await db.scalars(
                select(Unit).where(Unit.id.in_({t.unit_id for t in tenancies.values()}))
            )
        }
        if tenancies
        else {}
    )
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

    user_ids = {p.recorded_by_id for p in payments if p.recorded_by_id}
    users = (
        {row.id: row for row in await db.scalars(select(User).where(User.id.in_(user_ids)))}
        if user_ids
        else {}
    )

    document_ids = {p.receipt.document_id for p in payments if p.receipt and p.receipt.document_id}
    documents = (
        {row.id: row for row in await db.scalars(select(StoredFile).where(StoredFile.id.in_(document_ids)))}
        if document_ids
        else {}
    )

    result = []
    for payment in payments:
        tenancy = tenancies.get(payment.tenancy_id)
        tenant = tenants.get(tenancy.tenant_id) if tenancy else None
        unit = units.get(tenancy.unit_id) if tenancy else None
        property_record = properties.get(unit.property_id) if unit else None
        receipt = payment.receipt
        document = documents.get(receipt.document_id) if receipt and receipt.document_id else None

        result.append(
            PaymentDetail(
                **PaymentRead.model_validate(payment).model_dump(),
                tenant_name=tenant.full_name if tenant else None,
                unit_number=unit.unit_number if unit else None,
                property_name=property_record.name if property_record else None,
                receipt=ReceiptRead.model_validate(receipt) if receipt else None,
                receipt_url=file_service.to_url(document) if document else None,
                recorded_by_name=(
                    users[payment.recorded_by_id].full_name if payment.recorded_by_id in users else None
                ),
            )
        )
    return result


# ------------------------------------------------------------------------ invoices


@invoices_router.get("", response_model=list[InvoiceDetail])
async def list_invoices(
    tenancy_id: uuid.UUID | None = None,
    invoice_status: InvoiceStatus | None = None,
    property_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.INVOICE_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceDetail]:
    query = (
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.organization_id == context.organization_id)
    )
    if tenancy_id:
        query = query.where(Invoice.tenancy_id == tenancy_id)
    if invoice_status:
        query = query.where(Invoice.status == invoice_status)
    if property_id:
        query = query.where(
            Invoice.tenancy_id.in_(
                select(Tenancy.id)
                .join(Unit, Unit.id == Tenancy.unit_id)
                .where(Unit.property_id == property_id)
            )
        )

    rows = await db.scalars(query.order_by(Invoice.due_date.desc()).limit(limit))
    return [await _invoice_detail(db, invoice) for invoice in rows]


@invoices_router.post("/generate", response_model=InvoiceDetail, status_code=status.HTTP_201_CREATED)
async def generate_invoice(
    payload: GenerateInvoiceRequest,
    context: OrgContext = Depends(require_write(Permission.INVOICE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> InvoiceDetail:
    """Raise this period's invoice ahead of the scheduled run."""
    tenancy = await tenant_service.get_tenancy(db, context, payload.tenancy_id)
    invoice = await invoice_service.generate_invoice_for_tenancy(db, tenancy, payload.issue_date)
    if invoice is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An invoice already exists for this tenancy and billing period",
        )
    await db.commit()
    await db.refresh(invoice)
    return await _invoice_detail(db, invoice)


@invoices_router.get("/{invoice_id}", response_model=InvoiceDetail)
async def get_invoice(
    invoice_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.INVOICE_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> InvoiceDetail:
    invoice = assert_in_org(
        await db.scalar(
            select(Invoice).options(selectinload(Invoice.line_items)).where(Invoice.id == invoice_id)
        ),
        context,
        label="invoice",
    )
    return await _invoice_detail(db, invoice)


# ------------------------------------------------------------------------ payments


@payments_router.post("", response_model=PaymentDetail, status_code=status.HTTP_201_CREATED)
async def record_payment(
    payload: RecordPaymentRequest,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PAYMENT_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> PaymentDetail:
    """Record cash, bank transfer or cheque collected off-platform (US-020)."""
    payment = await payment_service.record_cash_payment(
        db,
        context,
        tenancy_id=payload.tenancy_id,
        amount=payload.amount,
        payment_date=payload.payment_date,
        method=payload.method,
        notes=payload.notes,
        reference=payload.reference,
        request=request,
    )
    reloaded = assert_in_org(
        await db.scalar(
            select(Payment).options(selectinload(Payment.receipt)).where(Payment.id == payment.id)
        ),
        context,
        label="payment",
    )
    return await _payment_detail(db, reloaded)


@payments_router.get("", response_model=list[PaymentDetail])
async def list_payments(
    tenancy_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    payment_status: PaymentStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.PAYMENT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[PaymentDetail]:
    rows = await payment_service.list_payments(
        db,
        context,
        tenancy_id=tenancy_id,
        property_id=property_id,
        payment_status=payment_status,
        limit=limit,
    )
    return await _payment_details(db, rows)


@payments_router.get("/{payment_id}", response_model=PaymentDetail)
async def get_payment(
    payment_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.PAYMENT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> PaymentDetail:
    payment = assert_in_org(
        await db.scalar(
            select(Payment).options(selectinload(Payment.receipt)).where(Payment.id == payment_id)
        ),
        context,
        label="payment",
    )
    return await _payment_detail(db, payment)


@payments_router.post("/stk-push", response_model=StkPushResponse, status_code=status.HTTP_202_ACCEPTED)
async def stk_push(
    payload: StkPushRequest,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PAYMENT_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> StkPushResponse:
    """Prompt the tenant's phone for their M-Pesa PIN (US-019)."""
    payment, message = await payment_service.initiate_stk_push(
        db,
        context,
        tenancy_id=payload.tenancy_id,
        amount=payload.amount,
        phone_number=payload.phone_number,
        request=request,
    )
    return StkPushResponse(payment=PaymentRead.model_validate(payment), message=message)


@payments_router.get("/{payment_id}/status", response_model=PaymentDetail)
async def poll_payment_status(
    payment_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.PAYMENT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> PaymentDetail:
    """Poll Daraja for a pending push — the safety net when a callback is lost."""
    await payment_service.poll_status(db, context, payment_id)
    payment = assert_in_org(
        await db.scalar(
            select(Payment).options(selectinload(Payment.receipt)).where(Payment.id == payment_id)
        ),
        context,
        label="payment",
    )
    return await _payment_detail(db, payment)


# ------------------------------------------------------------------ M-Pesa webhook


@mpesa_router.post("/callback")
async def mpesa_callback(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Daraja's STK callback.

    Unauthenticated by necessity — Safaricom calls it. Every result is answered
    with a 200 and `ResultCode: 0`, because a non-200 makes Daraja retry
    indefinitely; the body says what we actually did.
    """
    body = await request.json()
    outcome = await payment_service.handle_callback(db, body)
    return {"ResultCode": "0", "ResultDesc": "Accepted", "detail": outcome}


@mpesa_router.post("/b2c/result")
async def mpesa_b2c_result(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Daraja's B2C result callback — the outcome of an owner disbursement payout.

    Same contract as the STK callback: unauthenticated, always answered 200, and
    idempotent, because Safaricom re-delivers a result it thinks we missed.
    """
    body = await request.json()
    try:
        result = mpesa_service.parse_b2c_result(body)
    except mpesa_service.MpesaError as exc:
        return {"ResultCode": "0", "ResultDesc": "Accepted", "detail": str(exc)}

    if not await mpesa_service.claim_b2c_result(result.conversation_id):
        return {"ResultCode": "0", "ResultDesc": "Accepted", "detail": "duplicate"}

    disbursement = await agency_service.handle_b2c_result(db, result)
    detail = "settled" if disbursement is not None else "no matching disbursement"
    return {"ResultCode": "0", "ResultDesc": "Accepted", "detail": detail}


@mpesa_router.post("/b2c/timeout")
async def mpesa_b2c_timeout(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Daraja queue timeout — the payout never reached the payment engine."""
    body = await request.json()
    conversation_id = str(body.get("ConversationID") or body.get("Result", {}).get("ConversationID") or "")
    if conversation_id:
        await agency_service.fail_pending_payout(
            db, conversation_id, "M-Pesa timed out before processing the payout"
        )
    return {"ResultCode": "0", "ResultDesc": "Accepted"}


# ------------------------------------------------------------------ demand letters


@arrears_router.post("/demand-letters/{tenancy_id}")
async def issue_demand_letter(
    tenancy_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.ARREARS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Issue a formal demand, file it in the tenant's vault and send it to them."""
    return await demand_letter_service.issue_for_tenancy(db, context, tenancy_id)


@arrears_router.get("/demand-letters/{tenancy_id}/preview")
async def preview_demand_letter(
    tenancy_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.ARREARS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the letter without filing or sending it, so it can be read first."""
    pdf_bytes = await demand_letter_service.preview_for_tenancy(db, context, tenancy_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="demand-letter-preview.pdf"'},
    )


# ------------------------------------------------------------------------- arrears


def _buckets(values: dict[str, Decimal]) -> AgingBuckets:
    return AgingBuckets(
        current=values["current"],
        days_1_30=values["days_1_30"],
        days_31_60=values["days_31_60"],
        days_61_90=values["days_61_90"],
        days_90_plus=values["days_90_plus"],
    )


@arrears_router.get("", response_model=ArrearsReport)
async def arrears_report(
    property_id: uuid.UUID | None = None,
    min_amount: Decimal = Query(default=Decimal("0"), ge=0),
    context: OrgContext = Depends(require(Permission.ARREARS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ArrearsReport:
    summary = await arrears_service.build_report(db, context, property_id=property_id, min_amount=min_amount)
    return ArrearsReport(
        total_arrears=summary.total_arrears,
        tenants_in_arrears=summary.tenants_in_arrears,
        aging=_buckets(summary.aging),
        rows=[
            ArrearsRowRead(
                tenant_id=row.tenant_id,
                tenant_name=row.tenant_name,
                tenant_phone=row.tenant_phone,
                tenancy_id=row.tenancy_id,
                tenancy_reference=row.tenancy_reference,
                unit_number=row.unit_number,
                property_id=row.property_id,
                property_name=row.property_name,
                amount_owed=row.amount_owed,
                days_overdue=row.days_overdue,
                bucket=row.bucket,
                oldest_due_date=row.oldest_due_date,
                last_payment_date=row.last_payment_date,
                invoice_count=row.invoice_count,
                aging=_buckets(row.aging),
            )
            for row in summary.rows
        ],
    )


@arrears_router.get("/export.csv")
async def export_arrears_csv(
    property_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require(Permission.ARREARS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    summary = await arrears_service.build_report(db, context, property_id=property_id)
    filename = f"arrears-{date.today().isoformat()}.csv"
    return Response(
        content=arrears_service.to_csv(summary),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@arrears_router.post("/remind", response_model=SendRemindersResponse)
async def send_reminders(
    payload: SendRemindersRequest,
    context: OrgContext = Depends(require_write(Permission.ARREARS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> SendRemindersResponse:
    """One-click reminder to a chosen defaulter, or to all of them (US-022)."""
    summary = await arrears_service.build_report(db, context, property_id=payload.property_id)
    targets = (
        [row for row in summary.rows if row.tenancy_id in set(payload.tenancy_ids)]
        if payload.tenancy_ids
        else summary.rows
    )

    sent = 0
    for row in targets:
        tenant = await db.get(Tenant, row.tenant_id)
        if tenant is None:
            continue
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_tenant(tenant),
            notification_type=NotificationType.RENT_REMINDER,
            title="Outstanding rent balance",
            body=(
                f"Dear {tenant.full_name.split()[0]}, your balance for unit {row.unit_number} at "
                f"{row.property_name} is KES {format_kes(row.amount_owed)}, "
                f"{row.days_overdue} day(s) overdue. Please settle it at your earliest convenience."
            ),
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
            entity_type="tenancy",
            entity_id=row.tenancy_id,
            organization_id=context.organization_id,
        )
        sent += 1

    await db.commit()
    return SendRemindersResponse(sent=sent, message=f"Reminder sent to {sent} tenant(s)")
