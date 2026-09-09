"""The price list RentFlow charges its own customers.

Mirrors `frontend/src/features/marketing/plans.ts`, which is what the pricing
page advertises. The two must agree — an organisation charged something other
than the price it was shown is a support ticket at best — so the ids here are
the `SubscriptionPlan` enum values and the amounts are the same KES figures.

ENTERPRISE is deliberately absent: it is quoted per deal, not self-served, so
there is no amount to charge automatically.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.models.organization import SubscriptionPlan


@dataclass(frozen=True, slots=True)
class PlanPrice:
    monthly: Decimal
    annual: Decimal


# Annual is ten months' money for twelve months' service — the "two months free"
# the pricing page promises.
PLAN_PRICES: dict[SubscriptionPlan, PlanPrice] = {
    SubscriptionPlan.STARTER: PlanPrice(monthly=Decimal("2000.00"), annual=Decimal("20000.00")),
    SubscriptionPlan.PROFESSIONAL: PlanPrice(monthly=Decimal("8000.00"), annual=Decimal("80000.00")),
    SubscriptionPlan.BUSINESS: PlanPrice(monthly=Decimal("20000.00"), annual=Decimal("200000.00")),
}

SELF_SERVE_PLANS = tuple(PLAN_PRICES)


def price_for(plan: SubscriptionPlan, *, annual: bool) -> Decimal:
    """What one billing period of `plan` costs.

    Raises for TRIAL and ENTERPRISE: neither has a price anything may charge
    against, and defaulting to zero would silently give away a paid plan.
    """
    price = PLAN_PRICES.get(plan)
    if price is None:
        raise ValueError(f"{plan.value} has no self-serve price")
    return price.annual if annual else price.monthly
