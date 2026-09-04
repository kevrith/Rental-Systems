import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.organization import OrganizationRead
from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    organization_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone_number: str = Field(min_length=10, max_length=32, description="E.164 format, e.g. +2547XXXXXXXX")
    password: str = Field(min_length=8, max_length=72, description="Max 72 bytes — bcrypt's hard limit")
    account_type: str = Field(default="owner", pattern="^(owner|agency)$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_device: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
    inactivity_timeout_minutes: int | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterResponse(BaseModel):
    organization: OrganizationRead
    user: UserRead
    tokens: TokenResponse


class LoginChallengeResponse(BaseModel):
    """Either a 2FA challenge (`otp_required=True`) or, on a trusted device, the
    tokens straight away."""

    otp_required: bool = True
    challenge_token: str | None = None
    expires_in: int | None = None
    message: str
    tokens: TokenResponse | None = None


class VerifyLoginOtpRequest(BaseModel):
    challenge_token: str
    otp_code: str = Field(min_length=4, max_length=8)
    remember_device: bool = False


class VerifyPhoneRequest(BaseModel):
    otp_code: str = Field(min_length=4, max_length=8)


class VerifyEmailRequest(BaseModel):
    token: str


class ResendEmailVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_name: str
    ip_address: str | None
    location: str | None
    last_active_at: datetime
    created_at: datetime
    expires_at: datetime
    is_current: bool = False


class MessageResponse(BaseModel):
    message: str
