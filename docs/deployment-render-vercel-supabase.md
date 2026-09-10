# Deploying RentFlow — Vercel, Render (free) and Supabase

Three hosts, one for each tier:

| Tier | Host | What runs there |
| --- | --- | --- |
| Frontend | Vercel | The React SPA at `rent.kastra.co.ke`, served from the edge |
| Backend | Render (free) | FastAPI, plus the Celery worker and scheduler, at `api.rent.kastra.co.ke` |
| Database | Supabase | Postgres, reached over the session pooler |
| Cache / queue | Render Key Value | OTP codes, login lockouts, rate limits, Celery broker |
| File storage | Cloudflare R2 | Uploaded documents — see [Step 5](#step-5--object-storage) |

Object storage is a fourth account, and it is not optional. Render's disk is
ephemeral: without it, every lease, inspection photo and vault document is
deleted on the next deploy.

Work through the steps in order. Each one needs a value produced by the one
before it.

---

## Before you start: two things that will bite you

### 1. Supabase's Data API must be turned off

Supabase publishes every table in the `public` schema through PostgREST, and its
default privileges grant the `anon` role access to tables created there. Your
Alembic migrations create tables in `public`. The project's anon key is, by
design, public — it ships in any client that uses it.

Row Level Security covers 78 of RentFlow's 83 tables, so most of the schema
would refuse to answer. These five would not:

```
email_suppressions   organization_encryption_keys   security_breaches
task_runs            verification_tokens
```

`verification_tokens` holds live password-reset and email-verification tokens.
`organization_encryption_keys` holds the wrapped keys protecting customers' KRA
eTIMS credentials and accounting OAuth tokens. Either one being world-readable
is a full account-takeover path.

RentFlow never uses PostgREST — it connects straight to Postgres with
SQLAlchemy — so the Data API is pure attack surface here. **Turn it off in Step
1 and verify it in Step 8.**

### 2. A free Supabase project pauses after 7 days of inactivity

A paused project refuses connections until you restore it by hand from the
dashboard, and "inactivity" means no *database* traffic. The keepalive workflow
does not count: it hits a liveness endpoint that never queries Postgres. What
keeps the project awake is the Celery beat schedule, whose daily jobs all read
from the database — so this holds only while the embedded worker is actually
running. If the API starts returning connection errors after a quiet week, check
the Render logs for beat before anything else.

---

## Step 1 — Supabase

1. Create a project. Pick the region closest to Kenya (`eu-central-1` /
   Frankfurt is the usual choice; `ap-south-1` / Mumbai is comparable). Save the
   database password somewhere safe — it is shown once.

2. **Disable the Data API.** Project Settings → Data API → remove `public` from
   *Exposed schemas* and save. If your project offers a "Disable Data API"
   switch, use that instead. See the warning above for why this is mandatory.

3. Get the connection string: click **Connect** in the dashboard toolbar and
   choose **Session pooler**. It looks like:

   ```
   postgresql://postgres.abcdefghijklm:PASSWORD@aws-1-eu-central-1.pooler.supabase.com:5432/postgres
   ```

   Take the **session pooler on port 5432**, not the direct connection and not
   the transaction pooler:

   - The **direct connection** (`db.<ref>.supabase.co`) is IPv6-only on the free
     plan. Render has no IPv6 egress, so it simply cannot reach it.
   - The **transaction pooler** (port 6543) does not support prepared
     statements, which asyncpg uses by default and Alembic needs.

4. Turn that one string into the two the app wants. Same host, same credentials
   — the app speaks asyncpg, Alembic speaks psycopg2:

   ```bash
   DATABASE_URL=postgresql+asyncpg://postgres.abcdefghijklm:PASSWORD@aws-1-eu-central-1.pooler.supabase.com:5432/postgres
   DATABASE_URL_SYNC=postgresql+psycopg2://postgres.abcdefghijklm:PASSWORD@aws-1-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require
   ```

   Two details that cause silent failures:

   - **Never put `?sslmode=require` on the asyncpg URL.** SQLAlchemy passes
     query parameters straight through to `asyncpg.connect()`, which has no
     `sslmode` argument and raises `TypeError` on connect. asyncpg already
     defaults to `prefer`, so TLS happens anyway. Write `?ssl=require` if you
     want it explicit.
   - **URL-encode the password** if it contains `@ : / ? # [ ] %`. A raw `@`
     splits the URL in the wrong place and produces a baffling "host not found".

Nothing else is needed on Supabase. The migrations create the schema on first
boot, and they connect as `postgres`, which owns the tables and therefore
bypasses RLS — which is exactly what lets the Celery tasks and the M-Pesa
callback work across organisations.

---

## Step 2 — Cloudflare R2

Do this before Render, so the credentials are ready when Render asks.

1. Cloudflare dashboard → R2 → create a bucket, e.g. `rentflow-prod`. Keep it
   **private**; the app hands out signed URLs that expire after an hour.
2. R2 → Manage API tokens → create a token with **Object Read & Write** scoped
   to that bucket. Note the Access Key ID, Secret Access Key and your Account
   ID.

The free tier is 10GB of storage with no egress charges, which is why it beats
S3 here.

> **Using Supabase Storage instead?** It now works — `R2_ENDPOINT_URL` makes the
> storage backend point anywhere S3-compatible. Set `R2_ENDPOINT_URL` to
> `https://<project-ref>.storage.supabase.co/storage/v1/s3`, `R2_REGION` to your
> project's region, and leave `R2_ACCOUNT_ID` blank; keys come from Storage →
> Settings → S3 access keys. Verify a real upload end to end before trusting it:
> the whole flow depends on pre-signed `PUT` URLs, and that is the part of the
> S3 protocol third-party implementations most often get wrong. R2 is the path
> this code was built and tested against.

---

## Step 3 — Render

`render.yaml` in the repository root describes the whole backend, so this is a
blueprint deploy rather than clicking through forms.

1. Render dashboard → **New** → **Blueprint** → connect the GitHub repo and
   pick the branch. Render reads `render.yaml` and proposes an `rentflow-api`
   web service and an `rentflow-keyvalue` store.

2. Render prompts for every variable marked `sync: false`. Fill in:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | the asyncpg URL from Step 1 |
   | `DATABASE_URL_SYNC` | the psycopg2 URL from Step 1 |
   | `R2_ACCOUNT_ID` | Cloudflare account id |
   | `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | the R2 token pair |
   | `R2_BUCKET` | `rentflow-prod` |
   | `R2_ENDPOINT_URL` / `R2_REGION` | leave blank for R2 |
   | `AFRICAS_TALKING_*` | **required — login is OTP over SMS, so nobody can sign in without it** |
   | `RESEND_API_KEY` | transactional email |
   | `DARAJA_*` | M-Pesa; leave `DARAJA_ENVIRONMENT=sandbox` until Safaricom approves you for production |

   Anything you have no credentials for yet can be left blank. Every optional
   integration degrades cleanly — the AI lease analysis returns a clear 503,
   virus scanning marks uploads SKIPPED, push notifications no-op.

   `SECRET_KEY` and `METRICS_TOKEN` are generated by Render. **Do not rotate
   `SECRET_KEY` later**: it derives the key that encrypts customer eTIMS,
   portal and accounting credentials, and rotating it makes all of them
   unreadable.

3. Apply. The first build takes 5–10 minutes — WeasyPrint's pango/cairo stack is
   a lot of system packages. Then `render-start.sh` runs `alembic upgrade head`
   and starts uvicorn with the Celery worker beside it.

4. Note the assigned URL, `https://rentflow-api.onrender.com`.

### Why the backend runs on Docker

Render's native Python runtime has no pango or cairo, and WeasyPrint renders
every lease, invoice and receipt PDF against them. Docker is the only runtime
here that works — `render.yaml` already specifies it.

### Redis is load-bearing, not a cache

`rentflow-keyvalue` is created by the blueprint and wired in automatically, so
there is nothing to configure — but be clear about what it holds, because
"cache" understates it:

- **OTP codes.** Sign-in is OTP-over-SMS and the code lives only in Redis. No
  Redis, no logins — for anyone.
- **Login lockout counters and WebAuthn challenges.**
- **The Celery broker.** Queued tasks live here, so a restart loses whatever was
  queued at that moment. The scheduled jobs are all written to be safe to
  re-run, so the next run recovers.
- **Rate-limit counters**, which is the one part that fails *open* — the limiter
  deliberately lets traffic through rather than taking the API down when Redis
  is unreachable.

Render's free plan has no persistence, so a restart empties it. Everything above
is either short-lived or regenerated, so that is survivable; an in-flight login
just has to request a new code. Check the current free-plan size and retention
on Render's pricing page when you apply the blueprint — these limits move, and
the blueprint does not pin them.

### What the free plan costs you

- **The service sleeps after 15 minutes idle** and cold-starts in roughly 50
  seconds. The first person to open the app after a quiet night waits.
- **A sleeping service runs no scheduler.** No invoices on the billing day, no
  rent reminders, no lease-expiry alerts — silently. `.github/workflows/keepalive.yml`
  pings `/api/v1/health` every 10 minutes to prevent it. Set the repository
  variable `RENDER_API_URL` (Settings → Secrets and variables → Actions →
  Variables) to your API URL, or the workflow fails on every run.
- **512MB RAM and 0.1 CPU**, shared between the API and the worker. The worker
  runs at `--concurrency=1` with a memory ceiling so a runaway PDF job restarts
  the child rather than the container.
- **750 instance-hours a month** across all free services — one always-on
  service uses almost exactly that. Do not add a second free service.
- **No shell access**, which is why the super admin is created from your laptop
  in Step 7 rather than from a Render shell.

The upgrade path is written at the bottom of `render.yaml`. The first $7/mo goes
to a `starter` instance for the API: no sleeping, no cold start, no keepalive
workflow, and triple the RAM.

---

## Step 4 — Vercel

1. Vercel → **Add New** → **Project** → import the repo.
2. **Root Directory: `frontend`.** This is the one setting that matters; the
   rest is read from `frontend/vercel.json` (Vite preset, `npm ci`, output
   `dist`, SPA rewrite, cache headers).
3. Environment variable, for Production and Preview both:

   ```
   VITE_API_URL=https://rentflow-api.onrender.com/api/v1
   ```

   Change it to `https://api.rent.kastra.co.ke/api/v1` after Step 6.

   **`VITE_*` variables are baked into the bundle at build time.** Changing this
   value does nothing until you redeploy — there is no runtime config to edit.

4. Deploy, then note the URL, `https://rentflow.vercel.app`.

5. Go back to Render and set `CORS_ORIGINS`, `FRONTEND_URL`, `WEBAUTHN_ORIGIN`
   and `WEBAUTHN_RP_ID` to match. `CORS_ORIGINS` is parsed as JSON — brackets
   and double quotes included:

   ```
   CORS_ORIGINS=["https://rentflow.vercel.app"]
   FRONTEND_URL=https://rentflow.vercel.app
   WEBAUTHN_ORIGIN=https://rentflow.vercel.app
   WEBAUTHN_RP_ID=rentflow.vercel.app
   ```
   `CORS_ORIGINS=https://rentflow.vercel.app` without the brackets is the single
   most common way to make this fail: pydantic-settings rejects it and the
   service will not boot.

> **Preview deployments cannot call the API.** Every preview gets its own random
> `*.vercel.app` hostname, and `CORS_ORIGINS` is an exact-match list. Previews
> render but every request fails CORS. That is the right default — do not widen
> the list to `*.vercel.app`, which would let any Vercel project on the platform
> call your API with credentials.

---

## Step 5 — Object storage

Already done in Step 2, and the values went in during Step 3. This section
exists only to say why it is not skippable: **Render's filesystem is
ephemeral.** With `R2_*` blank the app falls back to `LOCAL_STORAGE_DIR` and
writes to container disk, which is wiped on every deploy, every restart and
every wake from sleep. It fails silently — uploads appear to work, then the
files are gone.

---

## Step 6 — Domains and DNS

The full reasoning is in [deployment-domains.md](deployment-domains.md). The
short version: RentFlow lives entirely on subdomains, and the existing Kastra
site at the apex is untouched.

1. **Vercel** → Project → Settings → Domains → add `rent.kastra.co.ke`. Vercel
   gives you a `CNAME` target; add it at your DNS provider.
2. **Render** → `rentflow-api` → Settings → Custom Domains → add
   `api.rent.kastra.co.ke`, and add the `CNAME` it gives you.
3. Wait for both certificates to issue (usually minutes).
4. Update the values that name a host, and redeploy each side:

   **Render:**
   ```
   FRONTEND_URL=https://rent.kastra.co.ke
   # Keep the Vercel backup URL so rentflow.vercel.app stays functional.
   CORS_ORIGINS=["https://rent.kastra.co.ke","https://rentflow.vercel.app"]
   WEBAUTHN_RP_ID=rent.kastra.co.ke
   WEBAUTHN_ORIGIN=https://rent.kastra.co.ke
   DARAJA_CALLBACK_BASE_URL=https://api.rent.kastra.co.ke
   OAUTH_CALLBACK_BASE_URL=https://api.rent.kastra.co.ke
   ```

   **Vercel:** `VITE_API_URL=https://api.rent.kastra.co.ke/api/v1`, then **redeploy**
   — the old API URL is compiled into the current bundle until you do.

   **GitHub:** set the `RENDER_API_URL` repository variable to
   `https://api.rent.kastra.co.ke`.

Changing `WEBAUTHN_RP_ID` invalidates every passkey already registered against
the old hostname. Do the domain move before customers enrol biometrics, not
after.

---

## Step 7 — Create the super admin

Render's free plan has no shell, so run this from your laptop against the
Supabase database. It needs `DATABASE_URL` and nothing else — no Redis, no
running API.

```bash
cd backend
export DATABASE_URL='postgresql+asyncpg://postgres.<ref>:<password>@aws-1-<region>.pooler.supabase.com:5432/postgres'
export SECRET_KEY='<the value Render generated — Environment tab>'
export SUPERADMIN_EMAIL='admin@kastra.co.ke'
export SUPERADMIN_PHONE='+2547XXXXXXXX'
read -rsp 'Super admin password: ' SUPERADMIN_PASSWORD && export SUPERADMIN_PASSWORD && echo

.venv/bin/python -m scripts.create_superadmin

unset SUPERADMIN_PASSWORD
```

`read -rsp` keeps the password out of your shell history. The phone number must
be reachable by SMS — sign-in sends an OTP to it, so a wrong number locks the
account out permanently.

The script is safe to re-run: an existing account is promoted in place rather
than duplicated, and the password is only touched if you also set
`SUPERADMIN_RESET_PASSWORD=true`.

---

## Step 8 — Verify

Work down this list. Each item catches a different class of misconfiguration.

```bash
API=https://api.rent.kastra.co.ke

# 1. The API process is up. Note this is a liveness check only — it returns
#    {"status":"ok"} without touching Postgres, so it passing does not prove
#    the database URL is right. Item 3 below and the sign-in test do that.
curl -fsS "$API/api/v1/health"

# 2. The Data API is off. This MUST fail — a 200 with JSON rows means
#    verification_tokens and the encryption keys are publicly readable.
curl -s "https://<project-ref>.supabase.co/rest/v1/verification_tokens?apikey=<anon-key>"

# 3. CORS names the real frontend. Look for access-control-allow-origin.
curl -sI -X OPTIONS "$API/api/v1/auth/login" \
  -H 'Origin: https://rent.kastra.co.ke' \
  -H 'Access-Control-Request-Method: POST' | grep -i access-control

# 4. /metrics is not world-readable.
curl -s -o /dev/null -w '%{http_code}\n' "$API/metrics"   # expect 401
```

Then, in a browser:

- [ ] `https://rent.kastra.co.ke` loads, and the apex `kastra.co.ke` still serves
      the existing Kastra site unchanged.
- [ ] `https://rentflow.vercel.app` also loads and calls the API correctly
      (backup URL check).
- [ ] Sign in end to end as the super admin. This exercises CORS,
      `FRONTEND_URL`, the database and Africa's Talking in one action — if the
      OTP SMS arrives and the session starts, most of the configuration is right.
- [ ] Upload a document, then reload and download it. Confirms R2 is wired up
      and not silently falling back to container disk.
- [ ] Render logs show `celery@... ready` and beat's `Scheduler: Sending due
      task ...`. If they do not, nothing scheduled will ever run.
- [ ] The keepalive workflow has a green run in the Actions tab.
- [ ] M-Pesa: the callback URL is reachable from outside your network.
      Safaricom's servers post to it directly, and a host that only resolves
      internally fails silently, leaving payments stuck pending.

---

## Where things break, and what it looks like

| Symptom | Cause |
| --- | --- |
| Service will not boot, `CORS_ORIGINS` in the traceback | Missing JSON brackets — it must be `["https://..."]` |
| `TypeError: connect() got an unexpected keyword argument 'sslmode'` | `?sslmode=require` on the asyncpg URL. Remove it, or use `?ssl=require` |
| Connection timeouts to Supabase | Using the direct connection (IPv6-only) instead of the session pooler |
| `prepared statement "__asyncpg_..." already exists` | Using the transaction pooler (6543). Move to the session pooler (5432) |
| Login page loads, every request fails CORS | Frontend built against a stale `VITE_API_URL` — redeploy Vercel |
| Uploads succeed, files vanish later | `R2_*` blank, so storage fell back to ephemeral container disk |
| No invoices raised, no reminders sent | The service slept, or the embedded worker died. Check keepalive and the Render logs |
| First request each morning takes ~50s | Free-plan cold start. This is the $7/mo fix |
| Supabase refuses all connections after a quiet week | Free project paused; restore it from the dashboard |
