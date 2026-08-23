"""Command-line entry point for the broker package.

    python -m broker serve                  # the Operations API
    python -m broker sweep                  # the three routine sweeps
    python -m broker sweep --restore-drill  # plus Gate 13, quarterly
    python -m broker health                 # freshness of every control

`serve` exists rather than `uvicorn broker.app:app` because **uvicorn explicitly
installs `WindowsProactorEventLoopPolicy` on Windows**, overriding the selector policy
`broker/__init__.py` sets - and psycopg's async driver cannot run on Proactor. The
symptom is not an error: the server starts, accepts connections, and every request hangs
until the client times out, with the real cause in a log line uvicorn prints once at
startup. Running the server with `loop="none"` leaves our policy alone.

Designed to be invoked by cron or a systemd timer. `health` exits non-zero when any
control is `never_run`, `stale` or `failing`, so a monitor can watch the exit code
rather than parse the output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import broker  # noqa: F401  - imported for its event-loop policy side effect
from broker import sweeps
from broker.db import connection


async def _sweep(include_restore_drill: bool) -> int:
    results = await sweeps.run_all(include_restore_drill=include_restore_drill)
    if not results:
        print("no sweeps ran; another process holds every lock", file=sys.stderr)
        return 1

    failed = 0
    for kind, result in sorted(results.items()):
        marker = "ok " if result.passed else "FAIL"
        print(f"{marker} {kind}: {result.status} over {result.denominator} item(s)")
        for key, value in sorted(result.findings.items()):
            if value not in (None, [], {}, 0, False):
                print(f"       {key}: {value}")
        if not result.passed:
            failed += 1
    return 1 if failed else 0


async def _health() -> int:
    async with connection() as conn:
        report = await sweeps.freshness(conn)

    unhealthy = [k for k, v in report.items() if not v["healthy"]]
    for kind, state in sorted(report.items()):
        marker = "ok " if state["healthy"] else "!! "
        print(f"{marker} {kind}: {state['state']}")
        print(f"       {json.dumps({k: v for k, v in state.items() if k != 'state'})}")

    if unhealthy:
        print(
            f"\nUNHEALTHY: {', '.join(sorted(unhealthy))}. "
            "never_run and stale are not passes - an absence of findings from a check "
            "that did not run is not evidence.",
            file=sys.stderr,
        )
        return 1
    return 0


def _serve(host: str, port: int, reload: bool) -> int:
    """Run the Operations API without letting uvicorn replace the event-loop policy.

    `loop="none"` is the important argument. uvicorn's default loop setup calls
    `asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())` on Windows, and
    psycopg's async driver cannot use Proactor - so every database-backed request hangs
    rather than failing, which is considerably harder to diagnose than a crash.
    """
    import uvicorn

    if reload:
        # Reload needs uvicorn to own the process, so the policy has to be set in the
        # child. UVICORN_LOOP is not a thing; use the programmatic path either way.
        print(
            "reload is not supported here: it requires uvicorn to own the event loop, "
            "which is exactly what this command avoids on Windows.",
            file=sys.stderr,
        )
        return 2

    config = uvicorn.Config(
        "broker.app:app", host=host, port=port, loop="none", log_level="info"
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="broker")
    sub = parser.add_subparsers(dest="command", required=True)

    srv = sub.add_parser("serve", help="Run the Operations API")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8080)
    srv.add_argument("--reload", action="store_true")

    s = sub.add_parser("sweep", help="Run the verification sweeps")
    s.add_argument(
        "--restore-drill",
        action="store_true",
        help="Also run Gate 13. Dumps and restores into a scratch database.",
    )
    sub.add_parser("health", help="Report freshness of every control")

    args = parser.parse_args()
    if args.command == "serve":
        return _serve(args.host, args.port, args.reload)
    if args.command == "sweep":
        return asyncio.run(_sweep(args.restore_drill))
    if args.command == "health":
        return asyncio.run(_health())
    return 2


if __name__ == "__main__":
    sys.exit(main())
