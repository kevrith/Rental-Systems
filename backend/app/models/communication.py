"""Editable message templates (Module 21).

Every notification RentFlow sends has default copy written into the service
that raises it. That default is right for most landlords and wrong for some:
an upmarket agency in Westlands and a caretaker-run block in Kayole do not
address their tenants the same way, and neither wants a message that reads as
though it came from a software company.

A `CommunicationTemplate` is an organisation's override for one notification
type on one channel. `notification_service.send` looks one up on every
dispatch; when there isn't one, the caller's hardcoded copy stands. That is
what makes this additive rather than a migration — nothing has to be
templated for the feature to work, and a template that fails to render falls
back rather than dropping the message.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.notification import TYPE_ENUM, NotificationChannel, NotificationType


class TemplateChannel(str, enum.Enum):
    """`ANY` is the catch-all: one body used on every channel the notification
    goes out on. A channel-specific row wins over it, which is how an
    organisation writes a terse SMS and a fuller email for the same event."""

    ANY = "any"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"
    IN_APP = "in_app"
    PUSH = "push"

    def matches(self, channel: NotificationChannel) -> bool:
        return self == TemplateChannel.ANY or self.value == channel.value


class CommunicationTemplate(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One organisation's wording for one notification type on one channel."""

    __tablename__ = "communication_templates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "notification_type",
            "channel",
            name="uq_communication_template_type_channel",
        ),
    )

    # The shared enum object from `app.models.notification`, not a second
    # `Enum(NotificationType, ...)` — two declarations of the same Postgres
    # type name collide on create_all.
    notification_type: Mapped[NotificationType] = mapped_column(TYPE_ENUM, nullable=False, index=True)
    channel: Mapped[TemplateChannel] = mapped_column(
        Enum(TemplateChannel, name="template_channel"), default=TemplateChannel.ANY, nullable=False
    )

    # `title` may be blank to keep the caller's default while overriding only
    # the body — the common case, since most titles are already short and
    # factual and it is the body a landlord wants to rewrite.
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # The placeholders this template was written against, captured when it was
    # saved. Purely informational — rendering never fails on an unknown name,
    # it leaves it in place — but it lets the editor show what is available and
    # warn about a typo before anything is sent to a real tenant.
    known_variables: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)

    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
