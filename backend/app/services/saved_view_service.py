"""Saved views (Sprint 26A, item 11) — a named filter set for one list screen.

Ownership is simple on purpose: a view is created, renamed and deleted only by
the user who made it — `is_shared` controls whether *other* organisation
members can see and apply it, not whether they can edit it. Letting anyone
edit a shared view would mean the ops lead's carefully-built "overdue and
unassigned" view could be silently rewritten by whoever opened it last.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.saved_view import SavedView
from app.schemas.saved_view import SavedViewCreate, SavedViewUpdate


async def _clear_other_defaults(db: AsyncSession, context: OrgContext, entity_type: str) -> None:
    existing = await db.scalars(
        select(SavedView).where(
            SavedView.organization_id == context.organization_id,
            SavedView.user_id == context.user.id,
            SavedView.entity_type == entity_type,
            SavedView.is_default.is_(True),
        )
    )
    for view in existing:
        view.is_default = False


async def list_views(db: AsyncSession, context: OrgContext, entity_type: str) -> list[SavedView]:
    query = (
        select(SavedView)
        .where(
            SavedView.organization_id == context.organization_id,
            SavedView.entity_type == entity_type,
            or_(SavedView.user_id == context.user.id, SavedView.is_shared.is_(True)),
        )
        .order_by(SavedView.name)
    )
    return list(await db.scalars(query))


async def create_view(db: AsyncSession, context: OrgContext, payload: SavedViewCreate) -> SavedView:
    clash = await db.scalar(
        select(SavedView.id).where(
            SavedView.user_id == context.user.id,
            SavedView.entity_type == payload.entity_type,
            SavedView.name == payload.name,
        )
    )
    if clash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have a saved view named '{payload.name}' for {payload.entity_type}",
        )

    if payload.is_default:
        await _clear_other_defaults(db, context, payload.entity_type)

    view = SavedView(
        organization_id=context.organization_id,
        user_id=context.user.id,
        entity_type=payload.entity_type,
        name=payload.name,
        filters=payload.filters,
        is_shared=payload.is_shared,
        is_default=payload.is_default,
    )
    db.add(view)
    await db.commit()
    await db.refresh(view)
    return view


async def _get_owned(db: AsyncSession, context: OrgContext, view_id: uuid.UUID) -> SavedView:
    view = assert_in_org(await db.get(SavedView, view_id), context, label="saved view")
    if view.user_id != context.user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner of a saved view can change it"
        )
    return view


async def update_view(
    db: AsyncSession, context: OrgContext, view_id: uuid.UUID, payload: SavedViewUpdate
) -> SavedView:
    view = await _get_owned(db, context, view_id)
    fields = payload.model_dump(exclude_unset=True)

    if fields.get("is_default"):
        await _clear_other_defaults(db, context, view.entity_type)

    for field, value in fields.items():
        setattr(view, field, value)

    await db.commit()
    await db.refresh(view)
    return view


async def delete_view(db: AsyncSession, context: OrgContext, view_id: uuid.UUID) -> None:
    view = await _get_owned(db, context, view_id)
    await db.delete(view)
    await db.commit()
