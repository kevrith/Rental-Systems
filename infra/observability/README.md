# Observability stack

Local and small-deployment observability: traces (Jaeger), metrics
(Prometheus + Grafana), all wired against the app's own `OTEL_EXPORTER_OTLP_ENDPOINT`
and `/metrics` — no vendor lock-in, since both are standard protocols a managed
service (Grafana Cloud, Honeycomb, Datadog) can receive from the same app
config with only `OTEL_EXPORTER_OTLP_ENDPOINT` and a Prometheus scrape target
changed.

## Running it locally

From the repo root, merge this compose file with the main one so services can
see each other by name:

```bash
docker compose -f docker-compose.yml -f infra/observability/docker-compose.yml up
```

Then set in `backend/.env`:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

and restart the backend/worker/beat services (or your local `uvicorn`/`celery`
processes, if you run those on the host rather than in Docker).

| Service | URL | Notes |
|---|---|---|
| Jaeger UI | http://localhost:16686 | Traces. Search by service `rentflow-api` or `rentflow-worker`. |
| Prometheus | http://localhost:9090 | Raw metrics + query. |
| Grafana | http://localhost:3001 | `admin` / `admin` — **change this immediately**, see below. Port 3001 rather than Grafana's default 3000 so it doesn't collide with a JS dev server. |

The "RentFlow overview" dashboard loads automatically (Grafana provisioning,
`grafana/dashboards/rentflow-overview.json`) — request rate by status,
p95 latency by route, 5xx rate, and the health of the 27 Celery beat tasks read
straight from `TaskRun` via the `/metrics` endpoint's custom collector (see
`app/core/metrics.py`).

## If the backend runs on the host, not in a container

Point Prometheus at `host.docker.internal:8000` instead of `backend:8000` in
`prometheus.yml`, and add to the `prometheus` service in this file:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

(`host.docker.internal` resolves automatically on Docker Desktop; on native
Linux Docker it needs that `extra_hosts` line.)

## What is real here and what is not

This directory gives you a working local stack you can point a browser at
today. Two things it deliberately does **not** do, because they are decisions
for you, not defaults I should have picked:

- **It is not a production deployment.** `docker-compose.yml` files are for
  local development. A droplet running this in production wants Prometheus and
  Grafana data on persistent volumes with real backups (the `infra/backup/`
  scripts don't currently cover them), Grafana behind the same TLS-terminating
  proxy as the app rather than exposed on its own port, and the default
  `admin`/`admin` Grafana login replaced — set `GF_SECURITY_ADMIN_PASSWORD`
  from a real secret, not the placeholder in this file, before this ever runs
  anywhere reachable from the internet.
- **`METRICS_TOKEN` and Jaeger/Prometheus retention are unset here on
  purpose.** Local dev doesn't need them; production does. Set
  `METRICS_TOKEN` in `backend/.env` and mirror it into `prometheus.yml`'s
  commented-out `authorization` block before deploying — an open `/metrics`
  endpoint on a public droplet hands out route names and internal call volume
  for free.

## Extending it

- **Celery task metrics beyond beat-job health** — a per-task Prometheus
  counter (attempts, retries, time-in-queue) would need
  `celery-prometheus-exporter` or hand-rolled signal handlers in
  `app/tasks/celery_app.py`, alongside the `task_prerun`/`task_postrun` pair
  already there for request-id correlation. Not built here; the beat-job
  health gauges (`rentflow_task_*`) cover what actually pages someone today.
- **A managed backend instead of this stack** — set
  `OTEL_EXPORTER_OTLP_ENDPOINT` to the vendor's OTLP/HTTP ingest URL and point
  the vendor's Prometheus-remote-write or scrape config at `/metrics` with the
  `METRICS_TOKEN` bearer header. Nothing in `app/core/observability.py` or
  `app/core/metrics.py` is Jaeger- or self-hosted-Prometheus-specific.
