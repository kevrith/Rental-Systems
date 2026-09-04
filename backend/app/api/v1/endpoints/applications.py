"""Tenant screening endpoints (Sprint 14).

Three routers, because the audiences are three different people:
`router` is the letting office, and `public_router` / `apply_router` are the
applicant, their guarantor and their previous landlord — none of whom have a
login, and all of whom reach the system through a link.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.application import (
    ApplicationStatus,
    GuarantorStatus,
    ReferenceStatus,
    TenantApplication,
)
from app.models.file import StoredFile
from app.models.property import Property, Unit, UnitStatus
from app.models.user import User
from app.schemas.application import (
    ApplicationApprove,
    ApplicationCreate,
    ApplicationDetail,
    ApplicationRead,
    ApplicationReject,
    ApplicationUpdate,
    ApplicationWithdraw,
    GuarantorCreate,
    GuarantorInvite,
    GuarantorRead,
    GuarantorResponse,
    InterviewSchedule,
    PublicUnitListing,
    ReferenceCheckRead,
    ReferenceInvite,
    ReferenceRequest,
    ReferenceResponse,
)
from app.services import application_service, file_service, screening_service

router = APIRouter()
public_router = APIRouter()
apply_router = APIRouter()


async def _detail(db: AsyncSession, application: TenantApplication) -> ApplicationDetail:
    unit = await db.get(Unit, application.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    decided_by = await db.get(User, application.decided_by_id) if application.decided_by_id else None

    async def url_for(file_id: uuid.UUID | None) -> str | None:
        if file_id is None:
            return None
        record = await db.get(StoredFile, file_id)
        return file_service.to_url(record) if record else None

    payslips = []
    for file_id in application.payslip_file_ids:
        link = await url_for(uuid.UUID(str(file_id)))
        if link:
            payslips.append(link)

    guarantors = []
    for guarantor in application.guarantors:
        guarantors.append(
            GuarantorRead(
                **GuarantorRead.model_validate(guarantor).model_dump(exclude={"id_document_url"}),
                id_document_url=await url_for(guarantor.id_document_id),
            )
        )

    return ApplicationDetail(
        **ApplicationRead.model_validate(application).model_dump(),
        unit_number=unit.unit_number if unit else None,
        property_name=property_record.name if property_record else None,
        property_id=property_record.id if property_record else None,
        monthly_rent=unit.monthly_rent if unit else None,
        decided_by_name=decided_by.full_name if decided_by else None,
        band=screening_service.band(application.score),
        id_document_url=await url_for(application.id_document_id),
        passport_photo_url=await url_for(application.passport_photo_id),
        payslip_urls=payslips,
        guarantors=guarantors,
        references=[ReferenceCheckRead.model_validate(check) for check in application.references],
    )


# ------------------------------------------------------------------- operator


@router.get("/summary")
async def summary(
    context: OrgContext = Depends(require(Permission.APPLICATION_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await application_service.screening_summary(db, context)


@router.get("/waiting-list/{unit_id}")
async def unit_waiting_list(
    unit_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.APPLICATION_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Everyone still in the running for one unit, best score first (US-067)."""
    return await application_service.waiting_list(db, context, unit_id)


