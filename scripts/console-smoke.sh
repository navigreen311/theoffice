#!/usr/bin/env bash
# console-smoke.sh - start the API and the console, verify every route, tear down.
#
# This exists because `next build` passing is not evidence the app runs. The console's
# revocation page compiled cleanly, type-checked cleanly, and threw at render because a
# React 19 hook does not exist in React 18. Only a real request found it.
#
# Runs on Linux and on Windows under Git Bash. Everything platform-specific is behind
# `pids_on_port` and `kill_pid`; the checks themselves are the same on both, which is
# the point - a smoke test that ran a different set of assertions in CI than a developer
# runs locally would be two tests wearing one name.
#
#   ./scripts/console-smoke.sh            # build the console first
#   ./scripts/console-smoke.sh --no-build # reuse an existing .next
#
# Configuration comes from .env when it exists, and from the environment when it does
# not - CI has no .env and should not need one.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8091}"
CONSOLE_PORT="${CONSOLE_PORT:-3001}"
BUILD=1
[ "${1:-}" = "--no-build" ] && BUILD=0

WORK="$(mktemp -d)"
COOKIE_JAR="$WORK/cookies.txt"
FAILURES=0
UNEXERCISED=0

say()  { printf '  %s\n' "$1"; }
step() { printf '\n==> %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
die()  { printf 'error: %s\n' "$1" >&2; exit 1; }

# A check that could not run is not a check that passed, and it does not get to be a
# quiet note either. Two of these hid in plain sight for three increments: the
# parameterised-route checks ran BEFORE the world was seeded, so on a fresh database
# they reported "not exercised" and the run still ended in "all checks passed". That is
# the same false green the CI test guard exists to prevent, in the script that is
# supposed to be the last line of defence.
notrun() { printf '  NOT EXERCISED %s\n' "$1"; UNEXERCISED=$((UNEXERCISED + 1)); }

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) OS_KIND=windows ;;
  *)                    OS_KIND=posix ;;
esac

# Which process is listening on a port. Three POSIX implementations because runners and
# developer machines do not agree on which of these is installed, and a lookup that
# silently finds nothing would leave a stale server running and make the next check
# fail against the wrong build.
pids_on_port() {
  local port="$1"
  if [ "$OS_KIND" = "windows" ]; then
    netstat -ano 2>/dev/null \
      | grep -E "[:.]${port}[[:space:]]" \
      | grep -i LISTENING \
      | awk '{print $NF}' | sort -u
    return
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -i "TCP:${port}" -sTCP:LISTEN 2>/dev/null | sort -u
  elif command -v ss >/dev/null 2>&1; then
    ss -lptnH "sport = :${port}" 2>/dev/null \
      | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u
  elif command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$port" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' | sort -u
  fi
}

kill_pid() {
  local pid="$1"
  if [ "$OS_KIND" = "windows" ]; then
    taskkill //PID "$pid" //F >/dev/null 2>&1 || true
    return
  fi
  kill "$pid" 2>/dev/null || true
}

kill_port() {
  local port="$1" pid
  for pid in $(pids_on_port "$port"); do
    kill_pid "$pid"
  done
  # A TERM that is ignored leaves the port bound, and the next start fails with an
  # error about the address rather than about the process that would not go.
  if [ "$OS_KIND" != "windows" ]; then
    local waited=0
    while [ -n "$(pids_on_port "$port")" ] && [ "$waited" -lt 5 ]; do
      sleep 1
      waited=$((waited + 1))
    done
    for pid in $(pids_on_port "$port"); do
      kill -9 "$pid" 2>/dev/null || true
    done
  fi
}

# Wait for a URL to answer, and FAIL LOUDLY if it never does.
#
# The previous version looped, broke on success, and then said "listening on $PORT"
# whether or not anything was. A server that never started produced a confident line
# followed by a cascade of unexplained failures, which is this script committing the
# error it exists to catch.
wait_for() {
  local url="$1" label="$2" logfile="$3" tries="${4:-40}"
  local i=0
  while [ "$i" -lt "$tries" ]; do
    if curl -fsS -o /dev/null "$url" 2>/dev/null; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  printf '  FAIL %s never answered %s after %ss\n' "$label" "$url" "$tries" >&2
  if [ -f "$logfile" ]; then
    printf '  --- last 30 lines of %s ---\n' "$logfile" >&2
    tail -30 "$logfile" >&2
  fi
  return 1
}

