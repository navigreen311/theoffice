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

# Verdicts computed in Python have to count too.
#
# Eleven checks did their arithmetic in Python and printed `FAIL ...` down a pipe into
# `sed`, where it was indented like every other line and counted by nothing - `FAILURES`
# is incremented by `fail()` alone. The script could print FAIL in its own output and
# still exit 0, which is the failure this whole script exists to catch, one level up.
#
# Usage is the same as before with the interpreter swapped: `pycheck - "$ARG" <<'PY'`.
# stdin passes through, so the heredoc still reaches Python.
pycheck() {
  pycheck_out="$("$VPY" "$@" 2>&1)" || {
    fail "a python check exited non-zero: $(printf '%s' "$pycheck_out" | tail -3)"
    return 0
  }
  printf '%s\n' "$pycheck_out" | sed 's/^/  /'
  case "$pycheck_out" in
    *FAIL*) FAILURES=$((FAILURES + 1)) ;;
  esac
  case "$pycheck_out" in
    *"NOT EXERCISED"*) UNEXERCISED=$((UNEXERCISED + 1)) ;;
  esac
  return 0
}

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
# Its own build directory, so running this script does not break a console the
# developer already has running. `next build` used to replace `console/.next` while a
# `next start` on 3100 was serving from it; that server keeps its own build in memory, so
# its pages then referenced chunks the new build did not contain. The chunk answered 400,
# React failed with error #423, and the page showed "a client-side exception has
# occurred" - but only when reached by clicking a link, because a direct load fetches the
# page fresh. It was reported by hand three times before anything here could see it.
export NEXT_DIST_DIR=".next-smoke"

if [ "$BUILD" -eq 1 ]; then
  (cd console && NEXT_DIST_DIR="$NEXT_DIST_DIR" npx next build \
     >"$WORK/console-build.log" 2>&1) \
    || { tail -40 "$WORK/console-build.log" >&2; die "next build failed"; }
  say "built into $NEXT_DIST_DIR"
fi
(cd console && OFFICE_API_URL="http://127.0.0.1:$API_PORT" \
  NEXT_DIST_DIR="$NEXT_DIST_DIR" \
  npx next start -p "$CONSOLE_PORT" >"$WORK/console.log" 2>&1 &)
if ! wait_for "http://127.0.0.1:$CONSOLE_PORT/login" "the console" "$WORK/console.log" 60; then
  die "the console did not start"
fi
say "listening on $CONSOLE_PORT"

ROUTES="/ /agents /audit /forge-map /revocations /ventures /proposals /instructions /packs /provisioning /knowledge /incidents /access"
# The tabs the Knowledge rebuild added. They carry the forms, which is where a
# React-version mistake shows up, and they are not reachable from $ROUTES.
KNOWLEDGE_ROUTES="/knowledge/personas /knowledge/history /knowledge/playbooks /knowledge/compliance"

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

step "A stale session is a redirect, not a crash"
# A cookie the API REJECTS - an expired token, or one from a database that has since
# been rebuilt - used to throw ApiError(401), which no page caught. Every screen
# answered with a 500 and a digest, and the only way out was knowing to clear a cookie
# you cannot read. `dev-up.sh` reissues a token on every run, so this was reachable by
# doing nothing except leaving a tab open.
stale=0
for path in $ROUTES; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-redirs 0     -H "Cookie: office_session=this-token-no-longer-exists"     "http://127.0.0.1:$CONSOLE_PORT$path")"
  case "$code" in
    30*) ;;
    *)   fail "$path answered $code to a rejected session; it must redirect to /login"; stale=1 ;;
  esac
done
[ "$stale" -eq 0 ] && say "every route sends a rejected session to the login page"

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
  pycheck - "$TOKEN" "$API_PORT" <<'PY'
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

  sed 's/<!-- -->//g' "$WORK"/ladder.html > "$WORK"/ladder-text.html

  # Sixteen rows, not nine. A ladder that lists only what has happened shows a stopped
  # run as a tidy column of passes. Counted by gate name, because React splits
  # `Gate {g.gate}` across text nodes and "Gate 9.5" never appears as a literal string.
  missing_row=0
  for name in "Bridge operational" "Pack authored" "Pack validated" "Generators ran" \
              "Manifest reconciled" "Human review" "Capacity and budget check" \
              "Sandbox grants issued" "Knowledge bases seeded" "Agents appointed, paused" \
              "Curriculum to SimForge" "Readiness Gate" "Held-out set" \
              "Named-human sign-off" "Production grants" "Live"; do
    grep -qF "$name" "$WORK"/ladder-text.html || { fail "gate row missing: $name"; missing_row=1; }
  done
  [ "$missing_row" -eq 0 ] && say "all sixteen gate rows render, including the ones still ahead"

  # A pending gate that shows only a name says nothing about what is ahead of the run.
  if grep -qF "Runs the readiness gate per role per domain" "$WORK"/ladder-text.html; then
    say "pending gates describe what they will do"
  else
    fail "pending gates render as bare names - the ladder documents nothing"
  fi

  # The same gate cannot mean two things on two screens.
  if grep -qF "blocked — ceiling" "$WORK"/ladder-text.html \
     || grep -qF "blocked - ceiling" "$WORK"/ladder-text.html; then
    say "gate 9.5 reads as the ceiling here, as it does on the index"
  else
    fail "gate 9.5 reads as an ordinary pending gate here and as a hard ceiling on the index"
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

  # The copy this screen is carried by.
  preserved=0
  while IFS= read -r phrase; do
    grep -qF "$phrase" "$WORK"/ladder-text.html \
      || { fail "detail page lost: ${phrase:0:60}"; preserved=1; }
  done <<'PHRASES'
This gate waits. It does not pass on its own, and nothing advances until a named human records what they read.
Runs from gate 4 until a gate stops it. Gates are not skippable.
Abandoning frees the venture for a new run. It does not revoke anything
Required. Recorded against your name in the append-only log.
All sixteen, including the ones still ahead.
PHRASES
  [ "$preserved" -eq 0 ] && say "the preserved copy is present verbatim"

  # The gap this rebuild closed. The page knew V13 fails at gate 4.5 and filed it under
  # "Generator warnings", then asked a human to write a review and advance into the halt.
  if grep -qF "Advancing will stop at gate" "$WORK"/ladder-text.html; then
    say "a known downstream failure is stated before the human is asked to act"
  elif grep -qF "Blocking failures (" "$WORK"/ladder-text.html; then
    fail "a blocking failure is listed but the page does not warn before the review form"
  else
    notrun "downstream blocker banner - this run has no failing downstream rule"
  fi

  # FAIL never inside a container labelled warnings, and never sharing its count.
  if grep -qE "Generator warnings \([0-9]+\)" "$WORK"/ladder-text.html; then
    fail "failures and warnings still share a container and a count"
  else
    say "failures and warnings do not share a container"
  fi

  # No raw JSON at the reviewer by default; still reachable for engineers.
  if grep -qF '{"certified_and_free"' "$WORK"/ladder-text.html; then
    fail "raw JSON is still rendered at the reviewer by default"
  else
    say "no raw JSON in the default view"
  fi
  if grep -qF "View raw" "$WORK"/ladder-text.html; then
    say "the raw evidence is still reachable behind a toggle"
  else
    fail "the raw evidence is gone entirely - engineers need it"
  fi

  # The line that closes off the obvious wrong fix.
  if grep -qF "V13" "$WORK"/ladder-text.html; then
    if grep -qF "not by lowering the utilisation factor" "$WORK"/ladder-text.html; then
      say "the V13 message keeps the line that rules out lowering the utilisation factor"
    else
      fail "V13 renders without the sentence ruling out the wrong fix"
    fi
  fi

  # Validation errors belong on submit, not on load.
  if grep -qF "Abandoning a run needs a reason" "$WORK"/ladder-text.html; then
    fail "a validation error renders before the form has been submitted"
  else
    say "no validation error renders on load"
  fi

  if grep -qF "Record review and advance" "$WORK"/ladder-text.html; then
    say "recording a review and advancing is one action"
  else
    fail "recording a review and advancing are still two unrelated controls"
  fi

  # History states the pattern rather than listing identical rows.
  if grep -qE "Run history — [0-9]+ run" "$WORK"/ladder-text.html; then
    say "the run history heading carries the finding"
  else
    fail "run history is a bare list again"
  fi

  # Abandon what this script started, which also exercises the abort path.
  pycheck - "$TOKEN" "$API_PORT" "$RUN_ID" <<'PY'
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
# Text, not markup: React writes `9<!-- --> of <!-- -->9` across three elements, so a
# grep for `9 of 9` against raw HTML answers no to a page that plainly says it.
sed 's/<!-- -->//g' "$WORK"/kb.html > "$WORK"/kb-text.html

# All five stores named. A Manager that quietly rendered four would be the version of
# this screen that was refused three times: a screen implying the thing exists.
missing_store=0
for store in "Forge Operating Instructions" "Compliance Library" "Business Playbooks"              "Persona Library" "Historical Records"; do
  grep -qF "$store" "$WORK"/kb.html || { fail "the Manager does not render $store"; missing_store=1; }
