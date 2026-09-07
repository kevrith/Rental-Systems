#!/usr/bin/env bash
#
# RentFlow — restore, and prove the backups actually restore.
#
#   restore.sh --latest --verify              # nightly drill: restore into a
#                                             # throwaway database, check it,
#                                             # drop it. Touches nothing real.
#   restore.sh <file> --into <postgres-url>   # restore into a named database
#   restore.sh --from-offsite <name> --verify # pull from R2 first
#
# An untested backup is a rumour. --verify is the whole point of this script:
# it is the only thing that catches a dump that has been silently empty for
# three weeks, and it is safe to run on a schedule.
#
# Restoring over an existing database requires --force, and prints what it is
# about to overwrite.

set -euo pipefail

log() { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${BACKUP_ENV_FILE:-$SCRIPT_DIR/backup.env}"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

BACKUP_DIR="${BACKUP_DIR:-/var/backups/rentflow}"
DOCKER_SERVICE="${BACKUP_DOCKER_SERVICE:-}"
COMPOSE_FILE="${BACKUP_COMPOSE_FILE:-$SCRIPT_DIR/../../docker-compose.yml}"
R2_PREFIX="${BACKUP_R2_PREFIX:-backups/postgres}"
R2_BUCKET="${BACKUP_R2_BUCKET:-${R2_BUCKET:-}}"

FILE=""
INTO=""
MODE="verify"
FORCE=0
OFFSITE_NAME=""

while [ $# -gt 0 ]; do
    case "$1" in
        --latest)        FILE="latest" ;;
        --from-offsite)  OFFSITE_NAME="${2:?--from-offsite needs a backup name}"; shift ;;
        --into)          INTO="${2:?--into needs a postgres URL}"; MODE="restore"; shift ;;
        --verify)        MODE="verify" ;;
        --force)         FORCE=1 ;;
        -h|--help)       sed -n '2,20p' "$0"; exit 0 ;;
        -*)              die "unknown option: $1" ;;
        *)               FILE="$1" ;;
    esac
    shift
done

DB_URL="${BACKUP_DATABASE_URL:-${DATABASE_URL_SYNC:-${DATABASE_URL:-}}}"
[ -n "$DB_URL" ] || die "no database URL: set BACKUP_DATABASE_URL (or DATABASE_URL) in $ENV_FILE"
DB_URL="${DB_URL/postgresql+asyncpg:/postgresql:}"
DB_URL="${DB_URL/postgresql+psycopg2:/postgresql:}"
DB_URL="${DB_URL/postgres+asyncpg:/postgresql:}"

# Split "postgresql://user:pw@host:port/dbname?opts" so we can swap the database
# without asking the operator to retype credentials.
url_base="${DB_URL%%\?*}"
url_query="${DB_URL#"$url_base"}"
url_prefix="${url_base%/*}"
url_dbname="${url_base##*/}"

s3() {
    : "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID required}" "${R2_ACCESS_KEY_ID:?}" "${R2_SECRET_ACCESS_KEY:?}"
    AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
    AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
    AWS_DEFAULT_REGION=auto \
    AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
    AWS_RESPONSE_CHECKSUM_VALIDATION=when_required \
    aws --endpoint-url "${BACKUP_S3_ENDPOINT:-https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com}" "$@"
}

# --- Locate the archive ----------------------------------------------------
if [ -n "$OFFSITE_NAME" ]; then
    [ -n "$R2_BUCKET" ] || die "--from-offsite needs BACKUP_R2_BUCKET"
    mkdir -p "$BACKUP_DIR"
    FILE="$BACKUP_DIR/$OFFSITE_NAME"
    log "downloading $OFFSITE_NAME from s3://$R2_BUCKET/$R2_PREFIX"
    s3 s3 cp --only-show-errors "s3://$R2_BUCKET/$R2_PREFIX/$OFFSITE_NAME" "$FILE"
    s3 s3 cp --only-show-errors "s3://$R2_BUCKET/$R2_PREFIX/$OFFSITE_NAME.sha256" "$FILE.sha256" || true
elif [ "$FILE" = "latest" ]; then
    FILE="$(ls -1t "$BACKUP_DIR"/*.dump "$BACKUP_DIR"/*.dump.gpg 2>/dev/null | head -n1 || true)"
    [ -n "$FILE" ] || die "no backups in $BACKUP_DIR"
fi
[ -n "$FILE" ] || die "no backup given: pass a file, --latest, or --from-offsite <name>"
[ -f "$FILE" ] || die "no such file: $FILE"

# --- Integrity -------------------------------------------------------------
if [ -f "$FILE.sha256" ]; then
    ( cd "$(dirname "$FILE")" && sha256sum --check --status "$(basename "$FILE").sha256" ) \
        || die "checksum mismatch on $FILE — the archive is corrupt, try another"
    log "checksum ok"
else
    log "WARN: no .sha256 beside $FILE, skipping integrity check"