# shellcheck disable=SC2317  # invoked by the EXIT trap, which shellcheck cannot see.
# It began firing only once the Result block ended in explicit exits, at which point
# there is no fallthrough path into this function - the trap is the only caller, and
# that is the intent.
cleanup() {
  kill_port "$API_PORT"
  kill_port "$CONSOLE_PORT"
  rm -rf "$WORK"
}
trap cleanup EXIT

# .env when it exists, the environment when it does not. CI sets the DSNs directly and
# should not have to write a dotfile to satisfy a script.
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

: "${OFFICE_ADMIN_DSN:?OFFICE_ADMIN_DSN is not set and no .env was found}"
: "${OFFICE_APP_DSN:?OFFICE_APP_DSN is not set and no .env was found}"

# The project venv on either platform, then whatever python is on PATH. CI installs
# into the runner's interpreter and has no venv at all.
VPY="$ROOT/.venv/Scripts/python.exe"
[ -x "$VPY" ] || VPY="$ROOT/.venv/bin/python"
[ -x "$VPY" ] || VPY="$(command -v python3 || command -v python || true)"
[ -n "$VPY" ] || die "no python found: no .venv and nothing on PATH"

for tool in curl npx; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is required and not on PATH"
done

step "Ports"
kill_port "$API_PORT"; kill_port "$CONSOLE_PORT"
say "cleared $API_PORT and $CONSOLE_PORT"

step "Operations API"
"$VPY" -m broker serve --port "$API_PORT" >"$WORK/api.log" 2>&1 &
# /api/health requires a bearer token, so it answers 401 before a token exists. `curl
# -f` treats that as a failure, and the readiness check must not depend on being
# authorised - the question here is whether anything is listening at all.
if ! wait_for "http://127.0.0.1:$API_PORT/openapi.json" "the API" "$WORK/api.log" 40; then
  die "the Operations API did not start"
fi
say "listening on $API_PORT"

step "Operator token"
TOKEN="$("$VPY" - <<'PY' 2>/dev/null | tail -1
import asyncio, sys, uuid
sys.path.insert(0, ".")
import broker  # noqa: F401 - event-loop policy
from broker import humans
from broker.db import connection

async def main():
    async with connection() as conn:
        suffix = uuid.uuid4().hex[:8]
        hid, token = await humans.create_human(
            conn, display_name=f"smoke-{suffix}", email=f"smoke-{suffix}@example.invalid"
        )
        await humans.grant_role(conn, human_id=hid, role="ivan", granted_by=hid)
        print(token)

asyncio.run(main())
PY
)"
[ -n "$TOKEN" ] || { echo "could not issue a token" >&2; exit 1; }
# Defined here, next to the token, because two steps below used to be above the old
# definition after a reorder. Under `set -u` that produced an empty header and a
# comparison against a response the script never received, which read as a pass.
API_AUTH="Authorization: Bearer $TOKEN"
say "issued ${TOKEN:0:8}..."

step "Console"
if [ "$BUILD" -eq 1 ]; then
  (cd console && npx next build >"$WORK/console-build.log" 2>&1) \
    || { tail -40 "$WORK/console-build.log" >&2; die "next build failed"; }
  say "built"
fi
(cd console && OFFICE_API_URL="http://127.0.0.1:$API_PORT" \
  npx next start -p "$CONSOLE_PORT" >"$WORK/console.log" 2>&1 &)
if ! wait_for "http://127.0.0.1:$CONSOLE_PORT/login" "the console" "$WORK/console.log" 60; then
  die "the console did not start"
fi
say "listening on $CONSOLE_PORT"

ROUTES="/ /agents /audit /forge-map /revocations /ventures /proposals /instructions /packs /provisioning /knowledge /incidents /access"

