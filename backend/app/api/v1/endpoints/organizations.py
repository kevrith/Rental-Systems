from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, get_org_context, require, require_write
from app.core import crypto
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.organization import MpesaCollectionMode, Organization, SubscriptionPlan
from app.schemas.auth import MessageResponse
from app.schemas.organization import (
    MpesaSetupRequest,
    MpesaSetupStatus,
    OrganizationRead,
    OrganizationWithTrial,
    UpdateOrganizationRequest,
)
from app.services import audit_service, demo_service, mpesa_service, security_service

router = APIRouter()


def _with_trial(organization: Organization) -> OrganizationWithTrial:
    is_trial = organization.subscription_plan == SubscriptionPlan.TRIAL
    days_remaining: int | None = None
    if is_trial and organization.trial_ends_at:
        delta = organization.trial_ends_at - datetime.now(UTC)
        days_remaining = max(0, delta.days + (1 if delta.seconds else 0))

    return OrganizationWithTrial(
        **OrganizationRead.model_validate(organization).model_dump(),
        is_trial=is_trial,
        is_trial_expired=organization.is_trial_expired,
        trial_days_remaining=days_remaining,
        is_read_only=organization.is_read_only,
    )


@router.get("/me", response_model=OrganizationWithTrial)
async def get_my_organization(
    context: OrgContext = Depends(get_org_context),
) -> OrganizationWithTrial:
    return _with_trial(context.organization)


