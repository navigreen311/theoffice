"""The Village's agent state is shown to people and read by no rule.

The Village is a simulation with grief, exhaustion, ambition and death in it. The Office
governs regulated work: PHI, financial records, a call to a Forge that acts on a real
customer. Those two things share a roster and must not share a decision.

WHAT WOULD GO WRONG

    An agent whose friend died in a simulation is still certified, still holds the
    grants somebody deliberately granted them, and is still refused for exactly the
    reasons the call path already refuses anybody. If mood reached an authorization
    decision, a patient record would go unprocessed because of a mortality roll, and no
    audit entry could explain it - the log would show a refusal whose cause lives in
    another application's random number generator.

    It is not a hypothetical shape. `village_state` is on the agent payload precisely so
    an operator can see it, and a field on a payload is one edit away from a condition.

WHY THIS IS AN AST WALK

    A grep for `mood` matches the word in this docstring and misses
    `state["mood"]`, `s.get("mood")`, and a variable assigned from it three lines
    earlier. The parse tree can tell a comparison from prose, which is the same reason
    the Village seal test and the raw-mutation guard are written this way.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: Modules that decide whether something may happen. A Village-state read inside any of
#: these is the failure. `app.py` is excluded from the *decision* list on purpose: it
#: fetches the state to render it, which is the whole point of D4.
DECISION_MODULES = (
    "broker/revocation.py",
    "broker/shifts.py",
    "broker/certification.py",
    "broker/call_path.py",
    "broker/budget.py",
    "broker/grants.py",
    "broker/escalation.py",
    "broker/provisioning.py",
    "generators/appointment.py",
    "generators/validator.py",
)

#: Fields the Village reports about an agent's inner life. Anything here reaching a
#: comparison, a branch, or a boolean operation is a simulation gating regulated work.
SIMULATED_STATE = frozenset({
    "mood", "morale", "energy", "exhaustion", "fatigue", "stress",
    "grief", "happiness", "satisfaction", "ambition", "lifecycle",
    "lifecycle_stage", "age", "health", "personality", "traits",
    "relationship", "relationships", "mortality",
})


def _sources() -> list[tuple[str, ast.Module]]:
    out = []
    for name in DECISION_MODULES:
        path = Path(name)
        if path.exists():
            out.append((name, ast.parse(path.read_text(encoding="utf-8"))))
    return out


def _string_constants(node: ast.AST) -> set[str]:
    return {
        n.value for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def _attribute_names(node: ast.AST) -> set[str]:
    return {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def test_the_decision_modules_exist():
    """A guard over an empty list passes by describing nothing.

    Half these paths are aspirational - `broker/call_path.py` and `broker/grants.py` may
    not exist under those names. What must not happen is all of them silently missing,
    which would turn this file into decoration.
    """
    found = [name for name, _ in _sources()]
    assert len(found) >= 5, f"only found {found}; the guard is covering almost nothing"


@pytest.mark.parametrize("module", DECISION_MODULES)
def test_no_decision_reads_simulated_agent_state(module):
    """The rule: nothing that decides may look at how an agent feels."""
    path = Path(module)
    if not path.exists():
        pytest.skip(f"{module} does not exist")

    tree = ast.parse(path.read_text(encoding="utf-8"))

    offences = []
    for node in ast.walk(tree):
        # A branch, a comparison, or a boolean operation is where a value becomes a
        # decision. A value merely passed along is not.
        if not isinstance(node, ast.If | ast.Compare | ast.BoolOp | ast.IfExp):
            continue
        touched = (_string_constants(node) | _attribute_names(node)) & SIMULATED_STATE
        if touched:
            offences.append((getattr(node, "lineno", "?"), sorted(touched)))

    assert not offences, (
        f"{module} branches on simulated agent state: {offences}. The Village is a "
        "simulation with grief and death in it; The Office governs regulated work. An "
        "agent who is grieving is still certified and still holds their grants."
    )


def test_no_decision_module_calls_the_village_for_agent_state():
    """`village.agent_state` belongs to rendering, not to deciding.

    Distinct from the field check above: this catches the call before anybody has picked
    a field out of the answer.
    """
    offences = []
    for name, tree in _sources():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "agent_state"
            ):
                offences.append((name, node.lineno))

    assert not offences, (
        f"a decision module calls village.agent_state: {offences}. Fetch it where it is "
        "rendered."
    )


def test_the_guard_catches_a_real_violation():
    """Mutation test. A guard nobody has seen fail is a guard nobody has tested.

    Both forms: the subscript a caller would actually write, and the attribute access.
    """
    violations = [
        "if state['mood'] == 'grieving':\n    refuse()\n",
        "allowed = agent.energy > 0.5\n",
        "tier = 'suggest' if state.get('exhaustion') else 'auto_execute'\n",
        "if grant.live and state['lifecycle'] != 'active':\n    refuse()\n",
    ]
    for source in violations:
        tree = ast.parse(source)
        caught = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.If | ast.Compare | ast.BoolOp | ast.IfExp):
                continue
            if (_string_constants(node) | _attribute_names(node)) & SIMULATED_STATE:
                caught = True
        assert caught, f"the guard missed: {source!r}"


def test_the_guard_does_not_fire_on_prose():
    """The word in a docstring or a comment is not a decision.

    This file's own module docstring names every field in the set. A guard that flagged
    it would be the same failure the raw-mutation guard had when it lowercased whole
    files and matched its own explanation.
    """
    source = '''
def f(state):
    """Mood and grief are simulated; they gate nothing here."""
    # energy and exhaustion are displayed only
    return state
'''
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.If | ast.Compare | ast.BoolOp | ast.IfExp):
            assert not (
                (_string_constants(node) | _attribute_names(node)) & SIMULATED_STATE
            )


def test_the_payload_says_it_gates_nothing():
    """Stated in the response, not only in a comment.

    The console renders this section, and the next person to read it should not have to
    infer that it is inert.
    """
    source = Path("broker/app.py").read_text(encoding="utf-8")
    assert '"village_state_gates": []' in source


# ============================================================ THE PAGE ACTUALLY SHOWS IT

# A guard proving nothing *reads* the state is only half of D4. The other half is that
# the state is on the payload at all, and that a Village outage does not take the agent
# page down with it - every other number on that page comes from The Office's own
# database and is still true when the Village is gone.

import uuid  # noqa: E402

import httpx  # noqa: E402
import psycopg  # noqa: E402

from broker import humans, village  # noqa: E402
from broker.app import app  # noqa: E402
from broker.db import connection  # noqa: E402

AGENT_REF = "d4-state-agent"


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def seeded(admin: psycopg.Connection):
    """One identity with a Village ref behind it, and a token that can read it."""
    agent_id = uuid.uuid4()

    def clear() -> None:
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM office_agent_identity WHERE village_agent_ref = %s",
                (AGENT_REF,),
            )
            cur.execute(
                "DELETE FROM village_agent WHERE village_agent_ref = %s", (AGENT_REF,)
            )
        admin.commit()

    clear()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO village_agent (village_agent_ref, agent_name, department, "
            "role_key, title, status, source) VALUES "
            "(%s, 'Wren Halloway', 'engineering', 'individual_contributor', "
            " 'Engineer', 'active', 'import')",
            (AGENT_REF,),
        )
        cur.execute(
            "INSERT INTO office_agent_identity (office_agent_id, village_agent_ref, "
            "agent_name, department, status) "
            "VALUES (%s, %s, 'Wren Halloway', 'engineering', 'active')",
            (agent_id, AGENT_REF),
        )
    admin.commit()

    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name="D4 reader", email="d4@x.d4.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role="venture_operator", venture_id=None,
            granted_by=human_id,
        )

    yield agent_id, token

    clear()
    with admin.cursor() as cur:
        cur.execute("DELETE FROM office_human_role WHERE human_id = %s", (human_id,))
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (human_id,))
    admin.commit()


@pytest.mark.asyncio
async def test_the_agent_page_carries_the_village_state(api, seeded, monkeypatch):
    agent_id, token = seeded

    async def state(agent_ref: str) -> village.Answer:
        from datetime import UTC, datetime
        assert agent_ref == AGENT_REF
        return village.Answer(
            data={"mood": "content", "lifecycle": "adult", "shift": "MORNING"},
            fetched_at=datetime.now(UTC),
        )

    monkeypatch.setattr(village, "agent_state", state)

    body = (await api.get(
        f"/api/agents/{agent_id}", headers={"Authorization": f"Bearer {token}"}
    )).json()

    assert body["village_state"]["mood"] == "content"
    assert body["village_unreachable"] is None
    assert body["village_state_gates"] == []


@pytest.mark.asyncio
async def test_a_village_outage_does_not_take_the_agent_page_down(
    api, seeded, monkeypatch
):
    """Everything else on this page is The Office's own record and is still true."""
    agent_id, token = seeded

    async def unreachable(agent_ref: str) -> village.Answer:
        raise village.VillageUnreachableError("connection refused")

    monkeypatch.setattr(village, "agent_state", unreachable)

    response = await api.get(
        f"/api/agents/{agent_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["village_state"] is None
    assert "connection refused" in body["village_unreachable"]
    # The parts that do not depend on the Village are still there.
    assert body["identity"]["agent_name"] == "Wren Halloway"
    assert "certifications" in body and "grants" in body
