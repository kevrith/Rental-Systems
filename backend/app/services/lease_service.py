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
from app.models.tenant import LeaseTemplate, Tenancy, TenancyCoTenant, Tenant
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
    co_tenant_names: str = "",
) -> dict:
    """The `{{placeholders}}` a custom lease template can reference.

    `co_tenant_names` (US-107) is a comma-joined list of any additional tenants
    on this tenancy beyond the primary — empty when there are none, so a
    template's `{% if co_tenant_names %}` guard costs nothing for the common case.
    """
    return {
        "landlord_name": organization.legal_name or organization.name,
        "landlord_address": organization.address or "",
        "landlord_phone": organization.contact_phone or "",
        "landlord_email": organization.contact_email or "",
        "tenant_name": tenant.full_name,
        "co_tenant_names": co_tenant_names,
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

    co_tenant_rows = await db.scalars(select(TenancyCoTenant).where(TenancyCoTenant.tenancy_id == tenancy.id))
    co_tenants = [await db.get(Tenant, row.tenant_id) for row in co_tenant_rows]
    co_tenant_names = ", ".join(co.full_name for co in co_tenants if co is not None)

    if template is not None:
        variables = build_variables(
            organization=organization,
            tenant=tenant,
            tenancy=tenancy,
            unit=unit,
            property_record=property_record,
            co_tenant_names=co_tenant_names,
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
<p>
THIS TENANCY AGREEMENT is made this {{ today }} BETWEEN <strong>{{ landlord_name }}</strong>
of {{ landlord_address }}, telephone {{ landlord_phone }}, email {{ landlord_email }}
(hereinafter called "the Landlord", which expression shall where the context so admits
include the Landlord's successors in title and permitted assigns) of the one part,
</p>
<p>
AND <strong>{{ tenant_name }}</strong>{% if co_tenant_names %} and <strong>{{ co_tenant_names }}</strong>
(jointly and severally with {{ tenant_name }}){% endif %}, holder of National ID / Passport No.
{{ tenant_id_number }}, telephone {{ tenant_phone }}, email {{ tenant_email }}
(hereinafter called "the Tenant", which expression shall where the context so admits
include the Tenant's legal representatives and any named co-tenant) of the other part.
</p>
<p>
The Landlord and the Tenant are together referred to as "the Parties" and this tenancy
is recorded under reference {{ tenancy_reference }}.
</p>

<h2>1. The Premises</h2>
<table class="kv">
  <tr><td class="label">Property</td><td class="value">{{ property_name }}</td></tr>
  <tr><td class="label">Address</td>
    <td class="value">{{ property_address }}, {{ property_county }} County</td></tr>
  <tr><td class="label">Unit</td><td class="value">{{ unit_number }} ({{ unit_type }})</td></tr>
  <tr><td class="label">Configuration</td>
    <td class="value">{{ bedrooms }} bedroom(s), {{ bathrooms }} bathroom(s)</td></tr>
</table>
<p>
(hereinafter called "the Premises"), together with the fixtures, fittings and appliances
recorded in the written inventory and condition report which the Parties shall complete
and sign at the start of the term and which forms part of this Agreement.
</p>

<h2>2. Term of Tenancy</h2>
<table class="kv">
  <tr><td class="label">Commencement date</td><td class="value">{{ lease_start_date }}</td></tr>
  <tr><td class="label">Expiry date</td><td class="value">{{ lease_end_date }}</td></tr>
  <tr><td class="label">Notice period</td><td class="value">{{ notice_period_days }} days</td></tr>
</table>

<h2>3. Rent and Deposit</h2>
<table class="kv">
  <tr><td class="label">Monthly rent</td><td class="value">KES {{ rent_amount }}</td></tr>
  <tr><td class="label">Security deposit</td><td class="value">KES {{ deposit_amount }}</td></tr>
  <tr><td class="label">Rent due on</td><td class="value">Day {{ billing_day }} of each month</td></tr>
</table>

<h2>4. Terms and Conditions</h2>

<div class="clause">
  <span class="clause-title">4.1 Term, renewal and holding over.</span>
  <ol type="a">
    <li>This Agreement is for a fixed term commencing on {{ lease_start_date }} and expiring
      on {{ lease_end_date }}.</li>
    <li>Either Party wishing to end the tenancy at the expiry of the fixed term shall give
      the other not less than {{ notice_period_days }} days' written notice before the
      expiry date.</li>
    <li>Either Party may also terminate this Agreement before the end of the fixed term by
      giving not less than {{ notice_period_days }} days' written notice expiring on a rent
      payment date, without prejudice to any accrued rights or liabilities.</li>
    <li>If the Tenant remains in occupation after the expiry date with the Landlord's
      consent and no new agreement is signed, the tenancy continues as a monthly tenancy on
      the same terms, terminable by either Party on {{ notice_period_days }} days' written
      notice.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.2 Payment of rent.</span>
  <ol type="a">
    <li>Rent is payable monthly in advance, without demand, deduction or set-off, into the
      bank or mobile money account notified in writing by the Landlord. Payment is only
      effective when received in cleared funds in that account, and every payment shall be
      acknowledged by an official receipt.</li>
    <li>Where the term commences on a date other than the billing day, the first payment
      shall be an apportioned amount covering the period from {{ lease_start_date }} to the
      first billing day, calculated on a daily basis, payable on or before the commencement
      date. Where a calendar month does not contain the billing day, rent for that month is
      payable on the last day of the month.</li>
    <li>Where the Premises are let for a commercial or business use and the Landlord is
      registered for value added tax, the rent stated above is exclusive of VAT, which
      shall be payable by the Tenant at the prevailing rate against a valid tax invoice.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.3 Late payment.</span>
  Rent remaining unpaid seven (7) days after the due date shall attract interest at the
  rate of one per cent (1%) per month, calculated on a daily basis until payment in full.
  This is an agreed contractual charge and is without prejudice to the Landlord's other
  remedies under this Agreement.
</div>

<div class="clause">
  <span class="clause-title">4.4 Rent review.</span>
  The rent may be reviewed on each anniversary of the commencement date, or on renewal, by
  written notice given not less than sixty (60) days in advance, having regard to
  prevailing market rates. Any increase takes effect only from the expiry of that notice.
</div>

<div class="clause">
  <span class="clause-title">4.5 Security deposit.</span>
  <ol type="a">
    <li>The deposit is held by the Landlord as security for the Tenant's performance of
      this Agreement and shall not bear interest unless required by law.</li>
    <li>The Tenant shall not treat the deposit as payment of rent for the final month or
      any other month of the term, and rent remains payable in full until the end of the
      term.</li>
    <li>The Landlord may deduct from the deposit any arrears of rent, unpaid utility or
      service charges, the cost of repairing damage beyond fair wear and tear, and the cost
      of replacing missing fixtures, fittings or keys.</li>
    <li>Within thirty (30) days after the Tenant has vacated, returned all keys and
      provided a forwarding address and bank details, the Landlord shall refund the balance
      of the deposit together with a written, itemised statement of any deductions,
      supported by receipts or quotations where available.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.6 Utilities and outgoings.</span>
  <ol type="a">
    <li>The Tenant shall pay promptly, when due, all charges for electricity, water,
      refuse collection, telephone, internet and any other utility consumed at the
      Premises, together with any service charge, and shall keep the accounts in good
      standing throughout the term.</li>
    <li>Where any utility is billed to the Landlord and recovered from the Tenant, the
      Landlord shall provide a copy of the bill or meter reading on request and the Tenant
      shall pay the recovered amount with the next instalment of rent.</li>
    <li>The Landlord shall pay all land rent, land rates and any statutory outgoings
      assessed on the Landlord as owner.</li>
    <li>On or before the date of vacating, the Tenant shall settle all utility accounts in
      full and deliver final receipts or meter readings to the Landlord. Any outstanding
      amount may be deducted from the deposit.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.7 Use of premises.</span>
  <ol type="a">
    <li>The Premises shall be used solely as a private residence by the Tenant and the
      persons named in this Agreement, and for no other purpose without the Landlord's
      prior written consent.</li>
    <li>The Tenant shall not use the Premises, or permit them to be used, for any illegal,
      immoral or hazardous purpose, or for any trade or business.</li>
    <li>The Tenant shall not do anything that causes nuisance, annoyance, damage or
      disturbance to the Landlord, other tenants or neighbouring occupiers, and shall
      comply with all reasonable house rules notified in writing by the Landlord or the
      management of the property.</li>
    <li>The maximum number of persons permitted to reside in the Premises is as agreed in
      writing with the Landlord.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.8 Repairs and maintenance.</span>
  <ol type="a">
    <li>The Landlord shall keep the structure, roof, exterior walls, main drains, and the
      main water, sewerage and electrical installations of the Premises in reasonable
      repair and working order, and shall carry out such repairs within a reasonable time
      after receiving written notice from the Tenant.</li>
    <li>The Tenant shall keep the interior of the Premises, including all fixtures,
      fittings, sanitary ware, doors, windows, locks and appliances supplied by the
      Landlord, in good and clean condition, fair wear and tear excepted.</li>
    <li>The Tenant shall bear the cost of repairing or replacing any item damaged by the
      negligence or misuse of the Tenant, members of the Tenant's household, or the
      Tenant's visitors.</li>
    <li>If the Tenant fails to carry out a repair for which the Tenant is responsible
      within fourteen (14) days of written notice, the Landlord may carry it out and
      recover the reasonable cost from the Tenant as a debt.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.9 Alterations and fixtures.</span>
  <ol type="a">
    <li>The Tenant shall not make any structural or non-structural alteration or addition
      to the Premises, including partitioning, drilling into walls, changing locks, or
      altering the electrical or plumbing installations, without the Landlord's prior
      written consent, which shall not be unreasonably withheld.</li>
    <li>All alterations, additions and fixtures made with consent shall, at the Landlord's
      written election, either remain part of the Premises without compensation to the
      Tenant or be removed by the Tenant at the Tenant's own cost before the end of the
      term, with the Premises reinstated and made good.</li>
    <li>The Tenant may remove trade fixtures and free-standing items belonging to the
      Tenant, provided any damage caused by removal is made good.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.10 Access and inspection.</span>
  <ol type="a">
    <li>The Landlord and persons authorised by the Landlord may enter the Premises at
      reasonable hours on giving the Tenant not less than twenty-four (24) hours' prior
      notice, in order to inspect their condition, carry out repairs or works, read
      meters, or show the Premises to prospective tenants or purchasers during the last
      sixty (60) days of the term.</li>
    <li>In a genuine emergency, including fire, flood, gas escape or a threat to life or
      property, the Landlord may enter without notice and, if necessary, by force, and
      shall inform the Tenant as soon as possible afterwards.</li>
    <li>The Tenant shall not unreasonably refuse access once proper notice has been given.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.11 Assignment and subletting.</span>
  The Tenant shall not assign, sublet, share possession of, or otherwise part with
  possession of the whole or any part of the Premises, nor list or offer the Premises for
  short-term or holiday letting on any platform, without the prior written consent of the
  Landlord, such consent not to be unreasonably withheld in the case of a respectable and
  responsible proposed assignee. Any purported assignment or subletting in breach of this
  clause is void and entitles the Landlord to terminate this Agreement.
</div>

<div class="clause">
  <span class="clause-title">4.12 Insurance and damage.</span>
  <ol type="a">
    <li>The Landlord shall insure the structure of the Premises against fire and other
      usual risks. The Landlord is not responsible for insuring the Tenant's furniture,
      equipment, goods or personal effects, and the Tenant is advised to take out contents
      insurance.</li>
    <li>The Landlord shall not be liable for loss of or damage to the Tenant's property, or
      for injury to any person, except to the extent caused by the Landlord's negligence or
      breach of this Agreement or by any liability that cannot lawfully be excluded.</li>
    <li>The Tenant shall not do anything that increases the premium on, or renders void,
      the Landlord's insurance, and shall reimburse any increase caused by the Tenant's use
      of the Premises.</li>
    <li>If the Premises are destroyed or so damaged by fire, flood or other insured risk
      (otherwise than through the fault of the Tenant) as to be unfit for occupation, rent
      shall abate in whole or in proportion to the unfit part until the Premises are
      restored. If they are not restored within ninety (90) days, either Party may
      terminate this Agreement by written notice, and the deposit and any rent paid in
      advance shall be refunded on a pro-rata basis.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.13 Quiet enjoyment and Landlord's warranty.</span>
  The Landlord warrants that the Landlord is the registered owner of the Premises or is
  otherwise lawfully entitled to grant this lease, and that there is no restriction
  preventing the letting. Provided the Tenant pays the rent and observes the Tenant's
  obligations under this Agreement, the Tenant may peaceably hold and enjoy the Premises
  without interruption by the Landlord or any person lawfully claiming through the
  Landlord.
</div>

<div class="clause">
  <span class="clause-title">4.14 Compliance with laws and house rules.</span>
  The Tenant shall comply with all applicable laws, county by-laws, and any reasonable
  house rules or estate regulations notified by the Landlord in writing from time to time,
  and shall not do or permit anything on the Premises that is a nuisance or annoyance to
  neighbouring occupiers or that invalidates the Landlord's insurance.
</div>

<div class="clause">
  <span class="clause-title">4.15 Termination.</span>
  <ol type="a">
    <li>The Landlord may terminate this Agreement by written notice if: (i) rent remains
      unpaid for thirty (30) days after the due date, whether formally demanded or not;
      (ii) the Tenant commits a material breach of any other term and fails to remedy it
      within twenty-one (21) days of written notice specifying the breach; or (iii) the
      Tenant is declared bankrupt or, being a company, enters liquidation.</li>
    <li>On lawful termination the Landlord may re-enter the Premises and this Agreement
      shall determine, without prejudice to any claim for arrears or for breach occurring
      before re-entry.</li>
    <li>The Landlord shall not evict the Tenant, change the locks, remove the Tenant's
      goods, or disconnect water or electricity otherwise than in accordance with the law.
      Any recovery of goods for rent arrears shall be effected only through a licensed
      auctioneer under the Distress for Rent Act (Cap 293).</li>
    <li>If the Tenant vacates before the end of the fixed term without giving the agreed
      notice, the Tenant remains liable for rent for the notice period, subject to the
      Landlord's duty to take reasonable steps to re-let the Premises.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.16 Vacation of premises and handover.</span>
  <ol type="a">
    <li>On the expiry or earlier termination of this Agreement the Tenant shall remove all
      belongings and rubbish, professionally clean the Premises, deliver up the Premises
      and all fixtures and fittings in the same condition as recorded in the inventory
      (fair wear and tear excepted), and return all keys, remotes and access cards to the
      Landlord.</li>
    <li>A joint check-out inspection shall be carried out on or before the vacating date.
      If the Tenant fails to attend after being given reasonable notice, the Landlord may
      inspect alone and the Landlord's written report shall be taken as accurate unless
      shown to be wrong.</li>
    <li>Any goods left in the Premises more than fourteen (14) days after vacation may,
      after written notice to the Tenant at the last known address, be removed and stored
      or disposed of by the Landlord, with the reasonable costs recoverable from the
      Tenant.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.17 Force majeure.</span>
  Neither Party shall be liable for any failure or delay in performing its obligations
  under this Agreement to the extent that the failure or delay is caused by an event
  beyond that Party's reasonable control, including fire, flood, riot, war, or government
  action, provided the affected Party notifies the other promptly and takes reasonable
  steps to mitigate the effect.
</div>

<div class="clause">
  <span class="clause-title">4.18 Indemnity.</span>
  Each Party shall indemnify the other against loss, damage or liability arising from that
  Party's negligence or breach of this Agreement, save to the extent caused by the other
  Party's own negligence or default.
</div>

<div class="clause">
  <span class="clause-title">4.19 Personal data.</span>
  <ol type="a">
    <li>The Landlord collects and processes the Tenant's personal data, including
      identification and contact details, for the purposes of administering this tenancy,
      billing, credit and reference checks, and compliance with legal obligations.</li>
    <li>The Landlord shall process such data in accordance with the Data Protection Act,
      2019, shall keep it secure, and shall not disclose it to third parties except to its
      managing agent, service providers, utility companies, insurers, professional
      advisers, or where required by law.</li>
    <li>Personal data shall be retained only for as long as necessary for these purposes
      and for any period required by law after the tenancy ends.</li>
    <li>The Tenant may request access to, correction of, or erasure of the Tenant's
      personal data by writing to the Landlord at the address in Clause 1, subject to the
      Landlord's legal retention obligations.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.20 Notices.</span>
  <ol type="a">
    <li>Any notice under this Agreement shall be in writing and delivered by hand, by
      registered post, or by email to the addresses stated in this Agreement (in the case
      of the Tenant, also to the Premises) or to such other address as a Party notifies in
      writing.</li>
    <li>A notice is deemed received: if delivered by hand, on the day of delivery; if sent
      by registered post, on the fifth business day after posting; and if sent by email, on
      the next business day after transmission, provided no delivery failure message is
      received.</li>
    <li>SMS or WhatsApp messages may be used for routine operational communication such as
      repair requests and inspection reminders, but not for notices terminating this
      Agreement or alleging breach.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.21 Governing law and dispute resolution.</span>
  <ol type="a">
    <li>This Agreement is governed by and shall be construed in accordance with the laws
      of Kenya.</li>
    <li>The Parties shall first attempt to resolve any dispute arising out of this
      Agreement amicably by negotiation within fourteen (14) days of written notice of the
      dispute.</li>
    <li>If the dispute is not resolved, it shall be referred to mediation by a mediator
      agreed between the Parties or, failing agreement, appointed by the Chairperson of the
      Mediation Training Institute (East Africa).</li>
    <li>Nothing in this clause prevents either Party from applying to the Business
      Premises Rent Tribunal, the Rent Restriction Tribunal or a court of competent
      jurisdiction in Kenya where the dispute falls within its jurisdiction, or from
      seeking urgent interim relief.</li>
  </ol>
</div>

<div class="clause">
  <span class="clause-title">4.22 Controlled tenancy note (commercial lettings only).</span>
  Where the Premises comprise a shop, hotel or catering establishment and the term of this
  Agreement is for less than five years, the tenancy may constitute a controlled tenancy
  under the Landlord and Tenant (Shops, Hotels and Catering Establishments) Act (Cap 301),
  restricting the Landlord's ability to terminate or raise rent except through the
  Business Premises Rent Tribunal. Where the Parties intend that the tenancy shall not be
  a controlled tenancy, this Agreement shall instead be granted for a term of not less than
  five years and one month, or shall contain a certified provision for termination
  otherwise than for breach in accordance with that Act.
</div>

<div class="clause">
  <span class="clause-title">4.23 Entire agreement and variation.</span>
  This Agreement, together with the inventory and any schedule referred to in it,
  constitutes the entire agreement between the Parties regarding the Premises and
  supersedes all prior discussions or representations. No variation shall be effective
  unless made in writing and signed by both Parties.
</div>

<div class="clause">
  <span class="clause-title">4.24 Severability.</span>
  If any provision of this Agreement is held invalid or unenforceable, the remaining
  provisions shall continue in full force and effect.
</div>

<h2>5. Execution</h2>
<p>
Under Section 3(3) of the Law of Contract Act (Cap 23), a contract creating an interest in
land must be in writing, signed by both Parties, with each signature attested by a witness
who was present at signing. Where the term of this Agreement exceeds one year, it shall
also be prepared in the prescribed form, stamped under the Stamp Duty Act (Cap 480) and
registered under the Land Registration Act, 2012 — an unstamped lease is not admissible in
evidence in proceedings to enforce it.
</p>
<p style="margin-top:5mm">
IN WITNESS WHEREOF the Parties have executed this Agreement on the date first written above.
</p>

<div class="signatures">
  <div>
    <div class="sig-line">Landlord — {{ landlord_name }}</div>
    <div style="font-size:8.5pt;color:#64748b">Date: ____________________</div>
    <div class="sig-line">Witness — Name, ID No. &amp; Signature</div>
  </div>
  <div>
    <div class="sig-line">Tenant — {{ tenant_name }}</div>
    <div style="font-size:8.5pt;color:#64748b">Date: ____________________</div>
    <div class="sig-line">Witness — Name, ID No. &amp; Signature</div>
  </div>
</div>
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
    "co_tenant_names": "",
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
