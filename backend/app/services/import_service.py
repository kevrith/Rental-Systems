"""Excel import for bulk tenant onboarding (US-072), and the template it expects.

Importing someone else's spreadsheet is mostly an exercise in refusing to guess.
Every row is validated in full before anything is written, the operator sees a
preview of exactly what will be created, and rows that cannot be understood are
reported by row number with the reason — never silently skipped, and never
half-imported.

The template is generated rather than shipped as a file so it can never drift
from the parser that reads it back.
"""

import io
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.models.property import Property, Unit, UnitStatus
from app.models.tenant import PaymentMethodPreference, Tenancy, TenancyStatus, Tenant
from app.services import audit_service, reference_service
from app.services.notifications import normalize_phone

ZERO = Decimal("0.00")

SHEET_NAME = "Tenants"

# (column header, required, hint shown in the template's second row)
COLUMNS: tuple[tuple[str, bool, str], ...] = (
    ("Full name", True, "Jane Wanjiru"),
    ("Phone number", True, "+254712345678"),
    ("Email", False, "jane@example.com"),
    ("National ID", False, "12345678"),
    ("Property name", True, "Must match a property already in RentFlow"),
    ("Unit number", True, "A1 — created if it does not exist"),
    ("Monthly rent", True, "25000"),
    ("Deposit", False, "25000"),
    ("Lease start", True, "2026-01-01"),
    ("Lease end", False, "Leave blank for an open-ended tenancy"),
    ("Billing day", False, "1 to 28 (default 1)"),
    ("Opening balance", False, "What they already owe you today"),
    ("Notes", False, ""),
)

HEADERS = [column[0] for column in COLUMNS]
MAX_ROWS = 2000


