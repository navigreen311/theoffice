"""Incidents: a published taxonomy, a detection that cannot be edited, an appended response."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest

from broker import humans
from broker import incident_taxonomy as taxonomy
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.world import build_world

pytestmark = [requires_db, pytest.mark.db]

MINE = "greenstone"
SEED = uuid.UUID("00000000-0000-5000-8000-00000000dddd")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wipe(conn: psycopg.Connection) -> None:
    """Clear what these tests write.

    `incident_account` refuses DELETE by trigger, which is the point of it, so the
    teardown disables the trigger for the duration rather than reaching for a second
    table or a softer guard. Doing this in application code would defeat the control;
    doing it in a fixture running as the admin role is housekeeping, and
    `test_the_account_store_refuses_an_edit` proves the trigger is back on afterwards by
    exercising it through the app role.
    """
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE incident_account DISABLE TRIGGER incident_account_append_only"
        )
        cur.execute("DELETE FROM incident_account")
        cur.execute(
            "ALTER TABLE incident_account ENABLE TRIGGER incident_account_append_only"
        )
        cur.execute("DELETE FROM incident_resolution")
        cur.execute("DELETE FROM incident")
    wipe_venture(conn, MINE)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
    conn.commit()


@pytest.fixture(autouse=True)
def world(admin: psycopg.Connection):
    _wipe(admin)
    build_world(admin)
    yield
    _wipe(admin)


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def make_human(name: str, role: str, venture_id: str | None) -> str:
    """A human holding one role, and their bearer token."""
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name, email=f"{name.lower()}@incidents.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role=role, venture_id=venture_id, granted_by=SEED
        )
    return token


# ------------------------------------------------------------------ the taxonomy

async def test_every_incident_kind_raised_in_the_source_is_published():
    """The taxonomy is derived from the call sites, and this is what keeps it derived.

    `kind` had no constraint at all before this, so any string was a kind and a column
    with a schema-shaped name was a free-text field. Publishing a list fixes that only
    for as long as the list matches the code: a kind added to `sweeps.py` and not to
    `incident_taxonomy.py` would fail at the database, but only when that condition
    actually occurred, which for a sweep might be months.

    So the source is walked. Every `kind="..."` passed to `raise_incident` must be
    published, and the failure names the file.
    """
    root = Path(__file__).resolve().parents[2] / "broker"
    pattern = re.compile(r"raise_incident\((.*?)\)", re.S)
    kind_arg = re.compile(r'kind="([a-z_]+)"')

    unpublished: list[tuple[str, str]] = []
    found = 0
    for source in root.glob("*.py"):
        if source.name in ("incidents.py", "incident_taxonomy.py"):
            continue
        text = source.read_text(encoding="utf-8")
        for call in pattern.findall(text):
            for kind in kind_arg.findall(call):
                found += 1
                if kind not in taxonomy.BY_KIND:
                    unpublished.append((source.name, kind))

    assert found > 0, "the walker matched no raise_incident call; the pattern is stale"
    assert not unpublished, (
        f"these kinds are raised but not published in incident_taxonomy.py: "
        f"{unpublished}. A kind the taxonomy does not list is one the database now "
        f"refuses, and the page cannot label."
    )


async def test_the_published_taxonomy_matches_the_database_constraint(
    admin: psycopg.Connection,
):
    """Migration 0023 imports the taxonomy rather than retyping it. This proves it.

    A constraint written by hand from the same list is the same list twice, and the two
    copies diverge the first time one is edited.
    """
    with admin.cursor() as cur:
        cur.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'incident_kind_check'"
        )
        row = cur.fetchone()

    assert row is not None, "incident.kind has no constraint; it is free text again"
    for kind in taxonomy.KIND_NAMES:
        assert f"'{kind}'" in row[0], f"{kind} is published but the database refuses it"


async def test_the_taxonomy_route_serves_what_the_module_holds(api):
    token = await make_human("Operator", "venture_operator", MINE)
    served = (await api.get("/api/incidents/taxonomy", headers=auth(token))).json()

    assert [k["kind"] for k in served["kinds"]] == list(taxonomy.KIND_NAMES)
    assert [s["value"] for s in served["severities"]] == list(taxonomy.SEVERITIES)
    assert [s["stage"] for s in served["stages"]] == list(taxonomy.STAGE_NAMES)


# --------------------------------------------------------------- filing by hand

async def test_a_person_can_file_the_two_sources_a_control_cannot_detect(api):
    """Part 9 names three detection sources; only agent flag arrives on its own.

    A regulator's question and a client's complaint had nowhere to go, so they lived in
    somebody's inbox while this page showed an empty list - and an empty list reads as
    calm.
    """
    token = await make_human("Officer", "compliance_officer", MINE)

    response = await api.post(
        "/api/incidents",
        json={
            "severity": "HIGH", "kind": "regulator_inquiry",
            "detection_source": "regulator_inquiry",
            "summary": "State regulator asked how consent is recorded.",
            "venture_id": MINE,
        },
        headers=auth(token),
    )
    assert response.status_code == 201
    incident_id = response.json()["incident_id"]

    detail = (
        await api.get(f"/api/incidents/{incident_id}", headers=auth(token))
    ).json()
    assert detail["detection_source"] == "regulator_inquiry"
    assert detail["reported_by_name"] is not None, (
        "a hand-filed incident must name who filed it; otherwise it is "
        "indistinguishable from one a control caught"
    )
    # The summary becomes the detection *and* opens the timeline, so the response starts
    # with what was seen rather than with whoever first opened the page.
    detection = next(s for s in detail["stages"] if s["stage"] == "detection")
    assert detection["accounted"] is True


async def test_a_control_kind_cannot_be_filed_by_hand(api):
    """Filing `audit_chain_broken` by hand would claim a check ran that did not.

    The same class of untruth as counting a test fixture as content: the row exists, and
    what it asserts about the system did not happen.
    """
    token = await make_human("Officer", "compliance_officer", MINE)
    response = await api.post(
        "/api/incidents",
        json={
            "severity": "HIGH", "kind": "audit_chain_broken",
            "detection_source": "external_report", "summary": "someone told me",
            "venture_id": MINE,
        },
        headers=auth(token),
    )
    assert response.status_code == 400
    assert "raised by a control" in response.json()["detail"]


async def test_an_incident_needs_an_account_not_just_a_label(api):
    token = await make_human("Officer", "compliance_officer", MINE)
    response = await api.post(
        "/api/incidents",
        json={
            "severity": "HIGH", "kind": "external_report",
            "detection_source": "external_report", "summary": "   ",
            "venture_id": MINE,
        },
        headers=auth(token),
    )
    assert response.status_code == 400


# ------------------------------------------------------------- the response timeline

async def test_the_response_appends_and_the_detection_is_never_touched(
    api, admin: psycopg.Connection
):
    """The rule the page states, enforced where it cannot be argued with.

    `incident` refuses UPDATE by grant and `incident_account` refuses it by trigger. The
    response can say anything; it can never change what was detected.
    """
    token = await make_human("Officer", "compliance_officer", MINE)
    created = await api.post(
        "/api/incidents",
        json={
            "severity": "MEDIUM", "kind": "external_report",
            "detection_source": "external_report",
            "summary": "Client reported a duplicated outbound call.",
            "venture_id": MINE,
        },
        headers=auth(token),
    )
    incident_id = created.json()["incident_id"]

    with admin.cursor() as cur:
        cur.execute(
            "SELECT severity, kind, detail FROM incident WHERE incident_id = %s",
            (incident_id,),
        )
        before = cur.fetchone()

    for stage, account in (
        ("triage", "Reproduced on two shifts; scope is one module."),
        ("containment", "Idempotency key added; duplicates stop at the broker."),
    ):
        appended = await api.post(
            f"/api/incidents/{incident_id}/accounts",
            json={"stage": stage, "account": account},
            headers=auth(token),
        )
        assert appended.status_code == 201

    detail = (
        await api.get(f"/api/incidents/{incident_id}", headers=auth(token))
    ).json()
    accounted = {s["stage"] for s in detail["stages"] if s["accounted"]}
    assert accounted == {"detection", "triage", "containment"}
    outstanding = {s["stage"] for s in detail["stages"] if not s["accounted"]}
    assert outstanding == {"disclosure", "post_mortem"}, (
        "a stage nobody has written about must say so; rendering it blank reads as "
        "nothing to report"
    )

    with admin.cursor() as cur:
        cur.execute(
            "SELECT severity, kind, detail FROM incident WHERE incident_id = %s",
            (incident_id,),
        )
        assert cur.fetchone() == before, "the detection changed while a response was written"


async def test_the_account_store_refuses_an_edit(api, admin: psycopg.Connection):
    """The trigger, not the absence of a route.

    A response timeline that can be tidied afterwards is a draft of what somebody wishes
    had happened, and the only version of this control that holds is the one in the
    database.
    """
    token = await make_human("Officer", "compliance_officer", MINE)
    created = await api.post(
        "/api/incidents",
        json={
            "severity": "LOW", "kind": "manual",
            "detection_source": "external_report", "summary": "Noted in passing.",
            "venture_id": MINE,
        },
        headers=auth(token),
    )
    incident_id = created.json()["incident_id"]

    with admin.cursor() as cur:
        cur.execute(
            "SELECT account_id FROM incident_account WHERE incident_id = %s",
            (incident_id,),
        )
        account_id = cur.fetchone()[0]

        for statement, params in (
            ("UPDATE incident_account SET account = 'nothing happened' WHERE account_id = %s",
             (account_id,)),
            ("DELETE FROM incident_account WHERE account_id = %s", (account_id,)),
        ):
            with pytest.raises(psycopg.Error) as refusal:
                cur.execute(statement, params)
            assert "append-only violation" in str(refusal.value)
            admin.rollback()


async def test_no_route_edits_or_deletes_an_incident():
    """The absent capability, enumerated rather than assumed."""
    surface = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    for path, method in surface:
        if "incident" in path:
            assert method not in {"DELETE", "PUT", "PATCH"}, (
                f"{method} {path} would edit a detection; incidents are append-only"
            )


# ------------------------------------------------------------------- the overview

async def test_the_overview_states_control_freshness_rather_than_deferring(api):
    """The gap this rebuild closed.

    The page told the reader to check freshness elsewhere and then showed an empty list.
    Both halves of that are computable here, and a screen that knows the answer and
    points at another screen is passing the work back.
    """
    token = await make_human("Operator", "venture_operator", MINE)
    overview = (await api.get("/api/incidents/overview", headers=auth(token))).json()

    controls = overview["controls"]
    assert controls["total"] > 0, "no controls are being reported on at all"
    assert set(controls["freshness"]) >= set(controls["never_ran"])
    # `all_fresh` must never be true while something has not run: an absence of findings
    # from a check that did not run is not evidence.
    if controls["never_ran"] or controls["stale"]:
        assert controls["all_fresh"] is False


async def test_the_overview_groups_by_kind_across_ventures(api):
    """Three of the same fault in two engagements is a pattern; a flat list shows neither."""
    token = await make_human("Officer", "compliance_officer", MINE)
    for _ in range(2):
        await api.post(
            "/api/incidents",
            json={
                "severity": "LOW", "kind": "external_report",
                "detection_source": "external_report",
                "summary": "Reported twice from the same engagement.",
                "venture_id": MINE,
            },
            headers=auth(token),
        )

    overview = (await api.get("/api/incidents/overview", headers=auth(token))).json()
    group = next(g for g in overview["by_kind"] if g["kind"] == "external_report")
    assert group["open"] >= 2
    assert group["ventures"] == [MINE]
    assert group["crosses_ventures"] is False, (
        "two incidents in one venture is not a cross-venture pattern, and saying so "
        "would make the flag meaningless"
    )


async def test_a_missing_incident_is_a_404_not_a_500(api):
    token = await make_human("Operator", "venture_operator", MINE)
    response = await api.get(f"/api/incidents/{uuid.uuid4()}", headers=auth(token))
    assert response.status_code == 404
