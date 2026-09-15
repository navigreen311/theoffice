"""Grant resolution — the authorization decision, made fresh on every call.

Master prompt §1.4: revocation is "checked per call at the broker, never cached.
A revoked agent's next call fails, not its next session."

That sentence rules out every cache, including a short-TTL one. There is no
`@lru_cache` here and there must never be. With no front desk to stop and no
queue to drain, this query *is* the kill switch.

One query answers four questions at once, because splitting them invites a caller
to check three and forget the fourth:

  1. Does the identity exist and is it `active`?
  2. Is there a grant for this agent x forge x module x venture?
  3. Is that grant un-revoked?
  4. Are BOTH certification units present AND in state `certified`?
  5. Has the grant been ACTIVATED (Gate 11)?

Point 5 was added with the provisioning pipeline, and finding that it was needed is
worth recording. `agent_forge_grant.is_assignable` is a generated column that encodes
exactly this condition - and **nothing read it.** This function re-derived the check
itself, so adding activation to the column changed nothing at runtime and the Gate 7/11
distinction would have been decorative. A computed column nobody reads is documentation
with a CHECK constraint attached.

Point 4 changed in Phase 2. Before, the gate was a non-null check on a free-text
column and any string satisfied it. Now it joins `certification` and requires state
`certified` on both units, live - so a cert that went stale because its module's
instructions were rewritten stops the very next call, for the same reason revocation
does.

The Forge and module are read from the registry in the same round trip - nothing
about which Forge is bridged first may be hardcoded (see CLAUDE.md).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import audit, humans
from broker.certification import cap_tier
from broker.errors import (
    GrantNotActivated,
    IdentityInactive,
    ModuleExcluded,
    NotAuthorized,
    NotCertified,
    NotGranted,
    UnknownForge,
)


@dataclass(frozen=True, slots=True)
class ResolvedGrant:
    """Everything the call path needs, resolved together and consistently."""

    grant_id: uuid.UUID
    office_agent_id: uuid.UUID
    agent_name: str
    forge_id: str
    module_id: str
    venture_id: str
    trust_tier: str
    base_url: str
    api_version: str
    auth_model: str
    credential_mode: str
    credential_ref: str
    idempotency_support: str
    is_mutating: bool
    compliance_flags: tuple[str, ...]
    certified_tier: str
    """Part 10.1: certified tier caps declared tier. `trust_tier` above is already
    capped by this - callers must not re-derive it."""

    @property
    def is_compliance_flagged(self) -> bool:
        """Whether a failed audit write must fail closed rather than degrade."""
        return bool(self.compliance_flags)


_RESOLVE_SQL = """
SELECT
    g.grant_id,
    g.office_agent_id,
    g.trust_tier,
    g.operation_cert_ref,
    g.dept_context_cert_ref,
    i.agent_name,
    i.department,
    i.status                  AS identity_status,
    r.base_url,
    r.api_version,
    r.auth_model,
    r.credential_mode,
    c.credential_ref,
    m.idempotency_support,
    m.is_mutating,
    m.compliance_flags_implied,
    g.activated_at,
    ca.state          AS unit_a_state,
    ca.certified_tier AS unit_a_tier,
    cb.state          AS unit_b_state,
    x.reason          AS exclusion_reason
FROM agent_forge_grant g
JOIN office_agent_identity i ON i.office_agent_id = g.office_agent_id
JOIN forge_registry       r ON r.forge_id        = g.forge_id
JOIN forge_module_registry m ON m.forge_id = g.forge_id AND m.module_id = g.module_id
LEFT JOIN forge_tenant_credential c ON c.forge_id = g.forge_id
-- An excluded module answers without doing the work. Joined here rather than
-- queried separately so the refusal costs no extra round trip on the hot path.
LEFT JOIN forge_module_exclusion x ON x.forge_id  = g.forge_id
                                  AND x.module_id = g.module_id
-- Certification state, live. LEFT JOIN so a missing cert is distinguishable from a
-- cert in a non-certified state: "never certified" and "failed" are different
-- findings and must not collapse into one message.
LEFT JOIN certification ca ON ca.unit = 'A'
                          AND ca.office_agent_id = g.office_agent_id
                          AND ca.forge_id = g.forge_id
                          AND ca.module_id = g.module_id
LEFT JOIN certification cb ON cb.unit = 'B'
                          AND cb.department = i.department
                          AND cb.forge_id = g.forge_id
WHERE g.office_agent_id = %(agent_id)s
  AND g.forge_id        = %(forge_id)s
  AND g.module_id       = %(module_id)s
  AND g.venture_id      = %(venture_id)s
