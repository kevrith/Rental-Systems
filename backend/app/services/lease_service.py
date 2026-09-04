"""Lease agreement generation (US-016).

A tenancy gets a professional PDF the moment it is created. Landlords who have
authored a custom template get theirs rendered with `{{variable}}` substitution;
everyone else gets the built-in Kenyan residential template, which is complete
enough to use unmodified.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import FileCategory, StoredFile
from app.models.organization import Organization
from app.models.property import Property, Unit
from app.models.tenant import LeaseTemplate, Tenancy, Tenant
from app.services import file_service, pdf_service, storage_service

DEFAULT_CLAUSES: list[dict[str, str]] = [
    {
        "title": "Use of premises",
        "body": (
            "The Tenant shall use the premises solely as a private residence and shall not "
            "carry on any trade or business therein without the prior written consent of the "
            "Landlord."
        ),
    },
    {
        "title": "Payment of rent",
        "body": (
            "Rent is payable monthly in advance on or before the due date stated above. Payment "
            "shall be made through the channels nominated by the Landlord, and every payment "
            "shall be acknowledged by an official receipt."
        ),
    },
    {
        "title": "Security deposit",
        "body": (
            "The deposit shall be held by the Landlord as security against damage, unpaid rent "
            "and unpaid utilities. It shall be refunded within thirty (30) days of vacation, "
            "less any lawful deductions, which shall be itemised in writing."
        ),
    },
    {
        "title": "Utilities",
        "body": (
            "The Tenant shall pay for water, electricity and any other utilities consumed on the "
            "premises. Where these are metered by the Landlord, charges shall be calculated from "
            "meter readings and billed with the monthly rent."
        ),
    },
    {
        "title": "Repairs and maintenance",
        "body": (
            "The Landlord shall keep the structure, roof and main services in good repair. The "
            "Tenant shall keep the interior in good and tenantable condition and shall report "
            "any defect promptly."
        ),
    },
    {
        "title": "Alterations",
        "body": (
            "The Tenant shall make no structural alteration, addition or redecoration without the "
            "Landlord's prior written consent."
        ),
    },
    {
        "title": "Access and inspection",
        "body": (
            "The Landlord or their agent may enter the premises at reasonable hours, having given "
            "the Tenant at least twenty-four (24) hours' notice, to inspect its condition or carry "
            "out repairs."
        ),
    },
    {
        "title": "Assignment and subletting",
        "body": (
            "The Tenant shall not assign, sublet or part with possession of the premises or any "
            "part of it without the Landlord's prior written consent."
        ),
    },
    {
        "title": "Termination",
        "body": (
            "Either party may terminate this Agreement by giving the notice period stated above in "
            "writing. The Landlord may terminate immediately where rent remains unpaid for sixty "
            "(60) days or where the Tenant is in material breach of these terms."
        ),
    },
    {
        "title": "Vacation of premises",
        "body": (
            "On termination the Tenant shall deliver up the premises in the condition recorded at "
            "the move-in inspection, fair wear and tear excepted, and shall return all keys."
        ),
    },
    {
        "title": "Governing law",
        "body": (
            "This Agreement is governed by the laws of Kenya, and any dispute shall be determined "
            "by the courts of Kenya."
        ),
    },
]


# A commercial lease is not a residential one with the word "office" in it: the
# covenants that matter are use class, service charge, alterations and insurance,
# and the quiet-enjoyment framing of a home is simply the wrong document (US-069).
COMMERCIAL_CLAUSES: list[dict[str, str]] = [
    {
        "title": "Permitted use",
        "body": (
            "The Tenant shall use the premises only for the permitted use stated above and for "
            "no other purpose. The Tenant shall not use the premises for any purpose that is "
            "unlawful, that invalidates the Landlord's insurance, or that causes nuisance or "
            "annoyance to other occupiers of the building."
        ),
    },
    {
        "title": "Rent and service charge",
        "body": (
            "Rent is payable monthly in advance. In addition, the Tenant shall pay the service "
            "charge apportioned to the premises, which covers the running of the common parts of "
            "the building including security, cleaning, the generator and the lift where "
            "provided. The Landlord shall account for the service charge annually, showing what "
            "was budgeted, what was charged and what was spent."
        ),
    },
    {
        "title": "Licences and compliance",
        "body": (
            "The Tenant shall at its own cost obtain and maintain every licence, permit and "
            "approval required to carry on its business at the premises, including the county "
            "single business permit, and shall comply with all statutory requirements applicable "
            "to that business."
        ),
    },
    {
        "title": "Alterations and fit-out",
        "body": (
            "The Tenant shall not make any structural alteration to the premises without the "
            "prior written consent of the Landlord. Non-structural fit-out works may be carried "
            "out with the Landlord's written approval of the plans, and shall be removed at the "
            "end of the term if the Landlord so requires, making good any damage."
        ),
    },
    {
        "title": "Repair",
        "body": (
            "The Tenant shall keep the interior of the premises in good and tenantable repair, "
            "fair wear and tear excepted. The Landlord shall keep the structure, exterior and "
            "common parts of the building in repair."
        ),
    },
    {
        "title": "Insurance",
        "body": (
            "The Landlord shall insure the building against fire and the usual risks. The Tenant "
            "shall insure its own stock, fittings and equipment, and shall maintain public "
            "liability insurance, producing evidence of cover to the Landlord on request."
        ),
    },
    {
        "title": "Parking",
        "body": (
            "The Tenant is allocated the parking bays stated above for the use of its staff and "
            "visitors. Bays are allocated and may be reallocated by the Landlord acting "
            "reasonably, and shall not be sub-let or assigned separately from the premises."
        ),
    },
    {
        "title": "Assignment and subletting",
        "body": (
            "The Tenant shall not assign, sublet, charge or part with possession of the whole or "
            "any part of the premises without the prior written consent of the Landlord, such "
            "consent not to be unreasonably withheld in the case of a respectable and responsible "
            "assignee."
        ),
    },
    {
        "title": "Termination and reinstatement",
        "body": (
            "At the end of the term the Tenant shall yield up the premises in the state of repair "
            "required by this lease, remove its signage and fittings, and make good all damage "
            "caused by that removal."
        ),
    },
]


def clauses_for(unit: Unit) -> list[dict[str, str]]:
    """Commercial units get the commercial covenants; everything else the standard ones."""
    return COMMERCIAL_CLAUSES if unit.use_class is not None else DEFAULT_CLAUSES


async def get_default_template(db: AsyncSession, organization_id: uuid.UUID) -> LeaseTemplate | None:
    return await db.scalar(
        select(LeaseTemplate).where(
            LeaseTemplate.organization_id == organization_id,
            LeaseTemplate.is_default.is_(True),
            LeaseTemplate.is_archived.is_(False),
        )
    )


def build_variables(
    *,
    organization: Organization,
    tenant: Tenant,
    tenancy: Tenancy,
    unit: Unit,
    property_record: Property,
) -> dict:
    """The `{{placeholders}}` a custom lease template can reference."""
    return {
        "landlord_name": organization.legal_name or organization.name,
        "landlord_address": organization.address or "",
        "landlord_phone": organization.contact_phone or "",
        "landlord_email": organization.contact_email or "",
        "tenant_name": tenant.full_name,
        "tenant_phone": tenant.phone_number,
        "tenant_email": tenant.email or "",
        "tenant_id_number": tenant.national_id or "",
        "tenant_reference": tenant.reference_code,
        "property_name": property_record.name,
        "property_address": property_record.address,
        "property_county": property_record.county or "",
        "unit_number": unit.unit_number,
        "unit_type": unit.unit_type or "",
        "bedrooms": unit.bedrooms or 0,
        "bathrooms": unit.bathrooms or 0,
        "rent_amount": pdf_service.format_kes(tenancy.monthly_rent),
        "deposit_amount": pdf_service.format_kes(tenancy.deposit_amount),
        "billing_day": tenancy.billing_day,
        "notice_period_days": tenancy.notice_period_days,
        "lease_start_date": pdf_service.format_long_date(tenancy.start_date),
        "lease_end_date": (
            "Open-ended" if tenancy.is_open_ended else pdf_service.format_long_date(tenancy.end_date)
        ),
        "tenancy_reference": tenancy.reference_code,
        "today": pdf_service.format_long_date(datetime.now(UTC).date()),
    }


async def _logo_url(db: AsyncSession, file_id: uuid.UUID | None) -> str | None:
    if file_id is None:
        return None
    record = await db.get(StoredFile, file_id)
    if record is None:
        return None
    # WeasyPrint fetches this while rendering, so it must resolve without auth —
    # a signed URL does, for its 60-minute lifetime.
    return storage_service.download_url(record.storage_key, record.filename)


async def generate_lease_pdf(
    db: AsyncSession,
    tenancy: Tenancy,
    *,
    template_id: uuid.UUID | None = None,
) -> bytes:
    organization = await db.get(Organization, tenancy.organization_id)
    tenant = await db.get(Tenant, tenancy.tenant_id)
    unit = await db.get(Unit, tenancy.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    if not (organization and tenant and unit and property_record):
        raise ValueError("Tenancy is missing the records needed to build a lease")

    template: LeaseTemplate | None = None
    if template_id:
        template = await db.get(LeaseTemplate, template_id)
        if template and template.organization_id != tenancy.organization_id:
            template = None
    if template is None:
        template = await get_default_template(db, tenancy.organization_id)

    logo_url = await _logo_url(db, (template.logo_file_id if template else None) or organization.logo_file_id)

    if template is not None:
        variables = build_variables(
            organization=organization,
            tenant=tenant,
            tenancy=tenancy,
            unit=unit,
            property_record=property_record,
        )
        body = pdf_service.substitute(template.body_html, variables)
        html = pdf_service.render_html(
            "lease_custom.html",
            {
                "organization": organization,
                "logo_url": logo_url,
                "letterhead_text": template.letterhead_text,
                "body": body,
                "generated_at": datetime.now(UTC).date(),
                "tenancy": tenancy,
            },
        )
        return pdf_service.render_string_to_pdf(html)

    return pdf_service.render_pdf(
        "lease.html",
        {
            "organization": organization,
            "logo_url": logo_url,
            "landlord": {
                "name": organization.legal_name or organization.name,
                "address": organization.address,
            },
            "tenant": tenant,
            "tenancy": tenancy,
            "unit": unit,
            "property": property_record,
            "clauses": clauses_for(unit),
            "is_commercial": unit.use_class is not None,
            "custom_clauses": [],
            "generated_at": datetime.now(UTC).date(),
        },
    )


async def generate_and_store_lease(
    db: AsyncSession, tenancy: Tenancy, template_id: uuid.UUID | None = None
) -> StoredFile:
    """Render the lease and file it in the tenant's document vault."""
    pdf_bytes = await generate_lease_pdf(db, tenancy, template_id=template_id)
    record = await file_service.register_generated(
        db,
        tenancy.organization_id,
        data=pdf_bytes,
        filename=f"Lease-{tenancy.reference_code}.pdf",
        category=FileCategory.LEASE,
        entity_type="tenant",
        entity_id=tenancy.tenant_id,
    )
    tenancy.lease_document_id = record.id
    return record


