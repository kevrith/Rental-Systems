#!/usr/bin/env bash
#
# Stop the RentFlow stack.
#
# Usage:
#   ./stop.sh            stop the containers, keep the database
#   ./stop.sh --clean    also remove the containers and network
#   ./stop.sh --wipe     remove containers AND delete the Postgres/Redis volumes
#                        (destroys all local data — asks first)
#
set -euo pipefail

cd "$(dirname "$0")"

MODE="stop"

for arg in "$@"; do
  case "$arg" in
    --clean) MODE="clean" ;;
    --wipe) MODE="wipe" ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; RED=""; RESET=""
fi

info() { printf '%s==>%s %s\n' "$BOLD" "$RESET" "$1"; }
ok()   { printf '%s  ok%s %s\n' "$GREEN" "$RESET" "$1"; }
fail() { printf '%s  xx%s %s\n' "$RED" "$RESET" "$1" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail "docker is not installed or not on PATH"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  fail "neither 'docker compose' nor 'docker-compose' is available"
fi

case "$MODE" in
  stop)
    info "Stopping services (data is preserved)"
    "${COMPOSE[@]}" stop
    ok "Stopped. Start again with ./start.sh"
    ;;

  clean)
    info "Removing containers and network (data is preserved)"
    "${COMPOSE[@]}" down
    ok "Removed. Your database volume is still there."
    ;;

  wipe)
    printf '%sThis deletes the Postgres and Redis volumes — every local property,\n' "$RED"
    printf 'tenant, payment and uploaded file goes with them.%s\n\n' "$RESET"
    read -r -p 'Type "wipe" to confirm: ' CONFIRM
    if [ "$CONFIRM" != "wipe" ]; then
      echo "Cancelled — nothing was deleted."
      exit 0
    fi
    info "Removing containers, network and volumes"
    "${COMPOSE[@]}" down -v
    ok "Wiped. The next ./start.sh will build a fresh database."
    ;;
esac
