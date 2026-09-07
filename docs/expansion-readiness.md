# Expansion Readiness — Uganda & Tanzania

Sprint 24, US-103. A technical and legal audit of what actually changes to
run RentFlow in Uganda or Tanzania, grounded in what's in this codebase
today — not a market-entry business case, which needs people on the ground
RentFlow doesn't have yet. Where this document says "needs research," that
research is the actual gap, not something I can substitute a guess for.

## 1. Mobile money — the biggest technical gap

`backend/app/core/config.py`'s `DARAJA_*` settings and
`mpesa_service.py` are Safaricom-specific: STK Push,
B2C payouts, and the callback contract are all Safaricom Daraja's own API
shape, and Safaricom operates only in Kenya (plus a joint venture in Ethiopia
— not a target market here). **Neither Uganda nor Tanzania can be reached
by pointing the existing `Daraja*` config at a different base URL** — each
needs its own integration:

| Market | Dominant mobile money | API |
|---|---|---|
| Uganda | MTN Mobile Money, Airtel Money | MTN MoMo API (Open API, OAuth2 + collections/disbursements), Airtel Money OpenAPI |
| Tanzania | Vodacom M-Pesa (Tanzania), Tigo Pesa, Airtel Money | Each telco publishes its own API; there is no single "Daraja for Tanzania" |

The good news: `payment_service.py` already separates the payment *method*
(cash, M-Pesa, bank transfer — Sprint 23) from settlement logic, and
`mpesa_service.py`'s STK-push/callback/idempotency shape (Redis `SET NX`,
webhook verification, receipt generation) is a template to copy, not
something the new integrations need to reinvent. Realistic scope: one new
`*_service.py` per telco API, each behind the same "record a
pending payment → webhook confirms → receipt fires" contract
`payment_service._confirm` already provides. This is a sprint-sized
technical project per country, not a config change.

## 2. SMS and WhatsApp — already covered

Africa's Talking (`AFRICAS_TALKING_*`) operates across Kenya, Uganda,
Tanzania, and several other African markets already — no new SMS integration
needed for either country. WhatsApp Business Cloud API is not
country-restricted (Meta's own infrastructure), so the existing
`WHATSAPP_API_TOKEN`/`WHATSAPP_PHONE_NUMBER_ID` setup extends unchanged,
modulo Meta's own business-account approval for the new phone number(s).

## 3. Tax compliance — Kenya-specific, no direct equivalent obligation

KRA eTIMS (`etims_service.py`) is a Kenya Revenue Authority requirement with
no Uganda or Tanzania equivalent built or assumed anywhere in this codebase.
Uganda's URA has its own EFRIS (Electronic Fiscal Receipting and Invoicing
Solution) and Tanzania's TRA has its own VFD/EFD regime — **both would be
new integrations, not an eTIMS config swap**, and neither is built. Whether
RentFlow's rental-income use case is even in scope for either regime is a
tax-law research question, not a code question — flag to Kelvin before any
Uganda/Tanzania eTIMS-equivalent work is scheduled.

## 4. Currency — a contained change, not a sweep

Money is already formatted through one function:
`frontend/src/lib/format.ts`'s `formatMoney`/`kes`, hardcoded to
`KES`/`en-KE`. Multi-currency support is a real feature (an
`Organization.currency` field, threading it through every PDF template,
formatting call, and the M-Pesa/mobile-money integrations' own currency
assumptions) but it is **not a sweep through the codebase** — the currency
formatting choke point already exists, so the surface area is one function
plus the templates and integrations that assume KES specifically (lease and
receipt PDF templates, the `KES ` literal prefix in a handful of WeasyPrint
templates — grep for `KES` before starting this work to enumerate them
precisely rather than guessing which ones).

## 5. Data residency — each country has its own law

- **Kenya** (current): Data Protection Act, 2019, enforced by the Office of
  the Data Protection Commissioner (ODPC). RentFlow's privacy policy
  (`/legal/privacy`, this sprint) is drafted against this law.
- **Uganda**: Data Protection and Privacy Act, 2019, enforced by the
  National Information Technology Authority-Uganda (NITA-U) via its Personal
  Data Protection Office. Requires data controller/processor registration.
- **Tanzania**: Personal Data Protection Act, 2022, enforced by the Personal
  Data Protection Commission (est. 2023) — the newest of the three regimes,
  meaning less enforcement precedent to go on.

None of the three laws (as of this writing) mandate that Kenyan-collected
data physically stay in-country, but Uganda's and Tanzania's own residents'
data would fall under their respective national laws the moment RentFlow
onboards a landlord or tenant there — meaning a second, market-specific
privacy policy addendum (not just relabeling the Kenya one), and likely a
local data-controller registration in each market. **This needs actual
local legal counsel in each target country** — this document flags the
requirement, it does not discharge it.

## 6. Pricing — a research framework, not a number

RentFlow has no research on Ugandan or Tanzanian rental-management pricing
norms, currency purchasing power, or competitor pricing (a real
market-pricing exercise needs people talking to landlords and agencies in
each market, which is outside what I can produce from this codebase). What
this document can offer is the framework to run that research:

- What do local competitors (if any exist in this category) charge, and in
  what currency/billing cycle?
- What's the actual ability-to-pay for a small landlord in each market —
  UGX/TZS equivalents of RentFlow Kenya's current KES pricing tiers won't
  necessarily map 1:1 in relative terms.
- Does the mobile-money integration cost structure (transaction fees per
  telco) change the unit economics enough to require a different pricing
  shape (e.g. flat fee vs. per-transaction) than Kenya's M-Pesa-based model?

## Summary — realistic sequencing

1. Legal: engage local counsel in each target market before onboarding a
   single real customer there — this is the actual blocker, not code.
2. Technical, in order of leverage: mobile money integration (biggest
   lift, market-specific per country), then currency support (contained),
   then a tax-authority integration only once the legal question in §3 is
   answered.
3. Business: run the pricing research in §6 in parallel with the legal
   work, since it doesn't block engineering.

Nothing in this codebase's architecture blocks expansion — the
integration-behind-a-service-interface pattern already used for payments,
SMS, and tax compliance is exactly the shape a second country's equivalents
would slot into. What's missing is the country-specific integrations
themselves and the legal groundwork, not a redesign.
