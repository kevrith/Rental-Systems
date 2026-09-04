"""Scheduled background work (US-021, US-031, US-006, US-028).

Celery workers are synchronous, so each task opens its own async session and
drives it with `asyncio.run` through `run_async`. Tasks are written to be safe
to re-run: reminders record what they have already sent, and invoice generation
is idempotent per billing period.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentStatus
from app.models.notification import (
    DeliveryStatus,
    Notification,
    NotificationChannel,
    NotificationType,
)
from app.models.organization import Organization, SubscriptionPlan
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.models.user import User, UserRole
from app.services import notification_service
from app.services.pdf_service import format_kes
from app.services.task_monitor_service import monitored
from app.tasks.celery_app import celery_app

logger = logging.getLogger("rentflow.tasks")

T = TypeVar("T")

RENT_REMINDER_OFFSETS = [7, 3, 0]
LEASE_EXPIRY_OFFSETS = [90, 60, 30, 14]
TRIAL_REMINDER_OFFSETS = [7, 3, 1]
LIVE_TENANCIES = [TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON, TenancyStatus.NOTICE_GIVEN]


def run_async(coro_factory: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run one async unit of work against a fresh engine and session.

    A per-task engine avoids sharing a connection pool across Celery's forked
    workers, which is a classic source of 'connection already closed' errors.
    """

    async def _run() -> T:
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
        try:
            async with factory() as session:
                return await coro_factory(session)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


async def _already_sent(
    db: AsyncSession,
    notification_type: NotificationType,
    entity_id: Any,
    marker: str,
    since: datetime | None = None,
) -> bool:
    """Has this exact reminder already gone out? Keyed on the payload marker so
    the 7-day and 3-day nudges for the same invoice are distinct."""
    query = select(Notification.id).where(
        Notification.notification_type == notification_type,
        Notification.entity_id == entity_id,
        Notification.payload["marker"].astext == marker,
        Notification.status.notin_([DeliveryStatus.FAILED]),
    )
    if since:
        query = query.where(Notification.created_at >= since)
    return bool(await db.scalar(query.limit(1)))


# ---------------------------------------------------------------------- invoicing


@celery_app.task(name="rentflow.generate_due_invoices")
@monitored("rentflow.generate_due_invoices")
def generate_due_invoices() -> dict[str, int]:
    from app.services import invoice_service

    async def work(db: AsyncSession) -> int:
        return await invoice_service.generate_due_invoices(db)

    created = run_async(work)
    logger.info("Generated %s invoice(s)", created)
    return {"created": created}


@celery_app.task(name="rentflow.refresh_tenancy_statuses")
@monitored("rentflow.refresh_tenancy_statuses")
def refresh_tenancy_statuses() -> dict[str, int]:
    from app.services import tenant_service

    async def work(db: AsyncSession) -> int:
        changed = 0
        for org_id in await db.scalars(select(Organization.id).where(Organization.is_active.is_(True))):
            changed += await tenant_service.refresh_tenancy_statuses(db, org_id)
        return changed

    changed = run_async(work)
    logger.info("Refreshed %s tenancy status(es)", changed)
    return {"changed": changed}


# ---------------------------------------------------------------------- reminders


