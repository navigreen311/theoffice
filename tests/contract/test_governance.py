"""Phase 1 acceptance — governance enforced in the call path.

Blueprint acceptance, verbatim: "an agent at `propose` tier cannot execute — the call
produces a proposal, not a Forge action. An `UNDECLARED` call raises a HIGH incident
and throttles. Exceeding the per-task ceiling halts that task."

Every test here asserts `stub_forge.call_count`. A governance gate that raises the
right exception while still reaching the Forge has failed at the only thing it exists
to do, and an exception-only assertion would not notice.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from broker import budget, limits, proposals, revocation
from broker.db import connection
from broker.errors import (
    BudgetExceeded,
    ManifestViolation,
    NotAuthorized,
    RateLimited,
    RequiresApproval,
    Revoked,
)
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

IVAN = uuid.uuid4()


# ------------------------------------------------------------------ revocation

@pytest.mark.parametrize(
    ("scope", "role"),
    [
        ("agent_module", "venture_operator"),
        ("agent", "venture_operator"),
        ("venture", "compliance_officer"),
        ("forge", "ivan"),
    ],
)
async def test_each_revocation_scope_blocks_the_next_call(
    office, stub_forge, agent_ctx, granted_agent, declare_module, scope, role
):
    """G1-G4 — all four scopes from master prompt §1.4."""
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)

    first = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert first.status_code == 200

    targets = {
        "agent_module": {"office_agent_id": agent_id, "forge_id": forge_id,
                         "module_id": module_id},
        "agent": {"office_agent_id": agent_id},
        "venture": {"venture_id": agent_ctx.venture_id},
        "forge": {"forge_id": forge_id},
    }[scope]

    async with connection() as conn:
        await revocation.revoke(
            conn, scope=scope, reason="test", revoked_by=IVAN,
            revoked_by_role=role, **targets,
        )

    with pytest.raises(Revoked) as exc:
        await office.call(forge_id, module_id, {"n": 2}, agent_ctx=agent_ctx)

    assert exc.value.context["scope"] == scope
    assert stub_forge.call_count == 1, "the Forge must not have been contacted"


@pytest.mark.parametrize(
    ("scope", "insufficient_role"),
    [("venture", "venture_operator"), ("forge", "venture_operator"),
     ("forge", "compliance_officer")],
)
def test_revocation_requires_the_right_authority(scope, insufficient_role):
    """G5 — a venture operator cannot revoke a Forge out from under everyone."""
    with pytest.raises(NotAuthorized):
        revocation.assert_authority(scope, insufficient_role)


def test_stronger_role_may_act_at_a_weaker_scope():
    """Ivan revoking one grant is not an authority error."""
    revocation.assert_authority("agent_module", "ivan")
    revocation.assert_authority("agent", "compliance_officer")


async def test_reinstatement_requires_a_named_human_and_a_reason(
    office, agent_ctx, granted_agent
):
    """G6 — §1.4: re-enable requires a documented ritual and a named human."""
    agent_id, _forge_id, _ = granted_agent
    async with connection() as conn:
        rev_id = await revocation.revoke(
            conn, scope="agent", reason="test", revoked_by=IVAN,
            revoked_by_role="venture_operator", office_agent_id=agent_id,
        )
        with pytest.raises(NotAuthorized):
            await revocation.reinstate(
                conn, revocation_id=rev_id, reinstated_by=IVAN,
                reinstated_by_role="venture_operator", reason="   ",
            )


async def test_reinstatement_restores_the_next_call(
    office, stub_forge, agent_ctx, granted_agent, declare_module
):
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)
    async with connection() as conn:
        rev_id = await revocation.revoke(
            conn, scope="agent", reason="suspected compromise", revoked_by=IVAN,
            revoked_by_role="venture_operator", office_agent_id=agent_id,
        )
    with pytest.raises(Revoked):
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    async with connection() as conn:
        await revocation.reinstate(
            conn, revocation_id=rev_id, reinstated_by=IVAN,
            reinstated_by_role="venture_operator",
            reason="investigated; false positive, see INC-1",
        )

    result = await office.call(forge_id, module_id, {"n": 2}, agent_ctx=agent_ctx)
    assert result.status_code == 200


async def test_venture_revocation_applies_to_a_grant_issued_afterwards(
    office, stub_forge, agent_ctx, granted_agent, admin, seed_forge
):
    """G7 — the reason revocation is a table and not a column on the grant.

    A venture-wide stop must cover grants that did not exist when it was declared.
    Stored on the grant, this case is silently missed.
    """
    agent_id, forge_id, module_id = granted_agent
    async with connection() as conn:
        await revocation.revoke(
            conn, scope="venture", reason="compliance hold", revoked_by=IVAN,
            revoked_by_role="compliance_officer", venture_id=agent_ctx.venture_id,
        )

    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_forge_grant
              (grant_id, office_agent_id, forge_id, module_id, venture_id, trust_tier,
               operation_cert_ref, dept_context_cert_ref, granted_by,
               activated_at)
            VALUES (%s, %s, %s, %s, %s, 'auto_execute', 'a', 'b', %s, now())
            """,
            (str(uuid.uuid4()), agent_id, forge_id, module_id,
             agent_ctx.venture_id, str(IVAN)),
        )
    admin.commit()

    with pytest.raises(Revoked) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert exc.value.context["scope"] == "venture"
    assert stub_forge.call_count == 0


