#!/usr/bin/env bash
# console-smoke.sh — start the API and the console, verify every route, tear down.
#
# Idempotent and self-cleaning: kills anything already on its ports, and kills what it
# started on exit however it exits.
#
# This exists because `next build` passing is not evidence the app runs. The console's
# revocation page compiled cleanly, type-checked cleanly, and threw at render because a
# React 19 hook does not exist in React 18. Only a real request found it.
#
#   ./scripts/console-smoke.sh            # build the console first
#   ./scripts/console-smoke.sh --no-build # reuse an existing .next

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8091}"
CONSOLE_PORT="${CONSOLE_PORT:-3001}"
BUILD=1
[ "${1:-}" = "--no-build" ] && BUILD=0

COOKIE_JAR="$(mktemp)"
FAILURES=0

say()  { printf '  %s\n' "$1"; }
step() { printf '\n==> %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; FAILURES=$((FAILURES + 1)); }

kill_port() {
  local port="$1" pid
  pid="$(netstat -ano 2>/dev/null | grep ":$port " | grep LISTENING | awk '{print $5}' | head -1 || true)"
  # Not `[ -n "$pid" ] && taskkill ... || true`: in that form the `|| true` also
  # swallows a failure of the test itself, which reads as if-then-else and is not.
  if [ -n "$pid" ]; then
    taskkill //PID "$pid" //F >/dev/null 2>&1 || true
  fi
}

cleanup() {
  kill_port "$API_PORT"
  kill_port "$CONSOLE_PORT"
  rm -f "$COOKIE_JAR"
}
trap cleanup EXIT

[ -f "$ROOT/.env" ] || { echo "error: .env not found" >&2; exit 1; }
set -a
# shellcheck disable=SC1091
. "$ROOT/.env"
set +a

VPY="$ROOT/.venv/Scripts/python.exe"
[ -x "$VPY" ] || VPY="$ROOT/.venv/bin/python"

step "Ports"
kill_port "$API_PORT"; kill_port "$CONSOLE_PORT"
say "cleared $API_PORT and $CONSOLE_PORT"

step "Operations API"
"$VPY" -m broker serve --port "$API_PORT" >/tmp/office-api.log 2>&1 &
for _ in $(seq 1 30); do
  curl -s -o /dev/null "http://127.0.0.1:$API_PORT/api/health" && break
  sleep 1
done
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
say "issued ${TOKEN:0:8}..."

step "Console"
if [ "$BUILD" -eq 1 ]; then
  (cd console && npx next build >/tmp/office-console-build.log 2>&1) \
    || { echo "next build failed; see /tmp/office-console-build.log" >&2; exit 1; }
  say "built"
fi
(cd console && OFFICE_API_URL="http://127.0.0.1:$API_PORT" \
  npx next start -p "$CONSOLE_PORT" >/tmp/office-console.log 2>&1 &)
for _ in $(seq 1 40); do
  curl -s -o /dev/null "http://127.0.0.1:$CONSOLE_PORT/login" && break
  sleep 1
done
say "listening on $CONSOLE_PORT"

ROUTES="/ /agents /audit /forge-map /revocations /ventures /proposals /instructions /packs /provisioning /knowledge"

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

step "Authenticated routes render"
for path in $ROUTES; do
  code="$(curl -s -b "$COOKIE_JAR" -o /tmp/office-page.html -w '%{http_code}' \
    "http://127.0.0.1:$CONSOLE_PORT$path")"
  if [ "$code" = "200" ]; then say "$path -> 200"; else fail "$path returned $code"; fi
done

step "The token never reaches the browser"
for path in $ROUTES; do
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT$path" > /tmp/office-page.html
  if grep -qF "$TOKEN" /tmp/office-page.html; then
    fail "$path leaked the bearer token into the HTML"
  fi
done
say "no route leaked the token"

step "Parameterised routes render"
# Ids come from the API, not from scraping the HTML. The first version of this grepped
# the page for /ventures/<slug> and matched a Next.js chunk filename, then reported a
# pass for a venture that does not exist. A check that can pass for the wrong reason is
# worse than no check.
API_AUTH="Authorization: Bearer $TOKEN"

AGENT_ID="$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/agents"   | grep -o '"office_agent_id": *"[^"]*"' | head -1 | grep -o '[0-9a-f-]\{36\}' || true)"
if [ -n "$AGENT_ID" ]; then
  code="$(curl -s -b "$COOKIE_JAR" -o /dev/null -w '%{http_code}'     "http://127.0.0.1:$CONSOLE_PORT/agents/$AGENT_ID")"
  if [ "$code" = "200" ]; then say "/agents/$AGENT_ID -> 200"; else fail "/agents/$AGENT_ID returned $code"; fi
