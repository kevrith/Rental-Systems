"""Scheduled task telemetry — Phase 2 (US-056).

Celery Beat runs a dozen jobs a day that nobody watches. When invoice generation
stops firing, the first sign today is a landlord asking why nobody was billed.
One row per run turns that into something a dashboard can answer, and gives the
retry endpoint something to point at.

Deliberately not organisation-scoped: these tasks sweep every organisation, so a
run belongs to the platform rather than to any one tenant.
"""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class TaskRunStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of one scheduled task."""

    __tablename__ = "task_runs"

    task_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[TaskRunStatus] = mapped_column(
        Enum(TaskRunStatus, name="task_run_status"),
        default=TaskRunStatus.RUNNING,
        nullable=False,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Whatever the task returned — counts of what it did, so the dashboard can
    # show "generated 42 invoices" rather than a bare green tick.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set when a person pressed "run now" instead of Beat firing it.
    triggered_manually: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
