"""One venture per agent per shift — enforced in the call path.

Master prompt §7.5: "One venture per agent per shift — locked. No mid-shift venture
switching under any condition, including non-PHI ventures."

The schema already forbade *overlapping shifts*. That is not the same rule. An agent
holding grants for two ventures could serve both inside a single shift simply by passing
a different `venture_id` — the grant resolves, every other gate passes, and the temporal
PHI wall has a hole in it that no constraint could see.

These tests are that hole, closed.
"""

from __future__ import annotations

import uuid

import pytest

from broker.shifts import OffShift
from client.office_client import AgentContext
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]


async def test_a_call_matching_the_open_shift_succeeds(
    office, stub_forge, agent_ctx, granted_agent, declare_module
):
    """The gate must let correct work through, or it is an outage rather than a wall."""
    declare_module(required=True)
    result = await office.call(
        granted_agent[1], granted_agent[2], {"n": 1}, agent_ctx=agent_ctx
    )
    assert result.status_code == 200
    assert stub_forge.call_count == 1


async def test_a_call_for_a_different_venture_is_refused(
    office, stub_forge, agent_ctx, granted_agent, declare_module, admin
):
    """S9 — the mid-shift switch, refused.

    The agent is on shift for burkham-wickmont and holds a live, certified grant for
    greenstone. Every other gate would pass this call.
    """
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)

    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_forge_grant
              (grant_id, office_agent_id, forge_id, module_id, venture_id, trust_tier,
               operation_cert_ref, dept_context_cert_ref, granted_by, activated_at)
            VALUES (%s, %s, %s, %s, 'greenstone', 'auto_execute', 'a', 'b', %s, now())
            """,
            (str(uuid.uuid4()), agent_id, forge_id, module_id, str(uuid.uuid4())),
        )
        cur.execute(
            """
            INSERT INTO venture_forge_manifest
              (venture_id, forge_id, module_id, is_required, criticality)
            VALUES ('greenstone', %s, %s, TRUE, 'soft')
            """,
            (forge_id, module_id),
        )
    admin.commit()

    other = AgentContext(
        office_agent_id=agent_id, venture_id="greenstone", task_id="t-switch"
    )

    with pytest.raises(OffShift) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=other)

    assert exc.value.context["shift_venture_id"] == "burkham-wickmont"
    assert exc.value.context["venture_id"] == "greenstone"
    assert stub_forge.call_count == 0, "the Forge must not have been contacted"


async def test_a_call_with_no_open_shift_is_refused(
    office, stub_forge, agent_ctx, granted_agent, declare_module, admin
):
    """S10 — an unscoped call has no venture context to isolate.

    Accepted cost, stated in §7.5 and worth repeating: an agent whose queue empties
    mid-shift idles until the boundary. Recoverable by tuning shift length. Not traded
    against isolation.
    """
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)

    with admin.cursor() as cur:
        cur.execute("DELETE FROM shift_assignment WHERE office_agent_id = %s", (agent_id,))
    admin.commit()

    with pytest.raises(OffShift) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert "not on shift" in str(exc.value)
    assert stub_forge.call_count == 0


async def test_a_call_after_the_shift_ends_is_refused(
    office, stub_forge, agent_ctx, granted_agent, declare_module, admin
):
    """The boundary is a moment, not a suggestion. A shift that has ended is over."""
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE shift_assignment SET shift_start = now() - interval '9 hours', "
            "shift_end = now() - interval '1 hour' WHERE office_agent_id = %s",
            (agent_id,),
        )
    admin.commit()

    with pytest.raises(OffShift):
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert stub_forge.call_count == 0


async def test_the_refusal_is_audited(
    office, agent_ctx, granted_agent, declare_module, admin, audit_events_for
):
    """A boundary violation nobody can query is a boundary violation nobody sees."""
    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)

    with admin.cursor() as cur:
        cur.execute("DELETE FROM shift_assignment WHERE office_agent_id = %s", (agent_id,))
    admin.commit()

    with pytest.raises(OffShift):
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert "call_refused_off_shift" in audit_events_for(agent_id)


async def test_revocation_is_reported_before_the_shift_problem(
    office, agent_ctx, granted_agent, declare_module, admin
):
    """Order matters in the message, not only in the logic.

    A revoked agent should be told it is revoked. Telling it that it is on the wrong
    shift sends whoever is watching to the wrong investigation.
    """
    from broker.errors import Revoked

    agent_id, forge_id, module_id = granted_agent
    declare_module(required=True)

    with admin.cursor() as cur:
        cur.execute("DELETE FROM shift_assignment WHERE office_agent_id = %s", (agent_id,))
        cur.execute(
            """
            INSERT INTO revocation (revocation_id, scope, office_agent_id, reason,
                                    revoked_by, revoked_by_role)
            VALUES (%s, 'agent', %s, 'test', %s, 'venture_operator')
            """,
            (str(uuid.uuid4()), agent_id, str(uuid.uuid4())),
        )
    admin.commit()

    with pytest.raises(Revoked):
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
