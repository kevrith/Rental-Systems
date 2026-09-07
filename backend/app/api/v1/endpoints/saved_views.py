import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require
from app.core.database import get_db
from app.models.saved_view import SavedView
from app.schemas.saved_view import SavedViewCreate, SavedViewRead, SavedViewUpdate
from app.services import saved_view_service

router = APIRouter()


@router.get("", response_model=list[SavedViewRead])
async def list_saved_views(
    entity_type: str = Query(min_length=1, max_length=64),
    context: OrgContext = Depends(require()),
    db: AsyncSession = Depends(get_db),
) -> list[SavedView]:
    return await saved_view_service.list_views(db, context, entity_type)


@router.post("", response_model=SavedViewRead, status_code=status.HTTP_201_CREATED)
async def create_saved_view(
    payload: SavedViewCreate,
    context: OrgContext = Depends(require()),
    db: AsyncSession = Depends(get_db),
) -> SavedView:
    return await saved_view_service.create_view(db, context, payload)


@router.patch("/{view_id}", response_model=SavedViewRead)
async def update_saved_view(
    view_id: uuid.UUID,
    payload: SavedViewUpdate,
    context: OrgContext = Depends(require()),
    db: AsyncSession = Depends(get_db),
) -> SavedView:
    return await saved_view_service.update_view(db, context, view_id, payload)


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_view(
    view_id: uuid.UUID,
    context: OrgContext = Depends(require()),
    db: AsyncSession = Depends(get_db),
) -> None:
    await saved_view_service.delete_view(db, context, view_id)
