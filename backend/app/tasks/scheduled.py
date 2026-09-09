"""Scheduled background work (US-021, US-031, US-006, US-028).

Celery workers are synchronous, so each task opens its own async session and
drives it with `asyncio.run` through `run_async`. Tasks are written to be safe
to re-run: reminders record what they have already sent, and invoice generation
is idempotent per billing period.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.tasks.async_utils import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger("rentflow.tasks")

RENT_REMINDER_OFFSETS = [7, 3, 0]
LEASE_EXPIRY_OFFSETS = [90, 60, 30, 14]
TRIAL_REMINDER_OFFSETS = [7, 3, 1]
LIVE_TENANCIES = [TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON, TenancyStatus.NOTICE_GIVEN]


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
                unit = await db.get(Unit, tenancy.unit_id) if tenancy else None
                property_record = await db.get(Property, unit.property_id) if unit else None
                organization = await db.get(Organization, invoice.organization_id)
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
                    # Supplied so an organisation that has rewritten this
                    # message (Module 21) has real values to interpolate. With
                    # no custom template these are simply unused.
                    variables={
                        "tenant_name": tenant.full_name,
                        "amount": format_kes(balance),
                        "balance": format_kes(balance),
                        "due_date": invoice.due_date.strftime("%d %b %Y"),
                        "property_name": property_record.name if property_record else "",
                        "unit_number": unit.unit_number if unit else "",
                        "organization_name": organization.name if organization else "",
                    },
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
                    lines.append(f"  ! {caretaker.full_name} has not logged in for 3+ days.")

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


@celery_app.task(name="rentflow.process_daily_disbursements")
@monitored("rentflow.process_daily_disbursements")
def process_daily_disbursements() -> dict[str, int]:
    """Settle yesterday's rent for owners on daily disbursement.

    The monthly run above prepares a disbursement and waits for an agency admin
    to approve it. This one approves and pays in the same pass, which is why it
    only touches owners who have `auto_disburse_daily` switched on — that flag is
    the standing approval, and it is off by default.

    Each owner is settled independently: one owner's failed payout must not stop
    the rest of the run, and a failure leaves a FAILED disbursement behind whose
    period is retried by tomorrow's pass rather than being lost.
    """
    from app.models.agency import OwnerProfile
    from app.models.organization import OperatingMode
    from app.services import agency_service

    async def work(db: AsyncSession) -> tuple[int, int, int]:
        today = date.today()
        settled = 0
        nothing_due = 0
        failed = 0

        profiles = await db.scalars(
            select(OwnerProfile).where(
                OwnerProfile.is_active.is_(True),
                OwnerProfile.auto_disburse_daily.is_(True),
            )
        )
        for profile in profiles:
            org = await db.get(Organization, profile.organization_id)
            if not org or org.operating_mode != OperatingMode.AGENCY:
                continue

            try:
                disbursement = await agency_service.auto_settle_owner(db, profile, today)
            except Exception:
                # Includes a Daraja rejection, which `dispatch_mpesa_payout` has
                # already recorded as FAILED and committed.
                await db.rollback()
                logger.exception("Daily settlement failed for owner %s", profile.id)
                failed += 1
                continue

            if disbursement is None:
                nothing_due += 1
                continue

            settled += 1
            await notification_service.send(
                db,
                recipient=notification_service.Recipient(
                    phone_number=profile.mpesa_phone or profile.phone_number
                ),
                notification_type=NotificationType.ACCOUNT,
                title="Rent sent to you",
                body=(
                    f"KES {format_kes(disbursement.net_amount)} has been sent to you for "
                    f"{disbursement.period_start} to {disbursement.period_end}. "
                    f"Reference: {disbursement.reference_code}."
                ),
                channels=[NotificationChannel.WHATSAPP],
                entity_type="disbursement",
                entity_id=disbursement.id,
                organization_id=profile.organization_id,
            )

        await db.commit()
        return settled, nothing_due, failed

    settled, nothing_due, failed = run_async(work)
    logger.info("Daily settlement: %s paid, %s with nothing due, %s failed", settled, nothing_due, failed)
    return {"settled": settled, "nothing_due": nothing_due, "failed": failed}


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


@celery_app.task(name="rentflow.sweep_stale_references")
@monitored("rentflow.sweep_stale_references")
def sweep_stale_references() -> dict[str, int]:
    """Close out landlord references nobody answered, so a screening score stops
    crediting a maybe (US-068)."""
    from app.services import screening_service

    closed = run_async(screening_service.sweep_stale_references)
    logger.info("Closed %s unanswered landlord reference(s)", closed)
    return {"closed": closed}


@celery_app.task(name="rentflow.chase_stale_leads")
@monitored("rentflow.chase_stale_leads")
def chase_stale_leads() -> dict[str, int]:
    """Nudge the office about vacancy enquiries nobody has followed up (US-075)."""
    from app.services import vacancy_service

    chased = run_async(vacancy_service.chase_stale_leads)
    logger.info("Chased %s stale lead(s)", chased)
    return {"chased": chased}


@celery_app.task(name="rentflow.monthly_data_export")
@monitored("rentflow.monthly_data_export")
def monthly_data_export() -> dict[str, int]:
    """Build each organisation's monthly tenancy export so nobody is ever locked
    in by inertia (US-077)."""
    from app.services import export_service

    built = run_async(export_service.run_scheduled_exports)
    logger.info("Built %s scheduled export(s)", built)
    return {"built": built}


@celery_app.task(name="rentflow.sweep_compliance_expiry")
@monitored("rentflow.sweep_compliance_expiry")
def sweep_compliance_expiry() -> dict[str, int]:
    """Walk the 90/60/30/7-day reminder ladder on every certificate (US-078)."""
    from app.services import facilities_service

    sent = run_async(facilities_service.sweep_compliance_expiry)
    logger.info("Sent %s compliance reminder(s)", sent)
    return {"sent": sent}


@celery_app.task(name="rentflow.sweep_overdue_utilities")
@monitored("rentflow.sweep_overdue_utilities")
def sweep_overdue_utilities() -> dict[str, int]:
    """Flag the building's own bills that have gone past due (US-081)."""
    from app.services import facilities_service

    alerted = run_async(facilities_service.sweep_overdue_utilities)
    logger.info("Flagged %s overdue utility account(s)", alerted)
    return {"alerted": alerted}