step "Unauthenticated routes redirect"
for path in $ROUTES; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-redirs 0 \
    "http://127.0.0.1:$CONSOLE_PORT$path")"
  case "$code" in
    30*) say "$path -> $code" ;;
    *)   fail "$path returned $code; an unauthenticated page must not render" ;;
  esac
done

step "Sign in"
curl -s -c "$COOKIE_JAR" -o /dev/null -X POST -d "token=$TOKEN" \
  "http://127.0.0.1:$CONSOLE_PORT/api/session"
if grep -q '^#HttpOnly_' "$COOKIE_JAR"; then
  say "session cookie is httpOnly"
else
  fail "session cookie is not httpOnly - a script could read the token"
fi

# The `Secure` attribute must follow the protocol in use, not the build mode.
#
# It used to follow NODE_ENV, and `next start` sets that to production - so a local
# build over http emitted a Secure cookie that the BROWSER SILENTLY DISCARDED. The
# sign-in redirected to a page that bounced straight back to the login screen, which
# looks exactly like a rejected token. curl stores the cookie anyway, so every check in
# this script passed while the console was unusable in a browser.
SET_COOKIE="$(curl -s -i -X POST -d "token=$TOKEN"   "http://127.0.0.1:$CONSOLE_PORT/api/session" | grep -i '^set-cookie:' || true)"
case "$SET_COOKIE" in
  *Secure*)
    fail "the session cookie is marked Secure over http; a browser will discard it and the sign-in will loop back to the login page" ;;
  "")
    fail "no session cookie was set at all" ;;
  *)
    say "session cookie is not Secure over http, so a browser will keep it" ;;
esac

# And the other direction: behind a proxy terminating TLS, it MUST be Secure. Dropping
# it there is the one failure that must never happen quietly.
FORWARDED="$(curl -s -i -X POST -H "X-Forwarded-Proto: https" -d "token=$TOKEN"   "http://127.0.0.1:$CONSOLE_PORT/api/session" | grep -i '^set-cookie:' || true)"
case "$FORWARDED" in
  *Secure*) say "session cookie is Secure when the client hop is https" ;;
  *)        fail "the session cookie is NOT Secure behind an https proxy - the token would travel in the clear" ;;
esac

step "Authenticated routes render"
for path in $ROUTES; do
  code="$(curl -s -b "$COOKIE_JAR" -o "$WORK"/page.html -w '%{http_code}' \
    "http://127.0.0.1:$CONSOLE_PORT$path")"
  if [ "$code" = "200" ]; then say "$path -> 200"; else fail "$path returned $code"; fi
done

step "The token never reaches the browser"
for path in $ROUTES; do
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT$path" > "$WORK"/page.html
  if grep -qF "$TOKEN" "$WORK"/page.html; then
    fail "$path leaked the bearer token into the HTML"
  fi
done
say "no route leaked the token"

step "Seed a development world if the bridge is empty"
# Without Forges registered, Gate 0 refuses every run - correctly - and the console's
# most important screens have nothing to render. A smoke test that quietly settles for
# that reports a pass over four checks it never performed.
if [ "$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/forges")" = "[]" ]; then
  "$VPY" scripts/seed_dev_world.py
else
  say "the Forge registry is not empty"
fi

step "Seed a Pack if there is none"
# Without this the two new screens are skipped, and a check that quietly skips reports
# a pass it never performed. Idempotent: publishes only when no venture has a Pack.
if [ "$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/packs")" = "[]" ]; then
  "$VPY" - "$TOKEN" "$API_PORT" <<'PY' | sed 's/^/  /'
import json, sys, urllib.request
token, port = sys.argv[1], sys.argv[2]
source = open("packs/greenstone.yaml", encoding="utf-8").read()
body = json.dumps({"yaml_source": source, "pack_version": "smoke-1.0.0"}).encode()
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/packs", data=body, method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as response:
    result = json.load(response)
print(f"published {result['venture_id']}@{result['pack_version']}")
PY
else
  say "a Pack already exists"
fi

