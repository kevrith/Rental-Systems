import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, get_current_user, get_org_context, require, require_write
from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.communication import TemplateChannel
from app.models.notification import (
    DeliveryStatus,
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationType,
    PushSubscription,
)
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.services import communication_template_service

router = APIRouter()
push_router = APIRouter()
# Message wording is organisation configuration, not a user's own inbox, so
# it gets its own prefix rather than sitting under /notifications.
templates_router = APIRouter()


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: NotificationChannel
    notification_type: NotificationType
    title: str
    body: str
    link_path: str | None
    status: DeliveryStatus
    error: str | None
    sent_at: datetime | None
    read_at: datetime | None
    created_at: datetime
    entity_type: str | None
    entity_id: uuid.UUID | None


class PreferenceRead(BaseModel):
    notification_type: NotificationType
    channel: NotificationChannel
    enabled: bool


class SetPreferencesRequest(BaseModel):
    preferences: list[PreferenceRead]


class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh_key: str
    auth_key: str
    user_agent: str | None = None


class VapidKeyResponse(BaseModel):
    public_key: str | None
    configured: bool


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Notification]:
    """The caller's own notification history with per-channel delivery status."""
    query = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    rows = await db.scalars(query.order_by(Notification.created_at.desc()).limit(limit))
    return list(rows)


@router.get("/unread-count", response_model=dict)
async def unread_count(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, int]:
    """Drives the app-icon badge (US-030)."""
    from sqlalchemy import func

    count = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
            Notification.channel.in_([NotificationChannel.IN_APP, NotificationChannel.PUSH]),
        )
    )
    return {"unread": int(count or 0)}


@router.post("/{notification_id}/read", response_model=MessageResponse)
async def mark_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != current_user.id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification.read_at = datetime.now(UTC)
    await db.commit()
    return MessageResponse(message="Marked as read")


