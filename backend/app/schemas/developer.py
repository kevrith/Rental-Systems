import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.developer import ApiKeyScope, WebhookEvent


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    scopes: list[ApiKeyScope] = Field(min_length=1, max_length=len(ApiKeyScope))
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def _unique(cls, value: list[ApiKeyScope]) -> list[ApiKeyScope]:
        return list(dict.fromkeys(value))


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyRead):
    """Returned once, at creation — the only time the raw key is shown."""

    api_key: str


class ApiKeyUsage(BaseModel):
    requests_today: int
    requests_last_7_days: int
    endpoints_hit: dict[str, int]


class WebhookEndpointCreate(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    description: str | None = Field(default=None, max_length=255)
    event_types: list[WebhookEvent] = Field(min_length=1, max_length=len(WebhookEvent))

    @field_validator("url")
    @classmethod
    def _https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("Webhook URLs must use https://")
        return value

    @field_validator("event_types")
    @classmethod
    def _unique(cls, value: list[WebhookEvent]) -> list[WebhookEvent]:
        return list(dict.fromkeys(value))


class WebhookEndpointUpdate(BaseModel):
    url: str | None = Field(default=None, min_length=8, max_length=500)
    description: str | None = Field(default=None, max_length=255)
    event_types: list[WebhookEvent] | None = Field(default=None, min_length=1, max_length=len(WebhookEvent))
    is_active: bool | None = None

    @field_validator("url")
    @classmethod
    def _https(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("Webhook URLs must use https://")
        return value


class WebhookEndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    description: str | None
    event_types: list[str]
    is_active: bool
    consecutive_failures: int
    last_triggered_at: datetime | None
    last_success_at: datetime | None
    created_at: datetime


class WebhookEndpointCreated(WebhookEndpointRead):
    """Returned once, at creation — the secret is shown so the caller can
    configure signature verification. It stays retrievable afterwards through
    `secret` on the same endpoint (unlike an API key, the customer legitimately
    needs it again if they lose it)."""

    secret: str


class WebhookDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    status: str
    attempt_count: int
    response_status_code: int | None
    response_body: str | None
    delivered_at: datetime | None
    next_retry_at: datetime | None
    created_at: datetime
