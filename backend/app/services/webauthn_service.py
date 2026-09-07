"""WebAuthn / biometric login (Sprint 25, US-108).

Two independent flows share this module:

  * **Registration** — an already-logged-in user adds an authenticator from
    account settings.
  * **Authentication** — step 2 of login, alongside (not instead of) the
    existing SMS OTP: `auth_service.initiate_login` offers WebAuthn options
    only when the user has at least one registered credential, and the
    frontend lets the user pick either path. Whichever completes first wins;
    the other is simply never submitted.

Challenges are one-time, short-lived and held in Redis exactly like an OTP —
`otp_service` is the precedent this follows rather than reinventing session
storage for a second kind of short-lived secret.
"""

import base64
import uuid
from datetime import UTC, datetime

import webauthn
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import settings
from app.core.redis import redis_client
from app.models.user import User
from app.models.webauthn import WebauthnCredential
from app.services import audit_service

REGISTRATION_CHALLENGE_TTL_SECONDS = 300
AUTHENTICATION_CHALLENGE_TTL_SECONDS = 300


def _registration_challenge_key(user_id: uuid.UUID) -> str:
    return f"webauthn_reg_challenge:{user_id}"


def _login_challenge_key(login_challenge_token: str) -> str:
    return f"webauthn_login_challenge:{login_challenge_token}"


async def list_credentials(db: AsyncSession, user: User) -> list[WebauthnCredential]:
    rows = await db.scalars(
        select(WebauthnCredential)
        .where(WebauthnCredential.user_id == user.id)
        .order_by(WebauthnCredential.created_at.desc())
    )
    return list(rows)


async def registration_options(db: AsyncSession, user: User) -> str:
    existing = await list_credentials(db, user)
    options = webauthn.generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.full_name,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=webauthn.base64url_to_bytes(cred.credential_id))
            for cred in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    await redis_client.set(
        _registration_challenge_key(user.id),
        base64.b64encode(options.challenge).decode(),
        ex=REGISTRATION_CHALLENGE_TTL_SECONDS,
    )
    return webauthn.options_to_json(options)


async def verify_registration(
    db: AsyncSession, user: User, credential: dict, device_name: str, request: Request | None = None
) -> WebauthnCredential:
    stored_challenge = await redis_client.get(_registration_challenge_key(user.id))
    if not stored_challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Registration session expired — try again"
        )

    try:
        verification = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=base64.b64decode(stored_challenge),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
        )
    except WebAuthnException as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    finally:
        await redis_client.delete(_registration_challenge_key(user.id))

    record = WebauthnCredential(
        organization_id=user.organization_id,
        user_id=user.id,
        credential_id=webauthn.helpers.bytes_to_base64url(verification.credential_id),
        public_key=webauthn.helpers.bytes_to_base64url(verification.credential_public_key),
        sign_count=verification.sign_count,
        device_name=device_name or "Passkey",
    )
    db.add(record)
    await db.flush()

    audit_service.record(
        db,
        organization_id=user.organization_id,
        action="webauthn.credential_registered",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        summary=f"Registered passkey '{record.device_name}'",
        request=request,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def delete_credential(
    db: AsyncSession, user: User, credential_id: uuid.UUID, request: Request | None = None
) -> None:
    record = await db.get(WebauthnCredential, credential_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found")

    audit_service.record(
        db,
        organization_id=user.organization_id,
        action="webauthn.credential_removed",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        summary=f"Removed passkey '{record.device_name}'",
        request=request,
    )
    await db.delete(record)
    await db.commit()


async def authentication_options_for_login(
    db: AsyncSession, login_challenge_token: str, user: User
) -> str | None:
    """Options for step 2 of login, or `None` when this user has nothing
    registered — the caller falls back to SMS-only in that case."""
    credentials = await list_credentials(db, user)
    if not credentials:
        return None

    options = webauthn.generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=webauthn.base64url_to_bytes(cred.credential_id))
            for cred in credentials
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    await redis_client.set(
        _login_challenge_key(login_challenge_token),
        base64.b64encode(options.challenge).decode(),
        ex=AUTHENTICATION_CHALLENGE_TTL_SECONDS,
    )
    return webauthn.options_to_json(options)


async def verify_login_assertion(db: AsyncSession, login_challenge_token: str, credential: dict) -> None:
    """Verify a login assertion against whichever credential id it claims to be.

    Raises on any failure — there is no partial success. On success, updates
    the credential's sign counter and last-used timestamp in place.
    """
    stored_challenge = await redis_client.get(_login_challenge_key(login_challenge_token))
    if not stored_challenge:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login session expired — please log in again"
        )

    raw_id = credential.get("id") if isinstance(credential, dict) else None
    record = (
        await db.scalar(select(WebauthnCredential).where(WebauthnCredential.credential_id == raw_id))
        if raw_id
        else None
    )
    if record is None:
        await redis_client.delete(_login_challenge_key(login_challenge_token))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Passkey not recognised")

    try:
        verification = webauthn.verify_authentication_response(
            credential=credential,
            expected_challenge=base64.b64decode(stored_challenge),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            credential_public_key=webauthn.base64url_to_bytes(record.public_key),
            credential_current_sign_count=record.sign_count,
        )
    except WebAuthnException as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from None
    finally:
        await redis_client.delete(_login_challenge_key(login_challenge_token))

    record.sign_count = verification.new_sign_count
    record.last_used_at = datetime.now(UTC)
    await db.commit()
