import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import redis_client
from app.core.security import (
    generate_url_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import OperatingMode, Organization, SubscriptionPlan
from app.models.session import TokenPurpose, VerificationToken
from app.models.user import DEFAULT_INACTIVITY_TIMEOUT_MINUTES, User, UserRole
from app.schemas.auth import (
    LoginChallengeResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services import notification_service, otp_service, session_service
from app.services.notifications import get_email_notifier, get_sms_notifier, normalize_phone

LOGIN_OTP_PURPOSE = "login"
PHONE_VERIFICATION_PURPOSE = "phone_verification"


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base or "org"


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base = _slugify(name)
    slug = base
    while await db.scalar(select(Organization.id).where(Organization.slug == slug)):
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug


def _mask_phone(phone_number: str) -> str:
    if len(phone_number) <= 6:
        return "*" * len(phone_number)
    prefix, suffix = phone_number[:4], phone_number[-2:]
    return f"{prefix}{'*' * (len(phone_number) - len(prefix) - len(suffix))}{suffix}"


def _login_fails_key(email: str) -> str:
    return f"login_fails:{email}"


def _login_lockout_key(email: str) -> str:
    return f"login_lockout:{email}"


async def _assert_not_locked_out(email: str) -> None:
    ttl = await redis_client.ttl(_login_lockout_key(email))
    if ttl and ttl > 0:
        minutes = max(1, ttl // 60)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Too many failed attempts. Try again in {minutes} minute(s).",
        )


async def _register_failed_login(email: str) -> None:
    fails_key = _login_fails_key(email)
    fails = await redis_client.incr(fails_key)
    if fails == 1:
        await redis_client.expire(fails_key, settings.LOGIN_LOCKOUT_SECONDS)
    if fails >= settings.LOGIN_MAX_ATTEMPTS:
        await redis_client.set(_login_lockout_key(email), "1", ex=settings.LOGIN_LOCKOUT_SECONDS)


async def _clear_failed_logins(email: str) -> None:
    await redis_client.delete(_login_fails_key(email), _login_lockout_key(email))


async def _send_phone_verification_otp(user: User) -> None:
    code = await otp_service.generate_otp(PHONE_VERIFICATION_PURPOSE, str(user.id))
    message = f"Your RentFlow phone verification code is {code}. It expires in 5 minutes."
    await get_sms_notifier().send(user.phone_number, message)
    if user.email:
        await get_email_notifier().send(
            user.email,
            "Your RentFlow phone verification code",
            f"<p>Hi {user.full_name.split()[0]},</p>"
            f"<p>Your phone verification code is <strong>{code}</strong>.</p>"
            f"<p>It expires in 5 minutes. If you didn't request this, you can safely ignore it.</p>",
        )


async def issue_link_token(db: AsyncSession, user: User, purpose: TokenPurpose, ttl_hours: int) -> str:
    """Mint a single-use link token, storing only its hash."""
    raw = generate_url_token()
    db.add(
        VerificationToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours),
        )
    )
    return raw


async def consume_link_token(db: AsyncSession, raw_token: str, purpose: TokenPurpose) -> VerificationToken:
    token = await db.scalar(
        select(VerificationToken).where(
            VerificationToken.token_hash == hash_token(raw_token),
            VerificationToken.purpose == purpose,
        )
    )
    if token is None or token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This link is invalid or has already been used"
        )
    if token.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This link has expired")

    token.used_at = datetime.now(UTC)
    return token


async def _send_email_verification(db: AsyncSession, user: User) -> None:
    raw = await issue_link_token(
        db, user, TokenPurpose.EMAIL_VERIFICATION, settings.EMAIL_VERIFICATION_TTL_HOURS
    )
    link = f"{settings.FRONTEND_URL}/verify-email?token={raw}"
    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_user(user),
        notification_type=NotificationType.ACCOUNT,
        title="Verify your RentFlow email",
        body=(
            f"Hi {user.full_name.split()[0]}, confirm your email address to finish setting up "
            f"your RentFlow account: {link} (the link expires in "
            f"{settings.EMAIL_VERIFICATION_TTL_HOURS} hours)."
        ),
        channels=[NotificationChannel.EMAIL, NotificationChannel.WHATSAPP],
        link_path="/verify-email",
    )


