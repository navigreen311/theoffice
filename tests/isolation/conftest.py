"""Fixtures for the isolation suite."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest


@pytest.fixture(autouse=True)
def _clean_shifts(admin: psycopg.Connection) -> Iterator[None]:
    """Shifts and working memory are shared state across tests.

    A leftover unflushed shift blocks the next test's assignment for a reason that
    test has nothing to do with - and the failure looks exactly like the control
    working, which is the worst kind of false positive.
    """
    _wipe(admin)
    yield
    _wipe(admin)


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM agent_working_memory")
        cur.execute("DELETE FROM shift_assignment")
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute("DELETE FROM audit_log")
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
    conn.commit()