@celery_app.task(name="rentflow.send_rent_reminders")
@monitored("rentflow.send_rent_reminders")
def send_rent_reminders() -> dict[str, int]:
    """Rent reminder sequence: 7 days before, 3 days before, and on the due date."""

    async def work(db: AsyncSession) -> int:
        today = date.today()
        sent = 0

        for offset in RENT_REMINDER_OFFSETS:
            target_due = today + timedelta(days=offset)
            invoices = await db.scalars(
                select(Invoice).where(
                    Invoice.due_date == target_due,
                    Invoice.status.notin_([InvoiceStatus.PAID, InvoiceStatus.CANCELLED]),
                )
            )
            for invoice in invoices:
                marker = f"rent-{offset}d"
                if await _already_sent(db, NotificationType.RENT_REMINDER, invoice.id, marker):
                    continue

                tenancy = await db.get(Tenancy, invoice.tenancy_id)
                tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
                if tenant is None:
                    continue

                balance = Decimal(invoice.total) - Decimal(invoice.amount_paid)
                when = "today" if offset == 0 else f"in {offset} day{'s' if offset != 1 else ''}"
                notifications = await notification_service.send(
                    db,
                    recipient=notification_service.Recipient.for_tenant(tenant),
                    notification_type=NotificationType.RENT_REMINDER,
                    title="Rent reminder",
                    body=(
                        f"Dear {tenant.full_name.split()[0]}, your rent of KES "
                        f"{format_kes(balance)} for invoice {invoice.reference_code} is due {when} "
                        f"({invoice.due_date.strftime('%d %b %Y')})."
                    ),
                    channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
                    entity_type="invoice",
                    entity_id=invoice.id,
                    organization_id=invoice.organization_id,
                )
                for notification in notifications:
                    notification.payload = {"marker": marker}
                sent += 1

        await db.commit()
        return sent

    sent = run_async(work)
    logger.info("Sent %s rent reminder(s)", sent)
    return {"sent": sent}


@celery_app.task(name="rentflow.send_lease_expiry_alerts")
@monitored("rentflow.send_lease_expiry_alerts")
def send_lease_expiry_alerts() -> dict[str, int]:
    """Lease expiry alerts at 90, 60, 30 and 14 days — to tenant and to owner."""

    async def work(db: AsyncSession) -> int:
        today = date.today()
        sent = 0

        for offset in LEASE_EXPIRY_OFFSETS:
            target = today + timedelta(days=offset)
            tenancies = await db.scalars(
                select(Tenancy).where(Tenancy.end_date == target, Tenancy.status.in_(LIVE_TENANCIES))
            )
            for tenancy in tenancies:
                if tenancy.end_date is None:
                    continue
                marker = f"lease-{offset}d"
                if await _already_sent(db, NotificationType.LEASE_EXPIRY, tenancy.id, marker):
                    continue

                tenant = await db.get(Tenant, tenancy.tenant_id)
                unit = await db.get(Unit, tenancy.unit_id)
                property_record = await db.get(Property, unit.property_id) if unit else None
                where = (
                    f"unit {unit.unit_number} at {property_record.name}"
                    if unit and property_record
                    else "your unit"
                )
                body = (
                    f"The lease for {where} (tenancy {tenancy.reference_code}) expires on "
                    f"{tenancy.end_date.strftime('%d %b %Y')} — {offset} days from now."
                )

                recipients = []
                if tenant:
                    recipients.append(notification_service.Recipient.for_tenant(tenant))
                owners = await db.scalars(
                    select(User).where(
                        User.organization_id == tenancy.organization_id,
                        User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
                        User.is_active.is_(True),
                    )
                )
                recipients.extend(notification_service.Recipient.for_user(o) for o in owners)

                for recipient in recipients:
                    notifications = await notification_service.send(
                        db,
                        recipient=recipient,
                        notification_type=NotificationType.LEASE_EXPIRY,
                        title=f"Lease expires in {offset} days",
                        body=body,
                        channels=[NotificationChannel.WHATSAPP],
                        entity_type="tenancy",
                        entity_id=tenancy.id,
                        organization_id=tenancy.organization_id,
                    )
                    for notification in notifications:
                        notification.payload = {"marker": marker}
                sent += 1

        await db.commit()
        return sent

    sent = run_async(work)
    logger.info("Sent %s lease expiry alert(s)", sent)
    return {"sent": sent}


