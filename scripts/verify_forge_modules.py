"""Ask each Forge what it dispatches, and record the answer against the registry.

    .venv/Scripts/python scripts/verify_forge_modules.py                 # every Forge
    .venv/Scripts/python scripts/verify_forge_modules.py cre-forge       # one
    .venv/Scripts/python scripts/verify_forge_modules.py --check         # report only

`--check` writes nothing and exits 1 on drift: a registry row for a module the Forge
does not dispatch, or a module it dispatches that The Office has no row for. That is
the CI form. A registry verified once and never again is a claim with a date on it.

WHAT A VERIFICATION MEANS
=========================

    A handler is bound to that name. Not that the handler works, and not that it does
    what the name says. This automates the half of the conformance question that was
    being done by hand and does not touch the other half — `readiness_score` is bound,
    answers 200, mutates nothing, and scores a business from query parameters it never
    reads. That class is found by reading the source and recorded in
    `forge_module_exclusion`. Nothing here will ever find it.

WHAT IT DOES NOT DO
===================

    **It never deletes a row.** A module that has stopped resolving is reported, not
    removed: `agent_forge_grant` has a foreign key into this table, and quietly
    deleting the row a live grant points at is not a thing a verifier should do as a
    side effect of a Forge deploy. Somebody revokes the grant, deliberately.

    **It never writes `hand`.** That is the default a human's row already carries.

    **It never invents a row.** A module the Forge dispatches and the registry has
    never heard of is reported so somebody can decide whether The Office should know
    about it. Writing it here would let a Forge enlarge its own agent-facing surface.

Runs as `office_app`, which holds UPDATE on this table. Unlike recording an exclusion
— a deliberate human act, admin-only by design — a verification is an observation a
machine made, and requiring an admin credential to record one would mean it happens
rarely, which is the opposite of what a dated claim needs.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from psycopg import AsyncConnection  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from broker import forge_modules  # noqa: E402
from broker.db import connection  # noqa: E402


async def _registered(conn: AsyncConnection) -> dict[str, set[str]]:
    """forge_id -> the module ids The Office has rows for."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT lower(forge_id) AS forge_id, module_id FROM forge_module_registry"
        )
        out: dict[str, set[str]] = {}
        for row in await cur.fetchall():
            out.setdefault(row["forge_id"], set()).add(row["module_id"])
        return out


async def _record(
    conn: AsyncConnection,
    forge_id: str,
    modules: set[str],
    answer: forge_modules.ForgeModules,
) -> int:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE forge_module_registry
               SET verified_at = now(),
                   verified_against = %s,
                   verification_method = %s
             WHERE lower(forge_id) = %s AND module_id = ANY(%s)
            """,
            (answer.provenance, answer.method, forge_id, sorted(modules)),
        )
        return int(cur.rowcount)


async def _corrections(
    conn: AsyncConnection, forge_id: str, modules: set[str],
    answer: forge_modules.ForgeModules,
) -> list[str]:
    """Rows whose shape disagrees with the Forge's, corrected to the Forge's.

    The registry is not consulted for the answer. `property_lookup` was recorded
    `is_mutating: TRUE` by hand and it is a search - a hand-written row got the
    checkable half wrong on the only module anybody had ever called, and V31
    decides whether an unattended agent may hold a module on exactly that field.

    Where the adapter does not state a shape - an older manifest, or a probe -
    nothing is written. An unanswered question is not a correction.
    """
    if answer.shapes is None:
        return []

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT module_id, is_mutating, idempotency_support
            FROM forge_module_registry
            WHERE lower(forge_id) = %s AND module_id = ANY(%s)
            """,
            (forge_id, sorted(modules)),
        )
        rows = await cur.fetchall()

    changed: list[str] = []
    for row in rows:
        shape = answer.shapes.get(row["module_id"])
        if shape is None:
            continue
        if (
            row["is_mutating"] == shape.is_mutating
            and row["idempotency_support"] == shape.idempotency_support
        ):
            continue
        changed.append(
            f"{forge_id}/{row['module_id']}: is_mutating "
            f"{row['is_mutating']} -> {shape.is_mutating}, idempotency_support "
            f"{row['idempotency_support']!r} -> {shape.idempotency_support!r}"
        )
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE forge_module_registry
                   SET is_mutating = %s, idempotency_support = %s
                 WHERE lower(forge_id) = %s AND module_id = %s
                """,
                (
                    shape.is_mutating, shape.idempotency_support,
                    forge_id, row["module_id"],
                ),
            )
    return changed


async def run(only: str | None, check: bool) -> int:
    drift = False
    async with connection() as conn:
        registered = await _registered(conn)
        if only:
            registered = {k: v for k, v in registered.items() if k == only.lower()}
            if not registered:
                print(f"{only}: no rows in forge_module_registry")
                return 1

        for forge_id, rows in sorted(registered.items()):
            answer = await forge_modules.read(
                conn, forge_id, candidates=rows, force=True
            )
            if isinstance(answer, forge_modules.Unread):
                # Not drift. Nothing was learned, which is a different thing from
                # learning that something is wrong, and it must not exit 1 on its own.
                print(f"{forge_id}: NOT_RUN - {answer.reason}")
                continue

            absent = sorted(rows - answer.modules)
            unknown = sorted(answer.modules - rows)
            confirmed = rows & answer.modules

            if confirmed and not check:
                touched = await _record(conn, forge_id, confirmed, answer)
                corrected = await _corrections(conn, forge_id, confirmed, answer)
                await conn.commit()
                print(f"{forge_id}: {touched} row(s) verified via {answer.method}")
                for line in corrected:
                    print(f"  CORRECTED {line}")
            else:
                print(f"{forge_id}: {len(confirmed)} row(s) resolve via {answer.method}")
                if answer.shapes is None:
                    print(
                        f"  {forge_id} states no module shapes, so is_mutating and "
                        "idempotency_support stay as written and unverified"
                    )

            for module_id in absent:
                drift = True
                print(
                    f"  DRIFT {forge_id}/{module_id}: a registry row for a module the "
                    "Forge does not dispatch. Any grant over it is a grant on a "
                    "capability that is not there. Not deleted - revoke the grant first."
                )
            for module_id in unknown:
                drift = True
                print(
                    f"  DRIFT {forge_id}/{module_id}: dispatched by the Forge and "
                    "unknown to the registry. Not added - a Forge does not enlarge its "
                    "own agent-facing surface."
                )

    print(f"\n{forge_modules.SCOPE}.")
    return 1 if (check and drift) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("forge_id", nargs="?", help="only this Forge")
    parser.add_argument(
        "--check", action="store_true", help="report only; exit 1 on drift"
    )
    args = parser.parse_args()
    return asyncio.run(run(args.forge_id, args.check))


if __name__ == "__main__":
    raise SystemExit(main())
