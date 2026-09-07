"""Custom report builder and monthly report history — Sprint 21 (US-093/094)."""

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.file import StoredFile
from app.models.reporting import MonthlyReport, ReportDefinition
from app.models.vacancy import ExportKind
from app.schemas.reporting import (
    MonthlyReportRead,
    ReportDefinitionCreate,
    ReportDefinitionRead,
    ReportDefinitionUpdate,
    ReportPreviewRequest,
    ReportPreviewResult,
)
from app.services import file_service, reporting_service

router = APIRouter()

MEDIA_TYPES = {
    "csv": "text/csv",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}

PREVIEW_ROW_LIMIT = 200


@router.get("/datasets")
async def list_datasets(
    context: OrgContext = Depends(require(Permission.REPORT_VIEW)),
) -> list[dict]:
    return [
        {"dataset": kind.value, "label": label} for kind, label in reporting_service.DATASET_LABELS.items()
    ]


@router.get("/datasets/{dataset}/fields")
async def list_dataset_fields(
    dataset: ExportKind,
    context: OrgContext = Depends(require(Permission.REPORT_VIEW)),
) -> list[dict]:
    return reporting_service.dataset_fields(dataset)


@router.post("/preview", response_model=ReportPreviewResult)
async def preview_report(
    payload: ReportPreviewRequest,
    context: OrgContext = Depends(require(Permission.REPORT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ReportPreviewResult:
    rows = await reporting_service.execute(
        db,
        context,
        dataset=payload.dataset,
        fields=payload.fields,
        filters=payload.filters,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )
    return ReportPreviewResult(rows=rows[:PREVIEW_ROW_LIMIT], row_count=len(rows))


@router.post("/definitions", response_model=ReportDefinitionRead, status_code=status.HTTP_201_CREATED)
async def create_definition(
    payload: ReportDefinitionCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.REPORT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ReportDefinition:
    return await reporting_service.create_definition(db, context, payload, request)


@router.get("/definitions", response_model=list[ReportDefinitionRead])
async def list_definitions(
    context: OrgContext = Depends(require(Permission.REPORT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[ReportDefinition]:
    return await reporting_service.list_definitions(db, context)


@router.get("/definitions/{definition_id}", response_model=ReportDefinitionRead)
async def get_definition(
    definition_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.REPORT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ReportDefinition:
    return await reporting_service.get_definition(db, context, definition_id)


@router.patch("/definitions/{definition_id}", response_model=ReportDefinitionRead)
async def update_definition(
    definition_id: uuid.UUID,
    payload: ReportDefinitionUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.REPORT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ReportDefinition:
    return await reporting_service.update_definition(db, context, definition_id, payload, request)


@router.delete("/definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_definition(
    definition_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.REPORT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    await reporting_service.delete_definition(db, context, definition_id, request)


@router.post("/definitions/{definition_id}/run")
async def run_definition(
    definition_id: uuid.UUID,
    format: str | None = Query(default=None, pattern="^(csv|excel|pdf)$"),  # noqa: A002
    context: OrgContext = Depends(require_write(Permission.REPORT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    definition = await reporting_service.get_definition(db, context, definition_id)
    data, filename, row_count = await reporting_service.run_definition(
        db, context, definition, export_format=format
    )
    await db.commit()
    return Response(
        content=data,
        media_type=MEDIA_TYPES[format or definition.export_format.value],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Row-Count": str(row_count),
        },
    )


@router.get("/monthly", response_model=list[MonthlyReportRead])
async def list_monthly_reports(
    limit: int = Query(default=12, ge=1, le=24),
    context: OrgContext = Depends(require(Permission.REPORT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[MonthlyReportRead]:
    rows = await db.scalars(
        select(MonthlyReport)
        .where(MonthlyReport.organization_id == context.organization_id)
        .order_by(MonthlyReport.period_start.desc())
        .limit(limit)
    )
    details = []
    for record in rows:
        stored = await db.get(StoredFile, record.file_id) if record.file_id else None
        details.append(
            MonthlyReportRead(
                **MonthlyReportRead.model_validate(record).model_dump(exclude={"download_url"}),
                download_url=file_service.to_url(stored) if stored else None,
            )
        )
    return details
