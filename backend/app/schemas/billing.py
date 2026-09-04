import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.billing import InvoiceStatus, LineItemKind, PaymentMethod, PaymentStatus


class LineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: LineItemKind
    description: str
    quantity: Decimal
    unit_amount: Decimal
    amount: Decimal


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    reference_code: str
    tenancy_id: uuid.UUID
    period_start: date
    period_end: date
    issue_date: date
    due_date: date
    total: Decimal
    amount_paid: Decimal
    status: InvoiceStatus
    document_id: uuid.UUID | None
    created_at: datetime


class InvoiceDetail(InvoiceRead):
    balance: Decimal
    line_items: list[LineItemRead] = []
    tenant_name: str | None = None
    unit_number: str | None = None
    property_name: str | None = None
    document_url: str | None = None


class GenerateInvoiceRequest(BaseModel):
    tenancy_id: uuid.UUID
    issue_date: date | None = None


class RecordPaymentRequest(BaseModel):
    tenancy_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    payment_date: date
    method: PaymentMethod = PaymentMethod.CASH
    reference: str | None = Field(default=None, max_length=64, description="M-Pesa or bank reference")
    notes: str | None = Field(default=None, max_length=1000)


class StkPushRequest(BaseModel):
    tenancy_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    phone_number: str | None = Field(default=None, max_length=32)


class ReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference_code: str
    issued_at: datetime
    signature: str
    balance_after: Decimal
    document_id: uuid.UUID | None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    reference_code: str
    tenancy_id: uuid.UUID
    invoice_id: uuid.UUID | None
    amount: Decimal
    method: PaymentMethod
    status: PaymentStatus
    mpesa_receipt: str | None
    phone_number: str | None
    failure_reason: str | None
    paid_at: datetime | None
    payment_date: date | None
    notes: str | None
    created_at: datetime


class PaymentDetail(PaymentRead):
    tenant_name: str | None = None
    unit_number: str | None = None
    property_name: str | None = None
    receipt: ReceiptRead | None = None
    receipt_url: str | None = None
    recorded_by_name: str | None = None


class StkPushResponse(BaseModel):
    payment: PaymentRead
    message: str


# ------------------------------------------------------------------------ arrears


class AgingBuckets(BaseModel):
    current: Decimal
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_90_plus: Decimal


class ArrearsRowRead(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    tenant_phone: str
    tenancy_id: uuid.UUID
    tenancy_reference: str
    unit_number: str
    property_id: uuid.UUID
    property_name: str
    amount_owed: Decimal
    days_overdue: int
    bucket: str
    oldest_due_date: date | None
    last_payment_date: date | None
    invoice_count: int
    aging: AgingBuckets


class ArrearsReport(BaseModel):
    total_arrears: Decimal
    tenants_in_arrears: int
    aging: AgingBuckets
    rows: list[ArrearsRowRead]


class SendRemindersRequest(BaseModel):
    tenancy_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Empty means every tenant in arrears"
    )
    property_id: uuid.UUID | None = None


class SendRemindersResponse(BaseModel):
    sent: int
    message: str
