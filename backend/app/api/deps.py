"""Request-scoped dependencies: authentication, tenancy, RBAC and trial state.

Every protected endpoint runs the same gate in order (US-003):

    JWT valid -> user exists and is active -> token org matches the user's org
    -> role holds the required permission -> (for writes) the org can still write

`OrgContext` carries the resolved organization for the rest of the request, and
`assert_in_org` is the single place that decides a cross-tenant read is a 403 —
never a 404, which would leak whether the id exists at all.
"""

import uuid
from dataclasses import dataclass
from typing import TypeVar

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rls
from app.core.database import get_db
from app.core.permissions import (
    PROPERTY_SCOPED_ROLES,
    READ_ONLY_ROLES,
    Permission,
    role_has,
)
from app.core.security import decode_token
from app.models.organization import Organization
from app.models.property import CaretakerAssignment
from app.models.user import User, UserRole

T = TypeVar("T")

_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token") from None

    user = await db.get(User, user_id)
    if not user or not user.is_active or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # A token minted before the user moved organizations must not keep working.
    if payload.get("org_id") != str(user.organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Token does not match this user's organization"
        )

    return user


@dataclass(slots=True)
class OrgContext:
    """The resolved tenant for this request."""

    user: User
    organization: Organization

    @property
    def organization_id(self) -> uuid.UUID:
        return self.organization.id

    @property
    def role(self) -> UserRole:
        return self.user.role

    def can(self, permission: Permission) -> bool:
        return role_has(self.role, permission)


async def get_org_context(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> OrgContext:
    organization = await db.get(Organization, current_user.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization not found")
    if not organization.is_active:
        # Say why, when there is a reason on record (Sprint 26). A locked door
        # with no notice on it just becomes a support ticket.
        detail = "This account has been suspended."
        if organization.suspension_reason:
            detail = f"{detail} Reason: {organization.suspension_reason}"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    # Bind the transaction to this organisation so Postgres' own row-level
    # policies can enforce isolation underneath the application's WHERE clauses.
    # Every authenticated request passes through here, which is what makes this
    # the one place it has to happen.
    #
    # Whether it bites depends on the database role: a table owner bypasses RLS,
    # so this is inert unless `DATABASE_URL` points at the restricted app role
    # (see `docs/deployment-database-roles.md`). Setting it unconditionally is
    # deliberate — the alternative is a security control that only works if
    # someone remembers to switch it on at the same time as the role.
    await rls.enter_tenant_scope(db, organization.id)

    return OrgContext(user=current_user, organization=organization)


def require(*permissions: Permission):
    """Dependency factory: the caller's role must hold every listed permission."""

    async def dependency(context: OrgContext = Depends(get_org_context)) -> OrgContext:
        missing = [p for p in permissions if not context.can(p)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role ({context.role.value}) lacks: {', '.join(p.value for p in missing)}",
            )
        return context

    return dependency


def assert_can_write(context: OrgContext) -> None:
    """The non-permission half of `require_write`, callable mid-handler.

    A route whose required permission depends on a query parameter cannot
    declare it as a dependency, so it resolves the permission itself and calls
    this for the account-state checks that would otherwise be skipped.
    """
    if context.role in READ_ONLY_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has read-only access")
    if context.organization.is_read_only:
        detail = (
            "Your free trial has ended. Upgrade your plan to add or change data."
            if context.organization.is_trial_expired
            else "Your subscription is unpaid. Settle it to add or change data."
        )
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=detail)


def require_write(*permissions: Permission):
    """Like `require`, but also refuses writes from read-only roles and from
    organizations whose trial has lapsed (US-006).

    An expired trial keeps full read access — the landlord's data never becomes
    invisible, it just stops growing until they upgrade.
    """

    async def dependency(context: OrgContext = Depends(get_org_context)) -> OrgContext:
        missing = [p for p in permissions if not context.can(p)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role ({context.role.value}) lacks: {', '.join(p.value for p in missing)}",
            )
        assert_can_write(context)
        return context

    return dependency


async def require_platform_staff(current_user: User = Depends(get_current_user)) -> User:
    """Gate for `app.api.v1.endpoints.internal` — RentFlow's own team, not a
    tenant role. Deliberately independent of `OrgContext`: these routes read
    across every organisation, so there is no single tenant to resolve.
    """
    if not current_user.is_platform_staff:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="RentFlow staff access required")
    return current_user


def assert_in_org(entity: T | None, context: OrgContext, *, label: str = "resource") -> T:
    """Confirm a loaded row belongs to the caller's organization.

    Missing rows are 404; rows belonging to another tenant are 403 — the spec is
    explicit that a cross-tenant hit must not be disguised as 'not found'.

    Generic on purpose: returning `T` rather than `Any` lets callers use the
    result directly and keeps the Optional narrowed for the type checker.
    """
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label.capitalize()} not found")
    if getattr(entity, "organization_id", None) != context.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"You do not have access to this {label}"
        )
    return entity


async def accessible_property_ids(db: AsyncSession, context: OrgContext) -> list[uuid.UUID] | None:
    """Property ids this user may touch, or `None` for 'the whole organization'.

    Only caretakers are property-scoped; everyone else sees the full portfolio.
    A caretaker with no assignments legitimately sees nothing, which is an empty
    list rather than `None`.
    """
    if context.role not in PROPERTY_SCOPED_ROLES:
        return None
    rows = await db.scalars(
        select(CaretakerAssignment.property_id).where(
            CaretakerAssignment.user_id == context.user.id,
            CaretakerAssignment.organization_id == context.organization_id,
            CaretakerAssignment.is_active.is_(True),
        )
    )
    return list(rows)


async def assert_property_access(db: AsyncSession, context: OrgContext, property_id: uuid.UUID) -> None:
    allowed = await accessible_property_ids(db, context)
    if allowed is not None and property_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this property",
        )


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
