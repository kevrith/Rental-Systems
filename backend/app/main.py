from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.api_errors import ExternalApiError
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.observability import configure_sentry
from app.core.rate_limit import RateLimitMiddleware

configure_logging(settings.DEBUG)
# Before the app is built, so an exception raised during startup is caught.
configure_sentry("api")

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)


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


# Middleware added last runs outermost, so the order below is:
#   CORS -> security headers -> rate limit -> the app.
# The limiter sits inside the header middleware on purpose: a 429 it returns
# short-circuits the app but still passes back out through the headers, so an
# error response is not the one response missing them.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.exception_handler(ExternalApiError)
async def external_api_error_handler(request: Request, exc: ExternalApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "data": None, "errors": [exc.detail]},
        headers=exc.headers,
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.APP_NAME, "status": "running"}
