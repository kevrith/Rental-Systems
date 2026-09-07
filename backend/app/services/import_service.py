"""Excel import for bulk onboarding (US-072, US-076), and the templates it expects.

Importing someone else's spreadsheet is mostly an exercise in refusing to guess.
Every row is validated in full before anything is written, the operator sees a
preview of exactly what will be created, and rows that cannot be understood are
reported by row number with the reason — never silently skipped, and never
half-imported.

Four kinds of sheet, because a landlord migrating off a spreadsheet has four
different things to bring across and they arrive in a fixed order:

  * **Properties** — the buildings. Nothing else can be imported first.
  * **Units** — the lettable spaces inside them.
  * **Tenants** — people, their tenancy, and what they owed on day one. This
    was the original importer and still creates a missing unit on the fly, so a
    landlord with a simple portfolio can skip the first two sheets entirely.
  * **Payments** — what has already been paid. Without this an imported
    tenant's history starts at zero, and every statement and receipt book
    understates what they have actually paid over the years.

The generic machinery — header matching, blank-row skipping, per-row error
reporting, the row cap — is written once in `_read_rows` and is the same for
all four; each kind supplies only its columns and its row parser.

Templates are generated rather than shipped as files so they can never drift
from the parser that reads them back.
"""

import enum
import io
import uuid
from collections.abc import Callable, Iterator
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.models.billing import Payment, PaymentMethod, PaymentStatus
from app.models.property import Property, PropertyType, Unit, UnitStatus
from app.models.tenant import PaymentMethodPreference, Tenancy, TenancyStatus, Tenant
from app.services import audit_service, reference_service
from app.services.notifications import normalize_phone

ZERO = Decimal("0.00")

SHEET_NAME = "Tenants"
MAX_ROWS = 2000


class ImportKind(str, enum.Enum):
    PROPERTIES = "properties"
    UNITS = "units"
    TENANTS = "tenants"
    PAYMENTS = "payments"


# (column header, required, hint shown in the template's second row)
Column = tuple[str, bool, str]

