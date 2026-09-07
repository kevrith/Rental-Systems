import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass


class FileCategory(str, enum.Enum):
    PROPERTY_PHOTO = "property_photo"
    UNIT_PHOTO = "unit_photo"
    TENANT_ID = "tenant_id"
    TENANT_PASSPORT_PHOTO = "tenant_passport_photo"
    LEASE = "lease"
    RECEIPT = "receipt"
    INVOICE = "invoice"
    METER_READING = "meter_reading"
    MAINTENANCE = "maintenance"
    NOTICE = "notice"
    ORG_LOGO = "org_logo"
    PROFILE_PHOTO = "profile_photo"
    OTHER = "other"
    # Phase 2
    INSPECTION_PHOTO = "inspection_photo"
    INSPECTION_REPORT = "inspection_report"
    OWNER_STATEMENT = "owner_statement"
    SIGNED_DOCUMENT = "signed_document"
    SIGNATURE_IMAGE = "signature_image"
    # Phase 2 — document vault (US-045, US-046)
    TITLE_DEED = "title_deed"
    INSURANCE_CERTIFICATE = "insurance_certificate"
    COMPLIANCE_CERTIFICATE = "compliance_certificate"
    DEMAND_LETTER = "demand_letter"
    RENEWAL_AGREEMENT = "renewal_agreement"
    # Phase 3
    GUARANTEE = "guarantee"
    # Sprint 21 — custom report exports and the monthly summary.
    REPORT = "report"
    # Sprint 25 — a subject access request export bundle (US-106).
    DATA_REQUEST_EXPORT = "data_request_export"
    # Sprint 26 — the signed owner-agency management agreement.
    MANAGEMENT_AGREEMENT = "management_agreement"


class UploadStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    FAILED = "failed"


class ScanStatus(str, enum.Enum):
    """Virus-scan outcome for an uploaded file (Sprint 25, US-105).

    `SKIPPED` means no ClamAV daemon is configured — the same degrade-gracefully
    treatment every other optional integration in this codebase gets. `FAILED`
    means a daemon is configured but was unreachable at scan time; that does not
    block the upload (scanning is defence in depth, not the thing standing
    between a landlord and a working upload button), but it does mark the file
    for the retry sweep.
    """

    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    FAILED = "failed"
    SKIPPED = "skipped"


class StoredFile(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata row for one object in Cloudflare R2.

    Bytes never pass through the API: the client requests a pre-signed PUT, uploads
    straight to R2, then confirms. Reads are handed out as short-lived signed URLs
    (US-012), so nothing here is publicly addressable.
    """

    __tablename__ = "stored_files"

    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    category: Mapped[FileCategory] = mapped_column(
        Enum(FileCategory, name="file_category"), default=FileCategory.OTHER, nullable=False
    )
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, name="upload_status"), default=UploadStatus.PENDING, nullable=False
    )

    # Loose polymorphic link — the owning row is identified by type + id so a file
    # can hang off a property, unit, tenant, payment, inspection, etc.
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Version history (US-048): a new version supersedes the previous file row.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )

    # Vault metadata (US-045, US-046). Free-form tags make a vault searchable
    # beyond the fixed category list — "2026 renewal", "insurance claim", a case
    # number — without a schema change per agency.
    tags: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Virus scan outcome (Sprint 25, US-105). Server-generated documents (leases,
    # receipts, reports) never pass through this — only user-supplied uploads do.
    scan_status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, name="scan_status"), default=ScanStatus.PENDING, nullable=False
    )
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scan_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
