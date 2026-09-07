"""Onboarding, in-app help, customer health, referrals, NPS, milestones, the
feature board and the changelog (Sprint 20).

Three tables here carry no `organization_id` at all: `HelpArticle`,
`FeatureRequest`/`FeatureVote`, and `ChangelogEntry`. They are the same content
for every customer — the same treatment `TaskRun` already gets — so they sit
outside the RLS registry rather than being scoped to a tenant that doesn't
apply to them. Everything else here belongs to one organisation.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class HealthTrend(str, enum.Enum):
    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"


class ReferralStatus(str, enum.Enum):
    PENDING = "pending"
    SIGNED_UP = "signed_up"
    CONVERTED = "converted"


class SupportRequestStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class NpsTrigger(str, enum.Enum):
    FIRST_PAYMENT = "first_payment"
    FIRST_INSPECTION = "first_inspection"
    FIRST_MONTH = "first_month"


class MilestoneKey(str, enum.Enum):
    PAYMENTS_100 = "payments_100"
    TENANTS_50 = "tenants_50"
    FIRST_ETIMS_RECEIPT = "first_etims_receipt"


class FeatureRequestStatus(str, enum.Enum):
    OPEN = "open"
    PLANNED = "planned"
    SHIPPED = "shipped"
    DECLINED = "declined"


class OnboardingProgress(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per organisation (US-089). Steps can be completed in any order,
    so each is its own flag rather than a single 'current step' pointer."""

    __tablename__ = "onboarding_progress"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_onboarding_progress_organization"),)

    added_property: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    added_units: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invited_caretaker: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    added_tenant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    setup_payment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HelpArticle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Contextual help content (US-090). Platform-wide — every organisation
    reads the same knowledge base, managed by RentFlow staff."""

    __tablename__ = "help_articles"

    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Video tutorial (US-090, Module 24). An article may be text, video, or both
    # — `body` stays required so a video article is still searchable and still
    # usable on a metered connection, which is most of this product's audience.
    video_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    video_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Where the video is hosted, e.g. "youtube" or "vimeo" — the player the
    # frontend embeds is chosen from this rather than parsed out of the URL.
    video_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class OrganizationHealthScore(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A weekly snapshot (US-091). Component scores are each 0-100 before their
    weight is applied; `score` is the already-weighted 0-100 total."""

    __tablename__ = "organization_health_scores"
    __table_args__ = (
        UniqueConstraint("organization_id", "week_of", name="uq_health_score_organization_week"),
    )

    week_of: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    login_score: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_score: Mapped[int] = mapped_column(Integer, nullable=False)
    adoption_score: Mapped[int] = mapped_column(Integer, nullable=False)
    caretaker_score: Mapped[int] = mapped_column(Integer, nullable=False)
    portal_score: Mapped[int] = mapped_column(Integer, nullable=False)
    support_score: Mapped[int] = mapped_column(Integer, nullable=False)
    trend: Mapped[HealthTrend] = mapped_column(
        Enum(HealthTrend, name="health_trend"), default=HealthTrend.STABLE, nullable=False
    )


class CustomerSuccessAlert(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Raised when a weekly score drops below the at-risk threshold (US-091)."""

    __tablename__ = "customer_success_alerts"

    health_score_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_health_scores.id", ondelete="SET NULL"), nullable=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ReferralCode(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One shareable code per organisation (US-092)."""

    __tablename__ = "referral_codes"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_referral_code_organization"),)

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)


class Referral(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """`organization_id` is the referrer. `referred_organization_id` fills in
    once the referred signup completes registration."""

    __tablename__ = "referrals"

    referral_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("referral_codes.id", ondelete="CASCADE"), nullable=False
    )
    referred_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    referred_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ReferralStatus] = mapped_column(
        Enum(ReferralStatus, name="referral_status"), default=ReferralStatus.PENDING, nullable=False
    )
    credit_granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SupportRequest(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A contact-support message, emailed to the RentFlow team (US-090)."""

    __tablename__ = "support_requests"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SupportRequestStatus] = mapped_column(
        Enum(SupportRequestStatus, name="support_request_status"),
        default=SupportRequestStatus.OPEN,
        nullable=False,
    )


class NpsSurveyPrompt(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One eligibility/response record per user per milestone trigger (US-092)."""

    __tablename__ = "nps_survey_prompts"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "trigger_event", name="uq_nps_prompt_user_trigger"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    trigger_event: Mapped[NpsTrigger] = mapped_column(Enum(NpsTrigger, name="nps_trigger"), nullable=False)
    shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class MilestoneEvent(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A per-organisation milestone, reached at most once (US-092)."""

    __tablename__ = "milestone_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "milestone_key", name="uq_milestone_organization_key"),
    )

    milestone_key: Mapped[MilestoneKey] = mapped_column(
        Enum(MilestoneKey, name="milestone_key"), nullable=False
    )
    reached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeatureRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A customer-submitted idea on the shared, platform-wide voting board
    (US-092)."""

    __tablename__ = "feature_requests"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[FeatureRequestStatus] = mapped_column(
        Enum(FeatureRequestStatus, name="feature_request_status"),
        default=FeatureRequestStatus.OPEN,
        nullable=False,
    )


class FeatureVote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_votes"
    __table_args__ = (UniqueConstraint("feature_request_id", "user_id", name="uq_feature_vote_user"),)

    feature_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feature_requests.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class ChangelogEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A platform-wide announcement shown on login (US-092)."""

    __tablename__ = "changelog_entries"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
