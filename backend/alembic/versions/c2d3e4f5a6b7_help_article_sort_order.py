"""help article reading order

`help_articles` had no ordering of its own, so `help_service` sorted by
`category, title`. That is right for a search box and wrong for a knowledge
base: "Getting started" landed between "Field operations" and "Rent and
payments", and inside it "Add units to a property" came before "Add your first
property" — the second step ahead of the first.

`sort_order` is global rather than per-category. Articles in a category are
contiguous in the numbering, so grouping by category and ordering by this one
column yields both the order of the categories and the order within each of
them, from a single field staff can edit in the CMS.

Values are spaced in tens so an article can be slotted between two others
without renumbering anything.

The backfill places the articles seeded by `b1c2d3e4f5a6` in the order a new
landlord meets them: set up the portfolio, charge and collect rent, chase what
is unpaid, run the tenancy, then the field, the owners, and the account.
Anything else already in the table — an article written in the staff CMS before
this ran — keeps its old relative position and is appended after the seeded set
rather than silently jumping to the top.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-08

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Reading order, category by category.
READING_ORDER: list[str] = [
    # Getting started
    "add-your-first-property",
    "add-units-to-a-property",
    "invite-your-caretaker",
    "add-your-first-tenant",
    "set-up-the-payment-account",
    # Rent and payments — what is charged, then how money arrives, then how it
    # is matched to a tenancy.
    "invoices-and-your-billing-day",
    "collect-rent-through-mpesa",
    "record-a-manual-payment",
    "how-a-payment-is-matched",
    "reconcile-a-bank-statement",
    # Arrears and reminders
    "work-the-arrears-list",
    "rent-reminders-and-templates",
    "escalating-arrears",
    # Tenants and leases, in the order a tenancy actually happens.
    "screen-an-applicant",
    "lease-templates-and-signing",
    "invite-tenants-to-the-portal",
    # Field operations
    "install-the-caretaker-app",
    "record-meter-readings",
    "maintenance-from-request-to-closed",
    "move-in-and-move-out-inspections",
    # Agency and owners
    "owner-statements-and-disbursements",
    "give-an-owner-a-portal",
    # Your account and data
    "roles-and-permissions",
    "export-your-data",
    "api-keys-and-webhooks",
]

# Where unseeded articles start, far enough above the seeded set that inserting
# a few more seeded articles later will not collide with them.
_APPENDED_FROM = 1000


def upgrade() -> None:
    op.add_column(
        "help_articles",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_help_articles_sort_order", "help_articles", ["sort_order"])

    connection = op.get_bind()
    for position, slug in enumerate(READING_ORDER, start=1):
        connection.execute(
            sa.text("UPDATE help_articles SET sort_order = :position WHERE slug = :slug"),
            {"position": position * 10, "slug": slug},
        )

    # Anything the loop above did not place — an article written in the CMS, or
    # a seeded one whose slug has since been edited — keeps its old
    # `category, title` order and follows the seeded set.
    connection.execute(
        sa.text(
            """
            UPDATE help_articles
               SET sort_order = ranked.position
              FROM (
                    SELECT id,
                           :start + row_number() OVER (ORDER BY category, title) * 10 AS position
                      FROM help_articles
                     WHERE sort_order = 0
                   ) AS ranked
             WHERE help_articles.id = ranked.id
            """
        ),
        {"start": _APPENDED_FROM},
    )


def downgrade() -> None:
    op.drop_index("ix_help_articles_sort_order", table_name="help_articles")
    op.drop_column("help_articles", "sort_order")
