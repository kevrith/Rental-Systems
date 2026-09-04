# RentFlow Kenya

Multi-tenant rental management SaaS for the Kenyan market — built for individual
landlords, property management agencies, caretakers and tenants on a single
codebase.

One platform replaces the exercise book, the WhatsApp group and the spreadsheet:
rent tracking, M-Pesa collection and reconciliation, digital leases with
e-signatures, inspections, trust accounting and owner disbursement, KRA eTIMS
receipts, and a self-service portal for every party.

- [`masterplan.md`](masterplan.md) — product blueprint: modes, personas, 26 modules, pricing
- [`sprint-plan.md`](sprint-plan.md) — 12-month engineering roadmap, sprint by sprint
- [`docs/data-model.md`](docs/data-model.md) — entities, tenancy scoping and RLS policies

---

## Operating modes

The platform runs three modes on one codebase:

| Mode | Who | Shape |
|---|---|---|
| **Owner self-managed** | Individual landlord | Owner is both the account holder and the manager |
| **Agency** | Property management firm | Agency manages units on behalf of many owners, each with a read-only owner portal |
| **Dual** | Owner with a mixed portfolio | Some properties self-managed, others handed to an agency |

---

## Stack

**Backend** — Python 3.12 · FastAPI · SQLAlchemy 2 (async) · PostgreSQL 15 ·
Alembic · Celery + Redis · WeasyPrint (PDF) · boto3 (S3/R2) · Resend (email) ·
pywebpush

**Frontend** — React 19 · TypeScript · Vite · Tailwind 4 · TanStack Query ·
Zustand · React Hook Form + Zod · Recharts · lucide-react · vite-plugin-pwa
(offline caretaker app)

**Tooling** — ruff · black · mypy · pytest · oxlint · pre-commit · GitHub Actions

---

## Getting started

Requires Docker (with the Compose plugin). Everything else runs in containers.

```bash
git clone git@github.com:kevrith/Rental-Systems.git
cd Rental-Systems

cp .env.example .env                  # Postgres credentials, ports
cp backend/.env.example backend/.env  # SECRET_KEY, integrations
cp frontend/.env.example frontend/.env

./start.sh --build
```

`start.sh` brings up the stack, waits for Postgres and Redis to pass their
healthchecks, applies Alembic migrations and blocks until the API answers.

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000/api/v1 |
| API docs | http://localhost:8000/docs |

```bash
./start.sh              # start (migrations run automatically)
./start.sh --logs       # start, then follow logs
./start.sh --no-migrate # skip Alembic
./stop.sh               # stop, keep the database
./stop.sh --wipe        # stop and delete the Postgres/Redis volumes
```

### Environment

Two `.env` files hold secrets and are gitignored; the matching `.env.example`
files list every key. At minimum set `SECRET_KEY` in `backend/.env` to a long
random value:

```bash
openssl rand -hex 32
```

Every third-party integration degrades gracefully when its credentials are
absent — SMS and WhatsApp log to the console, M-Pesa simulates a checkout, and
file storage writes to local disk. The same code paths run either way, so
nothing is stubbed out during development.

---

## Layout

```
backend/
  app/
    api/v1/endpoints/   21 routers — auth, properties, tenants, billing,
                        agency, signatures, inspections, etims, vault,
                        vendors, renewals, portal, analytics, …
    core/               config, database, security, permissions, RLS
    models/             SQLAlchemy models
    schemas/            Pydantic request/response schemas
    services/           business logic (one module per domain)
    tasks/              Celery workers and scheduled jobs
    templates/          Jinja2 templates for generated PDFs
  alembic/versions/     11 migrations
  tests/                pytest suite
frontend/
  src/
    features/           23 feature modules, one per domain
    components/         shared UI
    api/ hooks/ lib/ store/
    sw.ts               service worker (offline caretaker PWA)
docs/
```

---

## Security

Tenant isolation is enforced **twice**, independently:

1. **Application layer** — every query is scoped to the caller's organization;
   cross-tenant access returns `403`, never `404`, so the API never leaks the
   existence of another tenant's records.
2. **PostgreSQL Row Level Security** — 23 policies enforce the same boundary in
   the database, so a bug in the application layer cannot become a data breach.

Also in place: JWT sessions with server-side revocation, 2FA, role-based
permissions, OTP-verified document signing, and an append-only audit log.

`detect-private-key` runs on every commit, and `.env` files are gitignored — no
secret is ever committed.

---

## Development

Run the backend tooling from `backend/` inside the virtualenv:

```bash
ruff check .        # lint
black .             # format
mypy app            # typecheck
pytest -q           # tests
alembic upgrade head
alembic revision --autogenerate -m "description"
```

Frontend, from `frontend/`:

```bash
npm run dev
npm run lint        # oxlint
npm run build       # tsc -b && vite build
```

Install the git hooks once so lint, format, typecheck and the secret scan run
before each commit:

```bash
pre-commit install
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the same checks
on `main` and `develop`: backend lint, format, typecheck, migrations and tests
against live Postgres and Redis services, plus frontend lint and a production
build.

---

## Status

| Phase | Scope | State |
|---|---|---|
| **1** — Core foundation | Auth and multi-tenancy, properties and units, tenants and leases, M-Pesa, caretaker PWA, tenant portal | Complete |
| **2** — Enterprise | Agency mode, trust accounting and disbursement, e-signatures and document vault, inspections, eTIMS and analytics, recurring tasks and renewals | Complete |
| **3** — Full platform | Maintenance and vendors (done) · screening and KYC, service charges, vacancy marketing, compliance calendar, vehicle and equipment rentals | In progress |
| **4** — Intelligence | Public API and webhooks, AI features, partner integrations | Planned |

Deployment infrastructure (DigitalOcean, Nginx and TLS, Cloudflare R2, Sentry,
automated backups) and live Safaricom Daraja credentials are pending — the code
for each is written and falls back to local behaviour until the keys exist.

---

## License

Proprietary. All rights reserved.
