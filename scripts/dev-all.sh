#!/usr/bin/env bash
# dev-all.sh - everything the bridge needs, started or reported, in one command.
#
#   ./scripts/dev-all.sh              # start what is down, report what is up
#   ./scripts/dev-all.sh --status     # report only; start nothing
#   ./scripts/dev-all.sh --stop       # stop ONLY what a previous run of this started
#
# WHY THIS EXISTS
#
#   Nothing here survives a reboot, and bringing it back has been a recipe in a memory
#   file: Docker Desktop is a per-user install in AppData, SimForge reads its `.env` from
#   the repo root rather than `apps/api`, the Village needs its own venv because a bare
#   3.11 has no `yaml`, and CRE Forge must be `docker start`ed rather than re-created so
#   the override port map survives. Six services, six different ways to be wrong.
#
# THREE RULES THIS SCRIPT KEEPS, EACH FROM SOMETHING THAT WENT WRONG
#
#   1. NEVER KILL BY PORT.
#
#      On 16 September `taskkill //PID <holder of 8080> //T //F` took Docker Desktop's
#      backend with it - `com.docker.backend.exe` forwards 8080 and every container port,
#      so CRE Forge went unreachable and the next provisioning advance failed on V2. That
#      is decisions entry 91's hazard exactly, which is why `dev-up.sh` already refuses to
#      do it. This script records a PID for everything it starts and stops only those. A
#      port held by anything else is reported by name and left alone.
#
#   2. CHECK THE BODY, NEVER THE STATUS CODE ALONE.
#
#      A port answering proves a process, not the right process. `feedback_dshow` records
#      the same lesson elsewhere; here the case is CapitalForge, whose unconfigured bridge
#      401s from tenant middleware instead of 404ing as its own `.env.example` documents -
#      so the diagnostic is the adapter's OWN rejection code being present, not the status.
#
#   3. A LIVE PROCESS IS NOT AN UP-TO-DATE ONE.
#
#      After a merge on 16 September a stale API answered `/api/live` with 200 and 404ed a
#      route that had just landed. The route was in the file and not in the process. So
#      `/api/version` reports the build, and this script refuses to call the API healthy
#      when that commit is not the one checked out. **Stale is a failure, not a note.**
#
#      `/api/version` is AUTHENTICATED and `/api/live` is not, which is why this reads
#      OFFICE_OPERATOR_TOKEN. The commit went on `/api/live` for exactly one commit and
#      D1 refused it: a liveness endpoint is reachable by anyone who can reach the port,
#      so everything it returns is public. Without a token this reports the build
#      UNVERIFIED and does not call the API healthy - a check that could not run is not
#      a check that passed.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || { echo "error: cannot cd to $ROOT" >&2; exit 1; }

API_PORT="${API_PORT:-8080}"
CONSOLE_PORT="${CONSOLE_PORT:-3100}"
VILLAGE_PORT="${VILLAGE_PORT:-8120}"
SIMFORGE_PORT="${SIMFORGE_PORT:-8110}"
CAPITALFORGE_PORT="${CAPITALFORGE_PORT:-4000}"
CRE_FORGE_PORT="${CRE_FORGE_PORT:-8011}"

VILLAGE_DIR="${VILLAGE_DIR:-$HOME/village1.0.2-recovered/village1.0.2}"
SIMFORGE_DIR="${SIMFORGE_DIR:-$HOME/Projects/simforge/apps/api}"
CAPITALFORGE_DIR="${CAPITALFORGE_DIR:-$HOME/Projects/capitalforge}"

RUN_DIR="${TMPDIR:-/tmp}/office-dev-all"
LOG_DIR="$RUN_DIR/logs"
mkdir -p "$LOG_DIR"

STATUS_ONLY=0
STOP=0
for arg in "$@"; do
  case "$arg" in
    --status) STATUS_ONLY=1 ;;
    --stop)   STOP=1 ;;
    *) printf 'unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

FAILED=0
say()  { printf '  %s\n' "$1"; }
ok()   { printf '  OK    %s\n' "$1"; }
bad()  { printf '  DOWN  %s\n' "$1"; FAILED=$((FAILED + 1)); }
step() { printf '\n==> %s\n' "$1"; }

# ---------------------------------------------------------------- process bookkeeping

pids_on_port() {
  netstat -ano 2>/dev/null | grep -E "[:.]${1}[[:space:]]" | grep -i LISTENING \
    | awk '{print $NF}' | sort -u
}

