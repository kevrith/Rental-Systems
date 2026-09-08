import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.api_errors import ExternalApiError
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.metrics import instrument_app, metrics_endpoint
from app.core.observability import configure_sentry, configure_tracing
from app.core.rate_limit import RateLimitMiddleware
from app.core.request_context import RequestIDMiddleware

configure_logging(settings.DEBUG, settings.LOG_FORMAT)
# Before the app is built, so an exception raised during startup is caught.
configure_sentry("api")

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

# Tracing needs the app object to instrument FastAPI's own request handling,
# and needs to run after `app.core.database` has created its engine — see
# configure_tracing's docstring for why the ordering matters here.
configure_tracing("api", fastapi_app=app)
instrument_app(app)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """OWASP-recommended response headers (A05: Security Misconfiguration).

    Applied at the app layer rather than Nginx so they're present in every
    environment this API runs in, including local dev and tests — the
    production reverse proxy (Sprint 24, US-104) can add HSTS on top once
    there's a real TLS-terminating domain to pin it to.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


# Middleware added last runs outermost. Reading the block below bottom-up
# gives the order a request actually travels:
#   request ID -> CORS -> security headers -> rate limit -> the app.
# The limiter sits inside the header middleware on purpose: a 429 it returns
# short-circuits the app but still passes back out through the headers, so an
# error response is not the one response missing them. Request ID is
# outermost of all — even a CORS preflight or a 429 gets one, and it is the
# very first thing attached to the log line for that request.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Outermost of all: every response, including a CORS preflight or a 429 from
# the rate limiter, gets an X-Request-ID and a log line correlated to it.
app.add_middleware(RequestIDMiddleware)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# Prometheus convention: unversioned, outside /api/v1, exempted from the rate
# limiter (see RateLimitMiddleware.EXEMPT_PREFIXES) since a scrape every
# fifteen seconds is not user traffic.
app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)


@app.exception_handler(ExternalApiError)
async def external_api_error_handler(request: Request, exc: ExternalApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "data": None, "errors": [exc.detail]},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the full traceback so Render/Sentry captures it.
    traceback.print_exc()
    origin = request.headers.get("origin", "")
    cors_headers = (
        {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true"}
        if origin in settings.CORS_ORIGINS
        else {}
    )
    return JSONResponse(
        status_code=500,
        content={"status": "error", "data": None, "errors": ["Internal server error"]},
        headers=cors_headers,
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.APP_NAME, "status": "running"}
