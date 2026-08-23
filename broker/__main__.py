"""Command-line entry point for the broker package.

    python -m broker sweep                  # the three routine sweeps
    python -m broker sweep --restore-drill  # plus Gate 13, quarterly
    python -m broker health                 # freshness of every control

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


def main() -> int:
    parser = argparse.ArgumentParser(prog="broker")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("sweep", help="Run the verification sweeps")
    s.add_argument(
        "--restore-drill",
        action="store_true",
        help="Also run Gate 13. Dumps and restores into a scratch database.",
    )
    sub.add_parser("health", help="Report freshness of every control")

    args = parser.parse_args()
    if args.command == "sweep":
        return asyncio.run(_sweep(args.restore_drill))
    if args.command == "health":
        return asyncio.run(_health())
    return 2


if __name__ == "__main__":
    sys.exit(main())