done
[ "$missing_store" -eq 0 ] && say "all five knowledge bases render"

# Denominators, not bare counts. "3 of 7" is the whole point of the screen; a list of
# entries with no denominator is a filing cabinet with search.
if grep -qE '[0-9]+[[:space:]]+of[[:space:]]+[0-9]+' "$WORK"/kb-text.html; then
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
pycheck - "$TOKEN" "$API_PORT" "$PACK_VENTURE" "$PERSONA_MARKER" <<'PY'
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

step "The Packs page says whether each Pack can provision"
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/packs" > "$WORK"/packs-index.html

while IFS= read -r phrase; do
  grep -qF "$phrase" "$WORK"/packs-index.html || fail "packs page lost: ${phrase:0:60}"
done <<'PHRASES'
The Pack is the document every artifact derives from
Publishing supersedes the live version; the next provisioning run provisions the new one.
An engagement exists here
but there is no document to provision from.
PHRASES
say "the preserved copy is present verbatim"

# The gap the rebuild closed. The old page gave a hash and a version and never said
# whether the document worked - and a Pack failing any FAIL rule cannot provision,
# cannot generate and cannot appoint.
if grep -qE "can provision|cannot provision|not validated|provisions with warnings" "$WORK"/packs-index.html; then
  say "each Pack states whether it can provision"
else
  fail "no Pack reports a validation state - the page still cannot answer whether the document works"
fi

# `not validated` and `valid` must never render alike. A rule that could not run has
# validated nothing, and the two states carry different colours because a reader scans
# colour before text.
if grep -qF "not validated" "$WORK"/packs-index.html; then
  if grep -qF "could not run" "$WORK"/packs-index.html; then
    say "an unvalidated Pack says which rules could not run"
  else
    fail "a Pack reports 'not validated' without naming the rules that did not run"
  fi
fi

# A failing Pack names what is wrong with itself, not what the rule is called.
if grep -qF "cannot provision" "$WORK"/packs-index.html; then
  if grep -qE "V[0-9]+" "$WORK"/packs-index.html; then
    say "a failing Pack names the rules it fails"
  else
    fail "a Pack cannot provision and the page does not say which rule stopped it"
  fi
fi

# Three version states, and drift between the last two.
for phrase in "Versions" "provisioned" "Schema blocks" "Generated from this Pack"; do
  grep -qF "$phrase" "$WORK"/packs-index.html || fail "the Pack card is missing: $phrase"
done
say "versions, schema completeness and generated artifacts all render"

# Absence must not look like health here either.
if grep -qF "portfolio ventures have no Pack" "$WORK"/packs-index.html; then
  say "ventures with no Pack are listed as absent, not omitted"
else
  fail "a venture with no Pack is invisible - Gate 1 refuses it and the page does not say so"
fi

if grep -qF "New Pack" "$WORK"/packs-index.html; then
  say "a Pack can be created from the page"
else
  fail "no way to create a Pack"
fi

# Every denominator computed. The brief said 27 rules and 17 schema blocks; the
# validator registry has 28 and the model has 18, and both were wrong when written.
RULES_TOTAL="$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/packs/directory"   | grep -o '"rules_total": *[0-9]*' | sed 's/.*: *//' || true)"
# React separates adjacent text nodes with `<!-- -->`, so the rendered sentence reads
# "28 validator rules" while the markup does not. Strip the separators before matching -
# what the reader sees is the thing under test.
sed 's/<!-- -->//g' "$WORK"/packs-index.html > "$WORK"/packs-text.html
if [ -n "$RULES_TOTAL" ] && grep -qF "$RULES_TOTAL validator rules" "$WORK"/packs-text.html; then
  say "the rule denominator on the page matches the validator registry ($RULES_TOTAL)"
else
  fail "the page's rule count does not come from the registry - it will drift the next time a rule is added"
fi

step "A template is a starting point, and fails validation on purpose"
# A template that passed would mean this repository chose a budget. V18 fails on a
# non-positive cap, and that failure is what makes somebody set a real one.
CATEGORY="$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/packs/templates"   | grep -o '"category": *"[^"]*"' | head -1 | sed 's/.*: *"//; s/"$//' || true)"
if [ -n "$CATEGORY" ]; then
  curl -s -G -H "$API_AUTH" --data-urlencode "category=$CATEGORY"     "http://127.0.0.1:$API_PORT/api/packs/template" > "$WORK"/template.json
  if grep -qF "REPLACE_ME" "$WORK"/template.json; then
    say "the $CATEGORY template leaves venture-specific fields empty"
  else
    fail "a template carries no placeholders - it is guessing venture-specific values"
  fi
else
  notrun "pack templates - the catalogue is empty"
fi

step "The provisioning page shows the whole gate path"
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/provisioning" > "$WORK"/prov-index.html
sed 's/<!-- -->//g' "$WORK"/prov-index.html > "$WORK"/prov-text.html

# The ceiling notice is the strongest copy in the console. Checked verbatim, because
# these sentences are the ones most likely to be tightened by somebody who does not know
# why they are long.
preserved=0
while IFS= read -r phrase; do
  grep -qF "$phrase" "$WORK"/prov-text.html || { fail "provisioning page lost: ${phrase:0:60}"; preserved=1; }
done <<'PHRASES'
Sixteen gates from a Business Pack to a live venture. A run stops at the first gate that blocks and says which.
Ceiling in this deployment: gate 9.5
Stated here rather than discovered at the gate.
does not exist yet, so no run started from this console can pass gate 9.5 and no venture can reach gate 12.
not skipped: a run that skipped certification would produce a venture reading as fully provisioned that has been certified for nothing. There is no override, deliberately.
PHRASES
[ "$preserved" -eq 0 ] && say "the ceiling notice is present verbatim"

# The ceiling reads as a live constraint, not a paragraph. It was styled identically to
# body copy, which is how the strongest sentence in the console came to read as an aside.
if grep -q 'bg-warn-bg' "$WORK"/prov-index.html; then
  say "the ceiling notice carries a warning treatment"
else
  fail "the ceiling notice is styled as body copy again"
fi

# The gap the rebuild closed: sixteen gates were rendered as a fraction. Every gate has
# to appear, including the ones no run has reached.
missing_gate=0
for gate in 0 1 2 3 3.5 4 4.5 5 6 7 8 9 9.5 10 11 12; do
  grep -qE ">${gate}<" "$WORK"/prov-index.html || { fail "gate $gate is missing from the ladder"; missing_gate=1; }
done
[ "$missing_gate" -eq 0 ] && say "all sixteen gates render, not a fraction"

# Plain-language names, so the ladder can be scanned.
for phrase in "Bridge operational" "Pack validated" "Human review" "Held-out set" "Named-human sign-off" "Live"; do
  grep -qF "$phrase" "$WORK"/prov-text.html || fail "gate not named in plain language: $phrase"
done
say "gates carry plain-language names"

# The ceiling gate is visible in every ladder, wherever the run stopped. Those are two
# unrelated walls and the old page gave no way to tell them apart.
if grep -qF "ceiling, not buildable yet" "$WORK"/prov-text.html; then
  say "the ceiling gate is marked in the ladder itself"
else
  fail "the ladder does not distinguish the ceiling from wherever the run stopped"
fi

# The numbering contradiction, explained rather than left to be read as a bug.
if grep -qF "were inserted after the original twelve" "$WORK"/prov-text.html; then
  say "the gate numbering is explained"
else
  fail "the page shows a gate number and a cleared count that cannot be reconciled"
fi

step "A stopped run says what happened, who acted, and what it means"
# `aborted, gate 4` was the whole story. Gate 4 is human review, so that could have been
# a rejection, a timeout or an error.
if grep -qE "stopped at gate|rejected at gate|failed at gate|at ceiling|cancelled|complete|running at gate|awaiting review" "$WORK"/prov-text.html; then
  say "runs report an outcome in the reader's vocabulary"
else
  fail "no run states an outcome - the status vocabulary is missing"
fi

# `at ceiling` is not a failure. A run that reaches 9.5 has done everything currently
# possible, and rendering it as broken would misreport a successful run.
if grep -qF "at ceiling" "$WORK"/prov-text.html; then
  if grep -qE 'at ceiling[^<]*' "$WORK"/prov-text.html && ! grep -qF "failed at gate 9.5" "$WORK"/prov-text.html; then
    say "a run at the ceiling is not rendered as a failure"
  else
    fail "a run at the ceiling renders as a failure"
  fi
fi

if grep -qE "gates? downstream never ran" "$WORK"/prov-text.html; then
  say "a stopped run says what did not run because of it"
fi

