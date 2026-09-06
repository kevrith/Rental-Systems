"""Weekly customer health scoring (Sprint 20, US-091)."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.services.task_monitor_service import monitored
from app.tasks.celery_app import celery_app
from app.tasks.scheduled import run_async

logger = logging.getLogger("rentflow.tasks")


@celery_app.task(name="rentflow.compute_health_scores")
@monitored("rentflow.compute_health_scores")
def compute_health_scores() -> dict[str, int]:
    from app.services import health_score_service

    async def work(db: AsyncSession) -> int:
        computed = 0
        organizations = await db.scalars(select(Organization).where(Organization.is_active.is_(True)))
        for organization in organizations:
            await health_score_service.compute_for_organization(db, organization)
            computed += 1
        return computed

    computed = run_async(work)
    logger.info("Computed health scores for %s organization(s)", computed)
    return {"computed": computed}
