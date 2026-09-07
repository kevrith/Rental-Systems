import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SavedViewCreate(BaseModel):
    entity_type: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    filters: dict[str, Any] = Field(default_factory=dict)
    is_shared: bool = False
    is_default: bool = False


class SavedViewUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    filters: dict[str, Any] | None = None
    is_shared: bool | None = None
    is_default: bool | None = None


class SavedViewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    name: str
    filters: dict[str, Any]
    is_shared: bool
    is_default: bool
    user_id: uuid.UUID
    created_at: datetime
