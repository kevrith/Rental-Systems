"""File storage on Cloudflare R2, with a local-disk fallback for development.

Bytes never travel through the API (US-012): clients ask for a pre-signed PUT,
upload straight to R2, then confirm so we can record the real size. Reads are
handed out as signed URLs that expire after an hour, so no object is ever
publicly addressable.

With no R2 credentials configured the same interface is served from
`LOCAL_STORAGE_DIR` through the `/files/local/...` endpoints, so the whole upload
flow is exercisable offline.
"""

import mimetypes
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.file import FileCategory

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import sign_payload, verify_signature

ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


@dataclass(slots=True)
class PresignedUpload:
    storage_key: str
    upload_url: str
    method: str
    headers: dict[str, str]
    expires_in: int


def validate_upload(content_type: str, size_bytes: int) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{content_type}'. Allowed: jpg, png, webp, pdf, doc, docx.",
        )
    if size_bytes <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File size must be positive")
    if size_bytes > settings.MAX_UPLOAD_BYTES:
        limit_mb = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {limit_mb}MB limit",
        )


def build_storage_key(organization_id: uuid.UUID, category: str, filename: str, content_type: str) -> str:
    extension = Path(filename).suffix.lower() or ALLOWED_CONTENT_TYPES.get(content_type, "")
    stamp = datetime.now(UTC).strftime("%Y/%m")
    return f"org/{organization_id}/{category}/{stamp}/{uuid.uuid4().hex}{extension}"


class LocalStorageBackend:
    """Development stand-in. `upload_url` points back at this API, which writes the
    bytes to disk — the client-side flow is identical to R2."""

    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, storage_key: str) -> Path:
        # storage_key is server-generated, but resolve anyway so a crafted key can
        # never escape the storage root.
        target = (self.root / storage_key).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid storage key")
        return target

    def presign_upload(self, storage_key: str, content_type: str) -> PresignedUpload:
        return PresignedUpload(
            storage_key=storage_key,
            upload_url=f"{settings.API_V1_PREFIX}/files/local/{storage_key}",
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in=settings.SIGNED_URL_TTL_SECONDS,
        )

    def presign_download(self, storage_key: str, filename: str | None = None) -> str:
        """Signed and time-limited, exactly like R2's.

        The local backend is a development stand-in, but an unsigned URL here
        would make every vault document publicly addressable to anyone who
        guessed a key, and the difference would only show up in production. The
        expiry and the HMAC are the same shape either way.
        """
        expires = int(datetime.now(UTC).timestamp()) + settings.SIGNED_URL_TTL_SECONDS
        token = sign_payload("local-download", storage_key, str(expires))
        return f"{settings.API_V1_PREFIX}/files/local/{storage_key}?expires={expires}&token={token}"

    def write(self, storage_key: str, data: bytes) -> int:
        path = self._path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return len(data)

    def read(self, storage_key: str) -> bytes:
        path = self._path(storage_key)
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        return path.read_bytes()

    def exists(self, storage_key: str) -> bool:
        return self._path(storage_key).exists()

    def delete(self, storage_key: str) -> None:
        path = self._path(storage_key)
        if path.exists():
            path.unlink()


def verify_local_download(storage_key: str, expires: str | None, token: str | None) -> None:
    """Reject an expired or unsigned local-storage read."""
    if not expires or not token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This link is not signed")
    try:
        expires_at = int(expires)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Malformed link") from exc
    if expires_at < int(datetime.now(UTC).timestamp()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This link has expired")
    if not verify_signature(token, "local-download", storage_key, str(expires_at)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This link is not valid")


class R2StorageBackend:
    """Cloudflare R2, or any other S3-compatible store, over the S3 API.

    R2 is the default and needs nothing but an account id. Setting
    `R2_ENDPOINT_URL` points the same code at Supabase Storage, MinIO or S3
    itself; those need path-style addressing, because resolving a bucket as a
    subdomain of the endpoint (boto3's default) is a Cloudflare-ism.
    """

    name = "r2"

    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = settings.R2_BUCKET
        addressing_style = "path" if settings.R2_ENDPOINT_URL else "auto"
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3},
                s3={"addressing_style": addressing_style},
            ),
            region_name=settings.R2_REGION,
        )

    def presign_upload(self, storage_key: str, content_type: str) -> PresignedUpload:
        url = self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": storage_key, "ContentType": content_type},
            ExpiresIn=settings.SIGNED_URL_TTL_SECONDS,
        )
        return PresignedUpload(
            storage_key=storage_key,
            upload_url=url,
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in=settings.SIGNED_URL_TTL_SECONDS,
        )

    def presign_download(self, storage_key: str, filename: str | None = None) -> str:
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": storage_key}
        if filename:
            params["ResponseContentDisposition"] = f'inline; filename="{filename}"'
        return self.client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=settings.SIGNED_URL_TTL_SECONDS
        )

    def write(self, storage_key: str, data: bytes) -> int:
        content_type = mimetypes.guess_type(storage_key)[0] or "application/octet-stream"
        self.client.put_object(Bucket=self.bucket, Key=storage_key, Body=data, ContentType=content_type)
        return len(data)

    def read(self, storage_key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=storage_key)
        return response["Body"].read()

    def exists(self, storage_key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=storage_key)
            return True
        except ClientError:
            return False

    def delete(self, storage_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=storage_key)


@lru_cache
def get_storage() -> LocalStorageBackend | R2StorageBackend:
    if settings.r2_configured:
        return R2StorageBackend()
    root = Path(settings.LOCAL_STORAGE_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return LocalStorageBackend(root)


def store_generated_document(
    organization_id: uuid.UUID, category: str, filename: str, data: bytes, content_type: str
) -> str:
    """Write a server-generated artefact (lease, receipt, invoice PDF) and return
    its storage key. Unlike user uploads these never need a pre-signed PUT."""
    key = build_storage_key(organization_id, category, filename, content_type)
    get_storage().write(key, data)
    return key


def download_url(storage_key: str, filename: str | None = None) -> str:
    return get_storage().presign_download(storage_key, filename)


def local_upload_token() -> str:
    """Opaque marker used only by the local backend's test uploads."""
    return secrets.token_urlsafe(16)


async def store_bytes(
    db: Any,
    *,
    data: bytes,
    filename: str,
    content_type: str,
    category: "FileCategory",
    organization_id: uuid.UUID,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Store bytes directly (server-generated PDFs) and create a StoredFile row.

    Returns the StoredFile id. Used by PDF generation services that produce
    documents server-side rather than via client upload.
    """
    from datetime import UTC

    from app.models.file import StoredFile, UploadStatus

    key = build_storage_key(organization_id, category.value, filename, content_type)
    get_storage().write(key, data)

    stored = StoredFile(
        organization_id=organization_id,
        storage_key=key,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        category=category,
        status=UploadStatus.UPLOADED,
        entity_type=entity_type,
        entity_id=entity_id,
        uploaded_at=datetime.now(UTC),
    )
    db.add(stored)
    await db.flush()
    return stored.id


async def get_file_bytes(storage_key: str) -> bytes:
    """Read raw bytes for a stored file — used by signature overlay."""
    return get_storage().read(storage_key)
