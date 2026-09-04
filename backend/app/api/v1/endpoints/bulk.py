"""Bulk operations: preview, execute, and the spreadsheet import (US-071 to US-073).

Everything here is two-step by design. `POST /bulk/{kind}/preview` resolves the
targets and answers with the list; `POST /bulk/{id}/execute` runs against exactly
that list. Nothing sends a message or changes a rent on the preview call.
"""

import uuid

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.bulk import BulkOperationKind
from app.schemas.bulk import (
    AnnouncementPreview,
    BulkOperationRead,
    DocumentDistributionPreview,
    ImportCommit,
    ImportPreview,
    ImportResult,
    InvoiceRunPreview,
    ReminderPreview,
    RenewalNoticePreview,
    RentIncreasePreview,
)
from app.services import bulk_service, import_service

router = APIRouter()

# 5 MB is comfortably more than a 2,000-row tenant sheet and small enough that a
# mis-selected file is rejected before it is parsed.
MAX_IMPORT_BYTES = 5 * 1024 * 1024


@router.get("", response_model=list[BulkOperationRead])
async def list_operations(
    kind: BulkOperationKind | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[BulkOperationRead]:
    rows = await bulk_service.list_operations(db, context, kind=kind, limit=limit)
    return [BulkOperationRead.model_validate(row) for row in rows]


@router.get("/{operation_id}", response_model=BulkOperationRead)
async def get_operation(
    operation_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> BulkOperationRead:
    operation = await bulk_service.get_operation(db, context, operation_id)
    return BulkOperationRead.model_validate(operation)


@router.post("/rent-increase/preview", response_model=BulkOperationRead)
async def preview_rent_increase(
    payload: RentIncreasePreview,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BulkOperationRead:
    """Show the new rent per unit before anything changes (US-071)."""
    operation = await bulk_service.preview(db, context, BulkOperationKind.RENT_INCREASE, payload, request)
    return BulkOperationRead.model_validate(operation)


@router.post("/reminders/preview", response_model=BulkOperationRead)
async def preview_reminders(
    payload: ReminderPreview,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.INVOICE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BulkOperationRead:
    operation = await bulk_service.preview(db, context, BulkOperationKind.PAYMENT_REMINDER, payload, request)
    return BulkOperationRead.model_validate(operation)


@router.post("/announcement/preview", response_model=BulkOperationRead)
async def preview_announcement(
    payload: AnnouncementPreview,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BulkOperationRead:
    operation = await bulk_service.preview(db, context, BulkOperationKind.ANNOUNCEMENT, payload, request)
    return BulkOperationRead.model_validate(operation)


@router.post("/invoices/preview", response_model=BulkOperationRead)
async def preview_invoice_run(
    payload: InvoiceRunPreview,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.INVOICE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BulkOperationRead:
    operation = await bulk_service.preview(db, context, BulkOperationKind.GENERATE_INVOICES, payload, request)
    return BulkOperationRead.model_validate(operation)


@router.post("/renewals/preview", response_model=BulkOperationRead)
async def preview_renewal_notices(
    payload: RenewalNoticePreview,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BulkOperationRead:
    operation = await bulk_service.preview(db, context, BulkOperationKind.RENEWAL_NOTICES, payload, request)
    return BulkOperationRead.model_validate(operation)


@router.post("/documents/preview", response_model=BulkOperationRead)
async def preview_document_distribution(
    payload: DocumentDistributionPreview,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BulkOperationRead:
    """Send one document to every tenant in scope (US-073)."""
    operation = await bulk_service.preview(
        db, context, BulkOperationKind.DOCUMENT_DISTRIBUTION, payload, request
    )
    return BulkOperationRead.model_validate(operation)


@router.post("/{operation_id}/execute", response_model=BulkOperationRead)
async def execute_operation(
    operation_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BulkOperationRead:
    operation = await bulk_service.execute(db, context, operation_id, request)
    return BulkOperationRead.model_validate(operation)


@router.post("/{operation_id}/cancel", response_model=BulkOperationRead)
async def cancel_operation(
    operation_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BulkOperationRead:
    operation = await bulk_service.cancel(db, context, operation_id)
    return BulkOperationRead.model_validate(operation)


# ------------------------------------------------------------- tenant import


@router.get("/import/template")
async def download_import_template(
    context: OrgContext = Depends(require(Permission.TENANT_MANAGE)),
) -> Response:
    """The blank spreadsheet, generated from the same column list the parser uses."""
    return Response(
        content=import_service.build_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="rentflow-tenant-import.xlsx"'},
    )


@router.post("/import/preview", response_model=ImportPreview)
async def preview_import(
    file: UploadFile = File(...),
    context: OrgContext = Depends(require_write(Permission.TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ImportPreview:
    """Parse and validate the upload. Nothing is written."""
    data = await file.read()
    if len(data) > MAX_IMPORT_BYTES:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="That file is larger than 5 MB — split it into smaller batches",
        )

    parsed, parse_errors = import_service.parse(data)
    ready, db_errors = await import_service.validate_against_database(db, context, parsed)
    errors = sorted(parse_errors + db_errors, key=lambda item: item["row"])

    return ImportPreview(
        ready=ready,
        errors=errors,
        total_rows=len(ready) + len(errors),
        ready_count=len(ready),
        error_count=len(errors),
    )


@router.post("/import/commit", response_model=ImportResult)
async def commit_import(
    payload: ImportCommit,
    context: OrgContext = Depends(require_write(Permission.TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Create the rows the operator confirmed. Rows are independent — a late
    failure does not undo the tenants already created."""
    created, failures = await import_service.commit_rows(db, context, payload.rows)
    return ImportResult(created=created, failed=len(failures), failures=failures)
