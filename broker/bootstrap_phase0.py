"""Phase 0.8 — put one agent on the path, once, so a real call can be made.

Phase 0 of the build blueprint is called The Bridge, and its note reads "the only thing
here that has never been proven possible". 0.8 is the end of it: *one agent, one CRE
Forge module, one authenticated call, one ledger row naming that agent.*

WHY A BOOTSTRAP AND NOT THE LADDER
==================================

    Grants are written in exactly one place in normal operation - `runtime_config.apply`,
    at the end of the sixteen-gate provisioning ladder, after a Pack, human sign-offs and
    SimForge certifications. That ladder is Phase 2 and 3 machinery. Phase 0 predates it
    and exists to answer a narrower question: does the call path work at all.

    Every provisioning run in this database is `aborted` and the call ledger has never
    held a row. Requiring the full ladder to answer "can an agent call a Forge" makes the
    first proof depend on everything built after it.

    So this issues the minimum: one identity, two certifications, one grant, one shift.
    It uses the real functions for each - `roster.issue_identity`,
    `certification.record_result` - rather than writing the rows itself, so a bootstrapped
    row is the same shape as an earned one and nothing downstream has to know which it is.

RESUMABLE, NOT ATOMIC
=====================

    The five writes commit separately, because they go through four modules that each
    own their own transaction. That is safe here only because every partial state is
    inert: an identity grants nothing, certifications without a grant grant nothing, and
    a grant without a shift is refused by `assert_on_shift_for`. No ordering of these
    writes leaves an agent able to call something it should not, so a failed run can be
    re-run rather than needing one transaction spanning four modules.

    This is a weaker guarantee than `sync-roster`'s, and it is weaker on purpose: there
    the half-written state was an agent marked departed while still holding live
    authority, which is not inert at all.

WHAT IT DOES NOT DO
===================

    It does not weaken a control. The grant it writes is subject to every check the call
    path makes: certification state, revocation, shift, budget, tier cap. If any of those
    refuse the call, that is the correct outcome and the bridge is not built.

    It is not idempotent by accident either - it refuses to run when the agent already
    holds a grant for this module, because a command that silently re-issues authority is
    a command somebody will run twice.

EVERY ROW SAYS IT WAS BOOTSTRAPPED
==================================

    Five audit entries, each naming the human who ran it, and each carrying
    `bootstrap: true` in its subject. A grant nobody can distinguish from an earned one
    is a grant that will be cited as evidence that the ladder was followed.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import audit, certification, errors, humans, revocation, roster, shifts

#: Phase 0.8 names CRE Forge specifically. Not a parameter: this command exists to make
#: one documented call happen, and a general-purpose grant issuer is exactly the thing
#: the provisioning ladder is for.
#: The pair this command was written for, now a DEFAULT rather than a constant.
#:
#: They were never a rule. Phase 0.8 had one venture, one bridged Forge and one registered
#: module, so an author's convenience and a scope constraint looked identical - and stayed
#: identical for as long as there was only one venture to tell them apart.
#:
#: **Removing them removes the only thing that scoped this tool**, which is why
#: `_assert_pair_in_pack` exists. `record_result` has always been generic; `attested_by='bootstrap'`
#: has always demanded a reason and written `simforge_verdict = NULL`. What was missing was never
#: a guard on the writer - it was a way for a documented mechanism to name a venture it was not
#: parameterised for. The Pack is what says which pairs a venture may bootstrap, and it says so
#: already, in `positions_required`.
DEFAULT_FORGE_ID = "cre-forge"
DEFAULT_MODULE_ID = "property_lookup"

#: `auto_execute`, because nothing below it reaches a Forge at all.
#:
#: The first version of this file said `suggest` was "the weakest tier that still
#: permits a call". That was wrong, and the call path is explicit about it: step 7 of
#: the client library turns anything below `auto_execute` into a proposal and makes no
#: Forge call. A Phase 0.8 grant at `suggest` would produce a proposal row and prove
#: nothing about the bridge.
#:
#: `property_lookup` is a search over CRE Forge's property table. It is registered
#: `is_mutating` in forge_module_registry, which is worth questioning separately, but
#: the operation itself reads.
#: Fallback only, for the no-venture path. **The tier comes from the Pack.**
#:
#: It was a constant, and that made every bootstrap grant `auto_execute` regardless of what the
#: position declared - 20 of 21 grants in this database, against five positions that every one of
#: them declares `propose`. Inert only because no shift existed: `assert_on_shift_for` refuses the
#: call, so nothing had used the extra tier. That is a safety net catching it, not a reason it was
#: safe. A bootstrap certifies an agent for work a position defines; issuing it above the ceiling
#: that position declared is authority the Pack did not ask for.
DEFAULT_TIER = "auto_execute"

#: A marker on every row and audit entry this command writes.
BOOTSTRAP = "phase0.8"


class BootstrapError(Exception):
    """The bootstrap could not run, and nothing was written."""


async def _one_agent(
    conn: AsyncConnection, ref: str | None, department: str = "engineering"
) -> dict[str, Any]:
    """The agent to put on the path.

    Named explicitly when `ref` is given. Otherwise the lowest-ranked active agent in
    `department`, because the first agent across a new bridge should be the one whose
    authority is smallest.

    **The department moved; the rank filter did not.** `role_key = 'individual_contributor'`
    is the safety property in this selection and it holds for every department - a bootstrap
    that reached for a department head when asked for a new department would be answering a
    question about scope with a change of authority.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        if ref:
            await cur.execute(
                "SELECT village_agent_ref, agent_name, department, role_key "
                "FROM village_agent WHERE village_agent_ref = %s AND status = 'active'",
                (ref,),
            )
        else:
            await cur.execute(
                "SELECT village_agent_ref, agent_name, department, role_key "
                "FROM village_agent "
                "WHERE status = 'active' AND department = %s "
                "  AND role_key = 'individual_contributor' "
                "ORDER BY village_agent_ref LIMIT 1",
                (department,),
            )
        row = await cur.fetchone()

    if row is None:
        raise BootstrapError(
            f"no active Village agent {'matching ' + ref if ref else 'in ' + department}. "
            "Run `python -m broker sync-roster --confirm` first: The Office cannot "
            "appoint an agent the Village has never reported."
        )
    return dict(row)