async def register_organization(
    db: AsyncSession, payload: RegisterRequest, request: Request | None = None
) -> tuple[Organization, User, TokenResponse]:
    phone = normalize_phone(payload.phone_number)
    existing = await db.scalar(
        select(User).where((User.email == payload.email) | (User.phone_number == phone))
    )
    if existing:
        conflict = "email address" if existing.email == payload.email else "phone number"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"That {conflict} is already registered. Try logging in instead.",
        )

    is_agency = payload.account_type == "agency"
    role = UserRole.AGENCY_ADMIN if is_agency else UserRole.OWNER

    slug = await _unique_slug(db, payload.organization_name)
    organization = Organization(
        name=payload.organization_name,
        slug=slug,
        operating_mode=OperatingMode.AGENCY if is_agency else OperatingMode.OWNER,
        subscription_plan=SubscriptionPlan.TRIAL,
        trial_ends_at=datetime.now(UTC) + timedelta(days=settings.TRIAL_PERIOD_DAYS),
        contact_email=payload.email,
        contact_phone=phone,
    )
    db.add(organization)
    await db.flush()

    user = User(
        organization_id=organization.id,
        full_name=payload.full_name,
        email=payload.email,
        phone_number=phone,
        password_hash=hash_password(payload.password),
        role=role,
        inactivity_timeout_minutes=DEFAULT_INACTIVITY_TIMEOUT_MINUTES[role],
    )
    db.add(user)
    await db.flush()

    session, tokens = await session_service.create_session(db, user, request)
    # The registering device is implicitly trusted — they just proved control of
    # the account by creating it.
    await session_service.trust_device(
        db, user, session.device_fingerprint, request.headers.get("user-agent") if request else None
    )

    await _send_email_verification(db, user)
    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_user(user),
        notification_type=NotificationType.WELCOME,
        title=f"Welcome to RentFlow, {user.full_name.split()[0]}",
        body=(
            f"{organization.name} is set up and your 30-day free trial has started — no card needed. "
            f"Add your first property to get going: {settings.FRONTEND_URL}/properties/new"
        ),
        channels=[NotificationChannel.WHATSAPP],
        organization_id=organization.id,
    )

    await db.commit()
    await db.refresh(organization)
    await db.refresh(user)

    await _send_phone_verification_otp(user)

    return organization, user, tokens


async def initiate_login(
    db: AsyncSession, payload: LoginRequest, request: Request | None = None
) -> LoginChallengeResponse:
    """Step 1 of login: verify the password, then either hand over tokens (trusted
    device) or dispatch an OTP."""
    await _assert_not_locked_out(payload.email)

    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        await _register_failed_login(payload.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    await _clear_failed_logins(payload.email)

    fingerprint = session_service.request_fingerprint(request)
    was_known = await session_service.is_known_device(db, user, fingerprint)

    if await session_service.is_trusted_device(db, user, fingerprint):
        tokens = await _finalize_login(db, user, request, remember_device=False, device_was_known=True)
        return LoginChallengeResponse(
            otp_required=False, message="Signed in on a trusted device", tokens=tokens
        )

    code = await otp_service.generate_otp(LOGIN_OTP_PURPOSE, str(user.id))
    await get_sms_notifier().send(
        user.phone_number, f"Your RentFlow login code is {code}. It expires in 5 minutes."
    )
    challenge_token = await otp_service.create_login_challenge(
        str(user.id), remember_device=payload.remember_device, device_was_known=was_known
    )
    await db.commit()

    return LoginChallengeResponse(
        otp_required=True,
        challenge_token=challenge_token,
        expires_in=settings.OTP_TTL_SECONDS,
        message=f"Enter the code sent to {_mask_phone(user.phone_number)}",
    )


async def complete_login(
    db: AsyncSession,
    challenge_token: str,
    otp_code: str,
    remember_device: bool = False,
    request: Request | None = None,
) -> TokenResponse:
    """Step 2 of login: verify the OTP against the challenge, then open a session."""
    challenge = await otp_service.resolve_login_challenge(challenge_token)
    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login session expired — please log in again"
        )

    user_id = challenge["user_id"]
    if not await otp_service.verify_otp(LOGIN_OTP_PURPOSE, user_id, otp_code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired code")

    await otp_service.consume_login_challenge(challenge_token)

    user = await db.get(User, user_id)
    if not user or not user.is_active or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return await _finalize_login(
        db,
        user,
        request,
        remember_device=remember_device or challenge["remember_device"],
        device_was_known=challenge["device_was_known"],
    )


async def _finalize_login(
    db: AsyncSession,
    user: User,
    request: Request | None,
    *,
    remember_device: bool,
    device_was_known: bool,
) -> TokenResponse:
    session, tokens = await session_service.create_session(db, user, request)
    user.last_login_at = datetime.now(UTC)

    if remember_device:
        await session_service.trust_device(
            db, user, session.device_fingerprint, request.headers.get("user-agent") if request else None
        )

    if not device_was_known:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(user),
            notification_type=NotificationType.SUSPICIOUS_LOGIN,
            title="New sign-in to your RentFlow account",
            body=(
                f"A new sign-in was detected on {session.device_name}"
                f"{f' from {session.ip_address}' if session.ip_address else ''} at "
                f"{datetime.now(UTC).strftime('%d %b %Y %H:%M')} UTC. "
                "If this wasn't you, change your password and revoke the session immediately."
            ),
            channels=[NotificationChannel.WHATSAPP],
        )

    await db.commit()
    return tokens


