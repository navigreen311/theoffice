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

from typing import Any

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

#: The tier ladder, ranked. Duplicated from `broker.certification` deliberately: `generators`
#: does not import `broker`, and a generator that reached into the runtime for a constant would
#: make the artifact depend on the thing it is meant to describe.
_TIER_RANK = {"suggest": 1, "propose": 2, "auto_execute": 3}


def _lower(a: str, b: str) -> str:
    """The weaker of two tiers. Ties return the first, which is the declared one."""
    return a if _TIER_RANK[a] <= _TIER_RANK[b] else b


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
    overrides_by_title = {p.position_title: p.module_trust_tiers for p in roles.positions}

    grants: list[PlannedGrant] = []
    if blocked is None:
        for position in appointment.appointments:
            ceiling = tier_by_title.get(position.position_title, "suggest")
            for agent in position.appointed:
                # EVERY MODULE THE POSITION OPERATES, not the certified subset. Ruled
                # 21 September 2026, entry 145: the grant is the exam ticket, and
                # issuing one only for modules already certified is what closed the
                # loop - `_exam_takers` reads grants, so an uncertified agent was never
                # examined and could never stop being uncertified.
                #
                # The grant is written INACTIVE either way. `resolve_grant` refuses it
                # on certification state on every call, and Gate 11 refuses to activate
                # it - so what this hands an uncertified agent is a seat at the exam and
                # nothing else.
                for module in agent.modules:
                    forge = module_forge.get(module, "UNREGISTERED")
                    # The declared ceiling FOR THIS MODULE. Absent from the map means the
                    # position's single ceiling, which is every Pack authored before
                    # `module_trust_tiers` existed - so this line is a no-op for them.
                    # Keyed `forge_id/module_id`, and `forge` is resolved immediately
                    # above - so the two consumers of this map, here and the approval
                    # projection, qualify it the same way and cannot drift.
                    declared = overrides_by_title.get(
                        position.position_title, {}
                    ).get(f"{forge}/{module}", ceiling)
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
                            # The LOWER of what the Pack declares for this module and what
                            # the agent is certified to. Both halves are needed now and only
                            # one was before.
                            #
                            # 5.2 caps `certified_tier` against the position's single ceiling,
                            # so taking it alone used to be correct. With a per-module ceiling
                            # it is not: a module declared `propose` under a position whose
                            # ceiling is `auto_execute` would be issued at the agent's
                            # certified `auto_execute` and the override would do nothing.
                            #
                            # `_lower` rather than `min()` because these are ranked names, not
                            # numbers, and the ranking lives in one place.
                            trust_tier=_lower(
                                declared,
                                agent.certified_tiers.get(f"{forge}/{module}", declared),
                            ),
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


async def _excluded_modules(conn: AsyncConnection) -> dict[tuple[str, str], str]:
    """(forge_id, module_id) -> why no agent may be granted it.

    Read once per apply rather than per grant: the set is small, it does not change
    mid-run, and a per-grant query would make the number of round trips depend on how
    many agents a Pack appoints.
    """
    async with conn.cursor() as cur:
        await cur.execute("SELECT forge_id, module_id, reason FROM forge_module_exclusion")
        return {(r[0], r[1]): r[2] for r in await cur.fetchall()}


