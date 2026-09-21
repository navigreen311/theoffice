"""Unit B by named-human attestation: the basis, the authority, and what ends it.

RULED 21 SEPTEMBER 2026 (entry 147)
===================================

    *"A certification records its basis: attested or tested, the attester by name, and
    the reasons. A reader can always tell them apart."*

    *"Who attests: a human holding founder authority, recorded by name."*

    *"What ends it: when a real hand-over test ships, attested Unit B certifications stop
    counting at Gate 9 and must be re-earned."*

WHY THERE IS ANYTHING TO ATTEST
===============================

    A department run submits no curriculum - there is nothing on SimForge's side to
    submit one to - so no unit-B verdict has ever been earned by anything running.
    Greenstone's three department units sat at IN_PROGRESS for as long as anybody
    watched them.

THE LOAD-BEARING TESTS IN THIS FILE
===================================

    `test_a_tested_certification_is_not_marked_attested`. Every other test here asserts
    that an attested row says so; a `basis` that read `attested` for everything would
    satisfy all of them and make the distinction worthless in the direction that matters.

    `test_an_attested_unit_still_counts_while_no_test_exists` is the second. A Gate 9
    that refused attested units unconditionally would pass every "must be re-earned"
    assertion and make the stop-gap a no-op.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest
import pytest_asyncio

from broker import attestation, certification, humans
from broker.db import connection
from broker.errors import NotAuthorized
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
FORGE = "cre-forge"
DEPARTMENT = "research"

ESCALATION_REASON = (
    "Walked the path on 21 September: a research escalation reaches the governance "
    "queue and a named human answers it. Recorded because nothing tests it."
)
COUPLING_REASON = (
    "research operates property_lookup and comp_analysis; both declare "
    "no_framework_applies and the Compliance Library agrees. Read, not assumed."
)


@pytest_asyncio.fixture
async def conn(operator) -> AsyncIterator:
    async with connection() as opened:
        opened.operator = operator  # type: ignore[attr-defined]
        yield opened


@pytest_asyncio.fixture
async def founder(world) -> humans.Human:
    """A human holding `ivan` - founder authority, unscoped.

    NOT A NEW ROLE, and that is the measurement entry 147 rests on: `office_human_role`
    has held `('venture_operator', 'compliance_officer', 'ivan')` since 0010, and `ivan`
    is top of `ROLE_RANK`. It is named for the founder and it is what a Forge-scope
    revocation already requires.
    """
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name="Founder Under Test",
            email="founder.under.test@provisioning.invalid",
        )
        await humans.grant_role(
            conn, human_id=human_id, role="ivan", venture_id=None,
            granted_by=uuid.UUID("00000000-0000-5000-8000-00000000aaaa"),
        )
        resolved = await humans.authenticate(conn, token)
    assert resolved is not None
    return resolved


async def _attest(conn, human, **over):
    kwargs = {
        "venture_id": VENTURE, "department": DEPARTMENT, "forge_id": FORGE,
        "human": human,
        "escalation_path_verified": True,
        "escalation_path_reason": ESCALATION_REASON,
        "compliance_coupling_verified": True,
        "compliance_coupling_reason": COUPLING_REASON,
    }
    kwargs.update(over)
    return await attestation.attest(conn, **kwargs)


# ------------------------------------------------------------------ who may attest

async def test_founder_authority_attests(conn, founder):
    found = await _attest(conn, founder)
    assert found.attested_by_name == "Founder Under Test"
    assert found.escalation_path_reason == ESCALATION_REASON
    assert found.compliance_coupling_reason == COUPLING_REASON
    assert found.passed is True


async def test_a_venture_operator_may_not_attest(conn, operator):
    """**Not a matter of degree.** `operator` holds `venture_operator`, which is enough
    to review artifacts at Gate 4 and to abandon a run, and is not enough to stand in for
    a certification test that does not exist."""
    with pytest.raises(NotAuthorized):
        await _attest(conn, operator)


async def test_passed_is_derived_from_the_two_facts(conn, founder):
    """`DepartmentRunOutcome.passed` defaults to TRUE and both verified flags default to
    FALSE, so an outcome built from `passed` alone asserts a pass over two unanswered
    questions. It is computed from what a person actually attested to."""
    found = await _attest(conn, founder, compliance_coupling_verified=False)
    assert found.escalation_path_verified is True
    assert found.passed is False


async def test_a_verdict_without_a_reason_is_refused(conn, founder):
    """Both reasons, whichever way the verdicts go. The CHECK in 0050 backs it and this
    refuses it at the writer, so the constraint is never the first thing a caller meets.
    """
    with pytest.raises(attestation.AttestationError):
        await _attest(conn, founder, escalation_path_reason="   ")


async def test_a_negative_attestation_is_recordable(conn, founder):
    """*"I looked and it does not work"* is a fact somebody should be able to write down.

    Forcing it to be written as silence produces a register where absence means both
    "nobody looked" and "somebody looked and it failed".
    """
    found = await _attest(
        conn, founder,
        escalation_path_verified=False,
        escalation_path_reason="No queue answers a research escalation today.",
    )
    assert found.passed is False
    assert found.escalation_path_verified is False


# --------------------------------------------------------------------- append-only

async def test_the_table_refuses_an_update(conn, founder, admin):
    """A correction is a new attestation, never an edit. `audit_log`'s argument on a
    smaller table: immutability that depends on nobody writing the wrong statement is
    not immutability."""
    found = await _attest(conn, founder)
    with pytest.raises(psycopg.errors.RaiseException), admin.cursor() as cur:
        cur.execute(
            "UPDATE department_attestation SET escalation_path_reason = 'softened' "
            " WHERE attestation_id = %s",
            (found.attestation_id,),
        )
    admin.rollback()


async def test_the_table_refuses_a_delete(conn, founder, admin):
    found = await _attest(conn, founder)
    with pytest.raises(psycopg.errors.RaiseException), admin.cursor() as cur:
        cur.execute(
            "DELETE FROM department_attestation WHERE attestation_id = %s",
            (found.attestation_id,),
        )
    admin.rollback()


async def test_a_correction_is_a_new_row_and_the_latest_is_in_force(conn, founder):
    first = await _attest(conn, founder)
    second = await _attest(
        conn, founder,
        compliance_coupling_verified=False,
        compliance_coupling_reason="Re-read on the 22nd: the library entry was withdrawn.",
    )
    current = await attestation.current_attestation(
        conn, venture_id=VENTURE, department=DEPARTMENT, forge_id=FORGE
    )
    assert current is not None
    assert current.attestation_id == second.attestation_id
    assert current.passed is False

    # AND THE FIRST IS STILL THERE. Nothing supersedes anything, because nothing is ever
    # edited - which is what makes "what did we believe on the 21st" answerable.
    everything = await attestation.history(conn, venture_id=VENTURE)
    assert {a.attestation_id for a in everything} >= {
        first.attestation_id, second.attestation_id
    }


# ----------------------------------------------------- the basis, on the certification

async def test_an_attested_certification_says_so(conn, founder, admin):
    found = await _attest(conn, founder)
    state = await certification.record_result(
        conn, unit="B", forge_id=FORGE, department=DEPARTMENT,
        verdict="PASS", rubric_version="3.2.0", certified_tier="propose",
        instruction_content_hash="a" * 64, forge_api_version="1.4.0",
        agent_model="attested", model_identity=None,
        attestation_ref=found.attestation_id,
    )
    with admin.cursor() as cur:
        cur.execute(
            "SELECT c.basis, c.attestation_ref, a.attested_by_name, "
            "       a.escalation_path_reason, a.compliance_coupling_reason "
            "  FROM certification c "
            "  JOIN department_attestation a ON a.attestation_id = c.attestation_ref "
            " WHERE c.cert_id = %s",
            (state.cert_id,),
        )
        row = cur.fetchone()
    assert row is not None
    basis, ref, name, escalation_reason, coupling_reason = row
    assert basis == "attested"
    assert ref == found.attestation_id
    # THE ATTESTER BY NAME AND THE REASONS, one join from the certification and each of
    # them on an append-only row.
    assert name == "Founder Under Test"
    assert escalation_reason == ESCALATION_REASON
    assert coupling_reason == COUPLING_REASON


async def test_a_tested_certification_is_not_marked_attested(conn, admin, seed_agent):
    """**Load-bearing.** A `basis` that read `attested` for everything would satisfy
    every other assertion here and make the distinction worthless in the direction that
    matters - a tested certification claiming somebody's word behind it."""
    state = await certification.record_result(
        conn, unit="B", forge_id=FORGE, department="operations",
        verdict="PASS", rubric_version="3.2.0", certified_tier="propose",
        instruction_content_hash="b" * 64, forge_api_version="1.4.0",
        agent_model="ollama/phi4:latest",
        model_identity={
            "provider": "ollama", "model": "phi4:latest",
            "file_digest": "sha256:" + "cd" * 32,
            "settings": {"temperature": 0, "max_tokens": 2048},
            "fingerprint": "sha256:" + "ef" * 32,
        },
    )
    with admin.cursor() as cur:
        cur.execute(
            "SELECT basis, attestation_ref FROM certification WHERE cert_id = %s",
            (state.cert_id,),
        )
        row = cur.fetchone()
    assert row == ("tested", None)


