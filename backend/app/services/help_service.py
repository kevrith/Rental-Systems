"""Contextual help / knowledge base (US-090). Platform-wide content — writes
are reserved for RentFlow staff (`app.api.v1.endpoints.internal`); every
authenticated user can read and search the published set.
"""

import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models.customer_success import HelpArticle
from app.models.user import User
from app.schemas.customer_success import HelpArticleWrite

# Punctuation that splits a word people type as one: the hyphen in "M-Pesa",
# the dot in "e.g.", the apostrophe in a possessive. Stripped from both the
# stored text and the query so that "mpesa" finds "M-Pesa" — the single most
# searched term in this product, and the one the raw LIKE always missed.
#
# Spaces survive deliberately. Collapsing those too would fold "rent day" into
# "rentday", which is a substring of "diffe(rent day)" and of every other word
# pair that happens to run together.
_FOLDABLE = "[^a-z0-9 ]"
_fold_query = re.compile(_FOLDABLE).sub


def _folded(column: InstrumentedAttribute[str]) -> ColumnElement[str]:
    """The same folding as `_fold_query`, evaluated in Postgres."""
    return func.regexp_replace(func.lower(column), _FOLDABLE, "", "g")


def _matching(query: str) -> ColumnElement[bool]:
    """Raw match OR folded match.

    Additive by construction: every article the plain LIKE used to find is
    still found, and the folded pair only ever widens the result set.
    """
    like = f"%{query}%"
    clauses: list[ColumnElement[bool]] = [
        HelpArticle.title.ilike(like),
        HelpArticle.body.ilike(like),
    ]
    folded = _fold_query("", query.lower())
    # A query of pure punctuation folds to nothing, and "%%" would match every
    # article. The raw clauses above still answer it.
    if folded.strip():
        folded_like = f"%{folded}%"
        clauses += [
            _folded(HelpArticle.title).like(folded_like),
            _folded(HelpArticle.body).like(folded_like),
        ]
    return or_(*clauses)


def _in_reading_order(stmt: Select[tuple[HelpArticle]]) -> Select[tuple[HelpArticle]]:
    """`sort_order` first, title as the tie-break for anything unplaced."""
    return stmt.order_by(HelpArticle.sort_order, HelpArticle.title)


async def search(db: AsyncSession, query: str | None, *, video_only: bool = False) -> list[HelpArticle]:
    stmt = select(HelpArticle).where(HelpArticle.is_published.is_(True))
    if query:
        stmt = stmt.where(_matching(query))
    if video_only:
        # The "video tutorials" view (Module 24) is the same knowledge base
        # filtered, not a second content type — an article gains a video by
        # having one attached, and keeps its text either way.
        stmt = stmt.where(HelpArticle.video_url.is_not(None))
    rows = await db.scalars(_in_reading_order(stmt))
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
    rows = await db.scalars(_in_reading_order(select(HelpArticle)))
    return list(rows)


async def _next_sort_order(db: AsyncSession) -> int:
    """The end of the knowledge base, in tens.

    A new article defaults to last rather than to 0: an unplaced article
    landing at the top of the help centre is a content bug that only shows up
    for readers, while one at the bottom is visible to the author on the very
    screen they created it from.
    """
    highest = await db.scalar(select(func.max(HelpArticle.sort_order)))
    return (highest or 0) + 10


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
        sort_order=payload.sort_order if payload.sort_order is not None else await _next_sort_order(db),
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
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    row.video_url = payload.video_url
    row.video_duration_seconds = payload.video_duration_seconds
    row.video_thumbnail_url = payload.video_thumbnail_url
    row.video_provider = payload.video_provider
    row.updated_by_id = staff.id
    await db.commit()
    await db.refresh(row)
    return row
