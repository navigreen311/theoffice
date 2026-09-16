"""Seed a development world: Forges bridged, instructions authored, roster certified.

A fresh database has no Forge registry, so Gate 0 refuses every provisioning run - which
is Gate 0 doing exactly its job, and also means the console's most important screens
never render anything. The Pack editor shows a document, the provisioning console shows
one blocked gate, and the Gate 4 review form - the highest-risk piece of UI in the
console - is unreachable.

This is the same world `tests/world.py` builds, imported rather than copied. Two
definitions would drift: they would disagree about which Forges are registered or which
modules have instructions, and whichever was read last would look correct.

**Development only.** It registers Forges at `https://example.invalid` with credential
refs pointing at environment variables that do not exist, and it writes certifications
directly rather than through SimForge. Neither is survivable in an environment where
anything real is on the other end of a Forge call.

It is idempotent by deletion: it clears the world it owns before rebuilding it, so
running it twice leaves the same state. That clearing includes **all** certifications
and instructions, which is safe in a scratch database and is not safe anywhere else.

**So it refuses every database that does not carry the disposable marker** - the
database-level setting `office.disposable_world`, whose value must be the database's own
name. `tests.world.assert_disposable` holds the reasoning; decisions entry 95 holds what
this script would have done to the development database before the marker existed.

    .venv/Scripts/python scripts/seed_dev_world.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from generators.pack import load_pack  # noqa: E402
from tests.world import (  # noqa: E402
    PACK_PATH,
    ROSTER,
    NotADisposableDatabaseError,
    assert_disposable,
    build_world,
    certify_for_positions,
    seed_nv_discharge,
)


def register_budget(conn: psycopg.Connection) -> str:
    """Give the venture a budget, which is what puts it in the directory.

    A venture is an engagement rather than a table: `/api/ventures` derives it from
    grants, manifest rows or a budget. Grants and manifest rows are Gate 5 output and a
    dev seed has no business inventing them - but a budget is a governance fact a human
    sets, declared in the Pack, and setting it is exactly what an operator does before
    anything is provisioned.

    So the seeded venture appears with a cap and zero grants, which is the true state:
    planned and funded, nothing provisioned. Without it the Venture Dashboard and the
    Venture Directory have nothing to render, and the smoke script cannot exercise
    either - which it quietly did not, for three increments.
    """
    pack = load_pack(PACK_PATH)
    budget = pack.budget
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO venture_budget
              (venture_id, monthly_usd_cap, soft_cap_pct, hard_cap_action,
               per_agent_usd_daily_cap, per_task_usd_ceiling)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (venture_id) DO UPDATE
            SET monthly_usd_cap = EXCLUDED.monthly_usd_cap,
                soft_cap_pct = EXCLUDED.soft_cap_pct,
                hard_cap_action = EXCLUDED.hard_cap_action,
                per_agent_usd_daily_cap = EXCLUDED.per_agent_usd_daily_cap,
                per_task_usd_ceiling = EXCLUDED.per_task_usd_ceiling
            """,
            (pack.venture_id, budget.monthly_usd_cap, budget.soft_cap_pct,
             budget.hard_cap_action, budget.per_agent_usd_daily_cap,
             budget.per_task_usd_ceiling),
        )
    conn.commit()
    return pack.venture_id


def main() -> int:
    dsn = os.environ.get("OFFICE_ADMIN_DSN")
    if not dsn:
        print("OFFICE_ADMIN_DSN is not set; see .env.example", file=sys.stderr)
        return 1

    with psycopg.connect(dsn) as conn:
        # Refused here as well as inside `build_world`, so the message arrives before
        # anything else is printed and names the script the operator actually ran. The
        # check itself has one definition (decisions entry 95).
        try:
            assert_disposable(conn)
        except NotADisposableDatabaseError as refusal:
            print(f"refusing to seed: {refusal}", file=sys.stderr)
            return 1
        build_world(conn)
        certify_for_positions(conn)
        # THE NV DISCHARGE, AND WHAT IT IS AND IS NOT.
        #
        # Item F declared `recording_consent_required` human-held, which is correct: no
        # agent of this venture can place or record a call. V34 then asks whether a named
        # human has verified the obligation, and for the REAL venture the answer is no -
        # V34 FAILs and Gate 2 blocks, pending counsel on Nevada.
        #
        # A development world that stops at Gate 2 renders no Gate 4 review form, and the
        # console smoke check loses seven checks about a screen that has nothing to do with
        # Nevada. So this world assumes counsel has signed, exactly as it assumes every
        # agent is certified two lines above.
        #
        # **It is labelled rather than silent.** The smoke output prints the assumption
        # beside the capacity figures, so a reader is never shown a green ladder without
        # being told what was granted to produce it.
        seed_nv_discharge(conn)
        venture = register_budget(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM forge_registry")
            forges = cur.fetchone()
            cur.execute("SELECT count(*) FROM forge_operating_instruction")
            instructions = cur.fetchone()
            cur.execute("SELECT count(*) FROM certification WHERE state = 'certified'")
            certs = cur.fetchone()

    assert forges and instructions and certs
    print(
        f"  {forges[0]} Forge(s) registered, {len(ROSTER)} agent(s), "
        f"{instructions[0]} instruction(s), {certs[0]} certification(s), "
        f"venture {venture} budgeted"
    )
    print("  development fixtures only - example.invalid endpoints, no real credentials")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