STARTER_TEMPLATE_HTML = """
<h2>1. The Parties</h2>
<p>This Agreement is made between <strong>{{ landlord_name }}</strong> ("the Landlord")
of {{ landlord_address }}, and <strong>{{ tenant_name }}</strong> ("the Tenant"),
ID number {{ tenant_id_number }}, telephone {{ tenant_phone }}.</p>

<h2>2. The Premises</h2>
<p>Unit <strong>{{ unit_number }}</strong> at {{ property_name }}, {{ property_address }}.</p>

<h2>3. Term</h2>
<p>Commencing {{ lease_start_date }} and ending {{ lease_end_date }}, with a notice period of
{{ notice_period_days }} days.</p>

<h2>4. Rent and Deposit</h2>
<p>Rent of <strong>KES {{ rent_amount }}</strong> per month is payable on day {{ billing_day }} of
each month. A security deposit of KES {{ deposit_amount }} is payable on signing.</p>

<h2>5. Additional Terms</h2>
<p>Add your own clauses here.</p>
""".strip()


# ------------------------------------------------------------- template preview (US-047)

# Fictitious but complete — every placeholder resolves, so a preview shows the
# real layout rather than a page of empty gaps.
SAMPLE_VARIABLES: dict[str, Any] = {
    "landlord_name": "Acacia Property Management Ltd",
    "landlord_address": "Ngong Road, Nairobi",
    "landlord_phone": "+254 700 000 000",
    "landlord_email": "leases@example.co.ke",
    "tenant_name": "Amina Njeri",
    "tenant_phone": "+254 711 111 111",
    "tenant_email": "amina.njeri@example.com",
    "tenant_id_number": "12345678",
    "tenant_reference": "TNT-2026-0042",
    "property_name": "Riverside Gardens",
    "property_address": "Riverside Drive, Nairobi",
    "property_county": "Nairobi",
    "unit_number": "B4",
    "unit_type": "2 bedroom",
    "bedrooms": 2,
    "bathrooms": 1,
    "rent_amount": "45,000.00",
    "deposit_amount": "90,000.00",
    "billing_day": 1,
    "notice_period_days": 30,
    "lease_start_date": "1 October 2026",
    "lease_end_date": "30 September 2027",
    "tenancy_reference": "TCY-2026-0042",
    "today": "4 September 2026",
}

TEMPLATE_VARIABLES: list[str] = sorted(SAMPLE_VARIABLES)


async def preview_template_pdf(
    db: AsyncSession,
    organization: Organization,
    *,
    body_html: str,
    letterhead_text: str | None = None,
    logo_file_id: uuid.UUID | None = None,
) -> bytes:
    """Render a template body with sample data, exactly as a real lease renders.

    The body is taken from the request rather than the database so the editor can
    preview unsaved edits. It goes through the same autoescaping substitution as a
    live lease, so a preview that looks right is a lease that will look right.
    """
    body = pdf_service.substitute(body_html, SAMPLE_VARIABLES)
    html = pdf_service.render_html(
        "lease_custom.html",
        {
            "organization": organization,
            "logo_url": await _logo_url(db, logo_file_id or organization.logo_file_id),
            "letterhead_text": letterhead_text,
            "body": body,
            "generated_at": datetime.now(UTC).date(),
            "tenancy": None,
            "is_preview": True,
        },
    )
    return pdf_service.render_string_to_pdf(html)
