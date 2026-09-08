"""seed the help centre knowledge base

`help_articles` has been readable since Sprint 20 (US-090) but nothing ever
wrote to it: the only author surface is the staff CMS at `/internal/content`,
so every install — including a fresh `./start.sh` — showed "No articles found"
behind the help icon, and the Starter plan's advertised "Help centre" support
tier had nothing behind it.

This seeds the starter knowledge base. Content, not schema, so:

- the insert skips slugs that already exist, and `downgrade` deletes only the
  slugs seeded here. An article edited or unpublished later through the CMS
  survives a re-run of the chain either way.
- the rows are written with `created_by_id = NULL`. The column is nullable
  precisely for content that predates any staff account, which on a fresh
  database is all of it.

Bodies are plain text, not markdown: `HelpPanel` and the public help centre
both render them in a `whitespace-pre-wrap` block, and the search in
`help_service` is a `LIKE` over title and body, so markup would only add noise
to both.

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-09-08

"""

# Article bodies are prose meant to be read at the width of a phone screen, not
# code. Hard-wrapping them at 110 columns would put newlines mid-sentence into
# what `whitespace-pre-wrap` renders verbatim, so the line-length rule is off
# for this file rather than the content being mangled to satisfy it.
# ruff: noqa: E501

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (slug, category, title, body). Category strings are shown to the reader
# verbatim, and are what the public help centre groups by.
ARTICLES: list[tuple[str, str, str, str]] = [
    # ------------------------------------------------------------ getting started
    (
        "add-your-first-property",
        "Getting started",
        "Add your first property",
        """A property in RentFlow is the building, compound or standalone house you manage. Units live inside it, and almost everything else — tenancies, invoices, inspections, maintenance — hangs off a unit.

To add one, go to Properties and choose Add property.

What you are asked for:

1. Name. What you and your caretaker actually call it, for example "Kilimani Court" rather than a title deed reference. It appears on invoices and in every search result.
2. Property type. Apartment block, bedsitter block, maisonette, commercial or mixed use. This decides which fields appear later, so a commercial block can carry service charge apportionment and a residential one is not asked for it.
3. Address and county. Used on lease documents and on public vacancy listings.
4. Billing day. The day of the month invoices are raised for units in this property. It defaults to the organisation-wide billing day from Settings, and you can override it per property.

You do not need the full picture on day one. A name and a type is enough to get moving; everything else can be filled in from the property page later.

If you manage buildings for several different owners, add the owner first under Owner clients and attach the property to them as you create it. That is what makes owner statements and disbursements work later.""",
    ),
    (
        "add-units-to-a-property",
        "Getting started",
        "Add units to a property",
        """A unit is a rentable space: a single apartment, a shop, a bedsitter, a parking bay. Rent is charged against a unit, not against a building.

To add units, open the property and choose Add unit, or go to Units and use Add unit.

Each unit carries:

1. Unit number. The label on the door. It has to be unique inside its property, not across your whole portfolio, so two buildings can both have an A1.
2. Unit type and bedrooms. Used for vacancy listings and for comparing rent across similar units.
3. Rent amount and deposit. The default terms. A tenancy can override them, which is how you handle a legacy tenant on an old rate.
4. Status. Vacant, occupied, or under maintenance. RentFlow keeps this in step with tenancies on its own once one starts.

Adding a whole block one unit at a time is slow. Use Bulk add on the Units screen instead: give it a numbering pattern, a count and a default rent, and it generates the whole floor or block in one pass. You can edit any of them afterwards.

If you are moving an existing portfolio across, see Import your existing tenants and units.""",
    ),
    (
        "invite-your-caretaker",
        "Getting started",
        "Invite your caretaker",
        """Your caretaker gets their own login. They never see your books — no rent totals, no arrears, no owner statements — only the jobs, readings and visitors for the properties you assign them.

To invite one, go to Team and choose Invite, then pick the Caretaker role and the properties they cover. They get an SMS and email with a link to set their own password.

What they can do once in:

1. See a Today list of jobs and readings due on their properties.
2. Record water and power meter readings, with a photo of the meter.
3. Update maintenance jobs, attach before and after photos, and record what was spent.
4. Log visitors in and out at the gate.
5. Run move-in and move-out inspections room by room.

The caretaker app is designed for a corridor: large touch targets, one thumb, and it works with no signal. Readings and job updates queue on the handset and sync when the phone gets a connection. Tell your caretaker to install it — see Install the caretaker app on a phone.

Set a cash limit for them in Settings, under Organisation. Any spend above it stops and waits for your approval instead of going through.""",
    ),
    (
        "add-your-first-tenant",
        "Getting started",
        "Add your first tenant and start a tenancy",
        """A tenant is a person. A tenancy is the agreement putting that person in a unit for a period at a rent. RentFlow keeps them separate so a tenant who moves between your units keeps one payment history.

Add the person first, under Tenants, then Add tenant: name, phone number, email if they have one, national ID, and next of kin.

Then start the tenancy from Tenancies, using Start tenancy. The wizard walks through:

1. The unit and the tenant.
2. Start date, and end date if the lease is fixed term.
3. Rent, deposit, and any recurring charges such as service charge, water standing charge or parking.
4. Billing day, prefilled from the property.
5. The deposit already held, if the tenant is an existing one you are bringing across.

Finish the wizard and RentFlow marks the unit occupied, schedules the first invoice for the next billing day, and opens the tenant's statement.

Two things worth doing straight after:

- Invite the tenant to the portal so they can see their own statement and stop calling you for a balance. See Invite tenants to the portal.
- Generate the lease from a template and send it for signature. See Lease templates and signing.""",
    ),
    (
        "set-up-the-payment-account",
        "Getting started",
        "Set up the account tenants pay into",
        """Tenants need to know where to send rent, and RentFlow needs to know it too so that what arrives can be matched to what is owed.

Go to Settings, then Organisation, and fill in the Payment details section:

1. Bank name, account name, account number and branch. These are printed on every invoice as the bank transfer instructions, so check them character by character.
2. KRA PIN. Required before RentFlow can issue eTIMS-compliant electronic receipts.
3. Default billing day, used for new tenancies.

M-Pesa is set up separately, because the paybill or till integration runs through Safaricom's Daraja API rather than a field you type in. See Collect rent through M-Pesa.

While you are on this screen, set the default caretaker cash limit. Any maintenance spend above it waits for approval rather than being committed on site.

Nothing here is visible to tenants except the bank instructions on their invoice and in the portal.""",
    ),
    # --------------------------------------------------------- rent and payments
    (
        "collect-rent-through-mpesa",
        "Rent and payments",
        "Collect rent through M-Pesa",
        """M-Pesa collection runs through Safaricom's Daraja API. It is configured once for your RentFlow instance rather than per property, so if you are on the hosted service this is already live and you have nothing to switch on. If you are self-hosting, the Daraja consumer key, secret, shortcode and passkey are read from environment variables — the keys are listed in the backend environment example file, and the values come from your own Safaricom developer portal account.

Once it is live there are two ways money arrives.

Tenant-initiated. The tenant pays your paybill or till the way they always have, using their unit number as the account reference. The C2B callback lands the payment in RentFlow within seconds and it is matched automatically.

You-initiated (STK push). From Payments, choose Record payment, pick the tenancy, enter the amount and choose M-Pesa STK push. The tenant's phone prompts them for their PIN. RentFlow polls Daraja until it has an answer and marks the payment confirmed or failed — you do not have to refresh.

Payments that arrive without a usable reference, or from a phone number RentFlow does not recognise, land in the unmatched queue on the Payments screen for you to allocate by hand. See How a payment is matched to a tenancy.""",
    ),
    (
        "record-a-manual-payment",
        "Rent and payments",
        "Record a cash or bank payment",
        """Not every shilling arrives through M-Pesa. Cash at the gate, a bank transfer, a cheque, or rent settled against a repair the tenant paid for — all of it needs recording so the statement stays true.

Go to Payments, then Record payment:

1. Choose the tenancy. The screen shows what that tenancy currently owes and the oldest unpaid invoice.
2. Enter the amount and the date the money actually moved, which is not always today.
3. Choose the method: cash, bank transfer, cheque, or M-Pesa recorded after the fact.
4. Add the reference — bank slip number, cheque number, or M-Pesa code. This is what you will search on when someone disputes a payment two years from now.
5. Save.

RentFlow allocates the money to the oldest unpaid invoice first, then forward. If the amount does not settle an invoice exactly, the remainder stays as credit on the tenancy and is applied to the next one.

A payment recorded by a caretaker above the cash limit is held pending your approval before it is banked against an invoice. It shows on the Payments screen with a pending badge until you release it.""",
    ),
    (
        "how-a-payment-is-matched",
        "Rent and payments",
        "How a payment is matched to a tenancy",
        """Most of the work in collecting rent is not receiving money, it is working out whose money it is. RentFlow matches in this order.

1. Account reference. If the tenant used their unit number, the match is exact and immediate.
2. Phone number. If the paying number is on a tenant record, the payment goes to that tenant's active tenancy.
3. Amount and timing. A payment for exactly the outstanding balance of one tenancy, arriving near its billing day, is proposed as a match for you to confirm.
4. Nothing matched. It sits in the unmatched queue on the Payments screen until you allocate it.

The awkward cases, and what happens:

- Part payment. Allocated to the oldest unpaid invoice. The invoice stays partly paid and the tenancy stays in arrears for the balance.
- Overpayment. The excess stays as credit on the tenancy and is consumed by the next invoice automatically.
- Paid from a relative's number. Unmatched on the phone number rule, but matched if they used the unit number as the reference. If neither worked, allocate it by hand once, and add that number to the tenant's record so it matches on its own next time.
- Paid for two units at once. Allocate it manually and split it across both tenancies from the unmatched queue.""",
    ),
    (
        "reconcile-a-bank-statement",
        "Rent and payments",
        "Reconcile a bank statement",
        """Rent paid by bank transfer does not announce itself the way M-Pesa does. Upload the statement and RentFlow will do the matching.

Go to Payments, then Bank statements, and upload the file your bank exports — CSV or the statement export from your online banking.

RentFlow reads each credit line and proposes a match against outstanding invoices, using the narration, the amount and the date. The upload then opens a review screen with three groups:

1. Matched. Confident matches, ready to accept in bulk.
2. Needs a decision. Likely matches where the narration is ambiguous or the amount does not settle an invoice cleanly. Confirm or reassign each one.
3. Unmatched. Credits that are not rent at all, or are rent from someone RentFlow cannot identify. Allocate them by hand or leave them.

Nothing is posted until you accept it. Once accepted, each line becomes a payment against its tenancy exactly as if you had recorded it by hand, with the statement line kept as the reference.

Re-uploading the same statement does not double-count: lines already reconciled are recognised and skipped.""",
    ),
    (
        "invoices-and-your-billing-day",
        "Rent and payments",
        "Invoices and your billing day",
        """RentFlow raises invoices automatically on each tenancy's billing day. You do not press anything.

What lands on an invoice:

1. Rent for the period, from the tenancy.
2. Recurring charges attached to the tenancy — service charge, water standing charge, parking, refuse.
3. Metered utilities, if a reading was recorded since the last invoice. See Record meter readings and bill them.
4. Late fees, if the tenancy is past its grace period and you have late fees configured.
5. Any one-off charge you added during the month, such as a repair recharged to the tenant.

The invoice is sent on the channels the tenant is set up for — WhatsApp first, SMS as fallback, email for the paper trail — and appears in their portal at the same time.

To see them, go to Invoices. You can filter by property, by status, or by period. Opening one shows every line, every payment applied to it, and the delivery history: which channel it went out on and whether it was delivered.

If your KRA PIN is set and eTIMS is enabled, a compliant electronic receipt is issued automatically the moment a payment clears against the invoice. Nothing further is needed from you.""",
    ),
    # ---------------------------------------------------- arrears and reminders
    (
        "work-the-arrears-list",
        "Arrears and reminders",
        "Work the arrears list",
        """Arrears in RentFlow is a worklist, not a report. Go to Arrears.

Every tenancy that owes money appears as a row, ranked by how much is at stake and how long it has been outstanding. Each row shows:

1. Who owes, which unit, and how much.
2. How many days past due the oldest unpaid invoice is.
3. What has already been sent, and when — so you do not send a third first reminder.
4. The next action, ready to fire.

The actions available from a row, without leaving the screen:

- Send a reminder on WhatsApp or SMS, using your template.
- Record a payment promise with a date, which moves the row down the list until that date passes.
- Generate a demand letter as a PDF.
- Open the tenancy for the full history.

Filter by property, by ageing bucket, or by amount to work the list the way you actually work: biggest first, or oldest first, or one building at a time.

The ageing buckets — 1 to 30 days, 31 to 60, 61 to 90, over 90 — are the same ones the arrears ageing report uses, so what you see here and what an owner sees on their statement agree.""",
    ),
    (
        "rent-reminders-and-templates",
        "Arrears and reminders",
        "Set up rent reminders",
        """Reminders go out on their own once configured. Go to Settings, then Message templates.

You control the text of each template. The available ones cover the rent cycle: invoice issued, rent due soon, rent overdue, payment received, and the escalating arrears notices.

Templates use placeholders that RentFlow fills in per tenant — the tenant's name, the unit, the amount, the due date, the balance. The editor lists every placeholder available in the template you are editing, so you do not have to guess the spelling.

Channel order is WhatsApp first, SMS if WhatsApp does not reach them, email for the record. You can turn any channel off per template.

Timing is set per template: how many days before or after the due date it fires. A tenant who has already paid is skipped automatically — the check happens at send time, not when the batch was scheduled, so someone who pays the night before never gets the overdue message.

Keep the tone in your templates plain. These land in a WhatsApp thread that also has family messages in it, and they are read on a small screen.""",
    ),
    (
        "escalating-arrears",
        "Arrears and reminders",
        "Escalating arrears: demand letters and notices",
        """When reminders stop working, the ladder continues inside RentFlow so that the paper trail stays in one place.

Demand letter. From the Arrears screen, or from the tenancy, generate a demand letter. It is a PDF on your letterhead, stating the amount outstanding, the periods it covers, and the payment deadline. It is filed against the tenancy and delivered on the tenant's channels, with delivery recorded.

Notice to vacate. If it goes further, issue a notice from the tenancy. RentFlow records the notice date and the notice period, and schedules the move-out inspection.

Everything issued is kept: what was sent, on which channel, on what date, and whether it was delivered. That record is the thing that matters if the matter ever leaves your hands, and it is exportable from the tenancy.

Two things RentFlow deliberately does not do: it does not lock anyone out, and it does not generate court filings. The escalation ladder ends at a documented notice.

Before escalating, check the tenancy for unallocated credit and for payments sitting in the unmatched queue. A tenant who has paid but whose payment was never matched should not receive a demand letter.""",
    ),
    # ------------------------------------------------------- field operations
    (
        "install-the-caretaker-app",
        "Field operations",
        "Install the caretaker app on a phone",
        """The caretaker app is not a separate download from an app store. It is RentFlow itself, installed to the phone's home screen.

On the caretaker's phone:

1. Open the RentFlow address in Chrome and sign in with the invite they received.
2. Take the Install prompt when it appears, or open the browser menu and choose Add to home screen.
3. It now opens from the home screen icon, full screen, with no browser bar.

What it gives them:

- A Today list: the jobs, readings and inspections due on their properties.
- Large touch targets sized for one thumb, which matters when the other hand is holding a torch.
- Offline capture. Meter readings, visitor entries and job updates are saved on the handset when there is no signal and sync by themselves once there is. The app shows what is still queued, so nothing is silently lost.
- Camera capture straight into a job or an inspection, without going through the gallery.

Photos taken offline queue with everything else. A caretaker can work a whole basement corridor with no bars and sync at the gate on the way out.""",
    ),
    (
        "record-meter-readings",
        "Field operations",
        "Record meter readings and bill them",
        """Water and power readings recorded on a phone become invoice lines without anyone retyping them.

To record one, open Meter readings and choose Record reading, or take it from the caretaker's Today list where readings due are already listed.

Per reading:

1. The unit and the meter — water or electricity.
2. The current reading.
3. A photo of the meter face. This is what settles the argument later.

RentFlow shows the previous reading and the consumption as you type, and warns if the new figure is lower than the last one or wildly above the unit's usual usage — the two ways a misread digit shows up.

The consumption is multiplied by the rate set on the property or the unit, and appears on that tenancy's next invoice as its own line, with the opening and closing readings shown so the tenant can check it.

Readings taken with no signal queue on the handset and sync later. A reading that arrives after the invoice for its period has already been raised is billed on the following invoice rather than being dropped.""",
    ),
    (
        "maintenance-from-request-to-closed",
        "Field operations",
        "Maintenance, from request to closed job",
        """A maintenance job in RentFlow runs one path, whoever starts it.

1. Raised. The tenant raises it from their portal with a photo, or you or the caretaker raise it from Maintenance, then New request. It carries a category, a priority and the unit.
2. Assigned. To your caretaker for something in-house, or to a vendor from your vendor list. The assignee is notified on their own channel.
3. In progress. The caretaker photographs the work and updates the job from their phone. Photos and notes are timestamped against the job.
4. Cost recorded. Spend is entered against the job. Anything over the caretaker's cash limit, or over your approval threshold, stops and waits for approval — see the Approvals screen.
5. Closed. With the after photos, the final cost, and who did it.

The tenant sees the status change in their portal at each step, which is most of what the follow-up calls are about.

Vendors accumulate a record as you use them: jobs completed, average cost, average turnaround time. Maintenance analytics turns that into cost per unit and cost per property, so you can see which building is quietly eating the year's budget.""",
    ),
    (
        "move-in-and-move-out-inspections",
        "Field operations",
        "Run a move-in or move-out inspection",
        """An inspection is the evidence behind a deposit decision. Both ends of a tenancy should have one.

Start from Inspections, then New inspection, or from the tenancy itself. Choose the type — move-in, move-out, or routine — and the unit.

The capture screen walks room by room. For each item you record a condition and, where it matters, a photo. It is built to be worked through on a phone while standing in the room, and it works with no signal.

On a move-out inspection, RentFlow puts the move-in record beside the current one, item by item, so the comparison is on one screen rather than in your memory. Anything that has changed is flagged.

From the comparison you can raise deductions against the deposit, each tied to the specific item and photo it comes from. The deposit settlement statement is generated from those deductions, and the tenant sees the same photographs you did.

Sign-off is captured on the device from both the caretaker and the tenant. A signed inspection is filed in the property vault and cannot be edited afterwards, only superseded by a new one.""",
    ),
    # ------------------------------------------------------ tenants and leases
    (
        "invite-tenants-to-the-portal",
        "Tenants and leases",
        "Invite tenants to the portal",
        """The tenant portal answers the three questions that otherwise arrive as texts: what do I owe, did my payment land, and when is someone coming to fix it.

To invite a tenant, open the tenancy and choose Invite to portal, or invite in bulk from Bulk actions. They receive a link by SMS and email and set their own password.

What a tenant sees, and only for their own tenancy:

1. Their statement — every invoice, every payment, the running balance.
2. Payment instructions, and the ability to trigger an M-Pesa prompt on their own phone.
3. Their lease and any documents you have shared with them.
4. Maintenance requests: raise one with a photo, and follow its status.
5. Their own data and privacy controls, as required under the Data Protection Act.

They cannot see other tenants, other units, your arrears list, or anything about the property's finances.

If a tenant loses access, resend the invite from the tenancy. The old link stops working when a new one is issued.""",
    ),
    (
        "screen-an-applicant",
        "Tenants and leases",
        "Screen an applicant before handing over keys",
        """Screening happens over public links, so an applicant does not need a RentFlow login to complete it.

1. From the vacant unit, or from Vacancies, generate an application link and send it to the applicant.
2. They complete the form: identity, employment and income, current address, and the contact details of a guarantor and a previous landlord.
3. RentFlow emails the guarantor and the previous landlord their own links. Each responds directly, without going through the applicant.
4. Responses land on the application under Applications as they arrive, so you can see what is still outstanding.
5. The application carries a score built from what came back — income against rent, whether the previous landlord responded and what they said, whether the guarantor accepted.

You approve or decline from the application. Approving carries the applicant's details straight into a new tenancy, so nothing is retyped.

Everything collected is filed against the tenancy and kept under the same retention rules as the rest of the tenant's data. The applicant is told what is being collected and why at the point they fill in the form.""",
    ),
    (
        "lease-templates-and-signing",
        "Tenants and leases",
        "Lease templates and signing",
        """A lease template is your standard agreement with the tenancy-specific parts left as placeholders.

Set one up under Lease templates. Start from the provided starter template and edit it, or paste in the agreement your lawyer drafted. Placeholders are filled per tenancy: the parties, the unit, the rent, the deposit, the term, the notice period, your registered legal name and address from Settings.

To issue one, open the tenancy and generate the lease. RentFlow produces the PDF with everything filled in. Read it once before sending — the template is yours, and RentFlow does not check its terms.

Send it for signature and each party gets their own link. They sign on a phone or a laptop; no account is needed. RentFlow records who signed, when, and from which address, and produces the signed PDF with that audit trail attached.

The executed lease is filed in the tenant's document vault and appears in their portal, so neither of you has to find the email it came in.

You can hold more than one template — residential and commercial, or one per owner you manage for — and choose which to use at the point of issuing.""",
    ),
    # ----------------------------------------------------- agency and owners
    (
        "owner-statements-and-disbursements",
        "Agency and owners",
        "Owner statements and disbursements",
        """If you manage buildings for other people, RentFlow tracks what you collected on their behalf, what you are owed, and what has to be paid across.

Set up first. Under Owner clients, create the owner and attach their properties. On the owner record, set the management fee — a percentage of collections or a flat monthly amount — and their payout bank or M-Pesa details.

Each month, from Disbursements:

1. Choose the owner and the period. RentFlow builds a preview: rent collected on their units, less your management fee, less any maintenance spend recharged to them, less anything else you have recorded against them.
2. Check the preview. Every figure opens to the payments and jobs behind it.
3. Approve it. The statement PDF is generated and sent to the owner.
4. Record the payout, or send it by M-Pesa B2C where that is configured.

The statement shows the owner their own properties in full: which units paid, which are in arrears, what was spent on maintenance and on what. It is the document that stops the monthly phone call.

Statements are kept, so last year's is still there when the owner's accountant asks in June.""",
    ),
    (
        "give-an-owner-a-portal",
        "Agency and owners",
        "Give an owner their own portal",
        """An owner client can have a read-only login showing their own portfolio and nothing else.

Invite them from their record under Owner clients. They set their own password from the link.

What they see:

1. Their properties and units, with occupancy and rent roll.
2. Collections for the current and past periods.
3. Their statements and disbursement history.
4. Arrears on their units, and maintenance spend on them.

What they cannot see: any other owner's properties, your other clients, your management fees on other portfolios, your team, or your own account settings. The scoping is enforced on the server, not by hiding menu items.

Owner portal invites are limited by plan — five on Professional, twenty on Business, unlimited on Enterprise.

An owner cannot change anything. If they want a rent increase or a tenant approved, that is still a conversation with you, and you make the change. This is deliberate: two people editing the same tenancy from different sides is how a portfolio ends up with two versions of the truth.""",
    ),
    # -------------------------------------------------- your account and data
    (
        "roles-and-permissions",
        "Your account and data",
        "Roles and who sees what",
        """Everyone you invite gets a role, and the role decides what they can reach. Roles are set under Team when you invite someone, and can be changed afterwards.

The shape of it:

- Owner or admin. Everything, including settings, billing and team management.
- Manager. Day-to-day operations across assigned properties: tenancies, invoices, payments, maintenance, arrears. Not organisation settings.
- Finance. The money: payments, invoices, arrears, reports, disbursements. Not tenant records or maintenance.
- Caretaker. Only their assigned properties, and only jobs, readings, visitors and inspections. No financial figures at all.
- Owner client. Read-only, their own portfolio only. See Give an owner their own portal.

Permissions are checked on the server for every request, not just used to hide menu items, so a link shared with someone who lacks the permission still returns nothing.

Two settings worth reviewing when you add anyone: the caretaker cash limit and the approval threshold, both under Settings, then Organisation. They decide what a member of your team can commit without you.

Every action that changes money or a tenancy is written to an audit trail with who did it and when. It is tamper-evident: entries are chained, so a modified or deleted entry is detectable.""",
    ),
    (
        "export-your-data",
        "Your account and data",
        "Export your data",
        """Your data is yours and leaves in a format you can actually use.

Go to Settings, then Exports.

You can export:

1. Individual data sets — properties, units, tenants, tenancies, payments, invoices, maintenance — as CSV or Excel.
2. A full account export, covering everything above in one archive.
3. Analytical extracts in Parquet, for loading into a warehouse or a BI tool.

Reports have their own exports. Any report you build under Reports can be exported directly, or scheduled for delivery to email or WhatsApp on a recurring basis without anyone logging in to fetch it.

Documents in the vault — leases, inspection reports, ID copies — are included in the full export as files, not just as links, so the archive is complete on its own.

There is no exit fee, no notice period on an export, and no support ticket to raise. If you are leaving, take everything first.

For programmatic access rather than a file, see API keys and webhooks.""",
    ),
    (
        "api-keys-and-webhooks",
        "Your account and data",
        "API keys and webhooks",
        """If you want your own tooling, an accounting sync or a warehouse feed, RentFlow has a documented read-only public API.

Go to Developer.

API keys. Create a key, choose its scopes — properties, units, tenants, payments, invoices, each read-only — and optionally an expiry date. The key is shown once at creation and never again; RentFlow stores only a hash of it. If you lose it, revoke it and issue another. Revocation takes effect immediately.

Send the key on each request as an X-API-Key header. It is a different credential type from the login token the app itself uses, deliberately, so a leaked integration key cannot be used to sign in.

The default limit is 1,000 requests an hour per key, on a rolling window.

Webhooks. Rather than polling, register an endpoint and choose the events you want — a payment received, an invoice issued, a maintenance job closed. RentFlow posts to your URL when they happen, signs each delivery so you can verify it came from RentFlow, and retries failures with a backoff. The Developer screen shows recent deliveries and their responses, which is where to look first when an integration goes quiet.

Full endpoint documentation is generated from the API itself and served at /docs on your instance.

API access is included from the Business plan and available as an add-on below it.""",
    ),
]


def upgrade() -> None:
    help_articles = sa.table(
        "help_articles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("slug", sa.String),
        sa.column("title", sa.String),
        sa.column("body", sa.Text),
        sa.column("category", sa.String),
        sa.column("is_published", sa.Boolean),
    )

    connection = op.get_bind()
    existing = set(connection.scalars(sa.text("SELECT slug FROM help_articles")))
    rows = [
        {
            # `id` has a Python-side default on the model, not a server default,
            # so the migration has to supply one.
            "id": uuid.uuid4(),
            "slug": slug,
            "title": title,
            "body": body,
            "category": category,
            "is_published": True,
        }
        for slug, category, title, body in ARTICLES
        if slug not in existing
    ]
    if rows:
        op.bulk_insert(help_articles, rows)


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM help_articles WHERE slug = ANY(:slugs)"),
        {"slugs": [slug for slug, _, _, _ in ARTICLES]},
    )
