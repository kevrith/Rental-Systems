import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.integrations import (
    AccountingProvider,
    PortalName,
    PortalSyncStatus,
)

# --------------------------------------------------------------- property portals


class PortalConnectionUpsert(BaseModel):
    api_key: str = Field(min_length=3, max_length=256)
    account_id: str | None = Field(default=None, max_length=128)


class PortalListingSyncRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    listing_id: uuid.UUID
    portal: PortalName
    external_listing_id: str | None
    status: PortalSyncStatus
    attempts: int
    last_attempt_at: datetime | None
    last_error: str | None


# ------------------------------------------------------------ accounting software


class AccountingAuthorizeUrl(BaseModel):
    authorize_url: str


class AccountingConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: AccountingProvider
    external_account_id: str
    environment: str
    is_active: bool
    last_synced_at: datetime | None
    last_error: str | None


class AccountingSyncRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    external_id: str | None
    status: str
    attempts: int
    last_error: str | None
    synced_at: datetime | None
    created_at: datetime


class AccountingSyncReport(BaseModel):
    synced: int
    failed: int
    pending: int
    recent_failures: list[AccountingSyncRecordRead]