# Report a service that is not answering, naming whoever holds its port. Used by both
# paths: --status was the LESS informative of the two until 2026-09-16, which is
# backwards - the mode somebody runs to diagnose should say more, not less. "Docker
# Desktop is on this port" is the entire answer, and status mode was withholding it.
report_down() {
  local what="$1" port="$2" holder
  holder="$(port_holder "$port")"
  if [ -n "$holder" ]; then
    bad "$what - port held by $holder, which is not it"
  else
    bad "$what - nothing is listening on $port"
  fi
}

port_holder() {
  local pid name out=""
  for pid in $(pids_on_port "$1"); do
    name="$(tasklist //FI "PID eq $pid" //FO CSV //NH 2>/dev/null \
            | head -1 | cut -d, -f1 | tr -d '"')"
    out="$out pid $pid (${name:-unknown})"
  done
  printf '%s' "${out# }"
}

# Start a background service and record its PID. Nothing else is ever stopped.
start_bg() {
  local label="$1"; shift
  nohup "$@" </dev/null >"$LOG_DIR/$label.log" 2>&1 &
  echo $! > "$RUN_DIR/$label.pid"
  disown 2>/dev/null || true
}

stop_ours() {
  local label="$1"
  local pidfile="$RUN_DIR/$label.pid"
  local pid winpid
  [ -f "$pidfile" ] || { say "$label: not started by this script; left alone"; return 0; }
  pid="$(cat "$pidfile")"
  if [ -r "/proc/$pid/winpid" ]; then
    winpid="$(cat "/proc/$pid/winpid")"
    taskkill //PID "$winpid" //T //F >/dev/null 2>&1 || true
  fi
  kill "$pid" 2>/dev/null || true
  rm -f "$pidfile"
  say "$label: stopped (pid $pid)"
}

# ------------------------------------------------------------------- body-level checks
#
# Each returns 0 only when the RESPONSE BODY identifies the right service. A port that
# answers is not the service that should be on it - see rule 2 above.

probe() {
  local label="$1" url="$2" needle="$3" auth="${4:-}"
  local body
  if [ -n "$auth" ]; then
    body="$(curl -s -m 8 -H "Authorization: Bearer $auth" "$url" 2>/dev/null)"
  else
    body="$(curl -s -m 8 "$url" 2>/dev/null)"
  fi
  case "$body" in
    *"$needle"*) return 0 ;;
    *) return 1 ;;
  esac
}

# Empty when there is no token, or the API refuses it. The caller distinguishes
# "not the checked-out commit" from "could not ask" - they are different findings.
api_commit() {
  [ -n "${OFFICE_OPERATOR_TOKEN:-}" ] || return 0
  curl -s -m 8 -H "Authorization: Bearer $OFFICE_OPERATOR_TOKEN" \
    "http://127.0.0.1:$API_PORT/api/version" 2>/dev/null \
    | tr ',' '\n' | grep '"commit"' | sed 's/.*: *"//; s/"//'
}

wait_for() {
  local seconds="$1"; shift
  # The counter is deliberately discarded: this is a countdown, not an index.
  local _tick
  for _tick in $(seq 1 "$seconds"); do
    "$@" && return 0
    sleep 1
  done
  return 1
}

# ------------------------------------------------------------------------------ stop

if [ "$STOP" -eq 1 ]; then
  step "Stopping only what this script started"
  for label in console api village simforge capitalforge; do
    stop_ours "$label"
  done
  say "CRE Forge containers are left running: docker start/stop is yours to call, and"
  say "stopping them here would be this script reaching past what it began."
  exit 0
fi

# ------------------------------------------------------------------------------ env

[ -f "$ROOT/.env" ] || { echo "error: .env not found" >&2; exit 1; }
set -a
# shellcheck source=/dev/null
. "$ROOT/.env"
set +a

CHECKED_OUT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
printf 'The Office dev environment\n  repo %s at %s\n' "$ROOT" "${CHECKED_OUT:0:12}"

# --------------------------------------------------------------------------- docker

step "Docker daemon"
if docker ps >/dev/null 2>&1; then
  ok "daemon responding"
else
  if [ "$STATUS_ONLY" -eq 1 ]; then
    bad "daemon not responding (CRE Forge cannot run)"
  else
    say "starting Docker Desktop (per-user install, not Program Files)"
    DD="$HOME/AppData/Local/Programs/DockerDesktop/Docker Desktop.exe"
    if [ -x "$DD" ]; then
      "$DD" >/dev/null 2>&1 &
      disown 2>/dev/null || true
      if wait_for 180 docker ps >/dev/null 2>&1; then
        ok "daemon responding"
      else
        bad "daemon did not come up in 180s"
      fi
    else
      bad "Docker Desktop not found at $DD"
    fi
  fi
