#!/usr/bin/env bash
#
# RentFlow — PostgreSQL backup.
#
# Dumps the database, checksums it, optionally encrypts it, ships it to
# Cloudflare R2, then prunes both copies on a grandfather-father-son schedule.
# Designed to run from the systemd timer in this directory, but it is an
# ordinary script: run it by hand and it behaves the same way.
#
# Deliberate choices:
#   * Custom format (-Fc), not plain SQL. It is compressed, and pg_restore can
#     restore a single table from it — during an incident you rarely want the
#     whole database back.
#   * The dump is written to a .part file and renamed only after pg_dump exits
#     0, so an interrupted run can never leave a truncated file that looks like
#     a valid backup.
#   * pg_dump can run inside the Postgres container (BACKUP_DOCKER_SERVICE), so
#     the client version always matches the server. A pg_dump older than the
#     server refuses to run, and that mismatch is the classic reason a backup
#     job silently stops working after a Postgres upgrade.
#   * Nothing here writes a credential to disk or to the log.
#
# Requires: bash 4+, GNU coreutils (date, sha256sum), pg_dump.
# Optional: docker (containerised pg_dump), aws CLI (offsite), gpg (encryption).

set -euo pipefail

log() { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Settings come from the environment. The systemd unit points EnvironmentFile at
# backup.env; an interactive run picks the same file up from beside the script.
ENV_FILE="${BACKUP_ENV_FILE:-$SCRIPT_DIR/backup.env}"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

BACKUP_DIR="${BACKUP_DIR:-/var/backups/rentflow}"
BACKUP_LABEL="${BACKUP_LABEL:-rentflow}"
KEEP_DAILY="${BACKUP_KEEP_DAILY:-7}"
KEEP_WEEKLY="${BACKUP_KEEP_WEEKLY:-4}"
KEEP_MONTHLY="${BACKUP_KEEP_MONTHLY:-6}"
R2_PREFIX="${BACKUP_R2_PREFIX:-backups/postgres}"
DOCKER_SERVICE="${BACKUP_DOCKER_SERVICE:-}"
COMPOSE_FILE="${BACKUP_COMPOSE_FILE:-$SCRIPT_DIR/../../docker-compose.yml}"
GPG_RECIPIENT="${BACKUP_GPG_RECIPIENT:-}"
HEARTBEAT_URL="${BACKUP_HEARTBEAT_URL:-}"
MIN_BYTES="${BACKUP_MIN_BYTES:-20480}"

# --- Connection ------------------------------------------------------------
# Reuse whichever URL the app already has. SQLAlchemy's "+driver" suffix is not
# valid libpq, so strip it: postgresql+asyncpg://… -> postgresql://…
DB_URL="${BACKUP_DATABASE_URL:-${DATABASE_URL_SYNC:-${DATABASE_URL:-}}}"
[ -n "$DB_URL" ] || die "no database URL: set BACKUP_DATABASE_URL (or DATABASE_URL) in $ENV_FILE"
DB_URL="${DB_URL/postgresql+asyncpg:/postgresql:}"
DB_URL="${DB_URL/postgresql+psycopg2:/postgresql:}"
DB_URL="${DB_URL/postgres+asyncpg:/postgresql:}"

# Everything after the credentials, for log lines. Never log $DB_URL itself.
DB_SAFE="${DB_URL##*@}"

# --- Naming ----------------------------------------------------------------
# UTC throughout. A backup filename is the only record of when it was taken, and
# a DST-shifting local clock can order two dumps wrongly or collide two names.
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DATE_TAG="${STAMP:0:8}"
BASENAME="${BACKUP_LABEL}-${STAMP}.dump"
TARGET="$BACKUP_DIR/$BASENAME"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# A failed run must not leave its half-written .part behind: the names are
# timestamped, so orphans would accumulate one per failure until the disk fills.
trap 'rm -f "$TARGET.part"' EXIT

# --- Dump ------------------------------------------------------------------
# --no-owner / --no-privileges: roles differ between production and the scratch
# database a restore drill runs in, and a restore should not fail over a GRANT.
dump_args=(--format=custom --compress=9 --no-owner --no-privileges)

if [ -n "$DOCKER_SERVICE" ]; then
    log "dumping $DB_SAFE via docker compose service '$DOCKER_SERVICE'"
    docker compose -f "$COMPOSE_FILE" exec -T "$DOCKER_SERVICE" \
        pg_dump "${dump_args[@]}" "$DB_URL" > "$TARGET.part"
else
    command -v pg_dump >/dev/null 2>&1 || die "pg_dump not found (install postgresql-client, or set BACKUP_DOCKER_SERVICE)"
    log "dumping $DB_SAFE with $(pg_dump --version)"
    pg_dump "${dump_args[@]}" --file="$TARGET.part" "$DB_URL"
fi

# A dump far smaller than a schema-only file means pg_dump wrote an error page
# or an empty database. Better to fail loudly now than at restore time.
size=$(stat -c %s "$TARGET.part")
[ "$size" -ge "$MIN_BYTES" ] || die "dump is only ${size} bytes (min ${MIN_BYTES}) — refusing to keep it"

mv "$TARGET.part" "$TARGET"
chmod 600 "$TARGET"
log "wrote $TARGET ($(numfmt --to=iec "$size" 2>/dev/null || echo "${size}B"))"

# --- Encrypt (optional) ----------------------------------------------------
# Public-key encryption on purpose: the server can create a backup it cannot
# read back, so a stolen droplet does not hand over every tenant's finances.
# Keep the private key off this machine.
if [ -n "$GPG_RECIPIENT" ]; then
    command -v gpg >/dev/null 2>&1 || die "BACKUP_GPG_RECIPIENT is set but gpg is not installed"
    gpg --batch --yes --trust-model always --encrypt --recipient "$GPG_RECIPIENT" \
        --output "$TARGET.gpg" "$TARGET"
    shred -u "$TARGET" 2>/dev/null || rm -f "$TARGET"
    TARGET="$TARGET.gpg"
    BASENAME="$BASENAME.gpg"
    log "encrypted to $TARGET for <$GPG_RECIPIENT>"
fi

# --- Checksum --------------------------------------------------------------
( cd "$BACKUP_DIR" && sha256sum "$BASENAME" > "$BASENAME.sha256" )

# --- Retention -------------------------------------------------------------
# Grandfather-father-son. Input is "<YYYYMMDD><TAB><id>" sorted newest first;
# output is the ids that have aged out. Because the input is sorted, the first
# entry seen for a week or a month is that period's newest backup, which is the
# one worth keeping.
select_expired() {
    local today_days tag id day age keep week month months
    local -A seen_week=() seen_month=()
    today_days=$(( $(date -u +%s) / 86400 ))
    while IFS=$'\t' read -r tag id; do
        [ -n "$tag" ] && [ -n "$id" ] || continue
        local iso="${tag:0:4}-${tag:4:2}-${tag:6:2}"
        day=$(( $(date -u -d "$iso" +%s) / 86400 ))
        age=$(( today_days - day ))
        keep=0

        (( age < KEEP_DAILY )) && keep=1

        week="$(date -u -d "$iso" +%G-%V)"
        if [ -z "${seen_week[$week]:-}" ]; then
            seen_week[$week]=1
            (( age < KEEP_WEEKLY * 7 )) && keep=1
        fi

        month="${tag:0:6}"
        if [ -z "${seen_month[$month]:-}" ]; then
            seen_month[$month]=1
            months=$(( ( $(date -u +%Y) * 12 + 10#$(date -u +%m) ) - ( 10#${tag:0:4} * 12 + 10#${tag:4:2} ) ))
            (( months < KEEP_MONTHLY )) && keep=1
        fi

        (( keep )) || printf '%s\n' "$id"
    done
}

# Pull the date tag back out of a name like rentflow-20260905T020000Z.dump[.gpg]
tag_of() { printf '%s' "$1" | sed -n 's/.*-\([0-9]\{8\}\)T[0-9]\{6\}Z\..*/\1/p'; }

local_index() {
    local f name
    for f in "$BACKUP_DIR"/*.dump "$BACKUP_DIR"/*.dump.gpg; do
        [ -e "$f" ] || continue
        name="$(basename "$f")"
        printf '%s\t%s\n' "$(tag_of "$name")" "$name"
    done | sort -r
}

pruned=0
while read -r name; do
    [ -n "$name" ] || continue
    rm -f "$BACKUP_DIR/$name" "$BACKUP_DIR/$name.sha256"
    log "pruned local $name"
    pruned=$((pruned + 1))
done < <(local_index | select_expired)

# --- Offsite ---------------------------------------------------------------
# A backup on the same droplet as the database is not a backup. R2 reuses the
# credentials the app already has for file storage; give the token its own
# bucket if you can, so an app-token leak cannot reach the backups.
R2_BUCKET="${BACKUP_R2_BUCKET:-${R2_BUCKET:-}}"
if [ -n "$R2_BUCKET" ]; then
    command -v aws >/dev/null 2>&1 || die "BACKUP_R2_BUCKET is set but the aws CLI is not installed"
    : "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID is required for offsite upload}"
    : "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID is required for offsite upload}"
    : "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY is required for offsite upload}"
    S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com}"

    # Checksum vars: recent AWS SDKs attach CRC32 trailers that R2 rejects.
    # BACKUP_S3_ENDPOINT exists so this can be pointed at a local S3 for
    # testing, or at another S3-compatible provider without touching the code.
    s3() {
        AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
        AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
        AWS_DEFAULT_REGION=auto \
        AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
        AWS_RESPONSE_CHECKSUM_VALIDATION=when_required \
        aws --endpoint-url "$S3_ENDPOINT" "$@"
    }

    dest="s3://$R2_BUCKET/$R2_PREFIX"
    s3 s3 cp --only-show-errors "$BACKUP_DIR/$BASENAME" "$dest/$BASENAME"
    s3 s3 cp --only-show-errors "$BACKUP_DIR/$BASENAME.sha256" "$dest/$BASENAME.sha256"
    log "uploaded $BASENAME to $dest"

    # Read the object back rather than trusting the exit code: this is the only
    # step that proves the offsite copy exists and is the size we sent.
    remote_size="$(s3 s3api head-object --bucket "$R2_BUCKET" --key "$R2_PREFIX/$BASENAME" \
        --query ContentLength --output text)"
    local_size="$(stat -c %s "$BACKUP_DIR/$BASENAME")"
    [ "$remote_size" = "$local_size" ] || die "offsite copy is $remote_size bytes, local is $local_size"

    while read -r key; do
        [ -n "$key" ] || continue
        s3 s3 rm --only-show-errors "$dest/$key" || true
        s3 s3 rm --only-show-errors "$dest/$key.sha256" || true
        log "pruned offsite $key"
    done < <(
        s3 s3api list-objects-v2 --bucket "$R2_BUCKET" --prefix "$R2_PREFIX/" \
            --query 'Contents[].Key' --output text 2>/dev/null \
        | tr '\t' '\n' \
        | sed -n 's#.*/##p' \
        | grep -E '\.dump(\.gpg)?$' \
        | while read -r name; do printf '%s\t%s\n' "$(tag_of "$name")" "$name"; done \
        | sort -r | select_expired
    )
else
    log "offsite upload skipped (BACKUP_R2_BUCKET unset) — this copy lives on one machine"
fi

# --- Heartbeat -------------------------------------------------------------
# Ping a dead-man's-switch (healthchecks.io, Better Stack, …) only on success.
# Nobody notices a backup that stopped running; everybody notices an alert.
if [ -n "$HEARTBEAT_URL" ]; then
    curl -fsS -m 10 --retry 3 "$HEARTBEAT_URL" >/dev/null && log "heartbeat sent" || log "WARN: heartbeat failed"
fi

log "backup complete: $BASENAME (${pruned} local file(s) pruned)"
