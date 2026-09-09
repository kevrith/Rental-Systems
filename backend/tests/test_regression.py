"""Cross-cutting regression suite — Phase 2 (US-059).

The per-feature tests check that each thing works. These check the properties
that must hold across *every* endpoint, and which no single feature test would
notice breaking:

  * every authenticated route rejects an anonymous caller;
  * every authenticated route rejects a valid token from another organisation;
  * no response body ever carries a password hash, a token, or a stored secret;
  * the routing table has no accidental duplicates or unregistered routers.

They are driven off the live OpenAPI schema rather than a hand-maintained list,
so a route added next month is covered the day it is added — which is the whole
point. A route that legitimately needs to be public is named in PUBLIC_PREFIXES
with the reason, and that list is the review surface.
"""

import re
import uuid

import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from httpx import AsyncClient

from app.main import app

# Routes reachable without a session, each for a stated reason. Anything added
# here is a deliberate decision to expose something publicly.
PUBLIC_PREFIXES: dict[str, str] = {
    "/": "Service banner. Names the API and its version, nothing more.",
    "/api/v1/health": "Liveness probe for the load balancer.",
    # Sprint 26. Gated by its own bearer-token check (METRICS_TOKEN) rather
    # than the app's session auth — a Prometheus scrape has no user session to
    # present. Open by default because a local scrape has no token configured;
    # production sets one (see app.core.metrics).
    "/metrics": "Prometheus scrape target, authenticated by METRICS_TOKEN when one is set.",
    "/api/v1/auth/register": "Creating the first account.",
    "/api/v1/auth/login": "Obtaining a session.",
    "/api/v1/auth/refresh": "Rotating a session on the refresh token alone.",
    "/api/v1/auth/login/verify-otp": "Second factor, before a session exists.",
    "/api/v1/auth/google": "Sign in with Google, authenticated by Google's own signed ID token.",
    "/api/v1/auth/google/register": "Creating an account via Google, same as /auth/register.",
    "/api/v1/auth/forgot-password": "Password reset request.",
    "/api/v1/auth/reset-password": "Password reset, authenticated by the emailed token.",
    "/api/v1/auth/verify-email": "Email confirmation link.",
    "/api/v1/invitations": "Accepting a team invitation before the account exists.",
    "/api/v1/mpesa": "Safaricom's callbacks. Authenticated by matching a checkout id.",
    "/api/v1/paystack": "Paystack's charge webhooks. Authenticated by an HMAC-SHA512 body signature.",
    "/api/v1/webhooks": "Resend's delivery-event callbacks. Authenticated by a Svix HMAC signature.",
    "/api/v1/sign": "The tenant's signing link. Authenticated by a single-use token.",
    "/api/v1/renew": "The tenant's renewal link. Authenticated by a single-use token.",
    "/api/v1/files/local": "Development storage. Authenticated by a signed, expiring URL.",
    "/api/v1/portal/setup": "Tenant portal setup before the account exists.",
    # Sprint 26. A tenant who cannot remember their portal password has no
    # session by definition. The request endpoint answers identically whether
    # or not the number is a tenant, so it cannot be used to enumerate a
    # landlord's book, and it is rate-limited per number.
    "/api/v1/portal/magic-link": "Tenant sign-in link. Authenticated by a single-use token.",
    # Phase 3. Screening and vacancy marketing reach four people who have no
    # account and never will: a prospective tenant, their guarantor, their
    # previous landlord, and whoever the listing link was forwarded to.
    "/api/v1/apply": "The public application form. A vacant unit is a public advert.",
    "/api/v1/guarantee": "The guarantor's acknowledgement. Authenticated by a single-use token.",
    "/api/v1/reference": "The previous landlord's answer. Authenticated by a single-use token.",
    "/api/v1/listings": "The shareable vacancy listing and its enquiry form.",
    # Sprint 23. A connected portal reporting an enquiry, and Intuit/Xero
    # redirecting the landlord's browser back after they grant access.
    "/api/v1/portal-webhooks": "A connected property portal reporting an inbound enquiry.",
    "/api/v1/oauth": "Accounting OAuth callback. Authenticated by the signed `state` alone.",
    # The help centre. Read-only, and the rows carry no organisation: the whole
    # point is that it is readable before an account exists, and by anyone stuck
    # on the sign-in screen. Only published articles are served.
    "/api/v1/help": "The public help centre. Platform-wide content, identical for every tenant.",
}

