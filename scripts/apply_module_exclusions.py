"""Record the declared module exclusions, so no agent can ever be granted them.

    .venv/Scripts/python scripts/apply_module_exclusions.py           # apply
    .venv/Scripts/python scripts/apply_module_exclusions.py --check   # verify only

Reads `broker.module_exclusions.ALL` and upserts it into `forge_module_exclusion`,
where the BEFORE INSERT trigger on `agent_forge_grant` enforces it. Idempotent: the
reason and evidence are refreshed, `recorded_at` is left as first recorded, because
when an exclusion was first found is worth more than when the script last ran.

`--check` exits 1 if anything declared is missing or has drifted, and prints which.
That is the form CI wants: a declaration that was never applied is the same failure
as no declaration at all, and it is invisible from the code alone.

WHAT IT DOES NOT DO
===================

    It never deletes. An exclusion removed from the declaration stays in the table
    until somebody removes it deliberately, with the evidence that it no longer
    applies. Removing an exclusion re-opens a module for granting, and that is not a
    thing a seeder should do as a side effect of an edit.

**Requires OFFICE_ADMIN_DSN.** `office_app` holds SELECT here and nothing else -
recording an exclusion is a deliberate act, not something the broker does to itself.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from broker.module_exclusions import ALL  # noqa: E402

RECORDED_BY = "scripts/apply_module_exclusions.py"


def apply(conn: psycopg.Connection) -> tuple[int, int]:
    """Upsert every declared exclusion. Returns (inserted, updated)."""
    inserted = updated = 0
    for e in ALL:
        row = conn.execute(
            """
            INSERT INTO forge_module_exclusion
                   (forge_id, module_id, reason, evidence, recorded_by)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (forge_id, module_id) DO UPDATE
               SET reason = EXCLUDED.reason,
                   evidence = EXCLUDED.evidence,
                   recorded_by = EXCLUDED.recorded_by
            RETURNING (xmax = 0) AS was_insert
            """,
            (e.forge_id, e.module_id, e.reason, e.evidence, RECORDED_BY),
        ).fetchone()
        if row is not None and row[0]:
            inserted += 1
        else:
            updated += 1
    return inserted, updated


def check(conn: psycopg.Connection) -> list[str]:
    """Return a human-readable defect per declared exclusion that is not recorded."""
    defects: list[str] = []
    for e in ALL:
        row = conn.execute(
            "SELECT reason, evidence FROM forge_module_exclusion "
            "WHERE forge_id = %s AND module_id = %s",
            (e.forge_id, e.module_id),
        ).fetchone()
        if row is None:
            defects.append(f"{e.forge_id}/{e.module_id}: declared but NOT RECORDED")
            continue
        if row[0] != e.reason:
            defects.append(f"{e.forge_id}/{e.module_id}: recorded reason differs from declaration")
        if row[1] != e.evidence:
            defects.append(
                f"{e.forge_id}/{e.module_id}: recorded evidence differs from declaration"
            )
    return defects


def main() -> int:
    dsn = os.environ.get("OFFICE_ADMIN_DSN")
    if not dsn:
        print("OFFICE_ADMIN_DSN is not set; see .env.example", file=sys.stderr)
        return 2

    check_only = "--check" in sys.argv

    with psycopg.connect(dsn) as conn:
        if check_only:
            defects = check(conn)
            if defects:
                print(f"{len(defects)} defect(s):", file=sys.stderr)
                for d in defects:
                    print(f"  - {d}", file=sys.stderr)
                return 1
            print(f"All {len(ALL)} declared exclusions are recorded and match.")
            return 0

        inserted, updated = apply(conn)
        conn.commit()
        total_row = conn.execute("SELECT count(*) FROM forge_module_exclusion").fetchone()
        total = total_row[0] if total_row else 0
        print(f"{inserted} inserted, {updated} refreshed. Table holds {total} exclusion(s).")
        for e in ALL:
            print(f"  {e.forge_id}/{e.module_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
