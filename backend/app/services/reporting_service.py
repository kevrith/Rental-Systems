"""Custom report builder and the automatic monthly summary — Sprint 21
(US-093/094).

The report builder deliberately does not duplicate `export_service`'s
row-shaping functions. It calls the same `BUILDERS` dict, then filters and
projects the resulting dicts in Python. Organisation-scale row counts here are
in the hundreds, not millions, so an in-memory filter is the honest amount of
engineering for a solo-landlord product — the alternative is a bespoke
per-dataset SQL filter builder for a feature most accounts will use to build a
handful of saved reports.

The monthly summary is the automatic, unconfigurable report every account
gets: built the same way `owner_statement_service.py` builds an owner's
statement — reusing `dashboard_service`'s period-bound aggregates and
`arrears_service`'s current-snapshot arrears, rather than re-deriving either.
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.file import FileCategory, StoredFile
from app.models.notification import NotificationChannel, NotificationType
from app.models.operations import BILLABLE_STATUSES, MaintenanceRequest
from app.models.organization import Organization, ReportDeliveryChannel
from app.models.reporting import MonthlyReport, ReportDefinition, ReportSchedule
from app.models.user import User, UserRole
from app.models.vacancy import ExportKind
from app.schemas.reporting import ReportDefinitionCreate, ReportDefinitionUpdate
from app.services import (
    arrears_service,
    audit_service,
    dashboard_service,
    export_service,
    file_service,
    notification_service,
    pdf_service,
    property_service,
)

logger = logging.getLogger("rentflow.reporting")

ZERO = Decimal("0.00")

# (key, label, type) — must stay in sync with the dict keys export_service's
# row-shaping functions return for each dataset. `type` drives the report
# builder's field picker (which filter widget to show) on the frontend; it is
# metadata only and is not enforced server-side.
DATASET_FIELDS: dict[ExportKind, list[tuple[str, str, str]]] = {
    ExportKind.TENANTS: [
        ("Reference", "Reference", "string"),
        ("Full name", "Full name", "string"),
        ("Phone", "Phone", "string"),
        ("Email", "Email", "string"),
        ("National ID", "National ID", "string"),
        ("Employer", "Employer", "string"),
        ("Occupation", "Occupation", "string"),
        ("Monthly income", "Monthly income", "number"),
        ("Emergency contact", "Emergency contact", "string"),
        ("Emergency phone", "Emergency phone", "string"),
        ("Archived", "Archived", "bool"),
        ("Added on", "Added on", "date"),
    ],
    ExportKind.TENANCIES: [
        ("Reference", "Reference", "string"),
        ("Tenant", "Tenant", "string"),
        ("Phone", "Phone", "string"),
        ("Property", "Property", "string"),
        ("Unit", "Unit", "string"),
        ("Status", "Status", "enum"),
        ("Start", "Start", "date"),
        ("End", "End", "date"),
        ("Open ended", "Open ended", "bool"),
        ("Monthly rent", "Monthly rent", "number"),
        ("Deposit", "Deposit", "number"),
        ("Billing day", "Billing day", "number"),
        ("Notice period (days)", "Notice period (days)", "number"),
    ],
    ExportKind.PAYMENTS: [
        ("Reference", "Reference", "string"),
        ("Date", "Date", "date"),
        ("Tenant", "Tenant", "string"),
        ("Property", "Property", "string"),
        ("Unit", "Unit", "string"),
        ("Amount", "Amount", "number"),
        ("Method", "Method", "enum"),
        ("Status", "Status", "enum"),
        ("M-Pesa code", "M-Pesa code", "string"),
        ("Recorded on", "Recorded on", "date"),
    ],
    ExportKind.PROPERTIES: [
        ("Reference", "Reference", "string"),
        ("Name", "Name", "string"),
        ("Type", "Type", "enum"),
        ("Address", "Address", "string"),
        ("County", "County", "string"),
        ("Water rate", "Water rate", "number"),
        ("Electricity rate", "Electricity rate", "number"),
        ("Grace period (days)", "Grace period (days)", "number"),
        ("Maintenance budget", "Maintenance budget", "number"),
        ("Archived", "Archived", "bool"),
    ],
    ExportKind.UNITS: [
        ("Reference", "Reference", "string"),
        ("Property", "Property", "string"),
        ("Unit", "Unit", "string"),
        ("Type", "Type", "enum"),
        ("Use class", "Use class", "enum"),
        ("Floor", "Floor", "number"),
        ("Size (sqm)", "Size (sqm)", "number"),
        ("Bedrooms", "Bedrooms", "number"),
        ("Bathrooms", "Bathrooms", "number"),
        ("Parking bays", "Parking bays", "number"),
        ("Monthly rent", "Monthly rent", "number"),
        ("Deposit", "Deposit", "number"),
        ("Status", "Status", "enum"),
    ],
    ExportKind.INVOICES: [
        ("Reference", "Reference", "string"),
        ("Issued", "Issued", "date"),
        ("Due", "Due", "date"),
        ("Tenant", "Tenant", "string"),
        ("Property", "Property", "string"),
        ("Unit", "Unit", "string"),
        ("Period start", "Period start", "date"),
        ("Period end", "Period end", "date"),
        ("Total", "Total", "number"),
        ("Paid", "Paid", "number"),
        ("Balance", "Balance", "number"),
        ("Status", "Status", "enum"),
    ],
}

DATASET_LABELS: dict[ExportKind, str] = {
    ExportKind.TENANTS: "Tenants",
    ExportKind.TENANCIES: "Tenancies",
    ExportKind.PAYMENTS: "Payments",
    ExportKind.PROPERTIES: "Properties",
    ExportKind.UNITS: "Units",
    ExportKind.INVOICES: "Invoices",
}


def dataset_fields(dataset: ExportKind) -> list[dict[str, str]]:
    return [{"key": key, "label": label, "type": kind} for key, label, kind in DATASET_FIELDS[dataset]]


async def create_definition(
    db: AsyncSession, context: OrgContext, payload: ReportDefinitionCreate, request: Request | None = None
) -> ReportDefinition:
    definition = ReportDefinition(
        organization_id=context.organization_id,
        created_by_id=context.user.id,
        **payload.model_dump(),
    )
    db.add(definition)
    await db.flush()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="report.created",
        entity_type="report_definition",
        entity_id=definition.id,
        actor=context.user,
        summary=f"Created report “{definition.name}”",
        request=request,
    )
    await db.commit()
    await db.refresh(definition)
    return definition


async def get_definition(db: AsyncSession, context: OrgContext, definition_id: uuid.UUID) -> ReportDefinition:
    return assert_in_org(await db.get(ReportDefinition, definition_id), context, label="report")


async def list_definitions(db: AsyncSession, context: OrgContext) -> list[ReportDefinition]:
    return list(
        await db.scalars(
            select(ReportDefinition)
            .where(ReportDefinition.organization_id == context.organization_id)
            .order_by(ReportDefinition.created_at.desc())
        )
    )


async def update_definition(
    db: AsyncSession,
    context: OrgContext,
    definition_id: uuid.UUID,
    payload: ReportDefinitionUpdate,
    request: Request | None = None,
) -> ReportDefinition:
    definition = await get_definition(db, context, definition_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(definition, field, value)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="report.updated",
        entity_type="report_definition",
        entity_id=definition.id,
        actor=context.user,
        summary=f"Updated report “{definition.name}”",
        request=request,
    )
    await db.commit()
    await db.refresh(definition)
    return definition


async def delete_definition(
    db: AsyncSession, context: OrgContext, definition_id: uuid.UUID, request: Request | None = None
) -> None:
    definition = await get_definition(db, context, definition_id)
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="report.deleted",
        entity_type="report_definition",
        entity_id=definition.id,
        actor=context.user,
        summary=f"Deleted report “{definition.name}”",
        request=request,
    )
    await db.delete(definition)
    await db.commit()


async def execute(
    db: AsyncSession,
    context: OrgContext,
    *,
    dataset: ExportKind,
    fields: list[str],
    filters: dict[str, list[str]] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Run a report definition (or an unsaved preview) and return projected rows."""
    raw_rows = await export_service.BUILDERS[dataset](db, context, date_from=date_from, date_to=date_to)
    rows = [
        {key: export_service._cell(value) for key, value in row.items()} for row in raw_rows
    ]  # noqa: SLF001

    for field, allowed in (filters or {}).items():
        if not allowed:
            continue
        allowed_set = {str(value) for value in allowed}
        rows = [row for row in rows if str(row.get(field)) in allowed_set]

    selected = fields or [key for key, *_ in DATASET_FIELDS[dataset]]
    return [{field: row.get(field) for field in selected} for row in rows]


