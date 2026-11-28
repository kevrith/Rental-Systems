import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.pin import PIN_RULE_MESSAGE, is_acceptable_pin
from app.models.user import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    full_name: str
    email: str
    phone_number: str
    role: UserRole
    is_active: bool
    is_email_verified: bool
    is_phone_verified: bool
    is_platform_staff: bool = False
    profile_photo_url: str | None = None
    always_require_2fa: bool = False
    inactivity_timeout_minutes: int = 30
    deletion_requested_at: datetime | None = None
    last_login_at: datetime | None = None
    saved_signature: str | None = None


class UserProfile(UserRead):
    """`/auth/me` — adds what the UI needs to render role-aware navigation."""

    permissions: list[str] = []


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    phone_number: str | None = Field(default=None, min_length=10, max_length=32)
    profile_photo_url: str | None = Field(default=None, max_length=1024)
    always_require_2fa: bool | None = None
    inactivity_timeout_minutes: int | None = Field(default=None, ge=5, le=1440)


class TeamMemberRead(UserRead):
    assigned_property_ids: list[uuid.UUID] = []
    cash_limit: float | None = None


class InviteUserRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    phone_number: str = Field(min_length=10, max_length=32)
    email: EmailStr | None = None
    role: UserRole = UserRole.CARETAKER
    property_ids: list[uuid.UUID] = []
    cash_limit: float | None = Field(default=None, ge=0)


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone_number: str
    email: str | None
    role: str
    status: str
    property_ids: list[uuid.UUID]
    expires_at: datetime
    created_at: datetime
    invite_link: str | None = None


class AcceptInvitationRequest(BaseModel):
    """Join through an invitation link with a password, or (caretakers only) a PIN."""

    token: str
    password: str | None = Field(default=None, min_length=8, max_length=72)
    pin: str | None = None

    @model_validator(mode="after")
    def _one_credential(self) -> "AcceptInvitationRequest":
        if (self.password is None) == (self.pin is None):
            raise ValueError("Choose a password or a PIN, not both and not neither")
        if self.pin is not None and not is_acceptable_pin(self.pin):
            raise ValueError(PIN_RULE_MESSAGE)
        return self


class InvitationPreview(BaseModel):
    full_name: str
    organization_name: str
    role: str
    phone_number: str