@celery_app.task(name="rentflow.send_trial_reminders")
@monitored("rentflow.send_trial_reminders")
def send_trial_reminders() -> dict[str, int]:
    """Trial expiry nudges at 7, 3 and 1 days remaining (US-006)."""

    async def work(db: AsyncSession) -> int:
        now = datetime.now(UTC)
        sent = 0

        organizations = await db.scalars(
            select(Organization).where(
                Organization.subscription_plan == SubscriptionPlan.TRIAL,
                Organization.trial_ends_at.is_not(None),
                Organization.is_active.is_(True),
            )
        )
        for organization in organizations:
            if organization.trial_ends_at is None:
                continue
            days_left = (organization.trial_ends_at - now).days
            offset = next((o for o in TRIAL_REMINDER_OFFSETS if days_left == o), None)
            if offset is None:
                continue
            # Only ever move downward — 7 then 3 then 1, never a repeat.
            if organization.trial_reminder_sent_days is not None and (
                organization.trial_reminder_sent_days <= offset
            ):
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
                    notification_type=NotificationType.TRIAL_EXPIRY,
                    title=f"Your free trial ends in {offset} day{'s' if offset != 1 else ''}",
                    body=(
                        f"{organization.name}'s RentFlow trial ends on "
                        f"{organization.trial_ends_at.strftime('%d %b %Y')}. Upgrade to keep adding "
                        f"properties, tenants and payments: {settings.FRONTEND_URL}/settings/billing"
                    ),
                    channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
                    organization_id=organization.id,
                )
                sent += 1
            organization.trial_reminder_sent_days = offset

        await db.commit()
        return sent

    sent = run_async(work)
    logger.info("Sent %s trial reminder(s)", sent)
    return {"sent": sent}


# ------------------------------------------------------------------- caretakers


@celery_app.task(name="rentflow.caretaker_daily_summary")
@monitored("rentflow.caretaker_daily_summary")
def caretaker_daily_summary() -> dict[str, int]:
    """7pm digest of each caretaker's day, sent to the owners (US-028)."""
    from app.services import operations_service

    async def work(db: AsyncSession) -> int:
        since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        sent = 0

        organizations = await db.scalars(select(Organization).where(Organization.is_active.is_(True)))
        for organization in organizations:
            caretakers = list(
                await db.scalars(
                    select(User).where(
                        User.organization_id == organization.id,
                        User.role == UserRole.CARETAKER,
                        User.is_active.is_(True),
                    )
                )
            )
            if not caretakers:
                continue

            owners = list(
                await db.scalars(
                    select(User).where(
                        User.organization_id == organization.id,
                        User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
                        User.is_active.is_(True),
                    )
                )
            )
            if not owners:
                continue

            lines = []
            for caretaker in caretakers:
                counts = await operations_service.caretaker_activity_counts(
                    db, organization.id, caretaker.id, since
                )
                lines.append(
                    f"{caretaker.full_name}: {counts['payments_recorded']} payment(s), "
                    f"{counts['meter_readings']} meter reading(s), "
                    f"{counts['maintenance_requests']} maintenance request(s)."
                )

                # Inactivity alert: no login for three days or more.
                if caretaker.last_login_at is None or (
                    datetime.now(UTC) - caretaker.last_login_at
                ) > timedelta(days=3):
                    lines.append(f"  ⚠ {caretaker.full_name} has not logged in for 3+ days.")

            for owner in owners:
                await notification_service.send(
                    db,
                    recipient=notification_service.Recipient.for_user(owner),
                    notification_type=NotificationType.CARETAKER_DAILY_SUMMARY,
                    title="Today's caretaker activity",
                    body="\n".join(lines),
                    channels=[NotificationChannel.WHATSAPP, NotificationChannel.IN_APP],
                    organization_id=organization.id,
                )
                sent += 1

        await db.commit()
        return sent

    sent = run_async(work)
    logger.info("Sent %s caretaker summary/summaries", sent)
    return {"sent": sent}


# ------------------------------------------------------------------ phase 2 tasks


@celery_app.task(name="rentflow.apply_late_fees")
@monitored("rentflow.apply_late_fees")
def apply_late_fees() -> dict[str, int]:
    """Apply late fees to all overdue invoices (US-055)."""
    from app.services import late_fee_service

    async def work(db: AsyncSession) -> int:
        return await late_fee_service.apply_late_fees(db)

    applied = run_async(work)
    logger.info("Applied %s late fee(s)", applied)
    return {"applied": applied}


