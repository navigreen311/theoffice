"""A certification names the model it was earned on, not just the model's label.

Ruled by Ivan Green, 17 September 2026: a certification records the model the agent
passed on - **name, exact digest, temperature and max tokens**. A certification that
does not name the model cannot enforce re-certification when the model changes.

WHAT B34 ALREADY GOT, AND WHAT IT COULD NOT
===========================================

    `agent_model` has been mandatory on an answered SimForge verdict since B34. It
    carries `ollama/llama3.1:8b`, and that string is identical whether the tag was
    re-pulled at a different quantization or served at a different temperature. Two
    certifications with the same label can describe different candidates, and nothing
    could tell them apart.

    Measured while this was written: the exam runs at temperature 0.0 and 2048 tokens
    (SimForge `EXAM_TEMPERATURE` / `EXAM_MAX_TOKENS`), production at 0.7 and 200/300/500
    by route (Village `agent_orchestrator.py`). Every setting differs, on every call.

THE TWO TESTS THAT KEEP THIS FROM BEING A WALL
==============================================

    `test_a_failure_is_still_recorded_without_a_model` and
    `test_a_bootstrap_still_needs_no_model`. Every other test here asserts that
    something is refused, and a rule that refused everything would satisfy all of them
    while making it impossible to record a failed exam or to bootstrap a venture.

    This suite is `test_certification_records_its_model.py` one ruling later and uses
    the same fixtures deliberately - a reader comparing the two should not have to
    reconcile two sets of scaffolding as well.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import certification
from broker.db import connection
from tests.conftest import requires_db
from tests.world import (
    FIXTURE_MODEL_DIGEST,
    FIXTURE_MODEL_IDENTITY,
    FIXTURE_MODEL_MAX_TOKENS,
    FIXTURE_MODEL_TEMPERATURE,
)

pytestmark = [requires_db, pytest.mark.db]

MODEL = "ollama/llama3.1:8b"
MODULE = "property_lookup"
FORGE = "cre-forge"


def _basis(**over) -> dict:
    """The arguments a real SimForge verdict arrives with."""
    return {
        "unit": "A",
        "forge_id": FORGE,
        "module_id": MODULE,
        "verdict": "PASS",
        "rubric_version": "1.4.0",
        "certified_tier": "auto_execute",
        "instruction_content_hash": "a" * 64,
        "forge_api_version": "1.4.0",
        **over,
    }


# ------------------------------------------------------------------ what is refused

async def test_a_pass_without_a_model_identity_is_refused(seed_agent):
    """The label alone no longer buys a certification."""
    async with connection() as conn:
        with pytest.raises(certification.CertificationError) as refused:
            await certification.record_result(
                conn, office_agent_id=seed_agent, agent_model=MODEL, **_basis()
            )

    message = str(refused.value)
    assert "file_digest" in message
    assert "settings.temperature" in message
    assert "settings.max_tokens" in message
    # It says WHY, not only that. A refusal naming a column sends the reader to the
    # schema; this one has to send them to SimForge.
    assert "LABEL" in message


async def test_a_partial_model_identity_is_refused_and_names_what_is_missing(seed_agent):
    """Half a record is not a record, and the refusal says which half."""
    partial = {
        "provider": "ollama",
        "model": "llama3.1:8b",
        "file_digest": FIXTURE_MODEL_DIGEST,
        "settings": {"temperature": FIXTURE_MODEL_TEMPERATURE},
    }
    async with connection() as conn:
        with pytest.raises(certification.CertificationError) as refused:
            await certification.record_result(
                conn, office_agent_id=seed_agent, agent_model=MODEL,
                model_identity=partial, **_basis()
            )

    message = str(refused.value)
    assert "settings.max_tokens" in message
    assert "file_digest" not in message, "it named a field that was supplied"


async def test_the_database_refuses_it_too_when_nothing_goes_through_record_result(
    seed_agent, admin
):
    """**The constraint is the control; the guard is the sentence.**

    `record_result` is not the only way a row can be written - a migration, a script or
    a fixture can INSERT directly, and B34's own suite exists because one did. So the
    rule lives in `certification_names_its_model` as well, and this asserts the database
    half rather than trusting that every writer goes through the function.
    """
    with pytest.raises(psycopg.errors.CheckViolation) as refused, admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO certification
              (cert_id, unit, office_agent_id, forge_id, module_id, state,
               certified_tier, instruction_content_hash, forge_api_version,
               rubric_kind, rubric_version, simforge_verdict, basis, agent_model)
            VALUES (%s, 'A', %s, %s, %s, 'certified', 'auto_execute', %s, %s,
                    'operation', '1.4.0', 'PASS', 'tested', %s)
            """,
            (uuid.uuid4(), seed_agent, FORGE, MODULE, "a" * 64, "1.4.0", MODEL),
        )
    admin.rollback()
    assert "certification_names_its_model" in str(refused.value)


