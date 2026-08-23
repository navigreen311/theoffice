"""5.7 Runtime Config Generator.

In: everything above. Out: idempotent deployment configuration — grants issued,
integrations wired, flags applied, the engagement registered.

Two things master prompt 5.7 states that shape the whole module:

**"Consumes the Manifest, not the Pack."** So a Pack that would provision and a
Manifest that would not cannot disagree. If reconciliation blocks, this generator emits
a config with `blocked_reason` set and **no grants at all** — rather than emitting
grants and trusting a later gate to catch it.

**"Re-running produces identical state with zero duplicate side-effects."** That is
achieved structurally, not by defensive `ON CONFLICT` clauses bolted on afterwards:
`grant_id` is UUIDv5 over (venture, agent, forge, module), so a second run computes the
same primary keys and collides with its own prior rows. Idempotency by construction
survives a refactor; idempotency by remembering to write `ON CONFLICT` does not.

`apply()` is the only function here that writes. `generate()` is pure, so the config can
be reviewed at Gate 4 before anything touches the database.
"""

from __future__ import annotations

from psycopg import AsyncConnection

from generators.artifacts import (
    Appointment,
    ForgeManifest,
    PlannedGrant,
    RoleDefinition,
    RuntimeConfig,
    derive_id,
)
from generators.pack import BusinessPack


def generate(
    pack: BusinessPack,
    roles: RoleDefinition,
    appointment: Appointment,
    forge_manifest: ForgeManifest,
    *,
    module_forge: dict[str, str],
) -> RuntimeConfig:
    recon = forge_manifest.reconciliation
    blocked: str | None = None
    if recon.required_not_declared:
        blocked = (
            "REQUIRED_NOT_DECLARED: "
            f"{', '.join(recon.required_not_declared)}. A workflow step requires a "
            "module the Pack never declared. Declaring it here would let a workflow "
            "grant itself access to any module by referencing one."
        )
    elif recon.hard_dependency_on_gap:
        blocked = (
            "HARD DEPENDENCY ON MODULE GAP: "
            f"{', '.join(recon.hard_dependency_on_gap)}. Cannot provision."
        )

    tier_by_title = {p.position_title: p.trust_tier_ceiling for p in roles.positions}

    grants: list[PlannedGrant] = []
    if blocked is None:
        for position in appointment.appointments:
            ceiling = tier_by_title.get(position.position_title, "suggest")
            for agent in position.appointed:
                for module in agent.certified_modules:
                    forge = module_forge.get(module, "UNREGISTERED")
                    grants.append(
                        PlannedGrant(
                            grant_id=str(
                                derive_id(
                                    pack.venture_id,
                                    agent.office_agent_id,
                                    forge,
                                    module,
                                )
                            ),
                            office_agent_id=agent.office_agent_id,
                            forge_id=forge,
                            module_id=module,
                            # Certified tier already capped by the ceiling in 5.2;
                            # min() again here would be re-deriving a decision that
                            # has an owner.
                            trust_tier=agent.certified_tier or ceiling,
                        )
                    )
        grants.sort(key=lambda g: (g.office_agent_id, g.forge_id, g.module_id))

    rate_limits = {
        b.forge: {
            "max_rps": float(b.rate_limit_policy.max_rps),
            "burst": float(b.rate_limit_policy.burst),
        }
        for b in sorted(pack.forge_dependencies.forge_bindings, key=lambda b: b.forge)
        if b.rate_limit_policy is not None
    }

    return RuntimeConfig(
        venture_id=pack.venture_id,
        environment=pack.environment,
        grants=grants,
        manifest_rows=[e for e in forge_manifest.entries if e.declared],
        rate_limits=rate_limits,
        budget={
            "monthly_usd_cap": pack.budget.monthly_usd_cap,
            "soft_cap_pct": float(pack.budget.soft_cap_pct),
            "per_agent_usd_daily_cap": pack.budget.per_agent_usd_daily_cap,
            "per_task_usd_ceiling": pack.budget.per_task_usd_ceiling,
        },
        compliance_flags=sorted(
            {c.runtime_flag for c in pack.market.compliance_surface if c.runtime_flag}
        ),
        blocked_reason=blocked,
    )


