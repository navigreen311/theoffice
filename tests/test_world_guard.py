"""The world fixture refuses a database that was not marked disposable - entry 95.

`build_world` calls `teardown_world` first, and that deletes EVERY certification and
EVERY operating instruction in the database it is handed - not only its own rows. Its
callers guarded it on what the database CONTAINS (`dev-up.sh` seeds when the registry is
empty, `console-smoke.sh` when `/api/forges` returns `[]`) and never on WHICH database it
is. Pointed at the development database on 15 September 2026 it would have deleted 18
bootstrap-attested certifications and 16 authored instructions.

**The marker is a database-level setting whose value is the database's own name.** These
tests pin the three properties that make it a guard rather than a formality: an unmarked
database is refused, a database carrying somebody else's name is refused, and the refusal
names what to do about it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import psycopg
import pytest

from tests.conftest import requires_db
from tests.world import (
    DISPOSABLE_MARKER,
    NotADisposableDatabaseError,
    assert_disposable,
    build_world,
    teardown_world,
)

pytestmark = [requires_db, pytest.mark.db]


def _unmark(conn: psycopg.Connection, value: str) -> None:
    """Override the marker for this session only. The database setting is untouched."""
    with conn.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)", (DISPOSABLE_MARKER, value))


def test_the_suite_runs_against_a_database_that_is_marked(admin: psycopg.Connection):
    """The other half of the guard: a marked database is accepted, and says its name.

    If this fails, the database the suite is using has not been marked - which is the
    guard working, not a broken test. `./scripts/bootstrap.sh` marks the test database.
    """
    assert assert_disposable(admin) == admin.info.dbname


def test_an_unmarked_database_is_refused(admin: psycopg.Connection):
    """No marker at all. The default state of every database in the world."""
    _unmark(admin, "")
    try:
        with pytest.raises(NotADisposableDatabaseError) as refusal:
            assert_disposable(admin)
    finally:
        admin.rollback()

    message = str(refusal.value)
    assert admin.info.dbname in message, "the refusal must name the database it refused"
    assert "ALTER DATABASE" in message, "and say exactly how to mark a throwaway database"
    assert "nothing was written" in message


def test_a_marker_naming_another_database_is_refused(admin: psycopg.Connection):
    """The marker must equal the database's OWN name.

    So a marked database restored under another name is not marked, and a marker copied
    from one environment into another names the wrong database and refuses. A bare
    "somebody set a flag" would survive both.
    """
    _unmark(admin, "some-other-database")
    try:
        with pytest.raises(NotADisposableDatabaseError) as refusal:
            assert_disposable(admin)
    finally:
        admin.rollback()

    assert "'some-other-database'" in str(refusal.value), (
        "the refusal must quote the marker it found, or a copied marker looks like none"
    )


def test_build_and_teardown_both_refuse(admin: psycopg.Connection):
    """Both entry points, because fixtures call `teardown_world` directly.

    A guard on `build_world` alone would leave the deletes reachable through the function
    that actually performs them.
    """
    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM forge_operating_instruction")
        before = cur.fetchone()[0]

    _unmark(admin, "")
    try:
        with pytest.raises(NotADisposableDatabaseError):
            build_world(admin)
        with pytest.raises(NotADisposableDatabaseError):
            teardown_world(admin)

        # The refusal has to come BEFORE the deletes, not instead of the inserts. Counting
        # the table the teardown empties is the cheapest way to say that, and it is the
        # assertion that fails if the guard is ever moved below the first `DELETE`.
        with admin.cursor() as cur:
            cur.execute("SELECT count(*) FROM forge_operating_instruction")
            assert cur.fetchone()[0] == before, "the guard fired after a delete"
    finally:
        admin.rollback()


def test_the_development_database_is_refused():
    """The case this exists for, against the real development DSN.

    **Read out of `.env` rather than the environment**: `tests/conftest.py` overwrites
    `OFFICE_ADMIN_DSN` with the test DSN so the code under test and the fixtures agree on
    one database, which means the process no longer knows the development DSN at all.
    Asking the environment here would test the test database twice and pass for the wrong
    reason.

    **It does not skip.** A runner has no `.env` and one database, so there is no
    development DSN there - and this job refuses a run with any skip in it, correctly: a
    skip reads as a pass in every summary. So where there is no development database the
    test falls back to `postgres`, the maintenance database every cluster has and nobody
    would ever mark disposable. Both cases assert the same thing: a database this suite
    was not pointed at is refused, from a real connection to it.
    """
    dev_dsn = _declared_development_dsn()
    with psycopg.connect(dev_dsn) as other:
        assert other.info.dbname != os.environ["OFFICE_ADMIN_DSN"].rsplit("/", 1)[-1], (
            "this must connect to a database other than the marked one under test"
        )
        with pytest.raises(NotADisposableDatabaseError) as refusal:
            assert_disposable(other)
        assert other.info.dbname in str(refusal.value)


def _declared_development_dsn() -> str:
    """The development DSN from `.env`, or the maintenance database as the stand-in.

    Read out of the FILE rather than the environment: `tests/conftest.py` overwrites
    `OFFICE_ADMIN_DSN` with the test DSN so the code under test and the fixtures agree on
    one database. Asking the environment here would connect to the test database, which is
    marked, and the test would fail for the wrong reason - or worse, pass one.
    """
    env_file = Path(__file__).resolve().parents[1] / ".env"
    test_dsn = os.environ["OFFICE_ADMIN_DSN"]  # conftest has pointed this at the test DB

    if env_file.exists():
        declared = {
            key.strip(): value.strip()
            for key, _, value in (
                line.partition("=")
                for line in env_file.read_text(encoding="utf-8").splitlines()
                if "=" in line and not line.lstrip().startswith("#")
            )
        }
        dev_dsn = declared.get("OFFICE_ADMIN_DSN", "").replace("+psycopg", "")
        if dev_dsn:
            with psycopg.connect(dev_dsn) as dev, psycopg.connect(test_dsn) as test:
                if dev.info.dbname != test.info.dbname:
                    return dev_dsn

    # No separate development database. `postgres` always exists and is never disposable.
    return re.sub(r"/[^/?]+(\?.*)?$", "/postgres", test_dsn)