async def test_unit_a_can_never_be_attested(conn, founder, admin):
    """An attestation covers a department's escalation path and compliance coupling.

    There is no per-agent, per-module version of that, and allowing one would let an
    agent be certified to operate a module by assertion. The CHECK refuses it in the
    schema rather than leaving it to a caller's discipline.
    """
    found = await _attest(conn, founder)
    with pytest.raises(psycopg.errors.CheckViolation, match="only_unit_b_is_attested"), \
            admin.cursor() as cur:
        cur.execute(
            "INSERT INTO certification "
            "  (cert_id, unit, office_agent_id, forge_id, module_id, state, "
            "   rubric_kind, rubric_version, basis, attestation_ref) "
            "VALUES (%s, 'A', %s, %s, 'property_lookup', 'in_training', 'operation', "
            "        '1.4.0', 'attested', %s)",
            (uuid.uuid4(), uuid.uuid4(), FORGE, found.attestation_id),
        )
    admin.rollback()


async def test_a_basis_and_a_ref_cannot_disagree(conn, founder, admin):
    """Both directions. An attested row names its attestation, and nothing else may."""
    found = await _attest(conn, founder)
    for basis, ref in (("tested", found.attestation_id), ("attested", None)):
        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="an_attested_certification_names_its_attestation",
        ), admin.cursor() as cur:
            cur.execute(
                "INSERT INTO certification "
                "  (cert_id, unit, department, forge_id, state, rubric_kind, "
                "   rubric_version, basis, attestation_ref) "
                "VALUES (%s, 'B', 'research', %s, 'in_training', 'domain', '3.2.0', "
                "        %s, %s)",
                (uuid.uuid4(), FORGE, basis, ref),
            )
        admin.rollback()


