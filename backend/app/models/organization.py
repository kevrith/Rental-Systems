import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User  # lgtm[py/unsafe-cyclic-import]


class OperatingMode(str, enum.Enum):
    OWNER = "owner"
    AGENCY = "agency"


class SubscriptionPlan(str, enum.Enum):
    TRIAL = "trial"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class MpesaCollectionMode(str, enum.Enum):
    """How rent reaches this landlord, which decides how much RentFlow can automate.

    The three are not a maturity ladder — they are three real situations in this
    market, and the product has to be useful in all of them:

    AUTOMATED  the landlord has a paybill/till *and* Daraja API credentials, so
               RentFlow can push an STK prompt and confirm the payment itself.
               Everything reconciles without anyone typing.
    PAYBILL    they have a shortcode but no API credentials. Tenants are shown
               the paybill and account number to pay; someone records what came
               in, or it is matched from a statement.
    MANUAL     a personal M-Pesa number and nothing else, which is most small
               landlords. No API exists for this, so the payment is recorded by
               hand or from the forwarded confirmation SMS.
    """

    AUTOMATED = "automated"
    PAYBILL = "paybill"
    MANUAL = "manual"


class ReportDeliveryChannel(str, enum.Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    BOTH = "both"


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The top-level SaaS tenant. Every piece of data is scoped to an organization."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    operating_mode: Mapped[OperatingMode] = mapped_column(
        Enum(OperatingMode, name="operating_mode"), default=OperatingMode.OWNER
    )
    subscription_plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan"), default=SubscriptionPlan.TRIAL
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When dunning gave up on a paid subscription. Cleared the moment a charge
    # succeeds, so paying a late invoice restores writing immediately.
    subscription_lapsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Branding, used on leases, invoices and receipts (US-016, US-023).
    logo_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kra_pin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    letterhead_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Operational defaults
    default_caretaker_cash_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    default_billing_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Lease renewal defaults (US-057). A renewal offered automatically uses these,
    # so a landlord sets their annual uplift once rather than per tenancy.
    renewal_rent_increase_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default="0.00", nullable=False
    )
    renewal_term_months: Mapped[int] = mapped_column(Integer, default=12, server_default="12", nullable=False)
    # Renewals go out automatically unless a landlord would rather do it by hand.
    auto_offer_renewals: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    # Highest trial reminder already sent (7, 3 or 1) so Celery Beat never repeats one.
    trial_reminder_sent_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Public API (Sprint 19). None means "use the platform default" — only an
    # enterprise plan gets a bespoke ceiling.
    api_rate_limit_per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Referral credit (Sprint 20, US-092). Months of free subscription owed to
    # this organisation for referrals that converted. There is no billing engine
    # yet to draw this down against an invoice — it is a ledger waiting for one.
    credit_months: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    # Sprint 21 (US-093): where the automatic monthly summary report is sent.
    report_delivery_channel: Mapped[ReportDeliveryChannel] = mapped_column(
        Enum(ReportDeliveryChannel, name="report_delivery_channel"),
        default=ReportDeliveryChannel.BOTH,
        server_default="BOTH",
        nullable=False,
    )

    # Sprint 22 (US-098): login restricted to these IPs/CIDR ranges. Empty means
    # unrestricted — every account starts open, an enterprise account opts in.
    ip_whitelist: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    # Sprint 22 (US-098): role value -> minutes, overriding
    # `DEFAULT_INACTIVITY_TIMEOUT_MINUTES` for every user of that role in this
    # organization. Applied immediately to existing users when saved — this is
    # an organisation-imposed policy, not a per-user preference.
    role_session_timeouts: Mapped[dict[str, int]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # Sprint 22 (US-097): fraud detection thresholds, configurable per organisation.
    fraud_max_cash_payments_per_window: Mapped[int] = mapped_column(
        Integer, default=5, server_default="5", nullable=False
    )
    fraud_cash_window_minutes: Mapped[int] = mapped_column(
        Integer, default=30, server_default="30", nullable=False
    )
    # A payment more than this many times the tenancy's rent, or less than
    # 1/this many times it, is flagged as an unusual amount.
    fraud_unusual_amount_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("3.00"), server_default="3.00", nullable=False
    )

    # Sprint 23 (US-101): bank transfer instructions shown to a tenant in the
    # portal. All optional — a landlord who never fills these in simply never
    # shows the "pay by bank transfer" option.
    bank_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bank_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bank_branch: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # --- M-Pesa collection ---
    #
    # Rent is collected by the landlord, into the landlord's own M-Pesa. RentFlow
    # never touches it: no pooled shortcode, no float, no waiting on a payout.
    # What the platform does is prompt, confirm, receipt and reconcile — the work
    # that was manual before.
    #
    # Which of those is possible depends on what the landlord actually has, and
    # in this market that is three different situations (see `MpesaCollectionMode`).
    mpesa_collection_mode: Mapped["MpesaCollectionMode"] = mapped_column(
        Enum(MpesaCollectionMode, name="mpesa_collection_mode"),
        default=MpesaCollectionMode.MANUAL,
        server_default="MANUAL",
        nullable=False,
    )
    # The paybill/till a tenant pays, or the phone number for a landlord who has
    # neither. Shown to tenants in the portal either way.
    mpesa_shortcode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    mpesa_phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mpesa_account_label: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Daraja API credentials, present only in AUTOMATED mode. Encrypted with the
    # organisation's own key — these move that landlord's money, and a leak of
    # the table must not be a leak of every customer's till.
    daraja_consumer_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    daraja_consumer_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    daraja_passkey_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Safaricom issues sandbox and production credentials separately.
    daraja_environment: Mapped[str] = mapped_column(
        String(16), default="sandbox", server_default="sandbox", nullable=False
    )
    mpesa_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # B2C, for an agency paying its owner clients out of its own till. Separate
    # Safaricom credentials from collection, and optional: without them the
    # agency records payouts it made itself instead of RentFlow sending them.
    daraja_initiator_name_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    daraja_security_credential_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sprint 26 (Module 25): suspension. `is_active` is what `deps.get_org_context`
    # already enforces; these three record *why* it was flipped and by whom, so a
    # suspension is a reversible, auditable act rather than a silent boolean.
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suspended_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Cash above this figure is recorded but held PENDING until a second person
    # approves it (masterplan, Fraud Prevention). None means off, which is what
    # every existing account gets — turning a money-handling gate on silently
    # would strand payments no one knew to go and approve.
    cash_dual_approval_threshold: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Most live logins one user may hold at once. None falls back to
    # `settings.MAX_CONCURRENT_SESSIONS_PER_USER`; the oldest session is revoked
    # when a new login would exceed the cap.
    max_concurrent_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # A demo organisation is seeded with fabricated portfolio data (Module 24).
    # Nothing in it is real, so it is excluded from platform health scoring and
    # billing, and the UI can label it plainly.
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    # Sprint 26A, item 14: scheduled Parquet drops for an enterprise
    # customer's own analytics/warehouse team. Off by default — most
    # customers have no data team to hand a Parquet file to, so this is an
    # explicit opt-in rather than an extra background job every organisation
    # pays the cost of. See `app/services/export_service.run_bi_exports`.
    bi_export_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    # Document vault storage cap, in bytes. Null means "use the plan default"
    # (see `vault_service.PLAN_STORAGE_LIMITS_GB`) — this column exists only
    # to hold Enterprise's negotiated custom figure, which has no single
    # platform-wide default to fall back to. Platform-staff-set only
    # (`PATCH /internal/organizations/{id}/plan`); never exposed on the
    # customer-facing organization-settings update, since a customer setting
    # their own storage cap would defeat the point of having one.
    storage_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # `foreign_keys` is explicit because `suspended_by_id` above adds a second
    # foreign key between these two tables, and without it SQLAlchemy cannot
    # tell which one this relationship travels.
    users: Mapped[list["User"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
        foreign_keys="User.organization_id",
    )

    @property
    def is_trial_expired(self) -> bool:
        """True once a trial organization is past its end date.

        Expired trials drop to read-only rather than losing access — the owner's
        data stays visible behind an upgrade prompt (US-006).
        """
        if self.subscription_plan != SubscriptionPlan.TRIAL or self.trial_ends_at is None:
            return False
        return datetime.now(self.trial_ends_at.tzinfo) > self.trial_ends_at

    # Set by the subscription biller when dunning runs out (Sprint 27). A column
    # rather than a join so the write-gate on every request stays a single row
    # read, and so a lapse survives the subscription row being changed.
    @property
    def is_read_only(self) -> bool:
        """True when the account may be read but not written to.

        Two roads lead here — a trial that ran out and a subscription that went
        unpaid past its grace window — and both keep every record intact.
        """
        return self.is_trial_expired or self.subscription_lapsed_at is not None


class OrganizationEncryptionKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A per-organisation data encryption key, itself stored encrypted.

    Envelope encryption (masterplan, Multi-Tenant Data Isolation). The master
    key still derives from `SECRET_KEY` — there is no KMS in this deployment —
    but the material that actually encrypts a customer's third-party
    credentials is unique per organisation and rotatable on its own. What that
    buys, concretely: rotating one customer's key after a suspected compromise
    no longer forces every other customer to re-enter their credentials, and a
    leaked ciphertext from one tenant is useless against another's.

    Deliberately not `OrgScopedMixin`: RLS keys off `organization_id` for
    tenant reads, and this table is only ever touched by the server's own
    crypto path, never by a request-scoped query on a tenant's behalf.
    """

    __tablename__ = "organization_encryption_keys"
    __table_args__ = (UniqueConstraint("organization_id", "version", name="uq_org_encryption_key_version"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # The organisation's Fernet key, encrypted under the master key.
    wrapped_key: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
