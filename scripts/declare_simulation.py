"""Declare a venture in simulation, from the command line.

RULED 22 SEPTEMBER 2026 (decisions entry 166)
=============================================

    *"...Greenstone and Burkham Wickmont are both in simulation as of today, declared by
    Ivan Green, reason: mock runs and simulations before real clients."*

WHY A SCRIPT AND NOT A DATA MIGRATION
=====================================

    The declaration names a human, and `declared_by` must resolve to an `origin='human'`
    account. Ivan Green's account exists on one deployment. It does not exist in CI, it
    does not exist in the test database, and it will not exist on the next machine
    somebody runs `alembic upgrade head` on.

    A migration that looked up "the account named Ivan Green" would be a migration whose
    behaviour depends on which database it meets - and the two honest outcomes there are
    a migration that fails everywhere except one laptop, or one that quietly declares
    nothing. This is neither: it is a named act, run deliberately, by somebody who can
    read the refusal if the account is not there.

WHAT IT DOES NOT DO
===================

    It does not leave simulation. Leaving is a separate named act (entry 166) and it
    does not un-happen, so it is not something to reach for by re-running a script with
    a flag. `POST /api/ventures/{id}/simulation/leave` is the surface for that, and the
    console has it.

    Usage:

        python -m scripts.declare_simulation --declared-by "Ivan Green" \\
            --reason "mock runs and simulations before real clients" \\
            greenstone burkham-wickmont
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from psycopg.rows import dict_row

from broker import simulation
from broker.db import connection


async def _resolve(display_name: str) -> object:
    """The one active person with this display name, or a refusal naming the ambiguity.

    By name rather than by id because the person running this knows a name. Refusing on
    two matches rather than taking the first: `attributable_actor` records what happens
    when "the oldest one" is allowed to decide who signed something.
    """
    async with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT human_id, display_name, origin, status FROM office_human "
            " WHERE display_name = %s",
            (display_name,),
        )
        rows = [dict(r) for r in await cur.fetchall()]

    people = [r for r in rows if r["origin"] == "human" and r["status"] == "active"]
    if not people:
        raise SystemExit(
            f"no active account with origin 'human' is named {display_name!r}. "
            f"{len(rows)} account(s) carry that display name "
            f"({', '.join(sorted({r['origin'] for r in rows})) or 'none'}). A "
            "declaration of simulation is an act by a named human; create the account "
            "first, or check the spelling."
        )
    if len(people) > 1:
        raise SystemExit(
            f"{len(people)} active people are named {display_name!r}. This will not "
            "pick one - a declaration that suspends a compliance rule has to name the "
            "person who made it without ambiguity."
        )
    return people[0]["human_id"]


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ventures", nargs="+", help="venture ids to declare")
    parser.add_argument("--declared-by", required=True, help="display name")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    declared_by = await _resolve(args.declared_by)

    failures = 0
    async with connection() as conn:
        for venture_id in args.ventures:
            try:
                declared = await simulation.declare(
                    conn, venture_id=venture_id,
                    declared_by=declared_by,  # type: ignore[arg-type]
                    reason=args.reason,
                )
            except simulation.SimulationError as exc:
                # Reported and carried on, rather than stopping. Declaring two ventures
                # where one is already declared should leave the other declared.
                print(f"  {venture_id}: REFUSED - {exc}")
                failures += 1
                continue
            print(
                f"  {venture_id}: in simulation, declared by "
                f"{declared.declared_by_name} on {declared.declared_at.date()}"
            )

    print()
    print("Deferred is not verified. No attestation may read TRUE on the strength of")
    print("this, so a department's compliance coupling cannot be attested while it")
    print("stands - entry 166.")
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(main()))