# -------------------------------------------------------------------- manifest

async def test_required_module_proceeds_and_ledgers_required(
    office, stub_forge, agent_ctx, granted_agent, declare_module, app_dsn
):
    """G8 — the manifest happy path."""
    _, forge_id, module_id = granted_agent
    declare_module(required=True)

    result = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert result.manifest_match == "required"
    assert stub_forge.call_count == 1


async def test_declared_but_not_required_proceeds_with_a_high_incident(
    office, stub_forge, agent_ctx, granted_agent, declare_module, incidents_for
):
    """G9 — IN_USE_NOT_REQUIRED.

    Proceeds because the venture *did* declare it; the incident records that
    nothing required it. Blocking here would make a Pack's own declarations
    meaningless.
    """
    _, forge_id, module_id = granted_agent
    declare_module(required=False)

    result = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert result.manifest_match == "declared_only"
    assert stub_forge.call_count == 1
    raised = incidents_for(agent_ctx.venture_id)
    assert ("HIGH", "in_use_not_required") in raised


async def test_undeclared_module_is_blocked_with_a_high_incident_and_throttle(
    office, stub_forge, agent_ctx, granted_agent, incidents_for
):
    """G10 — blueprint acceptance criterion 2, all three effects."""
    agent_id, forge_id, module_id = granted_agent
    # No manifest row declared at all.

    with pytest.raises(ManifestViolation):
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert stub_forge.call_count == 0, "an undeclared call must not reach the Forge"
    assert ("HIGH", "undeclared_forge_call") in incidents_for(agent_ctx.venture_id)

    state = await limits.bucket_state(agent_id)
    assert state is not None
    assert float(state["throttle_factor"]) < 1.0, "the agent must be throttled"
    assert state["throttled_until"] is not None


# ------------------------------------------------------------------ trust tier

@pytest.mark.parametrize("tier", ["propose", "suggest"])
async def test_below_auto_execute_creates_a_proposal_and_no_forge_call(
    office, stub_forge, agent_ctx, granted_agent, declare_module, admin, tier
):
    """G11/G12 — blueprint acceptance criterion 1."""
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE agent_forge_grant SET trust_tier = %s WHERE office_agent_id = %s",
            (tier, agent_id),
        )
    admin.commit()

    with pytest.raises(RequiresApproval) as exc:
        await office.call(forge_id, module_id, {"amount": 5000}, agent_ctx=agent_ctx)

    assert stub_forge.call_count == 0, "a proposal is not a Forge action"

    async with connection() as conn:
        row = await proposals.get(conn, uuid.UUID(str(exc.value.proposal_id)))
    assert row is not None
    assert row["status"] == "pending"
    assert row["trust_tier"] == tier
    assert row["payload"] == {"amount": 5000}, "a human must be able to inspect it"


async def test_approving_a_proposal_records_the_decision(
    office, agent_ctx, granted_agent, declare_module, admin
):
    """G13 — the proposal lifecycle, and that a decision names a human."""
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE agent_forge_grant SET trust_tier = 'propose' WHERE office_agent_id = %s",
            (agent_id,),
        )
    admin.commit()

    with pytest.raises(RequiresApproval) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    proposal_id = uuid.UUID(str(exc.value.proposal_id))

    async with connection() as conn:
        decided = await proposals.decide(
            conn, proposal_id=proposal_id, approve=True, decided_by=IVAN,
            reason="reviewed the statement, amount is correct",
        )
        assert decided.status == "approved"

        await proposals.mark_executed(conn, proposal_id=proposal_id, call_id=uuid.uuid4())
        row = await proposals.get(conn, proposal_id)
    assert row is not None
    assert row["status"] == "executed"
    assert row["decided_by"] == IVAN


async def test_rejected_proposal_cannot_be_marked_executed(
    office, agent_ctx, granted_agent, declare_module, admin
):
    """A second code path must not be able to run something a human rejected."""
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE agent_forge_grant SET trust_tier = 'propose' WHERE office_agent_id = %s",
            (agent_id,),
        )
    admin.commit()

    with pytest.raises(RequiresApproval) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    proposal_id = uuid.UUID(str(exc.value.proposal_id))

    async with connection() as conn:
        await proposals.decide(
            conn, proposal_id=proposal_id, approve=False, decided_by=IVAN,
            reason="wrong account",
        )
        with pytest.raises(LookupError):
            await proposals.mark_executed(
                conn, proposal_id=proposal_id, call_id=uuid.uuid4()
            )


