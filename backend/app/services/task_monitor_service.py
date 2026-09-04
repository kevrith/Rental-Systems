"""Scheduled task monitoring — Phase 2 (US-056).

Wraps every Celery Beat task so each run leaves a record, and reads those records
back for the admin dashboard. The wrapper is deliberately defensive: telemetry
must never be the reason a task fails, so a failure to record a run is logged and
swallowed while the task itself carries on.

Alerting is by consecutive failure rather than by any single one. A task that
fails once and recovers is noise; a task that has failed every run since Tuesday
is why nobody was invoiced.
"""

import functools
import logging
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.models.task_run import TaskRun, TaskRunStatus

logger = logging.getLogger("rentflow.tasks")

T = TypeVar("T")

# Consecutive failures before a task is called broken on the dashboard.
ALERT_AFTER_CONSECUTIVE_FAILURES = 3
# Runs older than this are pruned; the dashboard only ever shows recent history.
RETENTION_DAYS = 30


@asynccontextmanager
async def _telemetry_session(session: AsyncSession | None):
    """Use the caller's session when there is one, else open a short-lived one.

    A Celery task has no session of its own to lend — its work runs on an engine
    it opens and disposes — so telemetry needs its own connection there. Anywhere
    a session already exists (a test, a request), borrowing it keeps the write in
    the same database and the same transaction boundary.
    """
    if session is not None:
        yield session
        return

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as owned:
            yield owned
    finally:
        await engine.dispose()


async def _start(task_name: str, *, manual: bool, session: AsyncSession | None = None) -> uuid.UUID | None:
    try:
        async with _telemetry_session(session) as db:
            run = TaskRun(
                task_name=task_name,
                status=TaskRunStatus.RUNNING,
                started_at=datetime.now(UTC),
                triggered_manually=manual,
            )
            db.add(run)
            await db.commit()
            return run.id
    except Exception:  # noqa: BLE001 — telemetry must not break the task
        logger.exception("Could not record the start of %s", task_name)
        return None


async def _finish(
    run_id: uuid.UUID | None,
    task_name: str,
    *,
    result: Any = None,
    error: str | None = None,
    session: AsyncSession | None = None,
) -> None:
    if run_id is None:
        return
    try:
        async with _telemetry_session(session) as db:
            run = await db.get(TaskRun, run_id)
            if run is None:
                return
            run.finished_at = datetime.now(UTC)
            run.duration_seconds = (run.finished_at - run.started_at).total_seconds()
            if error is None:
                run.status = TaskRunStatus.SUCCEEDED
                run.result = result if isinstance(result, dict) else {"result": str(result)}
            else:
                run.status = TaskRunStatus.FAILED
                run.error = error[:4000]
            await db.commit()

            if error is not None:
                await _maybe_alert(db, task_name)
    except Exception:  # noqa: BLE001 — telemetry must not break the task
        logger.exception("Could not record the end of %s", task_name)


async def _maybe_alert(db: AsyncSession, task_name: str) -> None:
    """Escalate only once a task is consistently failing, not on a single blip."""
    recent = list(
        await db.scalars(
            select(TaskRun)
            .where(
                TaskRun.task_name == task_name,
                TaskRun.status.in_([TaskRunStatus.SUCCEEDED, TaskRunStatus.FAILED]),
            )
            .order_by(TaskRun.started_at.desc())
            .limit(ALERT_AFTER_CONSECUTIVE_FAILURES)
        )
    )
    if len(recent) < ALERT_AFTER_CONSECUTIVE_FAILURES:
        return
    if any(run.status != TaskRunStatus.FAILED for run in recent):
        return

    # Logged at ERROR so whatever aggregates the platform's logs picks it up; the
    # dashboard shows the same thing to a human.
    logger.error(
        "Scheduled task %s has failed %s consecutive runs. Latest error: %s",
        task_name,
        ALERT_AFTER_CONSECUTIVE_FAILURES,
        recent[0].error,
    )


