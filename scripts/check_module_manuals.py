"""Every bound module has an operating instruction, and every instruction a module.

    .venv/Scripts/python scripts/check_module_manuals.py               # every Forge
    .venv/Scripts/python scripts/check_module_manuals.py capitalforge  # one

Exits 1 on a mismatch. Two kinds, and they mean opposite things:

    BOUND WITHOUT A MANUAL
        A Forge dispatches a module nobody has written down. An agent granted it has
        no instruction to be certified against, and Unit A certification is earned
        against an instruction's content hash - so the grant is either unissuable or
        was issued against nothing.

    A MANUAL WITHOUT A MODULE
        An instruction describes something the Forge does not dispatch. Either the
        module was never built, or it was renamed and the manual still names the old
        spelling. Both produce the same failure at the far end: V11 resolves the
        modules a Pack's curriculum teaches against the manifest, and a manual for a
        name that does not resolve teaches an agent to call something that is not
        there.

WHY IT ASKS THE FORGE RATHER THAN THE REGISTRY
==============================================

    The same reason `verify_forge_modules.py` does. `forge_module_registry` is rows a
    human wrote; an adapter's `_modules` is derived from its dispatch map, so a name is
    in the answer if and only if a handler is bound to it. Checking manuals against the
    registry would compare two documents.

    It is a real conformance check for the same reason and with the same limit: it
    proves a manual exists for a bound name. It does not read the manual, so it cannot
    tell you the manual is accurate, current, or about the right endpoints. A manual
    that describes thirteen endpoints for a module that now has six passes this.

WHAT `manual` IN THE MANIFEST IS, AND IS NOT
============================================

    An adapter may state a `manual` per module. That is a declaration - the adapter's
    word - and this checks it rather than trusting it: the named file must exist and
    must declare that module id in its own header.

    Where an adapter states no manual, the check falls back to matching on the module
    id declared inside each manual. That is weaker (a manual could name a module id it
    is not really about) but it is the only thing available, and it still catches both
    mismatch directions.

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

            for module_id in sorted(set(declared) - bound):
                print(
                    f"  FAIL {module_id}: {declared[module_id]} describes it, "
                    f"{forge_id} does not dispatch it. Either it was never built or "
                    "the manual names a spelling the adapter no longer uses."
                )
                exit_code = 1

            if bound == set(declared) and not exit_code:
                print("  OK  every bound module has a manual and every manual a module")

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
