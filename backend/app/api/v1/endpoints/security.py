"""Fraud alert triage and the security audit log export (Sprint 22, US-097/098)."""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.security import FraudAlert, FraudAlertStatus
from app.schemas.security import AuditChainVerification, FraudAlertRead, ResolveFraudAlertRequest
from app.services import audit_chain_service, security_service

router = APIRouter()

MEDIA_TYPES = {"csv": "text/csv", "pdf": "application/pdf"}


@router.get("/fraud-alerts", response_model=list[FraudAlertRead])
async def list_fraud_alerts(
    alert_status: FraudAlertStatus | None = Query(default=None, alias="status"),
    context: OrgContext = Depends(require(Permission.FRAUD_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[FraudAlert]:
    return await security_service.list_fraud_alerts(db, context, alert_status=alert_status)


@router.patch("/fraud-alerts/{alert_id}", response_model=FraudAlertRead)
async def resolve_fraud_alert(
    alert_id: uuid.UUID,
    payload: ResolveFraudAlertRequest,
    request: Request,
    context: OrgContext = Depends(require(Permission.FRAUD_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> FraudAlert:
    return await security_service.resolve_fraud_alert(
        db, context, alert_id, new_status=payload.status, request=request
    )


@router.get("/audit-log/export")
async def export_audit_log(
    format: Literal["csv", "pdf"] = Query(default="csv"),  # noqa: A002
    date_from: date | None = None,
    date_to: date | None = None,
    context: OrgContext = Depends(require(Permission.AUDIT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    data, filename = await security_service.export_audit_log(
        db, context, export_format=format, date_from=date_from, date_to=date_to
    )
    return Response(
        content=data,
        media_type=MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audit-log/verify", response_model=AuditChainVerification)
async def verify_audit_log_chain(
    context: OrgContext = Depends(require(Permission.AUDIT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> AuditChainVerification:
    """Recompute the audit log's hash chain from the stored rows and report
    whether it is intact — see `app.services.audit_chain_service`."""
    result = await audit_chain_service.verify_chain(db, context.organization_id)
    return AuditChainVerification(
        total=result.total,
        verified=result.verified,
        unchained=result.unchained,
        intact=result.intact,
        broken_at_id=result.broken_at_id,
        broken_at_created_at=result.broken_at_created_at,
    )
