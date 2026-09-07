"""Request correlation: one id that ties a log line, a trace and a support
ticket together.

Every log line this app emits — an API request, a Celery beat task, a webhook
delivery — carries a `request_id`. For an HTTP request it is either the caller's
own `X-Request-ID` (so a client's retry logs and this app's logs share one id)
or one generated here. For a Celery task it is the task's own broker-assigned
id, set by `bind_task_id` from a `task_prerun` signal in `celery_app.py`.

The id lives in a `contextvars.ContextVar` rather than being threaded through
every function signature. That is what lets `app.core.logging`'s formatter pick
it up in any log call, anywhere in the request's call graph, without every
service function taking a `request_id` parameter it would otherwise have no use
for.

Kept in its own module, separate from `logging.py`, so `main.py`'s middleware
and `celery_app.py`'s signal handler can both import the contextvar without
either importing the other's setup code.
"""

import contextvars
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def new_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str | None:
    return _request_id.get()


def bind_request_id(value: str | None) -> contextvars.Token[str | None]:
    """Set the id for the current context. Returns a token for `reset`.

    Used both by the HTTP middleware (per request) and by the Celery signal
    handler (per task run) — the two places a "unit of work" begins.
    """
    return _request_id.set(value)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    _request_id.reset(token)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Bind a correlation id to every request and echo it back.

    Reuses the caller's own `X-Request-ID` when it sends one — a client that
    retries a request, or a reverse proxy that already minted one, wants its
    logs and this app's logs to share the same id. Otherwise a fresh one is
    generated. Either way the id is on the response so a support conversation
    ("the app said something went wrong at 14:32") can name it precisely.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_id()
        token = bind_request_id(request_id)
        try:
            _tag_sentry(request_id)
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def _tag_sentry(request_id: str) -> None:
    """Best-effort — Sentry may not be configured, and that must never be
    the reason a request fails."""
    try:
        import sentry_sdk
    except ImportError:
        return
    sentry_sdk.set_tag("request_id", request_id)