def build_template() -> bytes:
    """The downloadable import template (US-076's format, used from Sprint 15)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_NAME

    header_fill = PatternFill("solid", fgColor="1F3A93")
    for index, (name, required, hint) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=1, column=index, value=name + ("*" if required else ""))
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")

        hint_cell = sheet.cell(row=2, column=index, value=hint)
        hint_cell.font = Font(italic=True, size=9, color="808080")
        sheet.column_dimensions[get_column_letter(index)].width = max(16, len(name) + 4)

    sheet.freeze_panes = "A3"

    notes = workbook.create_sheet("How to use this")
    for row, line in enumerate(
        [
            "Filling this in",
            "",
            "1. One row per tenant. Row 2 is an example — delete it before uploading.",
            "2. Columns marked * are required. A row missing one is reported, not guessed at.",
            "3. 'Property name' must match a property that already exists in RentFlow.",
            "4. Units are created automatically if the unit number is new.",
            "5. Dates are YYYY-MM-DD, for example 2026-01-31.",
            "6. 'Opening balance' is what the tenant already owes you on the day you import.",
            "   Leave it blank or zero if they are up to date.",
            "7. Upload the file, check the preview, then confirm. Nothing is saved until you do.",
        ],
        start=1,
    ):
        cell = notes.cell(row=row, column=1, value=line)
        if row == 1:
            cell.font = Font(bold=True, size=13)
    notes.column_dimensions["A"].width = 90

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal(value: Any, field: str) -> Decimal:
    if value in (None, ""):
        return ZERO
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} is not a number") from exc


def _date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field} is not a date the importer understands (use YYYY-MM-DD)")


def parse(data: bytes) -> tuple[list[dict], list[dict]]:
    """Read the workbook into (valid rows, errors). Nothing touches the database."""
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That file could not be read as an Excel workbook",
        ) from exc

    sheet = workbook[SHEET_NAME] if SHEET_NAME in workbook.sheetnames else workbook.worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The sheet is empty")

    header = [(_text(cell) or "").rstrip("*").strip().lower() for cell in rows[0]]
    missing = [name for name, required, _ in COLUMNS if required and name.lower() not in header]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The file is missing required column(s): {', '.join(missing)}",
        )

    index_of = {name: header.index(name.lower()) for name, _, _ in COLUMNS if name.lower() in header}

    def cell(row: tuple, name: str) -> Any:
        position = index_of.get(name)
        return row[position] if position is not None and position < len(row) else None

    parsed: list[dict] = []
    errors: list[dict] = []
    seen_phones: dict[str, int] = {}

    for number, row in enumerate(rows[1:], start=2):
        if all(value in (None, "") for value in row):
            continue
        if len(parsed) + len(errors) >= MAX_ROWS:
            errors.append({"row": number, "reason": f"Import is limited to {MAX_ROWS} rows per file"})
            break

        try:
            name = _text(cell(row, "Full name"))
            phone_raw = _text(cell(row, "Phone number"))
            if not name or not phone_raw:
                raise ValueError("Full name and phone number are both required")

            phone = normalize_phone(phone_raw)
            if phone in seen_phones:
                raise ValueError(f"Duplicate of row {seen_phones[phone]} — same phone number")
            seen_phones[phone] = number

            property_name = _text(cell(row, "Property name"))
            unit_number = _text(cell(row, "Unit number"))
            if not property_name or not unit_number:
                raise ValueError("Property name and unit number are both required")

            start = _date(cell(row, "Lease start"), "Lease start")
            if start is None:
                raise ValueError("Lease start is required")
            end = _date(cell(row, "Lease end"), "Lease end")
            if end is not None and end <= start:
                raise ValueError("Lease end must be after the lease start")

            rent = _decimal(cell(row, "Monthly rent"), "Monthly rent")
            if rent <= ZERO:
                raise ValueError("Monthly rent must be greater than zero")

            billing_day_raw = cell(row, "Billing day")
            billing_day = int(billing_day_raw) if billing_day_raw not in (None, "") else 1
            if not 1 <= billing_day <= 28:
                raise ValueError("Billing day must be between 1 and 28")

            parsed.append(
                {
                    "row": number,
                    "full_name": name,
                    "phone_number": phone,
                    "email": _text(cell(row, "Email")),
                    "national_id": _text(cell(row, "National ID")),
                    "property_name": property_name,
                    "unit_number": unit_number,
                    "monthly_rent": str(rent),
                    "deposit_amount": str(_decimal(cell(row, "Deposit"), "Deposit")),
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat() if end else None,
                    "billing_day": billing_day,
                    "opening_balance": str(_decimal(cell(row, "Opening balance"), "Opening balance")),
                    "notes": _text(cell(row, "Notes")),
                }
            )
        except ValueError as exc:
            errors.append({"row": number, "reason": str(exc)})

    return parsed, errors


async def validate_against_database(
    db: AsyncSession, context: OrgContext, rows: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Second pass: the things only the database knows — does the property exist,
    is that phone number already a tenant, is the unit already occupied."""
    properties = {
        record.name.strip().lower(): record
        for record in await db.scalars(
            select(Property).where(
                Property.organization_id == context.organization_id,
                Property.is_archived.is_(False),
            )
        )
    }
    existing_phones = {
        phone
        for phone in await db.scalars(
            select(Tenant.phone_number).where(Tenant.organization_id == context.organization_id)
        )
    }

    ready: list[dict] = []
    errors: list[dict] = []

    for row in rows:
        property_record = properties.get(row["property_name"].strip().lower())
        if property_record is None:
            errors.append(
                {
                    "row": row["row"],
                    "reason": f"No property called '{row['property_name']}' — create it first",
                }
            )
            continue

        if row["phone_number"] in existing_phones:
            errors.append(
                {
                    "row": row["row"],
                    "reason": f"{row['phone_number']} already belongs to a tenant in RentFlow",
                }
            )
            continue

        unit = await db.scalar(
            select(Unit).where(
                Unit.property_id == property_record.id,
                Unit.unit_number == row["unit_number"],
                Unit.is_archived.is_(False),
            )
        )
        if unit is not None:
            occupied = await db.scalar(
                select(Tenancy).where(
                    Tenancy.unit_id == unit.id,
                    Tenancy.status.in_(
                        [
                            TenancyStatus.ACTIVE,
                            TenancyStatus.EXPIRING_SOON,
                            TenancyStatus.NOTICE_GIVEN,
                        ]
                    ),
                )
            )
            if occupied is not None:
                errors.append(
                    {
                        "row": row["row"],
                        "reason": f"Unit {row['unit_number']} already has a live tenancy",
                    }
                )
                continue

        ready.append(
            {
                **row,
                "property_id": str(property_record.id),
                "unit_exists": unit is not None,
                "unit_id": str(unit.id) if unit else None,
            }
        )

    return ready, errors


