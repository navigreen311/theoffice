"""Audit: verification that is evidence, actors with names, and fixtures that stay put."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest

from broker import audit_events, audit_view, humans
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.world import build_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
SEED = uuid.UUID("00000000-0000-5000-8000-0000000000ad")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sweep_run")
        # `audit_log` is append-only by trigger, which is the point of it. The fixture
        # disables the guard for teardown rather than reaching for a softer one; the
        # trigger is proven still on by `test_the_audit_log_refuses_an_edit`.
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER USER")
        cur.execute("DELETE FROM audit_log")
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER USER")
    wipe_venture(conn, VENTURE)
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


async def make(name: str, email: str, role: str = "ivan") -> tuple[uuid.UUID, str]:
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name, email=email
        )
        await humans.grant_role(
            conn, human_id=human_id, role=role, venture_id=None, granted_by=SEED
        )
    return human_id, token


# ------------------------------------------------------------------ the glossary

async def test_every_audit_event_written_in_the_source_is_published():
    """The glossary is derived from the call sites, and this keeps it derived.

    Event names reached the page as raw identifiers with no glossary anywhere, and the
    filter asked the reader to type one. A published list fixes that only while it
    matches the code, so the source is walked.
    """
    root = Path(__file__).resolve().parents[2] / "broker"
    written: set[str] = set()
    for source in root.glob("*.py"):
        if source.name == "audit_events.py":
            continue
        text = source.read_text(encoding="utf-8")
        written |= set(re.findall(r'event_type=\s*"([a-z_]+)"', text))
        written |= set(re.findall(r'_audit_human_action\(\s*me,\s*"([a-z_]+)"', text, re.S))

    assert written, "the walker matched no audit write; the pattern is stale"
    missing = sorted(name for name in written if name not in audit_events.BY_TYPE)
    assert not missing, (
        f"these events are written and not published in audit_events.py: {missing}. "
        "An event the glossary does not describe renders as a raw identifier."
    )


async def test_the_glossary_says_what_each_event_means_and_what_writes_it(api):
    _id, token = await make("Ivan", "ivan@audit.example.com")
    events = (await api.get("/api/audit/events", headers=auth(token))).json()["events"]

    assert len(events) >= 30
    for event in events:
        assert event["label"] != event["event_type"], (
            f"{event['event_type']} has no plain-language label"
        )
        assert event["meaning"].strip(), f"{event['event_type']} explains nothing"
        assert event["written_by"].startswith("broker."), event["event_type"]


# ------------------------------------------------------- verification as evidence

async def test_the_chain_state_reports_what_was_verified_when_and_how(api):
    """A verification with no timestamp and no method is not evidence of anything."""
    _id, token = await make("Ivan", "ivan@audit.example.com")

    async with connection() as conn:
        before = await audit_view.chain_state(conn)

    # Nothing recorded yet: the page must say so rather than showing a green badge over
    # a check nobody can produce later.
    assert before["recorded"] is False
    assert before["trustworthy"] is False
    assert before["verified_at"] is None
    assert before["method"] is None

    # Two runs: the first writes an audit entry of its own, the second has something to
    # count. A verification over an empty log reports zero, which is true and is not what
    # this test is about.
    first = await api.post("/api/controls/audit-chain", json={}, headers=auth(token))
    assert first.status_code == 201
    recorded = await api.post("/api/controls/audit-chain", json={}, headers=auth(token))
    assert recorded.status_code == 201

    state = recorded.json()["recorded_verification"]
    assert state["recorded"] is True
    assert state["status"] == "passed"
    assert state["verified_at"] is not None, "a verification with no timestamp"
    assert "re-hash" in state["method"], "the method is not stated"
    assert state["head_hash"], "no head hash"
    assert state["verified_entries"] > 0


async def test_this_page_and_compliance_read_the_same_row(api):
    """The contradiction, closed by construction rather than by a disclaimer.

    The page reported a check it ran on load and recorded nowhere; Compliance read the
    control result. Both were true and they disagreed. There is one verification now, it
    leaves one row, and both screens read it.
    """
    _id, token = await make("Ivan", "ivan@audit.example.com")
    await api.post("/api/controls/audit-chain", json={}, headers=auth(token))

    audit = (await api.get("/api/audit/chain", headers=auth(token))).json()
    compliance = (
        await api.get("/api/incidents/overview", headers=auth(token))
    ).json()["controls"]["freshness"]["audit_chain"]

    assert audit["recorded_verification"]["status"] == "passed"
    assert compliance["state"] == "fresh", (
        "the audit page recorded a verification and Compliance still reports it stale"
    )
    assert audit["recorded_verification"]["verified_entries"] == compliance["denominator"]


async def test_the_live_check_is_reported_as_not_recorded(api):
    """The live check is real and is not evidence. Saying so is the whole point."""
    _id, token = await make("Ivan", "ivan@audit.example.com")
    chain = (await api.get("/api/audit/chain", headers=auth(token))).json()

    assert chain["ok"] is True, "the live check should pass on a healthy chain"
    assert chain["live_check_is_recorded"] is False, (
        "a check nothing records cannot be produced later and Compliance cannot see it"
    )


# --------------------------------------------------------------------- the actor

async def test_every_entry_names_the_person_not_only_the_type(api):
    """`actor: human` is a type. Non-repudiation is the point of this log."""
    ivan_id, token = await make("Ivan", "ivan@audit.example.com")
    await api.post("/api/controls/audit-chain", json={}, headers=auth(token))

    rows = (
        await api.get("/api/audit/entries", headers=auth(token))
    ).json()["rows"]
    assert rows, "nothing was written"

    for row in rows:
        assert row["actor_type"], "the type is still a useful signal and must stay"
        if row["actor_id"] == str(ivan_id):
            assert row["actor_name"] == "Ivan", "the entry names a type and no person"


async def test_the_log_can_be_filtered_by_actor(api):
    """"What did Dana do" has to be answerable."""
    ivan_id, token = await make("Ivan", "ivan@audit.example.com")
    other_id, other_token = await make("Nadia", "nadia@audit.example.com")

    await api.post("/api/controls/audit-chain", json={}, headers=auth(token))
    await api.post("/api/controls/audit-chain", json={}, headers=auth(other_token))

    mine = (
        await api.get(f"/api/audit/entries?actor_id={ivan_id}", headers=auth(token))
    ).json()
    assert mine["total"] >= 1
    assert {row["actor_id"] for row in mine["rows"]} == {str(ivan_id)}
    assert str(other_id) not in {row["actor_id"] for row in mine["rows"]}


# -------------------------------------------------------------------- fixtures

async def test_fixture_entries_are_tagged_filtered_and_never_removed(api, admin):
    """Filtering changes the view. The record is append-only and stays whole."""
    _id, token = await make("Ivan", "ivan@audit.example.com")
    _fid, fixture_token = await make("smoke-abcd1234", "smoke-abcd1234@example.invalid")

    await api.post("/api/controls/audit-chain", json={}, headers=auth(token))
    await api.post("/api/controls/audit-chain", json={}, headers=auth(fixture_token))

    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log")
        on_disk = cur.fetchone()[0]

    hidden = (await api.get("/api/audit/entries", headers=auth(token))).json()
    shown = (
        await api.get("/api/audit/entries?include_fixtures=true", headers=auth(token))
    ).json()

    assert hidden["excluded_fixtures"] > 0, "no fixture entry was recognised"
    assert all(not row["fixture"] for row in hidden["rows"])
    assert any(row["fixture"] for row in shown["rows"]), "the tag is missing"
    assert shown["total"] > hidden["total"], "the filter does nothing"

    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log")
        assert cur.fetchone()[0] == on_disk, "filtering removed a row from the record"


async def test_the_audit_log_refuses_an_edit(api, admin: psycopg.Connection):
    """The store the whole console leans on, guarded where it cannot be argued with.

    Seeded rather than skipped when the log is empty. A guard that skips is a guard that
    reports green without having run, which is the failure this whole console keeps
    finding in itself.
    """
    _id, token = await make("Ivan", "ivan@audit.example.com")
    await api.post("/api/controls/audit-chain", json={}, headers=auth(token))

    with admin.cursor() as cur:
        cur.execute("SELECT audit_id FROM audit_log ORDER BY audit_id LIMIT 1")
        row = cur.fetchone()
        assert row is not None, "nothing was written, so the guard was never exercised"

        for statement in (
            "UPDATE audit_log SET event_type = 'nothing_happened' WHERE audit_id = %s",
            "DELETE FROM audit_log WHERE audit_id = %s",
        ):
            with pytest.raises(psycopg.Error):
                cur.execute(statement, (row[0],))
            admin.rollback()


# ---------------------------------------------------------------- entry detail

async def test_an_entry_confirms_its_link_to_the_previous_one(api):
    """A hash chain nobody can check by eye is decoration."""
    _id, token = await make("Ivan", "ivan@audit.example.com")
    # Twice, so the newest entry has a predecessor to link to. With one entry the newest
    # is also the first, which is a different case and has its own test.
    await api.post("/api/controls/audit-chain", json={}, headers=auth(token))
    await api.post("/api/controls/audit-chain", json={}, headers=auth(token))

    rows = (await api.get("/api/audit/entries", headers=auth(token))).json()["rows"]
    newest = rows[0]

    detail = (
        await api.get(f"/api/audit/{newest['audit_id']}", headers=auth(token))
    ).json()

    assert detail["subject"] is not None, "no payload; the row says what but not what of"
    assert detail["entry_hash"] and detail["prev_hash"]
    assert detail["previous_entry_hash"], "nothing to compare the link against"
    assert detail["links_to_previous"] is True
    assert str(detail["previous_audit_id"]) in detail["link_note"]


async def test_the_first_entry_says_it_has_no_predecessor(api, admin):
    """Different from a broken link, and it must not read as one."""
    _id, token = await make("Ivan", "ivan@audit.example.com")
    await api.post("/api/controls/audit-chain", json={}, headers=auth(token))

    with admin.cursor() as cur:
        cur.execute("SELECT min(audit_id) FROM audit_log")
        first = cur.fetchone()[0]

    detail = (await api.get(f"/api/audit/{first}", headers=auth(token))).json()
    assert detail["links_to_previous"] is None
    assert "first entry" in detail["link_note"]


# --------------------------------------------------------------------- export

async def test_the_export_states_its_own_chain_state_and_fixture_inclusion(api):
    """An export that does not say those things looks like evidence and is not."""
    _id, token = await make("Ivan", "ivan@audit.example.com")
    _fid, fixture_token = await make("smoke-99887766", "smoke-99887766@example.invalid")
    await api.post("/api/controls/audit-chain", json={}, headers=auth(fixture_token))

    export = (await api.get("/api/audit/export", headers=auth(token))).json()

    assert export["fixtures_included"] is False
    assert export["fixtures_excluded"] > 0
    assert any("excluded from this export" in note for note in export["caveats"])
    assert export["chain"]["method"], "the export does not say how the chain was checked"
    assert export["chain"]["head_hash"]
    assert "entries_in_log" in export


async def test_an_export_from_an_unverified_log_says_so_on_its_face(api):
    """Exactly as the Compliance export does."""
    _id, token = await make("Ivan", "ivan@audit.example.com")

    # Nothing has recorded a verification in this world.
    export = (await api.get("/api/audit/export", headers=auth(token))).json()
    assert export["chain"]["recorded"] is False
    assert any("never recorded" in note for note in export["caveats"]), export["caveats"]


# ---------------------------------------------------------------------- shape

async def test_counts_are_available_before_paging(api):
    """1,157 rows with no aggregate hides a spike until somebody pages far enough."""
    _id, token = await make("Ivan", "ivan@audit.example.com")
    await api.post("/api/controls/audit-chain", json={}, headers=auth(token))

    shape = (await api.get("/api/audit/shape", headers=auth(token))).json()
    assert shape["counted"] > 0
    assert shape["by_event_type"], "no counts by event type"
    assert shape["by_actor"], "no counts by actor"
    # The event tally carries the plain-language label, so the aggregate is readable by
    # somebody who does not know the identifiers.
    assert any(row["label"] for row in shape["by_event_type"])
