# Domains, subdomains and DNS

RentFlow is deployed under `kastra.co.ke`, a domain that already serves an
unrelated Kastra Enterprises site at its apex. Nothing here touches that site:
the apex `A`/`AAAA` records stay exactly as they are, and RentFlow lives
entirely on subdomains that do not exist yet.

## The records to add

| Host | Type | Points at | Serves |
| --- | --- | --- | --- |
| `app.kastra.co.ke` | A / AAAA / CNAME | the frontend host | the React app and every public page (landing, help centre, tenant portal, public listings) |
| `api.kastra.co.ke` | A / AAAA / CNAME | the API host | FastAPI, at `/api/v1` |

The existing apex records are left alone. Adding a subdomain never affects
what the apex resolves to — they are independent records in the same zone.

Two hosts rather than one is deliberate. The frontend is static files that a
CDN can cache at the edge; the API is a stateful origin that must not be
cached. Splitting them lets each be fronted by the right thing, and keeps a
frontend redeploy from touching the API's TLS certificate.

## Email is separate from hosting, and stays at the apex

The super admin signs in as `admin@kastra.co.ke`, not
`admin@app.kastra.co.ke`. Mail delivery is decided by `MX` records on a
domain; web hosting is decided by `A`/`CNAME` records. They are independent,
so a mailbox at the apex is unaffected by the site already served there, and
putting the mailbox on a subdomain would mean a second set of MX, SPF, DKIM
and DMARC records to maintain for no benefit.

The one place a subdomain *is* the right answer for mail is **outbound
sending**. Transactional mail (verification links, receipts, arrears notices)
should go out from a dedicated sending subdomain — `mail.kastra.co.ke` — so
that RentFlow's sending reputation is scored separately from whatever the
apex domain sends. A deliverability problem on one then cannot drag the other
down. See `docs/procurement/email-deliverability.md` for the SPF/DKIM/DMARC
records themselves.

## Backend environment for this layout

These are the settings whose values are domain-dependent. Everything else in
`backend/.env.example` is unaffected.

```bash
FRONTEND_URL=https://app.kastra.co.ke
CORS_ORIGINS=["https://app.kastra.co.ke"]

# Bare host, no scheme or port. A passkey registered against this value only
# works on this exact hostname — set it to the apex only if the app will ever
# be served from more than one subdomain.
WEBAUTHN_RP_ID=app.kastra.co.ke
WEBAUTHN_ORIGIN=https://app.kastra.co.ke

# Callback URLs must be reachable by the third party, so they point at the
# API host rather than the app host.
DARAJA_CALLBACK_BASE_URL=https://api.kastra.co.ke
OAUTH_CALLBACK_BASE_URL=https://api.kastra.co.ke

EMAIL_FROM=RentFlow <noreply@mail.kastra.co.ke>
SUPPORT_EMAIL=support@kastra.co.ke
```

The frontend needs `VITE_API_URL=https://api.kastra.co.ke/api/v1` at build
time — it is baked into the bundle, so it is a build argument, not a runtime
variable.

## Checks before going live

- `https://app.kastra.co.ke` and `https://api.kastra.co.ke` both serve valid
  certificates, and the apex still serves the existing site untouched.
- A login from a clean browser completes end to end — this exercises
  `CORS_ORIGINS`, `FRONTEND_URL` and SMS delivery in one go.
- The M-Pesa callback URL is reachable from outside your network. Safaricom's
  servers post to it directly; a host that only resolves internally fails
  silently, leaving payments pending.
