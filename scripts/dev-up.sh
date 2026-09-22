#!/usr/bin/env bash
# dev-up.sh - a usable local instance, from whatever state the database is in.
#
#   ./scripts/dev-up.sh                  # seed if needed, start both servers, print a token
#   ./scripts/dev-up.sh --no-build       # reuse an existing .next
#   ./scripts/dev-up.sh --stop           # stop only what it started (recorded PIDs)
#   ./scripts/dev-up.sh --new-token      # reissue the operator token as well
#
# This exists because the test suite empties the database. Its fixtures delete
# `office_human`, the Forge registry and every venture-scoped table, which is correct -
# a suite that left rows behind would be a suite whose next run depended on its last -
# and it means a browser session dies every time the tests run. Re-seeding by hand three
# times is what produced this script.
#
# Idempotent. Seeds only what is missing, and reissues the token rather than failing
# when the operator already exists.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8080}"
CONSOLE_PORT="${CONSOLE_PORT:-3100}"
OPERATOR_EMAIL="${OPERATOR_EMAIL:-ivannextlevel@yahoo.com}"
# The name a NEW account is created with, and nothing else - this script never renames
# an account that exists. It defaulted to "Ivan", so a wiped database would have
# recreated the operator under the old spelling and silently undone a rename nobody
# would have thought to re-check. See decisions entry 103.
OPERATOR_NAME="${OPERATOR_NAME:-Ivan Green}"

BUILD=1
STOP=0
for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD=0 ;;
    --stop)     STOP=1 ;;
    --new-token) NEW_TOKEN=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '  %s\n' "$1"; }
step() { printf '\n==> %s\n' "$1"; }
die()  { printf 'error: %s\n' "$1" >&2; exit 1; }

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) OS_KIND=windows ;;
  *)                    OS_KIND=posix ;;
esac

pids_on_port() {
  local port="$1"
  if [ "$OS_KIND" = "windows" ]; then
    netstat -ano 2>/dev/null | grep -E "[:.]${port}[[:space:]]" | grep -i LISTENING \
      | awk '{print $NF}' | sort -u
    return
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -i "TCP:${port}" -sTCP:LISTEN 2>/dev/null | sort -u
  elif command -v ss >/dev/null 2>&1; then
    ss -lptnH "sport = :${port}" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u
  fi
}

# NOTHING IS KILLED BY PORT - decisions entry 91.
#
# This used to `taskkill //F` whatever listened on the API and console ports. On a machine
# running Docker Desktop, 8080 is forwarded by `com.docker.backend.exe` - the same process
# that forwards every other container's port, CRE Forge's included - so `dev-up.sh` would
# have killed Docker's backend and every container with it. That is why nobody used it.
#
# Now: each server this script starts has its PID written to $RUN_DIR. Stopping and
# restarting touch only those. A port held by anything else is reported by name and left
# alone, and the script refuses rather than guessing.
RUN_DIR="${TMPDIR:-/tmp}/office-dev"
mkdir -p "$RUN_DIR"

describe_port_holder() {
  local port="$1" pid name
  for pid in $(pids_on_port "$port"); do
    name=""
    if [ "$OS_KIND" = "windows" ]; then
      name="$(tasklist //FI "PID eq $pid" //FO CSV //NH 2>/dev/null | head -1 | cut -d, -f1 | tr -d '"')"
    else
      name="$(ps -p "$pid" -o comm= 2>/dev/null || true)"
    fi
    printf 'pid %s (%s) ' "$pid" "${name:-unknown}"
  done
}

stop_ours() {
  local label="$1" pidfile pid winpid
  pidfile="$RUN_DIR/$label.pid"
  [ -f "$pidfile" ] || return 1
  pid="$(cat "$pidfile")"
  if [ "$OS_KIND" = "windows" ] && [ -r "/proc/$pid/winpid" ]; then
    winpid="$(cat "/proc/$pid/winpid")"
    taskkill //PID "$winpid" //T //F >/dev/null 2>&1 || true
  fi
  kill "$pid" 2>/dev/null || true
  rm -f "$pidfile"
  return 0
}

