"""A grant's department certification reference points at the certification in force.

RULED 23 SEPTEMBER 2026 (decisions entry 181)
=============================================

    *"A grant's department certification reference points at the certification in
    force. Issuing a Unit B certification re-points every grant in that department and
    Forge. Measured: engineering's two grants reference cert ids no row holds, so
    certifying engineering would write a valid certification the gate cannot see;
    operations and research are reachable only because an upsert happens to preserve
    their ids."*

WHY IT SURVIVED
===============

    `dept_context_cert_ref` is written once, when a grant is issued, and nothing moved
    it. Both Unit B writers upsert on `(department, forge_id) WHERE unit = 'B'`, and an
    upsert that hits an existing row keeps its `cert_id` - so the reference stayed
    correct BY COINCIDENCE, for as long as a department never got its first
    certification after its grants were issued.

THE ONE THAT CARRIES THE RULING
===============================

    `test_a_departments_first_certification_is_visible_to_gate_9` - the engineering
    case. A brand new `cert_id`, and the grants must follow it.
"""

from __future__ import annotations

import uuid

import pytest

from broker import certification
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

FORGE = "probe-forge"
OTHER_FORGE = "probe-forge-2"


@pytest.fixture(autouse=True)
async def _clean_probe_rows():
    """Take the probe rows out again.

    These tests write identities, grants and a Forge registry entry that no fixture
    owns, and a row left behind is a row some other test counts. One did:
    `test_the_empty_state_names_this_cause_not_a_plausible_one` passed alone and
    failed in the suite, which is the only way this kind of leak ever shows up.

    In dependency order, and only rows this module made - keyed on the `probe-`
    prefix, so nothing here can reach a real Forge, agent or grant.
    """
    yield
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM agent_forge_grant WHERE forge_id LIKE 'probe-forge%'")
            await cur.execute(
                "DELETE FROM office_agent_identity WHERE department LIKE 'probe-%'")
            await cur.execute(
                "DELETE FROM forge_module_registry WHERE forge_id LIKE 'probe-forge%'")
            await cur.execute(
                "DELETE FROM forge_registry WHERE forge_id LIKE 'probe-forge%'")
        await conn.commit()



