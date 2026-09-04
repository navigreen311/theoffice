"""Load Compliance Library entries from a YAML file into the database.

    .venv/Scripts/python scripts/load_compliance_library.py PATH.yaml
    .venv/Scripts/python scripts/load_compliance_library.py --check PATH.yaml

WHY THIS EXISTS
===============

    `check_compliance_library.py` checks. Nothing loaded.

    Nineteen entries sat fully written in `packs/compliance-library/burkham-wickmont.yaml`
    while V28 reported all nineteen as resolving to nothing, and the Pack was described
    as claiming coverage it did not have. It had the coverage; the coverage was in a
    file. The entries were complete - every one carrying `applicability_rule`,
    `agent_behavior_implication`, `escalation_trigger` and `citation` - and no code
    path put them anywhere the validator could see.

    That is the same failure the nine CapitalForge operating instructions had, in a
    different table: written as files, never authored, reported by a rule as missing.
    It read as a documentation gap for as long as it went unexamined, which is
    precisely how long a "write the entry" message invites.

IT ADDS. IT DOES NOT REPLACE.
=============================

    `compliance_library_entry` is keyed on `entry_ref` alone and is shared across
    ventures. When this was written the table held exactly two entries -
    `compliance/ftc-tsr-v2` and `compliance/nv-two-party-consent-v1` - and both belong
    to **Greenstone**, whose Pack cites them. Neither is in Burkham's file.

    So a loader that truncated, or that scoped by file, would delete another venture's
    library as a side effect of loading this one. Every write here is an upsert on
    `entry_ref` and nothing is ever deleted.

    The consequence worth knowing: **two Packs citing the same `entry_ref` share one
    row.** Loading a file that redefines an entry another venture relies on overwrites
    it for both, so `--check` reports what a load would change before it changes it.

WHAT IT DOES NOT DO
===================

    **It does not assess quality.** `check_compliance_library.py` does that and should
    be run first; this refuses an entry missing a required field because the table
    would refuse it anyway, and says which field rather than surfacing a constraint
    violation.

    **It does not decide `library_gap`.** An entry absent from the file is absent, and
    a Pack claiming it is a Pack claiming coverage it does not have. That is V28's
    business and this does not paper over it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from psycopg import AsyncConnection  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from broker import knowledge  # noqa: E402
from broker.db import connection  # noqa: E402

#: The six Part 6.3 fields the table requires, plus the two that identify an entry.
REQUIRED = (
    "entry_ref",
    "framework",
    "jurisdiction",
    "applicability_rule",
    "agent_behavior_implication",
    "escalation_trigger",
    "citation",
)


def entries_in(path: Path) -> list[dict[str, Any]]:
    """Every entry in a library file, in file order."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    found = doc.get("entries") or doc.get("compliance_library") or []
    if not isinstance(found, list):
        raise SystemExit(f"{path.name}: no `entries` list found")
    return [e for e in found if isinstance(e, dict) and e.get("entry_ref")]


def missing_fields(entry: dict[str, Any]) -> list[str]:
    """Which required fields are absent or blank. Named, not counted."""
    bad = []
    for field in REQUIRED:
        value = entry.get(field)
        if (
            value is None
            or (isinstance(value, str) and not value.strip())
            or (isinstance(value, list) and not value)
        ):
            bad.append(field)
    return bad


async def loaded_refs(conn: AsyncConnection) -> dict[str, str]:
    """entry_ref -> framework, for everything already in the table."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT entry_ref, framework FROM compliance_library_entry")
        return {r["entry_ref"]: r["framework"] for r in await cur.fetchall()}


async def run(paths: list[Path], check_only: bool) -> int:
    async with connection() as conn:
        existing = await loaded_refs(conn)

        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT h.human_id FROM office_human h "
                "JOIN office_human_role r ON r.human_id = h.human_id "
                "WHERE h.status = 'active' "
                "  AND r.role IN ('administrator','venture_operator') LIMIT 1"
            )
            row = await cur.fetchone()
        if row is None and not check_only:
            raise SystemExit(
                "no active office_human holding administrator or venture_operator. "
                "An entry records who authored it and this will not invent one."
            )
        authored_by: uuid.UUID | None = row["human_id"] if row else None

        to_add: list[tuple[Path, dict[str, Any]]] = []
        to_replace: list[tuple[Path, dict[str, Any]]] = []
        refused: list[tuple[str, list[str]]] = []

        for path in paths:
            for entry in entries_in(path):
                bad = missing_fields(entry)
                if bad:
                    refused.append((entry["entry_ref"], bad))
                elif entry["entry_ref"] in existing:
                    to_replace.append((path, entry))
                else:
                    to_add.append((path, entry))

        print(f"{len(existing)} entr(ies) already in the table")
        for ref, framework in sorted(existing.items()):
            print(f"    {ref:52} {framework}")
        print()

        if refused:
            print(f"REFUSED - {len(refused)} entr(ies) missing a required field:")
            for ref, bad in refused:
                print(f"    {ref:52} missing {', '.join(bad)}")
            print()

        # Replacing is called out separately because the table is shared. An entry
        # another venture's Pack cites is overwritten for that venture too.
        if to_replace:
            print(f"WOULD REPLACE {len(to_replace)} - shared with whatever else cites them:")
            for _, entry in to_replace:
                print(f"    {entry['entry_ref']}")
            print()

        print(f"{'WOULD ADD' if check_only else 'ADDING'} {len(to_add)} entr(ies):")
        for _, entry in to_add:
            print(f"    {entry['entry_ref']:52} {entry.get('framework')}")

        if check_only:
            print()
            print("--check: nothing was written.")
            return 1 if refused else 0

        for _, entry in to_add + to_replace:
            await knowledge.author_compliance_entry(
                conn,
                entry_ref=entry["entry_ref"],
                framework=entry["framework"],
                jurisdiction=list(entry["jurisdiction"]),
                applicability_rule=entry["applicability_rule"],
                agent_behavior_implication=entry["agent_behavior_implication"],
                escalation_trigger=entry["escalation_trigger"],
                citation=entry["citation"],
                authored_by=authored_by,
                runtime_flag=entry.get("runtime_flag"),
            )

        after = await loaded_refs(conn)
        print()
        print(f"loaded. table now holds {len(after)} entr(ies).")
        return 1 if refused else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="library YAML file(s)")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report what a load would add and replace, and write nothing",
    )
    args = parser.parse_args()
    return asyncio.run(run([Path(p) for p in args.paths], args.check))


if __name__ == "__main__":
    raise SystemExit(main())