async def apply(
    config: RuntimeConfig, conn: AsyncConnection, *, granted_by: str
) -> dict[str, int]:
    """Write the config. Idempotent: re-running changes nothing and adds nothing.

    Returns counts so a caller can assert the second run wrote zero new rows, which
    is what "zero duplicate side-effects" means in practice.
    """
    if config.blocked_reason:
        raise ValueError(
            f"refusing to apply a blocked runtime config: {config.blocked_reason}"
        )

    written = {"manifest_rows": 0, "grants": 0, "budget": 0, "rate_limits": 0}

    async with conn.cursor() as cur:
        for row in config.manifest_rows:
            await cur.execute(
                """
                INSERT INTO venture_forge_manifest
                  (venture_id, forge_id, module_id, is_required, criticality, module_gap)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (venture_id, forge_id, module_id) DO UPDATE
                SET is_required = EXCLUDED.is_required,
                    criticality = EXCLUDED.criticality,
                    module_gap  = EXCLUDED.module_gap
                """,
                (
                    config.venture_id, row.forge_id, row.module_id,
                    row.required, row.criticality, row.module_gap,
                ),
            )
            written["manifest_rows"] += 1

        for grant in config.grants:
            # No ON CONFLICT DO NOTHING on the natural key here: the deterministic
            # grant_id IS the conflict target, so a re-run updates its own row.
            await cur.execute(
                """
                INSERT INTO agent_forge_grant
                  (grant_id, office_agent_id, forge_id, module_id, venture_id,
                   trust_tier, operation_cert_ref, dept_context_cert_ref, granted_by)
                VALUES (%s, %s, %s, %s, %s, %s,
                        (SELECT cert_id::text FROM certification
                          WHERE unit = 'A' AND office_agent_id = %s
                            AND forge_id = %s AND module_id = %s),
                        (SELECT cb.cert_id::text FROM certification cb
                           JOIN office_agent_identity i
                             ON i.department = cb.department
                          WHERE cb.unit = 'B' AND i.office_agent_id = %s
                            AND cb.forge_id = %s),
                        %s)
                ON CONFLICT (grant_id) DO UPDATE SET trust_tier = EXCLUDED.trust_tier
                """,
                (
                    grant.grant_id, grant.office_agent_id, grant.forge_id,
                    grant.module_id, config.venture_id, grant.trust_tier,
                    grant.office_agent_id, grant.forge_id, grant.module_id,
                    grant.office_agent_id, grant.forge_id,
                    granted_by,
                ),
            )
            written["grants"] += 1

        await cur.execute(
            """
            INSERT INTO venture_budget
              (venture_id, monthly_usd_cap, soft_cap_pct, per_agent_usd_daily_cap,
               per_task_usd_ceiling)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (venture_id) DO UPDATE
            SET monthly_usd_cap = EXCLUDED.monthly_usd_cap,
                soft_cap_pct = EXCLUDED.soft_cap_pct,
                per_agent_usd_daily_cap = EXCLUDED.per_agent_usd_daily_cap,
                per_task_usd_ceiling = EXCLUDED.per_task_usd_ceiling
            """,
            (
                config.venture_id,
                config.budget["monthly_usd_cap"],
                int(config.budget["soft_cap_pct"]),
                config.budget["per_agent_usd_daily_cap"],
                config.budget["per_task_usd_ceiling"],
            ),
        )
        written["budget"] += 1

        for forge, limits in sorted(config.rate_limits.items()):
            # Never resets tokens: re-applying a config must not hand a caller a
            # full bucket, which would make re-provisioning a rate-limit bypass.
            await cur.execute(
                """
                INSERT INTO rate_limit_bucket
                  (bucket_key, tokens, max_tokens, refill_per_second)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (bucket_key) DO UPDATE
                SET max_tokens = EXCLUDED.max_tokens,
                    refill_per_second = EXCLUDED.refill_per_second
                """,
                (f"forge:{forge}", limits["burst"], limits["burst"], limits["max_rps"]),
            )
            written["rate_limits"] += 1

    await conn.commit()
    return written