async def _forge(conn, forge_id: str, *modules: str) -> None:
    """A probe Forge and its modules, so the grants below have something to reference.

    Its own ids rather than the real registry's: these tests are about a column on
    `agent_forge_grant`, and borrowing `cre-forge` would make them depend on which
    modules the world fixture happened to register.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO forge_registry "
            "  (forge_id, display_name, base_url, api_version, auth_model, "
            "   credential_mode, health_status) "
            "VALUES (%s, %s, 'http://probe.invalid', '1.0.0', 'bearer', "
            "        'brokered', 'GREEN') ON CONFLICT DO NOTHING",
            (forge_id, forge_id),
        )
        for module_id in modules:
            await cur.execute(
                "INSERT INTO forge_module_registry "
                "  (forge_id, module_id, module_name, idempotency_support, is_mutating) "
                "VALUES (%s, %s, %s, 'natural', false) ON CONFLICT DO NOTHING",
                (forge_id, module_id, module_id),
            )


async def _identity(conn, *, department: str) -> uuid.UUID:
    agent_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO office_agent_identity "
            "  (office_agent_id, agent_name, village_agent_ref, department, status) "
            "VALUES (%s, %s, %s, %s, 'active')",
            (agent_id, f"Probe {str(agent_id)[:8]}",
             f"probe_{str(agent_id)[:8]}", department),
        )
    return agent_id


async def _grant(conn, *, agent_id, venture_id, forge_id, module_id, b_ref) -> uuid.UUID:
    grant_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO agent_forge_grant "
            "  (grant_id, office_agent_id, forge_id, module_id, venture_id, "
            "   dept_context_cert_ref, granted_by, origin) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 'unknown')",
            (grant_id, agent_id, forge_id, module_id, venture_id,
             b_ref, uuid.uuid4()),
        )
    return grant_id


async def _ref(conn, grant_id) -> str | None:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT dept_context_cert_ref FROM agent_forge_grant WHERE grant_id = %s",
            (grant_id,),
        )
        row = await cur.fetchone()
    return row[0] if row else None


# ======================================================== the ruling

async def test_a_departments_first_certification_is_visible_to_gate_9():
    """**THE RULING**, in the shape that produced it.

    A department with no Unit B row gets a fresh `cert_id`. Before this, its grants
    kept naming whatever they were issued with - and Gate 9, which joins
    `cb.cert_id::text = g.dept_context_cert_ref`, would read `never_certified` for a
    certification sitting in the table.
    """
    department = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        await _forge(conn, FORGE, 'alpha', 'beta')
        await _forge(conn, OTHER_FORGE, 'alpha', 'beta')
        agent = await _identity(conn, department=department)
        # A ref no certification row holds. This is engineering's live shape.
        dangling = str(uuid.uuid4())
        grant = await _grant(
            conn, agent_id=agent, venture_id="greenstone", forge_id=FORGE,
            module_id="alpha", b_ref=dangling)
        await conn.commit()

        assert await _ref(conn, grant) == dangling

        cert_id = uuid.uuid4()
        moved = await certification.repoint_department_grants(
            conn, department=department, forge_id=FORGE, cert_id=cert_id)
        await conn.commit()

        assert moved == 1
        assert await _ref(conn, grant) == str(cert_id)


async def test_every_grant_in_the_department_and_forge_moves():
    """"Every", and the key is the certification's own: (department, forge_id).

    `ux_cert_unit_b` carries no venture, so one department on one Forge has exactly
    one Unit B certification and every grant in it is about that row. Scoping the
    update by venture would leave a second venture's grant naming a row no longer in
    force.
    """
    department = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        await _forge(conn, FORGE, 'alpha', 'beta')
        await _forge(conn, OTHER_FORGE, 'alpha', 'beta')
        a1 = await _identity(conn, department=department)
        a2 = await _identity(conn, department=department)
        here = await _grant(conn, agent_id=a1, venture_id="greenstone",
                            forge_id=FORGE, module_id="alpha",
                            b_ref=str(uuid.uuid4()))
        # Same department and Forge, DIFFERENT VENTURE. Still about this certification.
        elsewhere = await _grant(conn, agent_id=a2, venture_id="burkham-wickmont",
                                 forge_id=FORGE, module_id="beta",
                                 b_ref=str(uuid.uuid4()))
        # Same department, ANOTHER FORGE. A different certification entirely.
        other_forge = await _grant(conn, agent_id=a1, venture_id="greenstone",
                                   forge_id=OTHER_FORGE, module_id="beta",
                                   b_ref="untouched")
        await conn.commit()

        cert_id = uuid.uuid4()
        moved = await certification.repoint_department_grants(
            conn, department=department, forge_id=FORGE, cert_id=cert_id)
        await conn.commit()

        assert moved == 2
        assert await _ref(conn, here) == str(cert_id)
        assert await _ref(conn, elsewhere) == str(cert_id)
        assert await _ref(conn, other_forge) == "untouched"


async def test_another_departments_grants_are_untouched():
    department = f"probe-{uuid.uuid4().hex[:8]}"
    other = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        await _forge(conn, FORGE, 'alpha', 'beta')
        mine = await _identity(conn, department=department)
        theirs = await _identity(conn, department=other)
        g1 = await _grant(conn, agent_id=mine, venture_id="greenstone",
                          forge_id=FORGE, module_id="alpha",
                          b_ref=str(uuid.uuid4()))
        g2 = await _grant(conn, agent_id=theirs, venture_id="greenstone",
                          forge_id=FORGE, module_id="beta", b_ref="theirs")
        await conn.commit()

        cert_id = uuid.uuid4()
        await certification.repoint_department_grants(
            conn, department=department, forge_id=FORGE, cert_id=cert_id)
        await conn.commit()

        assert await _ref(conn, g1) == str(cert_id)
        assert await _ref(conn, g2) == "theirs"


# ======================================================== what it leaves alone

async def test_a_superseded_grant_keeps_the_reference_it_retired_with():
    """**Live grants only.**

    A superseded grant confers nothing, and its reference is part of what was true
    when it was retired. Rewriting it would edit the record rather than correct it -
    the distinction entry 72 drew between revoking and deleting, one column over.
    """
    department = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        await _forge(conn, FORGE, 'alpha', 'beta')
        await _forge(conn, OTHER_FORGE, 'alpha', 'beta')
        agent = await _identity(conn, department=department)
        retired = await _grant(conn, agent_id=agent, venture_id="greenstone",
                               forge_id=FORGE, module_id="alpha",
                               b_ref="as-retired")
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE agent_forge_grant SET superseded_at = now() WHERE grant_id = %s",
                (retired,))
        await conn.commit()

        moved = await certification.repoint_department_grants(
            conn, department=department, forge_id=FORGE, cert_id=uuid.uuid4())
        await conn.commit()

        assert moved == 0
        assert await _ref(conn, retired) == "as-retired"


async def test_it_is_idempotent_and_counts_only_what_moved():
    """`IS DISTINCT FROM`, so a re-certification that keeps its id updates nothing.

    The count a caller records is the number of references that actually moved, not
    the number of grants it looked at.
    """
    department = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        await _forge(conn, FORGE, 'alpha', 'beta')
        await _forge(conn, OTHER_FORGE, 'alpha', 'beta')
        agent = await _identity(conn, department=department)
        await _grant(conn, agent_id=agent, venture_id="greenstone", forge_id=FORGE,
                     module_id="alpha", b_ref=str(uuid.uuid4()))
        await conn.commit()

        cert_id = uuid.uuid4()
        first = await certification.repoint_department_grants(
            conn, department=department, forge_id=FORGE, cert_id=cert_id)
        await conn.commit()
        second = await certification.repoint_department_grants(
            conn, department=department, forge_id=FORGE, cert_id=cert_id)
        await conn.commit()

        assert (first, second) == (1, 0)


async def test_a_department_with_no_grants_moves_nothing():
    async with connection() as conn:
        moved = await certification.repoint_department_grants(
            conn, department=f"probe-{uuid.uuid4().hex[:8]}",
            forge_id=FORGE, cert_id=uuid.uuid4())
        await conn.commit()
        assert moved == 0


# ======================================================== through the writers

def test_certify_for_simulation_repoints_and_records_the_count():
    """The act that produced the ruling.

    Source-level because the act needs an `ivan` human and a live declaration, which
    entry 167's own suite stands up and asserts; what this pins is that the path calls
    the re-point and puts the number on the event that names the act - one act, one
    entry, and a reader asking whether Gate 9 can see the certification finds the
    answer beside the certification itself.
    """
    import inspect

    source = inspect.getsource(certification.certify_for_simulation)
    assert "repoint_department_grants" in source
    assert '"grants_repointed": repointed' in source
    # BEFORE the commit: no instant at which a valid certification exists that the
    # gate cannot see.
    assert source.index("repoint_department_grants(") < source.index("await conn.commit()")


def test_record_result_repoints_on_every_unit_b_write():
    """Not only the simulation one. A tested department certification lands through
    `record_result` and has the identical defect.

    Read off the source: the DB paths above prove the update, and this pins that the
    other writer calls it.
    """
    import inspect

    source = inspect.getsource(certification.record_result)
    assert "repoint_department_grants" in source
    assert 'unit == "B"' in source


def test_unit_a_is_deliberately_untouched():
    """`operation_cert_ref` is keyed per (agent, forge, module) and is a separate
    question. Named in entry 181 rather than fixed quietly alongside it."""
    import inspect

    source = inspect.getsource(certification.repoint_department_grants)
    assert "operation_cert_ref" not in source