async def _assert_pair_in_pack(
    conn: AsyncConnection, *, venture_id: str, forge_id: str, module_id: str,
    department: str | None,
) -> str | None:
    """Refuse a pair the venture's live Pack does not ask for. Loudly, and never a warning.

    **This is what the constants used to do.** While `cre-forge/property_lookup` was hardcoded
    the tool could only ever certify the one pair its author had checked by hand. Taking
    `--forge` and `--module` removes that, and removing it without putting something in its
    place would turn a bootstrap into a way to certify anything for anyone - which is the
    difference between generalising a mechanism and loosening it.

    The Pack is the right authority and needs no new one: `positions_required` already declares
    every module each position operates, and Gate 4.5 appoints against exactly that list. So a
    pair this refuses is a pair that could never have filled a position anyway, and a warning
    would mean writing an unearned certification that no gate will ever read.

    Three separate refusals, because they are three different mistakes and collapsing them
    would tell the operator to fix the wrong one.

    **Returns the trust tier the Pack declares for this pair**, which is the other half of the
    same idea: if the Pack is the authority on WHICH pairs may be bootstrapped, it is the
    authority on AT WHAT TIER. The weakest ceiling wins where more than one position operates
    the module, because a certification is per (agent, forge, module) and cannot distinguish
    which position an agent will be appointed to.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT p->>'position_title' AS title, p->>'source_department' AS department, "
            "       p->>'trust_tier_ceiling' AS ceiling "
            "FROM business_pack b, jsonb_array_elements(b.parsed->'positions_required') p "
            "WHERE b.venture_id = %s AND b.status = 'live' "
            "  AND p->'forge_modules_operated' ? %s",
            (venture_id, module_id),
        )
        positions = [dict(r) for r in await cur.fetchall()]
        await cur.execute(
            "SELECT forge_id FROM forge_module_registry WHERE module_id = %s", (module_id,)
        )
        registered = await cur.fetchone()

    if not positions:
        raise BootstrapError(
            f"{venture_id}'s live Pack has no position operating {module_id!r}. Nothing was "
            "written. A certification for a module no position operates is a row Gate 4.5 "
            "will never read - the Pack decides what this venture may bootstrap, and it does "
            "not ask for this."
        )
    if registered is None:
        raise BootstrapError(f"{module_id!r} is not in forge_module_registry.")
    if registered["forge_id"] != forge_id:
        raise BootstrapError(
            f"{module_id!r} belongs to {registered['forge_id']!r}, not {forge_id!r}. Unit A is "
            "agent x forge x module, so a certification under the wrong Forge certifies "
            "nothing and matches no position."
        )
    if department is not None and department not in {p["department"] for p in positions}:
        asked = sorted({p["department"] for p in positions})
        raise BootstrapError(
            f"no position operating {module_id!r} draws from {department!r}. The Pack draws it "
            f"from {', '.join(asked)}. Unit B is certified per (department, Forge), so a "
            "certification in the wrong department is invisible to every position that needs it."
        )

    relevant = [p for p in positions if department is None or p["department"] == department]
    ceilings = [p["ceiling"] for p in relevant if p["ceiling"]]
    if not ceilings:
        raise BootstrapError(
            f"no position operating {module_id!r} declares a trust_tier_ceiling. The tier is the "
            "Pack's to state and this command will not choose one for it."
        )
    return str(min(ceilings, key=lambda t: certification.TIER_RANK[t]))


async def _already_granted(
    conn: AsyncConnection, office_agent_id: uuid.UUID, *, forge_id: str, module_id: str,
    venture_id: str,
) -> uuid.UUID | None:
    """A LIVE grant for this pair, or None.

    **A revoked grant is not a live one, and this used to say it was.** The guard asked whether
    a row existed; `agent_forge_grant` has no `revoked_at` (B37 dropped it, deliberately - there
    is one place revocation is recorded and it is the `revocation` table), so a revoked grant
    went on blocking re-issue forever with no way to clear it short of deleting the row. That
    turns "revoke it first if you mean to re-issue" into advice that cannot be taken.

    `check_revocations` is the same authority the call path uses per call, so the guard and the
    runtime now agree on what "granted" means rather than each keeping its own answer.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT grant_id FROM agent_forge_grant "
            "WHERE office_agent_id = %s AND forge_id = %s AND module_id = %s",
            (office_agent_id, forge_id, module_id),
        )
        row = await cur.fetchone()
    if row is None:
        return None

    try:
        await revocation.check_revocations(
            conn, office_agent_id=office_agent_id, forge_id=forge_id,
            module_id=module_id, venture_id=venture_id,
        )
    except errors.Revoked as exc:
        # Loud rather than silent. Re-issuing over a revocation is legitimate - it is what a
        # revoke-then-reissue repair IS - but it is somebody undoing a deliberate act, and the
        # operator should see that they are doing it.
        print(f"  re-issuing over a revoked grant ({row[0]}): {exc}")
        return None
    return uuid.UUID(str(row[0]))


