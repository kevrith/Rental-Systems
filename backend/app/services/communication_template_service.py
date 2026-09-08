"""Rendering an organisation's own message wording (Module 21).

Substitution is deliberately not Jinja. A landlord editing the rent reminder
should be typing `{{tenant_name}}`, not learning a template language, and the
strings they write are stored and rendered server-side — handing that surface
full Jinja means a customer-authored template can reach into the objects it is
rendered with. `{{name}}` and nothing else is the whole grammar.

The failure mode matters more than the feature. A template that references a
variable the caller never supplied would otherwise send a tenant the literal
text `{{balance}}`, or a message with a hole in it. Instead
`render` refuses: it returns None, the caller keeps its own hardcoded copy,
and the mismatch is logged. A slightly generic message that is correct beats a
personalised one that is wrong, every time.
"""

import logging
import re
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.communication import CommunicationTemplate, TemplateChannel
from app.models.notification import NotificationChannel, NotificationType
from app.services import audit_service

logger = logging.getLogger("rentflow.templates")

# `{{ name }}`, with or without the surrounding spaces. Names are restricted to
# identifiers so nothing resembling an expression can be smuggled in.
PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

# Longest a rendered SMS body may be before it stops being one message. Not
# enforced — a landlord may legitimately want a long WhatsApp message — but
# surfaced to the editor so the cost of a four-part SMS is a decision rather
# than a surprise on the bill.
SMS_SEGMENT_CHARS = 160

# Variables every template can use, whatever the caller passed.
UNIVERSAL_VARIABLES = ("organization_name", "today")

# What a landlord can put in each type of message. This is documentation the
# editor renders, not validation: a caller may pass more than is listed, and
# `render` refuses on anything genuinely missing rather than trusting this map.
SUGGESTED_VARIABLES: dict[NotificationType, tuple[str, ...]] = {
    NotificationType.RENT_REMINDER: (
        "tenant_name",
        "amount",
        "due_date",
        "property_name",
        "unit_number",
        "balance",
    ),
    NotificationType.PAYMENT_CONFIRMED: (
        "tenant_name",
        "amount",
        "reference_code",
        "balance",
        "property_name",
        "unit_number",
    ),
    NotificationType.RECEIPT_ISSUED: ("tenant_name", "amount", "reference_code", "balance"),
    NotificationType.INVOICE_ISSUED: ("tenant_name", "amount", "due_date", "reference_code"),
    NotificationType.LEASE_EXPIRY: ("tenant_name", "end_date", "days_remaining", "unit_number"),
    NotificationType.MAINTENANCE_UPDATE: ("tenant_name", "reference_code", "title", "status"),
    NotificationType.VACATE_NOTICE: ("tenant_name", "move_out_date", "unit_number"),
    NotificationType.WELCOME: ("full_name", "organization_name"),
    NotificationType.RENT_INCREASE: ("tenant_name", "old_rent", "new_rent", "effective_date"),
    NotificationType.ANNOUNCEMENT: ("tenant_name", "property_name"),
}


def variables_in(body: str) -> list[str]:
    """Placeholder names used by a template, in first-appearance order."""
    seen: list[str] = []
    for name in PLACEHOLDER.findall(body):
        if name not in seen:
            seen.append(name)
    return seen


def render(template_body: str, variables: dict[str, object]) -> str | None:
    """Substitute placeholders, or None if the template asks for something absent.

    None is the caller's signal to fall back to its own copy — see the module
    docstring for why a partial render is never the right answer.
    """
    missing = [name for name in variables_in(template_body) if name not in variables]
    if missing:
        logger.warning("Template not used — no value supplied for %s", ", ".join(missing))
        return None
    return PLACEHOLDER.sub(lambda match: str(variables[match.group(1)]), template_body)


async def find_for(
    db: AsyncSession,
    organization_id: uuid.UUID,
    notification_type: NotificationType,
    channel: NotificationChannel,
) -> CommunicationTemplate | None:
    """The best template for this type and channel, or None.

    A channel-specific row beats the `ANY` catch-all, which is how an
    organisation writes a terse SMS and a fuller email for the same event
    without having to write one for every channel.
    """
    rows = list(
        await db.scalars(
            select(CommunicationTemplate).where(
                CommunicationTemplate.organization_id == organization_id,
                CommunicationTemplate.notification_type == notification_type,
                CommunicationTemplate.is_active.is_(True),
            )
        )
    )
    if not rows:
        return None

    exact = next((row for row in rows if row.channel.value == channel.value), None)
    if exact is not None:
        return exact
    return next((row for row in rows if row.channel == TemplateChannel.ANY), None)


