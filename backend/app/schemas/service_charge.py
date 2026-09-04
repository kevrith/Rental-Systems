import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.service_charge import (
    Apportionment,
    ServiceChargeCategory,
    SinkingFundMovement,
)


class BudgetLine(BaseModel):
    category: ServiceChargeCategory
    monthly_budget: Decimal = Field(ge=0, le=Decimal("99999999.99"))
    notes: str | None = Field(default=None, max_length=500)


class SchemeUpsert(BaseModel):
    name: str = Field(default="Service charge", min_length=2, max_length=255)
    apportionment: Apportionment = Apportionment.FIXED_PER_UNIT
    fixed_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    monthly_pool: Decimal = Field(default=Decimal("0.00"), ge=0)
    sinking_fund_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=50)
    is_active: bool = True
    bill_with_rent: bool = True
    notes: str | None = Field(default=None, max_length=2000)
    # Omit to leave the budget untouched; send a list to replace it wholesale.
    budgets: list[BudgetLine] | None = None

    @model_validator(mode="after")
    def _amount_matches_method(self) -> "SchemeUpsert":
        if self.apportionment == Apportionment.FIXED_PER_UNIT and self.fixed_amount <= 0:
            raise ValueError("A fixed charge needs an amount per unit")
        if self.apportionment != Apportionment.FIXED_PER_UNIT and self.monthly_pool <= 0:
            raise ValueError("A proportional charge needs the building's monthly pool")
        return self


class SchemeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    property_id: uuid.UUID
    name: str
    apportionment: Apportionment
    fixed_amount: Decimal
    monthly_pool: Decimal
    sinking_fund_percent: Decimal
    is_active: bool
    bill_with_rent: bool
    notes: str | None
    created_at: datetime


class UnitCharge(BaseModel):
    unit_id: str
    unit_number: str
    size_sqm: float | None
    occupied: bool
    monthly_charge: float


class SchemeDetail(SchemeRead):
    property_name: str | None = None
    budgets: list[BudgetLine] = []
    monthly_total: float = 0
    sinking_fund_balance: float = 0
    units: list[UnitCharge] = []


class ExpenseCreate(BaseModel):
    category: ServiceChargeCategory
    amount: Decimal = Field(gt=0, le=Decimal("99999999.99"))
    incurred_on: date
    description: str = Field(min_length=3, max_length=512)
    vendor_id: uuid.UUID | None = None
    receipt_file_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _not_in_the_future(self) -> "ExpenseCreate":
        if self.incurred_on > date.today():
            raise ValueError("An expense cannot be dated in the future")
        return self


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: ServiceChargeCategory
    amount: Decimal
    incurred_on: date
    description: str
    vendor_id: uuid.UUID | None
    receipt_file_id: uuid.UUID | None
    created_at: datetime


class SinkingFundEntryCreate(BaseModel):
    movement: SinkingFundMovement
    amount: Decimal = Field(gt=0, le=Decimal("99999999.99"))
    entry_date: date
    description: str = Field(min_length=3, max_length=512)


class SinkingFundEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    movement: SinkingFundMovement
    amount: Decimal
    entry_date: date
    description: str
    billing_period: date | None
    created_at: datetime