@celery_app.task(name="rentflow.monthly_owner_report")
@monitored("rentflow.monthly_owner_report")
def monthly_owner_report() -> dict[str, int]:
    """Generate and deliver last month's financial summary to every owner
    (Sprint 21, US-093)."""
    from app.services import reporting_service

    built = run_async(reporting_service.run_scheduled_monthly_reports)
    logger.info("Built %s monthly owner report(s)", built)
    return {"built": built}


@celery_app.task(name="rentflow.run_scheduled_custom_reports")
@monitored("rentflow.run_scheduled_custom_reports")
def run_scheduled_custom_reports() -> dict[str, int]:
    """Run and deliver every saved custom report whose schedule is due today
    (Sprint 21, US-094)."""
    from app.services import reporting_service

    sent = run_async(reporting_service.run_scheduled_custom_reports)
    logger.info("Ran %s scheduled custom report(s)", sent)
    return {"sent": sent}


# ------------------------------------------------------------- security (Sprint 22)


@celery_app.task(name="rentflow.send_failed_login_digest")
@monitored("rentflow.send_failed_login_digest")
def send_failed_login_digest() -> dict[str, int]:
    """Daily summary of failed sign-in attempts per account (US-098).

    The Redis lockout counter in `auth_service` is ephemeral and only long
    enough to enforce the 15-minute lockout; this reads the durable
    `SecurityEvent` rows instead, so a slow trickle of failures spread across a
    day (too slow to ever trigger a lockout) is still visible to the owner.
    """
    from app.models.security import SecurityEvent, SecurityEventType

    async def work(db: AsyncSession) -> int:
        since = datetime.now(UTC) - timedelta(hours=24)
        sent = 0

        organizations = await db.scalars(select(Organization).where(Organization.is_active.is_(True)))
        for organization in organizations:
            count = await db.scalar(
                select(func.count(SecurityEvent.id)).where(
                    SecurityEvent.organization_id == organization.id,
                    SecurityEvent.event_type == SecurityEventType.LOGIN_FAILED,
                    SecurityEvent.created_at >= since,
                )
            )
            if not count:
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
                    notification_type=NotificationType.FAILED_LOGIN_DIGEST,
                    title="Failed sign-in attempts in the last 24 hours",
                    body=f"{organization.name} had {count} failed sign-in attempt(s) in the last 24 hours.",
                    channels=[NotificationChannel.IN_APP],
                    organization_id=organization.id,
                )
                sent += 1

        await db.commit()
        return sent

    sent = run_async(work)
    logger.info("Sent %s failed-login digest(s)", sent)
    return {"sent": sent}