# A port this script needs must be free, or held by the server this script started last time.
claim_port() {
  local label="$1" port="$2" var="$3"
  if [ -n "$(pids_on_port "$port")" ]; then
    stop_ours "$label" && sleep 2
  fi
  if [ -n "$(pids_on_port "$port")" ]; then
    die "port $port is held by $(describe_port_holder "$port")- which this script did not start, so nothing was stopped. Pick another: $var=<port> ./scripts/dev-up.sh"
  fi
}

[ -f "$ROOT/.env" ] || die ".env not found. Copy .env.example and fill it in."
set -a
# shellcheck source=/dev/null
. "$ROOT/.env"
set +a

VPY="$ROOT/.venv/Scripts/python.exe"
[ -x "$VPY" ] || VPY="$ROOT/.venv/bin/python"
[ -x "$VPY" ] || VPY="$(command -v python3 || command -v python || true)"
[ -n "$VPY" ] || die "no python found"

if [ "$STOP" -eq 1 ]; then
  step "Stopping"
  for label in api console; do
    if stop_ours "$label"; then
      say "stopped the $label this script started"
    else
      say "no $label recorded as started by this script - nothing stopped"
    fi
  done
  exit 0
fi

step "Schema"
"$VPY" -m alembic upgrade head >/dev/null
say "at head"

step "World"
# `seed_dev_world.py` clears and rebuilds what it owns, so running it when the world is
# already there is safe and cheap. Checking first only to keep the output honest about
# whether anything changed.
FORGES="$("$VPY" - <<'PY'
import os, psycopg
with psycopg.connect(os.environ["OFFICE_ADMIN_DSN"]) as conn, conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM forge_registry")
    print(cur.fetchone()[0])
PY
)"
if [ "$FORGES" = "0" ]; then
  "$VPY" scripts/seed_dev_world.py | sed 's/^/  /'
else
  say "$FORGES Forge(s) already registered"
fi

step "Business Pack"
"$VPY" - <<'PY' | sed 's/^/  /'
import asyncio, sys, uuid
sys.path.insert(0, ".")
import broker  # noqa: F401 - event-loop policy
from broker import packs
from broker.db import close_pool, connection

AUTHOR = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


async def main() -> None:
    async with connection() as conn:
        live = await packs.live(conn, "greenstone")
        if live is not None:
            print(f"greenstone already has {live.identity}")
        else:
            source = open("packs/greenstone.yaml", encoding="utf-8").read()
            stored = await packs.store(
                conn, yaml_source=source, pack_version="1.0.0", authored_by=AUTHOR
            )
            print(f"published {stored.identity}")
    await close_pool()


asyncio.run(main())
PY

step "Operator"
# Bootstrap when there is nobody. **Do not** reissue when there is, unless asked.
#
# This used to reissue on every run, which made restarting the servers and revoking the
# operator's token the same act. Restarting is something you do constantly - after a
# rebuild, after a migration, in the middle of debugging something else - and every one
# of those silently locked the person using the console out of it. The token survives a
# restart perfectly well; nothing about bringing servers up requires a new one.
#
# `--new-token` still reissues, because the token cannot be recovered - it is stored as a
# hash and returned exactly once - so "already exists" must not mean "you are locked out
# of your own dev instance". That is a thing you ask for, not a side effect.
TOKEN="$("$VPY" - "$OPERATOR_NAME" "$OPERATOR_EMAIL" "${NEW_TOKEN:-0}" <<'PY' | tail -1
import asyncio, sys
sys.path.insert(0, ".")
import broker  # noqa: F401
from broker import account_origin, audit, humans
from broker.db import close_pool, connection

name, email, reissue = sys.argv[1], sys.argv[2], sys.argv[3] == "1"


