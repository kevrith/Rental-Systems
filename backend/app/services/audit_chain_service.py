"""Hash-chained audit log (Sprint 26A) — item 8 of the enterprise-readiness pass.

`audit_service.record` is called from ~130 places across the codebase,
synchronously, inside whatever transaction is already open — it just
`db.add()`s a row and lets the caller's own commit land it. Making that
function itself compute a hash chain would mean either querying for "the
current tail hash" inside every one of those 130 call sites (turning a cheap,
fire-and-forget audit write into a query, and racing two concurrent writes to
the same organisation's chain against each other — two requests could both
read the same tail and each claim to extend it, corrupting the chain) or
rewriting every call site to `await` a newly-async `record` and serializing
audit writes per organisation, which is a lot of invasive, high-risk surface
for a feature whose entire point is "does not touch what it certifies."

So the chain is built after the fact instead, by a single scheduled job that
processes each organisation's *unhashed* rows in insertion order and stops
being ambiguous about ordering the moment it does: `entry_hash` is never
recomputed once set, so a later run only ever appends. `record()` itself is
untouched.

The hash reuses `app.core.security.sign_payload` — the exact same HMAC
construction receipts are already signed with (US-023) — over `prev_hash`
plus every field of the row that could be silently altered without changing
what actually happened. Being HMAC-keyed (not a bare hash) matters: a bare
SHA-256 chain only proves internal consistency to anyone who can read the
rows, but someone with full database write access could still delete every
row and rebuild a self-consistent chain from scratch. An attacker without
`SECRET_KEY` cannot forge a valid chain no matter how much of the database
they control, which is what "provably unaltered, not just append-only by
convention" actually requires.
"""

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import sign_payload
from app.models.audit import AuditLog

GENESIS_HASH = "0" * 32
CHAIN_BATCH_SIZE = 1000


def _hash_entry(entry: AuditLog, prev_hash: str) -> str:
    changes_json = json.dumps(entry.changes, sort_keys=True, default=str) if entry.changes else ""
    assert entry.created_at is not None  # only ever hashed after a commit assigns it
    return sign_payload(
        prev_hash,
        str(entry.id),
        entry.created_at.isoformat(),
        str(entry.organization_id),
        str(entry.user_id or ""),
        entry.action,
        entry.entity_type,
        str(entry.entity_id or ""),
        entry.summary or "",
        changes_json,
    )


async def _tail_hash(db: AsyncSession, organization_id: uuid.UUID) -> str:
    tail = await db.scalar(
        select(AuditLog.entry_hash)
        .where(AuditLog.organization_id == organization_id, AuditLog.entry_hash.isnot(None))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    )
    return tail or GENESIS_HASH


async def chain_new_entries(db: AsyncSession, organization_id: uuid.UUID) -> int:
    """Hash every unchained row for this organisation, oldest first. Commits. Returns the count."""
    prev_hash = await _tail_hash(db, organization_id)

    pending = list(
        await db.scalars(
            select(AuditLog)
            .where(AuditLog.organization_id == organization_id, AuditLog.entry_hash.is_(None))
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .limit(CHAIN_BATCH_SIZE)
        )
    )
    for entry in pending:
        entry.prev_hash = prev_hash
        entry.entry_hash = _hash_entry(entry, prev_hash)
        prev_hash = entry.entry_hash

    if pending:
        await db.commit()
    return len(pending)


@dataclass
class ChainVerification:
    total: int
    verified: int
    unchained: int
    intact: bool
    broken_at_id: uuid.UUID | None = None
    broken_at_created_at: str | None = None


async def verify_chain(db: AsyncSession, organization_id: uuid.UUID) -> ChainVerification:
    """Recompute every hash from the stored fields and compare. Read-only.

    `unchained` counts rows the scheduled job has not reached yet — not a
    problem on its own (they are simply not certified *yet*), only worth
    surfacing so a large, growing count can be noticed and investigated as a
    sign the scheduled task has stopped running.
    """
    rows = list(
        await db.scalars(
            select(AuditLog)
            .where(AuditLog.organization_id == organization_id)
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
    )

    prev_hash = GENESIS_HASH
    verified = 0
    unchained = 0
    broken_at_id: uuid.UUID | None = None
    broken_at_created_at: str | None = None

    for entry in rows:
        if entry.entry_hash is None:
            unchained += 1
            continue
        expected = _hash_entry(entry, prev_hash)
        if entry.prev_hash != prev_hash or entry.entry_hash != expected:
            broken_at_id = entry.id
            broken_at_created_at = entry.created_at.isoformat()
            break
        prev_hash = entry.entry_hash
        verified += 1

    return ChainVerification(
        total=len(rows),
        verified=verified,
        unchained=unchained,
        intact=broken_at_id is None,
        broken_at_id=broken_at_id,
        broken_at_created_at=broken_at_created_at,
    )