def monitored(task_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Record every run of a Celery task, including the ones that blow up.

    Applied under `@celery_app.task` so the wrapper sees the real function:

        @celery_app.task(name="rentflow.thing")
        @monitored("rentflow.thing")
        def thing() -> dict: ...
    """

    def decorate(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            import asyncio

            manual = bool(kwargs.pop("_manual", False))
            run_id = asyncio.run(_start(task_name, manual=manual))
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                asyncio.run(_finish(run_id, task_name, error=f"{type(exc).__name__}: {exc}"))
                raise
            asyncio.run(_finish(run_id, task_name, result=result))
            return result

        return wrapper

    return decorate


# ----------------------------------------------------------------- dashboard reads


async def overview(db: AsyncSession, *, limit: int = 20) -> dict:
    """Each known task with its last run, recent failure count, and health."""
    from app.tasks.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule or {}
    scheduled_names = {entry["task"] for entry in schedule.values()}
    schedule_by_task = {entry["task"]: str(entry["schedule"]) for entry in schedule.values()}

    seen = list(await db.scalars(select(TaskRun.task_name).distinct()))
    task_names = sorted(scheduled_names | set(seen))
    since = datetime.now(UTC) - timedelta(days=7)

    # Three grouped queries rather than three per task: this endpoint would get
    # slower every time a task joined the schedule, which is exactly the shape
    # that goes unnoticed until there are forty of them.
    latest_runs: dict[str, list[TaskRun]] = {}
    counts_7d: dict[str, int] = {}
    failures_7d: dict[str, int] = {}

    if task_names:
        ranked = (
            select(
                TaskRun,
                func.row_number()
                .over(partition_by=TaskRun.task_name, order_by=TaskRun.started_at.desc())
                .label("rank"),
            )
            .where(TaskRun.task_name.in_(task_names))
            .subquery()
        )
        recent_run = aliased(TaskRun, ranked)
        for run in await db.scalars(
            select(recent_run).where(ranked.c.rank <= ALERT_AFTER_CONSECUTIVE_FAILURES)
        ):
            latest_runs.setdefault(run.task_name, []).append(run)
        for runs in latest_runs.values():
            runs.sort(key=lambda run: run.started_at, reverse=True)

        for name, run_status, count in await db.execute(
            select(TaskRun.task_name, TaskRun.status, func.count(TaskRun.id))
            .where(TaskRun.task_name.in_(task_names), TaskRun.started_at >= since)
            .group_by(TaskRun.task_name, TaskRun.status)
        ):
            counts_7d[name] = counts_7d.get(name, 0) + count
            if run_status == TaskRunStatus.FAILED:
                failures_7d[name] = failures_7d.get(name, 0) + count

    tasks = []
    for name in task_names:
        runs = latest_runs.get(name, [])
        last = runs[0] if runs else None
        failures = failures_7d.get(name, 0)

        settled = [run for run in runs if run.status != TaskRunStatus.RUNNING]
        broken = len(settled) >= ALERT_AFTER_CONSECUTIVE_FAILURES and all(
            run.status == TaskRunStatus.FAILED for run in settled
        )

        tasks.append(
            {
                "task_name": name,
                "scheduled": name in scheduled_names,
                "schedule": schedule_by_task.get(name),
                "last_status": last.status.value if last else None,
                "last_run_at": last.started_at.isoformat() if last else None,
                "last_duration_seconds": last.duration_seconds if last else None,
                "last_result": last.result if last else None,
                "last_error": last.error if last else None,
                "runs_7d": counts_7d.get(name, 0),
                "failures_7d": failures,
                # Never run at all is its own state — a task Beat has forgotten.
                "health": (
                    "broken"
                    if broken
                    else "never_run" if last is None else ("failing" if failures else "healthy")
                ),
            }
        )

    recent = list(await db.scalars(select(TaskRun).order_by(TaskRun.started_at.desc()).limit(limit)))
    return {
        "tasks": tasks,
        "healthy": sum(1 for t in tasks if t["health"] == "healthy"),
        "failing": sum(1 for t in tasks if t["health"] in {"failing", "broken"}),
        "never_run": sum(1 for t in tasks if t["health"] == "never_run"),
        "recent_runs": [serialize(run) for run in recent],
    }


def serialize(run: TaskRun) -> dict:
    return {
        "id": str(run.id),
        "task_name": run.task_name,
        "status": run.status.value,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_seconds": run.duration_seconds,
        "result": run.result,
        "error": run.error,
        "triggered_manually": run.triggered_manually,
    }


async def history(db: AsyncSession, task_name: str, limit: int = 50) -> list[dict]:
    rows = await db.scalars(
        select(TaskRun).where(TaskRun.task_name == task_name).order_by(TaskRun.started_at.desc()).limit(limit)
    )
    return [serialize(run) for run in rows]


async def prune(db: AsyncSession) -> int:
    """Drop run history older than the retention window."""
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    stale = list(await db.scalars(select(TaskRun).where(TaskRun.started_at < cutoff)))
    for run in stale:
        await db.delete(run)
    await db.commit()
    return len(stale)
