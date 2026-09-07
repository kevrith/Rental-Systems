import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.ai_analysis import LeaseSuggestionCategory, LeaseSuggestionStatus


class LeaseSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: LeaseSuggestionCategory
    title: str
    issue: str
    suggested_text: str | None
    status: LeaseSuggestionStatus
    created_at: datetime


class LeaseAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lease_template_id: uuid.UUID
    model_used: str
    summary: str
    created_at: datetime
    suggestions: list[LeaseSuggestionRead]


class ResolveSuggestionRequest(BaseModel):
    status: Literal[LeaseSuggestionStatus.ACCEPTED, LeaseSuggestionStatus.DISMISSED]