step "There is no way past a gate in the UI"
# The ceiling notice states there is no override, deliberately. A control offering one
# would make that copy a lie.
found_override=0
for word in "Force" "force-past" "Skip gate" "Override" "Bypass" "admin-bypass"; do
  if grep -qF "$word" "$WORK"/prov-index.html; then
    fail "the provisioning page offers '$word' - the ceiling notice says there is no override"
    found_override=1
  fi
done
[ "$found_override" -eq 0 ] && say "no force, skip or override control is rendered"

step "A run can be started and re-run from the provisioning page"
# There was no action on this page at all: you could read how far a venture got and had
# to go somewhere else to do anything about it.
if grep -qF "Start run" "$WORK"/prov-text.html; then
  say "a run can be started from the page"
else
  fail "no way to start a run from the provisioning page"
fi
if grep -qF "Re-run" "$WORK"/prov-text.html; then
  say "a venture can be re-run"
else
  fail "no way to re-run a venture"
fi

# Run metadata. A run against a superseded Pack is not evidence about the current one.
if grep -qE "gates cleared" "$WORK"/prov-text.html && grep -qF "Pack" "$WORK"/prov-text.html; then
  say "runs carry their Pack version and a cleared count with a denominator"
else
  fail "a run renders without its Pack version or without a denominator"
fi

# The ladder is a map, so the gate the run stopped at is filled rather than merely named.
if grep -q 'bg-bad-bg' "$WORK"/prov-index.html; then
  say "the stopped gate is filled, not just labelled"
fi

step "Nothing rendered reads the clock or the locale"
# The bug this catches blanked pages in the browser while every status code stayed 200.
#
# A component that renders `Date.now()`, `new Date()` or `toLocaleString()` is rendered
# twice against two different runtimes: once by Node during SSR, once by the browser
# during hydration. The server says "3s ago" and formats in its own locale; the browser
# says "5s ago" and formats in the reader's. React cannot tell that apart from a bug, so
# it reports a hydration error and re-renders the tree on the client - which is what a
# page flashing and going blank looks like.
#
# `curl` never sees it, because the server HTML is correct. Only a browser hydrates. So
# this is a source check, and it has to be: there is no status code for it.
#
# `components/local-time.tsx` is the exception, and the only one. It reads the clock and
# the locale inside `useEffect`, which runs on the client and never during SSR - that is
# the fix, not the bug, and the whole reason the file exists.
CLOCK_EXEMPT="local-time.tsx"
clock=0

# `\(\)` escaped: unescaped, `()` is an empty regex group and the pattern matches every
# `new Date(anything)`, which flagged every correct call site in the console.
for pattern in 'Date\.now\(\)' 'new Date\(\)'; do
  # `while read` rather than `for f in $(...)`: a path containing a space would be split
  # into two non-existent paths and the check would quietly pass on both.
  # Redirected rather than piped, so `clock=1` is set in this shell, not a subshell.
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    case "$f" in *"$CLOCK_EXEMPT") continue;; esac
    # Ignore the pattern inside comments - the explanation of the rule is not a breach.
    if grep -E "$pattern" "$f" | grep -qvE '^\s*(//|\*|/\*)'; then
      fail "reads the render clock: ${f#"$ROOT/"}"
      clock=1
    fi
  done < <(grep -rlE "$pattern" "$ROOT/console/app" "$ROOT/console/components" \
           --include="*.tsx" 2>/dev/null)
done

# `toLocaleString()` with no locale uses the runtime's, and the two runtimes do not have
# to agree: "1,152" against "1.152", "8/24/2026" against "24/08/2026".
while IFS= read -r f; do
  [ -n "$f" ] || continue
  case "$f" in *"$CLOCK_EXEMPT") continue;; esac
  fail "formats without an explicit locale: ${f#"$ROOT/"}"
  clock=1
done < <(grep -rl 'toLocaleString()\|toLocaleTimeString()\|toLocaleDateString()' \
         "$ROOT/console/app" "$ROOT/console/components" --include="*.tsx" 2>/dev/null)
[ "$clock" -eq 0 ] && say "no component renders the clock or an implicit locale"

# The property itself, measured rather than argued. Two requests back to back must
# produce the same rendered text - anything in the markup that depends on the clock
# rather than on the payload shows up as a difference here.
#
# Compared as text with scripts stripped: the RSC payload carries the API's own as-of
# stamp, which is *supposed* to advance between requests. What must not move is what the
# reader sees.
stable=0
for path in / /provisioning /packs /ventures /provisioning/greenstone; do
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT$path" > "$WORK"/first.html
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT$path" > "$WORK"/second.html
  for n in first second; do
    sed -e 's/<script[^>]*>.*<\/script>//g' -e 's/<[^>]*>/ /g' "$WORK"/$n.html \
      | tr -s ' \n' ' ' > "$WORK"/$n.txt
  done
  if ! diff -q "$WORK"/first.txt "$WORK"/second.txt >/dev/null 2>&1; then
    fail "$path renders different text on two identical requests - something the reader sees depends on the clock"
    stable=1
  fi
done
[ "$stable" -eq 0 ] && say "identical requests render identical text"

step "The Pack editor carries what the directory added"
if [ -n "$PACK_VENTURE" ]; then
  # A draft, saved the way the directory saves one, so the editor is exercised in the
  # state the whole draft mechanism exists for rather than only in the empty case.
  pycheck - "$TOKEN" "$API_PORT" <<'PY'
import json, re, sys, urllib.error, urllib.request
token, port = sys.argv[1], sys.argv[2]
source = open("packs/greenstone.yaml", encoding="utf-8").read()

# Remove one optional block, so the sidebar has an absent block to report. Without this
# the fixture has all eighteen and a sidebar listing only what it finds is
# indistinguishable from one listing the whole schema.
source = re.sub(r"^triggers:\n(?:[ \t-].*\n|\n)*", "", source, flags=re.M)
assert "\ntriggers:" not in source, "the fixture still has the block it is meant to omit"

body = json.dumps({"yaml_source": source, "pack_version": "0.0.1-smoke"}).encode()
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/packs/draft", data=body, method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req) as response:
        print("draft saved:", json.load(response)["pack_version"])
except urllib.error.HTTPError as exc:
    print("draft not saved:", exc.code, exc.read()[:120].decode(errors="replace"))
PY

  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/packs/$PACK_VENTURE" \
    > "$WORK"/editor.html
  sed 's/<!-- -->//g' "$WORK"/editor.html > "$WORK"/editor-text.html

  while IFS= read -r phrase; do
    grep -qF "$phrase" "$WORK"/editor-text.html \
      || fail "pack editor lost: ${phrase:0:60}"
  done <<'PHRASES'
Publishing supersedes the live version and starts nothing. Provisioning is a separate act on a separate screen.
The hash is taken over these exact bytes, because a reviewer signs a document rather than a parse tree.
Superseded versions stay readable
PHRASES
  say "the preserved copy is present verbatim"

  # The gap: the directory grew drafts and this screen did not.
  if grep -qF "Save as draft" "$WORK"/editor-text.html; then
    say "a draft can be saved from the editor"
  else
    fail "the editor cannot save a draft - the one screen built to author a Pack"
  fi
  if grep -qF "Editing the draft" "$WORK"/editor-text.html; then
    say "the editor opens the draft and says what stays live"
  else
    fail "a draft exists and the editor is not showing it - the work is invisible here"
  fi
  if grep -qF "Publish draft" "$WORK"/editor-text.html; then
    say "a stored draft can be published from the editor"
  else
    fail "a draft exists and there is no way to publish it here"
  fi

  # THE ONE THAT MATTERS MOST HERE. The badge read `can provision - 28 of 28 rules
  # checked` while one rule had not been evaluated at all, on the screen where somebody
  # decides whether to publish.
  if grep -qF "can provision" "$WORK"/editor-text.html; then
    fail "the editor claims a Pack 'can provision' - a claim about the whole pipeline that this stage cannot support"
  else
    say "the editor does not claim a Pack can provision"
  fi
  if grep -qE "not evaluable at this stage" "$WORK"/editor-text.html; then
    say "unevaluable rules are counted separately from passes"
  else
    fail "the editor does not report unevaluable rules as their own state"
  fi
  three=0
  for part in "passed" "failed" "not"; do
    grep -qE "[0-9]+ $part" "$WORK"/editor-text.html || three=1
  done
  if [ "$three" -eq 0 ]; then
    say "the result is stated as three numbers, not one"
  else
    fail "validation renders as a single count again"
  fi

  # The denominator is the registry's, not a number typed into the copy. The editor
  # said "all 27 rules" against a registry of 28 for as long as that copy existed.
  RULES_TOTAL="$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/packs/directory"     | grep -o '"rules_total": *[0-9]*' | sed 's/.*: *//' || true)"
  if [ -n "$RULES_TOTAL" ] && grep -qF "all $RULES_TOTAL rules" "$WORK"/editor-text.html; then
    say "the rule denominator matches the validator registry ($RULES_TOTAL)"
  else
    fail "the editor's rule count does not come from the registry"
  fi

  # Every unevaluable rule names the gate that settles it. Checked against the payload
  # rather than the markup: the panel is behind a toggle, so a server render cannot
  # show it, and "not exercised" would be the honest but useless answer.
  pycheck - "$TOKEN" "$API_PORT" "$PACK_VENTURE" <<'PY'
