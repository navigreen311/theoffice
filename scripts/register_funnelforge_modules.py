"""Write FunnelForge's `forge_module_registry` rows from the adapter, never by hand.

    .venv/Scripts/python scripts/register_funnelforge_modules.py            # report only
    .venv/Scripts/python scripts/register_funnelforge_modules.py --confirm  # write

WHAT IT READS, AND WHY IT IS TWO THINGS
=======================================

    the adapter's dispatch map     spelling and shape. DERIVED - a name is there if and
                                   only if a handler is bound. Read from the module
                                   directly rather than over HTTP, because the adapter
                                   is in this repository; where it is deployed inside a
                                   Forge, read `GET {base_url}/_modules` instead and the
                                   generator takes the same dict either way.

    the Pack's modules_expected    a human's decision that The Office intends to make
                                   these grantable. DECLARED.

A row is written only where both agree. The two disagreements are printed and produce
nothing: a Forge does not enlarge its own agent-facing surface, and a Pack does not
conjure a capability by naming it.

WHAT THIS DOES NOT DO
=====================

It does not register the Forge. `forge_module_registry.forge_id` references
`forge_registry`, and a `base_url` is the thing FunnelForge does not currently have - the
containers publish no host ports and the adapter is not deployed. Running this before
that is done fails on the foreign key, which is the correct order of events rather than
an obstacle. See `docs/plans/funnelforge-binding-RECORD.md`.

It does not make anything callable. A row makes a module grantable; a grant plus a
manifest row plus Unit A and Unit B certifications at `auto_execute` make a call. Seven
of these nine are the shape V31 refuses at that tier, and that is in the record too.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.funnelforge.modules import manifest  # noqa: E402
from broker.db import connection  # noqa: E402
from generators import forge_module_rows  # noqa: E402
from generators.pack import load_pack  # noqa: E402
from generators.validator import validate  # noqa: E402

FORGE_ID = "funnelforge"
API_VERSION = "1.0.0"
PACK_PATH = ROOT / "packs" / "burkham-wickmont.draft.yaml"


async def run(confirm: bool) -> int:
    pack = load_pack(PACK_PATH)
    bindings = [
        b for b in pack.forge_dependencies.forge_bindings if b.forge == FORGE_ID
    ]
    if not bindings:
        print(f"{PACK_PATH.name} declares no {FORGE_ID} binding. Nothing to register.")
        return 1
    declared = set(bindings[0].modules_expected)

    generated = forge_module_rows.generate(FORGE_ID, API_VERSION, manifest(), declared)

    print(f"{FORGE_ID}@{API_VERSION}")
    print(f"  {len(generated.rows)} row(s) both the adapter and the Pack name")
    for row in generated.rows:
        print(
            f"    {row.module_id:<32} is_mutating={row.is_mutating!s:<5} "
            f"idempotency={row.idempotency_support}"
        )
    for module_id in generated.dispatched_not_declared:
        print(
            f"  DISPATCHED, NOT DECLARED {module_id}: no row. A Forge does not enlarge "
            "its own agent-facing surface; declare it in the Pack if it is wanted."
        )
    for module_id in generated.declared_not_dispatched:
        print(
            f"  DECLARED, NOT DISPATCHED {module_id}: no row. This is the lender_match "
            "shape - a Pack, a role and a registry row agreeing about a capability that "
            "is not there."
        )

    blocked = generated.blocked
    if blocked is not None:
        print(f"\nBLOCKED: {blocked}")
        return 1

    if not confirm:
        print(
            "\nNothing written. Re-run with --confirm to write these rows. They make "
            "the modules grantable; they do not make anything callable."
        )
        return 0

    async with connection() as conn:
        written = await forge_module_rows.apply(conn, generated, confirmed=True)
        await conn.commit()
        v31 = (await validate(pack, conn)).get("V31")
    print(f"\n{len(written)} row(s) written: {', '.join(written)}")
    print(
        "verification_method=adapter_manifest. That says a handler is bound to each "
        "name. It does not say the handler works, or that it does what the name says."
    )
    # Read V31 back here, where the rows just became readable. Writing rows is the
    # act that moves this rule off NOT_RUN, and the verdict it moves to is the whole
    # reason B33 says the rows land before or with the Pack edit and never after:
    # run in the wrong order, V31 was mute at the moment the declaration arrived and
    # this answer turned up later, attached to a registration step rather than to the
    # edit that caused it. Printing it here attaches it to the act that produced it.
    print(f"\nV31 is now {v31.verdict.value}: {v31.message}")
    if v31.verdict.value == "FAIL":
        print(
            "That refusal is the finding, not a regression. Do not soften the tier "
            "or the rule to clear it - see docs/blocking.md B38."
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm", action="store_true", help="write the rows; without it, report only"
    )
    args = parser.parse_args()
    return asyncio.run(run(args.confirm))


if __name__ == "__main__":
    raise SystemExit(main())
