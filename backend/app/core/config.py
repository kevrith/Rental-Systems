from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "RentFlow Kenya API"
    ENVIRONMENT: str = "development"
    # Secure by default: a deployment that forgets to set DEBUG explicitly gets
    # FastAPI's production behavior (no stack traces in error responses), not
    # its debug behavior. Local dev sets DEBUG=true in .env.example.
    DEBUG: bool = False
    # "console" (human-readable) or "json" (one object per line, for a log
    # aggregator). Independent of DEBUG — see app.core.logging's docstring.
    LOG_FORMAT: str = "console"
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:5173"

    # Security
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Google Sign-In (Identity Services). This is the OAuth *client ID*, not a
    # secret — it's compiled into the frontend bundle same as a Stripe
    # publishable key. Verification only needs it to check the ID token's
    # `aud` claim against Google's own public keys; no client secret involved.
    GOOGLE_CLIENT_ID: str | None = None

    # Database
    DATABASE_URL: str
    DATABASE_URL_SYNC: str | None = None

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # OTP / login security
    OTP_LENGTH: int = 6
    OTP_TTL_SECONDS: int = 300
    OTP_MAX_ATTEMPTS: int = 5
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_SECONDS: int = 900

    # Verification / invitation link lifetimes
    EMAIL_VERIFICATION_TTL_HOURS: int = 24
    PASSWORD_RESET_TTL_HOURS: int = 2
    INVITATION_TTL_HOURS: int = 168  # 7 days
    TRUSTED_DEVICE_DAYS: int = 30

    # Tenant portal magic link (Sprint 26). Deliberately far shorter-lived than
    # the invitation: an invitation is expected to sit in a WhatsApp thread for
    # days, a login link should be used within minutes of being asked for.
    PORTAL_MAGIC_LINK_TTL_MINUTES: int = 15
    PORTAL_MAGIC_LINK_MAX_PER_HOUR: int = 5

    # Most live logins one user may hold at once, unless the organisation sets
    # its own ceiling. Five covers a phone, a laptop, an office desktop and a
    # spare; beyond that a "session" is usually one nobody remembers starting.
    MAX_CONCURRENT_SESSIONS_PER_USER: int = 5

    # Account lifecycle
    TRIAL_PERIOD_DAYS: int = 30
    ACCOUNT_DELETION_GRACE_DAYS: int = 30

    # Uploads
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    MAX_UPLOAD_BATCH_BYTES: int = 50 * 1024 * 1024
    SIGNED_URL_TTL_SECONDS: int = 3600  # 60 minutes

    # Cloudflare R2 (S3-compatible). Blank locally — storage falls back to disk.
    R2_ACCOUNT_ID: str | None = None
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_BUCKET: str | None = None
    R2_PUBLIC_BASE_URL: str | None = None
    # Overrides for any other S3-compatible store — Supabase Storage, MinIO,
    # plain S3. Left blank the endpoint is derived from R2_ACCOUNT_ID in R2's
    # own format, which is what a Cloudflare deployment wants and what every
    # existing environment already has. A store that is not R2 also needs its
    # real region name (R2 has none, hence "auto") and path-style addressing,
    # since only Cloudflare resolves a bucket as a subdomain of the endpoint.
    R2_ENDPOINT_URL: str | None = None
    R2_REGION: str = "auto"
    LOCAL_STORAGE_DIR: str = "./var/uploads"

    # Africa's Talking (SMS)
    AFRICAS_TALKING_USERNAME: str | None = None
    AFRICAS_TALKING_API_KEY: str | None = None
    AFRICAS_TALKING_SENDER_ID: str | None = None

    # WhatsApp Business Cloud API
    WHATSAPP_API_TOKEN: str | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_API_BASE_URL: str = "https://graph.facebook.com/v21.0"

    # Safaricom Daraja (M-Pesa)
    DARAJA_CONSUMER_KEY: str | None = None
    DARAJA_CONSUMER_SECRET: str | None = None
    DARAJA_SHORTCODE: str | None = None
    DARAJA_PASSKEY: str | None = None
    DARAJA_ENVIRONMENT: str = "sandbox"  # sandbox | production
    DARAJA_CALLBACK_BASE_URL: str = "http://localhost:8000"

    # Daraja B2C — paying money *out* (owner disbursements, US-041). Separate
    # credentials from collections: B2C runs against the organisation shortcode
    # with an API operator ("initiator") whose password is RSA-encrypted by
    # Safaricom into the security credential.
    DARAJA_B2C_SHORTCODE: str | None = None
    DARAJA_B2C_INITIATOR_NAME: str | None = None
    DARAJA_B2C_SECURITY_CREDENTIAL: str | None = None

    # Resend (transactional email)
    RESEND_API_KEY: str | None = None
    EMAIL_FROM: str = "RentFlow <noreply@rentflow.co.ke>"
    # Signing secret for Resend's delivery-event webhooks (bounce/complaint),
    # from the Resend dashboard's webhook settings — starts with `whsec_`.
    # Unset in development; the webhook endpoint refuses to process events
    # without it rather than accepting unsigned callbacks.
    RESEND_WEBHOOK_SECRET: str | None = None

    # Web Push (VAPID) — generate with: vapid --gen
    VAPID_PUBLIC_KEY: str | None = None
    VAPID_PRIVATE_KEY: str | None = None
    VAPID_SUBJECT: str = "mailto:support@rentflow.co.ke"

    # Application rate limiting (Sprint 26). Ceilings are per minute, per user
    # for an authenticated request and per IP otherwise. Disabled in tests,
    # which fire hundreds of requests a second at the app deliberately.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_ANONYMOUS_PER_MINUTE: int = 30
    RATE_LIMIT_AUTHENTICATED_PER_MINUTE: int = 300
    # Endpoints that send an SMS, render a PDF, call a model or build an export.
    RATE_LIMIT_EXPENSIVE_PER_MINUTE: int = 20

    # Error tracking (Sprint 26). Blank means Sentry is simply not initialised —
    # the same degrade-gracefully treatment every other optional integration in
    # this file gets. `SENTRY_TRACES_SAMPLE_RATE` is deliberately low: this is a
    # cost-sensitive deployment and full tracing on every request is not worth
    # what it costs on a small droplet.
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.05
    SENTRY_PROFILES_SAMPLE_RATE: float = 0.0

    # Distributed tracing (OpenTelemetry). Blank means the SDK never installs a
    # tracer provider — see app.core.observability.configure_tracing. Points at
    # any OTLP/HTTP collector: the Jaeger all-in-one in
    # infra/observability/docker-compose.yml locally, a managed collector in
    # production.
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None

    # Prometheus metrics endpoint (Sprint 26). Mounted at /metrics, outside
    # /api/v1 and outside the rate limiter, matching Prometheus convention. A
    # blank token leaves it open, which is fine for a local scrape but not for
    # a public droplet — production must set one, and give it to the Prometheus
    # scrape config as a bearer token.
    METRICS_TOKEN: str | None = None

    # Public API (Sprint 19) — per-key hourly ceiling unless an organization
    # overrides it (Organization.api_rate_limit_per_hour).
    API_KEY_DEFAULT_RATE_LIMIT_PER_HOUR: int = 1000
    API_MAX_PAGE_SIZE: int = 200

    # Outbound webhooks (Sprint 19)
    WEBHOOK_MAX_PER_ORG: int = 10
    WEBHOOK_DELIVERY_TIMEOUT_SECONDS: int = 15

    # Customer success (Sprint 20)
    SUPPORT_EMAIL: str = "support@rentflow.co.ke"
    CUSTOMER_HEALTH_AT_RISK_THRESHOLD: int = 50

    # AI lease document intelligence (Sprint 22, US-096). Blank locally — the
    # analyze endpoint returns a clear 503 rather than a stack trace. Sonnet
    # rather than Opus: this is a single structured-output extraction over one
    # document, not open-ended agentic reasoning, so the much cheaper model is
    # the right default for this shape of task.
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    AI_ANALYSIS_MAX_PER_HOUR: int = 10

    # Meter photo OCR (Sprint 26, Module 5). Shares ANTHROPIC_API_KEY with lease
    # analysis; blank means the capture form simply never offers a suggestion.
    # A reading below the confidence threshold is shown but not pre-filled — the
    # caretaker has to type it, which is the point.
    METER_OCR_MAX_PER_HOUR: int = 200
    METER_OCR_CONFIDENCE_THRESHOLD: float = 85.0

    # API key rotation reminder (US-098).
    API_KEY_ROTATION_REMINDER_DAYS: int = 90

    # Accounting software OAuth (Sprint 23, US-100). Blank locally — the
    # connect endpoint returns a clear 503 rather than starting a broken OAuth
    # flow. The redirect URI both providers call back to is built from
    # `OAUTH_CALLBACK_BASE_URL`, which must be a URL Intuit/Xero can reach —
    # `localhost` only works with their own sandbox tooling.
    OAUTH_CALLBACK_BASE_URL: str = "http://localhost:8000"
    QUICKBOOKS_CLIENT_ID: str | None = None
    QUICKBOOKS_CLIENT_SECRET: str | None = None
    QUICKBOOKS_ENVIRONMENT: str = "sandbox"  # sandbox | production
    XERO_CLIENT_ID: str | None = None
    XERO_CLIENT_SECRET: str | None = None

    # Property portal integrations (Sprint 23, US-099). Each organisation
    # supplies its own account credentials (see `PortalConnection`); these are
    # only the partner base URLs, which are not yet published self-serve APIs —
    # see `app.services.portal_integration_service` for what that means today.
    BUYRENTKENYA_API_BASE_URL: str = "https://api.buyrentkenya.com/v1"
    PIGIAME_API_BASE_URL: str = "https://api.pigiame.co.ke/v1"

    # Virus scanning on upload (Sprint 25, US-105). Blank locally — uploads are
    # marked SKIPPED rather than blocked, the same degrade-gracefully treatment
    # every other optional integration in this file gets.
    CLAMAV_HOST: str | None = None
    CLAMAV_PORT: int = 3310
    CLAMAV_TIMEOUT_SECONDS: int = 10

    # WebAuthn / biometric login (Sprint 25, US-108). RP_ID must be the bare
    # domain (no scheme, no port) the browser is served from — "localhost" in
    # dev, the production apex domain in prod. ORIGIN is the full scheme+host
    # the browser sends as part of the signed assertion.
    WEBAUTHN_RP_ID: str = "localhost"
    WEBAUTHN_RP_NAME: str = "RentFlow"
    WEBAUTHN_ORIGIN: str = "http://localhost:5173"

    @property
    def clamav_configured(self) -> bool:
        return bool(self.CLAMAV_HOST)

    @property
    def sync_database_url(self) -> str:
        """
        Alembic is synchronous, so this has to name a sync driver whatever it
        was handed.

        Both URLs are typed by hand into the Render dashboard — render.yaml
        marks them `sync: false` — and pasting the asyncpg one into both
        fields is the obvious slip. Returning DATABASE_URL_SYNC verbatim
        turned that slip into `MissingGreenlet: greenlet_spawn has not been
        called` thrown out of the connection pool during `alembic upgrade
        head` at boot: an error that talks about greenlets and await, names
        neither the setting nor the URL, and sends you reading SQLAlchemy's
        async internals instead of the dashboard field that is actually
        wrong.

        Forcing the driver costs nothing and cannot itself be got wrong. Only
        the scheme is rewritten; everything after `://` is left byte for byte
        alone, so a percent-encoded password still arrives intact.
        """
        url = self.DATABASE_URL_SYNC or self.DATABASE_URL
        scheme, separator, rest = url.partition("://")
        if not separator or not scheme.startswith("postgres"):
            return url
        return f"postgresql+psycopg2://{rest}"

    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def celery_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @property
    def daraja_base_url(self) -> str:
        return (
            "https://api.safaricom.co.ke"
            if self.DARAJA_ENVIRONMENT == "production"
            else "https://sandbox.safaricom.co.ke"
        )

    @property
    def r2_endpoint_url(self) -> str:
        return self.R2_ENDPOINT_URL or f"https://{self.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

    @property
    def r2_configured(self) -> bool:
        # An explicit endpoint stands in for the account id: a non-Cloudflare
        # store has no account id to give, and requiring one would mean
        # inventing a value whose only job is to pass this check.
        has_host = bool(self.R2_ACCOUNT_ID or self.R2_ENDPOINT_URL)
        return bool(has_host and self.R2_ACCESS_KEY_ID and self.R2_SECRET_ACCESS_KEY and self.R2_BUCKET)

    @property
    def quickbooks_configured(self) -> bool:
        return bool(self.QUICKBOOKS_CLIENT_ID and self.QUICKBOOKS_CLIENT_SECRET)

    @property
    def xero_configured(self) -> bool:
        return bool(self.XERO_CLIENT_ID and self.XERO_CLIENT_SECRET)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