async def test_sub_five_second_approval_raises_a_governance_flag(
    office, agent_ctx, granted_agent, declare_module, admin, incidents_for
):
    """G14 — Part 14 rubber-stamp detection.

    A trust tier that is really a click-through is worse than no tier, because it
    looks like oversight.
    """
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE agent_forge_grant SET trust_tier = 'propose' WHERE office_agent_id = %s",
            (agent_id,),
        )
    admin.commit()

    with pytest.raises(RequiresApproval) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    async with connection() as conn:
        await proposals.decide(
            conn, proposal_id=uuid.UUID(str(exc.value.proposal_id)),
            approve=True, decided_by=IVAN, reason="ok",
        )

    assert ("MEDIUM", "rubber_stamp_approval") in incidents_for(agent_ctx.venture_id)


def test_effective_tier_downgrades_auto_execute_when_soft_capped():
    """The soft cap is a tier change, not a separate gate (Part 12)."""
    assert proposals.effective_tier("auto_execute", soft_capped=False) == "auto_execute"
    assert proposals.effective_tier("auto_execute", soft_capped=True) == "propose"
    # Already below auto_execute: the soft cap cannot upgrade or further demote.
    assert proposals.effective_tier("suggest", soft_capped=True) == "suggest"


# ----------------------------------------------------------------- rate limits

async def test_per_agent_rate_limit_denies_once_the_bucket_empties(
    office, stub_forge, agent_ctx, granted_agent, declare_module, set_bucket
):
    """G15 — per-agent ceiling."""
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)
    set_bucket(limits.agent_key(agent_id), tokens=2, max_tokens=2, rps=0.001)

    await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    await office.call(forge_id, module_id, {"n": 2}, agent_ctx=agent_ctx)

    with pytest.raises(RateLimited) as exc:
        await office.call(forge_id, module_id, {"n": 3}, agent_ctx=agent_ctx)

    assert exc.value.context["bucket_key"] == limits.agent_key(agent_id)
    assert stub_forge.call_count == 2


async def test_per_forge_ceiling_denies_even_when_the_agent_has_tokens(
    office, stub_forge, agent_ctx, granted_agent, declare_module, set_bucket
):
    """G16 — the global ceiling. A quiet agent cannot push a busy Forge over."""
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)
    set_bucket(limits.agent_key(agent_id), tokens=100, max_tokens=100, rps=100)
    set_bucket(limits.forge_key(forge_id), tokens=1, max_tokens=1, rps=0.001)

    await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    with pytest.raises(RateLimited) as exc:
        await office.call(forge_id, module_id, {"n": 2}, agent_ctx=agent_ctx)

    assert exc.value.context["bucket_key"] == limits.forge_key(forge_id)
    assert stub_forge.call_count == 1


async def test_throttle_reduces_the_effective_refill_rate(
    office, agent_ctx, granted_agent, set_bucket
):
    """G17 — the manifest→throttle linkage, measured on the bucket itself."""
    agent_id, _, _ = granted_agent
    set_bucket(limits.agent_key(agent_id), tokens=1, max_tokens=10, rps=10)

    await limits.throttle_agent(agent_id, 0.1, 600)

    state = await limits.bucket_state(agent_id)
    assert state is not None
    assert float(state["throttle_factor"]) == pytest.approx(0.1)
    assert state["throttled_until"] is not None


async def test_throttle_extends_but_never_shortens(office, granted_agent, set_bucket):
    """A second violation must not be able to reset the clock to something shorter."""
    agent_id, _, _ = granted_agent
    set_bucket(limits.agent_key(agent_id), tokens=1, max_tokens=10, rps=10)

    await limits.throttle_agent(agent_id, 0.1, 3600)
    first = (await limits.bucket_state(agent_id) or {})["throttled_until"]

    await limits.throttle_agent(agent_id, 0.5, 60)
    second = await limits.bucket_state(agent_id) or {}

    assert second["throttled_until"] == first, "a shorter throttle must not win"
    assert float(second["throttle_factor"]) == pytest.approx(0.1), "nor a weaker one"


# ---------------------------------------------------------------------- budget

async def test_per_task_ceiling_halts_that_task_only(
    office, stub_forge, agent_ctx, granted_agent, declare_module, set_budget, spend
):
    """G18 — blueprint acceptance criterion 3.

    "Exceeding the per-task ceiling halts that task" — that task, not the venture.
    """
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)
    set_budget(per_task=Decimal("1.00"), per_agent_daily=Decimal("999"),
               monthly=Decimal("999"))
    spend(task_id=agent_ctx.task_id, usd=Decimal("1.50"))

    with pytest.raises(BudgetExceeded) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert exc.value.context["rung"] == "per_task_ceiling"
    assert stub_forge.call_count == 0

    other = agent_ctx.__class__(
        office_agent_id=agent_id, venture_id=agent_ctx.venture_id,
        task_id="a-different-task",
    )
    result = await office.call(forge_id, module_id, {"n": 2}, agent_ctx=other)
    assert result.status_code == 200, "a different task must be unaffected"


