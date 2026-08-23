#!/usr/bin/env bash
# bootstrap.sh — set up The Office for local development, end to end.
#
# Idempotent: safe to re-run. Creates the venv, installs deps, creates the
# database if absent, runs migrations, and runs the test suite.
#
#   ./scripts/bootstrap.sh            # full setup + tests
#   ./scripts/bootstrap.sh --no-test  # setup only
#   ./scripts/bootstrap.sh --reset    # DROP and recreate the database first
#
# Requires .env (copy from .env.example). Never prints a secret.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY311="${PY311:-py -V:Astral/CPython3.11.15}"
VENV="$ROOT/.venv"
RUN_TESTS=1
RESET_DB=0

for arg in "$@"; do
  case "$arg" in
    --no-test) RUN_TESTS=0 ;;
    --reset)   RESET_DB=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

die() { printf 'error: %s\n' "$1" >&2; exit 1; }
step() { printf '\n==> %s\n' "$1"; }

# --- env ----------------------------------------------------------------
[ -f "$ROOT/.env" ] || die ".env not found. Copy .env.example to .env and fill it in."

set -a
# shellcheck disable=SC1091
. "$ROOT/.env"
set +a

: "${OFFICE_ADMIN_DSN:?OFFICE_ADMIN_DSN not set in .env}"
: "${OFFICE_APP_DSN:?OFFICE_APP_DSN not set in .env}"
: "${OFFICE_APP_PASSWORD:?OFFICE_APP_PASSWORD not set in .env}"

# Derive the admin connection parts without echoing the password.
DB_NAME="$(printf '%s' "$OFFICE_ADMIN_DSN" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')"
ADMIN_NO_DB="$(printf '%s' "$OFFICE_ADMIN_DSN" | sed -E 's#/[^/?]+(\?.*)?$#/postgres#')"

# --- venv ---------------------------------------------------------------
step "Python environment"
if [ ! -d "$VENV" ]; then
  $PY311 -m venv "$VENV"
  echo "  created .venv"
else
  echo "  .venv exists"
fi

VPY="$VENV/Scripts/python.exe"
[ -x "$VPY" ] || VPY="$VENV/bin/python"
[ -x "$VPY" ] || die "venv python not found under $VENV"

"$VPY" -m pip install --quiet --upgrade pip
"$VPY" -m pip install --quiet -e ".[dev]"
echo "  dependencies installed ($("$VPY" --version))"

# --- database -----------------------------------------------------------
step "Database"
if [ "$RESET_DB" -eq 1 ]; then
  psql "$ADMIN_NO_DB" -q -c "DROP DATABASE IF EXISTS \"$DB_NAME\" WITH (FORCE)" >/dev/null
  echo "  dropped $DB_NAME"
fi

if psql "$ADMIN_NO_DB" -tAc \
     "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
  echo "  $DB_NAME exists"
else
  psql "$ADMIN_NO_DB" -q -c "CREATE DATABASE \"$DB_NAME\"" >/dev/null
  echo "  created $DB_NAME"
fi

# --- migrations ---------------------------------------------------------
step "Migrations"
"$VPY" -m alembic upgrade head
"$VPY" -m alembic current

# Ledger partitions for the current and next month. Idempotent.
psql "$OFFICE_ADMIN_DSN" -q -tAc \
  "SELECT ensure_ledger_partition(date_trunc('month', now())::date);
   SELECT ensure_ledger_partition((date_trunc('month', now()) + interval '1 month')::date);" \
  >/dev/null
echo "  ledger partitions ensured"

# --- verify -------------------------------------------------------------
step "Chain self-check"
psql "$OFFICE_ADMIN_DSN" -tAc \
  "SELECT 'ok=' || ok || ' checked=' || checked_count || ' :: ' || reason
     FROM audit_log_verify_chain()" | sed 's/^/  /'

# --- tests --------------------------------------------------------------
if [ "$RUN_TESTS" -eq 1 ]; then
  step "Tests"
  "$VPY" -m pytest -q
fi

step "Done"
cat <<'NEXT'
  Run tests again:   .venv/Scripts/python -m pytest -q
  Lint:              .venv/Scripts/python -m ruff check .
  Type check:        .venv/Scripts/python -m mypy broker client generators
  Verify the chain:  psql "$OFFICE_ADMIN_DSN" -c "SELECT * FROM audit_log_verify_chain()"
NEXT