import json, sys, urllib.request
token, port, venture = sys.argv[1], sys.argv[2], sys.argv[3]
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/packs/{venture}",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as response:
    report = json.load(response)["validation"]

bad = [
    r["rule_id"] for r in report["rules"]
    if not r["evaluable"] and not (r["settled_at_gate"] and r["why_not_here"])
]
counted = report["passed"] + report["failed"] + report["not_evaluable"]
if bad:
    print(f"FAIL unevaluable rules with no gate named: {bad}")
elif counted != report["rules_total"]:
    print(f"FAIL {counted} rules accounted for, {report['rules_total']} exist")
else:
    print(
        f"three states partition all {report['rules_total']} rules; "
        f"every unevaluable rule names its gate"
    )
PY

  # A diff, on the document whose hash binds signatures.
  if grep -qF "Diff against live" "$WORK"/editor-text.html; then
    say "the editor offers a diff against the live Pack"
  else
    fail "no diff on a document that gets signed"
  fi

  # Publish confirms rather than firing on one click.
  if grep -qF "Publish this text" "$WORK"/editor-text.html; then
    say "publish asks before it supersedes"
  else
    fail "publish supersedes the live Pack in one click"
  fi

  # Version history coherence.
  # Every row carries a disposition, whichever one applies. Asserting a *specific* one
  # makes the check depend on the shape of the world it runs in: locally there are
  # abandoned drafts, in CI there are not, and "not exercised" is the honest answer to a
  # question that should not have been asked that way.
  if grep -qE "abandoned draft|superseded by [0-9]|>live<|>draft<"        "$WORK"/editor-text.html; then
    say "the history names what became of each version"
  else
    fail "a version renders with no disposition - a reader cannot tell what happened to it"
  fi
  if grep -qE "provisioned by [0-9]+ run|never provisioned" "$WORK"/editor-text.html; then
    say "each version says whether a run provisioned it"
  else
    fail "the history promises a run names its version and does not deliver it"
  fi
  if grep -qF "Restore as draft" "$WORK"/editor-text.html; then
    say "an old version can be restored as a draft"
  else
    fail "no way to recover an earlier version"
  fi

  # Unsaved edits are visible.
  if grep -qF "unsaved edits" "$WORK"/editor.html \
     || grep -qF "Unsaved edits" "$WORK"/editor-text.html \
     || grep -qF "not counting your unsaved edits" "$WORK"/editor-text.html; then
    say "the editor accounts for unsaved edits"
  fi

  # Block navigation. 342 lines in one scroll, with the actions below all of them.
  BLOCKS_TOTAL="$("$VPY" - <<'PY'
from generators.pack import BusinessPack
print(len(BusinessPack.model_fields))
PY
)"
  rows="$(grep -o 'min-w-0 flex-1 truncate' "$WORK"/editor.html | wc -l | tr -d ' ')"
  if [ "$rows" = "$BLOCKS_TOTAL" ]; then
    say "every one of the $BLOCKS_TOTAL schema blocks has a sidebar row"
  else
    fail "the sidebar renders $rows rows for $BLOCKS_TOTAL schema blocks - a block the document omits has no line to scroll to, so the sidebar is the only place it can appear"
  fi

  if grep -q 'aria-label="Pack blocks"' "$WORK"/editor.html; then
    say "the block sidebar renders"
  else
    fail "no block navigation - 342 lines in a single scroll"
  fi

  # The fixture omits one block. A missing block is the one thing a reader cannot find
  # by scrolling - there is no line to scroll to - so the sidebar has to say it.
  if grep -qE "not in this document" "$WORK"/editor-text.html; then
    say "a block the document omits is reported as absent"
  else
    fail "the sidebar lists only the blocks it found; an omitted block is invisible"
  fi

  # Below 1024px a seventeen-row list above the document is worse than none.
  if grep -qF "Jump to block" "$WORK"/editor-text.html; then
    say "narrow viewports get a block picker rather than a stacked list"
  else
    fail "no mobile block picker"
  fi

  # The actions were below the whole document.
  if grep -qE "No unsaved edits|Unsaved edits" "$WORK"/editor-text.html; then
    say "the pinned bar states the dirty state"
  else
    fail "the action bar does not say whether there are unsaved edits"
  fi
  shortcuts="$(grep -o 'form="pack-' "$WORK"/editor.html | wc -l | tr -d ' ')"
  if [ "$shortcuts" -ge 2 ]; then
    say "the pinned actions submit the same forms as the reference row ($shortcuts)"
  else
    fail "the pinned buttons do not reuse the forms below - two implementations of one action"
  fi

  # `min-w-0` is load-bearing: without it the monospace document sets the flex item's
  # minimum width and pushes the sidebar off the screen instead of scrolling.
  if grep -qF "min-w-0 flex-1" "$WORK"/editor.html; then
    say "the editor column can shrink below its content width"
  else
    fail "the editor column has no min-w-0; the document will push the sidebar out"
  fi

  # Clean up after the check, so a smoke run does not leave a draft on the venture.
   pycheck - "$OFFICE_ADMIN_DSN" <<'PY'
import sys
import psycopg
with psycopg.connect(sys.argv[1]) as conn, conn.cursor() as cur:
    cur.execute(
        "UPDATE business_pack SET status = 'superseded', superseded_at = now() "
        "WHERE pack_version = '0.0.1-smoke' AND status = 'draft'"
    )
    print(f"smoke draft cleared ({cur.rowcount})")
    conn.commit()
PY
else
  notrun "pack editor checks - no venture has a Pack"
fi

step "No React 19 API in a React 18 project"
# This class has now shipped twice, and neither time did anything catch it:
#
#   useActionState        type-checked, built, and threw `useActionState is not a
#                         function` in the browser.
#   <form action={fn}>    type-checked, built, and threw a client-side exception.
#
# Both are React 19. This project pins React 18.3.1 per the blueprint stack, and the
# type definitions Next ships describe a newer React than the runtime - so `tsc` agrees,
# `next build` agrees, `curl` agrees, and the page is broken for anyone using it.
#
# A source check is not a substitute for executing the page. It is what is available
# without putting a browser in CI, and it catches the specific shapes that have bitten.
react19=0
for pattern in 'useActionState\(' 'useOptimistic\(' 'action=\{(async )?\(' 'action=\{function'; do
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if grep -qE "$pattern" "$f"; then
      fail "React 19 API in a React 18 project: ${f#"$ROOT/"} matches $pattern"
      react19=1
    fi
  done < <(grep -rlE "$pattern" "$ROOT/console/app" "$ROOT/console/components" \
           --include="*.tsx" 2>/dev/null)
done
[ "$react19" -eq 0 ] && say "no React 19 API used against the pinned React 18.3.1"

# The positive form: every form that submits to an action uses the hook that works.
if grep -rq 'useFormState' "$ROOT/console/app" --include="*.tsx"; then
  say "forms dispatch through useFormState"
fi

step "The Agents page accounts for the Village, not just the appointed"
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/agents" > "$WORK"/agents.html
sed 's/<!-- -->//g' "$WORK"/agents.html > "$WORK"/agents-text.html

while IFS= read -r phrase; do
  grep -qF "$phrase" "$WORK"/agents-text.html || fail "agents page lost: ${phrase:0:60}"
done <<'PHRASES'
The Office appoints agents. The Village creates them. Certified tier caps declared tier.
PHRASES
say "the preserved copy is present verbatim"

# The gap the rebuild closed. Seven rows and no count reads as a roster of seven.
if grep -qE "Village agents hold an Office identity|No Village roster has been imported" \
     "$WORK"/agents-text.html; then
  say "the page states the roster gap rather than implying the roster is what it lists"
else
  fail "the page lists agents with no statement of how many exist"
fi

# And it must not invent one. The blueprint says 106; this database knows what the
# roster has told it, and the Compliance page set the rule that a denominator nothing
# can support is not written down.
if grep -qE "of 106|0 of 106" "$WORK"/agents-text.html; then
  fail "the page hardcodes a denominator of 106 that no table in this system supports"
else
  say "no invented denominator"
fi

# Every department, whether or not anybody in it has reached The Office.
pycheck - "$WORK/agents-text.html" <<'PY'
import html
import sys
from generators.pack import VILLAGE_DEPARTMENTS
# Unescaped first: eight of the twelve department names contain "&", which renders as
# `&amp;`, and a raw substring check reported them missing from a page they are on.
page = html.unescape(open(sys.argv[1], encoding="utf-8", errors="replace").read())
absent = [d for d in VILLAGE_DEPARTMENTS if d not in page]
if absent:
    print(f"FAIL departments missing from the page entirely: {absent}")
else:
    print(f"all {len(VILLAGE_DEPARTMENTS)} departments appear, represented or not")
PY

