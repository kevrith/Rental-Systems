"""A distinct exception type for the public API (Sprint 19).

Every other endpoint in the app reports errors as FastAPI's default
`{"detail": ...}` — the frontend depends on that shape everywhere. The public
API instead promises external integrators a consistent envelope
(`{"status": "error", "data": null, "errors": [...]}`, US-085), so it needs its
own exception class the global handler in `app.main` can key off, without
touching how the rest of the app already reports errors.
"""

from fastapi import HTTPException


class ExternalApiError(HTTPException):
    pass