async def verify_phone(db: AsyncSession, user: User, otp_code: str) -> User:
    if user.is_phone_verified:
        return user

    if not await otp_service.verify_otp(PHONE_VERIFICATION_PURPOSE, str(user.id), otp_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code")

    user.is_phone_verified = True
    await db.commit()
    await db.refresh(user)
    return user


async def resend_phone_verification(user: User) -> None:
    if not user.is_phone_verified:
        await _send_phone_verification_otp(user)


async def verify_email(db: AsyncSession, raw_token: str) -> User:
    token = await consume_link_token(db, raw_token, TokenPurpose.EMAIL_VERIFICATION)
    user = await db.get(User, token.user_id) if token.user_id else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    user.is_email_verified = True
    await db.commit()
    await db.refresh(user)
    return user


async def resend_email_verification(db: AsyncSession, email: str) -> None:
    """Always succeeds from the caller's point of view — a differing response would
    let an attacker enumerate registered addresses."""
    user = await db.scalar(select(User).where(User.email == email))
    if user and not user.is_email_verified:
        await _send_email_verification(db, user)
        await db.commit()


async def request_password_reset(db: AsyncSession, email: str) -> None:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return  # Silent, for the same enumeration reason.

    raw = await issue_link_token(db, user, TokenPurpose.PASSWORD_RESET, settings.PASSWORD_RESET_TTL_HOURS)
    link = f"{settings.FRONTEND_URL}/reset-password?token={raw}"
    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_user(user),
        notification_type=NotificationType.ACCOUNT,
        title="Reset your RentFlow password",
        body=(
            f"Use this link to set a new password: {link}\n"
            f"It expires in {settings.PASSWORD_RESET_TTL_HOURS} hours. "
            "If you didn't ask for this, you can safely ignore it."
        ),
        channels=[NotificationChannel.SMS, NotificationChannel.EMAIL],
    )
    await db.commit()


async def reset_password(db: AsyncSession, raw_token: str, new_password: str) -> None:
    token = await consume_link_token(db, raw_token, TokenPurpose.PASSWORD_RESET)
    user = await db.get(User, token.user_id) if token.user_id else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    user.password_hash = hash_password(new_password)
    # A password reset invalidates every existing session — that is the whole point.
    await session_service.revoke_all(db, user.id)
    await db.commit()


async def create_portal_user(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    full_name: str,
    phone_number: str,
    email: str | None,
    role: UserRole,
) -> User:
    """Create a user account for an owner portal invitation (US-038).

    The user has no password yet — they set one via the invitation link.
    """
    phone = normalize_phone(phone_number)
    # Ensure no duplicate phone
    existing = await db.scalar(select(User).where(User.phone_number == phone))
    if existing:
        # Return existing user if already a portal user for this org
        if existing.organization_id == organization_id:
            return existing
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That phone number is already registered",
        )

    user = User(
        organization_id=organization_id,
        full_name=full_name,
        email=email or f"portal-{uuid.uuid4().hex[:8]}@rentflow.local",
        phone_number=phone,
        password_hash="!",  # Unusable until they set a password via invite link
        role=role,
        inactivity_timeout_minutes=DEFAULT_INACTIVITY_TIMEOUT_MINUTES[role],
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user
