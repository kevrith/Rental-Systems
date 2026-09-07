import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.privacy import DataRequestStatus, DataRequestType


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
