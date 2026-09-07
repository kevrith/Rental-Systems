from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require
from app.core.database import get_db
from app.schemas.search import SearchResultRead
from app.services import search_service

router = APIRouter()


@router.get("", response_model=list[SearchResultRead])
async def search(
    q: str = Query(min_length=1, max_length=255),
    context: OrgContext = Depends(require()),
    db: AsyncSession = Depends(get_db),
) -> list[search_service.SearchResult]:
    """Cross-entity search for the command palette (Sprint 26A). No specific
    permission gate here — `search_service.search` checks per-entity-type
    view permissions itself, so a caretaker gets tenant/unit results and no
    403, rather than the whole endpoint requiring the union of every
    permission any result type might need."""
    return await search_service.search(db, context, q)
