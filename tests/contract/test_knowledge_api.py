"""The Knowledge Base Manager's routes.

Five new write routes, and the reason each is safe is the same as always: it delegates
to a guarded function. None of them touches a control - a playbook is an SOP, a
compliance entry is what *explains* a flag rather than what applies one, a persona is
SimForge input, and a historical record is append-only by grant.

The one worth reading twice is the persona route. It writes and there is deliberately no
route that reads a body back, because `office_app` holds no SELECT on the column. A read
route would be a privilege error rather than a leak - which is the difference between a
boundary and a habit, and is the only reason this store is safe to expose to a console
at all.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker import humans
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

MINE = "greenstone"
THEIRS = "burkham-wickmont"
AUTHOR = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")

ENTRY = {
    "entry_ref": "test/api-tsr",
    "framework": "FTC_TSR",
    "jurisdiction": ["FEDERAL"],
    "applicability_rule": "Outbound cold calls.",
    "agent_behavior_implication": "State identity and purpose before anything else.",
    "escalation_trigger": "The called party asserts a do-not-call registration.",
    "citation": "16 CFR 310",
}


@pytest.fixture(autouse=True)
def _clean(admin: psycopg.Connection):
    _wipe(admin)
    yield
    _wipe(admin)


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM playbook_share")
        cur.execute("DELETE FROM business_playbook")
        cur.execute("DELETE FROM compliance_library_entry WHERE entry_ref LIKE 'test/%'")
        cur.execute("DELETE FROM persona WHERE venture_id = ANY(%s)", ([MINE, THEIRS],))
        cur.execute(
            "ALTER TABLE historical_record DISABLE TRIGGER historical_record_append_only"
        )
        cur.execute(
            "DELETE FROM historical_record WHERE venture_id = ANY(%s)", ([MINE, THEIRS],)
        )
        cur.execute(
            "ALTER TABLE historical_record ENABLE TRIGGER historical_record_append_only"
        )
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
    conn.commit()


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://office.invalid"
    ) as client:
        yield client


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def make_human(name: str, role: str, venture: str | None = MINE) -> str:
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name, email=f"{name.lower()}@kb.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role=role, venture_id=venture, granted_by=AUTHOR
        )
    return token


# ------------------------------------------------------------------- coverage

async def test_coverage_reports_a_denominator_for_every_store(api):
    """The Manager's reason to exist, and the rule this console has followed since
    increment 2: no green check without a coverage count."""
    token = await make_human("Reader", "venture_operator")
    body = (await api.get("/api/knowledge/coverage", headers=auth(token))).json()

    for store in (
        "forge_operating_instructions", "compliance_library", "business_playbooks",
        "persona_library", "historical_records",
    ):
        assert store in body, f"{store} is not reported"
        assert "blocking" in body[store], f"{store} does not say whether it blocks"
        assert body[store]["note"], f"{store} has no explanation of what it is"

    assert body["forge_operating_instructions"]["blocking"] is True
    assert body["compliance_library"]["blocking"] is True
    assert body["business_playbooks"]["blocking"] is False
    assert body["persona_library"]["blocking"] is False

    assert "denominator" in body["forge_operating_instructions"]
    assert "uncovered" in body["compliance_library"]


# ------------------------------------------------------------------ playbooks

async def test_playbooks_are_not_readable_without_a_venture(api):
    """There is no unscoped read, and the route does not offer one.

    A caller that got "all playbooks" would be one forgotten filter away from showing a
    venture another venture's SOPs, and that call site would look exactly like every
    other one.
    """
    token = await make_human("Reader", "venture_operator")
    await api.post(
        "/api/knowledge/playbooks",
        json={"venture_id": MINE, "title": "Opener", "playbook_version": "1.0.0",
              "content": {"steps": ["a"]}},
        headers=auth(token),
    )
    unscoped = (await api.get("/api/knowledge/playbooks", headers=auth(token))).json()
    assert unscoped["playbooks"] == []

    scoped = (
        await api.get(f"/api/knowledge/playbooks?venture_id={MINE}", headers=auth(token))
    ).json()
    assert [p["title"] for p in scoped["playbooks"]] == ["Opener"]


async def test_sharing_is_authorised_against_the_owner_not_the_recipient(api):
    """The owner consents to disclosure. The recipient has nothing to consent to.

    Checking the recipient's operator instead would let a venture help itself to
    another's SOPs by having its own operator click the button.
    """
    owner = await make_human("Owner", "venture_operator", MINE)
    recipient = await make_human("Recipient", "venture_operator", THEIRS)

    written = (
        await api.post(
            "/api/knowledge/playbooks",
            json={"venture_id": MINE, "title": "Opener", "playbook_version": "1.0.0",
                  "content": {"steps": ["a"]}},
            headers=auth(owner),
        )
    ).json()

    helping_themselves = await api.post(
        "/api/knowledge/playbooks/share",
        json={"playbook_id": written["playbook_id"], "to_venture_id": THEIRS,
              "reason": "I would like this"},
        headers=auth(recipient),
    )
    assert helping_themselves.status_code == 403

    consented = await api.post(
        "/api/knowledge/playbooks/share",
        json={"playbook_id": written["playbook_id"], "to_venture_id": THEIRS,
              "reason": "same outbound motion, reviewed by both operators"},
        headers=auth(owner),
    )
    assert consented.status_code == 200

    theirs = (
        await api.get(
            f"/api/knowledge/playbooks?venture_id={THEIRS}", headers=auth(recipient)
        )
    ).json()
    assert [p["title"] for p in theirs["playbooks"]] == ["Opener"]
    assert theirs["playbooks"][0]["shared_from"] == MINE


# ---------------------------------------------------------- compliance library

async def test_an_incomplete_compliance_entry_is_refused_by_the_schema(api):
    """All six of Part 6.3's fields, refused before the domain function sees it."""
    token = await make_human("Officer", "compliance_officer", None)
    incomplete = dict(ENTRY)
    del incomplete["agent_behavior_implication"]

    response = await api.post(
        "/api/knowledge/compliance", json=incomplete, headers=auth(token)
    )
    assert response.status_code == 422


