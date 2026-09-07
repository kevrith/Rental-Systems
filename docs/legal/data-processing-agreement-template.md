# Data Processing Agreement — template

**Status: drafting template, not a signable document.** Every bracketed field
below (`[LIKE THIS]`) must be filled in, and the whole document must be
reviewed by a qualified advocate before it is offered to a single customer.
This was drafted from the actual system behaviour — what data the platform
processes, how, and under which controls — cross-checked against the Kenya
Data Protection Act, 2019 and its 2021 regulations, with GDPR-shaped clauses
included because an enterprise buyer's own legal team will look for them by
name even where Kenyan law does not require the identical wording. It is not
a substitute for counsel, and nothing here should be represented to a customer
as legal advice.

---

## Data Processing Agreement

This Data Processing Agreement ("**DPA**") is entered into between:

**[RENTFLOW LEGAL ENTITY NAME]**, a company incorporated in Kenya with
registration number **[REGISTRATION NUMBER]** and registered address
**[REGISTERED ADDRESS]** ("**Processor**", "**we**", "**us**"),

and

**[CUSTOMER LEGAL ENTITY NAME]**, registration number
**[CUSTOMER REGISTRATION NUMBER]**, registered address
**[CUSTOMER REGISTERED ADDRESS]** ("**Controller**", "**Customer**", "**you**"),

each a "**Party**" and together the "**Parties**".

This DPA supplements the [Terms of Service / Master Subscription Agreement —
**LINK**] (the "**Agreement**") between the Parties and applies whenever the
Processor processes Personal Data on the Controller's behalf in connection
with the RentFlow service.

### 1. Definitions

Terms not defined here have the meaning given in the Kenya Data Protection
Act, 2019 ("**DPA 2019**"). Where the Customer's own compliance obligations
also draw on the EU General Data Protection Regulation ("**GDPR**"), the
Parties agree the GDPR's equivalent definitions (Controller/Processor,
Personal Data, Processing, Data Subject) apply consistently with those in the
DPA 2019.

- "**Personal Data**" means any information relating to an identified or
  identifiable natural person processed by the Processor on the Controller's
  behalf through the Service — principally, a tenant's name, phone number,
  national ID number, email address, physical address, payment history, and
  any photograph or document uploaded in connection with a tenancy.
- "**Service**" means the RentFlow rental management platform, as described
  in the Agreement.
- "**Sub-processor**" means any third party engaged by the Processor to
  process Personal Data in the course of providing the Service, as listed in
  `sub-processors.md` (published at **[PUBLIC URL]**) and incorporated here
  by reference.
- "**Data Subject**" means the natural person to whom Personal Data relates —
  principally the Controller's tenants, and where the Controller operates in
  agency mode, the property owners the Controller represents.

### 2. Roles of the Parties

2.1. As between the Parties, the Customer is the **Controller** and the
Processor is the **Processor** in respect of Personal Data the Customer's
tenants, staff and property owners submit to or generate within the Service.

2.2. The Processor processes Personal Data only:

(a) on the Customer's documented instructions, which the Parties agree
include the instructions embedded in the Customer's own configuration of the
Service (for example, which notification channels are enabled, or whether a
tenant portal invitation is sent); and

(b) to the extent required by Kenyan law, in which case the Processor will,
where legally permitted, inform the Customer of that legal requirement before
processing.

### 3. Nature, Purpose and Duration of Processing

3.1. **Nature and purpose.** The Processor processes Personal Data to provide
the Service: tenancy and lease management, rent invoicing and payment
collection (via M-Pesa), tenant and caretaker communication (SMS, WhatsApp,
email, push notification), document generation and storage, screening and
reference checks the Customer initiates, and the reporting and analytics
features described in the Service documentation.

3.2. **Categories of Data Subjects.** Tenants, guarantors, applicants,
property owners (in agency mode), the Customer's own staff and caretakers,
and vendors/contractors where the Customer records their contact details.

