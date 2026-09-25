"""Derive Forge Operating Instructions from the manuals, for authoring.

    .venv/Scripts/python scripts/derive_capitalforge_instructions.py          # emit, write nothing
    .venv/Scripts/python scripts/derive_capitalforge_instructions.py --apply  # author them

WHY A SCRIPT AND NOT A TRANSCRIPTION
====================================

    `forge_operating_instruction` held rows typed into the console beside documents that already
    existed - two sources for one thing. The adapter's `manualVersion` constants are the worked
    example of what that costs: ten of eleven are stale against the documents, and the only one
    that agrees has never been revised (decisions.md entry 39). A hand transcription of ten
    manuals creates a third copy and drifts the same way.

    The document is the source. Its front-matter `**Version:**` is the instruction version.

THE SEVEN SECTIONS COME FROM HEADINGS. THE EIGHTH DOES NOT.
===========================================================

    `compliance_coupling` is NOT derived from the manual, and entry 40 is why. A manual's WHICH
    LAWS THIS TOUCHES section is prose that names entries in BOTH directions - four of the ten
    name at least one in order to rule it out, and one of those four reads affirmatively:

        `compliance/outbound-contact-boundary-v1` - scoped. Recording consent is not outbound
        contact and does not invoke the three-part test. But ...

    A regex sees an assertion. Deriving from it would couple `record_consent` to a boundary its
    own prose denies, and `client_read` to bureau handling that governs a different module.

    So the flag set comes from `forge_module_registry.compliance_flags_implied` - already
    per-module, already narrowed, and correct in every case that is independently checkable -
    joined to `compliance_library_entry` for the refs. The manual's laws section is a CHECK.

REFUSES RATHER THAN GUESSES
===========================

    Where the manual's affirmative refs and the registry's flags disagree, this stops and reports
    the module. It does not average them, prefer one, or drop the difference. With entry 40's
    ruling applied to `record_consent` it should stop nowhere; if it stops, that is a finding
    about a manual or a registry row, and it wants a person.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import broker  # noqa: E402,F401  - imported for its event-loop policy side effect
from broker import humans, instructions  # noqa: E402
from broker.db import connection  # noqa: E402

MANUALS = ROOT / "docs" / "instructions"
FORGE_ID = "capitalforge"

#: Manual heading -> section key. Keyed on TEXT, not number: the numbering differs per module
#: (`submit_application` puts the gates at 4 and the sequence at 5), so a positional map would
#: silently mis-assign.
#: The manuals were written by hand over weeks and a heading has more than one spelling.
#: `WHAT EACH INPUT MEANS` and `WHAT THE INPUTS MEAN` are the same section; three of the eleven
#: use the second. Listed rather than fuzzy-matched: a synonym is a fact about these documents
#: and belongs where someone can see which ones are accepted.
HEADING_TO_SECTION = {
    ("WHAT IT DOES NOT DO",): "what_it_does_not_do",
    ("WHAT IT DOES",): "what_it_does",
    ("WHAT EACH INPUT MEANS", "WHAT THE INPUTS MEAN"): "inputs",
    ("THE CORRECT SEQUENCE",): "correct_sequence",
    ("WHAT FAILURE LOOKS LIKE",): "failure_signatures",
    ("RETRY VS ESCALATE",): "retry_vs_escalate",
    ("NEVER",): "never_do",
}

#: A ref named in a paragraph carrying one of these is being ruled OUT. Entry 40.
NEGATION_MARKERS = (
    "no bureau entry applies",
    "no fair-treatment entry applies",
    "scoped.",
    "does not apply",
    "not this module",
)


def _sections(text: str) -> dict[str, str]:
    """Every `## N. HEADING` block, keyed by its heading text, uppercased."""
    out: dict[str, str] = {}
    parts = re.split(r"^## (.+?)$", text, flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        heading = re.sub(r"^\d+\.\s*", "", parts[i]).strip().upper()
        out[heading] = parts[i + 1].strip()
    return out


def _match_heading(secs: dict[str, str], wanted: tuple[str, ...]) -> str | None:
    """SHORTEST prefix match, per spelling, in order.

    Shortest, not longest: `WHAT IT DOES NOT DO` starts with `WHAT IT DOES`, so a
    longest-first search answers the shorter key with the longer section and both come back
    identical. That is what the first run did - every module reported `what_it_does` and
    `what_it_does_not_do` at exactly the same byte length, which is the tell.
    """
    for spelling in wanted:
        candidates = [h for h in secs if h.startswith(spelling)]
        if candidates:
            return secs[min(candidates, key=len)]
    return None


def _refs(laws_body: str) -> tuple[set[str], set[str]]:
    """(declared, ruled_out). A ref in a scoping or negating paragraph is ruled out."""
    declared: set[str] = set()
    ruled_out: set[str] = set()
    for para in re.split(r"\n\s*\n", laws_body):
        found = set(re.findall(r"compliance/[a-z0-9-]+", para))
        if not found:
            continue
        low = para.lower()
        if any(marker in low for marker in NEGATION_MARKERS):
            ruled_out.update(found)
        else:
            declared.update(found)
    return declared, ruled_out - declared


async def derive(conn: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """(ready, stops) — what this script would author. **Writes nothing.**

    EXTRACTED SO THE COMPARATOR CAN CALL IT. Ruled 21 September 2026, entry 152:

        *"The instruction comparator covers every Forge with authored instructions, and
        CI fails on drift in any of them. Measured: it covers cre-forge only.
        CapitalForge was checked by hand."*

    The comparator could not reach this before. `author_cre_forge_instructions` holds
    its manuals in a module-level `MANUALS` dict, so importing it is enough; this script
    derives its manuals from documents, inside `main`, behind an `argparse` call and a
    module-level `raise SystemExit`. There was no way to ask it what it would author
    without running it.

    So the derivation lives here and both callers use it: `main` derives then authors,
    the comparator derives then compares. A second spelling of the derivation would
    drift from this one exactly as the manuals drifted from the database.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT module_id, compliance_flags_implied FROM forge_module_registry "
            "WHERE forge_id = %s",
            (FORGE_ID,),
        )
        registry = {m: set(f or []) for m, f in await cur.fetchall()}
        await cur.execute("SELECT entry_ref, runtime_flag FROM compliance_library_entry")
        lib = dict(await cur.fetchall())

    flag_to_ref = {v: k for k, v in lib.items()}
    stops: list[str] = []
    ready: list[dict[str, Any]] = []

    for path in sorted(MANUALS.glob(f"{FORGE_ID}-*.md")):
        text = path.read_text(encoding="utf-8")
        # Not anchored to line start: `record_consent` carries Forge, Module and Endpoint on
        # one line. Anchoring is what made it the only manual with "no Module line".
        mid_m = re.search(r"\*\*Module:\*\*\s*`([a-z_]+)`", text)
        ver_m = re.search(r"\*\*Version:\*\*\s*([0-9.]+)", text)
        if not mid_m or not ver_m:
            stops.append(f"{path.name}: no Module or Version line in the front matter")
            continue
        module_id, version = mid_m.group(1), ver_m.group(1)
        if module_id not in registry:
            print(f"  skip   {module_id:<30} not in forge_module_registry")
            continue

        secs = _sections(text)
        content: dict[str, str] = {}
        missing: list[str] = []
        for heading, key in HEADING_TO_SECTION.items():
            body = _match_heading(secs, heading)
            if body:
                content[key] = body
            else:
                missing.append(heading[0])
        if missing:
            stops.append(f"{module_id}: no heading for {', '.join(missing)}")
            continue

        laws = next((v for h, v in secs.items() if "WHICH LAWS" in h), "")
        declared, ruled_out = _refs(laws)
        reg_flags = registry[module_id]
        reg_refs = {flag_to_ref[f] for f in reg_flags if f in flag_to_ref}

        if declared != reg_refs:
            stops.append(
                f"{module_id}: manual declares {sorted(declared)}, registry implies "
                f"{sorted(reg_refs)}; prose rules out {sorted(ruled_out)}"
            )
            continue

        lines = []
        for ref in sorted(reg_refs):
            after = laws.split(ref, 1)[1] if ref in laws else ""
            gloss = after.split("\n")[0].strip().lstrip("`*-— ").strip()
            lines.append(f"{ref} ({lib[ref]}) - {gloss}")
        content["compliance_coupling"] = "\n\n".join(lines)

        ready.append(
            {"module_id": module_id, "version": version, "content": content,
             "flags": sorted(reg_flags)}
        )

    return ready, stops