# ---------------------------------------------------------------- what is recorded

async def test_the_model_reaches_the_row_in_columns_and_whole(seed_agent, admin):
    """Promoted and kept. The scalars a CHECK can reach, and the record as sent."""
    async with connection() as conn:
        await certification.record_result(
            conn, office_agent_id=seed_agent, agent_model=MODEL,
            model_identity=FIXTURE_MODEL_IDENTITY, **_basis()
        )
        await conn.commit()

    with admin.cursor() as cur:
        cur.execute(
            "SELECT agent_model, model_digest, model_temperature, model_max_tokens, "
            "       model_identity, model_fingerprint "
            "FROM certification WHERE unit = 'A' AND office_agent_id = %s "
            "  AND module_id = %s",
            (seed_agent, MODULE),
        )
        row = cur.fetchone()

    assert row is not None, "nothing was written"
    label, digest, temperature, max_tokens, identity, fingerprint = row
    assert label == MODEL, "the readable label is kept, not replaced"
    assert digest == FIXTURE_MODEL_DIGEST
    assert float(temperature) == FIXTURE_MODEL_TEMPERATURE
    assert max_tokens == FIXTURE_MODEL_MAX_TOKENS
    # The whole record, so a field SimForge adds later is on the row rather than
    # discarded on the way in - `revocation.blast_radius`'s rule.
    assert identity == FIXTURE_MODEL_IDENTITY
    assert fingerprint == FIXTURE_MODEL_IDENTITY["fingerprint"]


async def test_a_re_certification_replaces_the_model_rather_than_keeping_the_old_one(
    seed_agent, admin
):
    """A new exam ran on whatever answered it.

    Keeping the previous digest beside a new verdict would describe a run that never
    happened. The upsert replaces all five, and this is what says so.
    """
    second = dict(FIXTURE_MODEL_IDENTITY)
    second["file_digest"] = "sha256:" + "9c" * 32
    second["settings"] = {"temperature": 0.2, "max_tokens": 1024}
    second["fingerprint"] = "sha256:" + "cd" * 32

    async with connection() as conn:
        await certification.record_result(
            conn, office_agent_id=seed_agent, agent_model=MODEL,
            model_identity=FIXTURE_MODEL_IDENTITY, **_basis()
        )
        await certification.record_result(
            conn, office_agent_id=seed_agent, agent_model=MODEL,
            model_identity=second, **_basis()
        )
        await conn.commit()

    with admin.cursor() as cur:
        cur.execute(
            "SELECT model_digest, model_max_tokens, model_fingerprint "
            "FROM certification "
            "WHERE unit = 'A' AND office_agent_id = %s AND module_id = %s",
            (seed_agent, MODULE),
        )
        digest, max_tokens, fingerprint = cur.fetchone()

    assert digest == second["file_digest"]
    assert max_tokens == 1024
    assert fingerprint == second["fingerprint"]


# ------------------------------------------- the two that keep this from being a wall

async def test_a_failure_is_still_recorded_without_a_model(seed_agent):
    """**Losing a pass is safe. Losing a failure is not.**

    A FAIL records that an agent was tested and did not pass - a claim that cannot go
    stale, so there is nothing to expire. Demanding the digest would make an older
    SimForge's failure refused rather than recorded and the finding would be gone. The
    same reasoning `record_result` already applies to the Forge api_version, whose
    docstring says a FAIL needs no basis.
    """
    async with connection() as conn:
        state = await certification.record_result(
            conn, office_agent_id=seed_agent, agent_model=MODEL,
            **_basis(verdict="FAIL", certified_tier=None)
        )
        await conn.commit()

    assert state.state == "failed"


async def test_a_bootstrap_still_needs_no_model(seed_agent, admin):
    """Phase 0 is defined not to have one. No battery ran, so nothing answered."""
    async with connection() as conn:
        state = await certification.record_result(
            conn, office_agent_id=seed_agent, attested_by="bootstrap",
            bootstrap_reason="Phase 0.8: proving the call path before the ladder exists",
            **_basis(rubric_version="bootstrap")
        )
        await conn.commit()

    assert state.state == "certified"

    with admin.cursor() as cur:
        cur.execute(
            "SELECT agent_model, model_digest, simforge_verdict FROM certification "
            "WHERE unit = 'A' AND office_agent_id = %s AND module_id = %s",
            (seed_agent, MODULE),
        )
        label, digest, verdict = cur.fetchone()

    assert (label, digest, verdict) == (None, None, None), (
        "a bootstrap named a model; no battery ran, so nothing answered"
    )