async def test_writing_an_entry_says_what_it_unblocks(api):
    """The consequence is not visible from the form: writing an entry changes what
    every Pack resolves and what Gate 6 considers explained."""
    token = await make_human("Officer", "compliance_officer", None)
    response = await api.post(
        "/api/knowledge/compliance",
        json={**ENTRY, "runtime_flag": "tsr_disclosure_required"},
        headers=auth(token),
    )
    assert response.status_code == 201
    assert "Gate 6" in response.json()["note"]

    listed = (await api.get("/api/knowledge/compliance", headers=auth(token))).json()
    assert any(e["entry_ref"] == ENTRY["entry_ref"] for e in listed)


async def test_a_venture_operator_cannot_write_a_portfolio_wide_entry(api):
    """The library is portfolio-wide, so authority is too.

    An entry changes what every Pack's `library_entry_ref` resolves against. That is not
    a per-venture decision, and a venture operator authorised for one venture would be
    making it for all of them.
    """
    token = await make_human("Operator", "venture_operator", MINE)
    response = await api.post(
        "/api/knowledge/compliance", json=ENTRY, headers=auth(token)
    )
    assert response.status_code == 403


# --------------------------------------------------------------------- persona

async def test_a_persona_body_appears_in_no_response(api):
    """K8 at the HTTP boundary.

    The column privilege makes a read fail. This makes it observable: the body written
    here is a distinctive string, and it must not come back from any knowledge route -
    including the one that just accepted it.
    """
    token = await make_human("Operator", "venture_operator", MINE)
    marker = "persona-body-marker-8f2c1e"

    written = await api.post(
        "/api/knowledge/personas",
        json={"venture_id": MINE, "persona_name": "Stalled broker",
              "target_persona": "Regional broker", "persona_version": "1.0.0",
              "persona_body": {"disposition": marker}},
        headers=auth(token),
    )
    assert written.status_code == 201
    assert marker not in written.text, "the write response echoed the body back"

    for path in (
        "/api/knowledge/coverage",
        f"/api/knowledge/personas?venture_id={MINE}",
        "/api/knowledge/history",
        "/api/audit?limit=100",
    ):
        response = await api.get(path, headers=auth(token))
        assert marker not in response.text, f"{path} leaked a persona body"

    index = (
        await api.get(f"/api/knowledge/personas?venture_id={MINE}", headers=auth(token))
    ).json()["rows"]
    assert index[0]["persona_name"] == "Stalled broker"
    assert "persona_body" not in index[0]
    assert len(index[0]["body_hash"]) == 64


async def test_there_is_no_route_that_reads_a_persona_body(api):
    """The absent capability, enumerated rather than assumed.

    `test_no_module_reads_a_persona_body` covers the source. This covers the surface: a
    route added later that returned a body would fail the first test, and a route that
    merely *looks* like one should not resolve at all.
    """
    paths = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    for path, _method in paths:
        assert "persona_body" not in path

    token = await make_human("Operator", "venture_operator", MINE)
    for candidate in (
        "/api/knowledge/personas/body", "/api/knowledge/persona-bodies",
    ):
        assert (await api.get(candidate, headers=auth(token))).status_code in (404, 405)


# --------------------------------------------------------------------- history