@celery_app.task(name="rentflow.send_lease_renewal_notices")
@monitored("rentflow.send_lease_renewal_notices")
def send_lease_renewal_notices() -> dict[str, int]:
    """Auto-generate renewal agreements at 30 days and send to tenants (US-057)."""

    async def work(db: AsyncSession) -> int:
        today = date.today()
        sent = 0

        # At 30 days: generate renewal agreement and send for signing
        target_30 = today + timedelta(days=30)
        tenancies = await db.scalars(
            select(Tenancy).where(
                Tenancy.end_date == target_30,
                Tenancy.status.in_(LIVE_TENANCIES),
                Tenancy.is_open_ended.is_(False),
            )
        )
        for tenancy in tenancies:
            marker = "renewal-30d"
            if await _already_sent(db, NotificationType.LEASE_RENEWAL, tenancy.id, marker):
                continue

            tenant = await db.get(Tenant, tenancy.tenant_id)
            unit = await db.get(Unit, tenancy.unit_id)
            property_record = await db.get(Property, unit.property_id) if unit else None
            where = (
                f"unit {unit.unit_number} at {property_record.name}"
                if unit and property_record
                else "your unit"
            )

            if tenant:
                notifications = await notification_service.send(
                    db,
                    recipient=notification_service.Recipient.for_tenant(tenant),
                    notification_type=NotificationType.LEASE_RENEWAL,
                    title="Lease renewal — action required",
                    body=(
                        f"Dear {tenant.full_name.split()[0]}, your lease for {where} expires on "
                        f"{target_30.strftime('%d %b %Y')}. "
                        f"Please contact your landlord to discuss renewal."
                    ),
                    channels=[NotificationChannel.WHATSAPP],
                    entity_type="tenancy",
                    entity_id=tenancy.id,
                    organization_id=tenancy.organization_id,
                )
                for n in notifications:
                    n.payload = {"marker": marker}
                sent += 1

        await db.commit()
        return sent

    sent = run_async(work)
    logger.info("Sent %s lease renewal notice(s)", sent)
    return {"sent": sent}