@celery_app.task(name="rentflow.sync_accounting_connections")
@monitored("rentflow.sync_accounting_connections")
def sync_accounting_connections() -> dict[str, int]:
    """Push everything unsynced to every connected QuickBooks/Xero company,
    daily (Sprint 23, US-100)."""
    from app.services import accounting_service

    synced = run_async(accounting_service.sync_due_connections)
    logger.info("Ran accounting sync for %s connection(s)", synced)
    return {"connections": synced}


@celery_app.task(name="rentflow.remind_api_key_rotation")
@monitored("rentflow.remind_api_key_rotation")
def remind_api_key_rotation() -> dict[str, int]:
    """Nudge an account to rotate an API key that has not been rotated in
    `API_KEY_ROTATION_REMINDER_DAYS` (US-098)."""
    from app.models.developer import ApiKey

    async def work(db: AsyncSession) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=settings.API_KEY_ROTATION_REMINDER_DAYS)
        sent = 0

        keys = await db.scalars(
            select(ApiKey).where(
                ApiKey.revoked_at.is_(None),
                ApiKey.created_at <= cutoff,
                (ApiKey.rotation_reminder_sent_at.is_(None)) | (ApiKey.rotation_reminder_sent_at <= cutoff),
            )
        )
        for key in keys:
            owners = await db.scalars(
                select(User).where(
                    User.organization_id == key.organization_id,
                    User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
                    User.is_active.is_(True),
                )
            )
            for owner in owners:
                await notification_service.send(
                    db,
                    recipient=notification_service.Recipient.for_user(owner),
                    notification_type=NotificationType.API_KEY_ROTATION_DUE,
                    title="Time to rotate an API key",
                    body=(
                        f"API key '{key.name}' has not been rotated in "
                        f"{settings.API_KEY_ROTATION_REMINDER_DAYS} days. Generate a new one and "
                        f"revoke this one once your integration is switched over."
                    ),
                    link_path="/settings/developer",
                    channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
                    entity_type="api_key",
                    entity_id=key.id,
                    organization_id=key.organization_id,
                )
            key.rotation_reminder_sent_at = datetime.now(UTC)
            sent += 1

        await db.commit()
        return sent

    sent = run_async(work)
    logger.info("Sent %s API key rotation reminder(s)", sent)
    return {"sent": sent}


