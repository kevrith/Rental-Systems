# RentFlow Public API (Sprint 19)

Read-only REST access to your organization's data for building your own
integrations — accounting sync, a custom dashboard, a data warehouse export.
For real-time events, see [Webhooks](#webhooks) below instead of polling.

Interactive, always-current documentation for every endpoint (including the
authenticated app API) is served by FastAPI itself at `/docs` (Swagger UI) and
`/redoc` on any running instance — e.g. `http://localhost:8000/docs` locally.
This file covers the parts specific to the public API: authentication,
pagination, and webhooks.

## Authentication

Create a key from **Developer → API keys** in the app, or `POST
/api/v1/developer/api-keys` while logged in. The raw key is shown exactly
once — store it somewhere safe, RentFlow only ever keeps a hash of it.

Send it on every request as a header, not a bearer token — the public API and
the logged-in app API are deliberately separate credential types:

```
X-API-Key: rf_live_9f8a2c1b_<secret>
```

A key is scoped to specific resources (`properties:read`, `units:read`,
`tenants:read`, `payments:read`, `invoices:read`) and can carry an expiry
date. Revoke a key any time from the same screen — revocation is immediate.

## Rate limits

1,000 requests/hour per key by default (an enterprise plan can raise this
per organization). Exceeding it returns `429` with the same error envelope
described below. The limit resets on a rolling one-hour window.

## Response shape

Every response — success or failure — has the same envelope:

```json
{
  "status": "ok",
  "data": { ... } | [ ... ],
  "errors": null,
  "meta": { "next_cursor": "...", "has_more": true }
}
```

`meta` is only present on list endpoints. An error looks like:

```json
{ "status": "error", "data": null, "errors": ["This API key lacks scope(s): payments:read"] }
```

## Endpoints

```
GET /api/v1/external/properties
GET /api/v1/external/properties/{id}
GET /api/v1/external/units
GET /api/v1/external/units/{id}
GET /api/v1/external/tenants
GET /api/v1/external/tenants/{id}
GET /api/v1/external/invoices
GET /api/v1/external/invoices/{id}
GET /api/v1/external/payments
GET /api/v1/external/payments/{id}
```

List endpoints accept:

- **Pagination** — `cursor` (from the previous page's `meta.next_cursor`) and
  `limit` (default 50, max 200). Pagination is keyset-based, not offset: a
  page is defined by "everything after this exact row," so it stays correct
  even while new rows are being inserted underneath a caller mid-scroll.
- **Sorting** — `sort=asc|desc` on `created_at` (default `desc`).
- **Field selection** — `fields=id,name` returns only those keys, to keep a
  response small when you only need a couple of columns.
- **Filtering** — resource-specific, e.g. `property_type`, `county` on
  properties; `status`, `tenancy_id` on invoices and payments. See `/docs`
  for the exact parameters per endpoint.

### cURL

```bash
curl -H "X-API-Key: rf_live_9f8a2c1b_..." \
  "https://your-instance/api/v1/external/payments?status=confirmed&limit=20"
```

### Python

```python
import httpx

response = httpx.get(
    "https://your-instance/api/v1/external/invoices",
    headers={"X-API-Key": "rf_live_9f8a2c1b_..."},
    params={"status": "pending"},
)
response.raise_for_status()
body = response.json()
invoices = body["data"]
```

### JavaScript

```javascript
const response = await fetch("https://your-instance/api/v1/external/tenants", {
  headers: { "X-API-Key": "rf_live_9f8a2c1b_..." },
});
const { data } = await response.json();
```

## Webhooks

Register an HTTPS endpoint from **Developer → Webhooks** (up to 10 per
organization) and choose which events to receive:

- `payment.received`
- `tenant.created`
- `lease.signed`
- `inspection.completed`
- `maintenance.status_changed`
- `invoice.generated`

Each delivery is a `POST` with a JSON body `{"event": "...", "data": {...},
"delivery_id": "..."}` and an `X-RentFlow-Signature: sha256=<hex>` header —
an HMAC-SHA256 of the raw request body using the endpoint's secret (shown
once at creation, and retrievable any time after from the same screen).
Verify it before trusting the payload:

```python
import hashlib
import hmac

def verify(secret: str, raw_body: bytes, signature_header: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```

A delivery that fails (a non-2xx response, a timeout, or an unreachable
host) is retried twice more with backoff — after one minute, then after ten
— for three attempts total. The full history for an endpoint, including the
response status and body RentFlow saw on each attempt, is in the deliveries
log on the same screen.

## What's not built yet

- A hosted sandbox with seeded test data — right now, testing means using
  your own trial account's real data.
- A separately branded docs site (`docs.rentflow.co.ke`) — `/docs` on the
  running instance is the interactive reference until that domain exists.