COLUMNS: tuple[Column, ...] = (
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

PROPERTY_COLUMNS: tuple[Column, ...] = (
    ("Property name", True, "Acacia Court"),
    ("Type", False, "residential, commercial, mixed_use (default residential)"),
    ("Address", True, "Kiambu Road, Runda"),
    ("County", False, "Nairobi"),
    ("Sub county", False, "Westlands"),
    ("Water rate", False, "KES per unit consumed, e.g. 150"),
    ("Electricity rate", False, "KES per unit consumed, e.g. 25"),
    ("Grace period days", False, "Days after the due date before a late fee (default 5)"),
    ("Description", False, ""),
)

UNIT_COLUMNS: tuple[Column, ...] = (
    ("Property name", True, "Must match a property already in RentFlow"),
    ("Unit number", True, "A1"),
    ("Unit type", False, "Bedsitter, 1 bedroom, Shop"),
    ("Bedrooms", False, "2"),
    ("Bathrooms", False, "1"),
    ("Floor", False, "Ground, 1, 2"),
    ("Size sqm", False, "45"),
    ("Monthly rent", True, "25000"),
    ("Deposit", False, "25000"),
    ("Status", False, "vacant or occupied (default vacant)"),
)

PAYMENT_COLUMNS: tuple[Column, ...] = (
    ("Tenant phone", True, "+254712345678 — must already be a tenant in RentFlow"),
    ("Amount", True, "25000"),
    ("Payment date", True, "2026-01-05"),
    ("Method", False, "mpesa, cash, bank_transfer, cheque (default mpesa)"),
    ("Reference", False, "M-Pesa code or bank reference"),
    ("Notes", False, ""),
)

HEADERS = [column[0] for column in COLUMNS]

SHEET_NAMES: dict[ImportKind, str] = {
    ImportKind.PROPERTIES: "Properties",
    ImportKind.UNITS: "Units",
    ImportKind.TENANTS: SHEET_NAME,
    ImportKind.PAYMENTS: "Payments",
}

COLUMNS_FOR: dict[ImportKind, tuple[Column, ...]] = {
    ImportKind.PROPERTIES: PROPERTY_COLUMNS,
    ImportKind.UNITS: UNIT_COLUMNS,
    ImportKind.TENANTS: COLUMNS,
    ImportKind.PAYMENTS: PAYMENT_COLUMNS,
}

INSTRUCTIONS: dict[ImportKind, list[str]] = {
    ImportKind.PROPERTIES: [
        "One row per building or site. Row 2 is an example — delete it before uploading.",
        "Columns marked * are required. A row missing one is reported, not guessed at.",
        "A property name that already exists in RentFlow is reported rather than duplicated.",
        "Utility rates are what you charge per unit consumed, and price meter readings.",
        "Import properties first, then units, then tenants, then historical payments.",
    ],
    ImportKind.UNITS: [
        "One row per lettable unit. Row 2 is an example — delete it before uploading.",
        "'Property name' must match a property that already exists in RentFlow.",
        "A unit number that already exists on that property is reported rather than duplicated.",
        "Leave 'Status' blank for vacant. Importing a tenant later marks their unit occupied.",
    ],
    ImportKind.TENANTS: [
        "One row per tenant. Row 2 is an example — delete it before uploading.",
        "Columns marked * are required. A row missing one is reported, not guessed at.",
        "'Property name' must match a property that already exists in RentFlow.",
        "Units are created automatically if the unit number is new.",
        "Dates are YYYY-MM-DD, for example 2026-01-31.",
        "'Opening balance' is what the tenant already owes you on the day you import.",
        "   Leave it blank or zero if they are up to date.",
    ],
    ImportKind.PAYMENTS: [
        "One row per payment already received. Row 2 is an example — delete it before uploading.",
        "'Tenant phone' must match a tenant already in RentFlow, so import tenants first.",
        "Each payment is allocated against that tenant's oldest unpaid invoice, exactly as a",
        "   payment recorded today would be.",
        "No receipt is sent and no tenant is notified — this is history, not a new payment.",
        "A payment whose reference already exists in RentFlow is reported, never banked twice.",
    ],
}


# ------------------------------------------------------------------ templates


def build_template(kind: ImportKind = ImportKind.TENANTS) -> bytes:
    """The downloadable import template (US-076's format, used from Sprint 15)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    columns = COLUMNS_FOR[kind]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_NAMES[kind]

    header_fill = PatternFill("solid", fgColor="1F3A93")
    for index, (name, required, hint) in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=index, value=name + ("*" if required else ""))
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")

        hint_cell = sheet.cell(row=2, column=index, value=hint)
        hint_cell.font = Font(italic=True, size=9, color="808080")
        sheet.column_dimensions[get_column_letter(index)].width = max(16, len(name) + 4)

    sheet.freeze_panes = "A3"

    notes = workbook.create_sheet("How to use this")
    lines = ["Filling this in", ""]
    for position, instruction in enumerate(INSTRUCTIONS[kind], start=1):
        # A continuation line (already indented) belongs to the step above it.
        lines.append(instruction if instruction.startswith("   ") else f"{position}. {instruction}")
    lines.append(
        f"{len(INSTRUCTIONS[kind]) + 1}. Upload the file, check the preview, then confirm. "
        "Nothing is saved until you do."
    )

    for row, line in enumerate(lines, start=1):
        cell = notes.cell(row=row, column=1, value=line)
        if row == 1:
            cell.font = Font(bold=True, size=13)
    notes.column_dimensions["A"].width = 90

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ------------------------------------------------------------- cell coercion


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


def _int(value: Any, field: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is not a whole number") from exc


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


def _enum(value: Any, field: str, options: type[enum.Enum], default: Any) -> Any:
    if value in (None, ""):
        return default
    candidate = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    for member in options:
        if member.value == candidate:
            return member
    allowed = ", ".join(member.value for member in options)
    raise ValueError(f"{field} must be one of: {allowed}")


# -------------------------------------------------------- sheet reading


CellGetter = Callable[[str], Any]


def _read_rows(data: bytes, kind: ImportKind) -> Iterator[tuple[int, CellGetter]]:
    """Yield `(row number, cell getter)` for every non-blank data row.

    Columns are located by header name rather than position, so a landlord who
    reordered or inserted columns in their own copy still imports cleanly. A
    missing *required* header is a whole-file error — nothing is more likely to
    produce silently wrong data than guessing which column the rent was in.
    """
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That file could not be read as an Excel workbook",
        ) from exc

    sheet_name = SHEET_NAMES[kind]
    columns = COLUMNS_FOR[kind]
    sheet = workbook[sheet_name] if sheet_name in workbook.sheetnames else workbook.worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The sheet is empty")

    header = [(_text(cell) or "").rstrip("*").strip().lower() for cell in rows[0]]
    missing = [name for name, required, _ in columns if required and name.lower() not in header]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The file is missing required column(s): {', '.join(missing)}",
        )

    index_of = {name: header.index(name.lower()) for name, _, _ in columns if name.lower() in header}

    for number, row in enumerate(rows[1:], start=2):
        if all(value in (None, "") for value in row):
            continue

        def cell(name: str, row: tuple = row) -> Any:
            position = index_of.get(name)
            return row[position] if position is not None and position < len(row) else None

        yield number, cell


def _parse_sheet(
    data: bytes,
    kind: ImportKind,
    row_parser: Callable[[int, CellGetter, dict[str, int]], dict],
) -> tuple[list[dict], list[dict]]:
    """Run `row_parser` over every row, collecting successes and failures.

    `row_parser` raises `ValueError` for a row it cannot understand; the
    message becomes what the operator reads next to that row number. The third
    argument is a scratch dict the parser can use to spot duplicates *within*
    the file, which no amount of database validation would catch.
    """
    parsed: list[dict] = []
    errors: list[dict] = []
    seen: dict[str, int] = {}

    for number, cell in _read_rows(data, kind):
        if len(parsed) + len(errors) >= MAX_ROWS:
            errors.append({"row": number, "reason": f"Import is limited to {MAX_ROWS} rows per file"})
            break
        try:
            parsed.append(row_parser(number, cell, seen))
        except ValueError as exc:
            errors.append({"row": number, "reason": str(exc)})

    return parsed, errors


# ------------------------------------------------------------------- tenants


def _parse_tenant_row(number: int, cell: CellGetter, seen: dict[str, int]) -> dict:
    name = _text(cell("Full name"))
    phone_raw = _text(cell("Phone number"))
    if not name or not phone_raw:
        raise ValueError("Full name and phone number are both required")

    phone = normalize_phone(phone_raw)
    if phone in seen:
        raise ValueError(f"Duplicate of row {seen[phone]} — same phone number")
    seen[phone] = number

    property_name = _text(cell("Property name"))
    unit_number = _text(cell("Unit number"))
    if not property_name or not unit_number:
        raise ValueError("Property name and unit number are both required")

    start = _date(cell("Lease start"), "Lease start")
    if start is None:
        raise ValueError("Lease start is required")
    end = _date(cell("Lease end"), "Lease end")
    if end is not None and end <= start:
        raise ValueError("Lease end must be after the lease start")

    rent = _decimal(cell("Monthly rent"), "Monthly rent")
    if rent <= ZERO:
        raise ValueError("Monthly rent must be greater than zero")

    billing_day_raw = cell("Billing day")
    billing_day = int(billing_day_raw) if billing_day_raw not in (None, "") else 1
    if not 1 <= billing_day <= 28:
        raise ValueError("Billing day must be between 1 and 28")

    return {
        "row": number,
        "full_name": name,
        "phone_number": phone,
        "email": _text(cell("Email")),
        "national_id": _text(cell("National ID")),
        "property_name": property_name,
        "unit_number": unit_number,
        "monthly_rent": str(rent),
        "deposit_amount": str(_decimal(cell("Deposit"), "Deposit")),
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end else None,
        "billing_day": billing_day,
        "opening_balance": str(_decimal(cell("Opening balance"), "Opening balance")),
        "notes": _text(cell("Notes")),
    }


def parse(data: bytes, kind: ImportKind = ImportKind.TENANTS) -> tuple[list[dict], list[dict]]:
    """Read the workbook into (valid rows, errors). Nothing touches the database."""
    return _parse_sheet(data, kind, _ROW_PARSERS[kind])


async def validate_against_database(
    db: AsyncSession, context: OrgContext, rows: list[dict], kind: ImportKind = ImportKind.TENANTS
) -> tuple[list[dict], list[dict]]:
    """Second pass: the things only the database knows."""
    return await _VALIDATORS[kind](db, context, rows)


async def commit_rows(
    db: AsyncSession, context: OrgContext, rows: list[dict], kind: ImportKind = ImportKind.TENANTS
) -> tuple[int, list[dict]]:
    """Write the confirmed rows. Returns (created, failures)."""
    return await _COMMITTERS[kind](db, context, rows)


async def _validate_tenants(
    db: AsyncSession, context: OrgContext, rows: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Does the property exist, is that phone number already a tenant, is the
    unit already occupied."""
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


async def _commit_tenants(db: AsyncSession, context: OrgContext, rows: list[dict]) -> tuple[int, list[dict]]:
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


# ---------------------------------------------------------------- properties


def _parse_property_row(number: int, cell: CellGetter, seen: dict[str, int]) -> dict:
    name = _text(cell("Property name"))
    address = _text(cell("Address"))
    if not name or not address:
        raise ValueError("Property name and address are both required")

    key = name.lower()
    if key in seen:
        raise ValueError(f"Duplicate of row {seen[key]} — same property name")
    seen[key] = number

    property_type = _enum(cell("Type"), "Type", PropertyType, PropertyType.RESIDENTIAL)
    grace = _int(cell("Grace period days"), "Grace period days")
    if grace is not None and not 0 <= grace <= 90:
        raise ValueError("Grace period days must be between 0 and 90")

    water = _decimal(cell("Water rate"), "Water rate")
    electricity = _decimal(cell("Electricity rate"), "Electricity rate")
    if water < ZERO or electricity < ZERO:
        raise ValueError("Utility rates cannot be negative")

    return {
        "row": number,
        "name": name,
        "property_type": property_type.value,
        "address": address,
        "county": _text(cell("County")),
        "sub_county": _text(cell("Sub county")),
        # Zero and "not configured" are different: a blank rate means readings
        # are captured but not priced, which is not the same as free water.
        "water_rate_per_unit": str(water) if water > ZERO else None,
        "electricity_rate_per_unit": str(electricity) if electricity > ZERO else None,
        "grace_period_days": grace if grace is not None else 5,
        "description": _text(cell("Description")),
    }


async def _validate_properties(
    db: AsyncSession, context: OrgContext, rows: list[dict]
) -> tuple[list[dict], list[dict]]:
    existing = {
        name.strip().lower()
        for name in await db.scalars(
            select(Property.name).where(
                Property.organization_id == context.organization_id,
                Property.is_archived.is_(False),
            )
        )
    }

    ready: list[dict] = []
    errors: list[dict] = []
    for row in rows:
        if row["name"].strip().lower() in existing:
            errors.append({"row": row["row"], "reason": f"'{row['name']}' already exists in RentFlow"})
            continue
        ready.append(row)
    return ready, errors


async def _commit_properties(
    db: AsyncSession, context: OrgContext, rows: list[dict]
) -> tuple[int, list[dict]]:
    created = 0
    failures: list[dict] = []

    for row in rows:
        try:
            reference = await reference_service.generate_reference(
                db, Property, context.organization_id, "PRP"
            )
            db.add(
                Property(
                    organization_id=context.organization_id,
                    reference_code=reference,
                    name=row["name"],
                    property_type=PropertyType(row["property_type"]),
                    address=row["address"],
                    county=row["county"],
                    sub_county=row["sub_county"],
                    water_rate_per_unit=(
                        Decimal(row["water_rate_per_unit"]) if row["water_rate_per_unit"] else None
                    ),
                    electricity_rate_per_unit=(
                        Decimal(row["electricity_rate_per_unit"])
                        if row["electricity_rate_per_unit"]
                        else None
                    ),
                    grace_period_days=row["grace_period_days"],
                    description=row["description"],
                )
            )
            await db.flush()
            created += 1
        except Exception as exc:  # noqa: BLE001 — one bad row must not sink the file
            failures.append({"row": row["row"], "reason": str(exc)[:300]})

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="bulk.property_import",
        entity_type="organization",
        entity_id=context.organization_id,
        actor=context.user,
        summary=(
            f"Imported {created} propert{'y' if created == 1 else 'ies'} from a spreadsheet"
            + (f", {len(failures)} row(s) failed" if failures else "")
        ),
    )
    await db.commit()
    return created, failures