# ------------------------------------------------------------------ what ends it

def test_an_attested_unit_still_counts_while_no_test_exists():
    """**Load-bearing.** A Gate 9 that refused attested units unconditionally would pass
    every "must be re-earned" assertion and make the stop-gap a no-op on the day it
    shipped."""
    reachable = {"reachable": True, "department_handover_test": None}
    assert attestation.handover_test_available(reachable) is None
    assert attestation.handover_test_available(
        {"reachable": True, "department_handover_test": False}
    ) is False


def test_a_shipped_test_is_read_as_shipped():
    assert attestation.handover_test_available(
        {"reachable": True, "department_handover_test": True}
    ) is True


def test_an_unreachable_forge_did_not_say():
    """`None`, not False. They lead to the same behaviour and call for different
    responses: one is a Forge to ask, the other is a field to add."""
    assert attestation.handover_test_available(
        {"reachable": False, "reason": "ConnectError"}
    ) is None
    assert attestation.handover_test_available(None) is None


def test_a_truthy_string_does_not_end_the_stop_gap():
    """A capability read off a truthy string is how a stop-gap ends by accident - `"no"`
    is truthy. A boolean or nothing."""
    for value in ("no", "false", "", 0, 1, [], {"shipped": True}):
        assert attestation.handover_test_available(
            {"reachable": True, "department_handover_test": value}
        ) is None
