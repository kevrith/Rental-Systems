import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models.security import FraudAlertStatus, FraudAlertType


class FraudAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_type: FraudAlertType
    entity_type: str
    entity_id: uuid.UUID
    summary: str
    details: dict[str, Any]
    status: FraudAlertStatus
    resolved_at: datetime | None
    created_at: datetime


class ResolveFraudAlertRequest(BaseModel):
    status: Literal[FraudAlertStatus.SUPPRESSED, FraudAlertStatus.RESOLVED]


class AuditChainVerification(BaseModel):
    total: int
    verified: int
    unchained: int
    intact: bool
    broken_at_id: uuid.UUID | None = None
    broken_at_created_at: str | None = None