# --------------------------------------------------------------------- units


def _parse_unit_row(number: int, cell: CellGetter, seen: dict[str, int]) -> dict:
    property_name = _text(cell("Property name"))
    unit_number = _text(cell("Unit number"))
    if not property_name or not unit_number:
        raise ValueError("Property name and unit number are both required")

    key = f"{property_name.lower()}::{unit_number.lower()}"
    if key in seen:
        raise ValueError(f"Duplicate of row {seen[key]} — same unit on the same property")
    seen[key] = number

    rent = _decimal(cell("Monthly rent"), "Monthly rent")
    if rent < ZERO:
        raise ValueError("Monthly rent cannot be negative")

    status_value = _enum(cell("Status"), "Status", UnitStatus, UnitStatus.VACANT)
    if status_value == UnitStatus.OCCUPIED:
        # Occupancy is a consequence of a tenancy, not a field to assert. A unit
        # imported as occupied with nobody in it breaks every occupancy figure
        # on the dashboard, so say so rather than quietly accepting it.
        raise ValueError("Import units as vacant — a unit becomes occupied when its tenant is imported")

    size = cell("Size sqm")
    return {
        "row": number,
        "property_name": property_name,
        "unit_number": unit_number,
        "unit_type": _text(cell("Unit type")),
        "bedrooms": _int(cell("Bedrooms"), "Bedrooms"),
        "bathrooms": _int(cell("Bathrooms"), "Bathrooms"),
        "floor": _text(cell("Floor")),
        "size_sqm": float(_decimal(size, "Size sqm")) if size not in (None, "") else None,
        "monthly_rent": str(rent),
        "deposit_amount": str(_decimal(cell("Deposit"), "Deposit")),
    }