else
  say "no agents in the registry; /agents/[id] not exercised"
fi

VENTURE="$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/ventures"   | grep -o '"venture_id": *"[^"]*"' | head -1 | sed 's/.*: *"//; s/"$//' || true)"
if [ -n "$VENTURE" ]; then
  code="$(curl -s -b "$COOKIE_JAR" -o /dev/null -w '%{http_code}'     "http://127.0.0.1:$CONSOLE_PORT/ventures/$VENTURE")"
  if [ "$code" = "200" ]; then say "/ventures/$VENTURE -> 200"; else fail "/ventures/$VENTURE returned $code"; fi
else
  say "no ventures registered; /ventures/[id] not exercised"
fi

# A venture that does not exist must 404 rather than render zeroes that look like data.
code="$(curl -s -b "$COOKIE_JAR" -o /dev/null -w '%{http_code}'   "http://127.0.0.1:$CONSOLE_PORT/ventures/definitely-not-a-venture")"
if [ "$code" = "404" ]; then
  say "unknown venture -> 404"
else
  fail "unknown venture returned $code; an empty dashboard for a mistyped venture is indistinguishable from a real one that has not started"
fi

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

step "Pack Editor and Provisioning Console"
# Both are parameterised on a venture that must actually have a Pack. Deriving the id
# from /api/packs rather than /api/ventures matters: a venture in the directory with no
# Pack 404s on both screens by design, and asserting 200 against one of those would be
# asserting the wrong thing.
PACK_VENTURE="$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/packs"   | grep -o '"venture_id": *"[^"]*"' | head -1 | sed 's/.*: *"//; s/"$//' || true)"
if [ -n "$PACK_VENTURE" ]; then
  for path in "/packs/$PACK_VENTURE" "/provisioning/$PACK_VENTURE"; do
    code="$(curl -s -b "$COOKIE_JAR" -o /tmp/office-page.html -w '%{http_code}'       "http://127.0.0.1:$CONSOLE_PORT$path")"
    if [ "$code" = "200" ]; then say "$path -> 200"; else fail "$path returned $code"; fi
  done

  # The editor must render the Pack source, not an empty textarea. An editor that
  # silently loads nothing and then publishes is how a Pack gets replaced by a blank.
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/packs/$PACK_VENTURE"     > /tmp/office-pack.html
  if grep -q 'schema_version' /tmp/office-pack.html; then
    say "the editor loaded the live Pack source"
  else
    fail "the Pack editor rendered without the Pack source in it"
  fi
