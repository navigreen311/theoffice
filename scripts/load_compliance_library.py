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

    **NOTHING STRUCTURAL PREVENTS THIS. IT IS A KNOWN PROPERTY, NOT AN OVERSIGHT.**

    `compliance_library_entry` is keyed on `entry_ref` and has no venture column, so
    the table cannot tell whose entry a row is. Burkham can change what Greenstone's
    agents read, and the only thing standing in the way is that this loader upserts
    and never deletes.

    That is a convention living in one file. **If you add a `--force`, a `--replace`
    or a truncate, you are removing the only protection there is** - and the failure
    will not look like a failure: another venture's Pack keeps citing a ref that still
    resolves, to text somebody else wrote for a different jurisdiction. V28 stays
    green throughout, because V28 asks whether the ref resolves and not whose entry
    answered.

    The general form of this is recorded in broker/compliance_couplings.py under
    A REF THAT RESOLVES TELLS YOU NOTHING ABOUT WHOSE IT IS, because it is now true
    of compliance flags as well as of library entries: resolution answers "does this
    name exist somewhere", and a reader hears "is this the right value here".

    The structural fix, if it is ever wanted, is a venture column and a composite key.
    That is a migration and a decision about whether shared entries are a feature -
    two ventures under one compliance regime arguably should share one row - and
    neither has been made. Recorded here so it is inherited as a decision rather than
    discovered as a bug.

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


def venture_of(path: Path) -> str:
    """Whose entries these are, declared by the file and cross-checked against its name.

    **A field, not the filename.** The field travels with the content, survives a rename
    and is reviewable in a diff; a filename convention re-homes nineteen entries the
    moment somebody moves a file. The filename is still checked against it, because two
    statements that disagree are worth stopping on and cost nothing to compare.

    **No `--venture` flag, deliberately.** That is the shape that makes the mistake easy:
    one operator typing the wrong venture at a prompt is exactly how one library ends up
    written under another's id, and the whole point of migration 0039 was to make that
    unrepresentable rather than merely discouraged.
    """
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    declared = str(doc.get("venture_id") or "").strip()
    if not declared:
        raise SystemExit(
            f"{path.name}: no top-level `venture_id`. Since migration 0039 an entry "
            "belongs to a venture, and this loader will not guess which - a wrong guess "
            "writes one venture's compliance text under another's id."
        )
    if declared != path.stem:
        raise SystemExit(
            f"{path.name}: declares venture_id {declared!r}, which does not match its "
            f"filename ({path.stem!r}). One of the two is wrong and this will not pick."
        )
    return declared


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


async def loaded_refs(conn: AsyncConnection) -> dict[tuple[str, str], str]:
    """(venture_id, entry_ref) -> framework, for everything already in the table.

    Keyed on the pair since 0039, so "already loaded" means already loaded FOR THIS
    VENTURE. On the single key, Greenstone's file meeting a Burkham ref of the same name
    counted as a replacement - which is the overwrite, reported as routine.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id, entry_ref, framework FROM compliance_library_entry"
        )
        return {
            (r["venture_id"], r["entry_ref"]): r["framework"] for r in await cur.fetchall()
        }


async def run(paths: list[Path], check_only: bool) -> int:
    async with connection() as conn:
        existing = await loaded_refs(conn)

        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                # A REVOKED ROLE GRANTS NOTHING - entry 150, the third of the
                # three queries that ignored it.
                #
                # `administrator` IS NOT A ROLE. `office_human_role` has held
                # ('venture_operator','compliance_officer','ivan') since 0010, so that
                # arm has never matched anything and the query has always resolved on
                # `venture_operator` alone. Left in the list would be a name somebody
                # reads as real; removed, the query says what it does.
                "SELECT h.human_id FROM office_human h "
                "JOIN office_human_role r ON r.human_id = h.human_id "
                "WHERE h.status = 'active' AND r.revoked_at IS NULL "
                "  AND r.role = 'venture_operator' LIMIT 1"
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

        ventures: dict[Path, str] = {path: venture_of(path) for path in paths}

        for path in paths:
            for entry in entries_in(path):
                bad = missing_fields(entry)
                if bad:
                    refused.append((entry["entry_ref"], bad))
                elif (ventures[path], entry["entry_ref"]) in existing:
                    to_replace.append((path, entry))
                else:
                    to_add.append((path, entry))

        print(f"{len(existing)} entr(ies) already in the table")
        for (venture, ref), framework in sorted(existing.items()):
            print(f"    {venture:18} {ref:52} {framework}")
        print()

        if refused:
            print(f"REFUSED - {len(refused)} entr(ies) missing a required field:")
            for ref, bad in refused:
                print(f"    {ref:52} missing {', '.join(bad)}")
            print()

        # Still called out, and it means something narrower now: since 0039 a replacement
        # can only touch THIS venture's entry. The warning used to say "shared with
        # whatever else cites them", which was true and was the defect.
        if to_replace:
            print(f"WOULD REPLACE {len(to_replace)} of this venture's own entr(ies):")
            for path, entry in to_replace:
                print(f"    {ventures[path]:18} {entry['entry_ref']}")
            print()

        print(f"{'WOULD ADD' if check_only else 'ADDING'} {len(to_add)} entr(ies):")
        for _, entry in to_add:
            print(f"    {entry['entry_ref']:52} {entry.get('framework')}")

        if check_only:
            print()
            print("--check: nothing was written.")
            return 1 if refused else 0

        for path, entry in to_add + to_replace:
            await knowledge.author_compliance_entry(
                conn,
                venture_id=ventures[path],
                entry_ref=entry["entry_ref"],
                framework=entry["framework"],
                jurisdiction=list(entry["jurisdiction"]),
                applicability_rule=entry["applicability_rule"],
                agent_behavior_implication=entry["agent_behavior_implication"],
                escalation_trigger=entry["escalation_trigger"],
                citation=entry["citation"],
                authored_by=authored_by,
                runtime_flag=entry.get("runtime_flag"),
                # Loaded since 0039. These two were in the files all along and had no
                # columns, so an entry tagged `draft_pending_claim_library_approval`,
                # whose Nevada claim its own author recorded as a contradiction between
                # two artifacts, read out of the database exactly like a statute.
                # `status` defaults to `draft` rather than to the file's absence meaning
                # "fine": the cautious direction is the ruling.
                status=str(entry.get("status") or "draft"),
                claim_provenance=list(entry.get("claim_provenance") or []),
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