async def commit_rows(db: AsyncSession, context: OrgContext, rows: list[dict]) -> tuple[int, list[dict]]:
    """Create the tenants, units and tenancies. Returns (created, failures).

    Each row is independent: a failure late in the file does not undo the tenants
    already created, which is what makes a partial import usable rather than an
    all-or-nothing gamble on somebody's spreadsheet.
    """
    created = 0
    failures: list[dict] = []

    for row in rows:
        try:
            unit_id = uuid.UUID(row["unit_id"]) if row.get("unit_id") else None
            if unit_id is None:
                unit_reference = await reference_service.generate_reference(
                    db, Unit, context.organization_id, "UNT"
                )
                unit = Unit(
                    organization_id=context.organization_id,
                    property_id=uuid.UUID(row["property_id"]),
                    reference_code=unit_reference,
                    unit_number=row["unit_number"],
                    monthly_rent=Decimal(row["monthly_rent"]),
                    deposit_amount=Decimal(row["deposit_amount"]),
                    status=UnitStatus.OCCUPIED,
                )
                db.add(unit)
                await db.flush()
            else:
                existing_unit = await db.get(Unit, unit_id)
                if existing_unit is None:
                    raise ValueError("The unit was removed between preview and import")
                unit = existing_unit
                unit.status = UnitStatus.OCCUPIED

            tenant_reference = await reference_service.generate_reference(
                db, Tenant, context.organization_id, "TNT"
            )
            tenant = Tenant(
                organization_id=context.organization_id,
                reference_code=tenant_reference,
                full_name=row["full_name"],
                phone_number=row["phone_number"],
                email=row["email"],
                national_id=row["national_id"],
                notes=row["notes"],
            )
            db.add(tenant)
            await db.flush()

            tenancy_reference = await reference_service.generate_reference(
                db, Tenancy, context.organization_id, "TCY"
            )
            tenancy = Tenancy(
                organization_id=context.organization_id,
                reference_code=tenancy_reference,
                tenant_id=tenant.id,
                unit_id=unit.id,
                start_date=date.fromisoformat(row["start_date"]),
                end_date=date.fromisoformat(row["end_date"]) if row["end_date"] else None,
                is_open_ended=row["end_date"] is None,
                monthly_rent=Decimal(row["monthly_rent"]),
                deposit_amount=Decimal(row["deposit_amount"]),
                billing_day=row["billing_day"],
                payment_method=PaymentMethodPreference.MPESA,
                status=TenancyStatus.ACTIVE,
            )
            db.add(tenancy)
            await db.flush()

            opening = Decimal(row["opening_balance"])
            if opening > ZERO:
                await _record_opening_balance(db, context, tenancy, opening)

            created += 1
        except Exception as exc:  # noqa: BLE001 — one bad row must not sink the file
            failures.append({"row": row["row"], "reason": str(exc)[:300]})

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="bulk.tenant_import",
        entity_type="organization",
        entity_id=context.organization_id,
        actor=context.user,
        summary=(
            f"Imported {created} tenant(s) from a spreadsheet"
            + (f", {len(failures)} row(s) failed" if failures else "")
        ),
    )
    await db.commit()
    return created, failures


async def _record_opening_balance(
    db: AsyncSession, context: OrgContext, tenancy: Tenancy, amount: Decimal
) -> None:
    """What the tenant already owed on the day they were imported (US-076).

    Recorded as a real invoice rather than a balance field, so the arrears report,
    the statements and the demand letters all see it without special cases.
    """
    from app.models.billing import Invoice, InvoiceLineItem, InvoiceStatus, LineItemKind

    today = date.today()
    reference = await reference_service.generate_invoice_reference(
        db, Invoice, context.organization_id, today
    )
    invoice = Invoice(
        organization_id=context.organization_id,
        tenancy_id=tenancy.id,
        reference_code=reference,
        period_start=today,
        period_end=today,
        issue_date=today,
        due_date=today,
        status=InvoiceStatus.OVERDUE,
        total=amount,
        line_items=[
            InvoiceLineItem(
                kind=LineItemKind.ARREARS,
                description="Balance brought forward at import",
                quantity=Decimal("1"),
                unit_amount=amount,
                amount=amount,
            )
        ],
    )
    db.add(invoice)
    await db.flush()
