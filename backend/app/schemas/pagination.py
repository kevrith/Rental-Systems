"""Keyset ('cursor') pagination for the public API (US-085).

Offset pagination shifts under a caller mid-scroll whenever a row is inserted
ahead of their position — exactly what happens to an integrator polling
`/payments` while rent is being collected. Keyset pagination on
`(created_at, id)` doesn't have that failure mode: each page is defined by
"rows after this exact point," which stays correct no matter what else is
inserted.
"""

import base64
import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, status
from pydantic import BaseModel


@dataclass(slots=True)
class CursorPosition:
    created_at: datetime
    id: uuid.UUID


def encode_cursor(created_at: datetime, id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> CursorPosition:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ts_raw, id_raw = raw.split("|", 1)
        return CursorPosition(created_at=datetime.fromisoformat(ts_raw), id=uuid.UUID(id_raw))
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pagination cursor"
        ) from exc


class Page(BaseModel):
    data: list[dict]
    next_cursor: str | None
    has_more: bool
