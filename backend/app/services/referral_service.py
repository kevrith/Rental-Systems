"""Referral tracking and credit (US-092).

RentFlow has no billing engine yet for its own subscription fee — nothing
currently changes `Organization.subscription_plan` except registration, which
always sets `TRIAL`. So there is no live "upgraded to paid" event to hook a
credit onto. `handle_plan_upgraded` exists for the one place that *can* change
a plan today: the platform-staff-only endpoint in
`app.api.v1.endpoints.internal`. The credit itself is a ledger
(`Organization.credit_months`) rather than an applied invoice discount, ready
for whenever a real billing engine exists to consume it.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.core.config import settings
from app.models.customer_success import Referral, ReferralCode, ReferralStatus
from app.models.organization import Organization, SubscriptionPlan
from app.schemas.customer_success import ReferralCreate


def _generate_code() -> str:
    return uuid.uuid4().hex[:10].upper()


async def get_or_create_code(db: AsyncSession, context: OrgContext) -> ReferralCode:
    row = await db.scalar(select(ReferralCode).where(ReferralCode.organization_id == context.organization_id))
    if row is not None:
        return row
    row = ReferralCode(organization_id=context.organization_id, code=_generate_code())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def summary(db: AsyncSession, context: OrgContext) -> tuple[ReferralCode, list[Referral]]:
    code = await get_or_create_code(db, context)
    referrals = list(
        await db.scalars(
            select(Referral)
            .where(Referral.organization_id == context.organization_id)
            .order_by(Referral.created_at.desc())
        )
    )
    return code, referrals


async def record_referral(db: AsyncSession, context: OrgContext, payload: ReferralCreate) -> Referral:
    code = await get_or_create_code(db, context)
    row = Referral(
        organization_id=context.organization_id,
        referral_code_id=code.id,
        referred_email=payload.referred_email.lower(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def link_signup(db: AsyncSession, *, email: str, organization_id: uuid.UUID) -> None:
    """Called from registration: a pending referral for this email becomes
    'signed up' the moment the referred prospect actually creates an account."""
    referral = await db.scalar(
        select(Referral).where(
            Referral.referred_email == email.lower(), Referral.status == ReferralStatus.PENDING
        )
    )
    if referral is None:
        return
    referral.referred_organization_id = organization_id
    referral.status = ReferralStatus.SIGNED_UP


async def handle_plan_upgraded(db: AsyncSession, organization: Organization) -> None:
    """Grant the referrer one month of credit the first time a referred
    organisation leaves the trial plan."""
    if organization.subscription_plan == SubscriptionPlan.TRIAL:
        return
    referral = await db.scalar(
        select(Referral).where(
            Referral.referred_organization_id == organization.id,
            Referral.status == ReferralStatus.SIGNED_UP,
        )
    )
    if referral is None:
        return
    referral.status = ReferralStatus.CONVERTED
    referral.credit_granted_at = datetime.now(UTC)
    referrer = await db.get(Organization, referral.organization_id)
    if referrer is not None:
        referrer.credit_months += 1
    await db.commit()


REFERRAL_LINK_TEMPLATE = f"{settings.FRONTEND_URL}/register?ref={{code}}"