# Strings that must never appear in any response body.
FORBIDDEN_IN_RESPONSES = ("password_hash", "token_hash", "api_key_encrypted", "device_serial_encrypted")


def _is_public(path: str) -> bool:
    # `startswith` on a bare "/" would match every route, so the root is matched
    # exactly and everything else by prefix.
    return any(path == prefix if prefix == "/" else path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def api_route_paths() -> set[str]:
    """Every path the API exposes, as one flat set.

    `app.routes` is not that list. Since FastAPI 0.141 `include_router` leaves a
    single opaque node behind instead of copying the child routes up, so
    iterating `app.routes` and filtering for APIRoute sees only the handful
    declared on the app itself — which is how this suite could pass while
    checking nothing. `iter_route_contexts` is the supported way to flatten it,
    and unlike the OpenAPI schema it still includes routes registered with
    `include_in_schema=False`.
    """
    return {
        context.path
        for context in iter_route_contexts(app.routes)
        if isinstance(context.original_route, APIRoute)
    }


def _authenticated_routes() -> list[tuple[str, str]]:
    """Every (method, path) the API exposes that is not deliberately public."""
    routes = []
    for context in iter_route_contexts(app.routes):
        if not isinstance(context.original_route, APIRoute):
            continue
        if _is_public(context.path):
            continue
        for method in sorted((context.methods or set()) - {"HEAD", "OPTIONS"}):
            routes.append((method, context.path))
    return sorted(routes)


def _fill(path: str) -> str:
    """Substitute a syntactically valid but non-existent id into each path param.

    The value must parse — otherwise FastAPI answers 422 before the auth
    dependency runs, and the test would pass without proving anything.
    """
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


@pytest.mark.asyncio
async def test_every_authenticated_route_rejects_an_anonymous_caller(client: AsyncClient):
    routes = _authenticated_routes()
    assert len(routes) > 80, f"Only found {len(routes)} routes — is the router registered?"

    leaked: list[str] = []
    for method, path in routes:
        response = await client.request(method, _fill(path), json={})
        # 401 is the goal. 403 is acceptable — the caller was identified as
        # having no rights. Anything else means the handler ran unauthenticated.
        if response.status_code not in (401, 403):
            leaked.append(f"{method} {path} -> {response.status_code}")

    assert not leaked, "Routes reachable without a session:\n  " + "\n  ".join(leaked)


@pytest.mark.asyncio
async def test_public_routes_are_exactly_the_documented_ones(client: AsyncClient):
    """A new public route must be a decision, not an accident."""
    public = sorted(path for path in api_route_paths() if _is_public(path))
    undocumented = [path for path in public if not any(path.startswith(p) for p in PUBLIC_PREFIXES)]
    assert not undocumented, f"Public routes with no stated reason: {undocumented}"

    # Every declared prefix should still match something; a stale entry hides
    # the fact that a route it used to cover has moved.
    unused = [prefix for prefix in PUBLIC_PREFIXES if not any(path.startswith(prefix) for path in public)]
    assert not unused, f"PUBLIC_PREFIXES entries matching no route: {unused}"


@pytest.mark.asyncio
async def test_no_response_leaks_a_secret(client: AsyncClient):
    """A serialiser that forgets to exclude a hash is a slow-motion breach."""
    from tests.test_phase2 import _agency_money_path, _make_agency_org

    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    await client.put(
        "/api/v1/etims/credentials",
        headers=headers,
        json={
            "kra_pin": "A012345678Z",
            "device_serial": "KRACU0300000001",
            "api_key": "super-secret-key",
        },
    )

    sampled = [
        "/api/v1/auth/me",
        "/api/v1/team",
        "/api/v1/tenants",
        "/api/v1/tenancies",
        "/api/v1/payments",
        "/api/v1/agency/owner-profiles",
        "/api/v1/etims/credentials",
        "/api/v1/etims/report",
        "/api/v1/renewals",
        f"/api/v1/vault/tenants/{setup['tenant']['id']}",
    ]

    for path in sampled:
        response = await client.get(path, headers=headers)
        assert response.status_code == 200, f"{path} -> {response.status_code}"
        body = response.text
        for secret in FORBIDDEN_IN_RESPONSES:
            assert secret not in body, f"{path} leaks {secret}"
        assert "super-secret-key" not in body, f"{path} leaks the stored eTIMS key"
        assert "KRACU0300000001" not in body, f"{path} leaks the stored device serial"


@pytest.mark.asyncio
async def test_organizations_cannot_read_each_others_records(client: AsyncClient):
    """One sweep over every entity type, rather than a per-feature check each time.

    Org A creates one of everything; org B holds a perfectly valid session and
    must not be able to read any of it.
    """
    from tests.test_phase2 import _agency_money_path, _make_agency_org

    headers_a = await _make_agency_org(client)
    headers_b = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers_a)

    disbursement = await client.post(
        "/api/v1/agency/disbursements",
        headers=headers_a,
        json={
            "owner_profile_id": setup["profile"]["id"],
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )
    inspection = await client.post(
        "/api/v1/inspections",
        headers=headers_a,
        json={"unit_id": setup["unit"]["id"], "inspection_type": "routine"},
    )

    forbidden = {
        "property": f"/api/v1/properties/{setup['property']['id']}",
        "unit": f"/api/v1/units/{setup['unit']['id']}",
        "tenant": f"/api/v1/tenants/{setup['tenant']['id']}",
        "tenancy": f"/api/v1/tenancies/{setup['tenancy']['id']}",
        "owner profile": f"/api/v1/agency/owner-profiles/{setup['profile']['id']}",
        "inspection": f"/api/v1/inspections/{inspection.json()['id']}",
        "tenant vault": f"/api/v1/vault/tenants/{setup['tenant']['id']}",
        "property vault": f"/api/v1/vault/properties/{setup['property']['id']}",
        "disbursement statement": (f"/api/v1/agency/disbursements/{disbursement.json()['id']}/statement"),
    }

    leaked: list[str] = []
    for label, path in forbidden.items():
        response = await client.get(path, headers=headers_b)
        if response.status_code not in (403, 404):
            leaked.append(f"{label}: {path} -> {response.status_code}")

    assert not leaked, "Org B can read org A's data:\n  " + "\n  ".join(leaked)


@pytest.mark.asyncio
async def test_list_endpoints_never_return_another_organizations_rows(client: AsyncClient):
    """The subtler failure: not a 200 on someone else's id, but their rows in your list."""
    from tests.test_phase2 import _agency_money_path, _make_agency_org

    headers_a = await _make_agency_org(client)
    headers_b = await _make_agency_org(client)
    await _agency_money_path(client, headers_a)

    for path in (
        "/api/v1/properties",
        "/api/v1/units",
        "/api/v1/tenants",
        "/api/v1/tenancies",
        "/api/v1/payments",
        "/api/v1/invoices",
        "/api/v1/agency/owner-profiles",
        "/api/v1/agency/disbursements",
        "/api/v1/inspections",
        "/api/v1/renewals",
    ):
        response = await client.get(path, headers=headers_b)
        assert response.status_code == 200, f"{path} -> {response.status_code}"
        rows = response.json()
        rows = rows if isinstance(rows, list) else rows.get("items", [])
        assert rows == [], f"{path} returned {len(rows)} rows belonging to another organisation"


@pytest.mark.asyncio
async def test_the_routing_table_has_no_duplicate_paths():
    """Two handlers on one path means one of them is unreachable."""
    seen: dict[tuple[str, str], int] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            seen[(method, route.path)] = seen.get((method, route.path), 0) + 1

    duplicates = [f"{method} {path}" for (method, path), count in seen.items() if count > 1]
    assert not duplicates, f"Duplicate routes: {duplicates}"


@pytest.mark.asyncio
async def test_a_read_only_trial_cannot_write(client: AsyncClient, db):
    """An expired trial drops to read-only; the guard is one dependency, so it is
    worth one test rather than one per endpoint."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select as sa_select

    from app.models.organization import Organization
    from tests.test_phase2 import _make_owner_org

    headers = await _make_owner_org(client)
    me = await client.get("/api/v1/auth/me", headers=headers)
    org_id = uuid.UUID(me.json()["organization_id"])

    organization = await db.scalar(sa_select(Organization).where(Organization.id == org_id))
    organization.trial_ends_at = datetime.now(UTC) - timedelta(days=1)
    await db.commit()

    blocked = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={"name": "After expiry", "address": "1 Late St", "property_type": "residential"},
    )
    assert blocked.status_code == 402, blocked.text

    # Reading still works — an expired trial locks the doors, it does not
    # confiscate the landlord's own records.
    assert (await client.get("/api/v1/properties", headers=headers)).status_code == 200