else
  say "no venture has a Pack; the editor and console screens were not exercised"
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
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/provisioning/$PACK_VENTURE"     > /tmp/office-ladder.html
  code="$(curl -s -b "$COOKIE_JAR" -o /dev/null -w '%{http_code}'     "http://127.0.0.1:$CONSOLE_PORT/provisioning/$PACK_VENTURE")"
  [ "$code" = "200" ] || fail "the gate ladder returned $code"

  # Sixteen rows, not nine. A ladder that lists only what has happened shows a stopped
  # run as a tidy column of passes.
  # React renders `Gate {g.gate}` as separate text nodes with a comment between them,
  # so "Gate 9.5" never appears as a literal string. Counting the verdict labels is the
  # check that actually holds: sixteen rows, whatever has and has not run.
  rows="$(grep -o 'passed\|blocked\|awaiting a human\|not run' /tmp/office-ladder.html     | wc -l | tr -d ' ')"
  if [ "$rows" -ge 16 ]; then
    say "every gate has a verdict label ($rows across the ladder and the history table)"
  else
    fail "the ladder rendered $rows verdict labels; a ladder that lists only what has happened shows a stopped run as a tidy column of passes"
  fi
  if grep -q 'not run' /tmp/office-ladder.html; then
    say "gates that have not run say so, rather than being absent"
  else
    fail "no gate rendered as 'not run'"
  fi

  if grep -q 'awaiting a human' /tmp/office-ladder.html; then
    say "gate 4 renders as awaiting a human, not as blocked or passed"
  else
    fail "gate 4 did not render its own verdict - awaiting_human collapsed into something else"
  fi

  if grep -qi 'What did you review' /tmp/office-ladder.html; then
    say "the Gate 4 review form rendered"
  else
    fail "the Gate 4 review form did not render"
  fi

  # The review brief must be on the page before the form, not behind a disclosure.
  if grep -qi 'Unfilled positions' /tmp/office-ladder.html; then
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
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/knowledge" > /tmp/office-kb.html

# All five stores named. A Manager that quietly rendered four would be the version of
# this screen that was refused three times: a screen implying the thing exists.
missing_store=0
for store in "Forge Operating Instructions" "Compliance Library" "Business Playbooks"              "Persona Library" "Historical Records"; do
  grep -qF "$store" /tmp/office-kb.html || { fail "the Manager does not render $store"; missing_store=1; }
done
[ "$missing_store" -eq 0 ] && say "all five knowledge bases render"

# Denominators, not bare counts. "3 of 7" is the whole point of the screen; a list of
# entries with no denominator is a filing cabinet with search.
if grep -qE '[0-9]+ of [0-9]+' /tmp/office-kb.html; then
  say "coverage renders with denominators"
else
  fail "no coverage fraction on the page - a store count without a denominator cannot show a gap"
fi

# Which stores block, said on the screen rather than left to be learned at Gate 6.
if grep -qF "blocks provisioning at Gate 6" /tmp/office-kb.html    && grep -qF "advisory at Gate 6" /tmp/office-kb.html; then
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
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT$path" > /tmp/office-page.html
  if grep -qF "$PERSONA_MARKER" /tmp/office-page.html; then
    fail "$path leaked a persona body into the HTML"
    leaked=1
  fi
done
[ "$leaked" -eq 0 ] && say "no rendered page contains a persona body"

step "The provisioning ceiling is stated, not discovered"
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/provisioning" > /tmp/office-prov.html
if grep -q '9.5' /tmp/office-prov.html && grep -qi 'held-out' /tmp/office-prov.html; then
  say "the console names gate 9.5 as the ceiling in this deployment"
else
  fail "the provisioning console does not say that no run can pass gate 9.5 - an operator would find out by clicking Advance nine times"
fi

step "Unverified controls render as unverified"
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/" > /tmp/office-home.html
if grep -q 'never_run\|stale' /tmp/office-home.html; then
  if grep -q 'text-bad\|text-critical' /tmp/office-home.html; then
    say "unhealthy controls carry a failing severity class"
  else
    fail "an unhealthy control rendered without a failing severity - a dashboard that shows 'never verified' quietly manufactures confidence"
  fi
else
  say "no unhealthy controls present to check"
fi

step "Result"
if [ "$FAILURES" -eq 0 ]; then
  say "all checks passed"
else
  say "$FAILURES check(s) failed"
  exit 1
fi
