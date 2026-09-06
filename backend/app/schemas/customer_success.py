import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.customer_success import (
    FeatureRequestStatus,
    HealthTrend,
    MilestoneKey,
    NpsTrigger,
    ReferralStatus,
    SupportRequestStatus,
)
from app.models.organization import SubscriptionPlan


class OnboardingProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    added_property: bool
    added_units: bool
    invited_caretaker: bool
    added_tenant: bool
    setup_payment: bool
    dismissed_at: datetime | None
    completed_at: datetime | None


class OnboardingStepUpdate(BaseModel):
    step: str = Field(pattern="^(added_property|added_units|invited_caretaker|added_tenant|setup_payment)$")


class HelpArticleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    body: str
    category: str
    is_published: bool
    created_at: datetime


class HelpArticleWrite(BaseModel):
    slug: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=2, max_length=255)
    body: str = Field(min_length=1)
    category: str = Field(min_length=2, max_length=100)
    is_published: bool = True


class SupportRequestCreate(BaseModel):
    subject: str = Field(min_length=2, max_length=255)
    message: str = Field(min_length=1, max_length=5000)


class SupportRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: str
    message: str
    status: SupportRequestStatus
    created_at: datetime


class ReferralRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    referred_email: str
    status: ReferralStatus
    credit_granted_at: datetime | None
    created_at: datetime


class ReferralCreate(BaseModel):
    referred_email: str = Field(min_length=5, max_length=255)


class ReferralSummary(BaseModel):
    code: str
    referral_link: str
    credit_months: int
    referrals: list[ReferralRead]


class OrganizationPlanUpdate(BaseModel):
    plan: SubscriptionPlan


class NpsPendingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger_event: NpsTrigger


class NpsResponseCreate(BaseModel):
    score: int = Field(ge=0, le=10)
    comment: str | None = Field(default=None, max_length=2000)


class MilestoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    milestone_key: MilestoneKey
    reached_at: datetime
    acknowledged_at: datetime | None


class FeatureRequestRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    status: FeatureRequestStatus
    vote_count: int
    voted_by_me: bool
    created_at: datetime


class FeatureRequestCreate(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    description: str = Field(min_length=4, max_length=4000)


class ChangelogEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    published_at: datetime


class ChangelogEntryWrite(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=1)
    is_published: bool = True


class OrganizationHealthScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    week_of: date
    score: int
    login_score: int
    payment_score: int
    adoption_score: int
    caretaker_score: int
    portal_score: int
    support_score: int
    trend: HealthTrend


class OrganizationHealthSummary(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    latest_score: int | None
    trend: HealthTrend | None
    week_of: date | None
    is_at_risk: bool


class CustomerSuccessAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    score: int
    triggered_at: datetime
    acknowledged_at: datetime | None
