"""Contact-support requests (US-090).

There is no live-chat vendor in the stack, so "in-app chat" is a short form
that gets emailed straight to the RentFlow team — the honest equivalent of
what a chat widget would do behind the scenes anyway.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.core.config import settings
from app.models.customer_success import SupportRequest
from app.schemas.customer_success import SupportRequestCreate
from app.services import audit_service
from app.services.notifications import get_email_notifier


async def create_request(
    db: AsyncSession, context: OrgContext, payload: SupportRequestCreate
) -> SupportRequest:
    row = SupportRequest(
        organization_id=context.organization_id,
        user_id=context.user.id,
        subject=payload.subject,
        message=payload.message,
    )
    db.add(row)
    await db.flush()
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="support_request.created",
        entity_type="support_request",
        entity_id=row.id,
        actor=context.user,
        summary=f"Support request: {row.subject}",
    )
    await db.commit()
    await db.refresh(row)

    notifier = get_email_notifier()
    html = (
        f"<p><strong>Organisation:</strong> {context.organization.name}</p>"
        f"<p><strong>From:</strong> {context.user.full_name} ({context.user.email})</p>"
        f"<p>{payload.message}</p>"
    )
    await notifier.send(settings.SUPPORT_EMAIL, f"Support request: {payload.subject}", html)
    return row
