"""Scheduled data retention (Sprint 26A) — see `docs/legal/data-retention-policy.md`.

Four categories, one sweep, run monthly by `app.tasks.scheduled.sweep_data_retention`:

  * Tenant personal data, once a tenant has had no live tenancy for
    `TENANT_RETENTION_YEARS` — redacted the same way a tenant-requested
    erasure redacts it (`privacy_service.redact_tenant_fields`).
  * Rejected/withdrawn applications, `APPLICATION_RETENTION_DAYS` after the
    decision — no ongoing relationship exists to justify keeping them longer.
  * Security events, `SECURITY_EVENT_RETENTION_DAYS` old — hard-deleted; there
    is no financial or audit-trail reason to keep these past their window,
    unlike everything else this sweep touches.
  * Demo datasets nobody removed, `DEMO_DATASET_RETENTION_DAYS` after seeding
    — torn down the same way an explicit removal would.

Every category checks `legal_hold_service.active_hold` before acting, and
skips whatever it covers. Financial records (`Invoice`, `Payment`) and audit
logs are never touched here — they are not this sweep's job, and
`privacy_service`'s own erasure already draws that same line.
"""

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import ApplicationStatus, TenantApplication
from app.models.demo import DemoDataset
from app.models.security import SecurityEvent
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.services import legal_hold_service, privacy_service

logger = logging.getLogger("rentflow.retention")

TENANT_RETENTION_YEARS = 2
APPLICATION_RETENTION_DAYS = 365
SECURITY_EVENT_RETENTION_DAYS = 365
DEMO_DATASET_RETENTION_DAYS = 30

_LIVE_TENANCY_STATUSES = [
    TenancyStatus.ACTIVE,
    TenancyStatus.EXPIRING_SOON,
    TenancyStatus.NOTICE_GIVEN,
]


async def _tenants_past_retention(db: AsyncSession) -> list[Tenant]:
    cutoff = date.today() - timedelta(days=365 * TENANT_RETENTION_YEARS)
    last_end = (
        select(Tenancy.tenant_id, func.max(Tenancy.end_date).label("last_end"))
        .group_by(Tenancy.tenant_id)
        .subquery()
    )
    live_tenant_ids = select(Tenancy.tenant_id).where(Tenancy.status.in_(_LIVE_TENANCY_STATUSES))
    query = (
        select(Tenant)
        .join(last_end, last_end.c.tenant_id == Tenant.id)
        .where(
            Tenant.erased_at.is_(None),
            last_end.c.last_end.isnot(None),
            last_end.c.last_end < cutoff,
            Tenant.id.notin_(live_tenant_ids),
        )
    )
    return list(await db.scalars(query))


async def sweep_tenants(db: AsyncSession) -> int:
    redacted = 0
    for tenant in await _tenants_past_retention(db):
        hold = await legal_hold_service.active_hold(db, tenant.organization_id, "tenant", tenant.id)
        if hold is not None:
            continue
        await privacy_service.redact_tenant_fields(db, tenant)
        redacted += 1
    return redacted


async def _stale_applications(db: AsyncSession) -> list[TenantApplication]:
    cutoff = datetime.now(UTC) - timedelta(days=APPLICATION_RETENTION_DAYS)
    query = select(TenantApplication).where(
        TenantApplication.status.in_([ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN]),
        TenantApplication.decided_at.isnot(None),
        TenantApplication.decided_at < cutoff,
        TenantApplication.full_name != "Redacted applicant",
    )
    return list(await db.scalars(query))


async def sweep_applications(db: AsyncSession) -> int:
    redacted = 0
    for application in await _stale_applications(db):
        hold = await legal_hold_service.active_hold(
            db, application.organization_id, "application", application.id
        )
        if hold is not None:
            continue
        application.full_name = "Redacted applicant"
        application.phone_number = f"redacted-{application.id.hex[:12]}"
        application.email = None
        application.national_id = None
        application.date_of_birth = None
        application.current_address = None
        application.current_landlord_name = None
        application.current_landlord_phone = None
        application.employer_name = None
        redacted += 1
    return redacted


async def sweep_security_events(db: AsyncSession) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=SECURITY_EVENT_RETENTION_DAYS)
    stale = list(await db.scalars(select(SecurityEvent).where(SecurityEvent.created_at < cutoff)))
    for event in stale:
        await db.delete(event)
    return len(stale)


async def sweep_demo_datasets(db: AsyncSession) -> int:
    from app.services import demo_service

    cutoff = datetime.now(UTC) - timedelta(days=DEMO_DATASET_RETENTION_DAYS)
    stale = list(
        await db.scalars(
            select(DemoDataset).where(DemoDataset.removed_at.is_(None), DemoDataset.created_at < cutoff)
        )
    )
    torn_down = 0
    for dataset in stale:
        try:
            await demo_service.remove_for_organization(db, dataset.organization_id, actor=None, commit=False)
            torn_down += 1
        except Exception:  # noqa: BLE001 — one bad dataset should not stop the sweep
            logger.exception("Failed to tear down abandoned demo dataset %s", dataset.id)
    return torn_down


async def sweep(db: AsyncSession) -> dict[str, int]:
    """Run every retention category and commit once, so a mid-sweep failure
    cannot leave one category redacted and another untouched for the same run."""
    result = {
        "tenants_redacted": await sweep_tenants(db),
        "applications_redacted": await sweep_applications(db),
        "security_events_deleted": await sweep_security_events(db),
        "demo_datasets_removed": await sweep_demo_datasets(db),
    }
    await db.commit()
    return result