@router.post("", response_model=ApplicationDetail, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.APPLICATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetail:
    """Key in an application taken over the counter or on the phone."""
    application = await application_service.create_application(
        db,
        context.organization_id,
        payload,
        actor=context.user,
        submitted_online=False,
        request=request,
    )
    return await _detail(db, application)


@router.get("", response_model=list[ApplicationDetail])
async def list_applications(
    unit_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    application_status: ApplicationStatus | None = None,
    open_only: bool = False,
    search: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.APPLICATION_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationDetail]:
    rows = await application_service.list_applications(
        db,
        context,
        unit_id=unit_id,
        property_id=property_id,
        application_status=application_status,
        open_only=open_only,
        search=search,
        limit=limit,
    )
    return [await _detail(db, application) for application in rows]


@router.get("/{application_id}", response_model=ApplicationDetail)
async def get_application(
    application_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.APPLICATION_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetail:
    application = await application_service.get_application(db, context, application_id)
    return await _detail(db, application)


@router.patch("/{application_id}", response_model=ApplicationDetail)
async def update_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.APPLICATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetail:
    application = await application_service.update_application(db, context, application_id, payload, request)
    return await _detail(db, application)


@router.post("/{application_id}/review", response_model=ApplicationDetail)
async def review_application(
    application_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.APPLICATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetail:
    application = await application_service.start_review(db, context, application_id, request)
    return await _detail(db, application)


@router.post("/{application_id}/interview", response_model=ApplicationDetail)
async def schedule_interview(
    application_id: uuid.UUID,
    payload: InterviewSchedule,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.APPLICATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetail:
    application = await application_service.schedule_interview(
        db, context, application_id, payload.scheduled_for, payload.note, request
    )
    return await _detail(db, application)


@router.post("/{application_id}/approve", response_model=ApplicationDetail)
async def approve_application(
    application_id: uuid.UUID,
    payload: ApplicationApprove,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.APPLICATION_DECIDE)),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetail:
    application = await application_service.approve(db, context, application_id, payload, request)
    return await _detail(db, application)


@router.post("/{application_id}/reject", response_model=ApplicationDetail)
async def reject_application(
    application_id: uuid.UUID,
    payload: ApplicationReject,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.APPLICATION_DECIDE)),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetail:
    application = await application_service.reject(db, context, application_id, payload, request)
    return await _detail(db, application)


@router.post("/{application_id}/withdraw", response_model=ApplicationDetail)
async def withdraw_application(
    application_id: uuid.UUID,
    payload: ApplicationWithdraw,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.APPLICATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetail:
    application = await application_service.withdraw(db, context, application_id, payload.reason, request)
    return await _detail(db, application)


@router.post("/{application_id}/guarantors", response_model=ApplicationDetail)
async def add_guarantor(
    application_id: uuid.UUID,
    payload: GuarantorCreate,
    context: OrgContext = Depends(require_write(Permission.APPLICATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetail:
    """Add a guarantor and WhatsApp them for their acknowledgement (US-065)."""
    from app.services.notifications import normalize_phone

    application = await application_service.get_application(db, context, application_id)
    await screening_service.add_guarantor(
        db,
        application,
        full_name=payload.full_name,
        relationship_to_applicant=payload.relationship_to_applicant,
        phone_number=normalize_phone(payload.phone_number),
        email=payload.email,
        national_id=payload.national_id,
        id_document_id=payload.id_document_id,
        employer_name=payload.employer_name,
        occupation=payload.occupation,
        monthly_income=payload.monthly_income,
    )
    await db.refresh(application, ["guarantors", "references"])
    await screening_service.rescore(db, application)
    await db.commit()
    await db.refresh(application)
    return await _detail(db, application)


@router.post("/{application_id}/references", response_model=ApplicationDetail)
async def request_reference(
    application_id: uuid.UUID,
    payload: ReferenceRequest,
    context: OrgContext = Depends(require_write(Permission.APPLICATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetail:
    """Ask a previous landlord for a reference over WhatsApp (US-068)."""
    from app.services.notifications import normalize_phone

    application = await application_service.get_application(db, context, application_id)
    await screening_service.request_reference(
        db,
        application,
        landlord_name=payload.landlord_name,
        landlord_phone=normalize_phone(payload.landlord_phone),
        property_reference=payload.property_reference,
    )
    await db.refresh(application, ["guarantors", "references"])
    await screening_service.rescore(db, application)
    await db.commit()
    await db.refresh(application)
    return await _detail(db, application)


@router.post("/{application_id}/guarantors/{guarantor_id}/sign", response_model=ApplicationDetail)
async def send_guarantee_for_signing(
    application_id: uuid.UUID,
    guarantor_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.APPLICATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetail:
    """Send the deed of guarantee out for OTP-verified signing (US-065)."""
    application = await application_service.get_application(db, context, application_id)
    guarantor = next((g for g in application.guarantors if g.id == guarantor_id), None)
    if guarantor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Guarantor not found on this application"
        )

    await screening_service.send_guarantee_for_signing(db, guarantor)
    await db.refresh(application, ["guarantors", "references"])
    return await _detail(db, application)


# --------------------------------------------------------------- public: apply


@apply_router.get("/{unit_id}", response_model=PublicUnitListing)
async def unit_for_application(unit_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """What the applicant sees above the form. No auth: this is a public advert.

    Only vacant and reserved units resolve — an occupied unit is not for let, and
    answering for it would leak the portfolio to anyone guessing ids.
    """
    unit = await db.get(Unit, unit_id)
    if unit is None or unit.is_archived or unit.status == UnitStatus.OCCUPIED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This unit is not accepting applications"
        )
    property_record = await db.get(Property, unit.property_id)
    photos = await file_service.list_for_entity(db, unit.organization_id, "unit", unit.id)

    return PublicUnitListing(
        unit_id=unit.id,
        unit_number=unit.unit_number,
        property_name=property_record.name if property_record else "",
        property_address=property_record.address if property_record else "",
        monthly_rent=unit.monthly_rent,
        deposit_amount=unit.deposit_amount,
        bedrooms=unit.bedrooms,
        unit_type=unit.unit_type,
        description=property_record.description if property_record else None,
        photo_urls=[file_service.to_url(photo) for photo in photos],
        accepting_applications=unit.status == UnitStatus.VACANT,
    )


@apply_router.post("/{unit_id}", status_code=status.HTTP_201_CREATED)
async def submit_application(
    unit_id: uuid.UUID,
    payload: ApplicationCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The public application form (US-064)."""
    unit = await db.get(Unit, unit_id)
    if unit is None or unit.is_archived or unit.status != UnitStatus.VACANT:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This unit is not accepting applications"
        )

    # The unit in the path is authoritative; the body's copy is ignored so a
    # crafted payload cannot apply against a different organisation's unit.
    payload = payload.model_copy(update={"unit_id": unit.id})
    application = await application_service.create_application(
        db, unit.organization_id, payload, submitted_online=True, request=request
    )
    return {
        "reference_code": application.reference_code,
        "status": application.status.value,
        "message": (
            "Thank you. Your application has been received and the landlord has been notified. "
            "Keep your reference safe — we will contact you on the number you provided."
        ),
    }


# ----------------------------------------------------------- public: guarantee


@public_router.get("/guarantee/{token}", response_model=GuarantorInvite)
async def read_guarantee(token: str, db: AsyncSession = Depends(get_db)) -> GuarantorInvite:
    guarantor = await screening_service.guarantor_by_token(db, token)
    application = await db.get(TenantApplication, guarantor.application_id)
    unit = await db.get(Unit, application.unit_id) if application else None
    property_record = await db.get(Property, unit.property_id) if unit else None

    return GuarantorInvite(
        guarantor_name=guarantor.full_name,
        applicant_name=application.full_name if application else "",
        relationship_to_applicant=guarantor.relationship_to_applicant,
        unit_number=unit.unit_number if unit else "",
        property_name=property_record.name if property_record else "",
        monthly_rent=unit.monthly_rent if unit else Decimal("0.00"),
        status=guarantor.status,
        already_answered=guarantor.status != GuarantorStatus.PENDING,
    )


@public_router.post("/guarantee/{token}")
async def respond_to_guarantee(
    token: str, payload: GuarantorResponse, db: AsyncSession = Depends(get_db)
) -> dict:
    guarantor = await screening_service.respond_as_guarantor(
        db, token, accepted=payload.accepted, reason=payload.reason
    )
    return {
        "status": guarantor.status.value,
        "message": (
            "Thank you. Your guarantee has been recorded and the landlord notified."
            if payload.accepted
            else "Thank you for letting us know. The landlord has been informed."
        ),
    }


# ----------------------------------------------------------- public: reference


@public_router.get("/reference/{token}", response_model=ReferenceInvite)
async def read_reference(token: str, db: AsyncSession = Depends(get_db)) -> ReferenceInvite:
    check = await screening_service.reference_by_token(db, token)
    application = await db.get(TenantApplication, check.application_id)
    return ReferenceInvite(
        landlord_name=check.landlord_name,
        applicant_name=application.full_name if application else "",
        property_reference=check.property_reference,
        already_answered=check.status != ReferenceStatus.SENT,
    )


@public_router.post("/reference/{token}")
async def respond_to_reference(
    token: str, payload: ReferenceResponse, db: AsyncSession = Depends(get_db)
) -> dict:
    check = await screening_service.record_reference_response(
        db,
        token,
        paid_on_time=payload.paid_on_time,
        would_rent_again=payload.would_rent_again,
        note=payload.note,
    )
    return {
        "status": check.status.value,
        "message": "Thank you — your answer has been recorded.",
    }
