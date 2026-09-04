import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.file import FileCategory, StoredFile
from app.services import file_service, storage_service

router = APIRouter()


class UploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=128)
    size_bytes: int = Field(gt=0)
    category: FileCategory = FileCategory.OTHER
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: uuid.UUID | None = None


class BatchUploadRequest(BaseModel):
    files: list[UploadRequest] = Field(min_length=1, max_length=20)


class UploadTicket(BaseModel):
    file_id: uuid.UUID
    storage_key: str
    upload_url: str
    method: str
    headers: dict[str, str]
    expires_in: int


class ConfirmUploadRequest(BaseModel):
    size_bytes: int | None = Field(default=None, gt=0)


class FileRead(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    category: FileCategory
    status: str
    url: str | None = None


def _ticket(record: StoredFile, presigned: storage_service.PresignedUpload) -> UploadTicket:
    return UploadTicket(
        file_id=record.id,
        storage_key=presigned.storage_key,
        upload_url=presigned.upload_url,
        method=presigned.method,
        headers=presigned.headers,
        expires_in=presigned.expires_in,
    )


@router.post("/upload-url", response_model=UploadTicket, status_code=status.HTTP_201_CREATED)
async def create_upload_url(
    payload: UploadRequest,
    context: OrgContext = Depends(require_write(Permission.FILE_UPLOAD)),
    db: AsyncSession = Depends(get_db),
) -> UploadTicket:
    """Reserve a slot and hand back a pre-signed PUT. The client uploads directly
    to storage, then calls `/files/{id}/confirm`."""
    record, presigned = await file_service.request_upload(
        db,
        context,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        category=payload.category,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
    )
    return _ticket(record, presigned)


@router.post("/upload-url/batch", response_model=list[UploadTicket], status_code=status.HTTP_201_CREATED)
async def create_upload_urls(
    payload: BatchUploadRequest,
    context: OrgContext = Depends(require_write(Permission.FILE_UPLOAD)),
    db: AsyncSession = Depends(get_db),
) -> list[UploadTicket]:
    results = await file_service.request_upload_batch(
        db, context, [item.model_dump() for item in payload.files]
    )
    return [_ticket(record, presigned) for record, presigned in results]


@router.post("/{file_id}/confirm", response_model=FileRead)
async def confirm_upload(
    file_id: uuid.UUID,
    payload: ConfirmUploadRequest,
    context: OrgContext = Depends(require_write(Permission.FILE_UPLOAD)),
    db: AsyncSession = Depends(get_db),
) -> FileRead:
    record = await file_service.confirm_upload(db, context, file_id, payload.size_bytes)
    return FileRead(
        id=record.id,
        filename=record.filename,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        category=record.category,
        status=record.status.value,
        url=file_service.to_url(record),
    )


@router.get("/{file_id}", response_model=FileRead)
async def get_file(
    file_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.FILE_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> FileRead:
    """Metadata plus a signed URL valid for 60 minutes."""
    record = await file_service.get_file(db, context, file_id)
    return FileRead(
        id=record.id,
        filename=record.filename,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        category=record.category,
        status=record.status.value,
        url=file_service.to_url(record),
    )


# ------------------------------------------------ local-development storage only


local_router = APIRouter()


@local_router.put("/{storage_key:path}", status_code=status.HTTP_200_OK)
async def local_put(storage_key: str, request: Request) -> dict[str, int]:
    """Stands in for R2's pre-signed PUT when no R2 credentials are configured."""
    body = await request.body()
    written = storage_service.get_storage().write(storage_key, body)
    return {"size_bytes": written}


@local_router.get("/{storage_key:path}")
async def local_get(storage_key: str, expires: str | None = None, token: str | None = None) -> Response:
    """Serves a local-storage object, but only against a live signed link."""
    storage_service.verify_local_download(storage_key, expires, token)
    backend = storage_service.get_storage()
    data = backend.read(storage_key)
    import mimetypes

    content_type = mimetypes.guess_type(storage_key)[0] or "application/octet-stream"
    return Response(content=data, media_type=content_type)