fi

# --- Decrypt ---------------------------------------------------------------
# Decrypted plaintext goes in a 0700 temp dir and is removed on any exit path.
WORKDIR=""
cleanup() { [ -n "$WORKDIR" ] && rm -rf "$WORKDIR"; return 0; }
trap cleanup EXIT

if [ "${FILE%.gpg}" != "$FILE" ]; then
    command -v gpg >/dev/null 2>&1 || die "$FILE is encrypted but gpg is not installed"
    WORKDIR="$(mktemp -d)"
    chmod 700 "$WORKDIR"
    log "decrypting (needs the private key for this backup's recipient)"
    gpg --batch --yes --decrypt --output "$WORKDIR/archive.dump" "$FILE"
    ARCHIVE="$WORKDIR/archive.dump"
else
    ARCHIVE="$FILE"
fi

# --- Choose the destination ------------------------------------------------
psql_run() {
    local url="$1"; shift
    if [ -n "$DOCKER_SERVICE" ]; then
        docker compose -f "$COMPOSE_FILE" exec -T "$DOCKER_SERVICE" psql "$url" "$@"
    else
        psql "$url" "$@"
    fi
}

pg_restore_run() {
    local url="$1"; shift
    if [ -n "$DOCKER_SERVICE" ]; then
        docker compose -f "$COMPOSE_FILE" exec -T "$DOCKER_SERVICE" pg_restore -d "$url" "$@" < "$ARCHIVE"
    else
        pg_restore -d "$url" "$@" "$ARCHIVE"
    fi
}

if [ "$MODE" = "verify" ]; then
    SCRATCH="restore_check_$(date -u +%Y%m%d%H%M%S)"
    TARGET_URL="$url_prefix/$SCRATCH$url_query"
    ADMIN_URL="$url_prefix/postgres$url_query"
    log "creating scratch database $SCRATCH"
    psql_run "$ADMIN_URL" -v ON_ERROR_STOP=1 -q -c "CREATE DATABASE \"$SCRATCH\""
    # Always drop it, even if the restore below fails.
    drop_scratch() {
        psql_run "$ADMIN_URL" -q -c "DROP DATABASE IF EXISTS \"$SCRATCH\" WITH (FORCE)" >/dev/null 2>&1 || true
        cleanup
        return 0
    }
    trap drop_scratch EXIT
else
    TARGET_URL="$INTO"
    target_name="${TARGET_URL%%\?*}"; target_name="${target_name##*/}"
    if [ "$FORCE" -ne 1 ]; then
        die "refusing to overwrite database '$target_name' without --force"
    fi
    log "RESTORING OVER '$target_name' on ${TARGET_URL##*@} — existing objects will be dropped"
fi

# --- Restore ---------------------------------------------------------------
# --clean --if-exists so a re-run is idempotent; --no-owner because the dump was
# taken that way. pg_restore reports non-fatal notices as a non-zero exit, so
# capture the log and judge on the checks below rather than on the exit code.
restore_log="$(mktemp)"
set +e
pg_restore_run "$TARGET_URL" --clean --if-exists --no-owner --no-privileges --exit-on-error >"$restore_log" 2>&1
restore_rc=$?
set -e
if [ "$restore_rc" -ne 0 ]; then
    log "pg_restore exited $restore_rc:"
    tail -n 30 "$restore_log" >&2
    rm -f "$restore_log"
    die "restore failed"
fi
rm -f "$restore_log"
log "restored into ${TARGET_URL##*/}"

# --- Sanity checks ---------------------------------------------------------
# A dump that restores but arrives empty is the failure this is really guarding
# against, so assert on content: the public schema is populated, Alembic's head
# is present, and every table that carries money survived the round trip.
tables=$(psql_run "$TARGET_URL" -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public'" | tr -d '[:space:]')
[ "${tables:-0}" -ge 20 ] || die "only ${tables:-0} tables restored — the dump is not a full database"

alembic_head=$(psql_run "$TARGET_URL" -tAc \
    "SELECT version_num FROM alembic_version" 2>/dev/null | tr -d '[:space:]' || true)
[ -n "$alembic_head" ] || die "no alembic_version row — schema is incomplete"

log "checks passed: $tables tables, alembic head $alembic_head"

# Row counts are printed, not asserted upward — a fresh install legitimately has
# zero tenants. A *missing* table is different: that is a partial restore.
for t in organizations users properties units tenants tenancies invoices payments; do
    n=$(psql_run "$TARGET_URL" -tAc "SELECT count(*) FROM $t" 2>/dev/null | tr -d '[:space:]' || true)
    [ -n "$n" ] || die "core table '$t' is missing from the restored database"
    printf '    %-16s %s\n' "$t" "$n"
done

if [ "$MODE" = "verify" ]; then
    log "verification complete — scratch database dropped, nothing else touched"
else
    log "restore complete"
fi
