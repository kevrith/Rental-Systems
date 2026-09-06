from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "RentFlow Kenya API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:5173"

    # Security
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

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

    # Web Push (VAPID) — generate with: vapid --gen
    VAPID_PUBLIC_KEY: str | None = None
    VAPID_PRIVATE_KEY: str | None = None
    VAPID_SUBJECT: str = "mailto:support@rentflow.co.ke"

    # Public API (Sprint 19) — per-key hourly ceiling unless an organization
    # overrides it (Organization.api_rate_limit_per_hour).
    API_KEY_DEFAULT_RATE_LIMIT_PER_HOUR: int = 1000
    API_MAX_PAGE_SIZE: int = 200

    # Outbound webhooks (Sprint 19)
    WEBHOOK_MAX_PER_ORG: int = 10
    WEBHOOK_DELIVERY_TIMEOUT_SECONDS: int = 15

    @property
    def sync_database_url(self) -> str:
        return self.DATABASE_URL_SYNC or self.DATABASE_URL.replace(
            "postgresql+asyncpg", "postgresql+psycopg2"
        )

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
    def r2_configured(self) -> bool:
        return bool(
            self.R2_ACCOUNT_ID and self.R2_ACCESS_KEY_ID and self.R2_SECRET_ACCESS_KEY and self.R2_BUCKET
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