@celery_app.task(name="rentflow.process_scheduled_disbursements")
@monitored("rentflow.process_scheduled_disbursements")
def process_scheduled_disbursements() -> dict[str, int]:
    """Prepare disbursements for owners whose disbursement_day is today (US-043).

    The payout covers the *previous* whole month: on the 5th of March an owner is
    settled for February. The disbursement is created PENDING and the agency's
    admins are asked to review it — no money moves without an explicit approval.
    """
    from app.models.agency import Disbursement, DisbursementStatus, OwnerProfile
    from app.models.organization import OperatingMode
    from app.services import agency_service, reference_service

    async def work(db: AsyncSession) -> tuple[int, int]:
        today = date.today()
        prepared = 0
        skipped = 0

        # The month that just ended.
        period_end = today.replace(day=1) - timedelta(days=1)
        period_start = period_end.replace(day=1)

        profiles = await db.scalars(
            select(OwnerProfile).where(
                OwnerProfile.is_active.is_(True),
                OwnerProfile.disbursement_day == today.day,
            )
        )
        for profile in profiles:
            org = await db.get(Organization, profile.organization_id)
            if not org or org.operating_mode != OperatingMode.AGENCY:
                continue

            existing = await db.scalar(
                select(Disbursement.id).where(
                    Disbursement.owner_profile_id == profile.id,
                    Disbursement.period_start == period_start,
                )
            )
            if existing:
                skipped += 1
                continue

            calc = await agency_service.calculate_for_profile(db, profile, period_start, period_end)
            code = await reference_service.generate_reference(
                db, Disbursement, profile.organization_id, "DSB"
            )
            disbursement = Disbursement(
                organization_id=profile.organization_id,
                reference_code=code,
                owner_profile_id=profile.id,
                period_start=period_start,
                period_end=period_end,
                gross_rent=calc["gross_rent"],
                management_fee=calc["management_fee"],
                maintenance_costs=calc["maintenance_costs"],
                other_deductions=calc["other_deductions"],
                net_amount=calc["net_amount"],
                status=DisbursementStatus.PENDING,
                notes="Prepared automatically on the owner's disbursement day",
            )
            db.add(disbursement)
            await db.flush()

            # The agency reviews and approves; the owner is told it is coming.
            admins = await db.scalars(
                select(User).where(
                    User.organization_id == profile.organization_id,
                    User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
                    User.is_active.is_(True),
                )
            )
            for admin in admins:
                await notification_service.send(
                    db,
                    recipient=notification_service.Recipient.for_user(admin),
                    notification_type=NotificationType.ACCOUNT,
                    title=f"Disbursement ready for review — {profile.full_name}",
                    body=(
                        f"{disbursement.reference_code} for "
                        f"{period_start.strftime('%B %Y')}: gross KES "
                        f"{format_kes(calc['gross_rent'])}, net KES "
                        f"{format_kes(calc['net_amount'])}. "
                        f"Approve it on the agency dashboard to release the payout."
                    ),
                    link_path="/agency/disbursements",
                    channels=[NotificationChannel.WHATSAPP, NotificationChannel.PUSH],
                    entity_type="disbursement",
                    entity_id=disbursement.id,
                    organization_id=profile.organization_id,
                )

            await notification_service.send(
                db,
                recipient=notification_service.Recipient(
                    phone_number=profile.mpesa_phone or profile.phone_number,
                    organization_id=profile.organization_id,
                ),
                notification_type=NotificationType.DISBURSEMENT_SENT,
                title="Your disbursement is being prepared",
                body=(
                    f"Dear {profile.full_name}, your statement for "
                    f"{period_start.strftime('%B %Y')} is being prepared. "
                    f"Net payable: KES {format_kes(calc['net_amount'])}. "
                    f"Reference: {disbursement.reference_code}."
                ),
                channels=[NotificationChannel.WHATSAPP],
                entity_type="disbursement",
                entity_id=disbursement.id,
                organization_id=profile.organization_id,
            )
            prepared += 1

        await db.commit()
        return prepared, skipped

    prepared, skipped = run_async(work)
    logger.info("Prepared %s disbursement(s), %s already existed", prepared, skipped)
    return {"prepared": prepared, "skipped": skipped}


# ------------------------------------------------------------------ housekeeping


@celery_app.task(name="rentflow.reconcile_pending_payments")
@monitored("rentflow.reconcile_pending_payments")
def reconcile_pending_payments() -> dict[str, int]:
    """Chase M-Pesa pushes whose callback never landed.

    Anything older than 15 minutes and still pending is queried directly; after
    an hour with no result, it is written off as failed so it stops cluttering
    the payments list.
    """
    from app.services import mpesa_service

    async def work(db: AsyncSession) -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=15)
        stale = datetime.now(UTC) - timedelta(hours=1)
        resolved = 0

        pending = await db.scalars(
            select(Payment).where(
                Payment.status == PaymentStatus.PENDING,
                Payment.mpesa_checkout_request_id.is_not(None),
                Payment.created_at <= cutoff,
            )
        )
        for payment in pending:
            if payment.mpesa_checkout_request_id is None:
                continue
            response = await mpesa_service.query_status(payment.mpesa_checkout_request_id)
            code = str(response.get("ResultCode", ""))
            if code and code not in ("0", "1037"):
                payment.status = PaymentStatus.CANCELLED if code == "1032" else PaymentStatus.FAILED
                payment.failure_reason = str(response.get("ResultDesc", ""))[:500]
                resolved += 1
            elif payment.created_at <= stale:
                payment.status = PaymentStatus.FAILED
                payment.failure_reason = "No confirmation received from M-Pesa within one hour"
                resolved += 1

        await db.commit()
        return resolved

    resolved = run_async(work)
    logger.info("Reconciled %s pending payment(s)", resolved)
    return {"resolved": resolved}


