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
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import audit, humans
from broker.certification import cap_tier
from broker.errors import (
    CertificationNamesNoModel,
    GrantNotActivated,
    GrantSuperseded,
    IdentityInactive,
    ModuleExcluded,
    NotAuthorized,
    NotCertified,
    NotGranted,
    NoTierPlanned,
    SimulationCertificationVoid,
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

    unit_b_simulation_only: bool = False
    """Whether this grant's department context is certified for simulation only.

    RULED 22 SEPTEMBER 2026, entry 167: *"Any surface showing a grant, a gate or a
    sign-off says which of its certifications are simulation-only."* This is the grant.

    False for a void one, because a void simulation certification never gets this far -
    `resolve_grant` raises `SimulationCertificationVoid` before building this. So the
    flag means exactly *certified on a live declaration rather than on an exam*, and it
    travels into the audit subject with every call the grant authorises.
    """

    @property
    def is_compliance_flagged(self) -> bool:
        """Whether this call carries a declared compliance framework.

        **No longer what decides fail-closed** - see `must_fail_closed`. Kept because the
        flags travel in the audit subject and a reader asking "was this a flagged call"
        is asking a real question; it is just not the question the audit branch asks.
        """
        return bool(self.compliance_flags)

    @property
    def must_fail_closed(self) -> bool:
        """Whether a failed audit write must halt the call rather than degrade.

        **Mutation, not flags. Ivan's ruling of 15 September:** any mutating module call
        fails if its audit write fails, whether or not a compliance flag is present.

        It used to be `bool(compliance_flags)`, and that rested on the flags being true.
        They were not: every CRE Forge module carried `tsr_disclosure_required` because
        the development fixture wrote one flag list per FORGE and looped it over every
        module (entry 105). So the fail-closed property of five modules - including
        `assign_contract`, which writes a contract - was an accident of a test fixture,
        and correcting the flags would have removed it silently.

        **`is_mutating` is the honest key.** It is the adapter's own declaration at its
        binding site, verified against the live manifest by `verify_forge_modules.py`,
        and it answers the question the rule is about: an unrecorded READ is a gap in the
        log, while an unrecorded WRITE is a change to the world nobody can find. A read
        still degrades, because halting every call on an audit outage turns a logging
        problem into a total outage.
        """
        return self.is_mutating


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
    g.superseded_at,
    ca.state          AS unit_a_state,
    ca.certified_tier AS unit_a_tier,
    ca.model_digest   AS unit_a_digest,
    ca.simforge_verdict AS unit_a_verdict,
    cb.state          AS unit_b_state,
    -- Entry 167. A simulation certification reads `certified` and is void the moment
    -- its venture leaves simulation - derived here by join, because a stored flag
    -- would let a call resolve on a permission that ended.
    (cb.basis = 'simulation')  AS unit_b_simulation_only,
    (vs.left_at IS NOT NULL)   AS unit_b_simulation_void,
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
LEFT JOIN venture_simulation vs ON vs.simulation_id = cb.simulation_ref
WHERE g.office_agent_id = %(agent_id)s
  AND g.forge_id        = %(forge_id)s
  AND g.module_id       = %(module_id)s
  AND g.venture_id      = %(venture_id)s
-- A LIVE GRANT BEATS A RETIRED ONE, WHATEVER THE DATES SAY.
--
-- `granted_at DESC` alone is nearly always enough: the ladder issues after the bootstrap.
-- Nearly is not a rule. Ordering retired rows last means the refusal below fires only when
-- EVERY grant for this triple has been superseded, which is the state it describes -
-- rather than when the newest one happens to be the retired one.
ORDER BY (g.superseded_at IS NOT NULL), g.granted_at DESC
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

    # A SIMULATION CERTIFICATION IS VOID ONCE THE VENTURE HAS LEFT.
    # Ruled 22 September 2026, entry 167.
    #
    # *"Every simulation certification is void at that point."* Void means void here
    # too: this is the check that runs on every single call, and a certification that
    # Gate 9 would now refuse cannot be one the call path still accepts. The row still
    # reads `certified` - nothing edits a certification - so without this the venture
    # would leave simulation and its agents would carry on.
    #
    # After `NotCertified`, because "never certified" is the more basic fact, and its
    # own type because the remedy is different: this grant was certified, on a
    # permission that has ended, and what it needs is a real Unit B rather than a
    # re-run of anything.
    if row["unit_b_simulation_void"]:
        raise SimulationCertificationVoid(
            "the Unit B certification behind this grant was issued for a simulation "
            "the venture has since left, and is void. Entry 167: a simulation "
            "certification is void the moment the venture leaves.",
            department=row["department"],
        )

    # THE CERTIFICATION PASSED AND NOTHING CAN SAY WHICH MODEL PASSED IT.
    #
    # After `NotCertified`, because "not certified" and "certified by a model nobody
    # recorded" are different facts and the first is the more basic one. Before
    # supersession and activation, because those are about the GRANT and this is about
    # the certification behind it.
    #
    # Only a SimForge-attested row is asked. A bootstrap certification carries no model
    # by design - no battery ran, so none answered - and demanding one here would refuse
    # every Phase 0 call for lacking a fact Phase 0 is defined not to have.
    if row["unit_a_verdict"] is not None and not row["unit_a_digest"]:
        raise CertificationNamesNoModel(
            "certification carries a SimForge verdict and no model digest; it cannot be "
            "expired when the model changes, so it cannot be relied on now",
            forge_id=forge_id,
            module_id=module_id,
        )

    # Retired before activation is considered: a superseded grant's `activated_at` is
    # whatever it was when the ladder replaced it, and reporting "not activated" for a row
    # that WAS activated would name the wrong problem.
    if row["superseded_at"] is not None:
        raise GrantSuperseded(
            "grant was superseded when the ladder issued its own for this agent, forge, "
            "module and venture; it is kept as history and confers nothing",
            grant_id=str(row["grant_id"]),
            venture_id=venture_id,
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
    if row["trust_tier"] is None:
        # Entry 145 / 0049. See `NoTierPlanned`: this is an exam ticket, and there is no
        # planned authority for `cap_tier` to cap.
        raise NoTierPlanned(
            "grant plans no trust tier; it was issued for an exam and confers nothing",
            grant_id=str(row["grant_id"]),
            module_id=module_id,
        )

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
        unit_b_simulation_only=bool(row["unit_b_simulation_only"]),
    )


async def retire(
    conn: AsyncConnection,
    *,
    grant_ids: list[uuid.UUID],
    human: humans.Human,
    reason: str,
) -> list[dict[str, Any]]:
    """Retire named grants. A named human, a reason, and an audit event.

    RULED 23 SEPTEMBER 2026 (decisions entry 182)
    =============================================

        *"A grant may be retired by a named human, with a reason and an audit event.
        Sets `superseded_at`; never a guess and never automatic. Measured:
        `superseded_at` has one writer, which retires only bootstrap grants a ladder
        grant replaced, so a revoked `origin='unknown'` grant cannot be retired at
        all."*

    WHAT WAS THERE, AND WHY IT COULD NOT REACH THESE ROWS
    ====================================================

        `agent_forge_grant.superseded_at` had exactly one writer:
        `generators/runtime_config.py`, retiring `origin = 'bootstrap'` rows that a
        `origin = 'ladder'` row replaced. Its own comment says why it will not go
        further - *"An `unknown` row must not retire anything - nothing is retired on a
        guess"* - and that is right about an AUTOMATIC rule.

        It leaves no path at all for a row that should be retired on a judgement.
        Measured: Amelie Wystan's two engineering grants are `origin = 'unknown'`, have
        no ladder replacement, are covered by live revocations of 15 September, and
        could not be retired by anything in this repository.

        So the gap is not in the automatic rule. It is that there was no deliberate one.

    RETIRED IS NOT REVOKED, AND NOT DEACTIVATED
    ===========================================

        Three verbs, one table, and they are a keystroke apart:

            revoke      the authority was WRONG. Its own table, consulted on every
                        call, liftable by a named human at the same scope.
            deactivate  the grant has not passed Gate 11 yet. `activated_at` only.
            retire      the grant is FINISHED. It is not the row that answers any
                        more, and nothing is claimed about whether it should have
                        existed.

        Retiring does not revoke and revoking does not retire. These two grants are
        both - revoked on 15 September because the authority was wrong, retired now
        because the row should stop being one Gate 9 counts. Either without the other
        would be half the record.

    NAMED INDIVIDUALLY, NEVER MATCHED
    =================================

        `grant_ids`, not a predicate. A retirement that selects rows by a rule is the
        automatic path this exists beside, and the ruling's words are *never a guess*.
        A caller that wants twenty rows names twenty.

        **Every id must exist and be live**, and the whole call refuses if one is not.
        A partial retirement would leave the operator deciding which half happened -
        the failure mode `author_cre_forge_instructions` calls out for the same reason.

    WHO
    ===

        `venture_operator`, scoped to each grant's own venture - the same authority
        `deactivate` takes, because the effect is the same size: a grant stops being
        the one that answers. It is NOT the `ivan` that `certify_for_simulation`
        needs, which spends a founder's declaration.

    Returns the rows it retired, so the caller reports what changed rather than a
    count nobody can check.
    """
    if not reason.strip():
        raise NotAuthorized("retiring a grant requires a documented reason")
    if not grant_ids:
        raise NotAuthorized(
            "retiring no grants is not an act. A retirement reporting success without "
            "naming a row is a record of something that did not happen."
        )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT g.grant_id::text AS grant_id, g.venture_id, g.forge_id, "
            "       g.module_id, g.origin, g.superseded_at, i.agent_name "
            "  FROM agent_forge_grant g "
            "  JOIN office_agent_identity i ON i.office_agent_id = g.office_agent_id "
            " WHERE g.grant_id = ANY(%s) ORDER BY g.forge_id, g.module_id",
            ([str(g) for g in grant_ids],),
        )
        found = [dict(r) for r in await cur.fetchall()]

    seen = {r["grant_id"] for r in found}
    missing = [str(g) for g in grant_ids if str(g) not in seen]
    if missing:
        raise NotAuthorized(
            f"no grant with id(s) {', '.join(sorted(missing))}. Nothing was retired: a "
            "call that names a row this table does not hold is a call about something "
            "else."
        )
    already = [r["grant_id"] for r in found if r["superseded_at"] is not None]
    if already:
        raise NotAuthorized(
            f"grant(s) {', '.join(sorted(already))} are already retired. Nothing was "
            "written - re-retiring would move `superseded_at` and overwrite the date "
            "the row actually stopped answering."
        )

    # AUTHORIZED PER VENTURE, not once. A list spanning two ventures needs the role in
    # both, and checking the first would let one venture's operator retire another's.
    for venture_id in sorted({r["venture_id"] for r in found}):
        humans.authorize(human, required_role="venture_operator", venture_id=venture_id)
    humans.assert_named_human(human, act="retire a grant")

    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE agent_forge_grant SET superseded_at = now() "
            " WHERE grant_id = ANY(%s) AND superseded_at IS NULL",
            ([str(g) for g in grant_ids],),
        )
    await conn.commit()

    await audit.write_event(
        event_type="grant_retired",
        actor_type="human",
        actor_id=human.human_id,
        # The venture when they share one, NULL when they do not - rather than picking
        # the first, which would file the act under a venture it was only half about.
        venture_id=(
            found[0]["venture_id"]
            if len({r["venture_id"] for r in found}) == 1
            else None
        ),
        subject={
            "human": human.display_name,
            "reason": reason.strip(),
            # Named individually. "2 grants" is not something a reader can check.
            "grants": [
                {
                    "grant_id": r["grant_id"],
                    "agent": r["agent_name"],
                    "venture_id": r["venture_id"],
                    "module": f"{r['forge_id']}/{r['module_id']}",
                    "origin": r["origin"],
                }
                for r in found
            ],
        },
    )
    return found


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