# Departments with nobody are named, not silently absent.
if grep -qE "departments have no agent with an Office identity" "$WORK"/agents-text.html; then
  say "departments with nobody appointed are named"
else
  notrun "empty-department panel - every department has somebody"
fi

# The roster is searchable and filterable.
for control in "Search by name" "Office identity" "Certified, no grants"; do
  grep -qF "$control" "$WORK"/agents-text.html || fail "roster filter missing: $control"
done
say "the roster is searchable and filterable"
code="$(curl -s -b "$COOKIE_JAR" -o /dev/null -w '%{http_code}' \
  "http://127.0.0.1:$CONSOLE_PORT/agents?identity=without&grants=certified_no_grants")"
# if/then/else, not `A && B || C`: that form runs C when B fails, so a `say` that
# returned non-zero would report a failure that did not happen.
if [ "$code" = "200" ]; then
  say "filters are addressable in the URL"
else
  fail "a filtered roster returned $code"
fi

# No control may imply The Office creates agents.
if grep -qiE ">Add agent<|>New agent<|>Create agent<" "$WORK"/agents.html; then
  fail "a control implies The Office creates agents - it does not, the Village does"
else
  say "no control implies The Office creates agents"
fi
for control in "Sync from Village roster" "Register Village agent"; do
  grep -qF "$control" "$WORK"/agents-text.html || fail "roster control missing: $control"
done
say "the roster can be synced and an agent registered"

# Certified with no grants, explained rather than left as two columns.
if grep -qF "no grants" "$WORK"/agents-text.html; then
  if grep -qF "Certification makes an agent eligible" "$WORK"/agents.html; then
    say "certified-with-no-grants explains itself"
  else
    fail "an agent shows no grants beside a certified tier with nothing connecting them"
  fi
fi

step "Agent detail names the Forge and module a certification is for"
AGENT_ID="$(curl -s -H "$API_AUTH" "http://127.0.0.1:$API_PORT/api/agents" \
  | grep -o '"office_agent_id": *"[^"]*"' | head -1 | sed 's/.*: *"//; s/"$//' || true)"
if [ -n "$AGENT_ID" ]; then
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/agents/$AGENT_ID" \
    > "$WORK"/agent.html
  sed 's/<!-- -->//g' "$WORK"/agent.html > "$WORK"/agent-text.html

  while IFS= read -r phrase; do
    grep -qF "$phrase" "$WORK"/agent-text.html || fail "agent detail lost: ${phrase:0:60}"
  done <<'PHRASES'
A grant with either certification unit missing is not assignable
One venture per agent per shift. A failed PHI flush blocks the next assignment.
PHRASES
  say "the preserved copy is present verbatim"

  # The section that did not exist, despite the list claiming a certified tier.
  if grep -qF "Unit A — operation certification" "$WORK"/agent-text.html \
     && grep -qF "Unit B — department context certification" "$WORK"/agent-text.html; then
    say "both certification units render"
  else
    fail "the detail page claims a certified tier and has no certifications section"
  fi

  # A certification is always for a Forge and a module. Never a bare tier.
  if grep -qE "cre-forge|simforge|voiceforge" "$WORK"/agent-text.html; then
    say "certifications name the Forge they were earned on"
  else
    notrun "certification scope - this agent holds none"
  fi

  # Forge health and this agent's access are different statements.
  if grep -qF "Forge access for this agent" "$WORK"/agent-text.html \
     && grep -qF "This agent" "$WORK"/agent-text.html; then
    say "Forge health and this agent's access are separate facts"
  else
    fail "Forge health and agent access are still one column - GREEN beside 'cannot reach any Forge'"
  fi

  # The kill switch under the brokered model.
  if grep -qF "Revocation" "$WORK"/agent-text.html; then
    say "revocation is available from the agent's own page"
  else
    fail "no revocation control on the page where somebody decides to revoke"
  fi
else
  notrun "agent detail checks - no agent holds an identity"
fi

step "The approvals page is a control, not a formality"
# A pending proposal, so the queue has something in it. Without one there are no
# approval controls on the page and every check below passes by finding nothing - which
# is exactly how a check comes to pass for the wrong reason.
PROPOSAL_ID="$("$VPY" - <<'PY' | tail -1
import asyncio, hashlib, json, sys, uuid
sys.path.insert(0, ".")
import broker  # noqa: F401
from broker import proposals
from broker.db import close_pool, connection


async def main() -> None:
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT office_agent_id FROM office_agent_identity LIMIT 1")
            row = await cur.fetchone()
        if row is None:
            print("")
            await close_pool()
            return

        payload = {"to": "+15550000000", "script": "smoke"}
        proposal_id = await proposals.submit(
            conn,
            office_agent_id=row[0],
            venture_id="greenstone",
            forge_id="cre-forge",
            module_id="place_call",
            task_id=f"smoke-{uuid.uuid4().hex[:8]}",
            trust_tier="propose",
            payload=payload,
            payload_hash=hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest(),
            idempotency_key=f"smoke-{uuid.uuid4().hex[:8]}",
            trace_id=uuid.uuid4(),
        )
        print(proposal_id)
    await close_pool()


asyncio.run(main())
PY
)"
if [ -n "$PROPOSAL_ID" ]; then
  say "queued proposal ${PROPOSAL_ID:0:8} so the queue is not empty"
else
  notrun "pending-approval fixture - no agent holds an identity"
fi

curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/proposals" > "$WORK"/approvals.html
sed 's/<!-- -->//g' "$WORK"/approvals.html > "$WORK"/approvals-text.html

# The clearest statement of the rubber-stamp problem in the console, and it must stay on
# screen when the queue is empty - an empty queue is exactly when somebody forgets why
# the threshold exists.
preserved=0
while IFS= read -r phrase; do
  grep -qF "$phrase" "$WORK"/approvals-text.html \
    || { fail "approvals page lost: ${phrase:0:60}"; preserved=1; }
done <<'PHRASES'
An agent below auto_execute asked to act. It has not acted.
Approvals decided in under 5 seconds raise a governance flag. That threshold exists because a trust tier that is really a click-through is worse than no tier at all
it looks like oversight. Read the payload.
PHRASES
[ "$preserved" -eq 0 ] && say "the rubber-stamp copy is present verbatim"

# THE ONE THAT MATTERS MOST. Bulk approval is that copy's warning, industrialised.
# Checked against the page's *controls*, not its prose. The first version matched the
# sentence that says the control does not exist, which is the same trap the React 19
# guard fell into: a rule that greps for a phrase flags the paragraph explaining it.
pycheck - "$WORK/approvals.html" <<'PY'
import re
import sys

page = open(sys.argv[1], encoding="utf-8", errors="replace").read()

# Split rather than match. A regex for `<button[^>]*>` breaks on an attribute value
# containing ">", which Tailwind's arbitrary-value classes produce - it found nothing on
# a page with nine buttons, and "found nothing" is the answer this check must never give
# for the wrong reason.
labels = []
for chunk in page.split("<button")[1:]:
    body = chunk.split("</button>")[0]
    text = re.sub(r"<[^>]+>", " ", body.split(">", 1)[-1])
    labels.append(" ".join(text.split()))

checkboxes = re.findall(r'<input[^>]*type="checkbox"[^>]*>', page)

banned = ("approve all", "approve selected", "bulk approve", "select all")
offenders = [label for label in labels if any(word in label.lower() for word in banned)]

# A checkbox on a pending item is a selection mechanism, which exists only to act on
# many at once. The history filter's checkbox is fine and is named.
selectors = [c for c in checkboxes if "proposal" in c.lower() or "select" in c.lower()]

if offenders:
    print(f"FAIL a control offers bulk approval: {offenders}")
elif selectors:
    print(f"FAIL a per-proposal selection control exists: {selectors}")
elif not labels:
    # Finding nothing among nothing is not evidence. No controls at all means the
    # fixture did not render, and this would pass on a page replaced by an error.
    print("FAIL no buttons on the page at all - the pending fixture did not render")
else:
    print(f"no bulk approve control among {len(labels)} buttons")
PY

# And the page says what happens when nobody decides.
if grep -qF "Expiry never approves" "$WORK"/approvals-text.html; then
  say "the page states that expiry never approves"
else
  fail "nothing says what happens to a proposal nobody decides"
fi

# The empty state must be derived. The old one named a real cause that was not this
# cause, and sent a reader to inspect trust tiers on a system where no agent held a
# grant at all.
if grep -qF "Nothing to approve" "$WORK"/approvals-text.html; then
  pycheck - "$TOKEN" "$API_PORT" "$WORK/approvals-text.html" <<'PY'
import json, sys, urllib.request
token, port, page_path = sys.argv[1], sys.argv[2], sys.argv[3]
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/proposals/queue",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as response:
    queue = json.load(response)

page = open(page_path, encoding="utf-8", errors="replace").read()
state, reason = queue["state"], queue["empty_reason"] or ""

if state["live_grants"] == 0 and "auto_execute" in reason:
    print("FAIL the empty state blames trust tiers on a system with no grants at all")
