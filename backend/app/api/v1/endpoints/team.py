import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.session import Invitation, InvitationStatus
from app.schemas.auth import MessageResponse, TokenResponse
from app.schemas.user import (
    AcceptInvitationRequest,
    InvitationPreview,
    InvitationRead,
    InviteUserRequest,
    TeamMemberRead,
    UserRead,
)
from app.services import user_service

router = APIRouter()


class UpdateAccessRequest(BaseModel):
    is_active: bool | None = None
    property_ids: list[uuid.UUID] | None = None
    cash_limit: float | None = Field(default=None, ge=0)


class AcceptInvitationResponse(BaseModel):
    user: UserRead
    tokens: TokenResponse


@router.get("", response_model=list[TeamMemberRead])
async def list_team(
    context: OrgContext = Depends(require(Permission.USER_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[TeamMemberRead]:
    rows = await user_service.list_team(db, context)
    return [
        TeamMemberRead(
            **UserRead.model_validate(user).model_dump(),
            assigned_property_ids=property_ids,
            cash_limit=float(limit) if limit is not None else None,
        )
        for user, property_ids, limit in rows
    ]


@router.post("/invitations", response_model=InvitationRead, status_code=status.HTTP_201_CREATED)
async def invite(
    payload: InviteUserRequest,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.USER_INVITE)),
    db: AsyncSession = Depends(get_db),
) -> InvitationRead:
    from app.core.config import settings

    invitation, raw_token = await user_service.invite_user(db, context, payload, request)
    data = InvitationRead.model_validate(invitation)
    data.invite_link = f"{settings.FRONTEND_URL}/accept-invite?token={raw_token}"
    return data


@router.get("/invitations", response_model=list[InvitationRead])
async def list_invitations(
    context: OrgContext = Depends(require(Permission.USER_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[Invitation]:
    rows = await db.scalars(
        select(Invitation)
        .where(
            Invitation.organization_id == context.organization_id,
            Invitation.status == InvitationStatus.PENDING,
        )
        .order_by(Invitation.created_at.desc())
    )
    return list(rows)


@router.delete("/invitations/{invitation_id}", response_model=MessageResponse)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.USER_INVITE)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await user_service.revoke_invitation(db, context, invitation_id)
    return MessageResponse(message="Invitation revoked")


@router.patch("/{user_id}/access", response_model=UserRead)
async def update_access(
    user_id: uuid.UUID,
    payload: UpdateAccessRequest,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.USER_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.set_user_access(
        db,
        context,
        user_id,
        is_active=payload.is_active,
        property_ids=payload.property_ids,
        cash_limit=Decimal(str(payload.cash_limit)) if payload.cash_limit is not None else None,
        request=request,
    )


# ---------------------------------------------------- public invitation acceptance


public_router = APIRouter()


@public_router.get("/preview", response_model=InvitationPreview)
async def preview_invitation(token: str, db: AsyncSession = Depends(get_db)) -> InvitationPreview:
    invitation, organization_name = await user_service.preview_invitation(db, token)
    return InvitationPreview(
        full_name=invitation.full_name,
        organization_name=organization_name,
        role=invitation.role,
        phone_number=invitation.phone_number,
    )


@public_router.post("/accept", response_model=AcceptInvitationResponse)
async def accept_invitation(
    payload: AcceptInvitationRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> AcceptInvitationResponse:
    user, tokens = await user_service.accept_invitation(db, payload, request)
    return AcceptInvitationResponse(user=user, tokens=tokens)  # type: ignore[arg-type]