@celery_app.task(name="rentflow.purge_deleted_accounts")
@monitored("rentflow.purge_deleted_accounts")
def purge_deleted_accounts() -> dict[str, int]:
    """Finalise account deletions once the grace period has elapsed (US-004)."""

    async def work(db: AsyncSession) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=settings.ACCOUNT_DELETION_GRACE_DAYS)
        purged = 0

        users = await db.scalars(
            select(User).where(
                User.deletion_requested_at.is_not(None),
                User.deletion_requested_at <= cutoff,
                User.deleted_at.is_(None),
            )
        )
        for user in users:
            # Anonymise rather than delete — payments and audit rows must keep
            # referring to a user, and financial history has to stay intact.
            user.deleted_at = datetime.now(UTC)
            user.is_active = False
            user.full_name = "Deleted user"
            user.email = f"deleted-{user.id.hex[:12]}@deleted.rentflow.local"
            user.phone_number = f"+000{user.id.hex[:9]}"
            user.password_hash = "!"
            user.profile_photo_url = None
            purged += 1

        await db.commit()
        return purged

    purged = run_async(work)
    logger.info("Purged %s account(s)", purged)
    return {"purged": purged}


@celery_app.task(name="rentflow.issue_demand_letters")
@monitored("rentflow.issue_demand_letters")
def issue_demand_letters() -> dict[str, int]:
    """Escalate aged arrears into formal demand letters (US-055)."""
    from app.services import demand_letter_service

    result = run_async(demand_letter_service.issue_due_letters)
    return result


@celery_app.task(name="rentflow.retry_etims_submissions")
@monitored("rentflow.retry_etims_submissions")
def retry_etims_submissions() -> dict[str, int]:
    """Re-attempt eTIMS submissions whose backoff has elapsed (US-053).

    The backoff lives on the row, so this task simply asks for whatever is due
    and can run on a fixed short schedule without hammering KRA.
    """
    from app.services import etims_service

    async def work(db: AsyncSession) -> tuple[int, int]:
        due = await etims_service.due_submissions(db)
        submitted = 0
        for submission in due:
            result = await etims_service.submit(db, submission)
            if result.status.value == "submitted":
                submitted += 1
        return len(due), submitted

    attempted, submitted = run_async(work)
    logger.info("Retried %s eTIMS submission(s), %s accepted", attempted, submitted)
    return {"attempted": attempted, "submitted": submitted}


@celery_app.task(name="rentflow.offer_lease_renewals")
@monitored("rentflow.offer_lease_renewals")
def offer_lease_renewals() -> dict[str, int]:
    """Generate renewal offers 30 days out and escalate silence at 14 (US-057)."""
    from app.services import renewal_service

    result = run_async(renewal_service.offer_due_renewals)
    lapsed = run_async(renewal_service.lapse_expired_offers)
    return {**result, "lapsed": lapsed}


@celery_app.task(name="rentflow.prune_task_runs")
@monitored("rentflow.prune_task_runs")
def prune_task_runs() -> dict[str, int]:
    """Keep the task monitoring history to its retention window (US-056)."""
    from app.services import task_monitor_service

    removed = run_async(task_monitor_service.prune)
    return {"removed": removed}


@celery_app.task(name="rentflow.flag_overdue_maintenance")
@monitored("rentflow.flag_overdue_maintenance")
def flag_overdue_maintenance() -> dict[str, int]:
    """Flag maintenance jobs that blew past their expected completion date and
    tell the manager who is chasing them (US-061)."""
    from app.services import maintenance_service

    flagged = run_async(maintenance_service.flag_overdue_jobs)
    logger.info("Flagged %s overdue maintenance job(s)", flagged)
    return {"flagged": flagged}