async def _validate_units(
    db: AsyncSession, context: OrgContext, rows: list[dict]
) -> tuple[list[dict], list[dict]]:
    properties = {
        record.name.strip().lower(): record
        for record in await db.scalars(
            select(Property).where(
                Property.organization_id == context.organization_id,
                Property.is_archived.is_(False),
            )
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
                    "reason": f"No property called '{row['property_name']}' — import properties first",
                }
            )
            continue

        clash = await db.scalar(
            select(Unit.id).where(
                Unit.property_id == property_record.id,
                Unit.unit_number == row["unit_number"],
            )
        )
        if clash is not None:
            errors.append(
                {
                    "row": row["row"],
                    "reason": f"Unit {row['unit_number']} already exists on {property_record.name}",
                }
            )
            continue

        ready.append({**row, "property_id": str(property_record.id)})
    return ready, errors


async def _commit_units(db: AsyncSession, context: OrgContext, rows: list[dict]) -> tuple[int, list[dict]]:
    created = 0
    failures: list[dict] = []

    for row in rows:
        try:
            reference = await reference_service.generate_reference(db, Unit, context.organization_id, "UNT")
            db.add(
                Unit(
                    organization_id=context.organization_id,
                    property_id=uuid.UUID(row["property_id"]),
                    reference_code=reference,
                    unit_number=row["unit_number"],
                    unit_type=row["unit_type"],
                    bedrooms=row["bedrooms"],
                    bathrooms=row["bathrooms"],
                    floor=row["floor"],
                    size_sqm=row["size_sqm"],
                    monthly_rent=Decimal(row["monthly_rent"]),
                    deposit_amount=Decimal(row["deposit_amount"]),
                    status=UnitStatus.VACANT,
                )
            )
            await db.flush()
            created += 1
        except Exception as exc:  # noqa: BLE001 — one bad row must not sink the file
            failures.append({"row": row["row"], "reason": str(exc)[:300]})

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="bulk.unit_import",
        entity_type="organization",
        entity_id=context.organization_id,
        actor=context.user,
        summary=(
            f"Imported {created} unit(s) from a spreadsheet"
            + (f", {len(failures)} row(s) failed" if failures else "")
        ),
    )
    await db.commit()
    return created, failures


