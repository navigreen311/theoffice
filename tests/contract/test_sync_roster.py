"""A sync either lands with a signature on it, or it fails loudly and writes nothing.

`sync-roster` is the only command in this system that writes to the table saying which
agents may act. Two failures found in its first live run are what these tests hold shut,
and both are of a kind this project keeps meeting: a control that exists but does not
hold.

    The command returned 0 while failing on a CHECK constraint. Nothing between the
    exception and the shell's exit code was doing anything - a traceback reached stderr
    and the caller saw success. A wrapper, a pipe, or a CI step would have recorded a
    sync that never happened.

    The audit entry was attributed to "the oldest active account holding `ivan`". 222 of
    the 223 accounts in the development database are smoke fixtures and every one of them
    holds `ivan`; the real account won only by being oldest. A re-seed, a restore, or one
    fixture created a second sooner, and a change to the identity table would have been
    signed by `smoke-1a2b3c4d`.

The second is the more serious. A wrong exit code is a lie about one run. An audit entry
naming a fixture is a lie about who is accountable, it is written into an append-only
store, and after the fact it is indistinguishable from a true one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.rows import dict_row

from broker import account_origin, humans, sync_roster, village
from broker.db import connection

pytestmark = pytest.mark.asyncio

VILLAGE_AGENT = {
    "agent_id": "aurelia_vance",
    "lore_name": "Aurelia Vance",
    "department": "research",
    "role_key": "researcher",
    "reports_to_id": "marcus_webb",
    "title": "Research Analyst",
}


def _wipe(conn: psycopg.Connection) -> None:
    """Only the rows this file creates.

    An earlier version cleared `office_agent_identity` outright and took out every other
    suite's grants with it. A test fixture that empties a shared table is a test fixture
    that fails somebody else's assertions from a different file.
    """
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM village_agent WHERE village_agent_ref = %s",
            (VILLAGE_AGENT["agent_id"],),
        )
        cur.execute(
            "DELETE FROM office_human_role WHERE human_id IN "
            "(SELECT human_id FROM office_human WHERE email LIKE '%%.sync-test.invalid')"
        )
        cur.execute("DELETE FROM office_human WHERE email LIKE '%%.sync-test.invalid'")
    conn.commit()


@pytest.fixture
def clean(admin: psycopg.Connection):
    _wipe(admin)
    yield admin
    _wipe(admin)


async def _make(display_name: str, local: str, role: str = "ivan") -> uuid.UUID:
    """An account this test owns. The domain is what `_wipe` keys on."""
    async with connection() as conn:
        human_id, _ = await humans.create_human(
            conn, display_name=display_name, email=f"{local}@x.sync-test.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role=role, venture_id=None, granted_by=human_id
        )
    return human_id


def _village_says(monkeypatch, agents: list[dict]) -> None:
    async def roster(degrade: bool = True) -> village.Answer:
        return village.Answer(data={"agents": agents}, fetched_at=datetime.now(UTC))

    monkeypatch.setattr(village, "roster", roster)


#: `suspension_names_who` requires both columns whenever status is `suspended`. The
#: schema will not record a suspension that names nobody, and a test that wrote the
#: status directly would be asserting against a state the application cannot produce.
_SUSPEND = (
    "UPDATE office_human SET status = 'suspended', suspended_at = now(), "
    "suspended_by = COALESCE(%s, human_id)"
)


def _mark_real(conn: psycopg.Connection, human_id: uuid.UUID) -> None:
    """Every address here ends `.invalid`, so the classifier calls them all fixtures.

    Overridden explicitly rather than by inventing a real-looking domain: a test that
    depends on a hostname the classifier happens not to recognise is a test that breaks
    the day somebody adds it to `TEST_DOMAINS`.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE office_human SET origin = 'human' WHERE human_id = %s", (human_id,)
        )
    conn.commit()


# ================================================== A FAILED SYNC REPORTS FAILURE