async def apply(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    notification_type: NotificationType,
    channel: NotificationChannel,
    title: str,
    body: str,
    variables: dict[str, object] | None = None,
) -> tuple[str, str]:
    """Return the (title, body) to actually send.

    Called on every dispatch from `notification_service.send`. The caller's own
    copy is returned unchanged when there is no template, when the template
    cannot be rendered, or when anything at all goes wrong — this sits directly
    in the path of every message the product sends, and it must not be able to
    stop one going out.
    """
    try:
        template = await find_for(db, organization_id, notification_type, channel)
        if template is None:
            return title, body

        merged: dict[str, object] = {
            "organization_name": "",
            "today": datetime.now(UTC).strftime("%d %b %Y"),
            **(variables or {}),
        }
        rendered_body = render(template.body, merged)
        if rendered_body is None:
            return title, body

        rendered_title = title
        if template.title:
            rendered_title = render(template.title, merged) or title

        template.last_used_at = datetime.now(UTC)
        return rendered_title, rendered_body
    except Exception as exc:  # noqa: BLE001 — a template bug must never block a message
        # Logged without the exception's own message/traceback: it was raised while
        # handling `variables` (tenant name, balance, amounts — caller-supplied PII),
        # and a built-in exception's message frequently echoes the offending value
        # verbatim (e.g. a bad KeyError/TypeError), which would otherwise land that
        # value in clear text in the log.
        logger.error("Communication template lookup failed for %s: %s", notification_type, type(exc).__name__)
        return title, body


# ------------------------------------------------------------------- editing


async def list_templates(db: AsyncSession, context: OrgContext) -> list[CommunicationTemplate]:
    rows = await db.scalars(
        select(CommunicationTemplate)
        .where(CommunicationTemplate.organization_id == context.organization_id)
        .order_by(CommunicationTemplate.notification_type, CommunicationTemplate.channel)
    )
    return list(rows)


async def upsert(
    db: AsyncSession,
    context: OrgContext,
    *,
    notification_type: NotificationType,
    channel: TemplateChannel,
    title: str | None,
    body: str,
    is_active: bool = True,
) -> CommunicationTemplate:
    """Create or replace the wording for one type and channel."""
    if not body.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A template needs a message body")

    used = variables_in(body) + (variables_in(title) if title else [])
    allowed = set(SUGGESTED_VARIABLES.get(notification_type, ())) | set(UNIVERSAL_VARIABLES)
    unknown = sorted({name for name in used if name not in allowed})
    if unknown:
        # Refused rather than warned: an unknown placeholder means every message
        # of this type silently falls back, and the landlord would have no way
        # of knowing their template was never used.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown placeholder(s): {', '.join(unknown)}. "
                f"Available here: {', '.join(sorted(allowed))}"
            ),
        )

    existing = await db.scalar(
        select(CommunicationTemplate).where(
            CommunicationTemplate.organization_id == context.organization_id,
            CommunicationTemplate.notification_type == notification_type,
            CommunicationTemplate.channel == channel,
        )
    )
    if existing is None:
        existing = CommunicationTemplate(
            organization_id=context.organization_id,
            notification_type=notification_type,
            channel=channel,
            body=body,
        )
        db.add(existing)

    existing.title = title or None
    existing.body = body
    existing.is_active = is_active
    existing.known_variables = used
    existing.updated_by_id = context.user.id

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="communication_template.saved",
        entity_type="communication_template",
        entity_id=existing.id,
        actor=context.user,
        summary=(
            f"Saved custom {notification_type.value} wording for "
            f"{'every channel' if channel == TemplateChannel.ANY else channel.value}"
        ),
    )
    await db.commit()
    await db.refresh(existing)
    return existing


async def delete(db: AsyncSession, context: OrgContext, template_id: uuid.UUID) -> None:
    """Drop the override; the built-in copy takes over again immediately."""
    template = assert_in_org(await db.get(CommunicationTemplate, template_id), context, label="template")
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="communication_template.deleted",
        entity_type="communication_template",
        entity_id=template.id,
        actor=context.user,
        summary=f"Reverted {template.notification_type.value} to the built-in wording",
    )
    await db.delete(template)
    await db.commit()


def preview(body: str, title: str | None, notification_type: NotificationType) -> dict:
    """What this template looks like filled in, without sending anything.

    Sample values come from the suggested-variable list, so the preview shows
    the shape of a real message and the length an SMS would actually be.
    """
    samples: dict[str, object] = {
        "organization_name": "Acacia Property Management",
        "today": datetime.now(UTC).strftime("%d %b %Y"),
        "tenant_name": "Jane Wanjiru",
        "full_name": "Jane Wanjiru",
        "amount": "25,000.00",
        "balance": "0.00",
        "old_rent": "25,000.00",
        "new_rent": "27,500.00",
        "due_date": "5 Oct 2026",
        "effective_date": "1 Nov 2026",
        "end_date": "31 Dec 2026",
        "move_out_date": "30 Nov 2026",
        "days_remaining": "30",
        "property_name": "Acacia Court",
        "unit_number": "B4",
        "reference_code": "PMT-7K2M9Q",
        "title": "Kitchen tap leaking",
        "status": "in progress",
    }
    rendered_body = render(body, samples)
    rendered_title = render(title, samples) if title else None
    segments = -(-len(rendered_body) // SMS_SEGMENT_CHARS) if rendered_body else 0

    return {
        "title": rendered_title,
        "body": rendered_body,
        "variables_used": variables_in(body) + (variables_in(title) if title else []),
        "available_variables": sorted(
            set(SUGGESTED_VARIABLES.get(notification_type, ())) | set(UNIVERSAL_VARIABLES)
        ),
        "character_count": len(rendered_body) if rendered_body else 0,
        "sms_segments": segments,
    }
