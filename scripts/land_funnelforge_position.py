"""Land the held FunnelForge Pack edit in the one order that leaves V31 able to speak.

    .venv/Scripts/python scripts/land_funnelforge_position.py            # check only
    .venv/Scripts/python scripts/land_funnelforge_position.py --confirm  # land it

THE RULE THIS SCRIPT IS, RATHER THAN DESCRIBES
==============================================

B33 states it and P-13 measured it: *the registry rows land before or with the patch,
never after, or V31 goes mute.* That sentence has been true and unenforced since
2026-09-09. `docs/plans/funnelforge-position-DEFERRED.patch` is a file anyone can
`git apply`, and doing so is the obvious thing to do; nothing between the patch and the
Pack knows about the rule.

**"Before" is not actually available, and that is why the rule kept being restated
instead of enforced.** `scripts/register_funnelforge_modules.py` reads the Pack's
`modules_expected` for the human half of each row, and while the edit is held the Pack
declares no `funnelforge` binding at all - so the script prints *"declares no funnelforge
binding. Nothing to register"* and exits 1. The rows cannot precede the patch. Only
"with" is reachable, and "with" is not something a person can do with two commands.

So this script does it as one, by splitting the held patch into the two hunks it has
always contained and putting the registration between them:

    1. the `forge_dependencies` hunk    the binding. Nine `modules_expected`, which is
                                        the half `register_funnelforge_modules.py` needs
                                        in order to write anything. **V31 does not read
                                        this block** - it iterates positions - so the
                                        Pack at this point cannot make V31 mute.

    2. the rows                          `register_funnelforge_modules.py --confirm`,
                                        derived from the adapter's dispatch map
                                        intersected with the binding just landed.

    3. the `positions_required` hunk     the Marketing Operations Coordinator at
                                        `auto_execute`. This is the block V31 reads, and
                                        it lands only once step 2 has put something in
                                        `forge_module_registry` for it to be read
                                        against.

    4. the read-back                     V31 is re-run. **If it comes back NOT_RUN, both
                                        hunks are reverted and this exits non-zero**,
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
have. On any failure every hunk applied is reverted, so the window does not outlive the
command.

WHAT IT WRITES, AND WHY THAT FILE EXISTS
========================================

`docs/plans/funnelforge-landing-receipt.json`, recording the nine rows as they stood when
the position landed, with their `verification_method`, plus V31's verdict at that moment.

It is not a log. `tests/validator/test_funnelforge_landing_order.py` fails if the Pack
carries the position and this receipt does not account for every module the position
operates - so a person who bypasses this script, `git apply`s the patch by hand and
commits it, gets a red build naming the rule. **That is the half of the enforcement git
can see.** The database half is steps 1-4 above; the repository half is the receipt.

WHAT IT WILL NOT DO
===================

It will not land the position while V31 would refuse it *for a reason of substance*, and
it does not try to. A V31 FAIL after step 3 is reported and the hunks are KEPT: a refusal
naming seven `at_most_once` sends under an unattended tier is the finding P-13 built this
binding to produce, and reverting it would be hiding the answer. Whether that Pack state
is one anybody should commit is a decision for a human, and this script says so rather
than deciding it. The revert in step 4 is for NOT_RUN only - silence, not refusal.
"""

from __future__ import annotations

import argparse
import asyncio
import json
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
PATCH_PATH = ROOT / "docs" / "plans" / "funnelforge-position-DEFERRED.patch"
RECEIPT_PATH = ROOT / "docs" / "plans" / "funnelforge-landing-receipt.json"
REGISTER = ROOT / "scripts" / "register_funnelforge_modules.py"

#: The two hunks, told apart by content rather than by position in the file. A hunk
#: header's line numbers move whenever the Pack above them changes; the text a hunk adds
#: does not, and picking hunks by `@@` offsets would be a splitter that silently swapped
#: the two the first time somebody inserted a position earlier in the Pack.
BINDING_MARKER = f"- forge: {FORGE_ID}"
POSITION_MARKER = "position_title: Marketing Operations Coordinator"


class LandingError(RuntimeError):
    """Something is not true that has to be true. The message is for a person."""


# ------------------------------------------------------------------ patch splitting


def split_hunks(patch_text: str) -> tuple[str, str]:
    """(binding-only patch, position-only patch), each a complete applicable patch.

    Pure, so `tests/validator/test_funnelforge_landing_order.py` can assert the split
    is faithful - every added line of the original appears in exactly one half - without
    a repository or a database.
    """
    lines = patch_text.splitlines()
    header: list[str] = []
    hunks: list[list[str]] = []
    for line in lines:
        if line.startswith("@@"):
            hunks.append([line])
        elif hunks:
            hunks[-1].append(line)
        else:
            header.append(line)

    def select(marker: str) -> str:
        chosen = [h for h in hunks if any(marker in ln for ln in h if ln.startswith("+"))]
        if len(chosen) != 1:
            raise LandingError(
                f"expected exactly one hunk adding {marker!r} in {PATCH_PATH.name}, "
                f"found {len(chosen)}. The patch has been edited into a shape this "
                "splitter cannot read; land it by hand in the order B39 states, or fix "
                "the splitter - do not apply the whole patch to get past this."
            )
        return "\n".join(header + chosen[0]) + "\n"

    return select(BINDING_MARKER), select(POSITION_MARKER)


def _apply(patch_text: str, *, reverse: bool = False) -> None:
    args = ["apply", "--verbose"] + (["-R"] if reverse else [])
    # Bytes, with text mode off. Python's text mode rewrites every line ending to CRLF
    # when writing to a pipe on Windows, and `git apply` compares context lines byte for
    # byte - so a text write would hand it a CRLF patch and it would refuse the whole
    # thing with "patch does not apply". That is the same failure `.gitattributes` now
    # pins `*.patch text eol=lf` to prevent on checkout; this is the other end of it.
    proc = subprocess.run(
        ["git", *args, "-"],
        cwd=ROOT,
        input=patch_text.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise LandingError(
            f"git apply{' -R' if reverse else ''} failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )


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
    if not PATCH_PATH.exists():
        print(f"{PATCH_PATH.name} is gone. Nothing to land.")
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
        PATCH_PATH.read_text(encoding="utf-8")
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
