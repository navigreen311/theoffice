"""What each Forge's authoring script says its operating instructions should be.

RULED 21 SEPTEMBER 2026 (decisions entry 152)
=============================================

    *"The instruction comparator covers every Forge with authored instructions, and CI
    fails on drift in any of them. Measured: it covers cre-forge only. CapitalForge was
    checked by hand."*

WHAT WAS WRONG WITH ONE FORGE'S WORTH OF COVERAGE
=================================================

    Entry 148 built `scripts/check_instructions_match.py` because `buyer_match` carried
    a correction nobody applied for a day, and every exam in between was set against
    text that said the opposite of the code. The comparator it built opens with

        from scripts.author_cre_forge_instructions import FORGE, MANUALS, VERSION

    - one import, one Forge, singular constants. CapitalForge has eleven authored
    modules and eleven live rows, and nothing compared them. They were measured by hand
    on 21 September and matched; that is a fact about one afternoon, not a control.

    **The failure mode the narrow version allows is the one entry 148 was written for,
    on a different Forge.** A CapitalForge manual edited without a re-run would drift
    exactly as `buyer_match` did, Gate 8 would bind exams to the stale row, and CI would
    stay green because CI was only ever looking at `cre-forge`.

THE REGISTRY IS THE CONTROL, NOT THE LOOP
=========================================

    Iterating over two derivers instead of one would leave the same hole one Forge
    further along: bind a third Forge, author its instructions, forget to add it here,
    and CI reports a clean bridge again.

    So `SOURCES` is checked against the database rather than trusted. `uncovered()` asks
    which Forges have live authored instructions and no entry here, and the comparator
    treats an answer as a failure. Adding a Forge without adding its deriver breaks the
    build, which is the only version of this that stays true.

WHY TWO SHAPES, AND WHY THEY ARE NOT UNIFIED
============================================

    `cre-forge`'s manuals are Python literals in a script - hand-written prose whose
    source is the script. CapitalForge's are derived from `docs/instructions/*.md`, whose
    source is the document. Those are genuinely different provenances (see entry 39 on
    what a third copy costs), and collapsing them into one format would mean
    transcribing one of them into the other's shape - a third copy, which is the defect.

    What they share is the only thing this module needs: *what would be authored*. Both
    answer it as `{module_id: Authored}`, and the comparison is identical from there.
"""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import author_cre_forge_instructions as cre  # noqa: E402
from scripts import derive_capitalforge_instructions as capital  # noqa: E402


@dataclass(frozen=True, slots=True)
class Authored:
    """One module's instruction as its authoring script would write it."""

    version: str
    content: dict[str, str]


#: Where each Forge's manuals actually live, for a message that tells a reader what to
#: open. Not derived from the module name: `cre-forge`'s are in the script and
#: CapitalForge's are in documents the script reads, and that difference is the point.
SOURCE_FILES = {
    cre.FORGE: "scripts/author_cre_forge_instructions.py",
    capital.FORGE_ID: "docs/instructions/capitalforge-*.md",
}


async def cre_forge(conn: Any) -> dict[str, Authored]:
    """`cre-forge`, from the script's own `MANUALS` dict at its own `VERSION`.

    `conn` is unused and still taken, so every deriver has one signature. The
    alternative - a registry of two different call shapes - puts a conditional in the
    comparator for a difference the comparator has no business knowing about.
    """
    return {
        module_id: Authored(version=cre.VERSION, content=dict(content))
        for module_id, content in cre.MANUALS.items()
    }


async def capitalforge(conn: Any) -> dict[str, Authored]:
    """CapitalForge, derived from `docs/instructions/*.md`.

    **A stop is a difference.** `derive` refuses a module whose manual and whose
    registry flags disagree rather than averaging them (entry 40), and a module it
    refuses is one whose live row cannot be checked against anything. Reporting that as
    "matches" would be the comparator agreeing with a derivation that did not happen, so
    the stop is raised here and the comparator turns it into a failure that names the
    module.
    """
    ready, stops = await capital.derive(conn)
    if stops:
        raise DerivationStoppedError(capital.FORGE_ID, stops)
    return {
        row["module_id"]: Authored(version=row["version"], content=dict(row["content"]))
        for row in ready
    }


class DerivationStoppedError(Exception):
    """An authoring script refused to derive, so there is nothing to compare against."""

    def __init__(self, forge_id: str, stops: list[str]) -> None:
        super().__init__(f"{forge_id}: {len(stops)} module(s) stopped")
        self.forge_id = forge_id
        self.stops = stops


#: Every Forge whose instructions this repository authors, and how to ask what it would
#: author. `uncovered()` is what keeps this honest against the database.
SOURCES: dict[str, Callable[[Any], Awaitable[dict[str, Authored]]]] = {
    cre.FORGE: cre_forge,
    capital.FORGE_ID: capitalforge,
}


async def forges_with_live_instructions(conn: Any) -> list[str]:
    """Every Forge that has at least one live operating instruction, of any provenance."""
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT DISTINCT forge_id FROM forge_operating_instruction "
            " WHERE superseded_at IS NULL ORDER BY forge_id"
        )
        return [row[0] for row in await cur.fetchall()]


async def authored_forges(conn: Any) -> list[str]:
    """Forges whose live instructions a real account authored.

    **"Authored" means a person's account signed it**, and since entry 151 that is a
    declaration rather than an inference: `office_human.origin` is set at creation, so
    `origin = 'human'` is the account saying what it is rather than a pattern guessing.
    The two rulings of 21 September hold each other up here - this check could not have
    been written on a classifier that read `dev-all@localhost` as a person.

    The distinction it draws is real and not a convenience. A prepared test world
    inserts `forge_operating_instruction` rows for `simforge` and `voiceforge` so that
    the gates have something to read; those are scaffolding, they carry no author, and
    demanding an authoring script for them would be demanding a script to maintain
    fixtures. A row a person authored is a manual somebody is being certified against,
    and that is what must have a script behind it.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT DISTINCT i.forge_id "
            "  FROM forge_operating_instruction i "
            "  JOIN office_human h ON h.human_id = i.authored_by "
            " WHERE i.superseded_at IS NULL AND h.origin = 'human' "
            " ORDER BY i.forge_id"
        )
        return [row[0] for row in await cur.fetchall()]


async def uncovered(conn: Any) -> list[str]:
    """Forges with human-authored live instructions that no deriver here can produce.

    **This is the rule, expressed as a query.** A loop over `SOURCES` would pass for
    ever on a Forge nobody added; this asks the database what is actually authored and
    reports what is missing. The comparator fails on a non-empty answer.
    """
    return [
        forge_id for forge_id in await authored_forges(conn) if forge_id not in SOURCES
    ]