def to_pdf(rows: list[dict[str, Any]], *, title: str, organization: Organization) -> bytes:
    columns = list(rows[0].keys()) if rows else []
    return pdf_service.render_pdf(
        "custom_report.html",
        {
            "organization": organization,
            "logo_url": None,
            "generated_at": date.today(),
            "title": title,
            "columns": columns,
            "rows": rows,
        },
    )


async def run_definition(
    db: AsyncSession,
    context: OrgContext,
    definition: ReportDefinition,
    *,
    export_format: str | None = None,
) -> tuple[bytes, str, int]:
    rows = await execute(
        db,
        context,
        dataset=definition.dataset,
        fields=definition.fields,
        filters=definition.filters,
        date_from=definition.date_from,
        date_to=definition.date_to,
    )
    stamp = date.today().isoformat()
    fmt = export_format or definition.export_format.value
    slug = definition.name.lower().replace(" ", "-")[:60] or definition.dataset.value

    if fmt == "csv":
        data = export_service.to_csv(rows)
        filename = f"{slug}-{stamp}.csv"
    elif fmt == "pdf":
        data = to_pdf(rows, title=definition.name, organization=context.organization)
        filename = f"{slug}-{stamp}.pdf"
    else:
        data = export_service.to_excel(rows, DATASET_LABELS[definition.dataset])
        filename = f"{slug}-{stamp}.xlsx"

    definition.last_run_at = datetime.now(UTC)
    return data, filename, len(rows)


