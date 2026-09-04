import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.permissions import permissions_for
from app.core.security import decode_token
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginChallengeResponse,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResendEmailVerificationRequest,
    ResetPasswordRequest,
    SessionRead,
    TokenResponse,
    VerifyEmailRequest,
    VerifyLoginOtpRequest,
    VerifyPhoneRequest,
)
from app.schemas.user import UpdateProfileRequest, UserProfile, UserRead
from app.services import auth_service, session_service, user_service

router = APIRouter()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> RegisterResponse:
    organization, user, tokens = await auth_service.register_organization(db, payload, request)
    return RegisterResponse(organization=organization, user=user, tokens=tokens)  # type: ignore[arg-type]


@router.post("/login", response_model=LoginChallengeResponse)
async def login(
    payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> LoginChallengeResponse:
    """Step 1: verify the password. Trusted devices get tokens here; everyone else
    gets an OTP challenge."""
    return await auth_service.initiate_login(db, payload, request)


@router.post("/login/verify-otp", response_model=TokenResponse)
async def verify_login_otp(
    payload: VerifyLoginOtpRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Step 2: verify the OTP and open a session."""
    return await auth_service.complete_login(
        db, payload.challenge_token, payload.otp_code, payload.remember_device, request
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    return await session_service.rotate(db, payload.refresh_token, request)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: LogoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """End the session the caller is on. Falls back to the refresh token's session
    when the access token predates session binding."""
    session_id: uuid.UUID | None = None
    if payload.refresh_token:
        token_payload = decode_token(payload.refresh_token)
        if token_payload and token_payload.get("sid"):
            session_id = uuid.UUID(token_payload["sid"])

    if session_id:
        await session_service.revoke(db, current_user, session_id)
    else:
        await session_service.revoke_all(db, current_user.id)
    await db.commit()
    return MessageResponse(message="Signed out")


# ----------------------------------------------------------------- verification


@router.post("/verify-phone", response_model=UserRead)
async def verify_phone(
    payload: VerifyPhoneRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await auth_service.verify_phone(db, current_user, payload.otp_code)


@router.post("/verify-phone/resend", status_code=status.HTTP_204_NO_CONTENT)
async def resend_phone_verification(current_user: User = Depends(get_current_user)) -> None:
    await auth_service.resend_phone_verification(current_user)


@router.post("/verify-email", response_model=UserRead)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> User:
    return await auth_service.verify_email(db, payload.token)


@router.post("/verify-email/resend", response_model=MessageResponse)
async def resend_email_verification(
    payload: ResendEmailVerificationRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    await auth_service.resend_email_verification(db, payload.email)
    return MessageResponse(message="If that address needs verifying, a new link is on its way.")


# -------------------------------------------------------------------- passwords


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    await auth_service.request_password_reset(db, payload.email)
    return MessageResponse(message="If that account exists, a reset link is on its way.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    await auth_service.reset_password(db, payload.token, payload.new_password)
    return MessageResponse(message="Password updated. Please log in again.")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await user_service.change_password(
        db, current_user, payload.current_password, payload.new_password, request
    )
    return MessageResponse(message="Password changed. Other devices have been signed out.")


# ---------------------------------------------------------------------- profile


@router.get("/me", response_model=UserProfile)
async def me(current_user: User = Depends(get_current_user)) -> UserProfile:
    return UserProfile(
        **UserRead.model_validate(current_user).model_dump(),
        permissions=permissions_for(current_user.role),
    )


@router.patch("/me", response_model=UserProfile)
async def update_me(
    payload: UpdateProfileRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    user = await user_service.update_profile(db, current_user, payload, request)
    return UserProfile(**UserRead.model_validate(user).model_dump(), permissions=permissions_for(user.role))


@router.post("/me/delete", response_model=MessageResponse)
async def request_account_deletion(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    grace_days = await user_service.request_account_deletion(db, current_user, request)
    return MessageResponse(
        message=(
            f"Deletion requested. Your account stays recoverable for {grace_days} days — "
            "log in and cancel any time before then."
        )
    )


@router.post("/me/delete/cancel", response_model=MessageResponse)
async def cancel_account_deletion(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await user_service.cancel_account_deletion(db, current_user, request)
    return MessageResponse(message="Deletion cancelled. Your account is active again.")


# --------------------------------------------------------------------- sessions


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionRead]:
    current_session_id = _current_session_id(request)
    sessions = await session_service.list_sessions(db, current_user)
    return [
        SessionRead(
            **SessionRead.model_validate(session).model_dump(exclude={"is_current"}),
            is_current=session.id == current_session_id,
        )
        for session in sessions
    ]


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def revoke_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await session_service.revoke(db, current_user, session_id)
    await db.commit()
    return MessageResponse(message="Session revoked")


@router.post("/sessions/revoke-others", response_model=MessageResponse)
async def revoke_other_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    revoked = await session_service.revoke_all(db, current_user.id, _current_session_id(request))
    await db.commit()
    return MessageResponse(message=f"Signed out of {revoked} other session(s)")


def _current_session_id(request: Request) -> uuid.UUID | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    payload = decode_token(header.split(" ", 1)[1])
    if not payload or not payload.get("sid"):
        return None
    try:
        return uuid.UUID(payload["sid"])
    except ValueError:
        return None