fi

# ------------------------------------------------------------------------- CRE Forge

step "CRE Forge :$CRE_FORGE_PORT"
if probe cre "http://127.0.0.1:$CRE_FORGE_PORT/forge/_modules" '"forge":"cre-forge"' \
        "${CRE_FORGE_TOKEN:-}"; then
  ok "answering as cre-forge"
elif [ "$STATUS_ONLY" -eq 1 ]; then
  report_down "not answering as cre-forge" "$CRE_FORGE_PORT"
else
  say "docker start creforge-db creforge-redis creforge-backend"
  say "(started, never re-created: the override port map lives on the containers)"
  docker start creforge-db creforge-redis creforge-backend >/dev/null 2>&1
  if wait_for 60 probe cre "http://127.0.0.1:$CRE_FORGE_PORT/forge/_modules" \
       '"forge":"cre-forge"' "${CRE_FORGE_TOKEN:-}"; then
    ok "answering as cre-forge"
  else
    bad "did not answer as cre-forge in 60s"
  fi
fi

# --------------------------------------------------------------------------- SimForge

step "SimForge :$SIMFORGE_PORT"
if probe sim "http://127.0.0.1:$SIMFORGE_PORT/office/_modules" '"forge":"simforge"' \
        "${SIMFORGE_TOKEN:-}"; then
  ok "answering as simforge"
elif [ "$STATUS_ONLY" -eq 1 ]; then
  report_down "not answering as simforge" "$SIMFORGE_PORT"
elif [ -n "$(pids_on_port "$SIMFORGE_PORT")" ]; then
  bad "port held by $(port_holder "$SIMFORGE_PORT") and it is not SimForge - left alone"
elif [ -x "$SIMFORGE_DIR/.venv/Scripts/uvicorn.exe" ]; then
  # Its .env is at the simforge repo ROOT, not apps/api - env_file=(".env","../../.env")
  ( cd "$SIMFORGE_DIR" && start_bg simforge "./.venv/Scripts/uvicorn.exe" \
      src.main:app --host 127.0.0.1 --port "$SIMFORGE_PORT" )
  if wait_for 45 probe sim "http://127.0.0.1:$SIMFORGE_PORT/office/_modules" \
       '"forge":"simforge"' "${SIMFORGE_TOKEN:-}"; then
    ok "answering as simforge"
  else
    bad "did not answer as simforge in 45s"
  fi
else
  bad "no venv at $SIMFORGE_DIR/.venv"
fi

# ---------------------------------------------------------------------- CapitalForge

step "CapitalForge :$CAPITALFORGE_PORT"
if probe cf "http://127.0.0.1:$CAPITALFORGE_PORT/api/office/_modules" \
        '"forge_id":"capitalforge"' "${CAPITALFORGE_TOKEN:-}"; then
  ok "answering as capitalforge"
elif [ "$STATUS_ONLY" -eq 1 ]; then
  report_down "not answering as capitalforge" "$CAPITALFORGE_PORT"
elif [ -n "$(pids_on_port "$CAPITALFORGE_PORT")" ]; then
  bad "port held by $(port_holder "$CAPITALFORGE_PORT") and it is not CapitalForge"
elif [ -d "$CAPITALFORGE_DIR" ]; then
  ( cd "$CAPITALFORGE_DIR" && start_bg capitalforge npm run dev:backend )
  if wait_for 90 probe cf "http://127.0.0.1:$CAPITALFORGE_PORT/api/office/_modules" \
       '"forge_id":"capitalforge"' "${CAPITALFORGE_TOKEN:-}"; then
    ok "answering as capitalforge"
  else
    bad "did not answer as capitalforge in 90s"
  fi
else
  bad "not found at $CAPITALFORGE_DIR"
fi

# ---------------------------------------------------------------------------- Village

step "Village :$VILLAGE_PORT"
if probe village "http://127.0.0.1:$VILLAGE_PORT/api/org/departments" '"department_count"'; then
  ok "answering as the Village"
elif [ "$STATUS_ONLY" -eq 1 ]; then
  report_down "not answering as the Village" "$VILLAGE_PORT"
elif [ -n "$(pids_on_port "$VILLAGE_PORT")" ]; then
  bad "port held by $(port_holder "$VILLAGE_PORT") and it is not the Village"
