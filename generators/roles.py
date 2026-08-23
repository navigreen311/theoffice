"""5.1 Role Definition Generator.

In: the Pack. Out: `positions_required` fully specified.

Master prompt 5.1: "The Office names the positions; it does not look them up." The
Pack author writes the titles — "Capital Underwriting Analyst", "Buyer Network
Manager" — because the Village roster does not natively contain them.

What this generator adds is the thing an author cannot be relied on to know:
**the compliance flags the modules themselves imply.**

`forge_module_registry.compliance_flags_implied` is set per module by whoever
registered the Forge. An author who omits `recording_consent_required` from a position
that operates `place_call` has not thereby escaped Nevada's two-party consent statute.
Declared flags and implied flags are kept as separate fields and unioned into an
effective set, so a reviewer can see which ones the author knew about — the gap between
the two lists is itself the finding.
"""

from __future__ import annotations

from psycopg import AsyncConnection

from generators.artifacts import DefinedPosition, RoleDefinition
from generators.pack import BusinessPack


async def generate(pack: BusinessPack, conn: AsyncConnection | None = None) -> RoleDefinition:
    implied_by_module: dict[str, list[str]] = {}
    known_modules: set[str] = set()

    if conn is not None:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT module_id, compliance_flags_implied FROM forge_module_registry"
            )
            for module_id, flags in await cur.fetchall():
                known_modules.add(module_id)
                implied_by_module[module_id] = sorted(flags or [])

    all_stages = _all_stages(pack)
    positions: list[DefinedPosition] = []
    unresolved: set[str] = set()

    for p in sorted(pack.positions_required, key=lambda x: x.position_title):
        declared = sorted(set(p.compliance_flags_in_scope))
        implied = sorted(
            {f for m in p.forge_modules_operated for f in implied_by_module.get(m, [])}
        )
        if conn is not None:
            unresolved |= {m for m in p.forge_modules_operated if m not in known_modules}

        stages = p.lifecycle_stages_owned or all_stages
        positions.append(
            DefinedPosition(
                position_title=p.position_title,
                reports_to=p.reports_to,
                duties=list(p.duties),
                forge_modules_operated=sorted(set(p.forge_modules_operated)),
                source_department=p.source_department,
                declared_compliance_flags=declared,
                implied_compliance_flags=implied,
                effective_compliance_flags=sorted(set(declared) | set(implied)),
                headcount=p.headcount,
                trust_tier_ceiling=p.trust_tier_ceiling,
                # Default to every stage rather than none: a position that owns no
                # stage appears in no workflow step, and would vanish from the venture
                # without anybody being told.
                lifecycle_stages_owned=[s for s in all_stages if s in stages],
            )
        )

    return RoleDefinition(
        venture_id=pack.venture_id,
        positions=positions,
        unresolved_modules=sorted(unresolved),
    )


def _all_stages(pack: BusinessPack) -> list[str]:
    """Lifecycle stages in declared order, de-duplicated across service lines.

    Order is the author's, not sorted: a workflow that runs Close before Source is
    not a workflow.
    """
    seen: list[str] = []
    for line in pack.engagement_model.service_lines:
        for stage in line.lifecycle_stages:
            if stage not in seen:
                seen.append(stage)
    return seen
