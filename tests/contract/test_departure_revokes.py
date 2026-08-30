"""An agent who leaves the Village stops being able to act, in the same write.

`sync_roster` said this in four places before it did it. The diff shown to the operator
read "any grants this agent holds are revoked when this is applied", they confirmed, and
the grants stayed live. A promise in the copy that the code does not keep is worse than
no promise at all, because it is the point at which the operator stops checking.

ATOMIC, AND WHY THAT WORD

    The departure and the revocations are one transaction. A commit between them leaves
    an agent the roster says is gone and the call path says may act - and nobody goes
    looking for that state, because the roster is where you would look.

    The Village kills agents on a mortality roll and auto-hires into the vacated seat.
    This is not a rare path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.rows import dict_row

from broker import humans, revocation, sync_roster, village
from broker.db import connection

pytestmark = pytest.mark.asyncio

REF = "dep-test-agent"
OTHER_REF = "dep-test-stayer"

#: Filled by the `world` fixture, which is where the Forge is seeded.
FORGE: list[str] = []

ROSTER = [
    {
        "agent_id": REF, "lore_name": "Wren Halloway", "department": "engineering",
        "role_key": "individual_contributor", "reports_to_id": None, "title": "Engineer",
    },
    {
        "agent_id": OTHER_REF, "lore_name": "Sable Quint", "department": "engineering",
        "role_key": "individual_contributor", "reports_to_id": None, "title": "Engineer",
    },
]


def _village_says(monkeypatch, agents: list[dict]) -> None:
    async def roster(degrade: bool = True) -> village.Answer:
        return village.Answer(data={"agents": agents}, fetched_at=datetime.now(UTC))

    monkeypatch.setattr(village, "roster", roster)


@pytest.fixture
def world(admin: psycopg.Connection, seed_forge):
    """Two agents with identities, one of them holding grants."""
    forge_id, module_id = seed_forge
    FORGE[:] = [forge_id, module_id]
    ids: dict[str, uuid.UUID] = {}

    def clear() -> None:
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM revocation WHERE office_agent_id IN "
                "(SELECT office_agent_id FROM office_agent_identity "
                " WHERE village_agent_ref = ANY(%s))", ([REF, OTHER_REF],)
            )
            cur.execute(
                "DELETE FROM agent_forge_grant WHERE office_agent_id IN "
                "(SELECT office_agent_id FROM office_agent_identity "
                " WHERE village_agent_ref = ANY(%s))", ([REF, OTHER_REF],)
            )
            cur.execute(
                "DELETE FROM office_agent_identity WHERE village_agent_ref = ANY(%s)",
                ([REF, OTHER_REF],),
            )
            cur.execute("DELETE FROM village_agent WHERE village_agent_ref = ANY(%s)",
                        ([REF, OTHER_REF],))
        admin.commit()

    clear()
    with admin.cursor() as cur:
        for ref, name in ((REF, "Wren Halloway"), (OTHER_REF, "Sable Quint")):
            agent_id = uuid.uuid4()
            ids[ref] = agent_id
            cur.execute(
                "INSERT INTO village_agent (village_agent_ref, agent_name, department, "
                "role_key, title, status, source) VALUES "
                "(%s, %s, 'engineering', 'individual_contributor', 'Engineer', "
                " 'active', 'import')",
                (ref, name),
            )
            cur.execute(
                "INSERT INTO office_agent_identity (office_agent_id, village_agent_ref, "
                "agent_name, department, status) "
                "VALUES (%s, %s, %s, 'engineering', 'active')",
                (agent_id, ref, name),
            )
            for venture in ("greenstone", "medlink-pro"):
                # Fully live grants: both cert refs present and activated, which is
                # what the generated `is_assignable` column requires. A grant that was
                # never assignable would be revoked by this code and prove nothing.
                cur.execute(
                    "INSERT INTO agent_forge_grant (grant_id, office_agent_id, forge_id, "
                    "module_id, venture_id, trust_tier, granted_by, "
                    "operation_cert_ref, dept_context_cert_ref, activated_at, "
                    "activated_by) "
                    "VALUES (%s, %s, %s, %s, %s, 'suggest', %s, 'cert://op', "
                    "'cert://dept', now(), %s)",
                    (uuid.uuid4(), agent_id, forge_id, module_id, venture,
                     uuid.uuid4(), uuid.uuid4()),
                )
    admin.commit()

    yield ids, admin
    clear()


@pytest.fixture
async def operator(admin: psycopg.Connection):
    """A real account, because attribution refuses a fixture and the suite has only those."""
    async with connection() as conn:
        human_id, _ = await humans.create_human(
            conn, display_name="Departure operator", email="dep@x.departure.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role="ivan", venture_id=None, granted_by=human_id
        )
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE office_human SET status = 'suspended', suspended_at = now(), "
            "suspended_by = human_id WHERE origin = 'human' AND human_id <> %s",
            (human_id,),
        )
        cur.execute(
            "UPDATE office_human SET origin = 'human' WHERE human_id = %s", (human_id,)
        )
    admin.commit()
    yield human_id
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE office_human SET status = 'active', suspended_at = NULL, "
            "suspended_by = NULL WHERE origin = 'human'"
        )
        cur.execute("DELETE FROM office_human_role WHERE human_id = %s", (human_id,))
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (human_id,))
    admin.commit()


def _live_grants(conn: psycopg.Connection, agent_id: uuid.UUID) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM agent_forge_grant "
            "WHERE office_agent_id = %s AND revoked_at IS NULL",
            (agent_id,),
        )
        return int(cur.fetchone()[0])


def _revocations(conn: psycopg.Connection, agent_id: uuid.UUID) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT scope, reason, revoked_by_role, blast_radius FROM revocation "
            "WHERE office_agent_id = %s ORDER BY revoked_at",
            (agent_id,),
        )
        return [dict(r) for r in cur.fetchall()]


# ================================================================== THE PROMISE IS KEPT

async def test_a_departure_revokes_the_agents_grants(world, operator, monkeypatch):
    """THE test. The diff said this happens; now it does."""
    ids, admin = world
    departing = ids[REF]

    # Only the stayer is still in the Village.
    _village_says(monkeypatch, [ROSTER[1]])

    async with connection() as conn:
        result = await sync_roster.apply(conn, actor=operator, confirmed=True)

    assert result["departed"] == 1
    assert result["grants_revoked"] == 2

    entries = _revocations(admin, departing)
    assert len(entries) == 1, "one revocation for the departure, not one per grant"
    assert entries[0]["scope"] == "agent"
    assert "no longer in the Village roster" in entries[0]["reason"]

    # And the effect that actually matters: the next call is refused. A revocation row
    # nobody consults is a record of an intention.
    from broker.errors import Revoked
    forge_id, module_id = FORGE
    async with connection() as conn:
        with pytest.raises(Revoked):
            await revocation.check_revocations(
                conn, office_agent_id=departing, forge_id=forge_id,
                module_id=module_id, venture_id="greenstone",
            )


async def test_an_agent_who_stayed_keeps_everything(world, operator, monkeypatch):
    """A revocation sweep that catches the wrong agent is worse than none."""
    ids, admin = world
    _village_says(monkeypatch, [ROSTER[1]])

    async with connection() as conn:
        await sync_roster.apply(conn, actor=operator, confirmed=True)

    assert _live_grants(admin, ids[OTHER_REF]) == 2
    assert _revocations(admin, ids[OTHER_REF]) == []

    # And they can still work.
    forge_id, module_id = FORGE
    async with connection() as conn:
        await revocation.check_revocations(
            conn, office_agent_id=ids[OTHER_REF], forge_id=forge_id,
            module_id=module_id, venture_id="greenstone",
        )


async def test_the_departed_identity_is_suspended(world, operator, monkeypatch):
    """The identity stops being active, and the row stays.

    Not deleted: who held what, and who granted it, is the record the console's own copy
    exists to protect.
    """
    ids, admin = world
    _village_says(monkeypatch, [ROSTER[1]])

    async with connection() as conn:
        await sync_roster.apply(conn, actor=operator, confirmed=True)

    with admin.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT status FROM office_agent_identity WHERE office_agent_id = %s",
            (ids[REF],),
        )
        assert cur.fetchone()["status"] == "suspended"
        cur.execute(
            "SELECT status, departed_at FROM village_agent WHERE village_agent_ref = %s",
            (REF,),
        )
        row = cur.fetchone()
        assert row["status"] == "departed" and row["departed_at"] is not None


async def test_the_revocation_and_the_departure_are_one_transaction(
    world, operator, monkeypatch
):
    """Atomic. Neither half may land without the other.

    A departure recorded without its revocations is an agent the roster says is gone and
    the call path says may act - and nobody goes looking for that, because the roster is
    where you would look.
    """
    ids, admin = world
    _village_says(monkeypatch, [ROSTER[1]])

    async def refuse(*args, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(sync_roster.audit, "write_event", refuse)

    with pytest.raises(RuntimeError):
        async with connection() as conn:
            await sync_roster.apply(conn, actor=operator, confirmed=True)

    # Nothing moved. Not the grants, not the identity, not the roster row.
    assert _live_grants(admin, ids[REF]) == 2
    assert _revocations(admin, ids[REF]) == []
    with admin.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT status FROM office_agent_identity WHERE office_agent_id = %s",
            (ids[REF],),
        )
        assert cur.fetchone()["status"] == "active"


async def test_an_agent_who_held_nothing_produces_no_revocation(
    world, operator, monkeypatch, admin
):
    """An empty revocation on the page would read as an event that happened."""
    ids, _ = world
    with admin.cursor() as cur:
        cur.execute(
            "DELETE FROM agent_forge_grant WHERE office_agent_id = %s", (ids[REF],)
        )
    admin.commit()

    _village_says(monkeypatch, [ROSTER[1]])
    async with connection() as conn:
        result = await sync_roster.apply(conn, actor=operator, confirmed=True)

    assert result["departed"] == 1
    assert result["grants_revoked"] == 0
    assert _revocations(admin, ids[REF]) == []


async def test_the_audit_entry_records_what_was_revoked(world, operator, monkeypatch,
                                                        admin):
    """A reader of the log can see the consequence, not just the roster change."""
    _village_says(monkeypatch, [ROSTER[1]])

    async with connection() as conn:
        await sync_roster.apply(conn, actor=operator, confirmed=True)

    with admin.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT subject FROM audit_log WHERE event_type = 'village_roster_imported' "
            "ORDER BY audit_id DESC LIMIT 1"
        )
        subject = cur.fetchone()["subject"]

    assert subject["grants_revoked"] == 2
    assert subject["departed"] == 1


async def test_nothing_is_revoked_when_nobody_departed(world, operator, monkeypatch,
                                                       admin):
    """A guard that fires on an ordinary sync is not a guard."""
    ids, _ = world
    _village_says(monkeypatch, ROSTER)

    async with connection() as conn:
        result = await sync_roster.apply(conn, actor=operator, confirmed=True)

    assert result["departed"] == 0
    assert result["grants_revoked"] == 0
    assert _live_grants(admin, ids[REF]) == 2


async def test_a_returning_agent_does_not_get_their_grants_back(
    world, operator, monkeypatch, admin
):
    """Reinstatement is a decision somebody makes, not a side effect of reappearing.

    The Village auto-hires into a vacated seat, and an agent id that came back would
    otherwise silently recover authority that was deliberately taken away.
    """
    ids, _ = world
    _village_says(monkeypatch, [ROSTER[1]])
    async with connection() as conn:
        await sync_roster.apply(conn, actor=operator, confirmed=True)

    _village_says(monkeypatch, ROSTER)
    async with connection() as conn:
        await sync_roster.apply(conn, actor=operator, confirmed=True)

    entries = _revocations(admin, ids[REF])
    assert len(entries) == 1, "the revocation stands; it is a record, not a state flag"