elif state["live_grants"] == 0 and "nothing could be" not in reason:
    print(f"FAIL no grants exist and the empty state does not say so: {reason[:80]}")
elif reason and reason[:40] not in page:
    print("FAIL the derived reason is not what the page renders")
else:
    print("the empty state is derived from real state and matches this system")
PY
fi

# Reviewer capacity - the page where V13 either holds or fails in practice.
if grep -qF "Reviewer capacity" "$WORK"/approvals-text.html; then
  if grep -qE "of [0-9]+ today" "$WORK"/approvals-text.html \
     || grep -qF "No live Pack declares any reviewer" "$WORK"/approvals-text.html; then
    say "reviewer capacity shows headroom against a daily limit"
  else
    fail "reviewer capacity renders without a denominator"
  fi
else
  fail "no reviewer capacity - this is the page where V13 holds or fails"
fi

# The threshold is measured, not only stated.
for label in "Median decision time" "Under 5s" "Decisions today"; do
  grep -qF "$label" "$WORK"/approvals-text.html || fail "metric missing: $label"
done
say "the five-second threshold is measured, not only asserted"

if grep -qF "Decision history" "$WORK"/approvals-text.html; then
  say "decisions are visible after they are made"
else
  fail "only pending items are shown; a reviewer cannot see what was decided"
fi

# The pending card itself: the payload a reviewer is told to read, the flags that apply,
# and what each decision causes.
if [ -n "$PROPOSAL_ID" ]; then
  if grep -qF "+15550000000" "$WORK"/approvals-text.html; then
    say "the payload is on screen, not behind a disclosure"
  else
    fail "the payload is not rendered - 'read the payload' has nothing to read"
  fi
  if grep -qF "Denying stops this task" "$WORK"/approvals-text.html; then
    say "both decisions state their consequence"
  else
    fail "the card does not say what approving or denying causes"
  fi
  if grep -qE "expires" "$WORK"/approvals-text.html; then
    say "the item carries a deadline"
  else
    fail "nothing says what happens if nobody decides this one"
  fi

  # Deny it, which also exercises the decision path and leaves the queue as it was.
  pycheck - "$TOKEN" "$API_PORT" "$PROPOSAL_ID" <<'PY'
import json, sys, urllib.request
token, port, proposal_id = sys.argv[1], sys.argv[2], sys.argv[3]
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/proposals/{proposal_id}/decide",
    data=json.dumps({"approve": False, "reason": "console smoke test"}).encode(),
    method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as response:
    print("smoke proposal denied:", json.load(response)["status"])
PY
fi

step "Authored means the curriculum has content"
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/instructions" > "$WORK"/instr.html
sed 's/<!-- -->//g' "$WORK"/instr.html > "$WORK"/instr-text.html

while IFS= read -r phrase; do
  grep -qF "$phrase" "$WORK"/instr-text.html || fail "instructions page lost: ${phrase:0:60}"
done <<'PHRASES'
Curriculum, not documentation. content_hash binds certification to this exact text.
Publishing a new version invalidates every certification earned against the current text.
PHRASES
say "the preserved copy is present verbatim"

# THE ONE THAT MATTERS MOST. `authored` meant a row exists, which the live curriculum
# satisfies with "what_it_does": "Documented." while agents are certified against it.
if grep -qE ">authored<" "$WORK"/instr.html; then
  fail "the list still reports 'authored' as a state - a row existing is not a curriculum"
else
  say "'authored' is no longer a state"
fi
if grep -qE "complete|thin|stub|sections missing" "$WORK"/instr-text.html; then
  say "completeness is assessed from content"
else
  fail "no completeness assessment on the list"
fi

# The assessment is the same one the validator uses. Checked against the payload, so a
# console that quietly disagreed with V11 would show up here.
pycheck - "$TOKEN" "$API_PORT" <<'PY'
import json, sys, urllib.request
token, port = sys.argv[1], sys.argv[2]
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/instructions/directory",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as response:
    directory = json.load(response)

totals = directory["totals"]
states = {m["quality"]["state"] for m in directory["modules"]}
bad = [m for m in directory["modules"] if m["quality"]["state"] not in
       {"complete", "thin", "stub", "missing"}]

if bad:
    print(f"FAIL a module has an unknown completeness state: {bad[:2]}")
elif not directory["modules"]:
    print("FAIL no instruction sets at all - this check has nothing to assess")
else:
    hollow = totals["hollow"]
    resting = totals["certifications_on_hollow"]
    print(
        f"{len(directory['modules'])} instruction sets assessed: "
        f"{totals['complete']} complete, {totals['thin']} thin, {hollow} teach nothing"
    )
    if hollow and not resting:
        print("  (no certification rests on a hollow curriculum)")
    elif hollow:
        print(f"  {resting} certification(s) rest on a curriculum that teaches nothing")
PY

step "A stub curriculum names the agents certified against it"
MODULE_PATH="$("$VPY" - "$TOKEN" "$API_PORT" <<'PY' | tail -1
import json, sys, urllib.request
token, port = sys.argv[1], sys.argv[2]
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/instructions/directory",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as response:
    directory = json.load(response)

# Prefer one that is both hollow and certified against - that is the case the page
# exists for. Fall back to any module so the render is still checked.
hollow = [m for m in directory["modules"] if m["certifications_on_hollow"] > 0]
chosen = (hollow or directory["modules"] or [None])[0]
print(f"{chosen['forge_id']}/{chosen['module_id']}" if chosen else "")
PY
)"

if [ -n "$MODULE_PATH" ]; then
  curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/instructions/$MODULE_PATH" \
    > "$WORK"/instr-detail.html
  sed 's/<!-- -->//g' "$WORK"/instr-detail.html > "$WORK"/instr-detail-text.html

  while IFS= read -r phrase; do
    grep -qF "$phrase" "$WORK"/instr-detail-text.html \
      || fail "instruction detail lost: ${phrase:0:60}"
  done <<'PHRASES'
Eight required sections. A curriculum missing its failure signatures reads fine and teaches nothing about the case that matters.
Curriculum, not documentation. content_hash binds certification to this exact text.
PHRASES
  say "the preserved copy is present verbatim"

  # Eight sections rendered individually, not a JSON dump.
  missing_section=0
  for title in "What it does" "What it does not do" "Inputs and their meanings" \
               "Correct sequence" "Failure signatures" "Retry vs escalate" \
               "Never do" "Compliance coupling"; do
    grep -qF "$title" "$WORK"/instr-detail-text.html \
      || { fail "section not rendered: $title"; missing_section=1; }
  done
  [ "$missing_section" -eq 0 ] && say "all eight sections render individually"

  if grep -qF "View raw" "$WORK"/instr-detail-text.html; then
    say "the raw JSON is behind a toggle"
  else
    fail "the raw JSON is gone entirely - engineers need it"
  fi

  # The blocking finding, with people named rather than counted.
  if grep -qF "certified against it" "$WORK"/instr-detail-text.html; then
    if grep -qE "Placeholder — the entire section reads" "$WORK"/instr-detail-text.html; then
      say "a stub curriculum names its placeholder sections and the agents bound to it"
    else
      fail "the page says a curriculum is a stub without naming which sections"
    fi
  fi

  # Authoring, which did not exist at all.
  if grep -qE "Author a new version|Write this curriculum|Edit this curriculum" \
       "$WORK"/instr-detail-text.html; then
    say "a curriculum can be authored from the page"
  else
    fail "no way to write the content the whole Teach section depends on"
  fi
else
  notrun "instruction detail checks - no module has instructions"
fi

step "V11 refuses a Pack whose instructions teach nothing"
# A content_hash computed over placeholder text satisfies the letter of V11 and defeats
# its purpose. Checked against the validator itself rather than the page.
pycheck - <<'PY'
import asyncio, sys
sys.path.insert(0, ".")
import broker  # noqa: F401
from broker import packs
from broker.curriculum_quality import assess
from broker.db import close_pool, connection
from generators.validator import validate


async def main() -> None:
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT content FROM forge_operating_instruction "
                "WHERE superseded_at IS NULL LIMIT 1"
            )
            row = await cur.fetchone()

        if row is None:
            print("NOT EXERCISED no instruction sets to assess")
            await close_pool()
            return

        hollow = assess(row[0])["teaches_nothing"]
        live = await packs.live(conn, "greenstone")
        if live is None:
            print("NOT EXERCISED greenstone has no live Pack")
            await close_pool()
            return

        report = await validate(live.pack, conn)
        v11 = report.get("V11")
        verdict = v11.verdict.value

        if hollow and verdict != "FAIL":
            print(f"FAIL instructions teach nothing and V11 says {verdict}")
        elif hollow:
            print("V11 fails the Pack whose instructions teach nothing")
        elif verdict == "FAIL" and "teach nothing" in v11.message:
            print("FAIL V11 reports hollow instructions that the assessment calls real")
        else:
            print(f"instructions are real and V11 says {verdict}")
    await close_pool()