@celery_app.task(name="rentflow.rescan_stored_files")
@monitored("rentflow.rescan_stored_files")
def rescan_stored_files(limit: int = 500) -> dict[str, int]:
    """Retroactively scan files uploaded before ClamAV was configured, or whose
    scan previously failed (US-105).

    Deliberately not on the beat schedule: this is a one-off catch-up run, not a
    recurring job — re-scanning already-clean files on a schedule would just be
    wasted daemon load. Trigger it by hand (e.g. once real CLAMAV_HOST
    credentials are in place) via
    `celery -A app.tasks.celery_app call rentflow.rescan_stored_files`.
    """
    from app.models.file import ScanStatus, StoredFile, UploadStatus
    from app.services import storage_service, virus_scan_service

    async def work(db: AsyncSession) -> dict[str, int]:
        rows = await db.scalars(
            select(StoredFile)
            .where(
                StoredFile.status == UploadStatus.UPLOADED,
                StoredFile.scan_status.in_([ScanStatus.PENDING, ScanStatus.SKIPPED, ScanStatus.FAILED]),
            )
            .limit(limit)
        )
        scanned = 0
        infected = 0
        for record in rows:
            try:
                data = storage_service.get_storage().read(record.storage_key)
            except Exception:
                continue
            outcome = virus_scan_service.scan_bytes(data)
            record.scan_status = outcome.status
            record.scan_detail = outcome.detail
            record.scanned_at = datetime.now(UTC)
            scanned += 1
            if outcome.status == ScanStatus.INFECTED:
                infected += 1
                logger.warning(
                    "Retroactive scan found an infected file already in storage: %s (%s)",
                    record.id,
                    outcome.detail,
                )
        await db.commit()
        return {"scanned": scanned, "infected": infected}

    result = run_async(work)
    logger.info("Rescanned %s stored file(s), %s infected", result["scanned"], result["infected"])
    return result


@celery_app.task(name="rentflow.complete_management_agreement_terminations")
@monitored("rentflow.complete_management_agreement_terminations")
def complete_management_agreement_terminations() -> dict[str, int]:
    """Close out management agreements whose notice period has run, and expire
    fixed-term ones that reached their end date (Sprint 26)."""
    from app.services import management_agreement_service

    completed = run_async(management_agreement_service.complete_due_terminations)
    logger.info("Closed %s management agreement(s)", completed)
    return {"completed": completed}


@celery_app.task(name="rentflow.escalate_breach_notifications")
@monitored("rentflow.escalate_breach_notifications")
def escalate_breach_notifications() -> dict[str, int]:
    """Chase any breach whose Kenya DPA 72-hour notification window is running
    down, and any that has already passed it (Sprint 26)."""
    from app.services import breach_service

    escalated = run_async(breach_service.escalate_due_notifications)
    if escalated:
        logger.warning("Escalated %s breach notification deadline(s)", escalated)
    return {"escalated": escalated}


@celery_app.task(name="rentflow.scan_for_breach_candidates")
@monitored("rentflow.scan_for_breach_candidates")
def scan_for_breach_candidates() -> dict[str, int]:
    """Raise breach candidates from authentication and export telemetry."""
    from app.services import breach_service

    found = run_async(breach_service.scan_for_candidates)
    return {"candidates": found}


@celery_app.task(name="rentflow.sweep_data_retention")
@monitored("rentflow.sweep_data_retention")
def sweep_data_retention() -> dict[str, int]:
    """Redact personal data past its retention window (Sprint 26A).

    See docs/legal/data-retention-policy.md for the periods and the legal
    hold override this checks before touching anything.
    """
    from app.services import retention_service

    return run_async(retention_service.sweep)


@celery_app.task(name="rentflow.chain_audit_log_entries")
@monitored("rentflow.chain_audit_log_entries")
def chain_audit_log_entries() -> dict[str, int]:
    """Extend the hash chain over every organisation's newly-written audit rows (Sprint 26A)."""
    from app.services import audit_chain_service

    async def work(db: AsyncSession) -> int:
        chained = 0
        for org_id in await db.scalars(select(Organization.id).where(Organization.is_active.is_(True))):
            chained += await audit_chain_service.chain_new_entries(db, org_id)
        return chained

    chained = run_async(work)
    return {"chained": chained}


@celery_app.task(name="rentflow.run_bi_exports")
@monitored("rentflow.run_bi_exports")
def run_bi_exports() -> dict[str, int]:
    """Parquet drops for every organisation that opted into BI export (Sprint 26A)."""
    from app.services import export_service

    built = run_async(export_service.run_bi_exports)
    logger.info("Built %s BI export dataset(s)", built)
    return {"built": built}
