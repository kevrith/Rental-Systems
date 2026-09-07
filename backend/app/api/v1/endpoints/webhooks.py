"""Inbound webhooks from third parties RentFlow doesn't control the traffic of.

Resend's delivery-event callback is the only one today — see
`app.services.email_service` for the signature scheme and what an event does.
"""

import json
import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import email_service

logger = logging.getLogger("rentflow.webhooks")

router = APIRouter()


@router.post("/resend")
async def resend_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Unauthenticated by necessity — Resend calls it. Authenticated instead by
    a Svix HMAC signature over the raw body (`email_service.verify_webhook_signature`);
    an unsigned or wrongly-signed request is rejected before the body is even parsed."""
    body = await request.body()

    if not email_service.verify_webhook_signature(body, dict(request.headers)):
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Invalid signature"})

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "Invalid payload"})

    await email_service.handle_event(db, event)
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ok"})
