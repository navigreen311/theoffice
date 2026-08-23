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

    .venv/Scripts/python scripts/seed_dev_world.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.world import (  # noqa: E402
    ROSTER,
    build_world,
    certify_for_positions,
)


def main() -> int:
    dsn = os.environ.get("OFFICE_ADMIN_DSN")
    if not dsn:
        print("OFFICE_ADMIN_DSN is not set; see .env.example", file=sys.stderr)
        return 1

    with psycopg.connect(dsn) as conn:
        build_world(conn)
        certify_for_positions(conn)
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
        f"{instructions[0]} instruction(s), {certs[0]} certification(s)"
    )
    print("  development fixtures only - example.invalid endpoints, no real credentials")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