def _schedule_due_today(definition: ReportDefinition, today: date) -> bool:
    if definition.schedule == ReportSchedule.WEEKLY:
        return definition.schedule_day is not None and today.weekday() == definition.schedule_day
    if definition.schedule == ReportSchedule.MONTHLY:
        return definition.schedule_day is not None and today.day == definition.schedule_day
    return False


async def run_scheduled_custom_reports(db: AsyncSession) -> int:
    """Deliver every saved report whose schedule is due today (US-094)."""
    today = date.today()
    organizations = list(await db.scalars(select(Organization).where(Organization.is_active.is_(True))))

    sent = 0
    for organization in organizations:
        definitions = list(
            await db.scalars(
                select(ReportDefinition).where(
                    ReportDefinition.organization_id == organization.id,
                    ReportDefinition.schedule != ReportSchedule.NONE,
                )
            )
        )
        due = [d for d in definitions if _schedule_due_today(d, today)]
        if not due:
            continue

        owner = await db.scalar(
            select(User)
            .where(
                User.organization_id == organization.id,
                User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
                User.is_active.is_(True),
            )
            .order_by(User.created_at)
        )
        if owner is None:
            continue
        context = OrgContext(user=owner, organization=organization)

        for definition in due:
            try:
                data, filename, row_count = await run_definition(db, context, definition)
                stored = await file_service.register_generated(
                    db,
                    organization.id,
                    data=data,
                    filename=filename,
                    category=FileCategory.REPORT,
                    entity_type="report_definition",
                    entity_id=definition.id,
                )
                definition.last_run_file_id = stored.id

                recipient_user = owner
                if definition.created_by_id:
                    created_by = await db.get(User, definition.created_by_id)
                    if created_by is not None:
                        recipient_user = created_by

                channels = [
                    NotificationChannel(value)
                    for value in definition.delivery_channels
                    if value in {"whatsapp", "email", "in_app"}
                ] or [NotificationChannel.IN_APP]
                await notification_service.send(
                    db,
                    recipient=notification_service.Recipient.for_user(recipient_user),
                    notification_type=NotificationType.REPORT_READY,
                    title=f"Report ready — {definition.name}",
                    body=f"{row_count} row(s) from your saved report “{definition.name}”.",
                    channels=channels,
                    attachment=notification_service.Attachment(
                        url=file_service.to_url(stored), filename=filename
                    ),
                    link_path="/reports",
                    entity_type="report_definition",
                    entity_id=definition.id,
                    organization_id=organization.id,
                )
                await db.commit()
                sent += 1
            except Exception:  # noqa: BLE001 — one report must not stop the rest
                logger.exception("Scheduled report failed for definition %s", definition.id)
                await db.rollback()

    return sent


# --------------------------------------------------------------------------
# Monthly summary report (US-093)
# --------------------------------------------------------------------------


async def _period_maintenance_cost(
    db: AsyncSession, organization_id: uuid.UUID, start: date, end: date
) -> Decimal:
    total = await db.scalar(
        select(func.coalesce(func.sum(MaintenanceRequest.cost), 0)).where(
            MaintenanceRequest.organization_id == organization_id,
            MaintenanceRequest.status.in_(BILLABLE_STATUSES),
            MaintenanceRequest.cost.is_not(None),
            MaintenanceRequest.completed_at >= start,
            MaintenanceRequest.completed_at <= end,
        )
    )
    return Decimal(total) if total else ZERO


