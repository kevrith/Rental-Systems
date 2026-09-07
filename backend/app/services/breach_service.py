"""Personal-data breach register and the 72-hour clock (Kenya DPA s.43).

Section 43 of the Data Protection Act, 2019 gives a controller 72 hours from
becoming aware of a breach to notify the Data Commissioner, and requires the
affected data subjects to be told where the breach is likely to harm them.
Meeting that is not primarily a software problem — it is a process problem —
but software can do the three things a process reliably fails at:

  * **Start the clock automatically.** `notification_due_at` is set the moment
    a breach is recorded, from the moment RentFlow became *aware*, not the
    moment the breach happened. Those are different dates and the law cares
    about the first one.
  * **Refuse to let it run out quietly.** The hourly sweep escalates at 48 and
    72 hours to every platform staff account. There is no state in which the
    deadline passes and nobody was told.
  * **Force the decision to be recorded.** A breach can be dismissed, but not
    silently: `no_notification_reason` is required to close one without
    notifying. The decision not to notify is itself a decision a regulator can
    ask about.

Detection is partly automatic and mostly not, which is honest about how
breaches are actually found. `scan_for_candidates` raises a DETECTED row from
two signals the platform can see for itself — credential-stuffing patterns in
`SecurityEvent`, and abnormal export volume — and everything else arrives
through `report`, because a person noticed.

Platform-level, not organisation-scoped: one incident routinely touches
several customers, and the party who must notify the Commissioner is RentFlow.
Each affected landlord is told separately, because they are the controller for
their own tenants' data and have their own duty to those tenants.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import Organization
from app.models.security import (
    BREACH_NOTIFICATION_WINDOW_HOURS,
    BreachCategory,
    BreachSeverity,
    BreachStatus,
    SecurityBreach,
    SecurityEvent,
    SecurityEventType,
)
from app.models.user import User, UserRole
from app.models.vacancy import DataExport
from app.services import audit_service, notification_service

logger = logging.getLogger("rentflow.breach")

# Escalation points inside the window, in hours elapsed since detection.
ESCALATION_HOURS = (48, BREACH_NOTIFICATION_WINDOW_HOURS)

# --- automatic detection thresholds ---
# Failed logins from one IP against this many distinct accounts inside the
# window is credential stuffing, not somebody mistyping their own password.
STUFFING_WINDOW_MINUTES = 30
STUFFING_DISTINCT_ACCOUNTS = 10
# Data exports by one user inside the window. A landlord exports their book
# occasionally; a departing employee exports everything at once.
EXPORT_WINDOW_MINUTES = 60
EXPORT_BURST_COUNT = 8


async def _next_reference(db: AsyncSession) -> str:
    """`BR-2026-0007`. Sequential within the year, because an incident number
    is quoted in correspondence with a regulator and has to be readable."""
    year = datetime.now(UTC).year
    used = (
        await db.scalar(
            select(func.count(SecurityBreach.id)).where(SecurityBreach.reference_code.like(f"BR-{year}-%"))
        )
        or 0
    )
    return f"BR-{year}-{used + 1:04d}"


def _audit(
    db: AsyncSession,
    breach: SecurityBreach,
    *,
    action: str,
    summary: str,
    actor: User | None = None,
    request: Request | None = None,
) -> None:
    """Write one audit row per affected organisation.

    `AuditLog` is organisation-scoped and the breach register is not, so a
    breach touching three customers leaves a trail in all three. That is the
    right answer rather than a workaround: each of those landlords is the
    controller for their own tenants' data, and their own compliance team can
    reasonably expect to see the incident in their own audit log. A breach with
    no customer attached — platform infrastructure, say — writes none, because
    there is no tenant whose log it belongs in.
    """
    for raw_id in breach.affected_organization_ids:
        audit_service.record(
            db,
            organization_id=uuid.UUID(str(raw_id)),
            action=action,
            entity_type="security_breach",
            entity_id=breach.id,
            actor=actor,
            summary=summary,
            request=request,
        )


async def report(
    db: AsyncSession,
    *,
    category: BreachCategory,
    severity: BreachSeverity,
    summary: str,
    detail: str | None = None,
    detected_at: datetime | None = None,
    occurred_at: datetime | None = None,
    affected_organization_ids: list[uuid.UUID] | None = None,
    affected_subject_count: int | None = None,
    data_categories: list[str] | None = None,
    reported_by: User | None = None,
    detector: str | None = None,
    pattern_key: str | None = None,
    request: Request | None = None,
) -> SecurityBreach:
    """Record a breach and start its 72-hour clock.

    `detected_at` defaults to now and is what the clock runs from — backdating
    it to when RentFlow genuinely became aware shortens the remaining window,
    which is the correct and uncomfortable behaviour.
    """
    if pattern_key is not None:
        existing = await db.scalar(select(SecurityBreach).where(SecurityBreach.pattern_key == pattern_key))
        if existing is not None:
            return existing

    detected = detected_at or datetime.now(UTC)
    breach = SecurityBreach(
        reference_code=await _next_reference(db),
        category=category,
        severity=severity,
        status=BreachStatus.DETECTED,
        summary=summary[:512],
        detail=detail,
        detected_at=detected,
        occurred_at=occurred_at,
        notification_due_at=detected + timedelta(hours=BREACH_NOTIFICATION_WINDOW_HOURS),
        affected_organization_ids=[str(oid) for oid in (affected_organization_ids or [])],
        affected_subject_count=affected_subject_count,
        data_categories=data_categories or [],
        detector=detector,
        pattern_key=pattern_key,
        reported_by_id=reported_by.id if reported_by else None,
    )
    db.add(breach)
    await db.flush()

    await _alert_platform_staff(
        db,
        breach,
        title=f"Data breach recorded — {breach.reference_code}",
        body=(
            f"{severity.value.upper()} severity {category.value.replace('_', ' ')}: {summary} "
            f"The Data Commissioner must be notified by "
            f"{breach.notification_due_at.strftime('%d %b %Y %H:%M UTC')}."
        ),
    )

    _audit(
        db,
        breach,
        action="security_breach.reported",
        summary=f"Breach {breach.reference_code} recorded: {summary}",
        actor=reported_by,
        request=request,
    )
    await db.commit()
    await db.refresh(breach)
    return breach


async def list_breaches(
    db: AsyncSession, *, open_only: bool = False, limit: int = 100
) -> list[SecurityBreach]:
    query = select(SecurityBreach)
    if open_only:
        query = query.where(SecurityBreach.status.notin_([BreachStatus.CLOSED, BreachStatus.DISMISSED]))
    rows = await db.scalars(query.order_by(SecurityBreach.detected_at.desc()).limit(limit))
    return list(rows)


async def get(db: AsyncSession, breach_id: uuid.UUID) -> SecurityBreach:
    breach = await db.get(SecurityBreach, breach_id)
    if breach is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Breach not found")
    return breach


async def advance(
    db: AsyncSession,
    breach_id: uuid.UUID,
    *,
    new_status: BreachStatus,
    staff: User,
    note: str | None = None,
    regulator_reference: str | None = None,
    request: Request | None = None,
) -> SecurityBreach:
    """Move a breach along, recording the evidence each state requires.

    The two states with real consequences are guarded. `NOTIFIED` stamps the
    time the Commissioner was told, which is the fact that either does or does
    not sit inside the 72 hours. `DISMISSED` demands a reason, because deciding
    a breach is not notifiable is a judgement someone may later have to defend.
    """
    breach = await get(db, breach_id)
    now = datetime.now(UTC)

    if new_status == BreachStatus.CONTAINED:
        breach.contained_at = now
        breach.containment_notes = note
    elif new_status == BreachStatus.NOTIFIED:
        breach.regulator_notified_at = now
        breach.regulator_reference = regulator_reference
        if not regulator_reference:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Record the reference the Data Commissioner gave you",
            )
    elif new_status == BreachStatus.DISMISSED:
        if not note:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Say why this breach does not need notifying — that decision has to be on record",
            )
        breach.no_notification_reason = note
        breach.closed_at = now
        breach.closed_by_id = staff.id
    elif new_status == BreachStatus.CLOSED:
        if breach.regulator_notified_at is None and breach.is_notifiable:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "A high or critical breach cannot be closed before the Data Commissioner "
                    "has been notified, or the decision not to notify has been recorded."
                ),
            )
        breach.remediation_notes = note or breach.remediation_notes
        breach.closed_at = now
        breach.closed_by_id = staff.id

    breach.status = new_status

    _audit(
        db,
        breach,
        action=f"security_breach.{new_status.value}",
        summary=f"Breach {breach.reference_code} marked {new_status.value}",
        actor=staff,
        request=request,
    )
    await db.commit()
    await db.refresh(breach)
    return breach


async def notify_affected_customers(
    db: AsyncSession, breach_id: uuid.UUID, *, staff: User, message: str
) -> int:
    """Tell each affected landlord, so they can tell their own tenants.

    A landlord is the data controller for their tenants' personal data;
    RentFlow is their processor. Telling the Commissioner does not discharge
    the landlord's own duty to the people whose data it was, and they cannot
    discharge it if nobody tells them.
    """
    breach = await get(db, breach_id)
    told = 0
    for raw_id in breach.affected_organization_ids:
        organization = await db.get(Organization, uuid.UUID(str(raw_id)))
        if organization is None:
            continue
        owners = await db.scalars(
            select(User).where(
                User.organization_id == organization.id,
                User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
                User.is_active.is_(True),
            )
        )
        for owner in owners:
            await notification_service.send(
                db,
                recipient=notification_service.Recipient.for_user(owner),
                notification_type=NotificationType.BREACH_NOTIFICATION,
                title=f"Security incident affecting your account ({breach.reference_code})",
                body=message,
                channels=[
                    NotificationChannel.EMAIL,
                    NotificationChannel.IN_APP,
                    NotificationChannel.SMS,
                ],
                entity_type="security_breach",
                entity_id=breach.id,
                organization_id=organization.id,
            )
            told += 1

    breach.customers_notified_at = datetime.now(UTC)
    _audit(
        db,
        breach,
        action="security_breach.customers_notified",
        summary=f"Notified {told} account contact(s) about breach {breach.reference_code}",
        actor=staff,
    )
    await db.commit()
    return told


# ------------------------------------------------------------- the 72h sweep


async def escalate_due_notifications(db: AsyncSession) -> int:
    """Chase every open breach approaching or past its deadline. Returns how many.

    `escalation_sent_hours` records the highest threshold already chased, so an
    hourly sweep sends one message at 48 hours and one at 72, not one every
    hour for three days — the difference between an alert people act on and an
    alert people filter.
    """
    now = datetime.now(UTC)
    open_breaches = await db.scalars(
        select(SecurityBreach).where(
            SecurityBreach.status.notin_([BreachStatus.CLOSED, BreachStatus.DISMISSED]),
            SecurityBreach.regulator_notified_at.is_(None),
        )
    )

    escalated = 0
    for breach in open_breaches:
        elapsed = (now - breach.detected_at).total_seconds() / 3600
        threshold = max((hours for hours in ESCALATION_HOURS if elapsed >= hours), default=None)
        if threshold is None or (breach.escalation_sent_hours or 0) >= threshold:
            continue

        remaining = breach.hours_remaining(now)
        if remaining >= 0:
            urgency = f"{remaining:.0f} hour(s) remain to notify the Data Commissioner."
        else:
            urgency = (
                f"The 72-hour notification deadline passed {abs(remaining):.0f} hour(s) ago. "
                "Notify the Data Commissioner immediately and record why it was late."
            )

        await _alert_platform_staff(
            db,
            breach,
            title=f"Breach {breach.reference_code} — notification deadline",
            body=f"{breach.summary} {urgency}",
        )
        breach.escalation_sent_hours = threshold
        escalated += 1

    await db.commit()
    return escalated


async def _alert_platform_staff(db: AsyncSession, breach: SecurityBreach, *, title: str, body: str) -> None:
    """Reach RentFlow's own team, on channels that survive being off-shift.

    Email and SMS rather than in-app: a 72-hour clock that started at 6pm on a
    Friday is the exact case this has to work for.
    """
    staff_members = await db.scalars(select(User).where(User.is_platform_staff.is_(True)))
    for member in staff_members:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(member),
            notification_type=NotificationType.BREACH_NOTIFICATION,
            title=title,
            body=body,
            channels=[NotificationChannel.EMAIL, NotificationChannel.SMS],
            entity_type="security_breach",
            entity_id=breach.id,
            organization_id=member.organization_id,
        )


# --------------------------------------------------------- automatic detection


async def scan_for_candidates(db: AsyncSession) -> int:
    """Raise DETECTED breaches from telemetry the platform can see itself.

    Both detectors are deliberately conservative and both produce a *candidate*
    — status DETECTED, not NOTIFIED. A human decides whether it is a real
    breach. A detector that cried wolf would get muted within a week, and a
    muted detector is worse than none.
    """
    found = 0
    found += await _detect_credential_stuffing(db)
    found += await _detect_export_bursts(db)
    return found


async def _detect_credential_stuffing(db: AsyncSession) -> int:
    """One IP failing logins against many distinct accounts at once."""
    since = datetime.now(UTC) - timedelta(minutes=STUFFING_WINDOW_MINUTES)
    rows = await db.execute(
        select(
            SecurityEvent.ip_address,
            func.count(func.distinct(SecurityEvent.user_id)).label("accounts"),
            func.count(SecurityEvent.id).label("attempts"),
        )
        .where(
            SecurityEvent.event_type == SecurityEventType.LOGIN_FAILED,
            SecurityEvent.created_at >= since,
            SecurityEvent.ip_address.is_not(None),
        )
        .group_by(SecurityEvent.ip_address)
        .having(func.count(func.distinct(SecurityEvent.user_id)) >= STUFFING_DISTINCT_ACCOUNTS)
    )

    found = 0
    for ip_address, accounts, attempts in rows:
        organization_ids = list(
            await db.scalars(
                select(func.distinct(SecurityEvent.organization_id)).where(
                    SecurityEvent.event_type == SecurityEventType.LOGIN_FAILED,
                    SecurityEvent.created_at >= since,
                    SecurityEvent.ip_address == ip_address,
                )
            )
        )
        # Bucketed by hour so a sustained attack raises one incident per hour
        # rather than one every sweep.
        bucket = datetime.now(UTC).strftime("%Y-%m-%dT%H")
        await report(
            db,
            category=BreachCategory.CREDENTIAL_COMPROMISE,
            # A failed attempt is not yet a breach — nothing has been disclosed.
            # It is raised for investigation, not because harm is established.
            severity=BreachSeverity.MEDIUM,
            summary=(
                f"{attempts} failed logins from {ip_address} against {accounts} distinct "
                f"accounts in {STUFFING_WINDOW_MINUTES} minutes."
            ),
            detail=(
                "Automatic detection: credential-stuffing pattern. Confirm whether any attempt "
                "succeeded before treating this as a breach — a failed attempt discloses nothing."
            ),
            affected_organization_ids=organization_ids,
            detector="credential_stuffing",
            pattern_key=f"stuffing:{ip_address}:{bucket}",
        )
        found += 1

    logger.info("Credential-stuffing scan raised %s candidate(s)", found)
    return found


async def _detect_export_bursts(db: AsyncSession) -> int:
    """One user pulling an unusual number of full data exports at once."""
    since = datetime.now(UTC) - timedelta(minutes=EXPORT_WINDOW_MINUTES)
    rows = await db.execute(
        select(
            DataExport.requested_by_id,
            DataExport.organization_id,
            func.count(DataExport.id).label("exports"),
        )
        .where(DataExport.created_at >= since, DataExport.requested_by_id.is_not(None))
        .group_by(DataExport.requested_by_id, DataExport.organization_id)
        .having(func.count(DataExport.id) >= EXPORT_BURST_COUNT)
    )

    found = 0
    for user_id, organization_id, exports in rows:
        user = await db.get(User, user_id)
        bucket = datetime.now(UTC).strftime("%Y-%m-%dT%H")
        await report(
            db,
            category=BreachCategory.DATA_EXFILTRATION,
            severity=BreachSeverity.HIGH,
            summary=(
                f"{user.full_name if user else 'A user'} generated {exports} data exports in "
                f"{EXPORT_WINDOW_MINUTES} minutes."
            ),
            detail=(
                "Automatic detection: export burst. Confirm with the account whether this was "
                "expected — a bulk migration looks the same as an employee leaving with the book."
            ),
            affected_organization_ids=[organization_id],
            data_categories=["tenant contact details", "financial records"],
            detector="export_burst",
            pattern_key=f"export_burst:{user_id}:{bucket}",
        )
        found += 1

    logger.info("Export-burst scan raised %s candidate(s)", found)
    return found


def dashboard(breaches: list[SecurityBreach]) -> dict:
    """Counts the internal breach board leads with."""
    now = datetime.now(UTC)
    open_breaches = [breach for breach in breaches if breach.is_open]
    return {
        "open": len(open_breaches),
        "awaiting_notification": len(
            [
                breach
                for breach in open_breaches
                if breach.is_notifiable and breach.regulator_notified_at is None
            ]
        ),
        "overdue": len(
            [
                breach
                for breach in open_breaches
                if breach.regulator_notified_at is None and breach.hours_remaining(now) < 0
            ]
        ),
        "window_hours": BREACH_NOTIFICATION_WINDOW_HOURS,
        "support_email": settings.SUPPORT_EMAIL,
    }
