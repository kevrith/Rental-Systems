"""The compliance audit report (US-078).

One PDF an owner can hand to an insurer, a bank or a county inspector that says
what the building holds, when each item expires, and what is already overdue.
"""

import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.models.facilities import ComplianceStatus
from app.models.organization import Organization
from app.models.property import Property
from app.services import facilities_service, pdf_service


async def render(
    db: AsyncSession, context: OrgContext, property_id: uuid.UUID | None = None
) -> tuple[bytes, str]:
    organization = await db.get(Organization, context.organization_id)
    property_record = await db.get(Property, property_id) if property_id else None

    items = await facilities_service.list_compliance_items(db, context, property_id=property_id)

    groups: dict[str, list] = {}
    for item in items:
        record = await db.get(Property, item.property_id)
        groups.setdefault(record.name if record else "Unassigned", []).append(item)

    counts = {state.value: 0 for state in ComplianceStatus}
    for item in items:
        counts[item.status.value] += 1

    try:
        pdf_bytes = pdf_service.render_pdf(
            "compliance_report.html",
            {
                "organization": organization,
                "logo_url": None,
                "property": property_record,
                "groups": sorted(groups.items()),
                "counts": counts,
                "total": len(items),
                "generated_at": date.today(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The compliance report could not be generated. Try again shortly.",
        ) from exc

    scope = property_record.name.replace(" ", "-") if property_record else "portfolio"
    return pdf_bytes, f"Compliance-{scope}-{date.today().isoformat()}.pdf"
