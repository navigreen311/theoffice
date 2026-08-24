"""V1-V10 - the venture directory, and the two states nothing can derive.

The old directory answered five questions nobody was asking. The question a reader opens
this page with is *where is this venture and can it go live*, and pipeline state - a
venture's most important attribute - appeared nowhere.

Two properties carry these tests.

**Status is derived, not stored.** A venture blocked at Gate 0 is blocked because the
validator says the bridge does not reach its operating Forge. The only stored states are
the two nothing can derive: `archived`, and the draft that exists before a Pack does.

**The blocked sentence comes from the rule that failed.** The brief that specified this
page supplied three example blockers and one of them - "structural PHI flush is not
built" - had stopped being true when Phase 3.3 shipped. A lookup table of blocker
strings is right the day it is written; this asserts the sentence is computed.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker import humans, packs, ventures
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.world import PACK_PATH, build_world, certify_for_positions, teardown_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
SEED = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


def _wipe(conn: psycopg.Connection) -> None:
    for slug in (VENTURE, "collingswood", "test-venture", "medlink-pro"):
        wipe_venture(conn, slug)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM venture")
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


async def make(name: str, role: str, venture: str | None = None) -> str:
    async with connection() as conn:
        _id, token = await humans.create_human(
            conn, display_name=name, email=f"{name.lower()}@ventures.invalid"
        )
        await humans.grant_role(
            conn, human_id=_id, role=role, venture_id=venture, granted_by=SEED
        )
    return token


async def publish_greenstone() -> None:
    async with connection() as conn:
        await packs.store(
            conn,
            yaml_source=PACK_PATH.read_text(encoding="utf-8"),
            pack_version="1.0.0",
            authored_by=SEED,
        )


# ------------------------------------------------------------------ creation

async def test_a_new_venture_is_a_draft_and_holds_nothing(world, api):
    """V1 - draft means no Pack, which means nothing to grant against.

    The inability to receive grants is structural rather than a flag: without a Pack
    there is no manifest and no runtime config, so there is nothing for a grant to be
    issued from.
    """
    token = await make("Officer", "compliance_officer")

    created = await api.post(
        "/api/ventures",
        json={"display_name": "Collingswood & Co.", "category": "Outbound voice"},
        headers=auth(token),
    )
    assert created.status_code == 201
    assert created.json()["slug"] == "collingswood-co"
    assert "Draft" in created.json()["note"]

    directory = (await api.get("/api/ventures/directory", headers=auth(token))).json()
    venture = next(v for v in directory["ventures"] if v["slug"] == "collingswood-co")

    assert venture["status"] == "draft"
    assert venture["has_pack"] is False
    assert venture["live_grants"] == 0
    assert venture["positions_defined"] == 0
    assert venture["monthly_usd_cap"] is None
    assert "No Business Pack" in venture["blocked_because"]


async def test_the_slug_is_derived_and_immutable(world, api):
    """V2 - a slug is a key, not a label.

    Every venture-scoped table stores it as text, so a typo produces a second venture
    rather than an error. It is derived from the name, editable at creation, and the
    primary key afterwards.
    """
    assert ventures.slugify("Collingswood & Co.") == "collingswood-co"
    assert ventures.slugify("  MedLink   Pro  ") == "medlink-pro"
    with pytest.raises(ventures.VentureError):
        ventures.slugify("!!!")

    token = await make("Officer", "compliance_officer")
    made = await api.post(
        "/api/ventures",
        json={"display_name": "Test Venture", "slug": "test-venture",
              "category": "Testing"},
        headers=auth(token),
    )
    assert made.status_code == 201

    duplicate = await api.post(
        "/api/ventures",
        json={"display_name": "Something else", "slug": "test-venture",
              "category": "Testing"},
        headers=auth(token),
    )
    assert duplicate.status_code == 400
    assert "already exists" in duplicate.json()["detail"]


@pytest.mark.parametrize("slug", ["Not A Slug", "trailing-", "UPPER", "has space"])
async def test_a_malformed_slug_is_refused(world, api, slug):
    token = await make("Officer", "compliance_officer")
    response = await api.post(
        "/api/ventures",
        json={"display_name": "X", "slug": slug, "category": "Testing"},
        headers=auth(token),
    )
    assert response.status_code == 400
    assert "slug" in response.json()["detail"]


async def test_creation_is_audited_with_the_human_as_actor(
    world, api, admin: psycopg.Connection
):
    """V3 - Part 9: humans sign, not agents."""
    token = await make("Officer", "compliance_officer")
    await api.post(
        "/api/ventures",
        json={"display_name": "Test Venture", "category": "Testing"},
        headers=auth(token),
    )

    with admin.cursor() as cur:
        cur.execute(
            "SELECT subject FROM audit_log WHERE event_type = 'console_venture_created' "
            "ORDER BY audit_id DESC LIMIT 1"
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0]["slug"] == "test-venture"
    assert row[0]["human"] == "Officer"


async def test_a_venture_operator_cannot_create_a_venture(world, api):
    """Creating one commits a slug for the rest of its life, and a venture operator is
    scoped to a venture that does not exist yet."""
    token = await make("Operator", "venture_operator", VENTURE)
    response = await api.post(
        "/api/ventures",
        json={"display_name": "X", "category": "Testing"},
        headers=auth(token),
    )
    assert response.status_code == 403


# ------------------------------------------------------------- blocked state

async def test_blocked_names_the_gate_and_the_specific_blocker(
    world, api, admin: psycopg.Connection
):
    """V4 and V5 - the headline of this rebuild.

    "Blocked" alone tells a reader nothing they can act on. The status carries the gate
    number and the sentence names the Forge, and both come from the validator rather
    than from a table of blocker strings - one of the examples this page was specified
    with had already stopped being true.
    """
    token = await make("Officer", "compliance_officer")
    await publish_greenstone()

    # Break the world, not the Pack: Gate 0 exists to catch exactly this.
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE forge_registry SET health_status = 'RED' WHERE forge_id = 'cre-forge'"
        )
    admin.commit()

    directory = (await api.get("/api/ventures/directory", headers=auth(token))).json()
    venture = next(v for v in directory["ventures"] if v["slug"] == VENTURE)

    assert venture["status"] == "blocked at gate 0"
    assert venture["gate"] == "0"
    assert "cre-forge" in venture["blocked_because"]
    assert "granted or appointed" in venture["blocked_because"]

    # The phase bar puts it in the first of six phases.
    assert venture["phases"][0]["state"] == "current"
    assert all(p["state"] == "todo" for p in venture["phases"][1:])


async def test_a_bridged_venture_is_no_longer_blocked_at_gate_zero(world, api):
    """The other direction. A rule that only ever fails is an outage."""
    token = await make("Officer", "compliance_officer")
    await publish_greenstone()

    directory = (await api.get("/api/ventures/directory", headers=auth(token))).json()
    venture = next(v for v in directory["ventures"] if v["slug"] == VENTURE)

    assert venture["status"] != "blocked at gate 0"
    assert venture["operating_forge"] == "cre-forge"
    assert venture["display_name"] == "Greenstone", "the Pack's name wins over the slug"


def test_the_phase_bar_maps_every_gate(world):
    """Sixteen gates into six phases, with none of them lost on the way."""
    from broker.provisioning import GATE_SEQUENCE

    mapped = [g for _name, gates in ventures.GATE_PHASES for g in gates]
    assert mapped == list(GATE_SEQUENCE), "a gate is in the wrong phase or missing"

    assert [p.state for p in ventures.phases_for(None, live=False)] == ["todo"] * 6
    assert [p.state for p in ventures.phases_for("12", live=True)] == ["done"] * 6
    mid = ventures.phases_for("5", live=False)
    assert [p.state for p in mid] == ["done", "done", "done", "current", "todo", "todo"]


# ------------------------------------------------------------------ the panel

async def test_the_unauthored_portfolio_ventures_are_reported_as_missing(world, api):
    """V7 - absence must not be able to look like health.

    Four of the five named ventures have no Pack. Rendering only what exists would make
    the portfolio look like one venture that happens to be fine.
    """
    token = await make("Officer", "compliance_officer")
    await publish_greenstone()

    directory = (await api.get("/api/ventures/directory", headers=auth(token))).json()

    assert directory["portfolio_size"] == 5
    missing = {m["slug"] for m in directory["missing"]}
    assert missing == {"medlink-pro", "collingswood", "burkham-wickmont", "cyber"}
    for gap in directory["missing"]:
        assert gap["display_name"] and gap["category"] and gap["frameworks"]
        assert gap["note"], "a missing venture says why it matters"


async def test_authoring_one_removes_it_from_the_missing_panel(world, api):
    """V8 - computed against what exists, not asserted.

    A hardcoded list of absent ventures would go on claiming a venture is unauthored
    after somebody authors it, which is the rot Gate 6's knowledge-base list had.
    """
    token = await make("Officer", "compliance_officer")
    before = (await api.get("/api/ventures/directory", headers=auth(token))).json()
    assert "medlink-pro" in {m["slug"] for m in before["missing"]}

    await api.post(
        "/api/ventures",
        json={"display_name": "MedLink Pro Staffing", "slug": "medlink-pro",
              "category": "Healthcare staffing"},
        headers=auth(token),
    )

    after = (await api.get("/api/ventures/directory", headers=auth(token))).json()
    assert "medlink-pro" not in {m["slug"] for m in after["missing"]}
    assert "medlink-pro" in {v["slug"] for v in after["ventures"]}


# ------------------------------------------------------------------ lifecycle

async def test_archiving_is_audited_and_revokes_nothing(
    world, api, admin: psycopg.Connection
):
    """V9 - a venture's grants and its ledger outlive the decision to stop operating it.

    Collapsing archive into revoke would make archiving a quiet way to pull authority
    with no revocation record.
    """
    token = await make("Officer", "compliance_officer")
    await api.post(
        "/api/ventures",
        json={"display_name": "Test Venture", "category": "Testing"},
        headers=auth(token),
    )

    no_reason = await api.post(
        "/api/ventures/test-venture/lifecycle",
        json={"state": "archived", "reason": ""}, headers=auth(token),
    )
    assert no_reason.status_code == 422

    archived = await api.post(
        "/api/ventures/test-venture/lifecycle",
        json={"state": "archived", "reason": "never started"}, headers=auth(token),
    )
    assert archived.status_code == 200

    directory = (await api.get("/api/ventures/directory", headers=auth(token))).json()
    venture = next(v for v in directory["ventures"] if v["slug"] == "test-venture")
    assert venture["status"] == "archived"

    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM revocation")
        assert cur.fetchone()[0] == 0, "archiving must not revoke anything"

    reopened = await api.post(
        "/api/ventures/test-venture/lifecycle",
        json={"state": "draft", "reason": "picked it back up"}, headers=auth(token),
    )
    assert reopened.status_code == 200
    after = (await api.get("/api/ventures/directory", headers=auth(token))).json()
    assert next(
        v for v in after["ventures"] if v["slug"] == "test-venture"
    )["status"] == "draft"


# ----------------------------------------------------------------- the numbers

async def test_every_metric_carries_a_denominator(world, api):
    """V6 - the page's own rule."""
    token = await make("Officer", "compliance_officer")
    await publish_greenstone()

    directory = (await api.get("/api/ventures/directory", headers=auth(token))).json()
    for key in ("live", "agents_appointed", "spend_this_month", "blocked"):
        metric = directory["scorecard"][key]
        assert "value" in metric and "denominator" in metric, key

    venture = next(v for v in directory["ventures"] if v["slug"] == VENTURE)
    assert venture["positions_defined"] > 0, "the Pack defines seven positions"
    assert venture["positions_filled"] <= venture["positions_defined"]


