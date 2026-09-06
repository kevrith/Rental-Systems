"""Onboarding, in-app help, referrals, NPS, milestones, the feature board and
the changelog (Sprint 20) — as seen by a logged-in user of one organisation.
The cross-organization customer-success view for RentFlow's own team lives in
`app.api.v1.endpoints.internal`.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, get_org_context, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.customer_success import MilestoneKey
from app.schemas.customer_success import (
    ChangelogEntryRead,
    FeatureRequestCreate,
    FeatureRequestRead,
    HelpArticleRead,
    MilestoneRead,
    NpsPendingRead,
    NpsResponseCreate,
    OnboardingProgressRead,
    OnboardingStepUpdate,
    ReferralCreate,
    ReferralRead,
    ReferralSummary,
    SupportRequestCreate,
    SupportRequestRead,
)
from app.services import (
    changelog_service,
    feature_board_service,
    help_service,
    milestone_service,
    nps_service,
    onboarding_service,
    referral_service,
    support_service,
)

router = APIRouter()


# ------------------------------------------------------------------ onboarding


@router.get("/onboarding", response_model=OnboardingProgressRead)
async def get_onboarding(
    context: OrgContext = Depends(get_org_context), db: AsyncSession = Depends(get_db)
) -> OnboardingProgressRead:
    row = await onboarding_service.get_or_create(db, context)
    return OnboardingProgressRead.model_validate(row)


@router.patch("/onboarding", response_model=OnboardingProgressRead)
async def update_onboarding(
    payload: OnboardingStepUpdate,
    context: OrgContext = Depends(require_write(Permission.ONBOARDING_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> OnboardingProgressRead:
    row = await onboarding_service.mark_step(db, context, payload.step)
    return OnboardingProgressRead.model_validate(row)


@router.post("/onboarding/dismiss", response_model=OnboardingProgressRead)
async def dismiss_onboarding(
    context: OrgContext = Depends(require_write(Permission.ONBOARDING_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> OnboardingProgressRead:
    row = await onboarding_service.dismiss(db, context)
    return OnboardingProgressRead.model_validate(row)


# ----------------------------------------------------------------------- help


@router.get("/help/articles", response_model=list[HelpArticleRead])
async def search_help_articles(
    q: str | None = Query(default=None, max_length=200),
    context: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> list[HelpArticleRead]:
    rows = await help_service.search(db, q)
    return [HelpArticleRead.model_validate(row) for row in rows]


@router.get("/help/articles/{slug}", response_model=HelpArticleRead)
async def get_help_article(
    slug: str, context: OrgContext = Depends(get_org_context), db: AsyncSession = Depends(get_db)
) -> HelpArticleRead:
    row = await help_service.get_by_slug(db, slug)
    return HelpArticleRead.model_validate(row)


# -------------------------------------------------------------------- support


@router.post("/support", response_model=SupportRequestRead, status_code=201)
async def create_support_request(
    payload: SupportRequestCreate,
    context: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> SupportRequestRead:
    row = await support_service.create_request(db, context, payload)
    return SupportRequestRead.model_validate(row)


# ------------------------------------------------------------------- referral


@router.get("/referral", response_model=ReferralSummary)
async def get_referral_summary(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)), db: AsyncSession = Depends(get_db)
) -> ReferralSummary:
    code, referrals = await referral_service.summary(db, context)
    return ReferralSummary(
        code=code.code,
        referral_link=referral_service.REFERRAL_LINK_TEMPLATE.format(code=code.code),
        credit_months=context.organization.credit_months,
        referrals=[ReferralRead.model_validate(row) for row in referrals],
    )


@router.post("/referral", response_model=ReferralRead, status_code=201)
async def create_referral(
    payload: ReferralCreate,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ReferralRead:
    row = await referral_service.record_referral(db, context, payload)
    return ReferralRead.model_validate(row)


# ------------------------------------------------------------------------ nps


@router.get("/nps/pending", response_model=NpsPendingRead | None)
async def get_pending_nps(
    context: OrgContext = Depends(get_org_context), db: AsyncSession = Depends(get_db)
) -> NpsPendingRead | None:
    prompt = await nps_service.pending_for(db, context)
    return NpsPendingRead.model_validate(prompt) if prompt else None


@router.post("/nps/{prompt_id}/respond", response_model=NpsPendingRead)
async def respond_to_nps(
    prompt_id: uuid.UUID,
    payload: NpsResponseCreate,
    context: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> NpsPendingRead:
    row = await nps_service.record_response(db, context, prompt_id, payload)
    return NpsPendingRead.model_validate(row)


# ------------------------------------------------------------------ milestones


@router.get("/milestones/pending", response_model=list[MilestoneRead])
async def get_pending_milestones(
    context: OrgContext = Depends(get_org_context), db: AsyncSession = Depends(get_db)
) -> list[MilestoneRead]:
    rows = await milestone_service.pending_for(db, context)
    return [MilestoneRead.model_validate(row) for row in rows]


@router.post("/milestones/{milestone_key}/acknowledge", status_code=204)
async def acknowledge_milestone(
    milestone_key: MilestoneKey,
    context: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    await milestone_service.acknowledge(db, context, milestone_key)


# --------------------------------------------------------------- feature board


@router.get("/feature-board", response_model=list[FeatureRequestRead])
async def list_feature_requests(
    context: OrgContext = Depends(get_org_context), db: AsyncSession = Depends(get_db)
) -> list[FeatureRequestRead]:
    return await feature_board_service.list_requests(db, context.user)


@router.post("/feature-board", status_code=201)
async def create_feature_request(
    payload: FeatureRequestCreate,
    context: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    row = await feature_board_service.create_request(db, context.user, payload)
    return {"id": str(row.id)}


@router.post("/feature-board/{feature_request_id}/vote")
async def vote_feature_request(
    feature_request_id: uuid.UUID,
    context: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    voted = await feature_board_service.toggle_vote(db, context.user, feature_request_id)
    return {"voted": voted}


# ----------------------------------------------------------------- changelog


@router.get("/changelog", response_model=list[ChangelogEntryRead])
async def list_changelog(
    context: OrgContext = Depends(get_org_context), db: AsyncSession = Depends(get_db)
) -> list[ChangelogEntryRead]:
    rows = await changelog_service.list_published(db)
    return [ChangelogEntryRead.model_validate(row) for row in rows]


@router.get("/changelog/unseen-count")
async def changelog_unseen_count(
    context: OrgContext = Depends(get_org_context), db: AsyncSession = Depends(get_db)
) -> dict[str, int]:
    count = await changelog_service.unseen_count(db, context.user)
    return {"count": count}