async def test_per_agent_daily_cap_pauses_the_agent(
    office, stub_forge, agent_ctx, granted_agent, declare_module, set_budget, spend
):
    """G19 — ladder rung 2."""
    _, forge_id, module_id = granted_agent
    declare_module(required=True)
    set_budget(per_task=Decimal("999"), per_agent_daily=Decimal("5.00"),
               monthly=Decimal("999"))
    spend(task_id="earlier-task", usd=Decimal("6.00"))

    with pytest.raises(BudgetExceeded) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert exc.value.context["rung"] == "per_agent_daily_cap"
    assert stub_forge.call_count == 0


async def test_soft_cap_downgrades_auto_execute_to_propose(
    office, stub_forge, agent_ctx, granted_agent, declare_module, set_budget, spend
):
    """G20 — ladder rung 3, engagement-wide.

    The grant still says auto_execute. The venture's spend is what demotes it.
    """
    _, forge_id, module_id = granted_agent
    declare_module(required=True)
    set_budget(per_task=Decimal("999"), per_agent_daily=Decimal("999"),
               monthly=Decimal("100.00"), soft_pct=80)
    spend(task_id="earlier-task", usd=Decimal("85.00"))

    with pytest.raises(RequiresApproval) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert exc.value.context["declared_tier"] == "auto_execute"
    assert exc.value.context["effective_tier"] == "propose"
    assert exc.value.context["soft_capped"] is True
    assert stub_forge.call_count == 0


async def test_hard_cap_pauses_and_only_ivan_can_reverse(
    office, stub_forge, agent_ctx, granted_agent, declare_module, set_budget, spend
):
    """G21 — ladder rung 4. Part 12: reversal is Ivan-only."""
    _, forge_id, module_id = granted_agent
    declare_module(required=True)
    set_budget(per_task=Decimal("999"), per_agent_daily=Decimal("999"),
               monthly=Decimal("100.00"))
    spend(task_id="earlier-task", usd=Decimal("120.00"))

    with pytest.raises(BudgetExceeded) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert exc.value.context["rung"] == "hard_cap"

    async with connection() as conn:
        with pytest.raises(NotAuthorized):
            await budget.reverse_hard_cap(
                conn, venture_id=agent_ctx.venture_id, actor_id=IVAN,
                actor_role="compliance_officer",
            )
        await budget.reverse_hard_cap(
            conn, venture_id=agent_ctx.venture_id, actor_id=IVAN, actor_role="ivan"
        )

    # Reversing the hard cap resumes work - but at 120% of a 100 cap the venture is
    # still past its 80% soft cap, so auto_execute remains demoted to propose. The
    # rungs are independent; lifting the harder one does not lift the softer one.
    with pytest.raises(RequiresApproval) as approval:
        await office.call(forge_id, module_id, {"n": 2}, agent_ctx=agent_ctx)
    assert approval.value.context["effective_tier"] == "propose"
    assert approval.value.context["soft_capped"] is True


async def test_unbudgeted_venture_is_unmetered_not_blocked(
    office, agent_ctx, granted_agent, declare_module
):
    """No budget row means no cap, not a zero cap.

    Silently applying a default would halt work for a reason nobody configured.
    Validator V18 makes budget caps a required Pack field, so this state cannot
    reach production.
    """
    _, forge_id, module_id = granted_agent
    declare_module(required=True)
    result = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert result.status_code == 200


# ------------------------------------------------------------------- auditing

@pytest.mark.parametrize(
    ("setup", "expected_event"),
    [
        ("revoked", "call_refused_revoked"),
        ("undeclared", "call_refused_undeclared_module"),
    ],
)
async def test_every_governance_refusal_is_audited_with_its_own_event(
    office, agent_ctx, granted_agent, declare_module, audit_events_for,
    setup, expected_event,
):
    """G22 — a refusal nobody can query is a refusal nobody can investigate."""
    agent_id, forge_id, module_id = granted_agent

    if setup == "revoked":
        declare_module(required=True)
        async with connection() as conn:
            await revocation.revoke(
                conn, scope="agent", reason="test", revoked_by=IVAN,
                revoked_by_role="venture_operator", office_agent_id=agent_id,
            )
    # "undeclared" needs no setup: declaring nothing is the condition.

    with pytest.raises(Exception):  # noqa: B017 - the type varies by setup
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert expected_event in audit_events_for(agent_id)