3.3. **Categories of Personal Data.** Name, phone number, email address,
national ID number, physical/residential address, employment details where
supplied during screening, payment and transaction history, lease documents,
photographs (ID documents, meter readings, inspection reports, maintenance
issues), GPS coordinates where a mobile user grants location access, and
device/session metadata (IP address, device identifier, login history).

3.4. **Special categories.** The Service is not designed to collect health
data, biometric data used for identification, or data revealing racial or
ethnic origin, political opinion, or religious belief. The Customer must not
enter such data into free-text fields (notes, descriptions) except where
strictly necessary and lawful, and the Processor accepts no liability for
special-category data the Customer chooses to enter against this instruction.

3.5. **Duration.** For the term of the Agreement, plus any retention period
set out in `data-retention-policy.md` in this directory, plus any period
required by the erasure and legal-hold provisions of that policy.

### 4. Sub-processing

4.1. The Customer authorises the Processor to engage the Sub-processors
listed in `sub-processors.md`, as that list stands at the date of this DPA
and as updated from time to time.

4.2. The Processor will give the Customer at least **[30]** days' notice
before adding a new Sub-processor that will process the Customer's Personal
Data, by email to the Customer's designated contact and/or by updating
`sub-processors.md` with a visible change log entry. The Customer may object
on reasonable data-protection grounds within that notice period; if the
Parties cannot resolve the objection, the Customer may terminate the affected
part of the Service without penalty.

4.3. The Processor remains liable to the Customer for a Sub-processor's
performance of its data protection obligations to the same extent the
Processor would be liable if performing those services directly.

### 5. Security Measures

The Processor implements and maintains technical and organisational measures
appropriate to the risk, including at minimum:

- **Encryption in transit** — TLS on every public endpoint.
- **Encryption at rest for third-party credentials** — per-organisation
  envelope encryption (see `docs/data-model.md`, "Sprint 26A"), so one
  customer's stored credentials cannot be decrypted using another's key even
  from a full database export.
- **Row Level Security** — every tenant-scoped database table is enforced at
  the PostgreSQL layer, not only in application code, so a missed
  authorization check cannot return another organisation's rows (see
  `docs/data-model.md`, "Multi-tenant isolation strategy").
- **Access control** — role-based permissions, audit logging of privileged
  actions, and multi-factor authentication (SMS OTP and/or WebAuthn) for
  operator accounts.
- **Rate limiting and abuse controls** on every authenticated and public
  endpoint (`app/core/rate_limit.py`).
- **Vulnerability management** — dependency scanning (`pip-audit`, `npm audit`)
  and static analysis (CodeQL) on every change, per `docs/owasp-top-10-checklist.md`.
- **Breach detection and notification** — a tracked, escalating process
  meeting the Kenya DPA 2019 section 43 72-hour notification standard (see
  §7 below).

Full detail is in `security-questionnaire-answers.md` in
`docs/procurement/`, which this DPA incorporates by reference and which the
Processor will keep current.

### 6. Assistance to the Controller

6.1. **Data subject requests.** The Processor provides the Customer with
tools to fulfil a Data Subject's export or erasure request without the
Processor's direct involvement (tenant portal self-service, and an
operator-initiated request path — see `app/services/privacy_service.py`).
Where a Data Subject contacts the Processor directly, the Processor will
redirect them to the Customer, as the Customer is the party responsible for
responding.

6.2. **Data protection impact assessments.** The Processor will provide
reasonably requested information about the Service's processing activities
to support a Customer DPIA, at the Customer's cost if the request requires
material additional work beyond what is already documented in the Service's
public documentation.

### 7. Personal Data Breach Notification

7.1. The Processor will notify the Customer without undue delay, and in any
case within **48 hours** of becoming aware, of any Personal Data Breach
affecting the Customer's Personal Data. This is a shorter window than the
Kenya DPA 2019's own 72-hour deadline for notifying the Data Commissioner,
deliberately: the Customer needs time within that 72-hour window to assess
and prepare its own notification to affected Data Subjects, which is the
Customer's obligation as Controller, not the Processor's.