step "Parameterised routes render"
# Ids come from the API, not from scraping the HTML. The first version of this grepped
# the page for /ventures/<slug> and matched a Next.js chunk filename, then reported a
# pass for a venture that does not exist. A check that can pass for the wrong reason is
# worse than no check.
AGENT_ID="$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/agents"   | grep -o '"office_agent_id": *"[^"]*"' | head -1 | grep -o '[0-9a-f-]\{36\}' || true)"
if [ -n "$AGENT_ID" ]; then
  code="$(curl -s -b "$COOKIE_JAR" -o /dev/null -w '%{http_code}'     "http://127.0.0.1:$CONSOLE_PORT/agents/$AGENT_ID")"
  if [ "$code" = "200" ]; then say "/agents/$AGENT_ID -> 200"; else fail "/agents/$AGENT_ID returned $code"; fi
else
  notrun "/agents/[id] - no agents in the registry"
fi

VENTURE="$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/ventures"   | grep -o '"venture_id": *"[^"]*"' | head -1 | sed 's/.*: *"//; s/"$//' || true)"
if [ -n "$VENTURE" ]; then
  code="$(curl -s -b "$COOKIE_JAR" -o /dev/null -w '%{http_code}'     "http://127.0.0.1:$CONSOLE_PORT/ventures/$VENTURE")"
  if [ "$code" = "200" ]; then say "/ventures/$VENTURE -> 200"; else fail "/ventures/$VENTURE returned $code"; fi
else
  notrun "/ventures/[id] - no venture appears in the directory"
fi

# A venture that does not exist must 404 rather than render zeroes that look like data.
code="$(curl -s -b "$COOKIE_JAR" -o /dev/null -w '%{http_code}'   "http://127.0.0.1:$CONSOLE_PORT/ventures/definitely-not-a-venture")"
if [ "$code" = "404" ]; then
  say "unknown venture -> 404"
else
  fail "unknown venture returned $code; an empty dashboard for a mistyped venture is indistinguishable from a real one that has not started"
fi

step "Pack Editor and Provisioning Console"
# Both are parameterised on a venture that must actually have a Pack. Deriving the id
# from /api/packs rather than /api/ventures matters: a venture in the directory with no
# Pack 404s on both screens by design, and asserting 200 against one of those would be
# asserting the wrong thing.
PACK_VENTURE="$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/packs"   | grep -o '"venture_id": *"[^"]*"' | head -1 | sed 's/.*: *"//; s/"$//' || true)"
if [ -n "$PACK_VENTURE" ]; then
  for path in "/packs/$PACK_VENTURE" "/provisioning/$PACK_VENTURE"; do
    code="$(curl -s -b "$COOKIE_JAR" -o "$WORK"/page.html -w '%{http_code}'       "http://127.0.0.1:$CONSOLE_PORT$path")"
    if [ "$code" = "200" ]; then say "$path -> 200"; else fail "$path returned $code"; fi
  done

  # The editor must render the Pack source, not an empty textarea. An editor that
  # silently loads nothing and then publishes is how a Pack gets replaced by a blank.
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/packs/$PACK_VENTURE"     > "$WORK"/pack.html
  if grep -q 'schema_version' "$WORK"/pack.html; then
    say "the editor loaded the live Pack source"
  else
    fail "the Pack editor rendered without the Pack source in it"
  fi
else
  notrun "the Pack editor and provisioning console - no venture has a Pack"
fi

# Both screens 404 for a venture with neither a Pack nor a run, for the same reason the
# venture dashboard does: an empty editor for a mistyped slug invites publishing a Pack
# under an id nobody meant.
for path in /packs/definitely-not-a-venture /provisioning/definitely-not-a-venture; do
  code="$(curl -s -b "$COOKIE_JAR" -o /dev/null -w '%{http_code}'     "http://127.0.0.1:$CONSOLE_PORT$path")"
  if [ "$code" = "404" ]; then say "$path -> 404"; else fail "$path returned $code"; fi
done

