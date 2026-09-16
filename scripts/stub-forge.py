"""Forges that answer the one question Gate 0 asks, for the smoke script.

WHY THIS EXISTS

    V2 used to read `forge_registry.health_status` and return. Since entry 99 it asks the
    Forge - `GET {base_url}/_modules`, under the Forge's own auth model - and a Forge that
    cannot be asked blocks Gate 0, by Ivan's ruling of 15 September.

    The smoke world's Forges are seeded at `https://example.invalid` with credential refs
    pointing at environment variables a runner does not have, so every smoke run stopped
    at Gate 0:

        run 8f2c1e04 stopped at gate 0 (blocked)
          bridge not operational: cre-forge: tenant credential unavailable ...

    That is the rule working and it is not a demonstration of anything. Eleven checks
    below the ladder need a run that reaches Gate 2, the same way seven of them needed one
    that reached Gate 4 before `stub-village.py` existed.

WHY A STUB SERVER RATHER THAN A MONKEYPATCH

    The suite gets this from `tests/world.py::dispatch_from_registry`, which replaces
    `forge_modules.read` in the calling process. The API runs in a different one, so that
    shape cannot work here - and it would skip the very path this script exists to
    exercise: the credential resolve, the HTTP call, the manifest parse, the unreachable
    branch. `stub-village.py` is here for the same reason and says so at greater length.

WHAT IT SERVES

    `/{forge_id}/_modules`, the path `broker.forge_modules` asks for, answering with the
    modules that Forge's rows were seeded with - read from `tests/world.py`, so the stub
    and the seeded world cannot drift. The shape is the richer of the two the reader
    accepts: `{module_id, is_mutating, idempotency_support}`, matching the registry rows
    the same fixture writes.

WHAT IT DOES NOT SERVE

    **Module dispatch.** A POST to `/{forge_id}/{module_id}` is a 404, deliberately. This
    answers the existence question - which is what Gate 0 and V32 ask - and a stub that
    returned `{"ok": true}` for any call would make a brokered call look like it worked
    against a Forge that did nothing. That is the failure `forge_module_exclusion` exists
    to name, and this script will not manufacture it.

    **Authorisation.** The bearer token is accepted unread. The credential still has to
    RESOLVE for the broker to get this far, which is the half the smoke world was missing;
    what the token says is CapitalForge's business, not a stub's.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.world import CRE_MODULES, FORGE_ID, SIM_MODULES, VOICE_MODULES  # noqa: E402

#: What each Forge answers with. One source: the same tuples `build_world` registers, so
#: a module added to the seeded world is served here without a second edit.
#:
#: SimForge's list was written out here rather than imported, and it named
#: `run_scenario_pack` - a module the real SimForge does not dispatch. **A stub that
#: serves what nothing serves makes the smoke world agree with a fixture instead of with
#: a Forge**, which is the one thing a stub must not do. It comes from `SIM_MODULES` now,
#: like the other two.
SERVED: dict[str, tuple[str, ...]] = {
    FORGE_ID: CRE_MODULES,
    "simforge": SIM_MODULES,
    "voiceforge": VOICE_MODULES,
}

#: The seed writes every module row `is_mutating = TRUE, idempotency_support = 'key'`.
#: The manifest says the same thing rather than a truer thing: a stub that corrected the
#: registry would make `verify_forge_modules.py` report a drift this script invented.
SHAPE = {"is_mutating": True, "idempotency_support": "key"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        if len(parts) != 2 or parts[1] != "_modules":
            self.send_error(404, "stub Forge serves only /{forge_id}/_modules")
            return

        forge_id = parts[0]
        modules = SERVED.get(forge_id)
        if modules is None:
            self.send_error(404, f"no stub Forge for {forge_id!r}")
            return

        body = json.dumps(
            {"modules": [{"module_id": m, **SHAPE} for m in sorted(modules)]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        """Silent. The smoke script's output is a merge gate, compared byte for byte."""


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8098
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(
        f"stub Forge on {port}: "
        + ", ".join(f"{f} ({len(m)} modules)" for f, m in sorted(SERVED.items())),
        flush=True,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