async def plan(
    conn: AsyncConnection, *, ref: str | None = None,
    forge_id: str = DEFAULT_FORGE_ID, module_id: str = DEFAULT_MODULE_ID,
    department: str = "engineering", venture_id: str | None = None,
) -> dict[str, Any]:
    """What the bootstrap would do. Writes nothing.

    The Pack check runs HERE, not only in `apply`, so that the dry run refuses a pair the
    venture cannot bootstrap. A plan that reports a write `--confirm` would then reject is a
    plan that taught the operator the wrong thing.
    """
    tier = DEFAULT_TIER
    if venture_id is not None:
        tier = await _assert_pair_in_pack(
            conn, venture_id=venture_id, forge_id=forge_id, module_id=module_id,
            department=None if ref else department,
        ) or DEFAULT_TIER
    agent = await _one_agent(conn, ref, department)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT api_version, base_url, health_status FROM forge_registry "
            "WHERE forge_id = %s",
            (forge_id,),
        )
        forge = await cur.fetchone()
        await cur.execute(
            "SELECT credential_ref FROM forge_tenant_credential WHERE forge_id = %s",
            (forge_id,),
        )
        credential = await cur.fetchone()
        await cur.execute(
            "SELECT office_agent_id FROM office_agent_identity "
            "WHERE village_agent_ref = %s",
            (agent["village_agent_ref"],),
        )
        identity = await cur.fetchone()

    if forge is None:
        raise BootstrapError(f"{forge_id} is not in forge_registry")
    if credential is None:
        raise BootstrapError(
            f"{forge_id} has no row in forge_tenant_credential, so the broker has no "
            "credential to inject. The call would be unauthenticated."
        )

    return {
        "agent": agent,
        "forge": dict(forge),
        "credential_ref": credential["credential_ref"],
        "identity_exists": identity is not None,
        "forge_id": forge_id,
        "module_id": module_id,
        "tier": tier,
    }