# ------------------------------------------------------------------ payments


def _parse_payment_row(number: int, cell: CellGetter, seen: dict[str, int]) -> dict:
    phone_raw = _text(cell("Tenant phone"))
    if not phone_raw:
        raise ValueError("Tenant phone is required")
    phone = normalize_phone(phone_raw)

    amount = _decimal(cell("Amount"), "Amount")
    if amount <= ZERO:
        raise ValueError("Amount must be greater than zero")

    paid_on = _date(cell("Payment date"), "Payment date")
    if paid_on is None:
        raise ValueError("Payment date is required")
    if paid_on > date.today():
        raise ValueError("Payment date is in the future — this sheet is for payments already received")

    method = _enum(cell("Method"), "Method", PaymentMethod, PaymentMethod.MPESA)
    reference = _text(cell("Reference"))
    if reference:
        key = f"{method.value}::{reference.lower()}"
        if key in seen:
            raise ValueError(f"Duplicate of row {seen[key]} — same reference")
        seen[key] = number

    return {
        "row": number,
        "phone_number": phone,
        "amount": str(amount),
        "payment_date": paid_on.isoformat(),
        "method": method.value,
        "reference": reference,
        "notes": _text(cell("Notes")),
    }


async def _validate_payments(
    db: AsyncSession, context: OrgContext, rows: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Each payment needs a tenant with a tenancy, and must not already exist.

    The tenancy is resolved here rather than at commit time so the preview can
    show the operator which tenant each row will land on — the single most
    useful thing to check before importing years of somebody's payment history.
    """
    tenants = {
        record.phone_number: record
        for record in await db.scalars(
            select(Tenant).where(
                Tenant.organization_id == context.organization_id,
                Tenant.is_archived.is_(False),
            )
        )
    }

    ready: list[dict] = []
    errors: list[dict] = []
    for row in rows:
        tenant = tenants.get(row["phone_number"])
        if tenant is None:
            errors.append(
                {
                    "row": row["row"],
                    "reason": f"No tenant with phone {row['phone_number']} — import tenants first",
                }
            )
            continue

        tenancy = await db.scalar(
            select(Tenancy).where(Tenancy.tenant_id == tenant.id).order_by(Tenancy.start_date.desc()).limit(1)
        )
        if tenancy is None:
            errors.append({"row": row["row"], "reason": f"{tenant.full_name} has no tenancy to credit"})
            continue

        if row["reference"]:
            column = (
                Payment.mpesa_receipt
                if row["method"] == PaymentMethod.MPESA.value
                else Payment.bank_reference
            )
            clash = await db.scalar(
                select(Payment.id).where(
                    Payment.organization_id == context.organization_id,
                    column == row["reference"],
                )
            )
            if clash is not None:
                errors.append(
                    {
                        "row": row["row"],
                        "reason": f"Reference {row['reference']} is already recorded in RentFlow",
                    }
                )
                continue

        ready.append(
            {
                **row,
                "tenant_name": tenant.full_name,
                "tenancy_id": str(tenancy.id),
                "tenancy_reference": tenancy.reference_code,
            }
        )
    return ready, errors


async def _commit_payments(db: AsyncSession, context: OrgContext, rows: list[dict]) -> tuple[int, list[dict]]:
    """Bank each historical payment against the tenant's oldest open invoice.

    Deliberately *not* routed through `payment_service.record_cash_payment`.
    That path issues a receipt, WhatsApps the tenant, runs fraud detection and
    fires a webhook — all correct for money arriving today, all wrong for a
    payment from 2023 being typed into a migration. What is shared is the
    allocation rule, so an imported payment settles invoices exactly as a live
    one would.
    """

    created = 0
    failures: list[dict] = []

    for row in rows:
        try:
            # A savepoint per row. Without one, an integrity error on row 40
            # poisons the session and the rollback that clears it would discard
            # the 39 payments already written — which is the opposite of the
            # "one bad row must not sink the file" contract every other
            # importer here keeps.
            async with db.begin_nested():
                await _commit_one_payment(db, context, row)
            created += 1
        except Exception as exc:  # noqa: BLE001 — one bad row must not sink the file
            failures.append({"row": row["row"], "reason": str(exc)[:300]})

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="bulk.payment_import",
        entity_type="organization",
        entity_id=context.organization_id,
        actor=context.user,
        summary=(
            f"Imported {created} historical payment(s) from a spreadsheet"
            + (f", {len(failures)} row(s) failed" if failures else "")
        ),
    )
    await db.commit()
    return created, failures


async def _commit_one_payment(db: AsyncSession, context: OrgContext, row: dict) -> None:
    """Bank one imported payment and allocate it. Runs inside a savepoint."""
    from app.services import invoice_service

    paid_on = date.fromisoformat(row["payment_date"])
    method = PaymentMethod(row["method"])
    reference = await reference_service.generate_reference(db, Payment, context.organization_id, "PMT")
    payment = Payment(
        organization_id=context.organization_id,
        reference_code=reference,
        tenancy_id=uuid.UUID(row["tenancy_id"]),
        amount=Decimal(row["amount"]),
        method=method,
        status=PaymentStatus.CONFIRMED,
        payment_date=paid_on,
        paid_at=datetime.combine(paid_on, datetime.min.time()),
        recorded_by_id=context.user.id,
        notes=row["notes"],
        mpesa_receipt=row["reference"] if method == PaymentMethod.MPESA else None,
        bank_reference=row["reference"] if method != PaymentMethod.MPESA else None,
    )
    db.add(payment)
    await db.flush()

    remaining = Decimal(payment.amount)
    for invoice in await invoice_service.open_invoices_for_tenancy(db, payment.tenancy_id):
        if remaining <= ZERO:
            break
        owed = Decimal(invoice.total) - Decimal(invoice.amount_paid)
        if owed <= ZERO:
            continue
        applied = min(owed, remaining)
        invoice.amount_paid = Decimal(invoice.amount_paid) + applied
        invoice.status = invoice_service.recalculate_status(invoice)
        remaining -= applied
        if payment.invoice_id is None:
            payment.invoice_id = invoice.id
    await db.flush()


# ------------------------------------------------------------------ dispatch

_ROW_PARSERS: dict[ImportKind, Callable[[int, CellGetter, dict[str, int]], dict]] = {
    ImportKind.PROPERTIES: _parse_property_row,
    ImportKind.UNITS: _parse_unit_row,
    ImportKind.TENANTS: _parse_tenant_row,
    ImportKind.PAYMENTS: _parse_payment_row,
}

_VALIDATORS: dict[ImportKind, Any] = {
    ImportKind.PROPERTIES: _validate_properties,
    ImportKind.UNITS: _validate_units,
    ImportKind.TENANTS: _validate_tenants,
    ImportKind.PAYMENTS: _validate_payments,
}

_COMMITTERS: dict[ImportKind, Any] = {
    ImportKind.PROPERTIES: _commit_properties,
    ImportKind.UNITS: _commit_units,
    ImportKind.TENANTS: _commit_tenants,
    ImportKind.PAYMENTS: _commit_payments,
}