async def build_monthly_summary_context(
    db: AsyncSession,
    organization: Organization,
    owner_context: OrgContext,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    collected = await dashboard_service.collected_between(db, owner_context, period_start, period_end)
    expected = await dashboard_service.invoiced_between(db, owner_context, period_start, period_end)
    expenses = await _period_maintenance_cost(db, organization.id, period_start, period_end)
    arrears = await arrears_service.build_report(db, owner_context)
    portfolio, _ = await property_service.portfolio_stats(db, owner_context)

    collection_rate = float(round(collected / expected * 100, 1)) if expected > 0 else 0.0

    return {
        "organization": organization,
        "logo_url": None,
        "generated_at": date.today(),
        "period_start": period_start,
        "period_end": period_end,
        "income": collected,
        "expected_income": expected,
        "collection_rate": collection_rate,
        "expenses": expenses,
        "net": collected - expenses,
        "total_arrears": arrears.total_arrears,
        "tenants_in_arrears": arrears.tenants_in_arrears,
        "top_defaulters": arrears.rows[:5],
        "occupancy_rate": portfolio.occupancy_rate,
        "occupied_units": portfolio.occupied_units,
        "total_units": portfolio.total_units,
    }


async def generate_monthly_report(
    db: AsyncSession,
    organization: Organization,
    owner_context: OrgContext,
    period_start: date,
    period_end: date,
) -> MonthlyReport | None:
    """Idempotent per `(organization, period_start)` — the unique constraint
    backs this up, but checking first avoids a failed-insert round trip."""
    existing = await db.scalar(
        select(MonthlyReport).where(
            MonthlyReport.organization_id == organization.id,
            MonthlyReport.period_start == period_start,
        )
    )
    if existing is not None:
        return existing

    try:
        context = await build_monthly_summary_context(
            db, organization, owner_context, period_start, period_end
        )
        pdf_bytes = pdf_service.render_pdf("monthly_report.html", context)
    except Exception:  # noqa: BLE001 — a missing PDF backend must not break the scheduler
        logger.exception("Monthly report rendering failed for organisation %s", organization.id)
        return None

    stored = await file_service.register_generated(
        db,
        organization.id,
        data=pdf_bytes,
        filename=f"Monthly-Report-{period_start.strftime('%Y-%m')}.pdf",
        category=FileCategory.REPORT,
        entity_type="organization",
        entity_id=organization.id,
    )
    report = MonthlyReport(
        organization_id=organization.id,
        period_start=period_start,
        period_end=period_end,
        file_id=stored.id,
    )
    db.add(report)
    await db.flush()
    return report


async def deliver_monthly_report(
    db: AsyncSession,
    organization: Organization,
    owner: User,
    report: MonthlyReport,
    stored: StoredFile | None,
) -> None:
    """Mirrors `owner_statement_service.deliver_statement` — WhatsApp/email,
    chosen from the organisation's delivery preference."""
    if stored is None:
        return

    period = report.period_start.strftime("%b %Y")
    body = (
        f"Your monthly summary for {period} is ready — {organization.name}'s income, "
        "expenses and arrears at a glance."
    )

    channels: list[NotificationChannel] = []
    if organization.report_delivery_channel in (ReportDeliveryChannel.WHATSAPP, ReportDeliveryChannel.BOTH):
        channels.append(NotificationChannel.WHATSAPP)
    if organization.report_delivery_channel in (ReportDeliveryChannel.EMAIL, ReportDeliveryChannel.BOTH):
        if owner.email:
            channels.append(NotificationChannel.EMAIL)
    if not channels:
        channels = [NotificationChannel.IN_APP]

    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_user(owner),
        notification_type=NotificationType.REPORT_READY,
        title=f"Monthly summary — {period}",
        body=body,
        channels=channels,
        attachment=notification_service.Attachment(url=file_service.to_url(stored), filename=stored.filename),
        link_path="/reports",
        entity_type="monthly_report",
        entity_id=report.id,
        organization_id=organization.id,
    )
    report.delivered_channels = [c.value for c in channels]
    report.delivered_at = datetime.now(UTC)


async def run_scheduled_monthly_reports(db: AsyncSession) -> int:
    """Generate and deliver last month's summary for every active organisation."""
    today = date.today()
    prior_month_end = today.replace(day=1) - timedelta(days=1)
    period_start = prior_month_end.replace(day=1)
    period_end = prior_month_end

    organizations = list(await db.scalars(select(Organization).where(Organization.is_active.is_(True))))

    built = 0
    for organization in organizations:
        owner = await db.scalar(
            select(User)
            .where(
                User.organization_id == organization.id,
                User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
                User.is_active.is_(True),
            )
            .order_by(User.created_at)
        )
        if owner is None:
            continue

        context = OrgContext(user=owner, organization=organization)
        try:
            report = await generate_monthly_report(db, organization, context, period_start, period_end)
            if report is None:
                await db.commit()
                continue
            stored = await db.get(StoredFile, report.file_id) if report.file_id else None
            if report.delivered_at is None:
                await deliver_monthly_report(db, organization, owner, report, stored)
            await db.commit()
            built += 1
        except Exception:  # noqa: BLE001 — one organisation must not stop the rest
            logger.exception("Scheduled monthly report failed for organisation %s", organization.id)
            await db.rollback()

    return built
