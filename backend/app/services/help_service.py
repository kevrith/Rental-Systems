"""Contextual help / knowledge base (US-090). Platform-wide content — writes
are reserved for RentFlow staff (`app.api.v1.endpoints.internal`); every
authenticated user can read and search the published set.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_success import HelpArticle
from app.models.user import User
from app.schemas.customer_success import HelpArticleWrite


async def search(db: AsyncSession, query: str | None, *, video_only: bool = False) -> list[HelpArticle]:
    stmt = select(HelpArticle).where(HelpArticle.is_published.is_(True))
    if query:
        like = f"%{query}%"
        stmt = stmt.where(or_(HelpArticle.title.ilike(like), HelpArticle.body.ilike(like)))
    if video_only:
        # The "video tutorials" view (Module 24) is the same knowledge base
        # filtered, not a second content type — an article gains a video by
        # having one attached, and keeps its text either way.
        stmt = stmt.where(HelpArticle.video_url.is_not(None))
    rows = await db.scalars(stmt.order_by(HelpArticle.category, HelpArticle.title))
    return list(rows)


async def get_by_slug(db: AsyncSession, slug: str) -> HelpArticle:
    row = await db.scalar(
        select(HelpArticle).where(HelpArticle.slug == slug, HelpArticle.is_published.is_(True))
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Help article not found")
    return row


async def list_all(db: AsyncSession) -> list[HelpArticle]:
    """Every article, published or not — for the internal CMS view."""
    rows = await db.scalars(select(HelpArticle).order_by(HelpArticle.category, HelpArticle.title))
    return list(rows)


async def create(db: AsyncSession, staff: User, payload: HelpArticleWrite) -> HelpArticle:
    existing = await db.scalar(select(HelpArticle).where(HelpArticle.slug == payload.slug))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That slug is already in use")
    row = HelpArticle(
        slug=payload.slug,
        title=payload.title,
        body=payload.body,
        category=payload.category,
        is_published=payload.is_published,
        video_url=payload.video_url,
        video_duration_seconds=payload.video_duration_seconds,
        video_thumbnail_url=payload.video_thumbnail_url,
        video_provider=payload.video_provider,
        created_by_id=staff.id,
        updated_by_id=staff.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update(
    db: AsyncSession, staff: User, article_id: uuid.UUID, payload: HelpArticleWrite
) -> HelpArticle:
    row = await db.get(HelpArticle, article_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Help article not found")
    row.slug = payload.slug
    row.title = payload.title
    row.body = payload.body
    row.category = payload.category
    row.is_published = payload.is_published
    row.video_url = payload.video_url
    row.video_duration_seconds = payload.video_duration_seconds
    row.video_thumbnail_url = payload.video_thumbnail_url
    row.video_provider = payload.video_provider
    row.updated_by_id = staff.id
    await db.commit()
    await db.refresh(row)
    return row