asyncio.run(main())
PY

step "The knowledge bases count substance, not rows"
curl -s -b "$COOKIE_JAR" "http://127.0.0.1:$CONSOLE_PORT/knowledge" > "$WORK"/kb.html
sed 's/<!-- -->//g' "$WORK"/kb.html > "$WORK"/kb-text.html

while IFS= read -r phrase; do
  grep -qF "$phrase" "$WORK"/kb-text.html || fail "knowledge page lost: ${phrase:0:60}"
done <<'PHRASES'
A flag with no entry reaches the agent as a label, not a constraint.
A module with no instructions can never be certified.
PHRASES
say "the preserved copy is present verbatim"

# The gap the rebuild closed. The page reported sixty personas and held none: every row
# was a `Smoke NNNNNN` fixture written by this very script. A count that includes them is
# a count of how often the smoke test has run.
if grep -qE "entries are test data" "$WORK"/kb-text.html; then
  say "test data is declared on the page rather than counted as content"
else
  fail "the overview does not say how much of what it counts is test data"
fi

# Not just declared - excluded. This asserts the arithmetic, so a page that quietly
# started counting fixtures again fails here rather than merely reading plausibly.
OVERVIEW_JSON="$(curl -s -H "$API_AUTH" \
  "http://127.0.0.1:$API_PORT/api/knowledge/overview")"
pycheck - "$WORK/kb.html" "$OVERVIEW_JSON" <<'PY'
import html
import json
import re
import sys

page = html.unescape(re.sub(r"<script.*?</script>", "", open(
    sys.argv[1], encoding="utf-8", errors="replace").read(), flags=re.S))
text = re.sub(r"<[^>]+>", " ", page)
overview = json.loads(sys.argv[2])
fixtures = overview["fixtures"]

declared = re.search(r"(\d+)\s+of\s+(\d+)\s+entries are test data", text)
if not declared:
    print("FAIL the overview does not state a test-data fraction")
    raise SystemExit

# The page must report the same fixture arithmetic the API computed, and the parts must
# add up to the whole. An earlier version of this check compared the persona headline
# against the page-wide fixture count - two different denominators - which passed on a
# database holding 60 fixtures and no real personas, and failed on a fresh one holding
# one of each. The invariant is that fixtures are excluded, not that there are many.
said, total = int(declared.group(1)), int(declared.group(2))
if (said, total) != (fixtures["test_fixtures"], fixtures["total_rows"]):
    print(f"FAIL the page says {said} of {total} test rows; "
          f"the API says {fixtures['test_fixtures']} of {fixtures['total_rows']}")
elif fixtures["personas"] + fixtures["records"] != fixtures["test_fixtures"]:
    print("FAIL the fixture parts do not sum to the fixture total")
else:
    print(f"the page and the API agree: {said} of {total} rows are test data")

# And no base counts them. Every base count must be at most the rows that are not
# fixtures, whatever the mix happens to be on this machine.
substantive = fixtures["total_rows"] - fixtures["test_fixtures"]
inflated = [b["label"] for b in overview["bases"] if b["count"] > substantive]
if inflated:
    print(f"FAIL these bases count more than the non-fixture rows: {inflated}")
else:
    print(f"no base counts more than the {substantive} rows that are not fixtures")
PY

# Every base states its gap in the terms of the thing that is missing. "0 entries" is a
# number; "no written SOP for any of them" is a finding somebody can act on.
for base in "Forge Operating Instructions" "Compliance Library" "Business Playbooks" \
            "Persona Library" "Historical Records"; do
  grep -qF "$base" "$WORK"/kb-text.html || fail "knowledge overview omits: $base"
done
say "all five bases appear on the overview"

if grep -qE "no written SOP for any of them|names [0-9]+ target persona" \
     "$WORK"/kb-text.html; then
  say "an empty base states what is missing, not just that it is empty"
else
  fail "an empty knowledge base reports a count with no statement of the gap"
fi

# Which of them can hold up Gate 6, and which are advisory. Reading them as equals is
# what let a blocking gap sit beside a cosmetic one for the same length of time.
if grep -qF "blocks provisioning at Gate 6" "$WORK"/kb-text.html; then
  say "the two bases that block Gate 6 are marked as blocking"
else
  fail "nothing distinguishes a base that blocks Gate 6 from one that does not"
fi

# Six tabs, each its own address. The five bases were one page with five tables on it.
for tab in "" "/personas" "/history" "/playbooks" "/compliance"; do
  code="$(curl -s -b "$COOKIE_JAR" -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:$CONSOLE_PORT/knowledge$tab")"
  if [ "$code" = "200" ]; then
    say "/knowledge$tab renders"
  else
    fail "/knowledge$tab returned $code"
  fi
done

# Fixtures are filtered out by default - and the filter is doing work rather than the
# table being empty for some other reason. Both halves are asserted: the default excludes
# them, and asking for them brings them back. The first alone passes when the route is
# broken, which is how the block-sidebar and bulk-approve checks first passed.
pycheck - "$TOKEN" "$API_PORT" <<'PY'
import json
import urllib.request

token, port = __import__("sys").argv[1], __import__("sys").argv[2]


def listing(store: str, **params) -> dict:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"http://127.0.0.1:{port}/api/knowledge/{store}?{query}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as response:
        return json.load(response)


# Per store, because a fresh database has fixtures in one and not the other: the smoke
# run always abandons a provisioning run, and only sometimes writes a smoke persona. The
# first version asked the persona store alone and reported the filter inert on CI, where
# the only persona is a real one.
filtered = 0
for store in ("personas", "history"):
    default = listing(store)
    withfix = listing(store, include_fixtures="true")
    excluded = default["excluded_fixtures"]

    if any(row["origin"] == "test_fixture" for row in default["rows"]):
        print(f"FAIL a test fixture appears in the default {store} listing")
        continue
    if excluded == 0:
        print(f"{store}: no fixtures to hide")
        continue
    if withfix["total"] <= default["total"]:
        print(f"FAIL {store}: include_fixtures returned no more than the default")
    elif not any(row["origin"] == "test_fixture" for row in withfix["rows"]):
        print(f"FAIL {store}: include_fixtures returned rows, none marked a fixture")
    else:
        filtered += 1
        print(f"{store}: default hides {excluded}, include_fixtures returns "
              f"{withfix['total']}")

if filtered == 0:
    print("FAIL no store had a fixture to filter; this run proved nothing")

# Paging is exercised deterministically by asking for one row per page, rather than by
# hoping the database holds enough rows to need a second page. A fresh database holds one
# row per store, so requiring a long table made this unrunnable there - and NOT EXERCISED
# is fatal, so an honest gap read as a broken script.
listed = listing("history", include_fixtures="true", page_size=1)
if listed["total"] == 0:
    print("FAIL the history store is empty; the smoke run records at least one entry")
elif listed["pages"] != listed["total"]:
    print(f"FAIL {listed['total']} rows at one per page reported "
          f"{listed['pages']} page(s)")
elif len(listed["rows"]) != 1:
    print(f"FAIL a page of size 1 returned {len(listed['rows'])} rows")
else:
    last = listing("history", include_fixtures="true", page_size=1,
                   page=listed["pages"])
    beyond = listing("history", include_fixtures="true", page_size=1,
                     page=listed["pages"] + 5)
    if not last["rows"]:
        print("FAIL the last page is empty")
    elif beyond["rows"]:
        print("FAIL a page past the end returned rows")
    elif last["rows"][0]["record_id"] == listed["rows"][0]["record_id"]             and listed["pages"] > 1:
        print("FAIL the last page repeats the first; the offset is not applied")
    else:
        print(f"paging holds: {listed['total']} row(s) one per page, the last page has "
              "content and a page past the end is empty rather than an error")
PY

# Historical records are never deleted. The store refuses it and the page must not offer
# it: an exclusion is a reading decision, and the decision is itself recorded.
if grep -qiE ">Delete record<|>Purge records<|>Delete entry<" "$WORK"/kb.html; then
  fail "the console offers to delete a historical record; that store is append-only"
else
  say "no control deletes a historical record"
fi
if grep -qF "compensating entry" "$WORK"/kb-text.html; then
  say "the page says what to do instead of deleting"
else
  fail "the page refuses deletion without saying what to do instead"
fi

# The refusal is the database's, not the page's. A UI that merely omits the button is a
# convention; this is the control that cannot be argued out of.
pycheck - "${OFFICE_APP_DSN:-}" "$OFFICE_ADMIN_DSN" <<'PY'
import sys

import psycopg

app_url, admin_url = sys.argv[1], sys.argv[2]

# The trigger raises with ERRCODE 'insufficient_privilege', which is also what a missing
# GRANT raises. So the error class cannot tell "the store refuses this" from "this role
# was never given DELETE" - and a table whose trigger had been dropped and whose grant
# had been revoked would answer identically. The message is what distinguishes them, so
# the message is what gets asserted.
REFUSAL = "append-only violation"


