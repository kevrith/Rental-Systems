"""Security hardening and fraud detection (Sprint 22, US-097/098).

`SecurityEvent` is a narrower, higher-volume cousin of `AuditLog`: it captures
authentication noise (a failed password, a login blocked by the IP whitelist)
that would otherwise have nowhere to live — `AuditLog` only ever records
privileged, successful actions. It exists so the daily failed-login digest has
something durable to aggregate; the Redis lockout counter in `auth_service`
is ephemeral and only long enough to enforce the lockout itself.

`FraudAlert` is one flagged pattern on one payment event. `pattern_key` is a
stable string per (rule, subject) — e.g. `rapid_cash:<user_id>` — used both to
avoid re-alerting on the same pattern every few minutes and to let an owner
suppress a pattern permanently once they have confirmed it is legitimate
(`FraudSuppression`).
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SecurityEventType(str, enum.Enum):
    LOGIN_FAILED = "login_failed"
    LOGIN_BLOCKED_IP = "login_blocked_ip"


class SecurityEvent(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One authentication-security occurrence, for the daily digest (US-098)."""

    __tablename__ = "security_events"

    event_type: Mapped[SecurityEventType] = mapped_column(
        Enum(SecurityEventType, name="security_event_type"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)


class FraudAlertType(str, enum.Enum):
    RAPID_CASH_PAYMENTS = "rapid_cash_payments"
    OFF_HOURS_ACTIVITY = "off_hours_activity"
    UNUSUAL_AMOUNT = "unusual_amount"
    VELOCITY_DUPLICATE = "velocity_duplicate"


class FraudAlertStatus(str, enum.Enum):
    OPEN = "open"
    SUPPRESSED = "suppressed"
    RESOLVED = "resolved"


class FraudAlert(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One suspicious pattern flagged on one payment event (US-097)."""

    __tablename__ = "fraud_alerts"

    alert_type: Mapped[FraudAlertType] = mapped_column(
        Enum(FraudAlertType, name="fraud_alert_type"), nullable=False, index=True
    )
    pattern_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[FraudAlertStatus] = mapped_column(
        Enum(FraudAlertStatus, name="fraud_alert_status"),
        default=FraudAlertStatus.OPEN,
        nullable=False,
        index=True,
    )
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FraudSuppression(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An owner's standing 'this pattern is legitimate' decision. Future alerts
    matching `pattern_key` for this organisation are never raised again."""

    __tablename__ = "fraud_suppressions"

    pattern_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "pattern_key", name="uq_fraud_suppression_org_pattern"),
    )


class BreachCategory(str, enum.Enum):
    """The shapes of incident the Kenya Data Protection Act, 2019 s.43 expects
    a data controller to be able to describe when it notifies."""

    UNAUTHORISED_ACCESS = "unauthorised_access"
    CREDENTIAL_COMPROMISE = "credential_compromise"
    DATA_EXFILTRATION = "data_exfiltration"
    ACCIDENTAL_DISCLOSURE = "accidental_disclosure"
    SYSTEM_COMPROMISE = "system_compromise"
    LOST_DEVICE = "lost_device"
    THIRD_PARTY_PROCESSOR = "third_party_processor"


class BreachSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BreachStatus(str, enum.Enum):
    """`NOTIFIED` is a distinct terminal-ish state from `CLOSED` on purpose: the
    regulator having been told is the legally significant event, and it happens
    well before the investigation and remediation are finished."""

    DETECTED = "detected"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    NOTIFIED = "notified"
    CLOSED = "closed"
    DISMISSED = "dismissed"


# Section 43 of the Act gives a controller 72 hours from becoming aware of a
# breach to notify the Data Commissioner.
BREACH_NOTIFICATION_WINDOW_HOURS = 72

# Breaches at or above this severity are presumed notifiable. Anything below it
# still gets a clock and still has to be dismissed explicitly with a reason —
# the decision not to notify is itself a decision that has to be on the record.
NOTIFIABLE_SEVERITIES: tuple[BreachSeverity, ...] = (BreachSeverity.HIGH, BreachSeverity.CRITICAL)


class SecurityBreach(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A personal-data breach and the 72-hour clock it starts (Kenya DPA s.43).

    Platform-level rather than organisation-scoped, like `TaskRun`: one
    incident routinely touches several customers at once, and the party who has
    to notify the Data Commissioner is RentFlow, not the landlord. Which
    customers were affected is a list on the row (`affected_organization_ids`),
    and every one of them gets told — a landlord is the controller for their
    own tenants' data and has their own duty to those tenants.

    Detection is partly automatic (`breach_service.scan_for_candidates` raises
    a DETECTED row from authentication and export telemetry) and partly manual,
    because most real breaches are reported by a human, not noticed by a query.
    Both paths land here, and neither can close a row without saying what was
    done about it.
    """

    __tablename__ = "security_breaches"

    reference_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)

    category: Mapped[BreachCategory] = mapped_column(
        Enum(BreachCategory, name="breach_category"), nullable=False
    )
    severity: Mapped[BreachSeverity] = mapped_column(
        Enum(BreachSeverity, name="breach_severity"),
        default=BreachSeverity.MEDIUM,
        nullable=False,
        index=True,
    )
    status: Mapped[BreachStatus] = mapped_column(
        Enum(BreachStatus, name="breach_status"),
        default=BreachStatus.DETECTED,
        nullable=False,
        index=True,
    )

    summary: Mapped[str] = mapped_column(String(512), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # When RentFlow became aware — which starts the clock, and is not the same
    # as when the breach happened.
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notification_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    affected_organization_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    affected_subject_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_categories: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)

    # Raised by a detector rather than a person; names the rule that fired.
    detector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Stable key for the pattern, so a detector re-running does not open a
    # second row for an incident already on the board.
    pattern_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    reported_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    contained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    containment_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- notification, the part with the legal deadline on it ---
    regulator_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    regulator_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    customers_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subjects_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Why no notification was made, when that is the decision. Required to
    # dismiss a row.
    no_notification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    remediation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Highest escalation reminder already sent (48 or 72), so the hourly sweep
    # never repeats one.
    escalation_sent_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def is_notifiable(self) -> bool:
        return self.severity in NOTIFIABLE_SEVERITIES

    @property
    def is_open(self) -> bool:
        return self.status not in (BreachStatus.CLOSED, BreachStatus.DISMISSED)

    def hours_remaining(self, now: datetime) -> float:
        """Negative once the 72-hour window has passed."""
        return (self.notification_due_at - now).total_seconds() / 3600
