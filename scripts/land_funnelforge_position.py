"""Land the held FunnelForge Pack edit in the one order that leaves V31 able to speak.

    .venv/Scripts/python scripts/land_funnelforge_position.py            # check only
    .venv/Scripts/python scripts/land_funnelforge_position.py --confirm  # land it

THE RULE THIS SCRIPT IS, RATHER THAN DESCRIBES
==============================================

B33 states it and P-13 measured it: *the registry rows land before or with the position,
never after, or V31 goes mute.* That sentence has been true and unenforced since
2026-09-09.

**READS A PLAN DOCUMENT, NOT A PATCH, SINCE 14 SEPTEMBER 2026.**
`docs/plans/funnelforge-position-DEFERRED.patch` held the same two edits as a unified
diff and was retired: a diff matches three lines of context and goes stale silently
whenever the Pack shifts near them, which is the expiry problem the deferral itself
demonstrated. `docs/plans/funnelforge-position-PLAN.md` carries the two edits as YAML
blocks, each naming the single Pack line it is inserted above. An anchor that has moved
or duplicated stops this script with a message; three lines of context that have moved
produce a subtly misplaced edit or an unexplained refusal.

**"Before" is not actually available, and that is why the rule kept being restated
instead of enforced.** `scripts/register_funnelforge_modules.py` reads the Pack's
`modules_expected` for the human half of each row, and while the edit is held the Pack
declares no `funnelforge` binding at all - so the script prints *"declares no funnelforge
binding. Nothing to register"* and exits 1. The rows cannot precede the patch. Only
"with" is reachable, and "with" is not something a person can do with two commands.

So this script does it as one, by splitting the plan into the two blocks it has
always contained and putting the registration between them:

    1. the `forge_dependencies` block   the binding. Nine `modules_expected`, which is
                                        the half `register_funnelforge_modules.py` needs
                                        in order to write anything. **V31 does not read
                                        this block** - it iterates positions - so the
                                        Pack at this point cannot make V31 mute.

    2. the rows                          `register_funnelforge_modules.py --confirm`,
                                        derived from the adapter's dispatch map
                                        intersected with the binding just landed.

    3. the `positions_required` block    the Marketing Operations Coordinator at
                                        `auto_execute`. This is the block V31 reads, and
                                        it lands only once step 2 has put something in
                                        `forge_module_registry` for it to be read
                                        against.

    4. the read-back                     V31 is re-run. **If it comes back NOT_RUN, both
                                        blocks are reverted and this exits non-zero**,
                                        because NOT_RUN after step 3 means the ordering
                                        failed in some way this script did not predict,
                                        and the state it would leave behind is the exact
                                        one B33 forbids.

Step 4 is the part that is enforcement rather than sequence. Steps 1-3 are the right
order; step 4 checks the property the order exists to produce, so a future change that
breaks the order some other way is still caught.

BETWEEN STEP 1 AND STEP 3 THE PACK IS BRIEFLY WRONG, AND DELIBERATELY THE RIGHT WRONG
=====================================================================================

With the binding landed and no rows yet, V6 FAILs: nine modules are declared and not in
`forge_module_registry`. That is a bookkeeping absence, it names itself accurately, and
step 2 closes it seconds later. The alternative window - position first - produces V31
NOT_RUN, which names a *missing measurement* where the truth is a *refused declaration*.
Both windows show "Gate 2 blocked"; only one of them tells you which kind of problem you
have. On any failure every block applied is reverted, so the window does not outlive the
command.

WHAT IT WRITES, AND WHY THAT FILE EXISTS
========================================

`docs/plans/funnelforge-landing-receipt.json`, recording the nine rows as they stood when
the position landed, with their `verification_method`, plus V31's verdict at that moment.

It is not a log. `tests/validator/test_funnelforge_landing_order.py` fails if the Pack
carries the position and this receipt does not account for every module the position
operates - so a person who bypasses this script, applies the plan by hand and
commits it, gets a red build naming the rule. **That is the half of the enforcement git
can see.** The database half is steps 1-4 above; the repository half is the receipt.

WHAT IT WILL NOT DO
===================

It will not land the position while V31 would refuse it *for a reason of substance*, and
it does not try to. A V31 FAIL after step 3 is reported and the blocks are KEPT: a refusal
naming seven `at_most_once` sends under an unattended tier is the finding P-13 built this
binding to produce, and reverting it would be hiding the answer. Whether that Pack state
is one anybody should commit is a decision for a human, and this script says so rather
than deciding it. The revert in step 4 is for NOT_RUN only - silence, not refusal.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import broker  # noqa: E402, F401  - imported for its event-loop policy side effect
from broker.db import connection  # noqa: E402
from generators.pack import load_pack  # noqa: E402
from generators.validator import validate  # noqa: E402

FORGE_ID = "funnelforge"
PACK_PATH = ROOT / "packs" / "burkham-wickmont.draft.yaml"
PLAN_PATH = ROOT / "docs" / "plans" / "funnelforge-position-PLAN.md"
RECEIPT_PATH = ROOT / "docs" / "plans" / "funnelforge-landing-receipt.json"
REGISTER = ROOT / "scripts" / "register_funnelforge_modules.py"

#: The two blocks, told apart by content rather than by order in the document. Picking
#: them by position would swap them the first time somebody reorders the plan.
BINDING_MARKER = f"- forge: {FORGE_ID}"
POSITION_MARKER = "position_title: Marketing Operations Coordinator"

#: Each block names the Pack line it is inserted ABOVE. An anchor is one whole line, and
#: the script refuses unless it appears exactly once - which is a stronger guarantee than
#: a diff's three lines of context, and the reason this replaced a `.patch`. Context goes
#: stale silently whenever the Pack changes nearby; a missing or duplicated anchor stops.
ANCHORS = {
    BINDING_MARKER: "  external_software:",
    POSITION_MARKER: "capacity_demand:",
}

#: ```yaml fences in the plan, in document order.
_BLOCK = re.compile(r"^```yaml$(.*?)^```", re.M | re.S)


class LandingError(RuntimeError):
    """Something is not true that has to be true. The message is for a person."""


# ------------------------------------------------------------------ plan reading


def split_hunks(plan_text: str) -> tuple[str, str]:
    """(binding block, position block), each a chunk of Pack YAML ready to insert.

    Named `split_hunks` still because it answers the same question the patch splitter
    did - which of the two edits is which - and `tests/validator/
    test_funnelforge_landing_order.py` asserts the split is faithful without needing a
    repository or a database. Pure, for the same reason.
    """
    blocks = [m.group(1) for m in _BLOCK.finditer(plan_text)]

    def select(marker: str) -> str:
        chosen = [b for b in blocks if marker in b]
        if len(chosen) != 1:
            raise LandingError(
                f"expected exactly one ```yaml block containing {marker!r} in "
                f"{PLAN_PATH.name}, found {len(chosen)}. The plan has been edited into a "
                "shape this reader cannot parse; land the two edits by hand in the order "
                "B39 states, or fix the reader - do not apply both at once to get past "
                "this."
            )
        return chosen[0]

    return select(BINDING_MARKER), select(POSITION_MARKER)


def _apply(block: str, *, reverse: bool = False) -> None:
    """Insert `block` above its anchor in the Pack, or remove it again.

    Text insertion at a named anchor rather than `git apply`, and that is the whole
    change: a diff matches three lines of context and fails - or worse, applies at the
    wrong offset - whenever the Pack shifts near them. An anchor is one line, required to
    appear exactly once, and a Pack that no longer contains it stops the script with a
    message rather than producing a subtly wrong Pack.
    """
    marker = BINDING_MARKER if BINDING_MARKER in block else POSITION_MARKER
    anchor = ANCHORS[marker]
    text = PACK_PATH.read_text(encoding="utf-8")

    if reverse:
        if block not in text:
            raise LandingError(
                f"cannot revert the {marker!r} block: it is not in the Pack as written. "
                "Something edited it between applying and reverting, so removing it "
                "automatically would guess at what to take out. Revert the Pack by hand."
            )
        PACK_PATH.write_text(text.replace(block, "", 1), encoding="utf-8")
        return

    if block in text:
        raise LandingError(
            f"the {marker!r} block is already in the Pack. Landing it twice would "
            "declare it twice; if a previous run half-completed, revert it by hand "
            "first so the state this script starts from is the one it reports."
        )
    hits = [ln for ln in text.splitlines() if ln == anchor]
    if len(hits) != 1:
        raise LandingError(
            f"anchor {anchor!r} appears {len(hits)} times in {PACK_PATH.name}; it must "
            "appear exactly once. The Pack's shape moved - update the anchor in "
            f"{PLAN_PATH.name} deliberately rather than making this script guess."
        )
    spaced = block.rstrip() + "\n\n" + anchor
    PACK_PATH.write_text(text.replace(anchor, spaced, 1), encoding="utf-8")


# ---------------------------------------------------------------------- the checks


def _pack_carries_position() -> bool:
    return any(
        p.position_title == "Marketing Operations Coordinator"
        for p in load_pack(PACK_PATH).positions_required
    )


async def _forge_is_registered(conn) -> str | None:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT base_url FROM forge_registry WHERE forge_id = %s", (FORGE_ID,)
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def _rows(conn) -> dict[str, str]:
    """module_id -> verification_method, for whatever is registered right now."""
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT module_id, verification_method FROM forge_module_registry "
            "WHERE forge_id = %s",
            (FORGE_ID,),
        )
        return {module_id: method for module_id, method in await cur.fetchall()}


async def _v31(conn):
    report = await validate(load_pack(PACK_PATH), conn)
    return report.get("V31")


# ------------------------------------------------------------------------- the run


async def run(confirm: bool) -> int:
    if not PLAN_PATH.exists():
        print(f"{PLAN_PATH.name} is gone. Nothing to land.")
        return 1

    if _pack_carries_position():
        print(
            "The Pack already carries the Marketing Operations Coordinator. This script "
            "lands it once; it is not an updater. If the landing was done by hand, the "
            "receipt this script writes is missing and "
            "tests/validator/test_funnelforge_landing_order.py will say so."
        )
        return 1

    binding_patch, position_patch = split_hunks(
        PLAN_PATH.read_text(encoding="utf-8")
    )

    async with connection() as conn:
        base_url = await _forge_is_registered(conn)
        if base_url is None:
            print(
                f"BLOCKED: {FORGE_ID} is not in forge_registry, and "
                "forge_module_registry.forge_id references it. No row can be written, "
                "so the rows cannot land with the patch, so the patch cannot land.\n\n"
                "This is not a step to work around. There is no base_url to register "
                "because the FunnelForge containers publish no host ports and the "
                "adapter is not deployed - see docs/plans/funnelforge-binding-RECORD.md. "
                "Deploy it, register the Forge, then run this again."
            )
            return 1
        print(f"forge_registry: {FORGE_ID} -> {base_url}")

    if not confirm:
        print(
            "\nNothing applied and nothing written. Re-run with --confirm to land the "
            "binding, register the rows, and land the position - in that order, as one "
            "command, which is the only order in which V31 can speak."
        )
        return 0

    applied: list[str] = []
    try:
        # 1. the binding. Two things, and the second is why this is step 1 rather than
        #    step 3. V31 examines only modules named by a position at `auto_execute`, and no
        #    FunnelForge position is declared yet - so nothing here can mute it. AND V31 scopes
        #    its `forge_module_registry` query to the Forges named in `forge_dependencies`
        #    (validator.py:1150-1152), so until this hunk lands, rows written by step 2 are not
        #    queried and the rule reports NOT_RUN with all nine rows present.
        _apply(binding_patch)
        applied.append("binding")
        print("applied: the funnelforge binding (forge_dependencies)")

        # 2. the rows, which need step 1 to have happened to have a declared half.
        proc = subprocess.run(
            [sys.executable, str(REGISTER), "--confirm"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        print(proc.stdout.rstrip())
        if proc.returncode != 0:
            raise LandingError(
                f"{REGISTER.name} exited {proc.returncode}: {proc.stderr.strip()}"
            )

        async with connection() as conn:
            rows = await _rows(conn)
        declared = set(
            next(
                b.modules_expected
                for b in load_pack(PACK_PATH).forge_dependencies.forge_bindings
                if b.forge == FORGE_ID
            )
        )
        missing = sorted(declared - set(rows))
        hand = sorted(m for m in declared & set(rows) if rows[m] == "hand")
        if missing or hand:
            raise LandingError(
                "the rows did not land as evidence. "
                + (f"no row: {', '.join(missing)}. " if missing else "")
                + (f"hand-written, which V31 will not pass on: {', '.join(hand)}. " if hand else "")
                + "The position is not being applied on top of that."
            )
        print(f"registered: {len(declared)} row(s), all adapter-verified")

        # 3. the position. Only now is there anything for V31 to read it against.
        _apply(position_patch)
        applied.append("position")
        print("applied: the Marketing Operations Coordinator (positions_required)")

        # 4. the read-back. This is the enforcement; the order above is only the method.
        async with connection() as conn:
            v31 = await _v31(conn)
            rows_now = await _rows(conn)
        print(f"\nV31 {v31.verdict.value}: {v31.message}")

        if v31.verdict.value == "NOT_RUN":
            raise LandingError(
                "V31 is NOT_RUN with the position landed. That is the mute state B33 "
                "forbids - the rule that governs this position measured nothing and the "
                "Pack records no answer about it. Reverting both hunks."
            )

        RECEIPT_PATH.write_text(
            json.dumps(
                {
                    "landed_at": datetime.now(UTC).isoformat(),
                    "landed_by": "scripts/land_funnelforge_position.py",
                    "forge_id": FORGE_ID,
                    "base_url": base_url,
                    "order": [
                        "forge_dependencies hunk",
                        "scripts/register_funnelforge_modules.py --confirm",
                        "positions_required hunk",
                        "V31 read-back",
                    ],
                    "modules": {m: rows_now[m] for m in sorted(declared)},
                    "v31_at_landing": {
                        "verdict": v31.verdict.value,
                        "message": v31.message,
                    },
                    "note": (
                        "A V31 FAIL here is the honest verdict, not a landing error. "
                        "See B39 and docs/plans/funnelforge-binding-RECORD.md."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"receipt: {RECEIPT_PATH.relative_to(ROOT).as_posix()}")

        if v31.verdict.value == "FAIL":
            print(
                "\nLANDED, AND V31 REFUSES IT. Both hunks are kept and the refusal is "
                "recorded, because a refusal is an answer. Burkham's Gate 2 is now "
                "blocked on V31 and that is what it is supposed to say. Do not soften "
                "the declaration or the rule to clear it; what clears it is an "
                "idempotency key on FunnelForge's send path."
            )
        return 0

    except LandingError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        for name, patch_text in reversed(
            [("binding", binding_patch), ("position", position_patch)]
        ):
            if name in applied:
                _apply(patch_text, reverse=True)
                print(f"reverted: {name}", file=sys.stderr)
        RECEIPT_PATH.unlink(missing_ok=True)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="land it; without this the preconditions are reported and nothing changes",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.confirm))


if __name__ == "__main__":
    raise SystemExit(main())
