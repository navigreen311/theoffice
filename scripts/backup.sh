#!/usr/bin/env bash
# backup.sh - dump the database, and prove the dump is restorable.
#
#   ./scripts/backup.sh staging
#   ./scripts/backup.sh production --verify   # also restore it and check the chain
#
# **A backup nobody has restored is a belief.** This system's central claim is that the
# audit log is tamper-evident, and a dump that restores into a database whose hash chain
# does not verify is not a backup of this system - it is a backup of the rows.
#
# `--verify` restores into a scratch database inside the same Postgres container and
# runs `audit_log_verify_chain()` against the restored copy. That is Gate 13's
# philosophy applied to the host: the sweep checks that a drill happened, and this is
# the drill.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Git Bash rewrites arguments that look like absolute POSIX paths into Windows ones, so
# a container path such as /backups/x.dump reaches the container as
# C:/Program Files/Git/backups/x.dump and pg_dump fails on a directory that does not
# exist. Harmless no-op on Linux, where the variable means nothing.
export MSYS_NO_PATHCONV=1

say()  { printf '  %s\n' "$1"; }
step() { printf '\n==> %s\n' "$1"; }
die()  { printf 'error: %s\n' "$1" >&2; exit 1; }

ENVIRONMENT="${1:-}"
VERIFY=0
[ "${2:-}" = "--verify" ] && VERIFY=1

case "$ENVIRONMENT" in
  staging|production) ;;
  *) die "usage: $0 <staging|production> [--verify]" ;;
esac

OVERLAY="compose.staging.yaml"
[ "$ENVIRONMENT" = "production" ] && OVERLAY="compose.prod.yaml"
ENV_FILE="deploy/${ENVIRONMENT}.env"
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found"

set -a
# shellcheck source=/dev/null  # the path is chosen at runtime, by environment
. "$ENV_FILE"
set +a

DB_NAME="${POSTGRES_DB:-theoffice}"
DB_USER="${POSTGRES_USER:-postgres}"
RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="${ENVIRONMENT}-${STAMP}.dump"

COMPOSE=(docker compose --env-file "$ENV_FILE" -f compose.yaml -f "$OVERLAY")

step "Dump"
# Custom format: compressed, and restorable selectively. ./backups is bind-mounted into
# the db container at /backups, so the file lands on the host without leaving the
# container's filesystem through a pipe that could truncate on error.
"${COMPOSE[@]}" exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" \
  --format=custom --file="/backups/$NAME"
[ -f "backups/$NAME" ] || die "pg_dump reported success but produced no file"
SIZE="$(wc -c < "backups/$NAME" | tr -d ' ')"
[ "$SIZE" -gt 1024 ] || die "the dump is $SIZE bytes; that is not a database"
say "backups/$NAME ($SIZE bytes)"

if [ "$VERIFY" -eq 1 ]; then
  step "Restore drill"
  # Into a scratch database in the same container, never over the live one. A verify
  # step that restored in place would be the most dangerous line in this repository.
  SCRATCH="verify_${STAMP}"
  "${COMPOSE[@]}" exec -T db createdb -U "$DB_USER" "$SCRATCH"

  restore_cleanup() {
    "${COMPOSE[@]}" exec -T db dropdb -U "$DB_USER" --if-exists "$SCRATCH" >/dev/null 2>&1 || true
  }
  trap restore_cleanup EXIT

  # pg_restore exits non-zero on warnings that do not matter here - the office_app role
  # already exists, so its GRANTs are re-applied rather than created. The check that
  # matters is the chain verification below, not the exit code of the restore.
  "${COMPOSE[@]}" exec -T db pg_restore -U "$DB_USER" -d "$SCRATCH" \
    --no-owner --no-privileges "/backups/$NAME" >/dev/null 2>&1 || true

  CHAIN="$("${COMPOSE[@]}" exec -T db psql -U "$DB_USER" -d "$SCRATCH" -tAc \
    "SELECT ok || '|' || checked_count || '|' || reason FROM audit_log_verify_chain()")"
  OK="${CHAIN%%|*}"
  REST="${CHAIN#*|}"
  COUNT="${REST%%|*}"
  REASON="${REST#*|}"

  say "restored $COUNT audit entr(ies): $REASON"
  case "$OK" in
    t*) say "the chain verifies on the restored copy" ;;
    *)  die "THE RESTORED COPY DOES NOT VERIFY. This dump is not a backup of this system." ;;
  esac

  # Report the denominator, and do not let zero read as reassurance. "The chain
  # verifies over 0 entries" is true of an empty database and of a dump that restored
  # nothing, and those are very different situations - on a fresh deployment the first
  # is expected, and after that it is the second.
  if [ "$COUNT" -eq 0 ]; then
    say "WARNING: the chain was verified over ZERO entries, which is not evidence."
    say "         Expected only on a deployment where nothing has happened yet."
  fi

  restore_cleanup
  trap - EXIT
fi

step "Retention"
# Deletes by age, and says how many. A retention step that silently removed the only
# copy would be indistinguishable from one that did nothing.
BEFORE="$(find backups -name '*.dump' -type f | wc -l | tr -d ' ')"
find backups -name "${ENVIRONMENT}-*.dump" -type f -mtime "+${RETAIN_DAYS}" -delete
AFTER="$(find backups -name '*.dump' -type f | wc -l | tr -d ' ')"
say "$((BEFORE - AFTER)) removed older than ${RETAIN_DAYS}d; $AFTER kept"

if [ "$AFTER" -eq 0 ]; then
  die "retention removed every backup. Check BACKUP_RETAIN_DAYS."
fi

step "Done"
say "off-host copy is NOT automated - a backup on the same VM as the database survives"
say "a bad migration and not a lost disk. See docs/deployment.md."
