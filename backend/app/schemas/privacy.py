import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.privacy import DataRequestStatus, DataRequestType

LegalHoldEntityType = Literal["tenant", "tenancy", "application", "organization"]


class DataRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    request_type: DataRequestType
    status: DataRequestStatus
    resolution_notes: str | None
    resolved_at: datetime | None
    created_at: datetime


class DataRequestDetail(DataRequestRead):
    tenant_name: str | None = None
    export_url: str | None = None


class LegalHoldCreate(BaseModel):
    entity_type: LegalHoldEntityType
    entity_id: uuid.UUID | None = None
    reason: str = Field(min_length=3)

    @property
    def requires_entity_id(self) -> bool:
        return self.entity_type != "organization"


class LegalHoldRelease(BaseModel):
    note: str | None = None


class LegalHoldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: LegalHoldEntityType
    entity_id: uuid.UUID | None
    reason: str
    placed_by_name: str | None
    released_at: datetime | None
    released_by_name: str | None
    release_note: str | None
    created_at: datetime