7.2. Notification will include, to the extent then known: the nature of the
breach, the categories and approximate number of Data Subjects and records
affected, the likely consequences, and the measures taken or proposed.

7.3. This process is implemented in the Processor's own breach register
(`app/services/breach_service.py`), which tracks the same 72-hour clock
internally and escalates automatically at 48 and 72 hours — see
`docs/data-model.md`, "Sprint 26A" for how this is enforced in the system
rather than left to a person remembering.

### 8. International Transfers

8.1. Personal Data is hosted at **[HOSTING REGION — e.g. a Kenyan or
EU-based DigitalOcean region]**. Where a Sub-processor in `sub-processors.md`
is located outside Kenya, the Processor relies on **[MECHANISM — e.g.
standard contractual clauses, an adequacy finding, or the Sub-processor's own
DPA]** for that transfer, details of which are available on request.

8.2. The Customer acknowledges that SMS, WhatsApp and email delivery
inherently route message content through the relevant Sub-processor's global
infrastructure (Africa's Talking, Meta, Resend — see `sub-processors.md`),
and consents to that transfer as necessary for the Service's core
notification functionality.

### 9. Audit Rights

9.1. On reasonable written notice, and no more than once per 12-month
period (except following a Personal Data Breach affecting the Customer),
the Processor will make available the information reasonably necessary to
demonstrate compliance with this DPA, which may take the form of: a summary
of the current SOC 2 status (see `docs/procurement/soc2-readiness.md`), the
most recent penetration test summary (see
`docs/procurement/penetration-testing-policy.md`), or answers to a
reasonable supplementary questionnaire.

9.2. A full on-site or system-level audit by the Customer or its nominee is
available on commercially reasonable terms, at the Customer's cost, subject
to confidentiality obligations protecting other customers' data.

### 10. Deletion or Return of Data

On termination of the Agreement, the Processor will, at the Customer's
election, delete or make available for export all Personal Data processed
under this DPA within **[30]** days, except to the extent retention is
required by Kenyan law (see `data-retention-policy.md`'s statutory retention
table — principally financial and tax records, which Kenyan law requires be
kept regardless of the Agreement's termination).

### 11. Liability

Each Party's liability arising out of or in connection with this DPA is
subject to the limitations and exclusions of liability set out in the
Agreement, except that nothing in this DPA limits liability for a Party's
own breach of its obligations as Controller or Processor under applicable
data protection law where such liability cannot lawfully be limited.

### 12. Governing Law

This DPA is governed by the laws of Kenya, and the Parties submit to the
exclusive jurisdiction of the courts of Kenya, consistent with the Agreement.

---

**Signed for and on behalf of [RENTFLOW LEGAL ENTITY NAME]:**

Name: _______________________ Title: _______________________ Date: _______________

**Signed for and on behalf of [CUSTOMER LEGAL ENTITY NAME]:**

Name: _______________________ Title: _______________________ Date: _______________

---

## Drafting notes (remove before use)

- Every `[BRACKETED]` field must be filled before this is sent to a customer.
- §8.1's hosting region is not yet decided — cross-reference the actual
  DigitalOcean deployment region once one exists in production, since a real
  DPA cannot say "configurable" to a customer's legal team.
- §4.2's 30-day notice period, §7.1's 48-hour internal breach window, and
  §10's 30-day post-termination deletion window are reasonable defaults, not
  fixed requirements — counsel may want to negotiate these per customer.
- This template does not yet have GDPR Standard Contractual Clauses annexed.
  If a customer requires them (an EU-based agency operating in Kenya, for
  instance), that annex needs its own legal drafting pass — this template
  only signals awareness of the requirement (§8.1), it does not satisfy it.