async def api_version(conn: Any) -> str | None:
    """The Forge's registered API version, stamped on what this script authors."""
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT api_version FROM forge_registry WHERE forge_id = %s", (FORGE_ID,)
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="author them; otherwise emit only")
    args = ap.parse_args()

    async with connection() as conn:
        ready, stops = await derive(conn)
        version = await api_version(conn)
        if version is None:
            # THE FORGE IS NOT REGISTERED, so there is no API version to stamp. Authoring
            # with a blank one would record a claim about a Forge nobody bridged, which is
            # the shape entry 39 calls a third copy: a value invented at the point of
            # writing because the real one was missing.
            print(f"  {FORGE_ID} has no api_version in forge_registry - nothing authored")
            return 1

    print(f"\n{len(ready)} ready, {len(stops)} stopped\n")
    for r in ready:
        sizes = " ".join(f"{k}={len(v)}" for k, v in r["content"].items())
        print(f"  {r['module_id']:<30} v{r['version']:<5} {sizes}")
    for stop in stops:
        print(f"  STOP   {stop}")

    if not args.apply:
        print("\nNothing written. Re-run with --apply to author these.")
        return 1 if stops else 0
    if stops:
        print("\nRefusing to apply while any module is stopped.")
        return 1

    async with connection() as conn:
        actor = await humans.attributable_actor(conn)
        for r in ready:
            written = await instructions.author(
                conn,
                forge_id=FORGE_ID,
                module_id=r["module_id"],
                instruction_version=r["version"],
                forge_api_version=version,
                content=r["content"],
                authored_by=actor,
            )
            print(f"  authored {r['module_id']:<30} {written.content_hash[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
