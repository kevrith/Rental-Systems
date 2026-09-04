"""Scheduled task monitoring API — Phase 2 (US-056).

The platform's background jobs are what makes the product run on autopilot;
these endpoints are how anyone finds out when one of them has stopped.

Beat tasks sweep every organisation, so what they report is platform state
rather than tenant data. Read access is granted to anyone who can manage an
organisation — an owner is entitled to know whether invoice generation ran —
while re-running a task by hand is reserved for a system administrator, because
it affects every tenant at once.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.user import UserRole
from app.services import task_monitor_service

router = APIRouter()


@router.get("")
async def task_overview(
    limit: int = Query(default=20, ge=1, le=100),
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Every scheduled task with its last run, recent failures and health."""
    return await task_monitor_service.overview(db, limit=limit)


@router.get("/{task_name}/history")
async def task_history(
    task_name: str,
    limit: int = Query(default=50, ge=1, le=200),
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    return await task_monitor_service.history(db, task_name, limit)


@router.post("/{task_name}/run")
async def run_task_now(
    task_name: str,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Re-run a failed task by hand.

    Restricted to system administrators: these tasks act across every
    organisation on the platform, so triggering one is not a per-tenant action.
    """
    if context.user.role != UserRole.SYSTEM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a system administrator can re-run a scheduled task",
        )

    from app.tasks.celery_app import celery_app

    known = {entry["task"] for entry in (celery_app.conf.beat_schedule or {}).values()}
    if task_name not in known:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown task")

    # Queued rather than run inline: some of these sweep the whole platform and
    # would hold the request open for minutes.
    async_result = celery_app.send_task(task_name, kwargs={"_manual": True})
    return {"task_name": task_name, "queued": True, "task_id": str(async_result.id)}