@router.post("/read-all", response_model=MessageResponse)
async def mark_all_read(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    now = datetime.now(UTC)
    rows = await db.scalars(
        select(Notification).where(Notification.user_id == current_user.id, Notification.read_at.is_(None))
    )
    count = 0
    for notification in rows:
        notification.read_at = now
        count += 1
    await db.commit()
    return MessageResponse(message=f"Marked {count} notification(s) as read")


# ------------------------------------------------------------------- preferences


@router.get("/preferences", response_model=list[PreferenceRead])
async def get_preferences(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[PreferenceRead]:
    """Every type/channel pair with its current setting — defaults included, so the
    UI can render the full matrix without knowing which rows exist."""
    stored = {
        (p.notification_type, p.channel): p.enabled
        for p in await db.scalars(
            select(NotificationPreference).where(NotificationPreference.user_id == current_user.id)
        )
    }
    return [
        PreferenceRead(
            notification_type=notification_type,
            channel=channel,
            enabled=stored.get((notification_type, channel), True),
        )
        for notification_type in NotificationType
        for channel in (
            NotificationChannel.WHATSAPP,
            NotificationChannel.SMS,
            NotificationChannel.PUSH,
        )
    ]


@router.put("/preferences", response_model=MessageResponse)
async def set_preferences(
    payload: SetPreferencesRequest,
    context: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    for item in payload.preferences:
        existing = await db.scalar(
            select(NotificationPreference).where(
                NotificationPreference.user_id == context.user.id,
                NotificationPreference.notification_type == item.notification_type,
                NotificationPreference.channel == item.channel,
            )
        )
        if existing:
            existing.enabled = item.enabled
        else:
            db.add(
                NotificationPreference(
                    organization_id=context.organization_id,
                    user_id=context.user.id,
                    notification_type=item.notification_type,
                    channel=item.channel,
                    enabled=item.enabled,
                )
            )
    await db.commit()
    return MessageResponse(message="Preferences saved")


# -------------------------------------------------------------------- web push


@push_router.get("/vapid-key", response_model=VapidKeyResponse)
async def vapid_key(context: OrgContext = Depends(get_org_context)) -> VapidKeyResponse:
    """The public key the browser needs to create a push subscription.

    The key itself is public by nature, but only a signed-in user ever subscribes,
    so this sits behind a session like everything else — an endpoint that does not
    need auth today is an endpoint nobody re-examines when it starts to.
    """
    return VapidKeyResponse(public_key=settings.VAPID_PUBLIC_KEY, configured=bool(settings.VAPID_PUBLIC_KEY))


@push_router.post("/subscribe", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def subscribe(
    payload: PushSubscribeRequest,
    context: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    existing = await db.scalar(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint))
    if existing:
        # Same browser re-subscribing, possibly as a different user on a shared device.
        existing.user_id = context.user.id
        existing.organization_id = context.organization_id
        existing.p256dh_key = payload.p256dh_key
        existing.auth_key = payload.auth_key
        existing.revoked_at = None
    else:
        db.add(
            PushSubscription(
                organization_id=context.organization_id,
                user_id=context.user.id,
                endpoint=payload.endpoint,
                p256dh_key=payload.p256dh_key,
                auth_key=payload.auth_key,
                user_agent=payload.user_agent,
            )
        )
    await db.commit()
    return MessageResponse(message="Push notifications enabled")


@push_router.post("/unsubscribe", response_model=MessageResponse)
async def unsubscribe(
    endpoint: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    subscription = await db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == endpoint, PushSubscription.user_id == current_user.id
        )
    )
    if subscription:
        subscription.revoked_at = datetime.now(UTC)
        await db.commit()
    return MessageResponse(message="Push notifications disabled")


# ------------------------------------------------------- message templates


class TemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notification_type: NotificationType
    channel: TemplateChannel
    title: str | None
    body: str
    is_active: bool
    known_variables: list[str]
    last_used_at: datetime | None
    updated_at: datetime


class TemplateWrite(BaseModel):
    notification_type: NotificationType
    channel: TemplateChannel = TemplateChannel.ANY
    title: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=4000)
    is_active: bool = True


class TemplatePreviewRequest(BaseModel):
    notification_type: NotificationType
    title: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=4000)


class TemplatePreviewResponse(BaseModel):
    title: str | None
    body: str | None
    variables_used: list[str]
    available_variables: list[str]
    character_count: int
    sms_segments: int


class TemplateTypeInfo(BaseModel):
    """One editable message, and what a landlord may put in it."""

    notification_type: NotificationType
    label: str
    available_variables: list[str]


@templates_router.get("/types", response_model=list[TemplateTypeInfo])
async def list_template_types(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
) -> list[TemplateTypeInfo]:
    """Which messages can be rewritten, and the placeholders each accepts."""
    universal = set(communication_template_service.UNIVERSAL_VARIABLES)
    return [
        TemplateTypeInfo(
            notification_type=notification_type,
            label=notification_type.value.replace("_", " ").title(),
            available_variables=sorted(set(variables) | universal),
        )
        for notification_type, variables in communication_template_service.SUGGESTED_VARIABLES.items()
    ]


@templates_router.get("", response_model=list[TemplateRead])
async def list_message_templates(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[TemplateRead]:
    rows = await communication_template_service.list_templates(db, context)
    return [TemplateRead.model_validate(row) for row in rows]


@templates_router.put("", response_model=TemplateRead)
async def save_message_template(
    body: TemplateWrite,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TemplateRead:
    """Create or replace the wording for one notification type and channel."""
    row = await communication_template_service.upsert(
        db,
        context,
        notification_type=body.notification_type,
        channel=body.channel,
        title=body.title,
        body=body.body,
        is_active=body.is_active,
    )
    return TemplateRead.model_validate(row)


@templates_router.post("/preview", response_model=TemplatePreviewResponse)
async def preview_message_template(
    body: TemplatePreviewRequest,
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
) -> TemplatePreviewResponse:
    """Fill the draft with sample values. Nothing is saved and nothing is sent."""
    return TemplatePreviewResponse(
        **communication_template_service.preview(body.body, body.title, body.notification_type)
    )


@templates_router.delete("/{template_id}", response_model=MessageResponse)
async def delete_message_template(
    template_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await communication_template_service.delete(db, context, template_id)
    return MessageResponse(message="Reverted to the built-in wording")
