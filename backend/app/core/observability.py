"""Error tracking via Sentry, and distributed tracing via OpenTelemetry.

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
on Sentry being reachable. `configure_tracing` below follows the identical
contract for OpenTelemetry: absent `OTEL_EXPORTER_OTLP_ENDPOINT`, it does
nothing, and every span the app would otherwise create becomes a genuine no-op
(the OTel SDK's default tracer already is one — this module never installs a
tracer provider at all unless a collector is actually configured to receive
spans).
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


def _scrub(event: Any, _hint: dict[str, Any]) -> Any:
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


def configure_tracing(component: str = "api", *, fastapi_app: Any | None = None) -> bool:
    """Wire up OpenTelemetry tracing if an OTLP collector endpoint is configured.

    Three things are instrumented, each answering a different "where did the
    time go" question a slow request raises: FastAPI (when `fastapi_app` is
    given — the Celery worker has no app to instrument), the SQLAlchemy engine
    (every query becomes a child span, which is what turns "this endpoint is
    slow" into "this endpoint is slow because of this query"), and httpx (every
    outbound call this app makes to M-Pesa, WhatsApp, Africa's Talking or the
    Anthropic API — the other place latency hides that a database span cannot
    show).

    The SQLAlchemy engine is instrumented by explicit reference
    (`app.core.database.engine.sync_engine`) rather than by letting the
    instrumentor patch `create_async_engine` globally. The patch-based approach
    only catches engines created *after* `.instrument()` runs, and this
    function is called after `app.core.database` has already created its
    module-level engine — so the explicit reference is not a style choice, it
    is the only way this actually attaches.
    """
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("OTEL_EXPORTER_OTLP_ENDPOINT is set but the opentelemetry packages are not installed")
        return False

    # A provider is process-global; a second call (the Celery worker importing
    # this module once per fork, say) must not double-instrument the same
    # engine, which would emit every query span twice.
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return True

    resource = Resource.create(
        {SERVICE_NAME: f"rentflow-{component}", "deployment.environment": settings.ENVIRONMENT}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT))
    )
    trace.set_tracer_provider(provider)

    from app.core.database import engine as db_engine

    SQLAlchemyInstrumentor().instrument(engine=db_engine.sync_engine)
    HTTPXClientInstrumentor().instrument()
    CeleryInstrumentor().instrument()

    if fastapi_app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(fastapi_app)

    logger.info("OpenTelemetry tracing enabled for %s -> %s", component, settings.OTEL_EXPORTER_OTLP_ENDPOINT)
    return True