async def apply(
    conn: AsyncConnection,
    *,
    human: humans.Human,
    venture_id: str,
    ref: str | None = None,
    forge_id: str = DEFAULT_FORGE_ID,
    module_id: str = DEFAULT_MODULE_ID,
    department: str = "engineering",
    confirmed: bool = False,
) -> dict[str, Any]:
    """Issue the identity, certifications, grant and shift. Refuses without confirmation."""
    if not confirmed:
        raise BootstrapError(
            "bootstrap-phase0 issues authority to an agent and will not run without "
            "--confirm. Run it without the flag first to see what it would do."
        )

    detail = await plan(
        conn, ref=ref, forge_id=forge_id, module_id=module_id, department=department,
        venture_id=venture_id,
    )
    agent = detail["agent"]
    forge = detail["forge"]
    department = agent["department"]
    # Re-checked against the agent's OWN department. `plan` could only test the requested one,
    # and `--agent` bypasses the request entirely: naming an engineer for an administration
    # module would otherwise write a unit-B row for `engineering` that no position can use.
    # This re-check, not `plan`'s, is what sets the tier: `--agent` can name someone from a
    # different department than the one requested, and the tier follows the position that will
    # actually appoint them.
    tier = await _assert_pair_in_pack(
        conn, venture_id=venture_id, forge_id=forge_id, module_id=module_id,
        department=department,
    ) or DEFAULT_TIER

    # 1. Identity. The real function, which refuses an agent the Village never reported.
    #
    # Resumable rather than atomic, and deliberately. Each step of this bootstrap commits
    # on its own, so a failure part-way leaves the earlier steps standing - but every one
    # of those partial states is inert: an identity grants nothing, certifications
    # without a grant grant nothing, and a grant without a shift is refused by
    # `assert_on_shift_for`. There is no ordering of these five writes that leaves an
    # agent able to call something it should not, so the command is safe to re-run rather
    # than needing one transaction across four modules.
    #
    # `issue_identity` refuses an agent that already holds one, which would make a retry
    # fail on step one, so an existing identity is adopted here instead.
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT office_agent_id FROM office_agent_identity "
            "WHERE village_agent_ref = %s",
            (agent["village_agent_ref"],),
        )
        row = await cur.fetchone()

    if row is not None:
        office_agent_id = row[0]
        print(
            f"  identity already issued for {agent['agent_name']}, continuing from there"
        )
    else:
        office_agent_id = await roster.issue_identity(
            conn, agent["village_agent_ref"], human=human
        )

    existing = await _already_granted(
        conn, office_agent_id, forge_id=forge_id, module_id=module_id, venture_id=venture_id
    )
    if existing is not None:
        raise BootstrapError(
            f"{agent['agent_name']} already holds a live grant for "
            f"{forge_id}/{module_id} ({existing}). Nothing was written. Revoke it first "
            "if you mean to re-issue: a command that silently re-issues authority is a "
            "command somebody runs twice."
        )

    # The hash a certification is earned against. **The live instruction's, when there is
    # one** - anything else is a certification bound to text that does not exist.
    #
    # This used to be unconditional:
    #
    #     sha256(f"{BOOTSTRAP}:{forge_id}:{module_id}:{api_version}")
    #
    # a hash of a LABEL, not of any instruction. It was written when CapitalForge had no
    # authored instructions at all, and it was defensible then and only then. The moment one
    # exists, `recompute_staleness` compares the cert's hash against the live `content_hash`,
    # they cannot match, and **every certification this command wrote goes
    # `stale_instructions` on the next sweep.** Not a risk - arithmetic.
    #
    # Its own docstring says why the no-instruction case must not be quietly treated as fresh:
    # *"NO LIVE INSTRUCTION IS STALE, NOT FRESH"* - a cert bound to a hash corresponding to no
    # text cannot be said to match anything, and `resolve_grant` dispatches on `state =
    # 'certified'`. So the fallback stays, it stays honest about being a fallback, and the
    # reason on the row says which of the two happened.
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT content_hash FROM forge_operating_instruction "
            "WHERE forge_id = %s AND module_id = %s AND superseded_at IS NULL",
            (forge_id, module_id),
        )
        live_instruction = await cur.fetchone()

    if live_instruction is not None:
        instruction_hash = live_instruction["content_hash"]
        basis = (
            f"Bound to the live operating instruction for {forge_id}/{module_id} "
            f"(content_hash {instruction_hash[:12]}), so staleness is computable against the "
            "text this agent was certified on."
        )
    else:
        instruction_hash = hashlib.sha256(
            f"{BOOTSTRAP}:{forge_id}:{module_id}:{forge['api_version']}".encode()
        ).hexdigest()
        basis = (
            f"NO operating instruction is authored for {forge_id}/{module_id}, so this is "
            "bound to a synthetic hash naming the bootstrap. It matches no text and will be "
            "marked stale by the first staleness sweep after one is authored - which is the "
            "correct outcome, not a defect to work around."
        )

    # 2. Unit B - the department is certified for this Forge.
    unit_b = await certification.record_result(
        conn, unit="B", forge_id=forge_id, department=department,
        verdict="PASS", rubric_version=BOOTSTRAP, certified_tier=tier,
        instruction_content_hash=instruction_hash,
        forge_api_version=forge["api_version"],
        # Not a SimForge verdict, and it no longer says it is. These two rows
        # carried `simforge_verdict = 'PASS'` against no scenario run until
        # 3 September 2026, which was a false statement in the column that exists
        # to record whether SimForge ran.
        attested_by="bootstrap",
        bootstrap_reason=(
            f"Phase 0.8. Issued outside the provisioning ladder because Gate 4.5 requires a "
            f"certification and no gate produces one. No SimForge scenario pack had been run "
            f"for {department} on {forge_id} when this was written. Unit B is certified per "
            f"(department, Forge), so this row covers every {forge_id} module that department "
            f"operates - it is not per-module and must not be read as one. {basis}"
        ),
    )

    # 3. Unit A - this agent is certified for this module.
    unit_a = await certification.record_result(
        conn, unit="A", forge_id=forge_id, module_id=module_id,
        office_agent_id=office_agent_id,
        verdict="PASS", rubric_version=BOOTSTRAP, certified_tier=tier,
        instruction_content_hash=instruction_hash,
        forge_api_version=forge["api_version"],
        # Not a SimForge verdict, and it no longer says it is. These two rows
        # carried `simforge_verdict = 'PASS'` against no scenario run until
        # 3 September 2026, which was a false statement in the column that exists
        # to record whether SimForge ran.
        attested_by="bootstrap",
        bootstrap_reason=(
            f"Phase 0.8. Issued outside the provisioning ladder because Gate 4.5 requires a "
            f"certification and no gate produces one. No SimForge scenario pack had been run "
            f"for {forge_id}/{module_id} when this was written. {basis}"
        ),
    )

    # 4. The grant, activated, carrying both certification ids. `is_assignable` is a
    # generated column over exactly these fields, so a grant missing one of them is
    # visibly not assignable rather than quietly half-issued.
    grant_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO agent_forge_grant
              (grant_id, office_agent_id, forge_id, module_id, venture_id, trust_tier,
               operation_cert_ref, dept_context_cert_ref, granted_by,
               activated_at, activated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
            """,
            (grant_id, office_agent_id, forge_id, module_id, venture_id, tier,
             str(unit_a.cert_id), str(unit_b.cert_id), human.human_id, human.human_id),
        )
        # The venture has to declare the module it uses. Step 4 of the call path raises
        # ManifestViolation and a HIGH incident on an undeclared module, before the tier
        # gate and regardless of what the caller holds - so a grant without a manifest
        # row is a grant whose every call is a violation.
        await cur.execute(
            """
            INSERT INTO venture_forge_manifest
              (venture_id, forge_id, module_id, is_required, criticality)
            VALUES (%s, %s, %s, TRUE, 'hard')
            ON CONFLICT (venture_id, forge_id, module_id) DO UPDATE
            SET is_required = EXCLUDED.is_required
            """,
            (venture_id, forge_id, module_id),
        )
    await conn.commit()

    await audit.write_event(
        event_type="grant_issued",
        actor_type="human",
        actor_id=human.human_id,
        venture_id=venture_id,
        subject={
            "bootstrap": True,
            "phase": BOOTSTRAP,
            "grant_id": str(grant_id),
            "office_agent_id": str(office_agent_id),
            "agent_name": agent["agent_name"],
            "forge_id": forge_id,
            "module_id": module_id,
            "trust_tier": tier,
            "operation_cert_ref": str(unit_a.cert_id),
            "dept_context_cert_ref": str(unit_b.cert_id),
            "why": (
                "Phase 0.8 bootstrap. Issued outside the provisioning ladder to make "
                "the first real call possible; not evidence that the ladder was run."
            ),
        },
    )

    # 5. A shift, so the agent is on shift for this venture when the call arrives.
    # `assign_shift` reads the quarter from the Village itself.
    #
    # An existing current shift is adopted rather than added to. The schema forbids
    # overlapping shifts per agent, so a re-run would otherwise fail here having already
    # written the grant - and a second shift is not what a retry means anyway.
    current = await shifts.current_shift(conn, office_agent_id)
    if current is not None and current["venture_id"] == venture_id:
        shift_id = current["shift_id"]
        print(f"  already on shift for {venture_id}, continuing from there")
    else:
        now = datetime.now(UTC)
        shift_id = await shifts.assign_shift(
            conn,
            office_agent_id=office_agent_id,
            venture_id=venture_id,
            shift_start=now - timedelta(minutes=1),
            shift_end=now + timedelta(hours=8),
            assigned_by=human.human_id,
        )

    return {
        "office_agent_id": str(office_agent_id),
        "agent_name": agent["agent_name"],
        "village_agent_ref": agent["village_agent_ref"],
        "department": department,
        "grant_id": str(grant_id),
        "unit_a_cert": str(unit_a.cert_id),
        "unit_b_cert": str(unit_b.cert_id),
        "shift_id": str(shift_id),
        "venture_id": venture_id,
        "forge_id": forge_id,
        "module_id": module_id,
        "trust_tier": tier,
    }
