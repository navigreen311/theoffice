"""Split `failure_signatures.silent_partial` where it holds two competencies.

    .venv/Scripts/python scripts/split_silent_partial.py

WHAT THIS SEPARATES, AND WHY IT IS NOT COSMETIC
===============================================

    `silent_partial` was one key holding two different things:

      "this success means LESS THAN IT LOOKS"   an empty result, a null, a 201 that
                                               records and nothing more - the reader
                                               over-reads what came back
      "this succeeded PARTLY"                  a manifest assembled with sections
                                               omitted, an export missing record types
                                               by design, a filter that silently did
                                               not apply - the call did less than it
                                               was asked

    They are different competencies and SimForge grades them as different scenario
    classes: `silent_failure` for the first, `partial_failure` for the second. The
    first is HELD OUT - SimForge authors it and The Office may not. The second is one
    The Office must supply.

    So a manual that blurs them puts its best material in the shape it may not submit
    and has nothing for the shape it must. **The distinction was surfaced by mapping
    the sections onto the classes, not invented to fit them** - three modules had
    genuine partial-completion material sitting under a heading about over-reading.

WHY ONLY THREE MODULES
======================

    Eleven CapitalForge manuals were read. Eight have `silent_partial` sections that
    are entirely about over-reading a success - shared rule 1 restated per module, an
    absence that is not a zero. Those are correct as they stand and get no new key.

    Adding an empty `partial_failure` to all eleven would be padding, and the rule
    against it is already written: "a thin section is a fact about the module, not a
    gap to fill". A module that cannot fail partly should say nothing about it.

NOTHING ENFORCES THESE KEYS
===========================

    `validate_sections` checks the eight top-level sections and that none is empty. It
    does not read inside `failure_signatures`, and neither does anything else in this
    repository - `hard_failure` / `silent_partial` is a convention held by nobody. That
    makes this change safe and it also means the new key is equally unenforced.

BLAST RADIUS, ESTABLISHED BEFORE THE CHANGE
===========================================

    Same procedure as 46cd4f0, because moving a content_hash decertifies whoever is
    bound to it. **Zero certifications are bound to any live CapitalForge hash.** The
    three that exist are already `stale_instructions` and bound to superseded hashes
    (047d69ab, dae96ff2, 0fc8dff5). Two live grants exist - client_read and
    scan_communication - and neither module is touched here.

    A curriculum change with no dependents, as the last one was.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from broker import instructions  # noqa: E402
from broker.db import connection  # noqa: E402
from broker.humans import attributable_actor  # noqa: E402

FORGE = "capitalforge"

#: module_id -> (new silent_partial, new partial_failure)
#:
#: The text is MOVED, not rewritten. Each sentence sits under the heading that matches
#: what it teaches, and nothing is added: a split that reworded the material would make
#: it impossible to tell the reorganisation from an edit.
SPLITS: dict[str, tuple[str, str]] = {
    "compliance_manifest_assemble": (
        "200 - assembled. The shape to watch is a manifest that looks complete and is "
        "not.\n\n"
        "timestampsTampered: 0 IS NOT VERIFIED. Unverifiable is the third state and it "
        "is the one a regulator asks about. Read it with the count of what could not be "
        "checked, never alone.",

        "THE MANIFEST IS ROUTINELY INCOMPLETE, AND WHAT IS MISSING IS NAMED IN THE "
        "ANSWER. This is not an error path - a normal 200 carries omissions, and the "
        "fields that declare them have to be read every time.\n\n"
        "AN EXCLUDED RECORD TYPE IS NOT AN EMPTY ONE. excludedRecordTypes names all four "
        "and says why. A count of zero against a type the manifest does not carry means "
        "nothing about the business.\n\n"
        "A DATE-FILTERED MANIFEST IS NOT COMPLETE. Report filteredFields with it - four "
        "clocks, one label.\n\n"
        "THE LEDGER SECTION IS NOT EVERYTHING THAT TOUCHED THE CLIENT. It is what could "
        "be attributed.",
    ),
    "regulator_dossier_export": (
        "200 - exported, and A ROW NOW EXISTS. That is the difference from the sibling "
        "and it is not recoverable by doing nothing.\n\n"
        "documentsTampered: 0 IS NOT VERIFIED. Unverifiable is the third state - and the "
        "field is documentsTampered here, not timestampsTampered as on the sibling.\n\n"
        "preservedDocumentIds FROM A PRE-a2968d7 EXPORT IS NOT A PRESERVATION RECORD. It "
        "was a document inventory wearing that name.",

        "THE EXPORT OMITS SIX RECORD TYPES BY DESIGN, AND A REGULATOR READING IT WILL "
        "NOT KNOW THAT UNLESS IT IS SAID. A successful export is a partial one every "
        "time.\n\n"
        "AN EMPTY SECTION IS NOT 'THE CLIENT HAS NONE' without checking "
        "excludedRecordTypes. Six record types are omitted by design. Five - product "
        "acknowledgments, card applications, fee schedules, suitability checks, the "
        "ledger - are carried by the sibling. The sixth, business_owners, is excluded "
        "from both and for a different reason: it holds encrypted SSNs and has its own "
        "permissioned endpoint.",
    ),
    "statement_pull": (
        "200, AND THE FILTER IT APPLIED IS IN THE BODY.\n\n"
        "AN EMPTY STATEMENT LIST IS A FACT ABOUT THE RECORDS. It means nobody ingested a "
        "statement. It does not mean the client has no cards, has not been billed, or is "
        "not spending. Shared rule 1.\n\n"
        "feesCharged AND interestCharged ARE NULLABLE AND THE NULL IS NOT ZERO. Null "
        "means the ingest did not record that figure. Reporting it as zero states that "
        "no fee was charged, which is a claim about the client's account that nothing "
        "here supports.\n\n"
        "/line-items CARRIES normalizedData AS IMPORTED, not transactions, payments or a "
        "reconciliation difference. Those do not exist anywhere in this system.",

        "THE CALL CAN ANSWER A DIFFERENT QUESTION FROM THE ONE ASKED, AND SUCCEED.\n\n"
        "AN UNRECOGNISED severity FALLS BACK TO NO FILTER rather than being refused. The "
        "handler checks the value against four names and drops anything else, so "
        "severity=hgih returns an unfiltered anomaly count to a caller who asked for "
        "critical ones.\n\n"
        "BUT THE ANSWER CARRIES severityFilter, and it is the filter that was actually "
        "applied - null when none was. A response to a request that named a severity, "
        "carrying severityFilter: null, is the fallback made visible. COMPARE "
        "severityFilter TO THE VALUE YOU SENT BEFORE REPORTING ANY COUNT. This is a "
        "silent fallback with a visible answer, the same shape as an empty result "
        "carrying a basis: the information is there and has to be read.\n\n"
        "The count itself is real - a real count of all anomalies - which is why it does "
        "not look wrong. What makes it wrong is the question it answers, and "
        "severityFilter is what tells you which question that was.",
    ),
}

VERSIONS = {
    "compliance_manifest_assemble": "1.3",
    "regulator_dossier_export": "1.3",
    "statement_pull": "1.3",
}


async def main() -> int:
    async with connection() as conn:
        actor: uuid.UUID = await attributable_actor(conn)
        for module_id, (silent, partial) in SPLITS.items():
            live = await instructions.live(conn, forge_id=FORGE, module_id=module_id)
            if live is None:
                print(f"  {FORGE}/{module_id}: no live instruction, skipped")
                continue
            if "partial_failure" in live.content["failure_signatures"]:
                print(f"  {FORGE}/{module_id}: already split, unchanged")
                continue

            content = dict(live.content)
            content["failure_signatures"] = {
                **live.content["failure_signatures"],
                "silent_partial": silent,
                "partial_failure": partial,
            }
            written = await instructions.author(
                conn,
                forge_id=FORGE,
                module_id=module_id,
                instruction_version=VERSIONS[module_id],
                forge_api_version=live.forge_api_version,
                content=content,
                authored_by=actor,
                version_sensitivity=live.version_sensitivity,
            )
            print(
                f"  {FORGE}/{module_id} v{live.instruction_version} -> "
                f"v{written.instruction_version}  {live.content_hash[:12]} -> "
                f"{written.content_hash[:12]}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
