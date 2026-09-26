"""`ivan` is refused to anything but a human account, and every role read filters
revocation. Entries 206 and 207.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import psycopg
import pytest

from broker import account_origin, humans
from broker.db import connection
from broker.errors import NotAuthorized
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

SEED = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


async def _account(origin: str, name: str) -> uuid.UUID:
    async with connection() as conn:
        human_id, _ = await humans.create_human(
            conn, origin=origin, display_name=name,
            email=f"{uuid.uuid4().hex[:10]}@x.entry206.invalid",
        )
    return human_id


@pytest.fixture(autouse=True)
def wipe(admin: psycopg.Connection):
    def clean():
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM office_human_role WHERE human_id IN "
                " (SELECT human_id FROM office_human WHERE email LIKE %s)",
                ("%@x.entry206.invalid",),
            )
            cur.execute(
                "DELETE FROM office_human WHERE email LIKE %s",
                ("%@x.entry206.invalid",),
            )
        admin.commit()

    clean()
    yield
    clean()


# ------------------------------------------------------------------ entry 206

async def test_ivan_is_refused_to_a_test_fixture():
    """130 accounts held it and 128 were fixtures. `assert_named_human` was the only
    thing between them and founder authority, and entry 148 is what that costs."""
    human_id = await _account(account_origin.TEST_FIXTURE, "smoke-entry206")

    async with connection() as conn:
        with pytest.raises(NotAuthorized) as exc:
            await humans.grant_role(
                conn, human_id=human_id, role="ivan", granted_by=SEED
            )
    assert exc.value.context["origin"] == "test_fixture"
    assert "declares a human account first" in str(exc.value)


async def test_ivan_is_refused_to_a_service_account():
    """`origin <> 'human'`, not `origin = 'test_fixture'`. A third origin exists."""
    human_id = await _account(account_origin.SERVICE, "service-entry206")

    async with connection() as conn:
        with pytest.raises(NotAuthorized):
            await humans.grant_role(
                conn, human_id=human_id, role="ivan", granted_by=SEED
            )


async def test_ivan_is_granted_to_a_human():
    human_id = await _account(account_origin.HUMAN, "A person, entry 206")

    async with connection() as conn:
        await humans.grant_role(conn, human_id=human_id, role="ivan", granted_by=SEED)
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM office_human_role "
                " WHERE human_id = %s AND role = 'ivan' AND revoked_at IS NULL",
                (human_id,),
            )
            assert (await cur.fetchone())[0] == 1


@pytest.mark.parametrize("role", ["venture_operator", "compliance_officer"])
async def test_a_fixture_keeps_every_other_role(role):
    """The suites need these, and `assert_named_human` still guards the acts that name
    a signer. Only `ivan` is refused."""
    human_id = await _account(account_origin.TEST_FIXTURE, f"smoke-{role}")

    async with connection() as conn:
        await humans.grant_role(
            conn, human_id=human_id, role=role, venture_id="greenstone",
            granted_by=SEED,
        )


async def test_no_fixture_holds_a_live_ivan_role(admin: psycopg.Connection):
    """0065 revoked the 128. This is what stops them coming back by another door."""
    with admin.cursor() as cur:
        cur.execute(
            "SELECT h.display_name, h.origin FROM office_human h "
            "  JOIN office_human_role r ON r.human_id = h.human_id "
            " WHERE r.role = 'ivan' AND r.revoked_at IS NULL AND h.origin <> 'human'"
        )
        held = cur.fetchall()
    assert held == [], f"non-human accounts holding a live ivan role: {held}"


# ------------------------------------------------------------------ entry 207

#: Where a read of this table may legitimately omit `revoked_at`.
#:
#: `grant_role` INSERTs and `revoke_role` UPDATEs the column itself; a filter on either
#: would be a filter on the thing being written. `force_role` in the test helpers is the
#: deliberate bypass entry 206 documents.
_WRITES = ("INSERT INTO office_human_role", "UPDATE office_human_role")


def test_every_read_of_a_role_filters_revocation():
    """RULED 26 SEPTEMBER 2026 (entry 207).

    Entry 150 found three reads that ignored `revoked_at` and fixed them. Nothing
    stopped a fourth, and on 26 September a revoked `ivan` was read as live and reported
    as a fixture holding founder authority - by a query written in a session, not by
    this repository, whose seven reads all filter correctly.

    So the rule is pinned rather than re-fixed. The same shape as entry 200's
    `superseded_at` and entry 190's audit scanner: the column exists, and what is
    checked is that everybody consults it.
    """
    root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for source in sorted((root / "broker").glob("*.py")):
        text = source.read_text(encoding="utf-8")
        lines = text.split("\n")
        for match in re.finditer(r"office_human_role", text):
            line_no = text[: match.start()].count("\n")
            # A COMMENT IS NOT A READ. `attestation.py` names the table in prose, to say
            # what `ivan` is; a scanner that cannot tell that from a query reports a file
            # nobody can fix.
            if lines[line_no].lstrip().startswith("#"):
                continue
            # Wide enough to reach past a comment block INSIDE the statement:
            # `humans.py`'s attributable-actor query carries four lines of entry 150
            # between the JOIN and the filter it was fixed to include.
            window = text[max(0, match.start() - 200): match.end() + 900]
            if any(w in window for w in _WRITES):
                continue
            if "revoked_at" in window:
                continue
            offenders.append(f"{source.name}:{line_no + 1}")
    assert not offenders, (
        "these reads of office_human_role do not filter revoked_at: "
        f"{offenders}. A revoked role grants nothing (entry 150), and a read that "
        "ignores the column reports authority somebody took away."
    )