async def test_a_sync_that_cannot_reach_the_village_reports_failure(clean, monkeypatch):
    """Raise, and say why. The failure this replaces returned 0."""
    async def unreachable(degrade: bool = True) -> village.Answer:
        raise village.VillageUnreachableError("connection refused")

    monkeypatch.setattr(village, "roster", unreachable)
    actor = await _make("Sync operator", "sync")
    _mark_real(clean, actor)

    with pytest.raises(sync_roster.SyncError) as exc:
        async with connection() as conn:
            await sync_roster.apply(conn, actor=actor, confirmed=True)

    assert "did not answer" in str(exc.value)


async def test_an_empty_roster_is_refused_rather_than_read_as_mass_departure(
    clean, monkeypatch
):
    """186 agents vanishing at once is a broken Village, not a resignation."""
    _village_says(monkeypatch, [])
    actor = await _make("Sync operator", "sync")
    _mark_real(clean, actor)

    with pytest.raises(sync_roster.SyncError):
        async with connection() as conn:
            await sync_roster.apply(conn, actor=actor, confirmed=True)


async def test_a_database_error_during_the_write_is_raised_not_swallowed(
    clean, monkeypatch
):
    """The shape of the live failure: a bad value reaching the database mid-write.

    The first run wrote `village_api` into `village_agent.source`, which permits only
    `import` or `manual`. The write failed and the command reported success. A null byte
    stands in for that value here because the original one is now impossible to send -
    which is the fix, and is why the test uses a different bad value rather than
    asserting on a constraint that no longer fires.
    """
    _village_says(monkeypatch, [{**VILLAGE_AGENT, "lore_name": "bad" + chr(0) + "name"}])
    actor = await _make("Sync operator", "sync")
    _mark_real(clean, actor)

    with pytest.raises(Exception) as exc:
        async with connection() as conn:
            await sync_roster.apply(conn, actor=actor, confirmed=True)

    assert not isinstance(exc.value, AssertionError)


async def test_a_failed_sync_leaves_no_half_written_roster(clean, monkeypatch):
    """Roster rows and their audit entry are one transaction.

    `apply` used to commit the roster and then write the audit entry. A failure between
    the two left the identity table changed with nothing recording who changed it - an
    unauditable write to the table that says who may act, which is the one outcome this
    command must not be able to produce.
    """
    _village_says(monkeypatch, [VILLAGE_AGENT])
    actor = await _make("Sync operator", "sync")
    _mark_real(clean, actor)

    async def refuse(*args, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(sync_roster.audit, "write_event", refuse)

    with pytest.raises(RuntimeError):
        async with connection() as conn:
            await sync_roster.apply(conn, actor=actor, confirmed=True)

    with clean.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM village_agent WHERE village_agent_ref = %s",
            (VILLAGE_AGENT["agent_id"],),
        )
        written = cur.fetchone()[0]

    assert written == 0, (
        "the audit write failed and the roster row survived it. The roster and the "
        "entry naming who imported it have to land together or not at all."
    )


async def test_the_cli_returns_non_zero_when_the_sync_fails(clean, monkeypatch, capsys):
    """Asserted at the exit code, because that is what a caller sees and what was wrong.

    A test on the exception would have passed against the broken version: the exception
    was always raised. It was the code path between the exception and the shell that was
    missing.
    """
    from broker import __main__ as cli

    async def unreachable(degrade: bool = True) -> village.Answer:
        raise village.VillageUnreachableError("connection refused")

    monkeypatch.setattr(village, "roster", unreachable)
    actor = await _make("Sync operator", "sync")
    _mark_real(clean, actor)

    code = await cli._sync_roster(confirm=True)

    assert code == 1
    assert "sync-roster" in capsys.readouterr().out


async def test_a_successful_sync_returns_zero(clean, monkeypatch, capsys):
    """The other half of the exit code. A guard that always fails is not a guard."""
    from broker import __main__ as cli

    _village_says(monkeypatch, [VILLAGE_AGENT])
    actor = await _make("Sync operator", "sync")
    _mark_real(clean, actor)

    assert await cli._sync_roster(confirm=True) == 0

    with clean.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM village_agent WHERE village_agent_ref = %s",
            (VILLAGE_AGENT["agent_id"],),
        )
        assert cur.fetchone()[0] == 1