async def apply(
    config: RuntimeConfig, conn: AsyncConnection, *, granted_by: str
) -> dict[str, Any]:
    """Write the config. Idempotent: re-running changes nothing and adds nothing.

    Returns counts so a caller can assert the second run wrote zero new rows, which
    is what "zero duplicate side-effects" means in practice.

    AN EXCLUDED MODULE IS SKIPPED AND NAMED, NOT CRASHED ON
    ======================================================

        `forge_module_exclusion` is enforced by a BEFORE INSERT trigger, so a Pack
        whose roles operate an excluded module used to abort the whole apply with a
        raw `IntegrityConstraintViolation` - taking every other grant, the manifest
        rows, the budget and the rate limits down with it. The control was right and
        the caller had never been told it existed.

        Now the excluded modules are read first and their grants are skipped, with
        the module and the reason returned under `grants_excluded`. The rest of the
        config applies. **Skipping is the whole point**: an exclusion means no agent
        may hold this, and a provisioning run that cannot finish because of one is a
        run that pressures somebody to remove the row.

        The trigger stays. This reads the same table a moment earlier; the trigger is
        what makes it true, and a check without it would be a check somebody can
        bypass by writing a grant another way.
    """
    if config.blocked_reason:
        raise ValueError(
            f"refusing to apply a blocked runtime config: {config.blocked_reason}"
        )

    excluded = await _excluded_modules(conn)
    written: dict[str, Any] = {
        "manifest_rows": 0, "grants": 0, "budget": 0, "rate_limits": 0,
        "grants_excluded": [],
    }

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
            reason = excluded.get((grant.forge_id, grant.module_id))
            if reason is not None:
                written["grants_excluded"].append({
                    "forge_id": grant.forge_id,
                    "module_id": grant.module_id,
                    "office_agent_id": str(grant.office_agent_id),
                    "reason": reason,
                })
                continue
            # No ON CONFLICT DO NOTHING on the natural key here: the deterministic
            # grant_id IS the conflict target, so a re-run updates its own row.
            await cur.execute(
                """
                INSERT INTO agent_forge_grant
                  (grant_id, office_agent_id, forge_id, module_id, venture_id,
                   trust_tier, operation_cert_ref, dept_context_cert_ref, granted_by,
                   origin)
                VALUES (%s, %s, %s, %s, %s, %s,
                        (SELECT cert_id::text FROM certification
                          WHERE unit = 'A' AND office_agent_id = %s
                            AND forge_id = %s AND module_id = %s),
                        (SELECT cb.cert_id::text FROM certification cb
                           JOIN office_agent_identity i
                             ON i.department = cb.department
                          WHERE cb.unit = 'B' AND i.office_agent_id = %s
                            AND cb.forge_id = %s),
                        %s, 'ladder')
                -- POINTERS ARE REFRESHED; HISTORY IS NOT.
                --
                -- This used to set `trust_tier` alone, and that left a re-run unable to
                -- repair a grant whose certification refs had gone stale - which is how
                -- Gate 9 came to block on 68 units pointing at rows that no longer
                -- existed, with "just re-provision" as the obvious remedy that could
                -- never work (entry 68).
                --
                -- The two refs are POINTERS at a current fact, so they converge: a
                -- second apply resolves them against the certifications that exist now.
                -- `granted_by` and `granted_at` are HISTORY and are deliberately absent
                -- from this list - refreshing them would rewrite who granted something
                -- and erase when, which is the opposite of what a re-run should do.
                --
                -- A ref resolving to NULL overwrites a non-NULL one on purpose. NULL is
                -- a state `resolve_grant` reports truthfully (`grants.py:225` raises
                -- NotCertified naming which half is missing); a stale non-NULL ref
                -- pointing at a deleted row is the silent failure this exists to end.
                --
                -- `origin` IS REFRESHED, AND IT IS THE ONE FACT THIS WRITER OWNS.
                --
                -- Greenstone's six ladder grants read `origin = 'unknown'` because Gate
                -- 5 wrote them before 0043 added the column. That is not harmless: the
                -- supersession rule below requires `l.origin = 'ladder'`, so a future
                -- Phase 0 grant on this venture would NOT be retired by its replacement.
                --
                -- **Backfilling those six on inference was refused.** 0043 would not
                -- write `ladder` on a guess, and the audit log cannot settle it either -
                -- checked, on 17 September 2026: the whole log holds three `grant_issued`
                -- events and all three are Phase 0.8 bootstraps. `apply` writes none, so
                -- there is no record of the ladder issuing anything.
                --
                -- So the row is corrected by the only party that knows: this statement.
                -- When the ladder writes a grant it says so, and a row it re-writes
                -- stops claiming not to know. That is a fact this writer observes rather
                -- than one a migration infers, and it converges - the same argument the
                -- certification pointers above are refreshed on.
                ON CONFLICT (grant_id) DO UPDATE SET
                  trust_tier            = EXCLUDED.trust_tier,
                  operation_cert_ref    = EXCLUDED.operation_cert_ref,
                  dept_context_cert_ref = EXCLUDED.dept_context_cert_ref,
                  origin                = 'ladder' 
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

        # RETIRE THE PHASE 0 GRANTS THIS RUN HAS JUST REPLACED.
        #
        # `bootstrap-phase0` issues one identity, two certifications, one grant and one
        # shift so that a real call can be made before the ladder exists. The grant it
        # writes is ACTIVE by design - an inactive one would prove nothing, and proving
        # the call path works is the whole of Phase 0.
        #
        # Which means a venture that bootstraps and then provisions ends up holding two
        # grants for the same triple: one active, one inactive. Gate 7 exists to refuse
        # exactly that shape - "grants are issued inactive and activated only against a
        # valid sign-off" - and run cb3a47f6 blocked on it, three gates after the review.
        #
        # **Retired, not revoked.** Revocation means the authority was wrong; a Phase 0
        # grant that has been replaced was not. It is also the wrong instrument: the
        # narrowest revocation scope is (agent, forge, module), which covers the
        # replacement too, so revoking would leave Gate 11 unable to activate the grant
        # this very loop just wrote. Measured before this was built.
        #
        # The row stays readable, and `resolve_grant` refuses it with `GrantSuperseded`.
        await cur.execute(
            """
            UPDATE agent_forge_grant b SET superseded_at = now()
             WHERE b.venture_id = %s
               AND b.origin = 'bootstrap'
               AND b.superseded_at IS NULL
               AND EXISTS (
                 SELECT 1 FROM agent_forge_grant l
                  WHERE l.office_agent_id = b.office_agent_id
                    AND l.forge_id        = b.forge_id
                    AND l.module_id       = b.module_id
                    AND l.venture_id      = b.venture_id
                    AND l.grant_id       <> b.grant_id
                    -- `= 'ladder'` and not `<> 'bootstrap'`. The ruling is that the
                    -- LADDER issuing its own grant retires the bootstrap one, and
                    -- `origin` has a third value: `unknown`, for the rows that predate
                    -- 0043 and for anything else that writes a grant without saying so.
                    -- An `unknown` row must not retire anything - nothing is retired on
                    -- a guess. (0043 applies a looser one-off over cb3a47f6's three,
                    -- whose replacements Gate 5 wrote before this column existed and so
                    -- backfilled as `unknown`; that migration says why, over rows that
                    -- were counted first.)
                    AND l.origin          = 'ladder'
                    AND l.superseded_at IS NULL
               )
            """,
            (config.venture_id,),
        )
        written["grants_superseded"] = cur.rowcount

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
