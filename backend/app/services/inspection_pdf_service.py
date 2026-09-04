"""Inspection PDF generation — Phase 2 (US-049, US-050).

Generates inspection reports and move-in/move-out comparison PDFs.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import FileCategory
from app.models.inspection import InspectionReport
from app.models.organization import Organization
from app.models.property import Unit
from app.services.storage_service import store_bytes


async def generate_inspection_pdf(
    db: AsyncSession,
    report: InspectionReport,
    organization_id: uuid.UUID,
) -> uuid.UUID:
    """Generate a PDF for an inspection report and store it. Returns the file id."""
    from weasyprint import HTML

    org = await db.get(Organization, organization_id)
    unit = await db.get(Unit, report.unit_id)

    html = _render_inspection_html(report, org, unit)
    pdf_bytes = HTML(string=html).write_pdf()

    filename = f"inspection_{report.reference_code}.pdf"
    file_id = await store_bytes(
        db,
        data=pdf_bytes,
        filename=filename,
        content_type="application/pdf",
        category=FileCategory.INSPECTION_REPORT,
        organization_id=organization_id,
        entity_type="inspection_report",
        entity_id=report.id,
    )
    return file_id


async def generate_comparison_pdf(
    db: AsyncSession,
    move_out_report: InspectionReport,
    move_in_report: InspectionReport,
    organization_id: uuid.UUID,
) -> uuid.UUID:
    """Generate a side-by-side comparison PDF for move-out vs move-in."""
    from weasyprint import HTML

    org = await db.get(Organization, organization_id)
    unit = await db.get(Unit, move_out_report.unit_id)

    html = _render_comparison_html(move_out_report, move_in_report, org, unit)
    pdf_bytes = HTML(string=html).write_pdf()

    filename = f"comparison_{move_out_report.reference_code}.pdf"
    file_id = await store_bytes(
        db,
        data=pdf_bytes,
        filename=filename,
        content_type="application/pdf",
        category=FileCategory.INSPECTION_REPORT,
        organization_id=organization_id,
        entity_type="inspection_report",
        entity_id=move_out_report.id,
    )
    return file_id


# Inline styles because WeasyPrint renders each report standalone, with no
# stylesheet to link against. Naming them keeps the row templates readable.
CELL = "padding:8px;border:1px solid #e5e7eb"
CELL_CENTER = f"{CELL};text-align:center"
BADGE = "color:white;padding:2px 8px;border-radius:4px;font-size:12px"
PAGE_CSS = (
    "body{font-family:Arial,sans-serif;margin:40px;color:#111}"
    "h1{color:#1e3a5f}table{width:100%;border-collapse:collapse}"
    "th{background:#1e3a5f;color:white;padding:10px;text-align:left}"
)


def _condition_badge(condition: str | None) -> str:
    colors = {"excellent": "#16a34a", "good": "#2563eb", "fair": "#d97706", "poor": "#dc2626"}
    color = colors.get((condition or "").lower(), "#6b7280")
    label = (condition or "N/A").title()
    return f'<span style="background:{color};{BADGE}">{label}</span>'


def _render_inspection_html(
    report: InspectionReport,
    org: Organization | None,
    unit: Unit | None,
) -> str:
    org_name = org.name if org else "RentFlow"
    unit_label = f"Unit {unit.unit_number}" if unit else "Unit"
    type_label = report.inspection_type.value.replace("_", " ").title()
    submitted = report.submitted_at.strftime("%d %b %Y %H:%M") if report.submitted_at else "Draft"

    rows = ""
    for room in report.rooms_data:
        rows += f"""
        <tr>
            <td style="{CELL}">{room.get('name','')}</td>
            <td style="{CELL_CENTER}">{_condition_badge(room.get('condition'))}</td>
            <td style="{CELL}">{room.get('notes','') or '—'}</td>
            <td style="{CELL_CENTER}">{len(room.get('photo_file_ids',[]))} photo(s)</td>
        </tr>"""

    deduction = ""
    if report.deposit_deduction:
        deduction = (
            '<p style="margin-top:20px"><strong>Deposit Deduction:</strong> '
            f"KES {report.deposit_deduction:,.2f}<br>{report.deduction_notes or ''}</p>"
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{PAGE_CSS}</style>
</head><body>
<h1>{org_name}</h1>
<h2>{type_label} Inspection Report</h2>
<p><strong>Reference:</strong> {report.reference_code} &nbsp;
<strong>Unit:</strong> {unit_label} &nbsp;
<strong>Date:</strong> {submitted}</p>
<p><strong>Inspector:</strong> {report.inspector_name or '—'}</p>
{f'<p><strong>Notes:</strong> {report.notes}</p>' if report.notes else ''}
<table>
<thead><tr><th>Room</th><th>Condition</th><th>Notes</th><th>Photos</th></tr></thead>
<tbody>{rows}</tbody>
</table>
{deduction}
</body></html>"""


def _render_comparison_html(
    move_out: InspectionReport,
    move_in: InspectionReport,
    org: Organization | None,
    unit: Unit | None,
) -> str:
    org_name = org.name if org else "RentFlow"
    unit_label = f"Unit {unit.unit_number}" if unit else "Unit"

    # Build a map of move-in rooms by name
    move_in_map = {r.get("name", ""): r for r in move_in.rooms_data}

    rows = ""
    for room in move_out.rooms_data:
        name = room.get("name", "")
        mi_room = move_in_map.get(name, {})
        mi_cond = mi_room.get("condition")
        mo_cond = room.get("condition")
        changed = mi_cond != mo_cond and mi_cond and mo_cond
        bg = ' style="background:#fef3c7"' if changed else ""
        rows += f"""
        <tr{bg}>
            <td style="{CELL}">{name}</td>
            <td style="{CELL_CENTER}">{_condition_badge(mi_cond)}</td>
            <td style="{CELL_CENTER}">{_condition_badge(mo_cond)}</td>
            <td style="{CELL_CENTER}">{'⚠ Changed' if changed else '✓ Same'}</td>
        </tr>"""

    move_in_date = move_in.submitted_at.strftime("%d %b %Y") if move_in.submitted_at else "—"
    move_out_date = move_out.submitted_at.strftime("%d %b %Y") if move_out.submitted_at else "—"

    deduction = ""
    if move_out.deposit_deduction:
        deduction = (
            '<p style="margin-top:20px;background:#fef3c7;padding:12px;border-radius:4px">'
            "<strong>Deposit Deduction:</strong> "
            f"KES {move_out.deposit_deduction:,.2f}<br>{move_out.deduction_notes or ''}</p>"
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{PAGE_CSS}</style>
</head><body>
<h1>{org_name}</h1>
<h2>Move-In / Move-Out Comparison Report</h2>
<p><strong>Unit:</strong> {unit_label} &nbsp;
<strong>Move-In:</strong> {move_in_date} ({move_in.reference_code}) &nbsp;
<strong>Move-Out:</strong> {move_out_date} ({move_out.reference_code})</p>
<table>
<thead><tr><th>Room</th><th>Move-In Condition</th><th>Move-Out Condition</th><th>Change</th></tr></thead>
<tbody>{rows}</tbody>
</table>
{deduction}
</body></html>"""
