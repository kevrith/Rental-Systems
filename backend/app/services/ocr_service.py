"""Reading a meter dial off the photo the caretaker just took (Module 5).

A caretaker walking a block of forty units types forty numbers into a phone,
in a stairwell, often in poor light. Every one of those is a chance to
transpose two digits, and a wrong meter reading becomes a wrong bill, which
becomes an argument with a tenant that costs far more to settle than the
reading was worth.

The photo is already mandatory (`operations_service.record_meter_reading`), so
the evidence is there. This reads the digits off it and offers them as a
suggestion.

Three things this deliberately does *not* do:

  * It never writes the reading. `current_reading` remains what a person
    submitted; `ocr_reading` and `ocr_confidence` are stored next to it as the
    record of what was proposed. A meter photographed at an angle, with a
    cracked cover, or an analogue dial mid-tick will be misread, and a bill
    that nobody looked at is exactly the failure this is supposed to prevent.
  * It never blocks. An unconfigured key, a provider outage or an unreadable
    photo all return "no suggestion" and the caretaker types the number as
    they always have — the same degrade-gracefully treatment every other
    optional integration in this codebase gets.
  * It does not run automatically on upload. OCR is a billed model call, and
    firing one per photo whether or not anyone wanted a suggestion is the kind
    of cost that only shows up on an invoice a month later. The client asks
    for it.
"""

import base64
import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

import anthropic
from anthropic.types import ImageBlockParam, MessageParam, TextBlockParam
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.core.config import settings
from app.core.redis import redis_client
from app.models.file import StoredFile, UploadStatus
from app.models.operations import MeterType
from app.services import storage_service

logger = logging.getLogger("rentflow.ocr")

# The photo goes to the model inline, so it has to be something the API
# accepts and something a phone camera actually produces. Keyed rather than a
# plain tuple so the media type handed to the SDK is the narrow literal its
# signature wants, not whatever string the upload happened to declare.
MEDIA_TYPES: dict[str, Literal["image/jpeg", "image/png", "image/webp"]] = {
    "image/jpeg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
}
# Above the provider's own inline-image ceiling the request is rejected
# outright, so refuse it here with a message that says what to do instead.
MAX_IMAGE_BYTES = 5 * 1024 * 1024

READING_SCHEMA = {
    "type": "object",
    "properties": {
        "reading": {
            "type": ["string", "null"],
            "description": (
                "The digits shown on the meter's register, as they read left to right, "
                "including any decimal part shown in a differently-coloured section. "
                "Null if no meter register is legible in the image."
            ),
        },
        "confidence": {
            "type": "number",
            "description": (
                "0-100. How certain you are that every digit is correct. Be strict: "
                "a partially obscured or motion-blurred digit should pull this well down."
            ),
        },
        "meter_kind": {
            "type": ["string", "null"],
            "enum": ["water", "electricity", None],
            "description": "Which utility this meter appears to measure, if it can be told.",
        },
        "notes": {
            "type": ["string", "null"],
            "description": (
                "One short sentence for the caretaker if something is wrong with the photo "
                "— glare, angle, a cracked cover, the dial cut off. Null if the photo is fine."
            ),
        },
    },
    "required": ["reading", "confidence", "meter_kind", "notes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You read utility meters from photographs for a Kenyan property management system. "
    "Kenyan water meters are usually mechanical with a row of black digits for whole units "
    "and red digits or dials for fractions; electricity meters are usually digital LCD "
    "prepaid or postpaid units. Report only the digits of the cumulative register — never "
    "the serial number, the tariff code, the token number, or anything on a sticker. If "
    "the register is not clearly legible, say so by returning null rather than guessing: a "
    "wrong reading becomes a wrong bill, which is far worse than no suggestion at all."
)


class OcrUnavailable(Exception):
    """Raised when no suggestion can be produced. Never fatal to the caller."""


def _client() -> anthropic.AsyncAnthropic:
    if not settings.ANTHROPIC_API_KEY:
        raise OcrUnavailable("Meter OCR is not configured — set ANTHROPIC_API_KEY.")
    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def _check_rate_limit(organization_id: uuid.UUID) -> None:
    """Each read is a billed model call with nothing else in front of it."""
    hour = datetime.now(UTC).strftime("%Y-%m-%dT%H")
    key = f"ocr:meter:rate:{organization_id}:{hour}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, 3600)
    if count > settings.METER_OCR_MAX_PER_HOUR:
        limit = settings.METER_OCR_MAX_PER_HOUR
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Meter photo reading limit reached: {limit} per hour. Type the reading in instead.",
        )


