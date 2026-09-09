import contextvars

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_postrun, task_prerun

from app.core.config import settings
from app.core.observability import configure_sentry, configure_tracing
from app.core.request_context import bind_request_id, reset_request_id

# Workers are a separate process from the API and fail in different ways —
# a beat task that has been silently erroring for a week is exactly what
# error tracking is for.
configure_sentry("worker")
# No `fastapi_app` — there is no app here to instrument, only the SQLAlchemy
# engine, httpx and the task graph itself.
configure_tracing("worker")

_request_id_tokens: dict[str, contextvars.Token[str | None]] = {}


@task_prerun.connect
def _bind_task_request_id(task_id: str, **_kwargs) -> None:
    """Give every task run the same correlation id an HTTP request gets.

    Celery's own broker-assigned task id is already unique per run, so it is
    reused directly rather than minting a second id nobody would look up by —
    the same id that would appear in `celery_worker` logs, in Flower, and in
    any retry, is the one now stamped on every log line the task's own work
    emits.
    """
    _request_id_tokens[task_id] = bind_request_id(task_id)


@task_postrun.connect
def _unbind_task_request_id(task_id: str, **_kwargs) -> None:
    token = _request_id_tokens.pop(task_id, None)
    if token is not None:
        reset_request_id(token)


celery_app = Celery(
    "rentflow",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
    include=["app.tasks.scheduled", "app.tasks.webhooks", "app.tasks.customer_success"],
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
        # Settle owners who are on daily disbursement, for rent that cleared
        # yesterday. Early enough that the money is with them before the working
        # day, and after the 00:15 status refresh so the period is closed.
        "process-daily-disbursements": {
            "task": "rentflow.process_daily_disbursements",
            "schedule": crontab(hour=6, minute=30),
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
        # Sprint 20: weekly customer health scoring, Monday before the office opens.
        "compute-health-scores": {
            "task": "rentflow.compute_health_scores",
            "schedule": crontab(day_of_week=1, hour=5, minute=30),
        },
        # Sprint 21: the automatic monthly summary, right after the data export.
        "monthly-owner-report": {
            "task": "rentflow.monthly_owner_report",
            "schedule": crontab(day_of_month=1, hour=5, minute=30),
        },
        # Sprint 21: any saved custom report scheduled for today.
        "run-scheduled-custom-reports": {
            "task": "rentflow.run_scheduled_custom_reports",
            "schedule": crontab(hour=6, minute=15),
        },
        # Sprint 22: daily failed-login summary per account.
        "send-failed-login-digest": {
            "task": "rentflow.send_failed_login_digest",
            "schedule": crontab(hour=7, minute=45),
        },
        # Sprint 22: nudge accounts to rotate an API key past its rotation window.
        "remind-api-key-rotation": {
            "task": "rentflow.remind_api_key_rotation",
            "schedule": crontab(hour=9, minute=15),
        },
        # Sprint 23: push unsynced payments, maintenance costs and disbursements
        # to every connected QuickBooks/Xero company.
        "sync-accounting-connections": {
            "task": "rentflow.sync_accounting_connections",
            "schedule": crontab(hour=4, minute=30),
        },
        # Sprint 26: end management agreements whose notice period has run.
        # Just after midnight so an agreement effective "today" is closed on
        # the day, before the disbursement and invoicing runs read it.
        "complete-management-agreement-terminations": {
            "task": "rentflow.complete_management_agreement_terminations",
            "schedule": crontab(hour=0, minute=30),
        },
        # Sprint 26: escalate any breach whose 72-hour notification window is
        # running down. Hourly, because the deadline is legal and a daily
        # sweep could burn a fifth of the window before anyone was told.
        "escalate-breach-notifications": {
            "task": "rentflow.escalate_breach_notifications",
            "schedule": crontab(minute=5),
        },
        # Sprint 26: look for breach-shaped patterns in authentication and
        # export telemetry. Every 15 minutes, matching the payment reconciler.
        "scan-for-breach-candidates": {
            "task": "rentflow.scan_for_breach_candidates",
            "schedule": crontab(minute="*/15"),
        },
        # Sprint 26A: redact personal data past its retention window — see
        # docs/legal/data-retention-policy.md. Monthly, same slot as the data
        # export, since both are "start of month" housekeeping.
        "sweep-data-retention": {
            "task": "rentflow.sweep_data_retention",
            "schedule": crontab(day_of_month=1, hour=5, minute=45),
        },
        # Sprint 26A: extend the audit log's hash chain over whatever was
        # written since the last run. Every 10 minutes — frequent enough that
        # "unchained" never means much more than "very recent."
        "chain-audit-log-entries": {
            "task": "rentflow.chain_audit_log_entries",
            "schedule": crontab(minute="*/10"),
        },
        # Sprint 26A: Parquet drops for organisations that opted into BI
        # export. Weekly (Monday, after the monthly export's own slot has
        # cleared) rather than daily — a warehouse team pulls on their own
        # schedule and does not need same-day freshness from this job.
        "run-bi-exports": {
            "task": "rentflow.run_bi_exports",
            "schedule": crontab(day_of_week=1, hour=5, minute=15),
        },
    },
)
