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
  [ -n "$pid" ] && taskkill //PID "$pid" //F >/dev/null 2>&1 || true
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

ROUTES="/ /agents /audit /forge-map /revocations /ventures /proposals /instructions"

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
