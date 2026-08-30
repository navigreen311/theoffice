"""The Compliance page's data, the control runner, and the regulator export.

The page exists to be honest about what is *not* known, which is harder than reporting
what is: an empty incident list and a verified chain look identical whether the checks
ran this morning or have never run at all.

Two properties carry these tests.

**No denominator is invented.** The master prompt describes a Village of 106 agents;
The Office knows about the agents that have actually reached it. Reporting "0 of 106"
against a roster of seven would fabricate a denominator on the one page whose own copy
insists on real ones.

**An export states its own control freshness on its face.** An export produced while
four controls have never run and saying nothing about it is the strongest possible
version of the failure this page exists to prevent - a complete-looking record of an
unchecked system, handed to a regulator.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker import humans
from broker.app import CONTROL_COPY, RUNNABLE_FROM_THE_API, app
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.world import build_world, certify_for_positions, teardown_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
SEED = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


def _wipe(conn: psycopg.Connection) -> None:
    # `wipe_venture` rather than a hand-rolled list. The first version of this deleted
    # business_pack directly and failed with a foreign key violation whenever the smoke
    # script had run first and left a provisioning_run referencing it - the staleness
    # the shared list exists to prevent.
    for venture in (VENTURE, "packless"):
        wipe_venture(conn, venture)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sweep_run")
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
    conn.commit()


@pytest.fixture
def world(admin: psycopg.Connection):
    _wipe(admin)
    build_world(admin)
    certify_for_positions(admin)
    yield admin
    _wipe(admin)
    teardown_world(admin)


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://office.invalid"
    ) as client:
        yield client


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def make(name: str, role: str) -> str:
    async with connection() as conn:
        _id, token = await humans.create_human(
            conn, display_name=name, email=f"{name.lower()}@compliance.invalid"
        )
        await humans.grant_role(
            conn, human_id=_id, role=role, venture_id=None, granted_by=SEED
        )
    return token


# ------------------------------------------------------------------ overview

async def test_every_metric_carries_a_real_denominator(world, api, admin):
    """The page's own rule, applied to the page.

    Each metric is `{value, denominator}` and both come from a count this database can
    actually support. A hardcoded 106 would look more impressive and would be a number
    nobody could verify.
    """
    token = await make("Reader", "compliance_officer")
    body = (await api.get("/api/compliance", headers=auth(token))).json()

    for key in (
        "ventures_live", "agents_with_grants", "frameworks_in_scope",
        "controls_verified",
    ):
        metric = body["scorecard"][key]
        assert "value" in metric and "denominator" in metric, key
        assert metric["value"] <= metric["denominator"], key

    # The denominator is the roster this database actually has, not a constant. Counted
    # rather than written down as 7: the literal passed for the right reason on a clean
    # database and failed on a dirty one, which is a test that reports the state of the
    # fixtures rather than the property under test.
    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM office_agent_identity")
        known = cur.fetchone()[0]
    assert known > 0, "nothing to compare a denominator against"
    assert body["scorecard"]["agents_with_grants"]["denominator"] == known
    assert "roster has not been imported" in body["scorecard"]["agents_with_grants"]["note"]

    assert body["scorecard"]["controls_verified"]["denominator"] == len(CONTROL_COPY)


async def test_every_control_carries_a_name_a_description_and_a_consequence(world, api):
    """A reader unfamiliar with the system must be able to say what each control does.

    `audit_chain` is an identifier, not an explanation. The identifier stays, beside the
    name, because engineers search by it.
    """
    token = await make("Reader", "compliance_officer")
    body = (await api.get("/api/compliance", headers=auth(token))).json()

    assert {c["id"] for c in body["controls"]} == set(CONTROL_COPY)
    for control in body["controls"]:
        assert control["name"] and control["name"] != control["id"]
        assert len(control["checks"]) > 80, "a sentence, not a label"
        assert control["consequence"]
        assert control["cadence"].startswith("Expected ")
        assert isinstance(control["blocking"], bool)


async def test_the_restore_drill_is_marked_unrunnable_with_the_command_that_works(
    world, api
):
    """It needs superuser credentials the API deliberately does not hold.

    A Run button that always fails is worse than no button. The row says why and gives
    the host command instead.
    """
    token = await make("Reader", "compliance_officer")
    body = (await api.get("/api/compliance", headers=auth(token))).json()
    drill = next(c for c in body["controls"] if c["id"] == "restore_drill")

    assert drill["runnable_from_here"] is False
    assert drill["host_command"] == "python -m broker sweep --restore-drill"
    for control in body["controls"]:
        if control["id"] in RUNNABLE_FROM_THE_API:
            assert control["runnable_from_here"] is True
            assert control["host_command"] is None


async def test_framework_coverage_needs_both_a_flag_and_a_library_entry(
    world, api, admin: psycopg.Connection
):
    """The largest gap this rebuild closes: frameworks on the compliance page.

    A framework resolves only when it has a runtime flag AND a Compliance Library entry.
    A flag with no entry reaches the agent as a label rather than a constraint; an entry
    with no flag is never applied to anything.
    """
    from broker import packs

    token = await make("Reader", "compliance_officer")
    source = (
        __import__("pathlib").Path("packs/greenstone.yaml").read_text(encoding="utf-8")
    )
    async with connection() as conn:
        await packs.store(
            conn, yaml_source=source, pack_version="1.0.0", authored_by=SEED
        )

    body = (await api.get("/api/compliance", headers=auth(token))).json()
    venture = next(v for v in body["ventures"] if v["venture_id"] == VENTURE)

    assert venture["declared"] == 2
    assert venture["resolved"] == 2
    assert venture["status"] == "ready"
    assert {f["framework"] for f in venture["frameworks"]} == {
        "TWO_PARTY_CONSENT_RECORDING", "FTC_TSR"
    }

    # Remove the library entries: the frameworks are still declared and no longer
    # resolve, so the venture reports gaps rather than silently reading as covered.
    with admin.cursor() as cur:
        cur.execute("UPDATE compliance_library_entry SET runtime_flag = NULL")
        cur.execute("DELETE FROM compliance_library_entry")
    admin.commit()

    after = (await api.get("/api/compliance", headers=auth(token))).json()
    venture = next(v for v in after["ventures"] if v["venture_id"] == VENTURE)
    assert venture["status"] == "gaps"
    assert venture["resolved"] == 0
    assert all(not f["has_entry"] for f in venture["frameworks"])


async def test_a_venture_with_no_pack_is_blocked_and_says_why(world, api):
    """"blocked" with no reason sends a reader to guess."""
    token = await make("Reader", "compliance_officer")
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO venture_budget (venture_id, monthly_usd_cap, "
            "per_agent_usd_daily_cap, per_task_usd_ceiling) "
            "VALUES ('packless', 100, 10, 1) ON CONFLICT DO NOTHING"
        )
        await conn.commit()

    body = (await api.get("/api/compliance", headers=auth(token))).json()
    venture = next(v for v in body["ventures"] if v["venture_id"] == "packless")
    assert venture["status"] == "blocked"
    assert venture["blocked_because"] == "no Business Pack authored"

    async with connection() as conn, conn.cursor() as cur:
        await cur.execute("DELETE FROM venture_budget WHERE venture_id = 'packless'")
        await conn.commit()


async def test_last_agent_call_is_none_when_nothing_has_called(world, api):
    """The one field that says the system has not started operating."""
    token = await make("Reader", "compliance_officer")
    body = (await api.get("/api/compliance", headers=auth(token))).json()
    assert "last_agent_call" in body["chain_stats"]
    assert "audit_entries" in body["chain_stats"]


# ------------------------------------------------------------ running controls

async def test_running_controls_requires_a_compliance_officer(world, api):
    """A sweep is not read-only: it recomputes staleness and can raise incidents."""
    operator = await make("Operator", "venture_operator")
    refused = await api.post("/api/controls/run", json={}, headers=auth(operator))
    assert refused.status_code == 403


async def test_running_controls_moves_them_out_of_never_run(world, api):
    """The button that closes the loop.

    A page reporting four never-run controls and offering no way to run them has
    described a problem and left the reader holding it.
    """
    token = await make("Officer", "compliance_officer")

    before = (await api.get("/api/compliance", headers=auth(token))).json()
    assert all(c["state"] == "never_run" for c in before["controls"])

    ran = await api.post("/api/controls/run", json={}, headers=auth(token))
    assert ran.status_code == 200
    assert {r["control"] for r in ran.json()["ran"]} == set(RUNNABLE_FROM_THE_API)

    after = (await api.get("/api/compliance", headers=auth(token))).json()
    states = {c["id"]: c["state"] for c in after["controls"]}
    assert states["restore_drill"] == "never_run", "not runnable from here, so unchanged"
    assert all(states[k] != "never_run" for k in RUNNABLE_FROM_THE_API)


async def test_the_restore_drill_cannot_be_triggered_through_the_api(world, api):
    """And the refusal carries the command that does work."""
    token = await make("Officer", "compliance_officer")
    refused = await api.post(
        "/api/controls/run", json={"control": "restore_drill"}, headers=auth(token)
    )
    assert refused.status_code == 400
    assert "superuser credentials" in refused.json()["detail"]
    assert "python -m broker sweep --restore-drill" in refused.json()["detail"]


# -------------------------------------------------------------------- export

async def test_an_export_states_its_own_control_freshness_on_its_face(world, api):
    """The property that makes this a record rather than a data dump.

    An export produced while controls have never run, that says nothing about it, hands
    a regulator a complete-looking document about an unchecked system. This is the test
    that stops that shipping.
    """
    token = await make("Officer", "compliance_officer")

    unchecked = await api.post(
        "/api/compliance/export", json={"venture_id": VENTURE}, headers=auth(token)
    )
    assert unchecked.status_code == 201
    document = unchecked.json()

    statement = document["control_freshness_at_export"]["statement"]
    assert "NOT verified" in statement
    assert "An absence of findings from a check that did not run is not evidence." in statement
    assert "not a clean record" in statement
    assert set(document["control_freshness_at_export"]["unverified"]) == set(CONTROL_COPY)

    # And once they have run, the statement changes rather than disappearing.
    await api.post("/api/controls/run", json={}, headers=auth(token))
    partial = (
        await api.post(
            "/api/compliance/export", json={"venture_id": VENTURE}, headers=auth(token)
        )
    ).json()
    assert "restore_drill" in partial["control_freshness_at_export"]["unverified"]
    assert "NOT verified" in partial["control_freshness_at_export"]["statement"]


async def test_an_export_lists_what_it_did_not_include(world, api):
    """A complete-looking document with silent omissions has misled its reader."""
    token = await make("Officer", "compliance_officer")
    document = (
        await api.post("/api/compliance/export", json={}, headers=auth(token))
    ).json()

    joined = " ".join(document["not_included"])
    assert "SimForge" in joined
    assert "Held-out" in joined
    assert "Forge-side attribution" in joined
    assert len(document["not_included"]) >= 4


async def test_an_export_is_hash_stamped_and_says_it_is_not_signed(world, api):
    """A fabricated signature would prove nothing while appearing to prove provenance."""
    token = await make("Officer", "compliance_officer")
    document = (
        await api.post("/api/compliance/export", json={}, headers=auth(token))
    ).json()

    assert document["integrity"]["signed"] is False
    assert len(document["integrity"]["content_hash"]) == 64
    assert "not signed" in document["integrity"]["note"]
    assert "no key material" in document["integrity"]["note"]


async def test_producing_an_export_is_audited(world, api, admin: psycopg.Connection):
    """Handing records to a regulator is an act somebody performed."""
    token = await make("Officer", "compliance_officer")
    document = (
        await api.post(
            "/api/compliance/export", json={"venture_id": VENTURE}, headers=auth(token)
        )
    ).json()

    with admin.cursor() as cur:
        cur.execute(
            "SELECT subject FROM audit_log WHERE event_type = 'console_compliance_exported' "
            "ORDER BY audit_id DESC LIMIT 1"
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0]["content_hash"] == document["integrity"]["content_hash"]
    assert row[0]["unverified_controls"]


async def test_a_venture_operator_cannot_export_another_ventures_record(world, api):
    token = await make("Operator", "venture_operator")
    refused = await api.post(
        "/api/compliance/export", json={"venture_id": VENTURE}, headers=auth(token)
    )
    assert refused.status_code == 403
