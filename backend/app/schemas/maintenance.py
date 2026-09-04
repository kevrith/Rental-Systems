"""Request bodies for the maintenance lifecycle actions (Sprint 13).

Each action is its own schema rather than one loose `PATCH` body: an approval
and a rejection require different fields, and making that explicit is what stops
a request being "rejected" with no reason attached.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.operations import RejectionReason


class MaintenanceApprove(BaseModel):
    estimated_cost: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    expected_completion_date: date | None = None
    # Approving and assigning in one step — the common case when the owner
    # already knows who they are sending.
    vendor_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _due_date_not_in_the_past(self) -> "MaintenanceApprove":
        if self.expected_completion_date and self.expected_completion_date < date.today():
            raise ValueError("Expected completion date cannot be in the past")
        return self


class MaintenanceReject(BaseModel):
    reason: RejectionReason
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _note_required_for_other(self) -> "MaintenanceReject":
        if self.reason == RejectionReason.OTHER and not (self.note or "").strip():
            raise ValueError("Tell the reporter why — a note is required when the reason is 'other'")
        return self


class MaintenanceInfoRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000)


class MaintenanceAssign(BaseModel):
    vendor_id: uuid.UUID
    estimated_cost: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    expected_completion_date: date | None = None

    @model_validator(mode="after")
    def _due_date_not_in_the_past(self) -> "MaintenanceAssign":
        if self.expected_completion_date and self.expected_completion_date < date.today():
            raise ValueError("Expected completion date cannot be in the past")
        return self


class MaintenanceComplete(BaseModel):
    actual_cost: Decimal = Field(ge=0, le=Decimal("99999999.99"))
    resolution_notes: str | None = Field(default=None, max_length=4000)
    vendor_rating: int | None = Field(default=None, ge=1, le=5)
    vendor_review: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _review_needs_a_rating(self) -> "MaintenanceComplete":
        if self.vendor_review and self.vendor_rating is None:
            raise ValueError("Give the vendor a star rating alongside your review")
        return self


class MaintenanceCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class MaintenanceRate(BaseModel):
    """The tenant's feedback on a finished job (US-063)."""

    rating: int = Field(ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=2000)


class PropertyMaintenanceBudget(BaseModel):
    monthly_budget: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))


class VendorSummary(BaseModel):
    id: uuid.UUID
    name: str
    phone_number: str
    average_rating: float | None = None
    jobs_completed: int = 0


class MaintenanceTimelineEntry(BaseModel):
    action: str
    summary: str
    actor_name: str | None = None
    occurred_at: datetime