# ================================================== ATTRIBUTION NAMES A REAL PERSON

async def test_a_fixture_cannot_sign_a_sync(clean):
    """The failure this exists for: fixtures hold `ivan` and were otherwise eligible.

    Ordering by `created_at` is what made the real account win. This asserts the rule
    rather than the luck - a fixture older than every real account still cannot sign.
    """
    fixture = await _make("smoke-1a2b3c4d", "smoke-1a2b3c4d")
    real = await _make("A real person", "person")
    _mark_real(clean, real)

    # The fixture is now the older row, so the query being replaced would have chosen it.
    with clean.cursor() as cur:
        cur.execute(
            "UPDATE office_human SET created_at = now() - interval '1 year' "
            "WHERE human_id = %s",
            (fixture,),
        )
    clean.commit()

    async with connection() as conn:
        chosen = await humans.attributable_actor(conn)

    assert chosen == real
    assert chosen != fixture


async def test_a_fixture_is_marked_when_it_is_created(clean):
    """Marked on insert, not backfilled later.

    A backfill describes the accounts that existed the day it ran, and the smoke script
    creates fixtures on every invocation. An unmarked fixture is a fixture eligible to
    sign an audit entry.
    """
    await _make("smoke-deadbeef", "smoke-deadbeef")

    with clean.cursor() as cur:
        cur.execute(
            "SELECT origin FROM office_human WHERE display_name = 'smoke-deadbeef'"
        )
        assert cur.fetchone()[0] == account_origin.TEST_FIXTURE


async def test_no_real_account_refuses_rather_than_signing_with_nobody(clean):
    """It stops. It does not write the roster with a null actor.

    A resolver returning None for "nobody could sign this" gets a caller that writes the
    row anyway. The point is that the write must not happen, so this raises.

    Fixtures from other suites may exist in this database; none of them can satisfy it,
    which is the assertion.
    """
    await _make("smoke-cafebabe", "smoke-cafebabe")

    with clean.cursor() as cur:
        cur.execute(_SUSPEND + " WHERE origin = 'human'", (None,))
    clean.commit()

    try:
        with pytest.raises(humans.NoAttributableActorError) as exc:
            async with connection() as conn:
                await humans.attributable_actor(conn)

        message = str(exc.value)
        assert "origin 'human'" in message
        # And it says what to do, because the operator hitting this has an empty database
        # and no reason to know fixtures are excluded deliberately.
        assert "broker human create" in message
    finally:
        with clean.cursor() as cur:
            cur.execute(
                "UPDATE office_human SET status = 'active', suspended_at = NULL, "
                "suspended_by = NULL WHERE origin = 'human'"
            )
        clean.commit()


async def test_a_suspended_person_cannot_sign_either(clean):
    """Origin is not the only condition. A suspended account is not an actor."""
    real = await _make("A real person", "person")
    _mark_real(clean, real)
    with clean.cursor() as cur:
        cur.execute(_SUSPEND + " WHERE human_id = %s", (real, real))
    clean.commit()

    async with connection() as conn:
        try:
            chosen = await humans.attributable_actor(conn)
        except humans.NoAttributableActorError:
            return

    assert chosen != real


async def test_the_stored_origin_agrees_with_the_classifier(clean):
    """One rule, in one place, and the column is its written-down answer.

    Migration 0027 backfilled in SQL so it would not import application code that could
    change under it. That is the right call for a migration and it is exactly what makes
    drift possible, so the two are compared here.
    """
    await _make("smoke-0badf00d", "smoke-0badf00d")

    with clean.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT display_name, email, origin FROM office_human")
        rows = cur.fetchall()

    # `service` and the accounts marked real by hand are set deliberately, not derived.
    disagreed = [
        r for r in rows
        if r["origin"] == account_origin.TEST_FIXTURE
        and account_origin.origin_of(r) != account_origin.TEST_FIXTURE
    ]
    assert not disagreed, (
        f"stored origin disagrees with the classifier for {len(disagreed)} accounts: "
        f"{[r['display_name'] for r in disagreed[:5]]}"
    )