async def main() -> None:
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT human_id FROM office_human WHERE email = %s", (email,)
            )
            row = await cur.fetchone()

        if row is not None and not reissue:
            # The existing token still works. Saying so is the whole point of the
            # change: a restart that silently rotated it looked identical to one that
            # did not, right up until the login screen refused.
            print("KEEP")
            await close_pool()
            return

        if row is None:
            human_id, token = await humans.create_human(
                # A PERSON, declared (entry 151). This is the developer's own account:
                # it self-grants `ivan` two lines down, which is the documented
                # exception `assert_may_grant` otherwise forbids.
                conn, display_name=name, email=email, origin=account_origin.HUMAN,
            )
            # Self-granted, and only here. Every later grant names a different granter
            # because `assert_may_grant` forbids granting to yourself; this row is the
            # documented exception and is visible as one.
            await humans.grant_role(
                conn, human_id=human_id, role="ivan", granted_by=human_id
            )
            await audit.write_event(
                event_type="bootstrap_human_created",
                actor_type="human", actor_id=human_id, venture_id=None,
                subject={"email": email, "role": "ivan", "via": "dev-up"},
            )
        else:
            # `name` is deliberately not applied here. An account that exists keeps the
            # name it has: renaming is `humans.rename`, which refuses a name another
            # account holds and writes an audit event naming both - and a dev script
            # quietly restating a default would be a rename with neither.
            human_id = row[0]
            token = await humans.reissue_token(conn, human_id=human_id)
            await audit.write_event(
                event_type="console_token_reissued",
                actor_type="human", actor_id=human_id, venture_id=None,
                subject={"email": email, "via": "dev-up"},
            )
    print(token)
    await close_pool()


asyncio.run(main())
PY
)"
[ -n "$TOKEN" ] || die "could not issue a token"
if [ "$TOKEN" = "KEEP" ]; then
  say "${OPERATOR_EMAIL} — existing token still valid, not reissued"
else
  say "${OPERATOR_EMAIL} — token issued"
fi

step "Servers"
claim_port api "$API_PORT" API_PORT
claim_port console "$CONSOLE_PORT" CONSOLE_PORT

# `</dev/null` and `disown` matter as much as `nohup`. Without them the servers keep
# the shell's stdout open, so the terminal that ran this script never gets its prompt
# back even though both servers are up and the work is finished.
nohup "$VPY" -m broker serve --port "$API_PORT" </dev/null >/tmp/office-api-dev.log 2>&1 &
echo "$!" > "$RUN_DIR/api.pid"
disown $! 2>/dev/null || true
for _ in $(seq 1 40); do
  curl -fsS -o /dev/null "http://127.0.0.1:$API_PORT/api/live" 2>/dev/null && break
  sleep 1
done
curl -fsS -o /dev/null "http://127.0.0.1:$API_PORT/api/live" 2>/dev/null \
  || { tail -20 /tmp/office-api-dev.log >&2; die "the API did not start"; }
say "API on $API_PORT"

if [ "$BUILD" -eq 1 ]; then
  (cd console && npx next build >/tmp/office-console-build.log 2>&1) \
    || { tail -30 /tmp/office-console-build.log >&2; die "next build failed"; }
  say "console built"
fi

# Same treatment as the API. `npx` spawns a node tree, and without `</dev/null` it
# holds the calling terminal's stdout open: the script finishes, both servers are up,
# and the prompt never comes back.
(
  cd console || exit 1
  OFFICE_API_URL="http://127.0.0.1:$API_PORT" \
    nohup npx next start -p "$CONSOLE_PORT" \
    </dev/null >/tmp/office-console-dev.log 2>&1 &
  echo "$!" > "$RUN_DIR/console.pid"
  disown $! 2>/dev/null || true
)
for _ in $(seq 1 60); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$CONSOLE_PORT/login" 2>/dev/null)" = "200" ] && break
  sleep 1
done
[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$CONSOLE_PORT/login" 2>/dev/null)" = "200" ] \
  || { tail -20 /tmp/office-console-dev.log >&2; die "the console did not start"; }
say "console on $CONSOLE_PORT"

step "Sign in"
printf '  http://localhost:%s\n' "$CONSOLE_PORT"
if [ "$TOKEN" = "KEEP" ]; then
  printf '  Your existing token still works - this run did not change it.
'
  printf '
  Need a new one: ./scripts/dev-up.sh --new-token
'
else
  printf '  %s
' "$TOKEN"
  printf '
  Shown once, and not recoverable - it is stored as a hash.
'
  printf '  Restarting does not change it; --new-token does.
'
fi
printf '  Use localhost, not 127.0.0.1: the cookie is scoped to the host you sign in on.\n'
printf '  Stop with: ./scripts/dev-up.sh --stop\n'
