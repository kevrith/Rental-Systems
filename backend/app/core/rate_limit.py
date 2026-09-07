"""Request rate limiting for the authenticated application API.

Until now the only ceiling in this codebase was on the public API-key surface
(`api_key_service`), which left the app's own endpoints — including the ones
that send SMS, generate PDFs and run reports — with nothing in front of them
but the login lockout. A stolen access token, a runaway client retry loop or a
misconfigured integration could all drive unbounded load, and the first anyone
would know is the Africa's Talking bill.

Three tiers, because the right limit is very different per endpoint:

  * **Unauthenticated** — keyed on client IP, and tight. Registration,
    password reset, portal magic links and the public signing and listing
    pages all live here, and every one of them is a thing an attacker would
    enjoy being able to call ten thousand times.
  * **Authenticated** — keyed on the user id from the bearer token, and
    generous. A busy property manager with a dashboard open is not the threat
    model; a compromised token replaying is.
  * **Expensive** — a much lower ceiling for the handful of paths that cost
    real money per call (SMS, PDF rendering, model calls, exports).

The window is a fixed one-minute bucket in Redis, not a sliding log. A fixed
window can let through up to twice the limit across a boundary; a sliding log
costs a sorted-set write and trim per request. At these limits the extra
precision buys nothing that matters and the cheaper primitive is the right
trade — the point is to stop runaway volume, not to meter billing.

Redis being unavailable fails **open**. A rate limiter that takes the whole
API down when its cache is unreachable has done more damage than the abuse it
was there to prevent.
"""

import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.redis import redis_client
from app.core.security import decode_token

logger = logging.getLogger("rentflow.ratelimit")

WINDOW_SECONDS = 60

# Paths that carry their own limiter or must never be limited. The external API
# is metered per API key against the organisation's own quota, and re-limiting
# it here would silently halve a customer's paid ceiling. Health checks are
# what a load balancer uses to decide whether this process is alive.
EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/v1/external",
    "/api/v1/health",
    "/api/v1/mpesa",
    "/docs",
    "/redoc",
    "/openapi.json",
)

# Paths where one request costs real money — an SMS, a rendered PDF, a model
# call, a full export. Matched as a prefix against the path, and only for a
# mutating method: every operation on this list is a POST, and browsing the
# lease templates or the report list is an ordinary read that must not be
# squeezed into the same twenty-a-minute budget as rendering one.
EXPENSIVE_PREFIXES: tuple[str, ...] = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/password-reset",
    "/api/v1/portal/magic-link",
    "/api/v1/meter-readings/read-photo",
    "/api/v1/bulk/import",
    "/api/v1/reports",
    "/api/v1/lease-templates",
    "/api/v1/signatures",
)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _subject(request: Request) -> tuple[str, str]:
    """`(bucket kind, identity)` for this request.

    The user id comes from decoding the bearer token rather than from the
    request state, because middleware runs before dependencies — there is no
    resolved user yet. Decoding is signature-checked and cheap; a token that
    does not verify simply falls through to the IP bucket, which is the
    stricter one, so a forged token buys an attacker nothing.
    """
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        payload = decode_token(header[7:])
        if payload and payload.get("type") == "access" and payload.get("sub"):
            return "user", str(payload["sub"])
    return "ip", _client_ip(request)


# Reads never fall into the expensive tier, whatever path they are on.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def limit_for(path: str, kind: str, method: str) -> int:
    if method.upper() not in SAFE_METHODS and any(path.startswith(prefix) for prefix in EXPENSIVE_PREFIXES):
        return settings.RATE_LIMIT_EXPENSIVE_PER_MINUTE
    if kind == "user":
        return settings.RATE_LIMIT_AUTHENTICATED_PER_MINUTE
    return settings.RATE_LIMIT_ANONYMOUS_PER_MINUTE


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window request limiting, keyed per user or per IP."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not settings.RATE_LIMIT_ENABLED or any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES):
            return await call_next(request)

        kind, identity = _subject(request)
        limit = limit_for(path, kind, request.method)
        window = int(time.time() // WINDOW_SECONDS)
        # The bucket is per (subject, tier), not per path: a client that hits a
        # hundred different cheap endpoints is still a client making a hundred
        # requests, and per-path buckets would let it multiply its ceiling by
        # the size of the API.
        tier = "expensive" if limit == settings.RATE_LIMIT_EXPENSIVE_PER_MINUTE else "standard"
        key = f"ratelimit:{tier}:{kind}:{identity}:{window}"

        try:
            used = await redis_client.incr(key)
            if used == 1:
                # Two windows of TTL so a bucket written at the very end of one
                # is not evicted before the window it belongs to has closed.
                await redis_client.expire(key, WINDOW_SECONDS * 2)
        except Exception:  # noqa: BLE001 — see the module docstring: fail open
            logger.warning("Rate limiter unavailable; allowing request", exc_info=True)
            return await call_next(request)

        if used > limit:
            retry_after = WINDOW_SECONDS - int(time.time() % WINDOW_SECONDS)
            logger.info("Rate limit hit: %s %s on %s", kind, identity, path)
            return JSONResponse(
                status_code=429,
                content={"detail": ("Too many requests. Slow down and try again in a moment.")},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - used))
        return response
