from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "rentflow",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
    include=["app.tasks.scheduled", "app.tasks.webhooks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Nairobi",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Raise invoices for every tenancy whose billing day is today.
        "generate-due-invoices": {
            "task": "rentflow.generate_due_invoices",
            "schedule": crontab(hour=6, minute=0),
        },
        # Rent reminders at 7, 3 and 0 days before the due date.
        "send-rent-reminders": {
            "task": "rentflow.send_rent_reminders",
            "schedule": crontab(hour=8, minute=0),
        },
        # Lease expiry alerts at 90, 60, 30 and 14 days out.
        "send-lease-expiry-alerts": {
            "task": "rentflow.send_lease_expiry_alerts",
            "schedule": crontab(hour=8, minute=30),
        },
        # Recompute date-driven tenancy statuses (expiring soon / expired).
        "refresh-tenancy-statuses": {
            "task": "rentflow.refresh_tenancy_statuses",
            "schedule": crontab(hour=0, minute=15),
        },
        # Trial expiry nudges at 7, 3 and 1 days remaining.
        "send-trial-reminders": {
            "task": "rentflow.send_trial_reminders",
            "schedule": crontab(hour=9, minute=0),
        },
        # Daily caretaker activity digest to owners, 7pm Nairobi time.
        "caretaker-daily-summary": {
            "task": "rentflow.caretaker_daily_summary",
            "schedule": crontab(hour=19, minute=0),
        },
        # Recover payments whose Daraja callback never arrived.
        "reconcile-pending-payments": {
            "task": "rentflow.reconcile_pending_payments",
            "schedule": crontab(minute="*/15"),
        },
        # Purge accounts past their deletion grace period.
        "purge-deleted-accounts": {
            "task": "rentflow.purge_deleted_accounts",
            "schedule": crontab(hour=2, minute=0),
        },
        # Phase 2: Apply late fees to overdue invoices daily.
        "apply-late-fees": {
            "task": "rentflow.apply_late_fees",
            "schedule": crontab(hour=7, minute=0),
        },
        # Phase 2: Send lease renewal notices at 30-day mark.
        "send-lease-renewal-notices": {
            "task": "rentflow.send_lease_renewal_notices",
            "schedule": crontab(hour=8, minute=45),
        },
        # Phase 2: Remind agency admins of scheduled disbursements.
        "process-scheduled-disbursements": {
            "task": "rentflow.process_scheduled_disbursements",
            "schedule": crontab(hour=7, minute=30),
        },
        # Phase 2: Escalate arrears into formal demand letters at 60 and 90 days.
        # Runs after late fees so a letter states the fee-inclusive balance.
        "issue-demand-letters": {
            "task": "rentflow.issue_demand_letters",
            "schedule": crontab(hour=7, minute=15),
        },
        # Phase 2: Offer lease renewals 30 days out, escalate silence at 14.
        "offer-lease-renewals": {
            "task": "rentflow.offer_lease_renewals",
            "schedule": crontab(hour=8, minute=15),
        },
        # Phase 3: Flag maintenance jobs past their expected completion date.
        # Early, so the overdue list is already correct when the office opens.
        "flag-overdue-maintenance": {
            "task": "rentflow.flag_overdue_maintenance",
            "schedule": crontab(hour=6, minute=30),
        },
        # Phase 3: The compliance reminder ladder, first thing.
        "sweep-compliance-expiry": {
            "task": "rentflow.sweep_compliance_expiry",
            "schedule": crontab(hour=6, minute=0),
        },
        # Phase 3: The building's own utility bills, weekly on a Monday.
        "sweep-overdue-utilities": {
            "task": "rentflow.sweep_overdue_utilities",
            "schedule": crontab(day_of_week=1, hour=8, minute=0),
        },
        # Phase 3: The monthly data export, on the 1st, before the office opens.
        "monthly-data-export": {
            "task": "rentflow.monthly_data_export",
            "schedule": crontab(day_of_month=1, hour=5, minute=0),
        },
        # Phase 3: Nudge the office about vacancy leads that have gone cold.
        "chase-stale-leads": {
            "task": "rentflow.chase_stale_leads",
            "schedule": crontab(hour=9, minute=30),
        },
        # Phase 3: Close out landlord references that were never answered.
        "sweep-stale-references": {
            "task": "rentflow.sweep_stale_references",
            "schedule": crontab(hour=6, minute=45),
        },
        # Phase 2: Keep the task monitoring history to its retention window.
        "prune-task-runs": {
            "task": "rentflow.prune_task_runs",
            "schedule": crontab(hour=3, minute=30),
        },
        # Phase 2: Retry eTIMS submissions KRA rejected or never answered.
        # Every 15 minutes because the backoff is in the row, not the schedule.
        "retry-etims-submissions": {
            "task": "rentflow.retry_etims_submissions",
            "schedule": crontab(minute="*/15"),
        },
    },
)
