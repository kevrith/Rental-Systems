# Database backups

Nightly `pg_dump` to disk, an encrypted copy in object storage, grandfather-
father-son retention, and a weekly drill that restores the newest backup into a
throwaway database and checks it. Sprint 0, "Set up automated database backups".

| File | What it is |
|---|---|
| `backup.sh` | Dump, checksum, encrypt, upload, prune. Idempotent, safe to run by hand. |
| `restore.sh` | Restore into a named database, or `--verify` into a scratch one. |
| `rentflow-backup.{service,timer}` | Nightly 02:15 UTC. |
| `rentflow-restore-check.{service,timer}` | Weekly restore drill, Sunday 03:30 UTC. |
| `backup.env.example` | Every setting, with the secrets blank. |
| `crontab.example` | Fallback for hosts without systemd. |

## Try it locally, right now

No server needed — this runs against the compose stack:

```bash
cp infra/backup/backup.env.example infra/backup/backup.env
chmod 600 infra/backup/backup.env
```

Edit `backup.env`: set `BACKUP_DATABASE_URL` to the same value as
`DATABASE_URL_SYNC` in `backend/.env`, point `BACKUP_DIR` somewhere writable
(`./var/backups`), and uncomment `BACKUP_DOCKER_SERVICE=postgres` so `pg_dump`
runs inside the Postgres container instead of needing a matching client on your
machine. Then:

```bash
./infra/backup/backup.sh              # take one
./infra/backup/restore.sh --latest --verify   # prove it restores
```

The verify run creates `restore_check_<timestamp>`, restores into it, asserts
the schema and Alembic head are present, prints row counts, and drops it. It
never touches the real database.

## Production install

Assumes the app is at `/opt/rentflow` and runs as the `rentflow` user. Adjust the
paths in the two `.service` files if yours differ.

```bash
sudo install -d -o rentflow -g rentflow -m 700 /var/backups/rentflow
sudo install -m 600 -o root -g root infra/backup/backup.env.example \
     /opt/rentflow/infra/backup/backup.env
sudo -e /opt/rentflow/infra/backup/backup.env        # fill in the real values

sudo cp infra/backup/rentflow-backup.{service,timer} /etc/systemd/system/
sudo cp infra/backup/rentflow-restore-check.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rentflow-backup.timer rentflow-restore-check.timer

sudo systemctl start rentflow-backup.service         # don't wait until 02:15
journalctl -u rentflow-backup -n 50
systemctl list-timers 'rentflow-*'
```

`postgresql-client` must be installed on the host and its major version must be
**>= the server's** — a `pg_dump` older than the server refuses to run, which is
how a backup job quietly dies after a Postgres upgrade. Pin the client to the
server's major version in your provisioning.

## Retention

Defaults keep 7 daily, 4 weekly, 6 monthly — about 17 dumps, roughly 6 MB at
today's schema and seed volume. The same rule prunes the local directory and the
offsite prefix, so the two copies do not drift. Files that don't match the
`<label>-<YYYYMMDD>T<HHMMSS>Z.dump` name are never deleted, so it is safe to keep
a manual dump in the same directory — pruning ignores it.

## Encryption

Set `BACKUP_GPG_RECIPIENT` to the key id of a GPG **public** key and every dump
is encrypted before it leaves the machine. Keep the private key off the server —
somewhere you will still have it when the server is gone, which is the situation
where you need it. The server can then write backups it cannot read back, so a
compromised droplet does not hand over every tenant's financial history.

Generate the pair somewhere else, and import only the public half:

```bash
gpg --quick-generate-key "RentFlow Backups <you@example.com>" default default never
gpg --export --armor you@example.com > rentflow-backups.pub    # copy to server
gpg --export-secret-keys --armor you@example.com > PRIVATE.asc # keep offline
sudo -u rentflow gpg --import rentflow-backups.pub             # on the server
```

Losing that private key means losing every encrypted backup. Store it the way you
would store the only copy of a company's books.

## When it is 3am and the database is gone

```bash
# 1. What have we got?
ls -lt /var/backups/rentflow/
aws --endpoint-url "https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com" \
    s3 ls "s3://$BACKUP_R2_BUCKET/backups/postgres/"

# 2. If the machine itself is gone, pull from offsite on a new one.
./restore.sh --from-offsite rentflow-prod-20260904T021500Z.dump --verify

# 3. Restore for real. --force is required; it prints the target first.
./restore.sh /var/backups/rentflow/rentflow-prod-20260904T021500Z.dump \
    --into "postgresql://…@localhost:5432/rentflow" --force

# 4. Confirm the schema matches the code before letting traffic in.
cd /opt/rentflow/backend && alembic current
```

Recovery point is the last nightly run, so up to 24h of transactions. If that is
too much once real money is flowing, the next step is WAL archiving for
point-in-time recovery — the tooling here is a prerequisite for it either way,
since PITR still needs periodic base backups.

## Monitoring

Set `BACKUP_HEARTBEAT_URL` to a dead-man's-switch (healthchecks.io and friends).
It is pinged only after a successful run, so silence pages you. Without it,
nothing tells you the backups stopped except needing one.

## Re-verified — Sprint 24

Re-ran the drill against the actual dev database (not a fresh schema) after
all of Sprints 13–23's migrations: `backup.sh` then
`restore.sh --latest --verify`. Passed — 81 tables, Alembic head
`7f8a9b0c1d2e` (the partner-integrations/bank-transfer migration, the
newest at time of writing), core financial tables round-tripped with their
real row counts intact. The scripts still work after ten sprints of schema
growth since Sprint 0 first wrote them; nothing here needed to change.

## Still to be provisioned

The scripts are done and tested. Two things need accounts and cannot be done
from the repo:

- a host to install the timers on (Sprint 0, DigitalOcean droplet);
- an R2 bucket and an API token scoped to it, separate from the app's file
  storage bucket, so an app-token leak cannot reach the backups.

Until `BACKUP_R2_BUCKET` is set, the script says so on every run and the dump
lives on one machine — which is not yet a backup.
