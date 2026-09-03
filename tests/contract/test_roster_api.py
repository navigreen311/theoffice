"""A1-A10 - the Village roster, and the denominator the Agents page could not have.

The list rendered the seven agents holding an Office identity and stopped, so a reader
concluded the Village has seven people. It has more; The Office simply had nowhere to
record who, because `office_agent_identity` is a list of agents The Office has
*appointed*, which is a different and smaller set.

The Compliance page hit this first and refused to invent the number - "reporting 0 of
106 against a roster of seven would invent a denominator, on the page whose own copy
insists on real ones". That was right and it left the gap unfixable rather than merely
unreported. `village_agent` is where the roster lives, so the count is a fact this
database can support.

Four properties carry these tests.

**An unimported roster is not an empty Village.** With no roster the page says the roster
is unknown. It never says the Village has seven agents, and it never says 106 either.

**The Office does not create agents.** `issue_identity` refuses an agent the roster has
never reported, and there is no route that adds one.

**A departure is a decision, not a side effect.** Importing a roster that omits an agent
produces a diff an operator confirms, and the diff names the grants that agent still
holds.

**Not declared is not zero.** An agent no Pack appoints has no declared tier, which is a
different state from a low one, and the effective tier is the lower of the two only when
both exist.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker import humans, roster
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db
from tests.world import VILLAGE_DEPARTMENTS

pytestmark = [requires_db, pytest.mark.db]

SEED = uuid.UUID("00000000-0000-5000-8000-00000000dddd")
# A department the live Village has. The Office no longer carries a list to index into:
# it held twelve names, nine of which stopped existing when the Village was rebuilt, and
# a test indexing that tuple was asserting against the same stale copy the code was.
DEPARTMENT = "research"

# What the directory is told the full list is. Read from the same fixture the stub
# Village serves and tests/world.py seeds, rather than typed again here - this was a
# fourth copy of the twelve, and The Office has already had a department list go wrong
# by being kept in more than one place.
ALL_DEPARTMENTS = tuple(name for name, _label, _seats in VILLAGE_DEPARTMENTS)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM agent_forge_grant")
        cur.execute("DELETE FROM certification")
        cur.execute("DELETE FROM shift_assignment")
        cur.execute("DELETE FROM office_agent_identity")
        cur.execute("DELETE FROM village_agent")
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
    conn.commit()


class World:
    def __init__(self, admin: psycopg.Connection, human_id: uuid.UUID, token: str):
        self.admin = admin
        self.human_id = human_id
        self.token = token


@pytest.fixture
async def world(admin: psycopg.Connection):
    _wipe(admin)
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name="Roster operator", email="roster@roster.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role="venture_operator", venture_id=None,
            granted_by=SEED,
        )
    yield World(admin, human_id, token)
    _wipe(admin)


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def entry(ref: str, name: str, department: str = DEPARTMENT) -> dict[str, str]:
    return {
        "village_agent_ref": ref, "agent_name": name, "department": department,
    }


# ============================================ A1 - THE ONE THAT MATTERS MOST

async def test_an_unimported_roster_is_not_an_empty_village(api, world):
    """A1 - seven rows is not a statement about how many agents exist.

    The page has to be able to say "the roster has not been imported", which is true,
    without saying either "the Village has seven agents" or "the Village has 106" - the
    first is wrong and the second is a number this database cannot support.
    """
    body = (await api.get("/api/agents/roster", headers=auth(world.token))).json()

    assert body["roster_imported"] is False
    assert body["roster_total"] == 0
    # And the identities are still reported, as identities - not as the roster.
    assert body["with_identity"] == 0
    assert body["departments_total"] == len(ALL_DEPARTMENTS)


async def test_every_department_is_listed_whether_or_not_anybody_is_in_it(api, world):
    """A2 - nine of twelve departments have nobody, and that was invisible.

    A page that renders the departments it found cannot say which ones it did not find,
    and "no agent in Infrastructure & Cybersecurity has an Office identity" is a
    staffing fact rather than an absence of data.
    """
    body = (await api.get("/api/agents/roster", headers=auth(world.token))).json()
    listed = [d["department"] for d in body["departments"]]

    assert listed == list(ALL_DEPARTMENTS), (
        "the page lists only the departments that have somebody in them"
    )
    assert all(d["with_identity"] == 0 for d in body["departments"])


async def test_every_department_carries_the_word_an_operator_reads(api, world):
    """The label, not the normalized name.

    `broker/departments` keeps both and says why on the two accessors: `department` is
    normalized - `media_production` - and is what a row is grouped and filtered by,
    while `label` is what the Village UI shows - `Media_Production` - and is the word an
    operator read before they typed it. The Agents page rendered the first where the
    second belongs, so it showed `ai_data`, `media_production` and `music_production` as
    headings and eleven of the twelve labels appeared nowhere on it.

    Nothing caught that until the smoke script had a Village to ask, because until then
    the department list was empty and both checks passed over nothing. This asserts it
    at the API, where it costs milliseconds rather than a browser.
    """
    body = (await api.get("/api/agents/roster", headers=auth(world.token))).json()


    expected = {name: label for name, label, _seats in VILLAGE_DEPARTMENTS}

    for group in body["departments"]:
        assert group["label"] == expected[group["department"]]

    # And the two option lists the console builds from this.
    assert [d["label"] for d in body["all_departments"]] == list(expected.values())
    assert [d["department"] for d in body["all_departments"]] == list(expected)


# ==================================== A3-A5 - The Office does not create agents

async def test_an_identity_cannot_be_issued_for_an_agent_the_village_never_reported(
    world,
):
    """A3 - the model, enforced. The Village creates agents; The Office appoints them.

    An identity for somebody the roster has never mentioned is The Office inventing a
    colleague, and it would make `office_agent_identity` a second source of truth for
    who exists.
    """
    async with connection() as conn:
        human = await humans.authenticate(conn, world.token)
        assert human is not None
        with pytest.raises(roster.RosterError) as caught:
            await roster.issue_identity(conn, "village:nobody", human=human)

    assert "not in the Village roster" in str(caught.value)
    assert "does not create agents" in str(caught.value)


async def test_no_route_creates_an_agent():
    """A4 - the surface, enumerated rather than reviewed by eye.

    An "add agent" control would contradict the page's own subtitle and would grow into
    a second roster. What exists is registration - recording an agent the Village has,
    which requires the Village's own reference.
    """
    writes = {
        route.path
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method in ("POST", "PUT", "PATCH", "DELETE")
    }
    agent_writes = {p for p in writes if "/api/agents" in p}

    assert agent_writes == {
        "/api/agents/roster",
        "/api/agents/roster/preview",
        "/api/agents/identities",
        "/api/agents/village",
    }, (
        "the agent write surface changed. None of these creates an agent: they import "
        "what the Village reports, record one it cannot report, and issue identities "
        "for agents that already exist."
    )


async def test_registering_an_agent_requires_the_village_reference(api, world):
    """A5 - without it there is nothing a later import can reconcile against."""
    response = await api.post(
        "/api/agents/village",
        headers=auth(world.token),
        json={"village_agent_ref": "", "agent_name": "Nameless", "department": DEPARTMENT},
    )
    assert response.status_code == 422


# ======================================== A6-A8 - importing, and what it disturbs

async def test_importing_a_roster_previews_before_it_applies(api, world):
    """A6 - an operator confirms a diff, not a promise that something reasonable happens."""
    payload = {"agents": [entry("village:a", "Ada"), entry("village:b", "Bo")]}

    preview = (
        await api.post(
            "/api/agents/roster/preview", headers=auth(world.token), json=payload
        )
    ).json()
    assert len(preview["added"]) == 2
    assert preview["current_total"] == 0

    # Preview wrote nothing.
    body = (await api.get("/api/agents/roster", headers=auth(world.token))).json()
    assert body["roster_total"] == 0

    applied = (
        await api.post("/api/agents/roster", headers=auth(world.token), json=payload)
    ).json()
    assert len(applied["added"]) == 2

    body = (await api.get("/api/agents/roster", headers=auth(world.token))).json()
    assert body["roster_total"] == 2
    assert body["roster_imported"] is True


async def test_a_departure_names_the_grants_that_agent_still_holds(api, world):
    """A7 - the reason the import is confirmed rather than applied.

    An agent that leaves the Village while holding grants is a revocation somebody has
    to perform. A roster import that silently dropped the row would take the evidence
    with it.
    """
    both = {"agents": [entry("village:a", "Ada"), entry("village:b", "Bo")]}
    await api.post("/api/agents/roster", headers=auth(world.token), json=both)

    async with connection() as conn:
        human = await humans.authenticate(conn, world.token)
        assert human is not None
        await roster.issue_identity(conn, "village:b", human=human)

    only_a = {"agents": [entry("village:a", "Ada")]}
    preview = (
        await api.post(
            "/api/agents/roster/preview", headers=auth(world.token), json=only_a
        )
    ).json()

    assert [row["village_agent_ref"] for row in preview["departed"]] == ["village:b"]
    departed = preview["departed"][0]
    assert departed["has_identity"] is True, (
        "the diff does not say the departing agent holds an Office identity, which is "
        "the thing somebody has to act on"
    )


async def test_a_roster_with_an_unknown_department_is_refused(api, world):
    """A8 - an agent in a department no Pack can name is permanently unappointable.

    `source_department` on a position is validated against the same list, so the row
    would be stored and could never be used, for a reason the page could not explain.
    """
    response = await api.post(
        "/api/agents/roster/preview",
        headers=auth(world.token),
        json={"agents": [entry("village:x", "Xan", department="Imaginary Department")]},
    )
    assert response.status_code == 400
    assert "not a Village department" in response.json()["detail"]


# ================================================ A9-A10 - what the page renders

async def test_not_declared_is_not_the_same_as_a_low_tier(world):
    """A9 - an agent no Pack appoints has no declared tier.

    The list rendered an empty declared tier beside a populated certified one, which
    inverts the stated rule: the Pack declares a ceiling and SimForge certifies what was
    earned. A reader could not tell which governed.
    """
    # Neither declared nor certified: nothing to report, and not a tier of zero.
    assert roster._effective(None, None) is None
    # Certified only. The effective tier is what was earned, and the page says the Pack
    # has declared nothing.
    assert roster._effective(None, "auto_execute") == "auto_execute"
    # Both: the lower of the two.
    assert roster._effective("propose", "auto_execute") == "propose"
    assert roster._effective("auto_execute", "suggest") == "suggest"

    # Certified above the declared ceiling is an inconsistency, not a promotion.
    assert roster._exceeds("auto_execute", "propose") is True
    assert roster._exceeds("propose", "auto_execute") is False
    assert roster._exceeds("auto_execute", None) is False


async def test_an_identity_with_no_roster_row_is_reported_not_hidden(api, world):
    """A10 - making two counts agree by losing a row is not making them agree.

    An agent The Office has appointed and the roster cannot account for is a
    discrepancy. Dropping it from the page would make the roster total and the identity
    total consistent, and wrong.
    """
    await api.post(
        "/api/agents/roster",
        headers=auth(world.token),
        json={"agents": [entry("village:a", "Ada")]},
    )
    async with connection() as conn:
        human = await humans.authenticate(conn, world.token)
        assert human is not None
        await roster.issue_identity(conn, "village:a", human=human)

        # An identity with a ref the roster does not contain.
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO office_agent_identity
                  (office_agent_id, village_agent_ref, agent_name, department, status)
                VALUES (%s, 'village:ghost', 'Ghost', %s, 'active')
                """,
                (uuid.uuid4(), DEPARTMENT),
            )
        await conn.commit()

    body = (await api.get("/api/agents/roster", headers=auth(world.token))).json()
    assert body["unmatched_identities"] == 1
    assert any(
        agent["agent_name"] == "Ghost" and agent["in_roster"] is False
        for agent in body["agents"]
    ), "an identity the roster cannot account for is missing from the page entirely"
