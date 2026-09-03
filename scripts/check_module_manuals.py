"""Every bound module has an operating instruction. The manuals are the to-do list.

    .venv/Scripts/python scripts/check_module_manuals.py               # every Forge
    .venv/Scripts/python scripts/check_module_manuals.py capitalforge  # one

Two mismatches, and only one of them is a failure. That asymmetry is the whole
design, so it is stated before anything else.

    BOUND WITHOUT A MANUAL          -> FAIL
        The Forge dispatches a module nobody has written down. An agent granted it has
        no instruction to be certified against, and Unit A certification is earned
        against an instruction's content hash - so the grant is either unissuable or
        was issued against nothing.

    A MANUAL WITHOUT A MODULE       -> TODO, reported and not failed
        An instruction exists for something the adapter does not dispatch yet. That is
        a description of work outstanding, not a defect in the Forge.

WHY THE SECOND ONE IS NOT A FAILURE
===================================

    Because of what happens if it is. A failing check pushes whoever hits it towards
    the cheapest way to make it pass, and the cheapest way is to register the name -
    a module id, a registry row, a manifest entry, all resolving, with nothing behind
    them.

    That is `lender_match`. The Burkham Pack declares it at criticality:hard and a
    role's `forge_modules_operated` names it, and CapitalForge has no lender matching
    - it matches to card issuers. A Pack, a role and a registry row all agreeing about
    a capability that does not exist, because each one was made consistent with the
    last.

    `_modules` reports what the adapter dispatches. Nothing may enter it to satisfy a
    check. So a manual with no module is information: the manual set is the to-do list
    for the adapter, and this prints how much of it is done.

    THIS ALREADY HAPPENED HERE. Two evidence manuals were reported unbound and both
    were then bound - correctly, as it turned out, because both had real endpoints
    behind them. But the check was what applied the pressure, and it would have applied
    exactly the same pressure to a name with nothing behind it. Exercising all sixteen
    operations against a running server is what established the difference, and this
    check cannot do that.

WHY IT ASKS THE FORGE RATHER THAN THE REGISTRY
==============================================

    The same reason `verify_forge_modules.py` does. `forge_module_registry` is rows a
    human wrote; an adapter's `_modules` is derived from its dispatch map, so a name is
    in the answer if and only if a handler is bound to it. Checking manuals against the
    registry would compare two documents.

    It is a real conformance check for the same reason and with the same limit: it
    proves a manual exists for a bound name. It does not read the manual and it does
    not call the module, so it cannot tell you the manual is accurate, that the handler
    works, or that it does what the name says. A manual describing thirteen endpoints
    for a module that now has six passes this.

WHAT `manual` IN THE MANIFEST IS, AND IS NOT
============================================

    An adapter may state a `manual` per module. That is a declaration - the adapter's
    word - and this checks it rather than trusting it: the named file must exist and
    must declare that module id in its own header. A manual named by the manifest that
    does not exist IS a failure, because that is the adapter making a false statement
    about itself.

    Where an adapter states no manual, the check falls back to matching on the module
    id declared inside each manual. Weaker, and still catches the failing direction.

NOT_RUN IS NOT A PASS
=====================

    A Forge that cannot be reached, or that serves no manifest, is reported NOT_RUN and
    does not affect the exit code unless it is the only Forge asked. There is nothing to
    compare a manual against, and calling that a pass would make an unreachable Forge
    the easiest way to satisfy this check.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from broker import forge_modules  # noqa: E402
from broker.db import connection  # noqa: E402

INSTRUCTIONS = ROOT / "docs" / "instructions"

#: `**Forge:** CapitalForge` and `**Module:** `client_read``, in either order and on
#: either one line or two - the manuals use both layouts.
FORGE_LINE = re.compile(r"\*\*Forge:\*\*\s*([^*\n]+?)(?:\s{2,}|\n|\*\*)")
MODULE_LINE = re.compile(r"\*\*Module:\*\*\s*`([a-z0-9_]+)`")

#: Not a module manual. Shared rules govern many modules and name none.
SHARED = {"foi-shared-rules.md"}


def _forge_slug(name: str) -> str:
    """`CapitalForge` -> `capitalforge`. Matches how forge_registry spells ids."""
    return name.strip().lower().replace(" ", "-")


def manuals_on_disk() -> dict[str, dict[str, str]]:
    """forge_id -> {module_id: filename}, read from the manual headers."""
    found: dict[str, dict[str, str]] = {}
    for path in sorted(INSTRUCTIONS.glob("*.md")):
        if path.name in SHARED:
            continue
        text = path.read_text(encoding="utf-8")
        forge = FORGE_LINE.search(text)
        module = MODULE_LINE.search(text)
        if forge is None or module is None:
            print(
                f"  ! {path.name} declares no Forge and Module header pair; skipped. "
                "A manual that does not say what it is about cannot be checked."
            )
            continue
        found.setdefault(_forge_slug(forge.group(1)), {})[module.group(1)] = path.name
    return found


async def run(only: str | None) -> int:
    on_disk = manuals_on_disk()
    exit_code = 0
    asked = 0

    async with connection() as conn:
        forge_ids = sorted(on_disk) if only is None else [only.lower()]

        for forge_id in forge_ids:
            answer = await forge_modules.read(conn, forge_id, force=True)

            if isinstance(answer, forge_modules.Unread):
                print(f"{forge_id}: NOT_RUN - {answer.reason}")
                continue

            asked += 1
            bound = set(answer.modules)
            declared = on_disk.get(forge_id, {})

            print(f"{forge_id}: {len(bound)} bound, {len(declared)} manual(s)")
            print(f"  scope: {forge_modules.SCOPE}")

            # The adapter's own claim about which manual describes which module,
            # checked rather than trusted.
            claimed = _claimed_manuals(answer)
            for module_id, filename in sorted(claimed.items()):
                path = INSTRUCTIONS / filename
                if not path.exists():
                    print(
                        f"  FAIL {module_id}: manifest names {filename}, which does "
                        "not exist in docs/instructions/"
                    )
                    exit_code = 1
                    continue
                declares = declared.get(module_id)
                if declares != filename:
                    owner = next((m for m, f in declared.items() if f == filename), "nothing")
                    print(
                        f"  FAIL {module_id}: manifest names {filename}, but that file "
                        f"declares itself the manual for {owner}"
                    )
                    exit_code = 1

            for module_id in sorted(bound - set(declared)):
                print(
                    f"  FAIL {module_id}: bound, no operating instruction. Unit A "
                    "certification is earned against an instruction's content hash, so "
                    "a grant for this is issued against nothing."
                )
                exit_code = 1

            # Reported, never failed. See the module docstring: a failure here
            # would be satisfied by registering the name, and a name registered to
            # satisfy a check is what lender_match is.
            outstanding = sorted(set(declared) - bound)
            for module_id in outstanding:
                print(
                    f"  TODO {module_id}: {declared[module_id]} describes it, "
                    f"{forge_id} does not dispatch it yet. Not a failure - do not "
                    "register the name to clear this line."
                )

            if outstanding:
                done = len(bound & set(declared))
                print(
                    f"  {done} of {len(declared)} manual(s) bound. {len(outstanding)} outstanding."
                )

            if not exit_code and not outstanding:
                print("  OK  every bound module has a manual, and every manual is bound")
            elif not exit_code:
                print("  OK  every bound module has a manual")

    if asked == 0:
        print("NOT_RUN: no Forge could be asked. This proves nothing.")
        return 1
    return exit_code


def _claimed_manuals(answer: forge_modules.ForgeModules) -> dict[str, str]:
    """What the adapter says describes each module, where it says anything.

    Read from `ForgeModules.entries`, which is the manifest verbatim. Kept out of
    `DispatchShape`: a manual reference is this check's business and not something
    `forge_module_registry` has a column for.

    An adapter that states no manual returns nothing here, and the caller falls
    back to matching on the module id each manual declares. Weaker, and still
    catches both mismatch directions.
    """
    if answer.entries is None:
        return {}
    claims: dict[str, str] = {}
    for entry in answer.entries:
        module_id = entry.get("module_id")
        manual = entry.get("manual")
        if isinstance(module_id, str) and isinstance(manual, str) and manual:
            claims[module_id] = manual
    return claims


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("forge_id", nargs="?", help="only this Forge")
    args = parser.parse_args()
    return asyncio.run(run(args.forge_id))


if __name__ == "__main__":
    raise SystemExit(main())