async def test_a_venture_with_no_budget_reads_unmetered_not_zero(world, api):
    """V10 - and the distinction is the whole content of the V18 footnote.

    "Unmetered" means no budget row exists. A zero cap would mean somebody set one to
    zero, which is a different decision with a different consequence.
    """
    token = await make("Officer", "compliance_officer")
    await api.post(
        "/api/ventures",
        json={"display_name": "Test Venture", "category": "Testing"},
        headers=auth(token),
    )

    directory = (await api.get("/api/ventures/directory", headers=auth(token))).json()
    venture = next(v for v in directory["ventures"] if v["slug"] == "test-venture")
    assert venture["monthly_usd_cap"] is None, "None, never 0 - they mean different things"


async def test_spend_reports_zero_because_nothing_is_measured(world, api):
    """`usd_cost` is never populated - the stub Forge reports no usage.

    A spend figure of zero would be read as "nothing spent". The note is what makes it
    "nothing measured", and those are different claims.
    """
    token = await make("Officer", "compliance_officer")
    directory = (await api.get("/api/ventures/directory", headers=auth(token))).json()
    note = directory["scorecard"]["spend_this_month"]["note"]
    assert "not wired" in note
    assert "nothing is measured" in note


# ---------------------------------------------- a bug found while building this

async def test_the_three_capacity_numbers_sum_to_the_active_roster(
    world, api, admin: psycopg.Connection
):
    """§7.2: all three, always - one hides the state. So must all three.

    An agent with no certification row appeared in NONE of them: `bool_or` over zero
    rows is NULL, and `NOT NULL` is NULL rather than TRUE, so every filter excluded
    them. Three numbers that quietly omit somebody are a worse version of the single
    number they replace, and nothing would have shown it - the totals simply did not
    add up, and nobody was adding them.
    """
    agent_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_agent_identity (office_agent_id, village_agent_ref, "
            "agent_name, department, status) "
            "VALUES (%s, %s, 'Uncertified Agent', 'AI & Data Science', 'active')",
            (agent_id, f"village::uncert-{agent_id.hex[:8]}"),
        )
        cur.execute("SELECT count(*) FROM office_agent_identity WHERE status = 'active'")
        roster = cur.fetchone()[0]
    admin.commit()

    try:
        token = await make("Capacity", "compliance_officer")
        capacity = (
            await api.get(f"/api/ventures/{VENTURE}/capacity", headers=auth(token))
        ).json()

        total = (
            capacity["certified_and_free"]
            + capacity["certified_but_allocated"]
            + capacity["produced_not_yet_certified"]
        )
        assert total == roster, (
            f"the three numbers sum to {total} against a roster of {roster}; "
            "somebody is in none of them"
        )
        assert capacity["produced_not_yet_certified"] >= 1, (
            "an agent nobody has certified is produced-but-not-certified, which is a "
            "state rather than an absence of one"
        )
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM office_agent_identity WHERE office_agent_id = %s",
                (agent_id,),
            )
        admin.commit()
