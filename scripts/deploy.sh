#!/usr/bin/env bash
# deploy.sh - build, migrate, start, and refuse to report success until it is true.
#
#   ./scripts/deploy.sh staging
#   ./scripts/deploy.sh production
#   ./scripts/deploy.sh staging --no-build     # reuse the images already built
#
# Reads deploy/<environment>.env, which is NOT in git and holds the DSNs, the Postgres
# password, the Vault token and the domain. See deploy/example.env.
#
# The order matters and is the whole content of this script.
#
#   1. migrate BEFORE starting the new API, because /api/ready compares the schema to
#      the revision the build expects and would otherwise never pass;
#   2. wait for readiness, and FAIL if it never comes - a deploy that reports success
#      while the container is restarting is a deploy that has told you nothing;
#   3. verify the audit chain afterwards, because a migration is the most plausible
#      thing to have broken it and the chain is what makes every other record credible.

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
BUILD=1
[ "${2:-}" = "--no-build" ] && BUILD=0

case "$ENVIRONMENT" in
  staging|production) ;;
  *) die "usage: $0 <staging|production> [--no-build]" ;;
esac

OVERLAY="compose.staging.yaml"
[ "$ENVIRONMENT" = "production" ] && OVERLAY="compose.prod.yaml"

ENV_FILE="deploy/${ENVIRONMENT}.env"
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found. Copy deploy/example.env and fill it in."

# Refuse a dirty tree. A deployment whose commit does not exist anywhere is a
# deployment nobody can reproduce, roll back to, or reason about after an incident.
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  git status --short >&2
  die "working tree is dirty. Commit or stash before deploying."
fi

REVISION="$(git rev-parse --short HEAD)"
export IMAGE_TAG="${IMAGE_TAG:-$REVISION}"

COMPOSE=(docker compose --env-file "$ENV_FILE" -f compose.yaml -f "$OVERLAY")

step "Deploying $ENVIRONMENT at $REVISION"
say "images tagged $IMAGE_TAG"

# Config is validated before anything is built or stopped, so a missing variable is a
# five-second failure rather than a half-applied deploy.
step "Configuration"
"${COMPOSE[@]}" config >/dev/null || die "compose configuration is invalid"
say "valid"

if [ "$BUILD" -eq 1 ]; then
  step "Build"
  "${COMPOSE[@]}" build
  say "built"
fi

step "Database"
"${COMPOSE[@]}" up -d db
for _ in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T db pg_isready >/dev/null 2>&1; then break; fi
  sleep 2
done
"${COMPOSE[@]}" exec -T db pg_isready >/dev/null 2>&1 || die "database never became ready"
say "up"

# Migrations run from the API image, so they use the same code as the build being
# deployed. A separate migration image is a second thing to keep in step, and a deploy
# where the two disagree migrates to a schema the API was not written for.
step "Migrations"
"${COMPOSE[@]}" run --rm --no-deps \
  -e OFFICE_ADMIN_DSN \
  -e OFFICE_APP_PASSWORD \
  api python -m alembic upgrade head
say "at head"

step "Start"
"${COMPOSE[@]}" up -d
say "started"

step "Readiness"
# The check this script exists for. /api/ready is 503 until the database answers AND
# the schema matches what this build expects, so a deploy that switched traffic without
# waiting would be serving from a container that is about to be restarted.
READY=0
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T api curl -fsS http://127.0.0.1:8080/api/ready >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done
if [ "$READY" -ne 1 ]; then
  printf '  --- api logs ---\n' >&2
  "${COMPOSE[@]}" logs --tail 50 api >&2 || true
  die "the API never became ready. Traffic has NOT been switched; the previous containers are still serving."
fi
say "ready"

step "Audit chain"
# A migration is the most plausible thing to have broken it, and the chain is what makes
# every other record in this system credible. Cheap to check, catastrophic to assume.
CHAIN="$("${COMPOSE[@]}" exec -T db psql -U "${POSTGRES_USER:-postgres}" \
  -d "${POSTGRES_DB:-theoffice}" -tAc \
  "SELECT ok || ' checked=' || checked_count || ' :: ' || reason FROM audit_log_verify_chain()")"
say "$CHAIN"
case "$CHAIN" in
  t*) ;;
  *) die "the audit chain does not verify after this deploy. Investigate before serving." ;;
esac

step "Control freshness"
# never_run and stale are not passes. Reported rather than fatal: on a first deploy every
# sweep is legitimately never_run, and failing here would make the first deploy
# impossible for a reason that is true of every first deploy.
"${COMPOSE[@]}" exec -T api python -m broker health || \
  say "controls are not all fresh - expected on a first deploy, investigate otherwise"

step "Done"
say "$ENVIRONMENT is serving $REVISION"
say "logs:   docker compose --env-file $ENV_FILE -f compose.yaml -f $OVERLAY logs -f"
say "backup: ./scripts/backup.sh $ENVIRONMENT"
