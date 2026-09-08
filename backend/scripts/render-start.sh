#!/usr/bin/env bash
#
# Entrypoint for the API service on Render's free tier.
#
# Two jobs in one container, because a free Render account gets web services
# and nothing else — background workers, cron jobs and pre-deploy commands are
# all paid features. So the Celery worker that raises rent invoices and sends
# reminders runs beside uvicorn here rather than as its own service.
#
# This is a cost decision with real trade-offs, and they are worth knowing:
#
#   * 512MB of RAM is shared between the API and the worker. `--concurrency=1`
#     and a per-child memory ceiling keep the worker from taking the API down
#     with it; a PDF-heavy month is what would push this over.
#   * A free web service sleeps after 15 minutes without a request, and a
#     sleeping service runs no scheduler. Something must ping it — see
#     .github/workflows/keepalive.yml.
#   * `--beat` embeds the scheduler in the worker. Correct at exactly one
#     instance, wrong at two: each would fire the same schedule.
#
# Set RUN_EMBEDDED_WORKER=false once the worker is its own paid service.
set -euo pipefail

echo "==> Running database migrations"
# Migrations run here rather than at build time because they need the live
# DATABASE_URL, which only exists now. `set -e` means a failed migration aborts
# the boot, so Render marks the deploy failed and keeps serving the previous
# version instead of running an API against a schema it does not match.
alembic upgrade head

if [ "${RUN_EMBEDDED_WORKER:-true}" = "true" ]; then
  echo "==> Starting embedded Celery worker + beat"
  celery -A app.tasks.celery_app worker \
    --beat \
    --loglevel=info \
    --concurrency=1 \
    --max-tasks-per-child=50 \
    --max-memory-per-child=200000 &
  worker_pid=$!

  echo "==> Starting API on port ${PORT:-8000}"
  uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
  api_pid=$!

  # Exit as soon as *either* dies, so Render restarts the container. Without
  # this the API would happily keep serving with a dead scheduler behind it,
  # and the first sign of trouble would be a month with no invoices.
  # `|| exit_code=$?` rather than a bare `wait -n`: under `set -e` a non-zero
  # wait aborts the script on the spot, and the log line below — the one thing
  # that says *which* process died — would never be printed.
  exit_code=0
  wait -n "$worker_pid" "$api_pid" || exit_code=$?
  echo "==> A child process exited (${exit_code}); shutting down so Render restarts us"
  kill "$worker_pid" "$api_pid" 2>/dev/null || true
  exit "$exit_code"
fi

echo "==> Starting API on port ${PORT:-8000} (worker runs elsewhere)"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
