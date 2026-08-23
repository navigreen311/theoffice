"""Command-line entry point for the generators package.

    python -m generators validate packs/greenstone.yaml

Exits 1 on any FAIL or NOT_RUN, so it is usable as a CI gate rather than only as a
report. NOT_RUN exits non-zero deliberately: a Pack whose bridge check could not run
has not been validated, and a green exit code would say otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Imported at module level, not lazily inside _validate, because broker/__init__.py
# sets the Windows selector event-loop policy - and it has to run BEFORE asyncio.run()
# creates a loop. Deferred, the policy arrives too late and psycopg's async driver
# retries to a 30-second PoolTimeout instead of connecting.
import broker  # noqa: F401  - imported for its event-loop policy side effect
from generators.pack import PackLoadError, load_pack
from generators.validator import validate


async def _validate(path: Path, use_db: bool) -> int:
    try:
        pack = load_pack(path)
    except PackLoadError as exc:
        print(f"FAILED TO LOAD: {exc}", file=sys.stderr)
        return 2

    conn = None
    ctx = None
    if use_db and os.environ.get("OFFICE_APP_DSN"):
        from broker.db import connection

        ctx = connection()
        conn = await ctx.__aenter__()

    try:
        report = await validate(pack, conn)
    finally:
        if ctx is not None:
            await ctx.__aexit__(None, None, None)

    print(f"Pack: {pack.identity.venture_name}  (venture_id: {pack.venture_id})")
    print(report.render())

    if report.failures:
        print(f"\nGate 2 BLOCKED by {len(report.failures)} failing rule(s).", file=sys.stderr)
        return 1
    if report.not_run:
        deferred = {r.rule_id for r in report.not_run}
        if deferred - {"V24"}:
            print(
                f"\nGate 2 INCOMPLETE: {sorted(deferred - {'V24'})} did not run. "
                "NOT_RUN is not a pass - run with a database connection.",
                file=sys.stderr,
            )
            return 1
    print("\nGate 2 PASSED.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="generators")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="Run the Pack Validator (Gate 2)")
    v.add_argument("pack", type=Path)
    v.add_argument(
        "--no-db",
        action="store_true",
        help="Skip world-aware rules (V2/V6/V11). They report NOT_RUN, which is not a pass.",
    )

    args = parser.parse_args()
    if args.command == "validate":
        return asyncio.run(_validate(args.pack, use_db=not args.no_db))
    return 2


if __name__ == "__main__":
    sys.exit(main())
