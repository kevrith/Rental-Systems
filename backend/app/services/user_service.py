"""Profile management, team invitations and caretaker assignment (US-004, US-013)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.core.config import settings
from app.core.security import generate_url_token, hash_password, hash_token, verify_password
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import CaretakerAssignment, Property
from app.models.session import Invitation, InvitationStatus
from app.models.user import DEFAULT_INACTIVITY_TIMEOUT_MINUTES, User, UserRole
from app.schemas.user import AcceptInvitationRequest, InviteUserRequest, UpdateProfileRequest
from app.services import audit_service, auth_service, notification_service, session_service
from app.services.notifications import get_sms_notifier, normalize_phone


async def update_profile(
    db: AsyncSession, user: User, payload: UpdateProfileRequest, request: Request | None = None
) -> User:
    before = {
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "always_require_2fa": user.always_require_2fa,
        "inactivity_timeout_minutes": user.inactivity_timeout_minutes,
    }

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.profile_photo_url is not None:
        user.profile_photo_url = payload.profile_photo_url
    if payload.always_require_2fa is not None:
        user.always_require_2fa = payload.always_require_2fa
    if payload.inactivity_timeout_minutes is not None:
        user.inactivity_timeout_minutes = payload.inactivity_timeout_minutes

    if payload.phone_number is not None:
        new_phone = normalize_phone(payload.phone_number)
        if new_phone != user.phone_number:
            clash = await db.scalar(select(User.id).where(User.phone_number == new_phone, User.id != user.id))
            if clash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="That phone number belongs to another account",
                )
            user.phone_number = new_phone
            # A changed number is unverified until a fresh OTP proves it.
            user.is_phone_verified = False

    after = {
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "always_require_2fa": user.always_require_2fa,
        "inactivity_timeout_minutes": user.inactivity_timeout_minutes,
    }
    audit_service.record(
        db,
        organization_id=user.organization_id,
        action="user.profile_updated",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        summary="Updated their profile",
        changes=audit_service.diff(before, after),
        request=request,
    )
    await db.commit()
    await db.refresh(user)

    if before["phone_number"] != user.phone_number:
        await auth_service.resend_phone_verification(user)
    return user


async def change_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
    request: Request | None = None,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Your current password is incorrect"
        )
    if verify_password(new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose a password you haven't used on this account",
        )

    user.password_hash = hash_password(new_password)
    current_session = session_service.request_fingerprint(request)
    # Keep the caller signed in on this device, drop everything else.
    await session_service.revoke_all(db, user.id, _session_id_from_request(request))

    audit_service.record(
        db,
        organization_id=user.organization_id,
        action="user.password_changed",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        summary="Changed their password",
        changes={"device_fingerprint": current_session},
        request=request,
    )
    await db.commit()


def _session_id_from_request(request: Request | None) -> uuid.UUID | None:
    if request is None:
        return None
    from app.core.security import decode_token

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


async def request_account_deletion(db: AsyncSession, user: User, request: Request | None = None) -> int:
    """Soft delete with a grace period — nothing is destroyed on the spot (US-004)."""
    user.deletion_requested_at = datetime.now(UTC)
    audit_service.record(
        db,
        organization_id=user.organization_id,
        action="user.deletion_requested",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        summary=f"Requested account deletion ({settings.ACCOUNT_DELETION_GRACE_DAYS}-day grace period)",
        request=request,
    )
    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_user(user),
        notification_type=NotificationType.ACCOUNT,
        title="Account deletion scheduled",
        body=(
            f"Your RentFlow account will be deleted in {settings.ACCOUNT_DELETION_GRACE_DAYS} days. "
            "Log in and cancel before then if this wasn't intended."
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
    )
    await db.commit()
    return settings.ACCOUNT_DELETION_GRACE_DAYS


async def cancel_account_deletion(db: AsyncSession, user: User, request: Request | None = None) -> None:
    user.deletion_requested_at = None
    audit_service.record(
        db,
        organization_id=user.organization_id,
        action="user.deletion_cancelled",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        summary="Cancelled account deletion",
        request=request,
    )
    await db.commit()


# ------------------------------------------------------------------ team & invites


async def list_team(
    db: AsyncSession, context: OrgContext
) -> list[tuple[User, list[uuid.UUID], Decimal | None]]:
    users = list(
        await db.scalars(
            select(User)
            .where(User.organization_id == context.organization_id, User.deleted_at.is_(None))
            .order_by(User.created_at)
        )
    )
    assignments = list(
        await db.scalars(
            select(CaretakerAssignment).where(
                CaretakerAssignment.organization_id == context.organization_id,
                CaretakerAssignment.is_active.is_(True),
            )
        )
    )

    by_user: dict[uuid.UUID, list[CaretakerAssignment]] = {}
    for assignment in assignments:
        by_user.setdefault(assignment.user_id, []).append(assignment)

    result = []
    for user in users:
        owned = by_user.get(user.id, [])
        limit = next((a.cash_limit for a in owned if a.cash_limit is not None), None)
        result.append((user, [a.property_id for a in owned], limit))
    return result


async def invite_user(
    db: AsyncSession, context: OrgContext, payload: InviteUserRequest, request: Request | None = None
) -> tuple[Invitation, str]:
    """Create a pending invitation and SMS the one-click setup link."""
    if payload.role in (UserRole.SYSTEM_ADMIN, UserRole.TENANT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System admins and tenants cannot be invited as staff",
        )

    phone = normalize_phone(payload.phone_number)
    if await db.scalar(select(User.id).where(User.phone_number == phone)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Someone with that phone number already has an account",
        )

    # Every named property must exist inside this organization.
    for property_id in payload.property_ids:
        prop = await db.get(Property, property_id)
        if prop is None or prop.organization_id != context.organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown property {property_id}"
            )

    raw_token = generate_url_token()
    invitation = Invitation(
        organization_id=context.organization_id,
        full_name=payload.full_name,
        phone_number=phone,
        email=payload.email,
        role=payload.role.value,
        property_ids=[str(pid) for pid in payload.property_ids],
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.INVITATION_TTL_HOURS),
        invited_by_id=context.user.id,
        cash_limit=Decimal(str(payload.cash_limit)) if payload.cash_limit is not None else None,
    )
    db.add(invitation)

    link = f"{settings.FRONTEND_URL}/accept-invite?token={raw_token}"
    await get_sms_notifier().send(
        phone,
        f"{context.user.full_name} invited you to {context.organization.name} on RentFlow. "
        f"Set your password here: {link}",
    )

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="user.invited",
        entity_type="invitation",
        actor=context.user,
        summary=f"Invited {payload.full_name} as {payload.role.value}",
        request=request,
    )
    await db.commit()
    await db.refresh(invitation)
    return invitation, raw_token


async def preview_invitation(db: AsyncSession, raw_token: str) -> tuple[Invitation, str]:
    invitation = await db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(raw_token)))
    if invitation is None or invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This invitation is no longer valid"
        )
    if invitation.expires_at <= datetime.now(UTC):
        invitation.status = InvitationStatus.EXPIRED
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This invitation has expired")

    from app.models.organization import Organization

    organization = await db.get(Organization, invitation.organization_id)
    return invitation, organization.name if organization else ""


async def accept_invitation(
    db: AsyncSession, payload: AcceptInvitationRequest, request: Request | None = None
) -> tuple[User, object]:
    invitation, _ = await preview_invitation(db, payload.token)

    role = UserRole(invitation.role)
    user = User(
        organization_id=invitation.organization_id,
        full_name=invitation.full_name,
        email=invitation.email or f"{invitation.phone_number.lstrip('+')}@no-email.rentflow.local",
        phone_number=invitation.phone_number,
        password_hash=hash_password(payload.password),
        role=role,
        is_phone_verified=True,  # They received the invite link on this number.
        inactivity_timeout_minutes=DEFAULT_INACTIVITY_TIMEOUT_MINUTES[role],
    )
    db.add(user)
    await db.flush()

    for property_id in invitation.property_ids:
        db.add(
            CaretakerAssignment(
                organization_id=invitation.organization_id,
                user_id=user.id,
                property_id=uuid.UUID(str(property_id)),
                cash_limit=invitation.cash_limit,
            )
        )

    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(UTC)
    invitation.accepted_user_id = user.id

    _, tokens = await session_service.create_session(db, user, request)

    audit_service.record(
        db,
        organization_id=invitation.organization_id,
        action="user.invitation_accepted",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        summary=f"{user.full_name} joined as {role.value}",
        request=request,
    )
    await db.commit()
    await db.refresh(user)
    return user, tokens


async def revoke_invitation(db: AsyncSession, context: OrgContext, invitation_id: uuid.UUID) -> None:
    invitation = await db.get(Invitation, invitation_id)
    if invitation is None or invitation.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    invitation.status = InvitationStatus.REVOKED
    await db.commit()


async def set_user_access(
    db: AsyncSession,
    context: OrgContext,
    user_id: uuid.UUID,
    *,
    is_active: bool | None = None,
    property_ids: list[uuid.UUID] | None = None,
    cash_limit: Decimal | None = None,
    request: Request | None = None,
) -> User:
    """Activate/deactivate a team member and reset their property assignments."""
    user = await db.get(User, user_id)
    if user is None or user.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == context.user.id and is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own account"
        )

    if is_active is not None:
        user.is_active = is_active
        if not is_active:
            await session_service.revoke_all(db, user.id)

    if property_ids is not None:
        existing = list(
            await db.scalars(
                select(CaretakerAssignment).where(
                    CaretakerAssignment.user_id == user.id,
                    CaretakerAssignment.organization_id == context.organization_id,
                )
            )
        )
        wanted = set(property_ids)
        for assignment in existing:
            keep = assignment.property_id in wanted
            assignment.is_active = keep
            assignment.revoked_at = None if keep else datetime.now(UTC)
            if cash_limit is not None and keep:
                assignment.cash_limit = cash_limit
            wanted.discard(assignment.property_id)

        for property_id in wanted:
            prop = await db.get(Property, property_id)
            if prop is None or prop.organization_id != context.organization_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown property {property_id}"
                )
            db.add(
                CaretakerAssignment(
                    organization_id=context.organization_id,
                    user_id=user.id,
                    property_id=property_id,
                    cash_limit=cash_limit,
                )
            )

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="user.access_updated",
        entity_type="user",
        entity_id=user.id,
        actor=context.user,
        summary=f"Updated access for {user.full_name}",
        request=request,
    )
    await db.commit()
    await db.refresh(user)
    return user
