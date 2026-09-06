"""In-app changelog (US-092). Platform-wide announcements — "unseen" is
computed against `User.last_login_at` rather than a separate marker column, so
there is nothing new to keep in sync when a user logs in.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_success import ChangelogEntry
from app.models.user import User
from app.schemas.customer_success import ChangelogEntryWrite


async def list_published(db: AsyncSession, limit: int = 20) -> list[ChangelogEntry]:
    rows = await db.scalars(
        select(ChangelogEntry)
        .where(ChangelogEntry.is_published.is_(True))
        .order_by(ChangelogEntry.published_at.desc())
        .limit(limit)
    )
    return list(rows)


async def list_all(db: AsyncSession, limit: int = 100) -> list[ChangelogEntry]:
    """Published and unpublished — for the internal CMS view."""
    rows = await db.scalars(select(ChangelogEntry).order_by(ChangelogEntry.published_at.desc()).limit(limit))
    return list(rows)


async def unseen_count(db: AsyncSession, viewer: User) -> int:
    since = viewer.last_login_at
    query = select(func.count(ChangelogEntry.id)).where(ChangelogEntry.is_published.is_(True))
    if since is not None:
        query = query.where(ChangelogEntry.published_at > since)
    return int(await db.scalar(query) or 0)


async def create(db: AsyncSession, author: User, payload: ChangelogEntryWrite) -> ChangelogEntry:
    row = ChangelogEntry(
        title=payload.title,
        body=payload.body,
        is_published=payload.is_published,
        published_at=datetime.now(UTC),
        created_by_id=author.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update(db: AsyncSession, entry_id: uuid.UUID, payload: ChangelogEntryWrite) -> ChangelogEntry:
    row = await db.get(ChangelogEntry, entry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Changelog entry not found")
    row.title = payload.title
    row.body = payload.body
    row.is_published = payload.is_published
    await db.commit()
    await db.refresh(row)
    return row
