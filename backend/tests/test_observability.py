"""Observability: request correlation, structured logs, and /metrics.

An enterprise buyer's security questionnaire asks two things about this
category, and both are what this file checks: can you find every log line for
one request across three processes (API, worker, beat), and can you point a
Prometheus at this app and get something real back.
"""

import json
import logging
import uuid

import pytest
from httpx import AsyncClient

from app.core import metrics as metrics_module
from app.core.config import settings
from app.core.logging import JsonFormatter, RequestIdFilter
from app.core.observability import configure_tracing
from app.core.request_context import REQUEST_ID_HEADER, bind_request_id, get_request_id, reset_request_id
from tests.conftest import Actor

# ------------------------------------------------------------------ request id


async def test_a_response_always_carries_a_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]


async def test_the_callers_own_request_id_is_echoed_back(client: AsyncClient) -> None:
    """A client's own retry logs and this app's logs should share one id,
    rather than the app silently minting a second one."""
    mine = uuid.uuid4().hex

    response = await client.get("/api/v1/health", headers={REQUEST_ID_HEADER: mine})

    assert response.headers[REQUEST_ID_HEADER] == mine


async def test_two_requests_never_share_a_request_id(client: AsyncClient) -> None:
    first = await client.get("/api/v1/health")
    second = await client.get("/api/v1/health")

    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


async def test_a_rejected_request_still_carries_a_request_id(owner: Actor) -> None:
    """The middleware is outermost of all — even a 403 gets one, because that
    is exactly the response a support ticket quotes."""
    response = await owner.get("/api/v1/agency/dashboard")

    assert response.headers.get(REQUEST_ID_HEADER)


# --------------------------------------------------------------- log format


def _record(message: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="rentflow.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_the_request_id_filter_attaches_the_current_context_value() -> None:
    token = bind_request_id("req-abc123")
    try:
        record = _record()
        assert RequestIdFilter().filter(record) is True
        assert record.request_id == "req-abc123"
    finally:
        reset_request_id(token)


def test_the_request_id_filter_uses_a_placeholder_outside_any_request() -> None:
    assert get_request_id() is None
    record = _record()
    RequestIdFilter().filter(record)
    assert record.request_id == "-"


def test_json_formatter_produces_one_parseable_object_with_the_expected_keys() -> None:
    token = bind_request_id("req-xyz")
    try:
        record = _record("payment recorded", tenancy_id="t-1", amount="25000.00")
        line = JsonFormatter().format(record)
    finally:
        reset_request_id(token)

    parsed = json.loads(line)
    assert parsed["message"] == "payment recorded"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "rentflow.test"
    assert parsed["request_id"] == "req-xyz"
    # extra= fields a caller passed are carried through, not dropped.
    assert parsed["tenancy_id"] == "t-1"
    assert parsed["amount"] == "25000.00"
    assert "timestamp" in parsed


def test_json_formatter_serialises_an_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record("failed")
        record.exc_info = sys.exc_info()

    parsed = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in parsed["exception"]


def test_json_formatter_does_not_choke_on_an_unserialisable_extra_value() -> None:
    """A logging call is never allowed to crash the thing it is logging about."""
    record = _record("weird", thing=object())

    line = JsonFormatter().format(record)

    parsed = json.loads(line)
    assert "thing" in parsed


# --------------------------------------------------------------------- tracing


def test_configure_tracing_is_a_no_op_without_an_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", None)

    assert configure_tracing("test") is False


# --------------------------------------------------------------------- metrics


async def test_metrics_endpoint_is_open_by_default_and_returns_prometheus_text(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "METRICS_TOKEN", None)

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


async def test_metrics_include_the_scheduled_task_gauges(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "METRICS_TOKEN", None)

    response = await client.get("/metrics")

    # The gauge names exist even with zero task runs recorded — a gauge that
    # only appears once something has gone wrong is a gauge nobody can alert
    # on, since "the metric is missing" and "everything is fine" look the same.
    body = response.text
    assert "rentflow_task_broken" in body
    assert "rentflow_task_failures_7d" in body


async def test_metrics_endpoint_requires_the_token_once_one_is_set(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "METRICS_TOKEN", "shh-secret")

    unauthenticated = await client.get("/metrics")
    assert unauthenticated.status_code == 401

    authenticated = await client.get("/metrics", headers={"Authorization": "Bearer shh-secret"})
    assert authenticated.status_code == 200


def test_instrument_app_is_a_no_op_without_the_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors the contract every optional integration in this codebase keeps:
    missing the package must never be the reason the app fails to start."""
    import builtins

    real_import = builtins.__import__

    def blocked(name: str, *args: object, **kwargs: object):
        if name == "prometheus_fastapi_instrumentator":
            raise ImportError("simulated: package not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)

    from fastapi import FastAPI

    metrics_module.instrument_app(FastAPI())  # must not raise