step "The gate ladder renders with a real run"
# The page above rendered its empty state. That proves nothing about the ladder or the
# four action forms, which is precisely the gap that shipped a React 19 hook into a
# React 18 app: it compiled, type-checked, and threw at render. So drive a real run
# through the API and render the page again.
#
# Gate 10's sign-off form is NOT exercised here: the real Greenstone Pack blocks at gate
# 4.5 on the compliance-officer capacity finding, so a run from this seed never reaches
# it. Said plainly rather than left as an unexplained gap in the output.
RUN_ID="$("$VPY" - "$TOKEN" "$API_PORT" "$PACK_VENTURE" <<'PY' | tail -1
import json, sys, urllib.request
token, port, venture = sys.argv[1], sys.argv[2], sys.argv[3]
base = f"http://127.0.0.1:{port}"
head = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def call(path, payload=None):
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(base + path, data=data, method="POST", headers=head)
    with urllib.request.urlopen(req) as response:
        return json.load(response)

runs = json.load(urllib.request.urlopen(urllib.request.Request(
    f"{base}/api/provisioning/runs?venture_id={venture}", headers=head)))
open_run = next(
    (r for r in runs if r["status"] in ("running", "blocked", "awaiting_human")), None
)
run_id = open_run["run_id"] if open_run else call(
    "/api/provisioning/runs", {"venture_id": venture})["run_id"]
call(f"/api/provisioning/runs/{run_id}/advance")
print(run_id)
PY
)"
if [ -n "$RUN_ID" ]; then
  say "run ${RUN_ID:0:8} advanced to its first stop"
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/provisioning/$PACK_VENTURE"     > "$WORK"/ladder.html
  code="$(curl -s -b "$COOKIE_JAR" -o /dev/null -w '%{http_code}'     "http://127.0.0.1:$CONSOLE_PORT/provisioning/$PACK_VENTURE")"
  [ "$code" = "200" ] || fail "the gate ladder returned $code"

  # Sixteen rows, not nine. A ladder that lists only what has happened shows a stopped
  # run as a tidy column of passes.
  # React renders `Gate {g.gate}` as separate text nodes with a comment between them,
  # so "Gate 9.5" never appears as a literal string. Counting the verdict labels is the
  # check that actually holds: sixteen rows, whatever has and has not run.
  rows="$(grep -o 'passed\|blocked\|awaiting a human\|not run' "$WORK"/ladder.html     | wc -l | tr -d ' ')"
  if [ "$rows" -ge 16 ]; then
    say "every gate has a verdict label ($rows across the ladder and the history table)"
  else
    fail "the ladder rendered $rows verdict labels; a ladder that lists only what has happened shows a stopped run as a tidy column of passes"
  fi
  if grep -q 'not run' "$WORK"/ladder.html; then
    say "gates that have not run say so, rather than being absent"
  else
    fail "no gate rendered as 'not run'"
  fi

  if grep -q 'awaiting a human' "$WORK"/ladder.html; then
    say "gate 4 renders as awaiting a human, not as blocked or passed"
  else
    fail "gate 4 did not render its own verdict - awaiting_human collapsed into something else"
  fi

  if grep -qi 'What did you review' "$WORK"/ladder.html; then
    say "the Gate 4 review form rendered"
  else
    fail "the Gate 4 review form did not render"
  fi

  # The review brief must be on the page before the form, not behind a disclosure.
  if grep -qi 'Unfilled positions' "$WORK"/ladder.html; then
    say "the review brief is expanded above the form"
  else
    fail "the review form rendered without the artifacts summary above it - that is a rubber-stamp machine"
  fi

  # Abandon what this script started, which also exercises the abort path.
  "$VPY" - "$TOKEN" "$API_PORT" "$RUN_ID" <<'PY' | sed 's/^/  /'
import json, sys, urllib.request
token, port, run_id = sys.argv[1], sys.argv[2], sys.argv[3]
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/provisioning/runs/{run_id}/abort",
    data=json.dumps({"note": "console smoke test"}).encode(), method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as response:
    print(json.load(response)["status"])
PY
else
  fail "could not start a provisioning run"
fi

step "Knowledge Base Manager"
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/knowledge" > "$WORK"/kb.html

