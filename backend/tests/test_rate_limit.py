"""Application rate limiting (Sprint 26).

The public API-key surface has been metered since Sprint 19; the app's own
endpoints had nothing in front of them but the login lockout. These cases turn
the limiter back on — `conftest.no_rate_limit` disables it for every other
file — and check the three things that would make it either useless or
actively harmful:

  * an unauthenticated caller is bounded, and told when to come back;
  * two different users do not share a bucket, so one busy account cannot
    lock out another;
  * Redis being unreachable lets requests through rather than taking the API
    down with it.
"""

import pytest
from httpx import AsyncClient

from app.core import rate_limit
from app.core.config import settings
from tests.conftest import Actor


@pytest.fixture(autouse=True)
def enable_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    # Small enough to hit in a handful of requests, which keeps these fast.
    monkeypatch.setattr(settings, "RATE_LIMIT_ANONYMOUS_PER_MINUTE", 3)
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTHENTICATED_PER_MINUTE", 5)
    monkeypatch.setattr(settings, "RATE_LIMIT_EXPENSIVE_PER_MINUTE", 2)


async def test_an_anonymous_caller_is_bounded_and_told_when_to_retry(
    client: AsyncClient,
) -> None:
    path = "/api/v1/listings/does-not-exist"

    for _ in range(settings.RATE_LIMIT_ANONYMOUS_PER_MINUTE):
        assert (await client.get(path)).status_code != 429

    limited = await client.get(path)
    assert limited.status_code == 429
    assert limited.headers["Retry-After"].isdigit()
    assert limited.headers["X-RateLimit-Remaining"] == "0"


async def test_remaining_budget_is_reported_on_every_response(owner: Actor) -> None:
    response = await owner.get("/api/v1/properties")

    assert response.status_code == 200
    assert int(response.headers["X-RateLimit-Limit"]) == settings.RATE_LIMIT_AUTHENTICATED_PER_MINUTE
    assert int(response.headers["X-RateLimit-Remaining"]) >= 0


async def test_two_users_do_not_share_a_bucket(owner: Actor, other_owner: Actor) -> None:
    """Keyed on the user id from the token. If the bucket were per-IP, one busy
    account would lock out every other customer behind the same proxy."""
    for _ in range(settings.RATE_LIMIT_AUTHENTICATED_PER_MINUTE + 1):
        await owner.get("/api/v1/properties")

    assert (await owner.get("/api/v1/properties")).status_code == 429
    assert (await other_owner.get("/api/v1/properties")).status_code == 200


async def test_an_expensive_endpoint_has_a_tighter_ceiling(client: AsyncClient) -> None:
    """Every one of these sends a real SMS or renders a real PDF, and the cost
    lands on the bill rather than on the load average."""
    payload = {"phone_number": "+254700000999"}

    for _ in range(settings.RATE_LIMIT_EXPENSIVE_PER_MINUTE):
        response = await client.post("/api/v1/portal/magic-link", json=payload)
        assert response.status_code != 429

    limited = await client.post("/api/v1/portal/magic-link", json=payload)
    assert limited.status_code == 429


async def test_health_checks_are_never_limited(client: AsyncClient) -> None:
    """A load balancer uses this to decide whether the process is alive."""
    for _ in range(settings.RATE_LIMIT_ANONYMOUS_PER_MINUTE * 3):
        assert (await client.get("/api/v1/health")).status_code == 200


async def test_the_external_api_keeps_its_own_meter(client: AsyncClient) -> None:
    """It is billed against the organisation's own quota; limiting it here too
    would silently halve what a customer paid for."""
    for _ in range(settings.RATE_LIMIT_ANONYMOUS_PER_MINUTE * 2):
        response = await client.get("/api/v1/external/properties")
        # Unauthenticated, so 401 — but never 429 from this middleware.
        assert response.status_code != 429


async def test_a_forged_token_falls_back_to_the_stricter_ip_bucket(
    client: AsyncClient,
) -> None:
    headers = {"Authorization": "Bearer not-a-real-token"}

    for _ in range(settings.RATE_LIMIT_ANONYMOUS_PER_MINUTE):
        await client.get("/api/v1/properties", headers=headers)

    limited = await client.get("/api/v1/properties", headers=headers)
    assert limited.status_code == 429
    assert int(limited.headers["X-RateLimit-Limit"]) == settings.RATE_LIMIT_ANONYMOUS_PER_MINUTE


async def test_the_limiter_fails_open_when_redis_is_unreachable(
    owner: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rate limiter that takes the whole API down when its cache is
    unreachable has done more damage than the abuse it was there to prevent."""

    async def explode(*_args, **_kwargs):
        raise ConnectionError("Redis is down")

    monkeypatch.setattr(rate_limit.redis_client, "incr", explode)

    response = await owner.get("/api/v1/properties")

    assert response.status_code == 200


async def test_a_rate_limited_response_still_carries_the_security_headers(
    client: AsyncClient,
) -> None:
    """The limiter sits inside the header middleware, so a 429 is not the one
    response that ships without them."""
    path = "/api/v1/listings/does-not-exist"
    for _ in range(settings.RATE_LIMIT_ANONYMOUS_PER_MINUTE + 1):
        await client.get(path)

    limited = await client.get(path)

    assert limited.status_code == 429
    assert limited.headers["X-Content-Type-Options"] == "nosniff"
    assert limited.headers["X-Frame-Options"] == "DENY"


async def test_reading_an_expensive_path_uses_the_ordinary_budget(owner: Actor) -> None:
    """Rendering a report costs money; listing the saved ones does not. The
    expensive tier applies to the POST, not to the whole prefix."""
    for _ in range(settings.RATE_LIMIT_EXPENSIVE_PER_MINUTE + 1):
        response = await owner.get("/api/v1/reports")
        assert response.status_code != 429
        assert int(response.headers["X-RateLimit-Limit"]) == settings.RATE_LIMIT_AUTHENTICATED_PER_MINUTE
