"""The shared feature-voting board (US-092). Platform-wide: every organisation's
users see and vote on the same list, so nothing here is scoped by
`organization_id`.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_success import FeatureRequest, FeatureVote
from app.models.user import User
from app.schemas.customer_success import FeatureRequestCreate, FeatureRequestRead


async def list_requests(db: AsyncSession, viewer: User) -> list[FeatureRequestRead]:
    vote_counts = dict(
        (row.feature_request_id, row.count)
        for row in (
            await db.execute(
                select(FeatureVote.feature_request_id, func.count().label("count")).group_by(
                    FeatureVote.feature_request_id
                )
            )
        ).all()
    )
    my_votes = set(
        await db.scalars(select(FeatureVote.feature_request_id).where(FeatureVote.user_id == viewer.id))
    )
    requests = await db.scalars(select(FeatureRequest).order_by(FeatureRequest.created_at.desc()))
    return [
        FeatureRequestRead(
            id=row.id,
            title=row.title,
            description=row.description,
            status=row.status,
            vote_count=vote_counts.get(row.id, 0),
            voted_by_me=row.id in my_votes,
            created_at=row.created_at,
        )
        for row in requests
    ]


async def create_request(db: AsyncSession, submitter: User, payload: FeatureRequestCreate) -> FeatureRequest:
    row = FeatureRequest(title=payload.title, description=payload.description, submitted_by_id=submitter.id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def toggle_vote(db: AsyncSession, voter: User, feature_request_id: uuid.UUID) -> bool:
    """Returns True if a vote was added, False if an existing vote was removed."""
    existing = await db.scalar(
        select(FeatureVote).where(
            FeatureVote.feature_request_id == feature_request_id, FeatureVote.user_id == voter.id
        )
    )
    if existing is not None:
        await db.delete(existing)
        await db.commit()
        return False

    stmt = pg_insert(FeatureVote).values(feature_request_id=feature_request_id, user_id=voter.id)
    await db.execute(stmt.on_conflict_do_nothing(constraint="uq_feature_vote_user"))
    await db.commit()
    return True