async def test_a_note_is_recorded_against_the_human_who_wrote_it(api):
    """Part 9: humans sign, not agents."""
    token = await make_human("Operator", "venture_operator", MINE)
    response = await api.post(
        "/api/knowledge/history",
        json={"summary": "Decided to defer the capacity amendment", "venture_id": MINE},
        headers=auth(token),
    )
    assert response.status_code == 201

    rows = (
        await api.get(f"/api/knowledge/history?venture_id={MINE}", headers=auth(token))
    ).json()["rows"]
    assert rows[0]["summary"] == "Decided to defer the capacity amendment"
    assert rows[0]["actor_type"] == "human"
    assert rows[0]["recorded_by"] is not None


async def test_the_deletable_flags_are_read_from_the_grants(api):
    """A page may not claim a capability the role does not hold.

    `personas_deletable` was `True`, reasoned from "personas are never production data".
    That is true and irrelevant: `office_app` holds INSERT and UPDATE on `persona` and no
    DELETE, so the console could not have purged one, and the overview offered an action
    the system does not support. The flags are read from
    `information_schema.table_privileges` now, so a later GRANT moves the page instead of
    leaving it asserting yesterday's privileges.
    """
    token = await make_human("Operator", "venture_operator", MINE)
    fixtures = (
        await api.get("/api/knowledge/overview", headers=auth(token))
    ).json()["fixtures"]

    assert fixtures["records_deletable"] is False, (
        "historical_record is append-only; nothing should report it as deletable"
    )
    assert fixtures["personas_deletable"] is False, (
        "office_app holds no DELETE on persona, so the console cannot purge one"
    )


async def test_there_is_no_route_that_purges_a_knowledge_store(api):
    """The absent capability, enumerated rather than assumed.

    A purge route added later would need a grant this role does not have, and adding the
    grant is the part worth noticing: `persona` is write-only by design and
    `historical_record` is append-only by design.
    """
    paths = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    for path, method in paths:
        if method in {"DELETE"}:
            assert "knowledge" not in path, f"{method} {path} deletes from a knowledge store"
        assert "purge" not in path.lower()


async def test_excluding_fixtures_is_recorded_rather_than_applied(api):
    """The brief's own rule, at the boundary.

    Filtering rows out of a count is a judgement. A judgement nobody wrote down is
    indistinguishable from a filter nobody noticed, which is how sixty smoke personas
    came to read as a library.
    """
    token = await make_human("Operator", "venture_operator", MINE)

    # A fixture the derived origin will recognise, so there is something to exclude.
    await api.post(
        "/api/knowledge/personas",
        json={"venture_id": MINE, "persona_name": "Smoke 774411",
              "target_persona": "Regional broker", "persona_version": "1.0.0",
              "persona_body": {"disposition": "generated by a smoke run"}},
        headers=auth(token),
    )

    before = (
        await api.get("/api/knowledge/overview", headers=auth(token))
    ).json()["fixtures"]
    assert before["personas"] >= 1, "the fixture was not recognised as one"

    response = await api.post(
        "/api/knowledge/fixtures/exclude", json={}, headers=auth(token)
    )
    assert response.status_code == 201

    rows = (
        await api.get("/api/knowledge/history", headers=auth(token))
    ).json()["rows"]
    written = [r for r in rows if r["record_type"] == "knowledge_fixture_exclusion"]
    assert written, "the exclusion was applied without being recorded"
    assert str(before["personas"]) in written[0]["summary"], (
        "the record does not say how much was excluded"
    )
    assert written[0]["actor_type"] == "human", "a person decided this, not the system"

    # And the fixture is still there. Excluding is a reading decision; the row is
    # untouched, which is what makes the record the only evidence of the decision.
    after = (
        await api.get(
            "/api/knowledge/personas?include_fixtures=true", headers=auth(token)
        )
    ).json()
    assert any(r["persona_name"] == "Smoke 774411" for r in after["rows"]), (
        "the fixture was removed; exclusion must not delete"
    )

async def test_history_has_no_write_route_that_edits_or_deletes(api):
    """Append-only reaches the API surface as an absence, not a guard."""
    writes = {
        path
        for route in app.routes
        for path in [route.path]
        for method in getattr(route, "methods", set())
        if method in ("PUT", "PATCH", "DELETE")
    }
    assert writes == set(), f"the API has non-POST write routes: {writes}"


async def test_every_knowledge_read_requires_a_session(api):
    for path in (
        "/api/knowledge/coverage", "/api/knowledge/playbooks",
        "/api/knowledge/compliance", "/api/knowledge/personas",
        "/api/knowledge/history",
    ):
        assert (await api.get(path)).status_code == 401, path