# All five stores named. A Manager that quietly rendered four would be the version of
# this screen that was refused three times: a screen implying the thing exists.
missing_store=0
for store in "Forge Operating Instructions" "Compliance Library" "Business Playbooks"              "Persona Library" "Historical Records"; do
  grep -qF "$store" "$WORK"/kb.html || { fail "the Manager does not render $store"; missing_store=1; }
done
[ "$missing_store" -eq 0 ] && say "all five knowledge bases render"

# Denominators, not bare counts. "3 of 7" is the whole point of the screen; a list of
# entries with no denominator is a filing cabinet with search.
if grep -qE '[0-9]+ of [0-9]+' "$WORK"/kb.html; then
  say "coverage renders with denominators"
else
  fail "no coverage fraction on the page - a store count without a denominator cannot show a gap"
fi

# Which stores block, said on the screen rather than left to be learned at Gate 6.
if grep -qF "blocks provisioning at Gate 6" "$WORK"/kb.html    && grep -qF "advisory at Gate 6" "$WORK"/kb.html; then
  say "blocking and advisory stores are distinguished"
else
  fail "the Manager does not say which knowledge bases block provisioning"
fi

step "A persona body never reaches the browser"
# The column privilege makes a read fail server-side. This is the observable half: write
# a persona through the API with a distinctive body, then check every rendered page.
PERSONA_MARKER="smoke-persona-body-$$"
"$VPY" - "$TOKEN" "$API_PORT" "$PACK_VENTURE" "$PERSONA_MARKER" <<'PY' | sed 's/^/  /'
import json, sys, urllib.error, urllib.request
token, port, venture, marker = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/knowledge/personas",
    data=json.dumps({
        "venture_id": venture, "persona_name": f"Smoke {marker[-6:]}",
        "target_persona": "Regional broker with stale pocket listings",
        "persona_version": "1.0.0", "persona_body": {"disposition": marker},
    }).encode(),
    method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req) as response:
        body = response.read().decode()
    print("persona written" if marker not in body else "LEAK: the write echoed the body")
except urllib.error.HTTPError as error:
    print(f"could not write a persona: {error.code} {error.read().decode()[:120]}")
PY

leaked=0
for path in $ROUTES; do
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT$path" > "$WORK"/page.html
  if grep -qF "$PERSONA_MARKER" "$WORK"/page.html; then
    fail "$path leaked a persona body into the HTML"
    leaked=1
  fi
done
[ "$leaked" -eq 0 ] && say "no rendered page contains a persona body"

step "Access administration"
# The screen that removed the shell dependency. Until it existed, a deployed Office
# needed somebody with a terminal to create its second operator.
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/access" > "$WORK"/access.html
if grep -qi "Administrators" "$WORK"/access.html    && grep -qi "Add a person" "$WORK"/access.html    && grep -qi "Change a role" "$WORK"/access.html; then
  say "the access screen renders people, roles and the administrator count"
else
  fail "the access screen did not render its controls"
fi

# The smoke operator holds `ivan`, so they are the administrator the screen counts.
if grep -q "active" "$WORK"/access.html; then
  say "the administrator count rendered"
else
  fail "the administrator count did not render"
fi

# A second operator, created THROUGH THE API rather than through a python shell - which
# is the whole point of the increment. The token comes back once and must work.
NEW_TOKEN="$("$VPY" - "$TOKEN" "$API_PORT" <<'PY' | tail -1
import json, sys, urllib.error, urllib.request, uuid
token, port = sys.argv[1], sys.argv[2]
suffix = uuid.uuid4().hex[:8]
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/humans",
    data=json.dumps({
        "display_name": f"smoke-operator-{suffix}",
        "email": f"smoke-operator-{suffix}@example.invalid",
        "role": "venture_operator", "venture_id": "greenstone",
    }).encode(),
    method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req) as response:
        print(json.load(response)["token"])
except urllib.error.HTTPError as error:
    print(f"FAILED {error.code} {error.read().decode()[:120]}")
