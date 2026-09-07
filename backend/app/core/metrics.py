"""Prometheus metrics: HTTP request health, and the scheduled-task fleet.

Two sources, one `/metrics` endpoint:

  * **HTTP** — `prometheus-fastapi-instrumentator` records request count and
    latency, labelled by route template, method and status, into the process's
    default registry. Instrumented via `.instrument(app)` only, deliberately
    not `.expose(app)`: `expose()` mounts its own synchronous `/metrics` route,
    and this app needs `/metrics` to also carry the task-health gauges below,
    which require an async database read. One route, both sources.
  * **Scheduled tasks** — 27 Celery beat jobs already write one `TaskRun` row
    per execution, read back by `task_monitor_service.overview` for the admin
    dashboard. Rather than a second, parallel notion of task health, the metrics
    endpoint calls that exact function and turns its answer into gauges — a
    task Prometheus calls broken and a task the dashboard calls broken are
    always the same task, because they are the same query.

Gated by `METRICS_TOKEN` when one is set: `/metrics` reveals route names, call
volume and which internal jobs exist, which is internal topology a public
droplet should not hand out for free. Left open when unset, which is the
convenient default for a local scrape and for tests.
"""

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Gauge, generate_latest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

# Registered once, at import time, and reset to the current fleet on every
# scrape — a Gauge is a snapshot, not a counter, so a task that stops being
# scheduled must stop reporting a stale "healthy" reading rather than being
# silently frozen at its last value.
_TASK_LAST_RUN_SUCCESS = Gauge(
    "rentflow_task_last_run_success",
    "1 if the task's most recent run succeeded, 0 if it failed, absent if it has never run.",
    ["task_name"],
)
_TASK_LAST_DURATION_SECONDS = Gauge(
    "rentflow_task_last_duration_seconds",
    "Duration of the task's most recent completed run.",
    ["task_name"],
)
_TASK_FAILURES_7D = Gauge(
    "rentflow_task_failures_7d",
    "Failed runs of this task in the last 7 days.",
    ["task_name"],
)
_TASK_BROKEN = Gauge(
    "rentflow_task_broken",
    "1 if the task's last 3 runs all failed (alert threshold), else 0.",
    ["task_name"],
)


def instrument_app(app: FastAPI) -> None:
    """Record HTTP metrics into the default registry. No-op without the
    optional dependency, same contract as Sentry and tracing."""
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:
        return

    Instrumentator(
        excluded_handlers=["/metrics", "/api/v1/health", "/docs", "/redoc", "/openapi.json"],
        should_group_status_codes=True,
        should_ignore_untemplated=True,
    ).instrument(app)


async def _refresh_task_gauges(db: AsyncSession) -> None:
    from app.services import task_monitor_service

    report = await task_monitor_service.overview(db)

    # Clear anything from a previous scrape whose task no longer appears —
    # otherwise a renamed or removed task reports its last reading forever.
    for gauge in (_TASK_LAST_RUN_SUCCESS, _TASK_LAST_DURATION_SECONDS, _TASK_FAILURES_7D, _TASK_BROKEN):
        gauge.clear()

    for task in report["tasks"]:
        labels = {"task_name": task["task_name"]}
        if task["last_status"] is not None:
            _TASK_LAST_RUN_SUCCESS.labels(**labels).set(1 if task["last_status"] == "succeeded" else 0)
        if task["last_duration_seconds"] is not None:
            _TASK_LAST_DURATION_SECONDS.labels(**labels).set(task["last_duration_seconds"])
        _TASK_FAILURES_7D.labels(**labels).set(task["failures_7d"])
        _TASK_BROKEN.labels(**labels).set(1 if task["health"] == "broken" else 0)


def _check_token(request: Request) -> None:
    if not settings.METRICS_TOKEN:
        return
    header = request.headers.get("authorization", "")
    if header != f"Bearer {settings.METRICS_TOKEN}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid metrics token")


async def metrics_endpoint(
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(_check_token),
) -> Response:
    await _refresh_task_gauges(db)
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