def refuses(url: str) -> str:
    """Attempt the delete and report what stopped it, if anything."""
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT record_id FROM historical_record LIMIT 1")
            row = cur.fetchone()
            if row is None:
                return "empty"
            try:
                cur.execute(
                    "DELETE FROM historical_record WHERE record_id = %s", (row[0],)
                )
            except psycopg.Error as refusal:
                if REFUSAL in str(refusal):
                    return "trigger"
                return f"other:{type(refusal).__name__}"
            finally:
                conn.rollback()
    return "accepted"


admin = refuses(admin_url)
if admin == "empty":
    print("NOT EXERCISED no historical record exists to delete")
elif admin == "accepted":
    print("FAIL historical_record accepted a DELETE from the admin role")
elif admin != "trigger":
    # Refused, but by the wrong thing. The admin role holds DELETE on this table, so a
    # refusal that is not the trigger means the trigger is gone and a grant is standing
    # in for it - which the next migration to re-grant would silently undo.
    print(f"FAIL a delete was refused by {admin}, not the append-only trigger")
else:
    print("the append-only trigger itself refuses a delete, even as admin")
    if app_url:
        app = refuses(app_url)
        if app == "accepted":
            print("FAIL historical_record accepted a DELETE from the app role")
        else:
            print("and the console's own role cannot reach the table at all")
PY

# The page may not offer a capability the role does not hold. `personas_deletable` was
# hardcoded True, reasoned from "personas are never production data" - true, and beside
# the point: office_app holds INSERT and UPDATE on `persona` and no DELETE. The flags are
# read from the grants now, so this asserts the page agrees with the database.
pycheck - "$TOKEN" "$API_PORT" "$OFFICE_ADMIN_DSN" <<'PY'
import json
import sys
import urllib.request

import psycopg

token, port, admin_dsn = sys.argv[1], sys.argv[2], sys.argv[3]
req = urllib.request.Request(
    f"http://127.0.0.1:{port}/api/knowledge/overview",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as response:
    fixtures = json.load(response)["fixtures"]

with psycopg.connect(admin_dsn) as conn, conn.cursor() as cur:
    cur.execute(
        """
        SELECT table_name, privilege_type
          FROM information_schema.table_privileges
         WHERE grantee = 'office_app'
           AND table_name IN ('persona', 'historical_record')
           AND privilege_type = 'DELETE'
        """
    )
    deletable = {row[0] for row in cur.fetchall()}

claimed = {
    "persona": fixtures["personas_deletable"],
    "historical_record": fixtures["records_deletable"],
}
wrong = [t for t, said in claimed.items() if said != (t in deletable)]
if wrong:
    print(f"FAIL the page claims the wrong delete capability for {wrong}")
else:
    print("the page claims exactly the delete privileges the role holds: "
          f"{sorted(deletable) or 'none'}")
PY

# There is no purge, and the honest action in its place is recorded rather than applied.
if grep -qiE ">Purge|>Delete all|>Clear fixtures<" "$WORK"/kb.html; then
  fail "the console offers a purge; neither knowledge store permits one"
else
  say "no purge control is offered"
fi

pycheck - "$TOKEN" "$API_PORT" <<'PY'
import json
import sys
import urllib.error
import urllib.request

token, port = sys.argv[1], sys.argv[2]


def call(path: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as response:
        return json.load(response)


before = call("/api/knowledge/overview")["fixtures"]
if before["test_fixtures"] == 0:
    print("NOT EXERCISED no fixtures to exclude")
    raise SystemExit

try:
    call("/api/knowledge/fixtures/exclude", "POST", {})
except urllib.error.HTTPError as exc:
    print(f"FAIL recording the exclusion returned {exc.code}")
    raise SystemExit

rows = call("/api/knowledge/history?record_type=knowledge_fixture_exclusion"
            "&include_fixtures=true")["rows"]
if not rows:
    print("FAIL the exclusion was not recorded")
    raise SystemExit
if rows[0]["actor_type"] != "human":
    print("FAIL the exclusion was recorded as a system act; a person decided it")

# And nothing was removed. Excluding is a reading decision: the rows it describes are
# still there, which is what makes the record the only evidence the decision happened.
after = call("/api/knowledge/overview")["fixtures"]
if after["personas"] < before["personas"]:
    print("FAIL recording an exclusion deleted personas")
else:
    print(f"the exclusion of {before['test_fixtures']} rows is recorded, "
          "and every row it describes is still there")
PY

# Paging and search, because a listing with neither is one nobody reads to the end of.
curl -s -b "$COOKIE_JAR" \
  "http://127.0.0.1:$CONSOLE_PORT/knowledge/personas?include_fixtures=true" \
  > "$WORK"/kb-personas.html
sed 's/<!-- -->//g' "$WORK"/kb-personas.html > "$WORK"/kb-personas-text.html
if grep -qiE "page [0-9]+ of [0-9]+" "$WORK"/kb-personas-text.html; then
  say "a long listing renders its page control"
else
  # Not `notrun`: on a fresh database the persona store holds one row, and a control that
  # correctly hides itself is not an unrun check. The arithmetic is asserted above.
  say "the listing fits on one page, so no page control renders"
fi
if grep -qF "Search" "$WORK"/kb-personas-text.html; then
  say "the listing is searchable"
else
  fail "the persona listing has no search"
fi

step "Every page survives being opened in a browser"
# Every other render check here asks the server and believes the answer. The server says
# 200 to a page that is about to die during hydration, and three "a client-side exception
# has occurred" reports have now arrived by hand for pages this script called green: a
# React 19 API against React 18.3.1, a clock read during SSR, and a JS chunk answering
# 400 because `next build` rewrote `.next` under a running `next start`. None of the
# three is visible in HTML. This opens the pages in Chrome and reports what the browser
# reports.
CHROME=""
for candidate in \
  "${CHROME_BIN:-}" "${CHROME_PATH:-}" \
  "/c/Program Files/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  "$(command -v google-chrome 2>/dev/null || true)" \
  "$(command -v google-chrome-stable 2>/dev/null || true)" \
  "$(command -v chromium 2>/dev/null || true)" \
  "$(command -v chromium-browser 2>/dev/null || true)" \
  "$(command -v microsoft-edge 2>/dev/null || true)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then CHROME="$candidate"; break; fi
done

if [ -z "$CHROME" ]; then
  # Fatal, like every other unexercised check. This one exists precisely because the
  # failures it catches are invisible to everything else in this file, so "no browser
  # available" must not read as "the pages are fine".
  notrun "hydration - no Chrome or Edge binary found; set CHROME_BIN"
else
  CDP_PORT=9333
  kill_port "$CDP_PORT"
  "$CHROME" --headless=new --remote-debugging-port="$CDP_PORT" \
    --user-data-dir="$WORK/chrome" --no-first-run --no-default-browser-check \
    --disable-gpu --disable-dev-shm-usage --no-sandbox \
    about:blank >"$WORK/chrome.log" 2>&1 &
  CHROME_PID=$!

  SESSION="$(grep office_session "$COOKIE_JAR" | awk '{print $7}' | tail -1)"
  if [ -z "$SESSION" ]; then
    fail "no session cookie to hand the browser"
  else
    # `node` runs the checker: it needs a WebSocket client, and Node 22+ has one built
    # in, so this adds no dependency to the repository.
    # Routes are passed dot-prefixed: `./`, `./agents`. Git Bash rewrites any
    # argument starting with `/` into a Windows path, so `/knowledge` arrived as
    # `C:/Program Files/Git/knowledge` and every page reported rendering nothing.
    # Turning conversion off wholesale then broke the script path itself, which
    # genuinely needs converting - so the fix is to hand it nothing to convert.
    #
    # The dot rather than a bare strip, because stripping turned `/` into the empty
    # string and the shell dropped it: the dashboard silently stopped being checked
    # while the step still reported every page hydrating. The checker counts what it
    # was given, so a drop like that fails instead of shrinking the sweep.
    # An array rather than a string relying on word splitting, which shellcheck
    # flags (SC2086) and which would mangle any route that ever contained a space.
    read -r -a ALL_ROUTES <<<"$ROUTES $KNOWLEDGE_ROUTES"
    DOTTED_ROUTES=()
    for route in "${ALL_ROUTES[@]}"; do DOTTED_ROUTES+=(".$route"); done
    ROUTE_COUNT="${#DOTTED_ROUTES[@]}"
    if EXPECTED_ROUTES="$ROUTE_COUNT" CDP_PORT="$CDP_PORT" \
         node "$ROOT/scripts/hydration-check.mjs" \
         "http://localhost:$CONSOLE_PORT" "$SESSION" "${DOTTED_ROUTES[@]}" \
         2>&1 | sed 's/^/  /'; then
      say "every page hydrated in a real browser"
    else
      fail "a page broke in the browser after the server called it 200"
    fi
  fi
  kill "$CHROME_PID" 2>/dev/null || true
  kill_port "$CDP_PORT"
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