PY
)"
case "$NEW_TOKEN" in
  FAILED*) fail "could not create a second operator: $NEW_TOKEN" ;;
  "")      fail "creating a second operator returned no token" ;;
  *)
    code="$(curl -s -o /dev/null -w '%{http_code}'       -H "Authorization: Bearer $NEW_TOKEN"       "http://127.0.0.1:$API_PORT/api/health")"
    if [ "$code" = "200" ]; then
      say "a second operator was created through the API and their token works"
    else
      fail "the new operator's token returned $code"
    fi

    # And they must NOT be able to read the roster - who holds ivan is a map of whom to
    # compromise, and a venture operator has no business with it.
    code="$(curl -s -o /dev/null -w '%{http_code}'       -H "Authorization: Bearer $NEW_TOKEN"       "http://127.0.0.1:$API_PORT/api/humans")"
    if [ "$code" = "403" ]; then
      say "a venture operator is refused the roster"
    else
      fail "a venture operator read the roster ($code)"
    fi
    ;;
esac

step "Pagination reports a denominator"
# The audit explorer capped at 100 and said nothing about the rest, so "I searched and
# found nothing" was indistinguishable from "I looked at the most recent hundred".
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/audit?limit=5" > "$WORK"/audit.html
if grep -qE "showing (all [0-9]+|[0-9]+–[0-9]+ of [0-9]+|no matches)" "$WORK"/audit.html; then
  say "the audit explorer states what it did not show"
else
  fail "the audit explorer rendered no denominator - a truncated list that looks complete"
fi

step "The provisioning ceiling is stated, not discovered"
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/provisioning" > "$WORK"/prov.html
if grep -q '9.5' "$WORK"/prov.html && grep -qi 'held-out' "$WORK"/prov.html; then
  say "the console names gate 9.5 as the ceiling in this deployment"
else
  fail "the provisioning console does not say that no run can pass gate 9.5 - an operator would find out by clicking Advance nine times"
fi

step "The compliance page states a conclusion, not a count"
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/" > "$WORK"/home.html

# The copy that is the whole point of this page. Checked verbatim, because these
# sentences are the thing most likely to be "tightened" by somebody who does not know
# why they are long.
preserved=0
while IFS= read -r phrase; do
  grep -qF "$phrase" "$WORK"/home.html || { fail "compliance page lost: ${phrase:0:60}"; preserved=1; }
done <<'PHRASES'
An absence of findings from a check that did not run is not evidence.
Shown above incidents deliberately: a quiet incident list means nothing if the check producing it is stale.
Until Forges carry per-agent identity this ledger is the only per-agent record anywhere.
PHRASES
[ "$preserved" -eq 0 ] && say "the epistemic copy is present verbatim"

# The banner states a conclusion in one of its two forms. It never disappears: health
# communicated by the absence of a warning is indistinguishable from a warning that
# failed to render.
if grep -qF "Compliance posture is unverified, not clean" "$WORK"/home.html; then
  say "banner: unverified, stated as a conclusion"
elif grep -qF "All controls verified within their max age" "$WORK"/home.html; then
  say "banner: all controls verified, stated rather than implied"
else
  fail "the compliance banner rendered in neither state - health by absence of a warning"
fi

# Every control explains itself to a reader who does not know the system.
for phrase in "Audit chain integrity" "Certification staleness" "Forge manifest reconciliation" "Backup restore drill"; do
  grep -qF "$phrase" "$WORK"/home.html || fail "control not named in human terms: $phrase"
done
if grep -qF "Re-hashes the ledger to prove no entry was altered" "$WORK"/home.html; then
  say "controls carry a description, not just an identifier"
else
  fail "controls render without their descriptions"
fi

# Frameworks on the compliance page - the largest gap the rebuild closed.
if grep -qF "Framework coverage by venture" "$WORK"/home.html; then
  say "framework coverage renders"
else
  fail "a compliance page with no compliance frameworks on it"
fi

# Every number with a denominator, and the time anchor without which a screenshot
# cannot be dated.
if grep -qE "of [0-9]+" "$WORK"/home.html; then
  say "metrics carry denominators"
else
  fail "a metric rendered without its denominator"
fi
if grep -qF "As of " "$WORK"/home.html; then
  say "the page states its as-of time"