ORDER BY g.granted_at DESC
LIMIT 1
"""


async def resolve_grant(
    conn: AsyncConnection,
    *,
    office_agent_id: uuid.UUID,
    forge_id: str,
    module_id: str,
    venture_id: str,
) -> ResolvedGrant:
    """Resolve authorization, or raise the specific reason it was refused.

    Raises a distinct type per refusal so the caller audits *why*, not merely
    *that*. Ordering is deliberate: identity state is reported before grant
    state, because a suspended agent with a valid grant is a different incident
    from an active agent with none.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            _RESOLVE_SQL,
            {
                "agent_id": office_agent_id,
                "forge_id": forge_id,
                "module_id": module_id,
                "venture_id": venture_id,
            },
        )
        row = await cur.fetchone()

    if row is None:
        # Distinguish "this Forge/module is not registered" from "this agent has
        # no grant for it" - they are different failures with different fixes.
        #
        # Exclusion is checked here too, and first. An excluded module is usually
        # NOT registered - it is excluded precisely so it never gets a registry row
        # - so without this an excluded module reports as merely unknown, and the
        # reader learns nothing about why it will stay unknown.
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT reason FROM forge_module_exclusion "
                "WHERE forge_id = %s AND module_id = %s",
                (forge_id, module_id),
            )
            excluded = await cur.fetchone()
            await cur.execute(
                "SELECT 1 FROM forge_module_registry WHERE forge_id = %s AND module_id = %s",
                (forge_id, module_id),
            )
            known = await cur.fetchone()
        if excluded is not None:
            raise ModuleExcluded(
                "module is excluded and may never be granted",
                forge_id=forge_id,
                module_id=module_id,
                exclusion_reason=excluded["reason"],
            )
        if known is None:
            raise UnknownForge(
                "forge or module is not registered",
                forge_id=forge_id,
                module_id=module_id,
            )
        raise NotGranted(
            "no grant for this agent, forge, module and venture",
            forge_id=forge_id,
            module_id=module_id,
            venture_id=venture_id,
        )

    # Before anything about this agent. A grant that exists for an excluded module
    # predates the exclusion or bypassed the trigger; either way no agent may use it,
    # and reporting a suspended identity first would bury the reason that matters.
    if row["exclusion_reason"] is not None:
        raise ModuleExcluded(
            "module is excluded and may never be granted",
            forge_id=forge_id,
            module_id=module_id,
            grant_id=str(row["grant_id"]),
            exclusion_reason=row["exclusion_reason"],
        )

    if row["identity_status"] != "active":
        raise IdentityInactive(
            f"agent identity is {row['identity_status']}",
            identity_status=row["identity_status"],
        )

    # A revoked grant is refused by `check_revocations` above, against the
    # `revocation` table. There is no second answer here: `agent_forge_grant.revoked_at`
    # was dropped in migration 0036 (B37) because nothing ever wrote it and a value in
    # it was a stop with no reason, no actor and no reinstatement path.

    if row["operation_cert_ref"] is None or row["dept_context_cert_ref"] is None:
        raise NotCertified(
            "grant is missing a certification unit reference and is not assignable",
            operation_cert=row["operation_cert_ref"] is not None,
            dept_context_cert=row["dept_context_cert_ref"] is not None,
        )

    # Phase 2: the reference existing is not the gate - the STATE is. Reported
    # per unit and by name, because `stale_instructions` (was good, text changed),
    # `failed` (was never good) and `never_certified` (never attempted) call for
    # three different responses.
    unit_a = row["unit_a_state"] or "never_certified"
    unit_b = row["unit_b_state"] or "never_certified"
    if unit_a != "certified" or unit_b != "certified":
        raise NotCertified(
            "certification is not current; the grant is not assignable",
            unit_a_state=unit_a,
            unit_b_state=unit_b,
            department=row["department"],
        )

    # Gate 11. An issued-but-unactivated grant is a venture mid-provisioning, not a
    # missing appointment.
    if row["activated_at"] is None:
        raise GrantNotActivated(
            "grant has not been activated; the venture has not completed provisioning "
            "through Gate 11",
            grant_id=str(row["grant_id"]),
            venture_id=venture_id,
        )

    if row["credential_ref"] is None:
        raise UnknownForge(
            "forge has no tenant credential registered", forge_id=forge_id
        )

    # Part 10.1: "The Pack declares a ceiling; SimForge sets the actual." Applied
    # live rather than at grant issuance, so a cert downgraded after the grant was
    # written takes effect on the next call - same reason revocation is not cached.
    certified_tier = row["unit_a_tier"]
    effective_tier = cap_tier(row["trust_tier"], certified_tier)

    return ResolvedGrant(
        grant_id=row["grant_id"],
        office_agent_id=row["office_agent_id"],
        agent_name=row["agent_name"],
        forge_id=forge_id,
        module_id=module_id,
        venture_id=venture_id,
        trust_tier=effective_tier,
        certified_tier=certified_tier,
        base_url=row["base_url"],
        api_version=row["api_version"],
        auth_model=row["auth_model"],
        credential_mode=row["credential_mode"],
        credential_ref=row["credential_ref"],
        idempotency_support=row["idempotency_support"],
        is_mutating=row["is_mutating"],
        compliance_flags=tuple(row["compliance_flags_implied"] or ()),
    )


