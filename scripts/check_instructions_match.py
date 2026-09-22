"""The live operating instructions must match the authoring script — for every Forge.

    .venv/Scripts/python scripts/check_instructions_match.py          # exit 1 on drift

RULED 21 SEPTEMBER 2026 (decisions entries 148 and 152)
=======================================================

    148: *"The live operating instructions must match the authoring script. CI fails
    when they differ. Measured: `buyer_match` carried a correction entry 137 proved
    necessary until 21 September, because nobody ran the script, and every exam in
    between was set against the false text."*

    152: *"The instruction comparator covers every Forge with authored instructions, and
    CI fails on drift in any of them. Measured: it covers cre-forge only. CapitalForge
    was checked by hand."*

WHAT HAPPENED
=============

    Entry 137 proved `buyer_match`'s manual wrong: `correct_sequence` said *"`limit`
    bounds the page, not the population"*, and the service slices its ranked list to
    `limit` BEFORE counting, so `total` IS the page. The correction was written into
    `scripts/author_cre_forge_instructions.py` and merged on 20 September.

    **Nobody ran the script.** `main` skips a module already live at `VERSION`, `VERSION`
    was not bumped, and the live row kept the false claim until 21 September. Every
    `buyer_match` exam set in between - including the ones that produced the verdicts of
    the 20th and the 21st - was bound to an instruction that said the opposite of what
    the code does.

    Nothing could have caught it. The script and the database were compared nowhere.

AND THEN THIS FILE HAD THE SAME SHAPE OF GAP
============================================

    It was written for one Forge - `from scripts.author_cre_forge_instructions import
    FORGE, MANUALS, VERSION` - and CapitalForge's eleven authored modules were compared
    by nothing. They were measured by hand on 21 September and matched, which is a fact
    about that afternoon rather than a control. A CapitalForge manual edited without a
    re-run would have drifted exactly as `buyer_match` did, under a green CI.

    Entry 152 is that hole closed, and `scripts/instruction_sources.py` is where each
    Forge's deriver lives. **The coverage is checked, not assumed:** `uncovered()` asks
    the database which Forges have live authored instructions and which of those have no
    deriver, and an answer is a failure. Binding a Forge and forgetting to register it
    breaks the build instead of reporting a clean bridge.

WHY THIS COMPARES CONTENT AND NOT HASHES
========================================

    `content_hash` is computed by a database function, `instruction_hash(content)`, in a
    BEFORE INSERT trigger. Reproducing it in Python would be a second spelling of the one
    thing both sides have to agree on, and the first time either moved they would
    disagree silently - which is the defect this file exists to catch, one level down.

    So the comparison is on `content` itself, field by field, and the hash is never
    recomputed here.

WHAT IT CANNOT TELL YOU
=======================

    Whether the script is RIGHT. It compares two things that are meant to be identical
    and says where they differ; which one is wrong is a question for whoever reads the
    difference. The live row is not authoritative and neither is the file.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from broker import instructions  # noqa: E402
from broker.db import connection  # noqa: E402
from scripts.instruction_sources import (  # noqa: E402
    SOURCE_FILES,
    SOURCES,
    DerivationStoppedError,
    forges_with_live_instructions,
    uncovered,
)


class Difference:
    """One module's disagreement, in a shape a caller can print or assert on."""

    __slots__ = ("detail", "forge_id", "kind", "module_id")

    def __init__(self, forge_id: str, module_id: str, kind: str, detail: str) -> None:
        self.forge_id = forge_id
        self.module_id, self.kind, self.detail = module_id, kind, detail

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"{self.forge_id}/{self.module_id}: {self.kind} - {self.detail}"


async def differences(conn: Any) -> list[Difference]:
    """Every way the live instructions and the authoring scripts disagree.

    Empty means they match, on every Forge this repository authors for - and that every
    Forge with authored instructions has a script to be compared against.
    """
    found: list[Difference] = []

    # THE COVERAGE CHECK COMES FIRST, because a Forge nobody compares is not a match.
    for forge_id in await uncovered(conn):
        found.append(Difference(
            forge_id, "-", "no authoring script",
            f"{forge_id} has live operating instructions and no deriver in "
            "scripts/instruction_sources.py, so nothing checks them. Entry 152: the "
            "comparator covers every Forge with authored instructions.",
        ))

    live_anywhere = set(await forges_with_live_instructions(conn))

    for forge_id, derive in sorted(SOURCES.items()):
        # A FORGE WITH NO LIVE ROWS AT ALL HAS NOT DRIFTED - it has not been authored on
        # this database. That is the state of a fresh one and of CI's, and reporting
        # eleven "not live" differences for it would drown the one that means something.
        # A forge with SOME live rows is held to all of them: a module the script
        # authors and this database does not hold is the drift this file exists for.
        if forge_id not in live_anywhere:
            continue
        try:
            authored_modules = await derive(conn)
        except DerivationStoppedError as stopped:
            # A refusal to derive is reported per module it named. The script stopped
            # because a manual and a registry row disagree (entry 40), and a live row
            # with nothing to compare against is not a row that matches.
            for stop in stopped.stops:
                found.append(Difference(
                    forge_id, stop.split(":", 1)[0], "derivation stopped",
                    f"the authoring script refuses to derive this module: {stop}",
                ))
            continue

        for module_id, authored in sorted(authored_modules.items()):
            live = await instructions.live(
                conn, forge_id=forge_id, module_id=module_id
            )
            if live is None:
                found.append(Difference(
                    forge_id, module_id, "not live",
                    "the script authors this module and no live instruction exists "
                    "for it",
                ))
                continue
            if live.instruction_version != authored.version:
                # NOT A DIFFERENCE IN THE TEXT, and reported separately because the
                # response differs: a version behind means the script has not been run
                # since it was last edited, which is exactly the 20-September failure.
                found.append(Difference(
                    forge_id, module_id, "version behind",
                    f"live is v{live.instruction_version}, the script authors "
                    f"v{authored.version}",
                ))
            for field in sorted(set(authored.content) | set(live.content)):
                ours = authored.content.get(field)
                theirs = live.content.get(field)
                if ours != theirs:
                    found.append(Difference(
                        forge_id, module_id, f"field {field!r} differs",
                        f"live: {_short(theirs)}  |  script: {_short(ours)}",
                    ))
    return found


def _short(value: Any, width: int = 90) -> str:
    text = repr(value)
    return text if len(text) <= width else text[: width - 1] + "…"


async def main() -> int:
    async with connection() as conn:
        found = await differences(conn)
        live = set(await forges_with_live_instructions(conn))
        counts = {}
        for forge_id, derive in sorted(SOURCES.items()):
            if forge_id not in live:
                continue
            try:
                counts[forge_id] = len(await derive(conn))
            except DerivationStoppedError:
                counts[forge_id] = 0

    if not found:
        for forge_id, count in sorted(counts.items()):
            print(f"  {count} {forge_id} instruction(s) match "
                  f"{SOURCE_FILES.get(forge_id, '(unknown source)')}")
        return 0

    print(f"  DRIFT: {len(found)} difference(s) between the live instructions and the")
    print("  authoring scripts. Run the script, or correct it - but do not leave them")
    print("  disagreeing: an exam is bound to the live instruction's content hash, and")
    print("  a manual nobody applied is a manual nobody is being certified against.")
    for difference in found:
        print(f"    {difference.forge_id}/{difference.module_id:<30} "
              f"{difference.kind}")
        print(f"      {difference.detail}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
