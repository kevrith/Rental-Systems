import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.property import CaretakerAssignment
    from app.models.session import UserSession


class UserRole(str, enum.Enum):
    SYSTEM_ADMIN = "system_admin"
    OWNER = "owner"
    AGENCY_ADMIN = "agency_admin"
    PROPERTY_MANAGER = "property_manager"
    CARETAKER = "caretaker"
    ACCOUNTANT = "accountant"
    OWNER_PORTAL_USER = "owner_portal_user"
    TENANT = "tenant"


# Inactivity auto-logout defaults, in minutes (US-005). Owners hold the most
# privilege so they time out fastest; caretakers work a whole shift in the field.
DEFAULT_INACTIVITY_TIMEOUT_MINUTES: dict[UserRole, int] = {
    UserRole.SYSTEM_ADMIN: 30,
    UserRole.OWNER: 30,
    UserRole.AGENCY_ADMIN: 30,
    UserRole.PROPERTY_MANAGER: 60,
    UserRole.CARETAKER: 240,
    UserRole.ACCOUNTANT: 60,
    UserRole.OWNER_PORTAL_USER: 60,
    UserRole.TENANT: 240,
}


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # RentFlow's own staff, not a tenant role — grants access to the cross-organization
    # customer-success surface in app.api.v1.endpoints.internal (Sprint 20).
    is_platform_staff: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile_photo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Security preferences (US-002 / US-005)
    always_require_2fa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    inactivity_timeout_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    # Account deletion with a 30-day grace period (US-004)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship(
        back_populates="users", foreign_keys=[organization_id]
    )
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    caretaker_assignments: Mapped[list["CaretakerAssignment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", foreign_keys="CaretakerAssignment.user_id"
    )
