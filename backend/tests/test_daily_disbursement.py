"""Daily auto-disbursement — settling an owner the morning after rent clears.

The monthly run (`process_scheduled_disbursements`) prepares a payout and waits
for an agency admin to approve it. This path approves and pays in one pass, so
what matters most is that it only ever touches owners who opted in, and that no
shilling is either paid twice or dropped when an amount is too small to send.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.agency import Disbursement, DisbursementStatus, OwnerProfile
from app.services import agency_service
from tests.test_phase2 import _agency_money_path, _make_agency_org


async def _profile(db, profile_id: str) -> OwnerProfile:
    return await db.get(OwnerProfile, uuid.UUID(profile_id))


async def _enable_daily(
    client: AsyncClient, headers: dict, profile_id: str, *, minimum: str = "1000.00"
) -> dict:
    resp = await client.patch(
        f"/api/v1/agency/owner-profiles/{profile_id}",
        headers=headers,
        json={"auto_disburse_daily": True, "auto_disburse_minimum": minimum},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ----------------------------------------------------------------- the setting


@pytest.mark.asyncio
async def test_daily_disbursement_is_off_until_it_is_switched_on(client: AsyncClient, db) -> None:
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)

    profile = await _profile(db, setup["profile"]["id"])
    assert profile.auto_disburse_daily is False

    updated = await _enable_daily(client, headers, setup["profile"]["id"])
    assert updated["auto_disburse_daily"] is True


# ----------------------------------------------------------------- the period


@pytest.mark.asyncio
async def test_first_run_reaches_back_to_the_owners_earliest_rent(client: AsyncClient, db) -> None:
    """Switching the setting on mid-life settles the backlog, not just one day."""
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    profile = await _profile(db, setup["profile"]["id"])

    today = date.today()
    start, end = await agency_service.next_auto_period(db, profile, today)

    assert end == today - timedelta(days=1)
    assert start <= today  # the payment made by the helper is dated today


@pytest.mark.asyncio
async def test_the_next_period_starts_the_day_after_the_last_one_ended(client: AsyncClient, db) -> None:
    """No day is ever settled twice, and no day is skipped."""
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    profile = await _profile(db, setup["profile"]["id"])

    today = date.today()
    settled_to = today - timedelta(days=3)
    db.add(
        Disbursement(
            organization_id=profile.organization_id,
            reference_code="DSB-PRIOR-1",
            owner_profile_id=profile.id,
            period_start=settled_to - timedelta(days=5),
            period_end=settled_to,
            gross_rent=Decimal("10000.00"),
            management_fee=Decimal("1000.00"),
            maintenance_costs=Decimal("0.00"),
            other_deductions=Decimal("0.00"),
            net_amount=Decimal("9000.00"),
            status=DisbursementStatus.COMPLETED,
        )
    )
    await db.commit()

    start, end = await agency_service.next_auto_period(db, profile, today)
    assert start == settled_to + timedelta(days=1)
    assert end == today - timedelta(days=1)


# ----------------------------------------------------------------- settling


@pytest.mark.asyncio
async def test_an_amount_under_the_minimum_is_not_sent(client: AsyncClient, db) -> None:
    """Below the floor nothing moves — a B2C fee on a trivial payout costs the
    owner more than waiting does."""
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers, rent="30000.00")
    await _enable_daily(client, headers, setup["profile"]["id"], minimum="999999.00")
    profile = await _profile(db, setup["profile"]["id"])

    result = await agency_service.auto_settle_owner(db, profile, date.today() + timedelta(days=1))
    assert result is None

    rows = list(await db.scalars(select(Disbursement).where(Disbursement.owner_profile_id == profile.id)))
    assert rows == []


@pytest.mark.asyncio
async def test_money_held_back_by_the_minimum_is_picked_up_by_a_later_run(client: AsyncClient, db) -> None:
    """The window rolls forward rather than closing, so a small day is not lost —
    it is settled by the first run that clears the floor."""
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers, rent="30000.00")
    profile = await _profile(db, setup["profile"]["id"])
    tomorrow = date.today() + timedelta(days=1)

    profile.auto_disburse_daily = True
    profile.auto_disburse_minimum = Decimal("999999.00")
    await db.commit()
    assert await agency_service.auto_settle_owner(db, profile, tomorrow) is None

    profile.auto_disburse_minimum = Decimal("1000.00")
    await db.commit()
    disbursement = await agency_service.auto_settle_owner(db, profile, tomorrow)

    assert disbursement is not None
    # The full 30,000 less the 10% fee — nothing was dropped by the first pass.
    assert Decimal(disbursement.gross_rent) == Decimal("30000.00")
    assert Decimal(disbursement.net_amount) == Decimal("27000.00")


@pytest.mark.asyncio
async def test_settling_approves_and_pays_without_a_human(client: AsyncClient, db) -> None:
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers, rent="30000.00")
    await _enable_daily(client, headers, setup["profile"]["id"])
    profile = await _profile(db, setup["profile"]["id"])

    disbursement = await agency_service.auto_settle_owner(db, profile, date.today() + timedelta(days=1))

    assert disbursement is not None
    assert disbursement.approved_at is not None
    assert disbursement.approved_by_id is None  # nobody approved it; the setting did
    assert disbursement.payment_method == "mpesa"
    # With no Daraja credentials the B2C stub settles in the same call.
    assert disbursement.status == DisbursementStatus.COMPLETED


@pytest.mark.asyncio
async def test_a_second_run_the_same_day_sends_nothing_further(client: AsyncClient, db) -> None:
    """The guard against paying an owner twice for the same rent."""
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers, rent="30000.00")
    await _enable_daily(client, headers, setup["profile"]["id"])
    profile = await _profile(db, setup["profile"]["id"])
    tomorrow = date.today() + timedelta(days=1)

    first = await agency_service.auto_settle_owner(db, profile, tomorrow)
    second = await agency_service.auto_settle_owner(db, profile, tomorrow)

    assert first is not None
    assert second is None

    rows = list(await db.scalars(select(Disbursement).where(Disbursement.owner_profile_id == profile.id)))
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_an_owner_with_no_mpesa_number_is_skipped_rather_than_half_settled(
    client: AsyncClient, db
) -> None:
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers, rent="30000.00")
    await _enable_daily(client, headers, setup["profile"]["id"])
    profile = await _profile(db, setup["profile"]["id"])

    profile.mpesa_phone = None
    profile.phone_number = ""
    await db.commit()

    assert await agency_service.auto_settle_owner(db, profile, date.today() + timedelta(days=1)) is None
    rows = list(await db.scalars(select(Disbursement).where(Disbursement.owner_profile_id == profile.id)))
    assert rows == []


# ----------------------------------------------------------------- scheduling


def test_the_daily_task_is_on_the_beat_schedule() -> None:
    """A task nobody scheduled never runs, and owners silently stop being paid."""
    from app.tasks.celery_app import celery_app

    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert "rentflow.process_daily_disbursements" in scheduled
