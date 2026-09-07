"""Structured logging: JSON in production, human-readable in development.

A log line that cannot be parsed cannot be aggregated, alerted on or searched —
which is what "centralized logging" actually means once a platform has more
than one process writing logs (this one has an API, a Celery worker and a Celery
beat scheduler, each restarted and scaled independently). `JsonFormatter` below
emits one JSON object per line: timestamp, level, logger name, message,
`request_id` and, when a trace is active, `trace_id`/`span_id` — the join keys a
log aggregator (CloudWatch Logs Insights, Loki, Datadog) needs to pull every log
line for one request, or line up a slow request against its trace.

`request_id` is populated from `app.core.request_context`, which both the HTTP
middleware and the Celery task-run signal handler set — see that module's
docstring for why it is a contextvar rather than a function parameter.

Format is controlled by `LOG_FORMAT`, not hardcoded to `DEBUG`: a developer
debugging locally may still want JSON to test a log-parsing rule, and
`DEBUG=true` genuinely means something different in production emergencies
(verbose SQL echo) than the log line shape does. The default — human-readable
outside DEBUG, JSON only when asked for — is what every project boots with
without config, and `LOG_FORMAT=json` is what the production deploy sets.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.request_context import get_request_id

# Attributes stdlib LogRecord always carries — anything else in a record's
# __dict__ came from a caller's `extra={...}` and is worth including.
_STANDARD_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__)


class RequestIdFilter(logging.Filter):
    """Attach the current request/task id to every record, even in the
    human-readable format — so a developer can grep a local log by it too."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or get_request_id() or "-",
        }

        trace_ids = _current_trace_ids()
        if trace_ids:
            payload.update(trace_ids)

        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS or key in payload:
                continue
            # Anything a caller passed via `extra=`. Kept best-effort: a value
            # that cannot serialise must not be the reason a log line is lost.
            try:
                json.dumps(value)
            except TypeError:
                value = str(value)
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def _current_trace_ids() -> dict[str, str] | None:
    """The active OpenTelemetry trace/span id, if tracing is configured and a
    span is open. Absent either condition, this is a no-op — logging must not
    depend on tracing being installed."""
    try:
        from opentelemetry import trace
    except ImportError:
        return None

    span = trace.get_current_span()
    context = span.get_span_context()
    if not context.is_valid:
        return None
    return {
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x"),
    }


def configure_logging(debug: bool, log_format: str = "console") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())

    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO if debug else logging.WARNING)

    # We don't use create_async_engine(echo=True) because it attaches SQLAlchemy's
    # own handler directly to this logger (bypassing our config) and causes double
    # logging once records also propagate to root. Controlling the level directly
    # gives us SQL echo in debug mode through the single handler above.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO if debug else logging.WARNING)
