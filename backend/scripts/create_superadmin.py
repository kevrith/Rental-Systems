"""Bootstrap RentFlow's own super admin — the first `is_platform_staff` account.

Every other account on the platform is created by someone who already has
access: a landlord self-registers, and their team arrives by invitation. The
platform-staff surface (`app.api.v1.endpoints.internal`) has no such door —
`require_platform_staff` only lets through a user whose `is_platform_staff`
flag is already set, and nothing in the API can set it. This script is that
door, and it is deliberately a shell command rather than an endpoint: a
"promote me to super admin" route is a permanent hole in the platform whether
or not anyone ever walks through it.

The account it creates is `SYSTEM_ADMIN` (every permission in
`ROLE_PERMISSIONS`) *and* `is_platform_staff` (the cross-organization internal
console). It lives in its own organization, which exists only to satisfy the
`users.organization_id` foreign key — RentFlow staff are not a customer, so
that organization is put on ENTERPRISE with no trial end date rather than
sitting on a trial that would eventually lapse into read-only.

Credentials come from the environment, never from arguments or this file:

    SUPERADMIN_EMAIL       required
    SUPERADMIN_PASSWORD    required, 8-72 characters (bcrypt's own limit)
    SUPERADMIN_PHONE       required — logins are OTP-verified over SMS, so an
                           unreachable number locks the account out
    SUPERADMIN_NAME        optional, defaults to "RentFlow Super Admin"
    SUPERADMIN_ORG_NAME    optional, defaults to "RentFlow Platform"
    SUPERADMIN_RESET_PASSWORD  optional, "true" to reset an existing account's
                           password to SUPERADMIN_PASSWORD

Usage (from `backend/`, with DATABASE_URL pointing at the target environment):

    python -m scripts.create_superadmin

or against the Docker stack, from the repository root:

    docker compose exec backend python -m scripts.create_superadmin

Safe to re-run. An existing account with SUPERADMIN_EMAIL is promoted in place
(flags set, role raised) rather than duplicated, so this doubles as the way to
grant a second staff member access. The password is only touched when
SUPERADMIN_RESET_PASSWORD is set, so a routine re-run never silently changes
the credential someone is already using.
"""

import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.organization import OperatingMode, Organization, SubscriptionPlan
from app.models.user import DEFAULT_INACTIVITY_TIMEOUT_MINUTES, User, UserRole
from app.services.notifications import normalize_phone

DEFAULT_NAME = "RentFlow Super Admin"
DEFAULT_ORG_NAME = "RentFlow Platform"


def _slugify(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in name)
    return "-".join(part for part in cleaned.split("-") if part) or "rentflow-platform"


def _require_env(key: str) -> str:
    value = (os.getenv(key) or "").strip()
    if not value:
        sys.exit(f"{key} is not set. See this script's docstring for the full list.")
    return value


async def _platform_organization(db: AsyncSession, name: str) -> Organization:
    """The organization RentFlow's own staff belong to, created on first run.

    Matched by slug rather than name so renaming it in the environment does not
    quietly create a second one.
    """
    slug = _slugify(name)
    organization = await db.scalar(select(Organization).where(Organization.slug == slug))
    if organization is not None:
        return organization

    organization = Organization(
        name=name,
        slug=slug,
        operating_mode=OperatingMode.OWNER,
        # Not a customer: no trial to expire, no plan limit to trip over.
        subscription_plan=SubscriptionPlan.ENTERPRISE,
        trial_ends_at=None,
        is_active=True,
    )
    db.add(organization)
    await db.flush()
    print(f"Created platform organization '{name}' ({slug}).")
    return organization


async def main() -> None:
    email = _require_env("SUPERADMIN_EMAIL").lower()
    password = _require_env("SUPERADMIN_PASSWORD")
    phone = normalize_phone(_require_env("SUPERADMIN_PHONE"))
    full_name = (os.getenv("SUPERADMIN_NAME") or "").strip() or DEFAULT_NAME
    org_name = (os.getenv("SUPERADMIN_ORG_NAME") or "").strip() or DEFAULT_ORG_NAME
    reset_password = (os.getenv("SUPERADMIN_RESET_PASSWORD") or "").strip().lower() == "true"

    # Mirrors `RegisterRequest.password` — bcrypt truncates silently past 72
    # bytes, which would make a longer password work here and fail elsewhere.
    if not 8 <= len(password.encode("utf-8")) <= 72:
        sys.exit("SUPERADMIN_PASSWORD must be between 8 and 72 bytes.")

    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == email))

        if existing is not None:
            changes: list[str] = []
            if not existing.is_platform_staff:
                existing.is_platform_staff = True
                changes.append("granted platform-staff access")
            if existing.role is not UserRole.SYSTEM_ADMIN:
                existing.role = UserRole.SYSTEM_ADMIN
                existing.inactivity_timeout_minutes = DEFAULT_INACTIVITY_TIMEOUT_MINUTES[
                    UserRole.SYSTEM_ADMIN
                ]
                changes.append("raised to system_admin")
            if not existing.is_active or existing.deleted_at is not None:
                existing.is_active = True
                existing.deleted_at = None
                existing.deletion_requested_at = None
                changes.append("reactivated")
            if reset_password:
                existing.password_hash = hash_password(password)
                changes.append("password reset")

            await db.commit()
            print(f"{email} already exists — {', '.join(changes) if changes else 'nothing to change'}.")
            if not reset_password:
                print("Password left as it was. Set SUPERADMIN_RESET_PASSWORD=true to replace it.")
            return

        # A second staff member joining an existing platform org would collide on
        # the unique phone number, which is a clearer failure here than a raw
        # IntegrityError out of the flush below.
        phone_taken = await db.scalar(select(User.email).where(User.phone_number == phone))
        if phone_taken:
            sys.exit(f"SUPERADMIN_PHONE is already registered to {phone_taken}.")

        organization = await _platform_organization(db, org_name)

        user = User(
            organization_id=organization.id,
            full_name=full_name,
            email=email,
            phone_number=phone,
            password_hash=hash_password(password),
            role=UserRole.SYSTEM_ADMIN,
            is_platform_staff=True,
            is_active=True,
            # Verified on creation: the two verification flows send a link and an
            # OTP to whoever runs this, and there is no one to receive them
            # during a deploy. Login still requires an SMS OTP on an untrusted
            # device, so this does not weaken the sign-in itself.
            is_email_verified=True,
            is_phone_verified=True,
            inactivity_timeout_minutes=DEFAULT_INACTIVITY_TIMEOUT_MINUTES[UserRole.SYSTEM_ADMIN],
        )
        db.add(user)
        await db.commit()

    print(f"Created super admin {email} ({full_name}) in '{org_name}'.")
    print("Password: set via SUPERADMIN_PASSWORD in the environment — not shown here.")
    print("Sign in at /login; the RentFlow staff section appears in the sidebar.")


if __name__ == "__main__":
    asyncio.run(main())