elif [ -x "$VILLAGE_DIR/.venv/Scripts/python.exe" ]; then
  # Its OWN venv. A bare 3.11 has no `yaml` and the boot dies in a warning cascade.
  ( cd "$VILLAGE_DIR" && VILLAGE_PORT="$VILLAGE_PORT" \
      start_bg village "./.venv/Scripts/python.exe" app.py )
  if wait_for 120 probe village \
       "http://127.0.0.1:$VILLAGE_PORT/api/org/departments" '"department_count"'; then
    ok "answering as the Village"
  else
    bad "did not answer as the Village in 120s"
  fi
else
  bad "no venv at $VILLAGE_DIR/.venv"
fi

# -------------------------------------------------------------------------- the API

step "The Office API :$API_PORT"
start_api() {
  start_bg api "$ROOT/.venv/Scripts/python.exe" -m broker serve --port "$API_PORT"
  wait_for 45 probe api "http://127.0.0.1:$API_PORT/api/live" '"status":"live"'
}

if probe api "http://127.0.0.1:$API_PORT/api/live" '"status":"live"'; then
  RUNNING="$(api_commit)"
  if [ -z "$RUNNING" ]; then
    bad "live, but the build is UNVERIFIED - set OFFICE_OPERATOR_TOKEN so this can"
    say "      ask /api/version. A live process is not an up-to-date one, and a"
    say "      check that could not run is not a check that passed."
  elif [ "$RUNNING" = "$CHECKED_OUT" ]; then
    ok "live on ${RUNNING:0:12}, which is what is checked out"
  elif [ "$STATUS_ONLY" -eq 1 ]; then
    bad "live on ${RUNNING:0:12} but ${CHECKED_OUT:0:12} is checked out - STALE"
  elif [ -f "$RUN_DIR/api.pid" ]; then
    # Ours, so we may restart it. Nothing is killed by port.
    say "live on ${RUNNING:0:12}, stale against ${CHECKED_OUT:0:12} - restarting ours"
    stop_ours api
    sleep 2
    if start_api; then
      RUNNING="$(api_commit)"
      if [ -n "$RUNNING" ]; then ok "live on ${RUNNING:0:12}"; else ok "live (build unverified)"; fi
    else
      bad "did not come back"
    fi
  else
    bad "live on ${RUNNING:0:12} but ${CHECKED_OUT:0:12} is checked out, and this script"
    say "      did not start it. Stop it yourself; killing by port takes Docker with it."
  fi
elif [ "$STATUS_ONLY" -eq 1 ]; then
  report_down "not answering" "$API_PORT"
elif [ -n "$(pids_on_port "$API_PORT")" ]; then
  bad "port held by $(port_holder "$API_PORT") and it is not the API"
else
  if start_api; then
    RUNNING="$(api_commit)"
    if [ -n "$RUNNING" ]; then ok "live on ${RUNNING:0:12}"; else ok "live (build unverified)"; fi
  else
    bad "did not start"
  fi
fi

# A live API on the right commit can still be pointed at the wrong schema.
if probe api "http://127.0.0.1:$API_PORT/api/live" '"status":"live"'; then
  if probe api "http://127.0.0.1:$API_PORT/api/ready" '"status":"ready"'; then
    ok "ready: schema matches what this build expects"
  else
    bad "live but NOT ready - run: ./.venv/Scripts/python.exe -m alembic upgrade head"
  fi
fi

# ---------------------------------------------------------------------------- console

step "Console :$CONSOLE_PORT"
if probe console "http://127.0.0.1:$CONSOLE_PORT/login" "<html"; then
  ok "serving"
elif [ "$STATUS_ONLY" -eq 1 ]; then
  report_down "not serving" "$CONSOLE_PORT"
elif [ -n "$(pids_on_port "$CONSOLE_PORT")" ]; then
  bad "port held by $(port_holder "$CONSOLE_PORT") and it is not the console"
elif [ -d "$ROOT/console/.next" ]; then
  ( cd "$ROOT/console" && start_bg console npx next start -p "$CONSOLE_PORT" )
  if wait_for 60 probe console "http://127.0.0.1:$CONSOLE_PORT/login" "<html"; then
    ok "serving"
  else
    bad "did not serve in 60s"
  fi
else
  bad "no build at console/.next - run: (cd console && npx next build)"
fi

# ----------------------------------------------------------------------------- result

step "Result"
if [ "$FAILED" -eq 0 ]; then
  say "all six answering, on the commit that is checked out"
  exit 0
fi
say "$FAILED service(s) not healthy. Logs: $LOG_DIR"
say "Nothing was killed by port. Stop what this started with: ./scripts/dev-all.sh --stop"
exit 1
