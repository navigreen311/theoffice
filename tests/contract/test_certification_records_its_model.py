"""A certification names the model that answered — and only when one did.

`certified_records_its_basis` has demanded the instruction hash, the Forge api_version
and the tier since migration 0007, on the argument that a certification whose basis is
unknown is permanent by accident. All three describe the **exam**. The model is the
**candidate**, and until 0035 it went unrecorded — so a row could say *this agent passed*
and not *this agent, on this model, passed*, and swapping the model left it reading as
current. blocking.md B34's shape, in the row the call path enforces on every request.

These tests pin the rule in both directions, because a guard that only refuses is as
wrong as one that only permits: the first blocks a bootstrap that legitimately has
nothing to name, the second is the hole 0035 exists to close.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import certification
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

MODEL = "ollama/llama3.1:8b"


async def _basis(**over):
    """The arguments a real SimForge verdict arrives with."""
    return {
        "unit": "A",
        "forge_id": "cre-forge",
        "module_id": "property_lookup",
        "verdict": "PASS",
        "rubric_version": "1.4.0",
        "certified_tier": "auto_execute",
        "instruction_content_hash": "a" * 64,
        "forge_api_version": "1.4.0",
        **over,
    }


async def test_a_verdict_that_answered_must_name_the_model(seed_agent):
    """The hole 0035 closes. PASS means a battery ran; something produced that answer."""
    async with connection() as conn:
        with pytest.raises(certification.CertificationError) as exc:
            await certification.record_result(
                conn, office_agent_id=seed_agent, **await _basis()
            )

    message = str(exc.value)
    assert "model" in message.lower()
    # The refusal names the missing fact rather than only reporting a rejection - a
    # CHECK violation says the row was refused and not which of four columns was empty.
    assert "provider/model" in message


async def test_a_bootstrap_names_no_model_and_stays_legal(seed_agent):
    """`attested_by='bootstrap'` is *a grant issued against no scenario run*.

    It has no model because nothing answered, and forcing it to invent one would be the
    opposite of what this constraint is for. Every certified row in the table on the day
    0035 landed was one of these.
    """
    async with connection() as conn:
        state = await certification.record_result(
            conn,
            office_agent_id=seed_agent,
            attested_by="bootstrap",
            bootstrap_reason="proving the bridge before any battery existed",
            **await _basis(),
        )
    assert state.state == certification.CERTIFIED


async def test_a_timeout_names_no_model_and_stays_legal(seed_agent):
    """A TIMEOUT is a verdict *about an open run*, not a result earned in one.

    `gate_result_for` derives it from the window when nothing was stored, so a row
    carrying it records that nothing answered. The first draft of this rule keyed on
    "a real verdict" and refused these; a test caught it, which is why the CHECK mirrors
    `simforge.TERMINAL_VERDICTS` rather than testing for NULL.
    """
    async with connection() as conn:
        state = await certification.record_result(
            conn, office_agent_id=seed_agent, **await _basis(verdict="TIMEOUT")
        )
    assert state.state == certification.IN_TRAINING


async def test_the_model_reaches_the_row_and_is_not_merely_accepted(seed_agent):
    """Accepting the argument and storing it are different facts.

    A guard that validated and then dropped the value would pass every other test here
    and leave the column NULL - which is precisely what `attested_by` does, and why B34
    exists. So this asserts the database, not the return value.
    """
    async with connection() as conn:
        await certification.record_result(
            conn, office_agent_id=seed_agent, agent_model=MODEL, **await _basis()
        )
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT agent_model FROM certification "
                "WHERE unit = 'A' AND office_agent_id = %s AND module_id = %s",
                (seed_agent, "property_lookup"),
            )
            row = await cur.fetchone()

    assert row is not None
    assert row[0] == MODEL


async def test_the_database_refuses_it_even_if_the_guard_is_bypassed(seed_agent):
    """The CHECK is the control; the Python guard is the good error message.

    Written as a raw INSERT deliberately. If someone later adds a second writer that
    does not go through `record_result`, the guard does not run and this is what still
    refuses the row.
    """
    async with connection() as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO certification
                      (cert_id, unit, office_agent_id, forge_id, module_id, state,
                       certified_tier, instruction_content_hash, forge_api_version,
                       rubric_kind, rubric_version, simforge_verdict)
                    VALUES (%s, 'A', %s, 'cre-forge', 'property_lookup', 'certified',
                            'auto_execute', %s, '1.4.0', 'operation', '1.4.0', 'PASS')
                    """,
                    (str(uuid.uuid4()), seed_agent, "b" * 64),
                )
        await conn.rollback()
