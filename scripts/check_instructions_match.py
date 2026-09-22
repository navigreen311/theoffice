"""The live operating instructions must match the authoring script.

    .venv/Scripts/python scripts/check_instructions_match.py          # exit 1 on drift

RULED 21 SEPTEMBER 2026 (decisions entry 148)
=============================================

    *"The live operating instructions must match the authoring script. CI fails when
    they differ. Measured: `buyer_match` carried a correction entry 137 proved necessary
    until 21 September, because nobody ran the script, and every exam in between was set
    against the false text."*

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

    Nothing could have caught it. The script and the database are compared nowhere.

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
from scripts.author_cre_forge_instructions import FORGE, MANUALS, VERSION  # noqa: E402


class Difference:
    """One module's disagreement, in a shape a caller can print or assert on."""

    __slots__ = ("detail", "kind", "module_id")

    def __init__(self, module_id: str, kind: str, detail: str) -> None:
        self.module_id, self.kind, self.detail = module_id, kind, detail

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"{self.module_id}: {self.kind} - {self.detail}"


async def differences(conn: Any) -> list[Difference]:
    """Every way the live instructions and `MANUALS` disagree. Empty means they match."""
    found: list[Difference] = []
    for module_id, authored in sorted(MANUALS.items()):
        live = await instructions.live(conn, forge_id=FORGE, module_id=module_id)
        if live is None:
            found.append(Difference(
                module_id, "not live",
                "the script authors this module and no live instruction exists for it",
            ))
            continue
        if live.instruction_version != VERSION:
            # NOT A DIFFERENCE IN THE TEXT, and reported separately because the response
            # differs: a version behind means the script has not been run since it was
            # last edited, which is exactly the 20-September failure.
            found.append(Difference(
                module_id, "version behind",
                f"live is v{live.instruction_version}, the script authors v{VERSION}",
            ))
        for field in sorted(set(authored) | set(live.content)):
            ours, theirs = authored.get(field), live.content.get(field)
            if ours != theirs:
                found.append(Difference(
                    module_id, f"field {field!r} differs",
                    f"live: {_short(theirs)}  |  script: {_short(ours)}",
                ))
    return found


def _short(value: Any, width: int = 90) -> str:
    text = repr(value)
    return text if len(text) <= width else text[: width - 1] + "…"


async def main() -> int:
    async with connection() as conn:
        found = await differences(conn)

    if not found:
        print(
            f"  {len(MANUALS)} {FORGE} instruction(s) match "
            f"scripts/author_cre_forge_instructions.py at v{VERSION}"
        )
        return 0

    print(f"  DRIFT: {len(found)} difference(s) between the live instructions and the")
    print("  authoring script. Run the script, or correct it - but do not leave them")
    print("  disagreeing: an exam is bound to the live instruction's content hash, and")
    print("  a manual nobody applied is a manual nobody is being certified against.")
    for difference in found:
        print(f"    {difference.module_id:<18} {difference.kind}")
        print(f"      {difference.detail}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
