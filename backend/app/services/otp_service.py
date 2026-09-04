import json
import secrets
import string
from typing import Any

from app.core.config import settings
from app.core.redis import redis_client


def _otp_key(purpose: str, subject: str) -> str:
    return f"otp:{purpose}:{subject}"


def _attempts_key(purpose: str, subject: str) -> str:
    return f"otp_attempts:{purpose}:{subject}"


def _challenge_key(token: str) -> str:
    return f"login_challenge:{token}"


async def generate_otp(purpose: str, subject: str) -> str:
    """Create and store a fresh OTP, replacing any previous one for this purpose+subject."""
    code = "".join(secrets.choice(string.digits) for _ in range(settings.OTP_LENGTH))
    await redis_client.set(_otp_key(purpose, subject), code, ex=settings.OTP_TTL_SECONDS)
    await redis_client.delete(_attempts_key(purpose, subject))
    return code


async def verify_otp(purpose: str, subject: str, code: str) -> bool:
    """Check `code` against the stored OTP, enforcing a per-OTP attempt cap.

    Correct code consumes it (single use). Exceeding OTP_MAX_ATTEMPTS invalidates
    the OTP outright, forcing a fresh one to be requested.
    """
    otp_key = _otp_key(purpose, subject)
    stored = await redis_client.get(otp_key)
    if stored is None:
        return False

    attempts_key = _attempts_key(purpose, subject)
    attempts = await redis_client.incr(attempts_key)
    if attempts == 1:
        await redis_client.expire(attempts_key, settings.OTP_TTL_SECONDS)
    if attempts > settings.OTP_MAX_ATTEMPTS:
        await redis_client.delete(otp_key)
        return False

    if not secrets.compare_digest(stored, code):
        return False

    await redis_client.delete(otp_key, attempts_key)
    return True


async def create_login_challenge(
    user_id: str, remember_device: bool = False, device_was_known: bool = False
) -> str:
    """Park the half-finished login in Redis.

    The device decisions taken at step 1 ride along with the challenge so step 2
    doesn't have to trust a client that could simply claim its device is known.
    """
    token = secrets.token_urlsafe(32)
    payload = json.dumps(
        {
            "user_id": user_id,
            "remember_device": remember_device,
            "device_was_known": device_was_known,
        }
    )
    await redis_client.set(_challenge_key(token), payload, ex=settings.OTP_TTL_SECONDS)
    return token


async def resolve_login_challenge(token: str) -> dict[str, Any] | None:
    raw = await redis_client.get(_challenge_key(token))
    if raw is None:
        return None
    return json.loads(raw)


async def consume_login_challenge(token: str) -> None:
    await redis_client.delete(_challenge_key(token))