def _parse_reading(raw: object) -> Decimal | None:
    if raw in (None, ""):
        return None
    text = str(raw).strip().replace(",", "").replace(" ", "")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    # A negative or absurd register is a misread, not a meter.
    if value < 0 or value >= Decimal("100000000"):
        return None
    return value.quantize(Decimal("0.01"))


async def read_meter_photo(
    db: AsyncSession,
    context: OrgContext,
    *,
    photo_file_id: uuid.UUID,
    meter_type: MeterType | None = None,
) -> dict:
    """Suggest a reading from an already-uploaded meter photo.

    Returns the same shape whether or not a number came back, so the capture
    form has one code path: `reading` is None when there is nothing to suggest
    and `message` says why in words a caretaker can act on.
    """
    photo = await db.get(StoredFile, photo_file_id)
    if photo is None or photo.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meter photo not found")
    if photo.status != UploadStatus.UPLOADED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Finish uploading the photo before reading it",
        )
    media_type = MEDIA_TYPES.get(photo.content_type)
    if media_type is None:
        return _no_suggestion("That file is not a photo the reader can open. Type the reading in.")
    if photo.size_bytes > MAX_IMAGE_BYTES:
        return _no_suggestion("That photo is too large to read. Retake it at a lower resolution.")

    await _check_rate_limit(context.organization_id)

    try:
        client = _client()
    except OcrUnavailable as exc:
        logger.info("Meter OCR skipped: %s", exc)
        return _no_suggestion("Automatic meter reading is not switched on for this deployment.")

    image_bytes = await storage_service.get_file_bytes(photo.storage_key)
    hint = (
        f"This is expected to be a {meter_type.value} meter."
        if meter_type is not None
        else "The utility is not known in advance."
    )

    image_block: ImageBlockParam = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(image_bytes).decode("ascii"),
        },
    }
    prompt_block: TextBlockParam = {"type": "text", "text": f"Read this meter. {hint}"}
    messages: list[MessageParam] = [{"role": "user", "content": [image_block, prompt_block]}]

    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            # One image and a handful of fields out. The ceiling exists to cap
            # a runaway, not because a real answer approaches it.
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=messages,
            output_config={"format": {"type": "json_schema", "schema": READING_SCHEMA}},
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError, anthropic.RateLimitError) as exc:
        logger.warning("Meter OCR call failed for photo %s: %s", photo_file_id, exc)
        return _no_suggestion("The meter reader is unavailable right now. Type the reading in.")

    if response.stop_reason in ("refusal", "max_tokens"):
        return _no_suggestion("The meter could not be read from that photo. Type the reading in.")

    try:
        text = next(block.text for block in response.content if block.type == "text")
        data = json.loads(text)
    except (StopIteration, json.JSONDecodeError):
        logger.warning("Meter OCR returned an unreadable response for photo %s", photo_file_id)
        return _no_suggestion("The meter could not be read from that photo. Type the reading in.")

    reading = _parse_reading(data.get("reading"))
    if reading is None:
        return _no_suggestion(data.get("notes") or "No meter dial was legible in that photo.")

    try:
        confidence = Decimal(str(data.get("confidence", 0))).quantize(Decimal("0.01"))
    except InvalidOperation:
        confidence = Decimal("0.00")
    confidence = max(Decimal("0.00"), min(confidence, Decimal("100.00")))

    return {
        "reading": reading,
        "confidence": confidence,
        "meter_kind": data.get("meter_kind"),
        "message": data.get("notes"),
        # Below this the number is shown but the field starts empty, so the
        # caretaker has to type it rather than tap past a guess.
        "high_confidence": confidence >= Decimal(str(settings.METER_OCR_CONFIDENCE_THRESHOLD)),
    }


def _no_suggestion(message: str) -> dict:
    return {
        "reading": None,
        "confidence": None,
        "meter_kind": None,
        "message": message,
        "high_confidence": False,
    }
