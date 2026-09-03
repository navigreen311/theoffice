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

from broker import audit, certification, humans, roster, shifts

#: Phase 0.8 names CRE Forge specifically. Not a parameter: this command exists to make
#: one documented call happen, and a general-purpose grant issuer is exactly the thing
#: the provisioning ladder is for.
FORGE_ID = "cre-forge"
MODULE_ID = "property_lookup"

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
TIER = "auto_execute"

#: A marker on every row and audit entry this command writes.
BOOTSTRAP = "phase0.8"


class BootstrapError(Exception):
    """The bootstrap could not run, and nothing was written."""


async def _one_agent(conn: AsyncConnection, ref: str | None) -> dict[str, Any]:
    """The agent to put on the path.

    Named explicitly when `ref` is given. Otherwise the lowest-ranked active agent in
    engineering, because the first agent across a new bridge should be the one whose
    authority is smallest.
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
                "WHERE status = 'active' AND department = 'engineering' "
                "  AND role_key = 'individual_contributor' "
                "ORDER BY village_agent_ref LIMIT 1"
            )
        row = await cur.fetchone()

    if row is None:
        raise BootstrapError(
            f"no active Village agent {'matching ' + ref if ref else 'in engineering'}. "
            "Run `python -m broker sync-roster --confirm` first: The Office cannot "
            "appoint an agent the Village has never reported."
        )
    return dict(row)


async def _already_granted(
    conn: AsyncConnection, office_agent_id: uuid.UUID
) -> uuid.UUID | None:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT grant_id FROM agent_forge_grant "
            "WHERE office_agent_id = %s AND forge_id = %s AND module_id = %s "
            "  AND revoked_at IS NULL",
            (office_agent_id, FORGE_ID, MODULE_ID),
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def plan(conn: AsyncConnection, *, ref: str | None = None) -> dict[str, Any]:
    """What the bootstrap would do. Writes nothing."""
    agent = await _one_agent(conn, ref)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT api_version, base_url, health_status FROM forge_registry "
            "WHERE forge_id = %s",
            (FORGE_ID,),
        )
        forge = await cur.fetchone()
        await cur.execute(
            "SELECT credential_ref FROM forge_tenant_credential WHERE forge_id = %s",
            (FORGE_ID,),
        )
        credential = await cur.fetchone()
        await cur.execute(
            "SELECT office_agent_id FROM office_agent_identity "
            "WHERE village_agent_ref = %s",
            (agent["village_agent_ref"],),
        )
        identity = await cur.fetchone()

    if forge is None:
        raise BootstrapError(f"{FORGE_ID} is not in forge_registry")
    if credential is None:
        raise BootstrapError(
            f"{FORGE_ID} has no row in forge_tenant_credential, so the broker has no "
            "credential to inject. The call would be unauthenticated."
        )

    return {
        "agent": agent,
        "forge": dict(forge),
        "credential_ref": credential["credential_ref"],
        "identity_exists": identity is not None,
        "forge_id": FORGE_ID,
        "module_id": MODULE_ID,
        "tier": TIER,
    }


async def apply(
    conn: AsyncConnection,
    *,
    human: humans.Human,
    venture_id: str,
    ref: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Issue the identity, certifications, grant and shift. Refuses without confirmation."""
    if not confirmed:
        raise BootstrapError(
            "bootstrap-phase0 issues authority to an agent and will not run without "
            "--confirm. Run it without the flag first to see what it would do."
        )

    detail = await plan(conn, ref=ref)
    agent = detail["agent"]
    forge = detail["forge"]
    department = agent["department"]

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

    existing = await _already_granted(conn, office_agent_id)
    if existing is not None:
        raise BootstrapError(
            f"{agent['agent_name']} already holds a live grant for "
            f"{FORGE_ID}/{MODULE_ID} ({existing}). Nothing was written. Revoke it first "
            "if you mean to re-issue: a command that silently re-issues authority is a "
            "command somebody runs twice."
        )

    # The hash a certification is earned against. Real instructions have a content hash;
    # this names the bootstrap so staleness has something concrete to compare and the
    # certification cannot be permanent by accident.
    instruction_hash = hashlib.sha256(
        f"{BOOTSTRAP}:{FORGE_ID}:{MODULE_ID}:{forge['api_version']}".encode()
    ).hexdigest()

    # 2. Unit B - the department is certified for this Forge.
    unit_b = await certification.record_result(
        conn, unit="B", forge_id=FORGE_ID, department=department,
        verdict="PASS", rubric_version=BOOTSTRAP, certified_tier=TIER,
        instruction_content_hash=instruction_hash,
        forge_api_version=forge["api_version"],
        # Not a SimForge verdict, and it no longer says it is. These two rows
        # carried `simforge_verdict = 'PASS'` against no scenario run until
        # 3 September 2026, which was a false statement in the column that exists
        # to record whether SimForge ran.
        attested_by="bootstrap",
        bootstrap_reason=(
            "Phase 0.8. Issued outside the provisioning ladder so the first real "
            "brokered call could be made. No SimForge scenario pack existed for "
            "cre-forge when this was written."
        ),
    )

    # 3. Unit A - this agent is certified for this module.
    unit_a = await certification.record_result(
        conn, unit="A", forge_id=FORGE_ID, module_id=MODULE_ID,
        office_agent_id=office_agent_id,
        verdict="PASS", rubric_version=BOOTSTRAP, certified_tier=TIER,
        instruction_content_hash=instruction_hash,
        forge_api_version=forge["api_version"],
        # Not a SimForge verdict, and it no longer says it is. These two rows
        # carried `simforge_verdict = 'PASS'` against no scenario run until
        # 3 September 2026, which was a false statement in the column that exists
        # to record whether SimForge ran.
        attested_by="bootstrap",
        bootstrap_reason=(
            "Phase 0.8. Issued outside the provisioning ladder so the first real "
            "brokered call could be made. No SimForge scenario pack existed for "
            "cre-forge when this was written."
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
            (grant_id, office_agent_id, FORGE_ID, MODULE_ID, venture_id, TIER,
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
            (venture_id, FORGE_ID, MODULE_ID),
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
            "forge_id": FORGE_ID,
            "module_id": MODULE_ID,
            "trust_tier": TIER,
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
        "forge_id": FORGE_ID,
        "module_id": MODULE_ID,
        "trust_tier": TIER,
    }