async def deactivate(
    conn: AsyncConnection,
    *,
    venture_id: str,
    human: humans.Human,
    reason: str,
) -> int:
    """Return a venture's active grants to awaiting-activation. NOT a revocation.

    THE LINE THIS MUST NOT CROSS
    ============================

        **Deactivating a grant is not revoking it, and the two are one keystroke apart.**
        A revocation says *this authority is withdrawn* and is recorded in its own table,
        consulted on every call, liftable only by a named human at the same scope.
        Deactivation says *this grant has not yet passed Gate 11* - the state Gate 5
        creates and Gate 11 clears.

        So this touches `activated_at` and `activated_by` and NOTHING else. No revocation
        row is written, no certification ref moves, the grant keeps its `granted_by` and
        `granted_at`, and `revocation.check_revocations` is not consulted or altered. A
        caller that wants authority withdrawn wants `revocation.revoke`, which says so.

    WHY IT EXISTS, AND WHY IT DID NOT
    =================================

        `agent_forge_grant.activated_at` had exactly one writer in the repository -
        `_gate_11`, which only ever writes `now()`, under `WHERE activated_at IS NULL`.
        Activation was one-way by intent: a threshold you cross, not a state you toggle.

        **That was right until a grant arrived already across it.** `bootstrap_phase0`
        issues Phase 0 grants activated at insert, because Phase 0 runs before any
        provisioning run exists and there is no sign-off to activate against.
        `docs/blocking.md` recorded the collision before anyone reached it: *"Phase 0
        activated grants because there was no ladder to activate them; the ladder now
        refuses to run past grants that are already active. The two are correct and
        incompatible."*

        **That is a conditional, and the condition expired.** A grant activated for want
        of a mechanism is provisional by construction, and when the mechanism arrives the
        grant goes through it. This is the verb for that, and without it the only option
        was an unattributed `UPDATE` on the column that decides whether an agent can
        reach a Forge.

    WHAT HAPPENS NEXT, SO NOBODY READS THE RESULT AS MORE THAN IT IS
    ================================================================

        Gate 11 is venture-scoped - `WHERE venture_id = %s AND activated_at IS NULL` -
        so every grant deactivated here is in the set it acts on, and comes back against
        a Gate 10 signature bound to the current artifacts.

        **Coming back active is not the same as becoming reachable.** Where two grants
        share an (agent, forge, module) triple, `resolve_grant` takes the newest and the
        older one is unselectable whatever its `activated_at` says. Deactivating and
        reactivating a superseded grant moves it through the gate and changes nothing
        about which row answers a call. That duplication is a separate question
        (decisions.md entry 67) and this function does not touch it.
    """
    if not reason.strip():
        raise NotAuthorized("deactivating grants requires a documented reason")
    humans.authorize(human, required_role="venture_operator", venture_id=venture_id)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT grant_id::text, forge_id, module_id, office_agent_id::text "
            "  FROM agent_forge_grant "
            " WHERE venture_id = %s AND activated_at IS NOT NULL "
            " ORDER BY forge_id, module_id",
            (venture_id,),
        )
        targets = [dict(r) for r in await cur.fetchall()]

    if not targets:
        raise NotAuthorized(
            f"{venture_id} has no active grants. A deactivation reporting success "
            "without changing anything is a record of an act that did not happen."
        )

    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE agent_forge_grant SET activated_at = NULL, activated_by = NULL "
            " WHERE venture_id = %s AND activated_at IS NOT NULL",
            (venture_id,),
        )
        changed = cur.rowcount
    await conn.commit()

    await audit.write_event(
        event_type="grant_deactivated",
        actor_type="human",
        actor_id=human.human_id,
        venture_id=venture_id,
        subject={
            "grants": changed,
            "reason": reason,
            # Named individually, because "34 grants" is not something a reader can
            # check and a list is. Same argument as the dry-run legibility note.
            "modules": sorted({f"{t['forge_id']}/{t['module_id']}" for t in targets}),
        },
    )
    return changed
