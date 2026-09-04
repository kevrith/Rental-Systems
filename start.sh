#!/usr/bin/env bash
#
# Start the RentFlow stack (Postgres, Redis, API, Celery worker + beat, frontend),
# apply any pending database migrations, and wait until the API answers.
#
# Usage:
#   ./start.sh              start everything and run migrations
#   ./start.sh --build      rebuild images first (after dependency changes)
#   ./start.sh --logs       follow logs once everything is healthy
#   ./start.sh --no-migrate skip the Alembic step
#
set -euo pipefail

cd "$(dirname "$0")"

BUILD=false
FOLLOW_LOGS=false
RUN_MIGRATIONS=true

for arg in "$@"; do
  case "$arg" in
    --build) BUILD=true ;;
    --logs) FOLLOW_LOGS=true ;;
    --no-migrate) RUN_MIGRATIONS=false ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

# --- colours (disabled when not a terminal) -----------------------------------
if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi

info()  { printf '%s==>%s %s\n' "$BOLD" "$RESET" "$1"; }
ok()    { printf '%s  ok%s %s\n' "$GREEN" "$RESET" "$1"; }
warn()  { printf '%s  !!%s %s\n' "$YELLOW" "$RESET" "$1"; }
fail()  { printf '%s  xx%s %s\n' "$RED" "$RESET" "$1" >&2; exit 1; }

# --- preflight ----------------------------------------------------------------
command -v docker >/dev/null 2>&1 || fail "docker is not installed or not on PATH"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  fail "neither 'docker compose' nor 'docker-compose' is available"
fi

# Both .env files hold secrets and are gitignored — the examples show what to set.
[ -f .env ] || fail "missing .env — copy .env.example to .env and fill it in"
[ -f backend/.env ] || fail "missing backend/.env — copy backend/.env.example and fill it in"

# --- bring the stack up -------------------------------------------------------
if [ "$BUILD" = true ]; then
  info "Building images"
  "${COMPOSE[@]}" build
fi

info "Starting services"
"${COMPOSE[@]}" up -d

# Compose waits on the healthchecks for postgres and redis, but the API needs a
# moment more before it will accept connections.
info "Waiting for Postgres and Redis"
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" ps --format '{{.Service}} {{.Health}}' 2>/dev/null \
      | grep -E '^(postgres|redis) ' | grep -qv healthy; then
    sleep 1
  else
    break
  fi
done
ok "Datastores are healthy"

# --- migrations ---------------------------------------------------------------
if [ "$RUN_MIGRATIONS" = true ]; then
  info "Applying database migrations"
  if "${COMPOSE[@]}" exec -T backend alembic upgrade head; then
    ok "Database is at the latest revision"
  else
    fail "migrations failed — check 'docker compose logs backend'"
  fi
fi

# --- wait for the API ---------------------------------------------------------
BACKEND_PORT="$(grep -E '^BACKEND_PORT=' .env | cut -d= -f2 || true)"
FRONTEND_PORT="$(grep -E '^FRONTEND_PORT=' .env | cut -d= -f2 || true)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

info "Waiting for the API to answer"
API_UP=false
for _ in $(seq 1 45); do
  if curl -fsS "http://localhost:${BACKEND_PORT}/api/v1/health" >/dev/null 2>&1; then
    API_UP=true
    break
  fi
  sleep 1
done

if [ "$API_UP" = true ]; then
  ok "API is up"
else
  warn "API did not respond in time — check 'docker compose logs -f backend'"
fi

printf '\n%sRentFlow is running%s\n' "$BOLD" "$RESET"
printf '  Frontend    http://localhost:%s\n' "$FRONTEND_PORT"
printf '  API         http://localhost:%s/api/v1\n' "$BACKEND_PORT"
printf '  API docs    http://localhost:%s/docs\n' "$BACKEND_PORT"
printf '\n  Logs        ./start.sh --logs   (or: docker compose logs -f)\n'
printf '  Stop        ./stop.sh\n\n'

if [ "$FOLLOW_LOGS" = true ]; then
  "${COMPOSE[@]}" logs -f backend frontend celery_worker celery_beat
fi