@router.patch("/me", response_model=OrganizationWithTrial)
async def update_my_organization(
    payload: UpdateOrganizationRequest,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> OrganizationWithTrial:
    organization = context.organization
    before = {field: getattr(organization, field) for field in payload.model_fields_set}

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(organization, field, value)

    if "role_session_timeouts" in payload.model_fields_set:
        await security_service.apply_role_session_timeouts(db, organization)

    after = {field: getattr(organization, field) for field in payload.model_fields_set}
    audit_service.record(
        db,
        organization_id=organization.id,
        action="organization.updated",
        entity_type="organization",
        entity_id=organization.id,
        actor=context.user,
        summary="Updated organization settings",
        changes=audit_service.diff(before, after),
        request=request,
    )
    await db.commit()
    await db.refresh(organization)
    return _with_trial(organization)


# ------------------------------------------------------------------ M-Pesa collection


def _mpesa_status(organization: Organization) -> MpesaSetupStatus:
    return MpesaSetupStatus(
        mode=organization.mpesa_collection_mode,
        shortcode=organization.mpesa_shortcode,
        phone_number=organization.mpesa_phone_number,
        account_label=organization.mpesa_account_label,
        daraja_environment=organization.daraja_environment,
        has_api_credentials=bool(
            organization.daraja_consumer_key_encrypted
            and organization.daraja_consumer_secret_encrypted
            and organization.daraja_passkey_encrypted
        ),
        can_send_payouts=bool(
            organization.daraja_initiator_name_encrypted and organization.daraja_security_credential_encrypted
        ),
        verified_at=organization.mpesa_verified_at,
    )


@router.get("/me/mpesa", response_model=MpesaSetupStatus)
async def mpesa_setup(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
) -> MpesaSetupStatus:
    """How this organisation collects rent. Never returns the credentials."""
    return _mpesa_status(context.organization)


@router.put("/me/mpesa", response_model=MpesaSetupStatus)
async def save_mpesa_setup(
    payload: MpesaSetupRequest,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MpesaSetupStatus:
    """Point rent at this landlord's own M-Pesa.

    Rent goes to their till, not to RentFlow — so these are their credentials,
    encrypted under their organisation's own key. Sending a credential as null
    leaves the stored one alone, which is what lets someone edit the account
    label without re-typing their Daraja secret.
    """
    organization = context.organization
    organization.mpesa_collection_mode = payload.mode
    organization.mpesa_shortcode = payload.shortcode
    organization.mpesa_phone_number = payload.phone_number
    organization.mpesa_account_label = payload.account_label
    organization.daraja_environment = payload.daraja_environment

    secrets_written = []
    for field, value in (
        ("daraja_consumer_key_encrypted", payload.consumer_key),
        ("daraja_consumer_secret_encrypted", payload.consumer_secret),
        ("daraja_passkey_encrypted", payload.passkey),
        ("daraja_initiator_name_encrypted", payload.initiator_name),
        ("daraja_security_credential_encrypted", payload.security_credential),
    ):
        if value:
            setattr(
                organization,
                field,
                await crypto.encrypt_for_org(db, organization.id, value),
            )
            secrets_written.append(field.removesuffix("_encrypted"))

    # Leaving AUTOMATED means the stored keys are no longer used for anything,
    # so they are dropped rather than left lying in the table.
    if payload.mode != MpesaCollectionMode.AUTOMATED:
        organization.daraja_consumer_key_encrypted = None
        organization.daraja_consumer_secret_encrypted = None
        organization.daraja_passkey_encrypted = None
        organization.daraja_initiator_name_encrypted = None
        organization.daraja_security_credential_encrypted = None
        organization.mpesa_verified_at = None

    audit_service.record(
        db,
        organization_id=organization.id,
        action="organization.mpesa_setup_changed",
        entity_type="organization",
        entity_id=organization.id,
        actor=context.user,
        summary=f"M-Pesa collection set to {payload.mode.value}",
        # The values are never recorded, only which ones were replaced.
        changes={"credentials_replaced": secrets_written, "shortcode": payload.shortcode},
    )
    await db.commit()
    await db.refresh(organization)
    return _mpesa_status(organization)


class MpesaTestResult(BaseModel):
    ok: bool
    message: str
    verified_at: datetime | None = None


@router.post("/me/mpesa/test", response_model=MpesaTestResult)
async def test_mpesa_credentials(
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MpesaTestResult:
    """Check the saved Daraja credentials against Safaricom.

    Without this a landlord types a wrong secret, sees "Saved", and only finds
    out when a tenant's payment fails — which is exactly the moment this product
    is supposed to be earning their trust.
    """
    organization = context.organization
    creds = await mpesa_service.credentials_for(db, organization)
    if creds is None:
        return MpesaTestResult(
            ok=False,
            message="Add your paybill and Daraja credentials first.",
            verified_at=organization.mpesa_verified_at,
        )

    ok, message = await mpesa_service.verify_credentials(creds)
    organization.mpesa_verified_at = datetime.now(UTC) if ok else None

    audit_service.record(
        db,
        organization_id=organization.id,
        action="organization.mpesa_tested",
        entity_type="organization",
        entity_id=organization.id,
        actor=context.user,
        summary=f"M-Pesa credential test {'passed' if ok else 'failed'}",
    )
    await db.commit()
    await db.refresh(organization)
    return MpesaTestResult(ok=ok, message=message, verified_at=organization.mpesa_verified_at)


# ------------------------------------------------------------- sample data


class DemoDataStatus(BaseModel):
    loaded: bool
    row_count: int
    recipe: str | None = None
    loaded_at: datetime | None = None


@router.get("/demo-data", response_model=DemoDataStatus)
async def demo_data_status(
    context: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> DemoDataStatus:
    dataset = await demo_service.current(db, context.organization_id)
    if dataset is None:
        return DemoDataStatus(loaded=False, row_count=0)
    return DemoDataStatus(
        loaded=True,
        row_count=dataset.row_count,
        recipe=dataset.recipe,
        loaded_at=dataset.created_at,
    )


@router.post("/demo-data", response_model=DemoDataStatus, status_code=status.HTTP_201_CREATED)
async def load_demo_data(
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> DemoDataStatus:
    """Fill the account with a sample portfolio so every screen has data (Module 24)."""
    dataset = await demo_service.seed(db, context)
    return DemoDataStatus(
        loaded=True,
        row_count=dataset.row_count,
        recipe=dataset.recipe,
        loaded_at=dataset.created_at,
    )


@router.delete("/demo-data", response_model=MessageResponse)
async def remove_demo_data(
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete exactly the rows the sample seeding created, and nothing else."""
    removed = await demo_service.remove(db, context)
    return MessageResponse(message=f"Removed {removed} sample record(s)")
