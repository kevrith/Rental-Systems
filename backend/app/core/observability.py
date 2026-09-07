"""Error tracking via Sentry (Sprint 26).

Sentry has been in the stack list since the masterplan was written and was
never actually wired in, which meant every production exception reached exactly
one place: a log file on the droplet that nobody reads until something is
already broken.

Two things are configured deliberately rather than left at their defaults:

**`send_default_pii` stays off.** This application handles Kenyan tenants'
national ID numbers, phone numbers and payment history, and the Data Protection
Act does not stop applying because the data ended up in an error tracker.
`before_send` additionally scrubs the request body and strips the headers that
carry credentials, so a 500 on a login handler cannot ship a password to a
third party.

**Sampling is low and explicit.** Performance tracing at 100% on a small
droplet costs more than it tells you. Errors are always captured; traces are a
sample.

Absent a DSN this is a no-op, so local development and CI carry no dependency
on Sentry being reachable.
"""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger("rentflow.observability")

# Headers that carry credentials or session material. Removed before an event
# leaves the process.
_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-device-id",
        "proxy-authorization",
    }
)


def _scrub(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    """Strip credentials and request bodies before an event is sent.

    Sentry's own `send_default_pii=False` covers a lot but not the request
    body, which on this API is where the national IDs, phone numbers and
    passwords actually are.
    """
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for name in list(headers):
                if name.lower() in _SENSITIVE_HEADERS:
                    headers[name] = "[redacted]"
    return event


def configure_sentry(component: str = "api") -> bool:
    """Initialise Sentry if a DSN is configured. Returns whether it was.

    `component` distinguishes the API process from the Celery workers in
    Sentry's own UI, which matters because they fail in very different ways.
    """
    if not settings.SENTRY_DSN:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return False

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        # Never. See the module docstring — this is a Kenya DPA obligation, not
        # a preference.
        send_default_pii=False,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
        before_send=_scrub,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            SqlalchemyIntegration(),
            CeleryIntegration(),
        ],
    )
    sentry_sdk.set_tag("component", component)
    logger.info("Sentry error tracking enabled for %s (%s)", component, settings.ENVIRONMENT)
    return True