else
  fail "no as-of timestamp - this cannot be used as evidence"
fi

step "Unverified controls render as unverified"
if grep -q 'never run\|stale' "$WORK"/home.html; then
  if grep -q 'text-bad\|text-critical' "$WORK"/home.html; then
    say "unhealthy controls carry a failing severity class"
  else
    fail "an unhealthy control rendered without a failing severity - a dashboard that shows 'never verified' quietly manufactures confidence"
  fi
else
  say "no unhealthy controls present to check"
fi

step "The ventures page answers where each venture is"
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/ventures" > "$WORK"/ventures.html

while IFS= read -r phrase; do
  grep -qF "$phrase" "$WORK"/ventures.html || fail "ventures page lost: ${phrase:0:60}"
done <<'PHRASES'
The Village carries several ventures at once. One venture per agent per shift.
V18 makes budget caps a required Pack field, so an unmetered venture cannot reach
PHRASES
say "the preserved copy is present verbatim"

# Pipeline state is a venture's most important attribute and used to appear nowhere.
if grep -qE "blocked at gate [0-9]|draft|validating|live|awaiting sign-off" "$WORK"/ventures.html; then
  say "ventures carry a pipeline status"
else
  fail "no venture reports where it is in the pipeline"
fi

# A blocked venture must name its gate. "Blocked" alone is not actionable.
if grep -qF "blocked at gate" "$WORK"/ventures.html; then
  if grep -qE "blocked at gate [0-9]" "$WORK"/ventures.html; then
    say "a blocked venture names its gate"
  else
    fail "a venture reports blocked without naming the gate"
  fi
fi

# Absence must not look like health: the unauthored portfolio ventures are listed.
if grep -qF "portfolio ventures have no Pack yet" "$WORK"/ventures.html; then
  say "the unauthored portfolio ventures are visible as absent"
else
  fail "four portfolio ventures are missing and the page does not say so"
fi

if grep -qF "New venture" "$WORK"/ventures.html; then
  say "a venture can be created from the page"
else
  fail "no way to create a venture"
fi

step "Every page has a route home"
# There was no way back to a dashboard from anywhere: the wordmark was not a link and
# nothing in the nav pointed at `/`.
missing_home=0
for path in /ventures /packs /knowledge /access /audit; do
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT$path" > "$WORK"/page.html
  grep -qF '>Dashboard<' "$WORK"/page.html || { fail "$path has no route home"; missing_home=1; }
done
[ "$missing_home" -eq 0 ] && say "every page links back to the dashboard"

if grep -qF ">Ventures<" "$WORK"/ventures.html; then
  say "the breadcrumb names where you are"
else
  fail "no breadcrumb on the ventures page"
fi

step "Dark mode is defined, not hardcoded"
# Every colour resolves through a CSS variable. A hex literal in a component is a
# colour that cannot invert, and one of them eventually renders a failure state in a
# reassuring grey.
if grep -rqE "#[0-9a-fA-F]{6}" "$ROOT/console/app" "$ROOT/console/components"      --include="*.tsx" 2>/dev/null; then
  fail "a hex colour literal exists in a component; dark mode cannot invert it"
else
  say "no hex literals in components"
fi
if grep -q "prefers-color-scheme: dark" "$ROOT/console/app/globals.css"; then
  say "a dark palette is defined"
else
  fail "no dark palette defined"
fi

step "Result"
if [ "$UNEXERCISED" -gt 0 ]; then
  say "$UNEXERCISED check(s) could not run"
fi
if [ "$FAILURES" -eq 0 ] && [ "$UNEXERCISED" -eq 0 ]; then
  say "all checks passed"
  exit 0
fi
if [ "$FAILURES" -gt 0 ]; then
  say "$FAILURES check(s) failed"
fi
# Unexercised is fatal, deliberately. Everything this script needs is either seeded by
# it or seeded by seed_dev_world.py, so a check that cannot run means the script is
# wrong about its own preconditions or the environment is broken. Both are worth
# stopping for, and neither is worth reporting as green.
exit 1
