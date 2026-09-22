"""A compliance entry names a real author.

RULED 22 SEPTEMBER 2026 (decisions entry 162)
=============================================

    *"A compliance entry names a real author. `authored_by` must resolve to an
    `origin='human'` account. Report the 21 existing rows; don't rewrite them."*

WHAT WAS MEASURED
=================

    Every row in `compliance_library_entry`, 22 September 2026:

        19  burkham-wickmont  87c873da...  smoke-operator-0eda802c   test_fixture
         2  greenstone        00000000-0000-5000-8000-00000000aaaa   no such account

    Twenty-one of twenty-one, and not one names a person. `authored_by` has been
    `UUID NOT NULL` with no foreign key since migration 0012, so any value at all was
    accepted - and nothing in the codebase ever resolved it.

THE TWO THAT CARRY THE RULING
=============================

    `test_the_database_refuses_even_over_the_admin_connection` - the Python check is the
    message; the trigger is the control, and a control only the application enforces is
    an application everybody can go around.

    `test_the_report_rewrites_nothing` - *"don't rewrite them."* The remedy for the
    twenty-one is to be seen, not to be assigned an author nobody knows.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import account_origin, humans, knowledge
from broker.db import connection
from broker.errors import NotAuthorized
from tests.conftest import declare_author, requires_db, undeclare_author

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "test-real-author"
PERSON = uuid.UUID("a0a0a0a0-0000-4000-8000-000000000162")
FIXTURE = uuid.UUID("a0a0a0a0-0000-4000-8000-000000000163")
#: The id `scripts/dev-up.sh` passes, which Greenstone's two live entries carry and
#: which has never matched a row in `office_human`.
NOBODY = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")

ENTRY = {
    "framework": "FTC_TSR",
    "jurisdiction": ["FEDERAL"],
    "applicability_rule": "Outbound cold calls to property owners.",
    "agent_behavior_implication": "State identity and purpose before anything else.",
    "escalation_trigger": "The called party asserts a do-not-call registration.",
    "citation": "16 CFR 310",
}


@pytest.fixture(autouse=True)
def _accounts(admin: psycopg.Connection):
    declare_author(admin, PERSON, "Author Who Is A Person")
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin, token_hash) "
            "VALUES (%s, 'smoke-author-0162', 'smoke-0162@author.invalid', "
            "        'bearer_token', %s, %s) "
            "ON CONFLICT (human_id) DO NOTHING",
            (FIXTURE, account_origin.TEST_FIXTURE, f"fixture-{FIXTURE.hex}"),
        )
    admin.commit()
    _wipe(admin)
    yield
    _wipe(admin)
    undeclare_author(admin, PERSON, FIXTURE)


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM compliance_library_entry WHERE venture_id = %s", (VENTURE,)
        )
    conn.commit()


async def _author(author: uuid.UUID, ref: str = "test/real-author-v1") -> str:
    async with connection() as conn:
        return await knowledge.author_compliance_entry(
            conn, venture_id=VENTURE, entry_ref=ref, authored_by=author, **ENTRY
        )


def _plant(conn: psycopg.Connection, ref: str, author: uuid.UUID) -> None:
    """A row the controls would refuse, planted the only way the live twenty-one exist.

    They predate both controls, so reproducing them means standing both down for one
    statement: the trigger AND the foreign key, which enforces on a new row even though
    it is NOT VALID. The constraint goes back exactly as migration 0056 leaves it.

    This is deliberately awkward. Writing an unattributed entry should take more than
    one statement, and the test that describes the twenty-one should not have an easier
    path to making one than the application does.
    """
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE compliance_library_entry "
            "  DROP CONSTRAINT compliance_entry_author_is_an_account"
        )
        cur.execute(
            "ALTER TABLE compliance_library_entry "
            "  DISABLE TRIGGER a_compliance_entry_names_a_real_author"
        )
        cur.execute(
            "INSERT INTO compliance_library_entry "
            "  (venture_id, entry_ref, framework, jurisdiction, applicability_rule, "
            "   agent_behavior_implication, escalation_trigger, citation, authored_by) "
            "VALUES (%s, %s, 'FTC_TSR', ARRAY['FEDERAL'], 'r', 'i', 't', 'c', %s)",
            (VENTURE, ref, author),
        )
        cur.execute(
            "ALTER TABLE compliance_library_entry "
            "  ENABLE TRIGGER a_compliance_entry_names_a_real_author"
        )
        cur.execute(
            "ALTER TABLE compliance_library_entry "
            "  ADD CONSTRAINT compliance_entry_author_is_an_account "
            "  FOREIGN KEY (authored_by) REFERENCES office_human(human_id) NOT VALID"
        )
    conn.commit()


def _rows(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM compliance_library_entry WHERE venture_id = %s",
            (VENTURE,),
        )
        return int(cur.fetchone()[0])


# --------------------------------------------------------------- the rule, in Python

async def test_a_person_may_author_an_entry():
    """**Load-bearing.** A check that refused everything would pass every test below."""
    assert await _author(PERSON) == "test/real-author-v1"


async def test_a_fixture_may_not_author_an_entry(admin):
    """The nineteen. `smoke-operator-0eda802c` held `compliance_officer` honestly.

    What a fixture is not is somebody who can be asked about a claim made about the
    law, and that is a different question from what it is allowed to do - the same
    distinction entry 148 drew for deciding a proposal.
    """
    with pytest.raises(NotAuthorized) as raised:
        await _author(FIXTURE)

    assert "test_fixture" in str(raised.value)
    assert "smoke-author-0162" in str(raised.value), "the message does not name the account"
    assert _rows(admin) == 0, "the refusal left a row behind"


async def test_an_id_that_resolves_to_nobody_may_not_author_an_entry(admin):
    """The two. Greenstone's entries carry exactly this id.

    A separate message from the fixture case, because they are separate mistakes: this
    one is a placeholder or a typo, and the other is a real account.
    """
    with pytest.raises(NotAuthorized) as raised:
        await _author(NOBODY)

    assert "not an account" in str(raised.value)
    assert _rows(admin) == 0


async def test_the_refusal_comes_before_the_insert(admin):
    """Checked first, so a refusal leaves nothing to clean up.

    `author_compliance_entry` is an upsert, so a check placed after the statement would
    have overwritten a good entry with a bad author's text and then complained.
    """
    await _author(PERSON)
    with pytest.raises(NotAuthorized):
        await _author(FIXTURE)

    async with connection() as conn:
        entries = await knowledge.compliance_entries(conn, VENTURE)
    assert len(entries) == 1


# ------------------------------------------------------- the rule, at the database

def test_the_database_refuses_even_over_the_admin_connection(admin):
    """**THE RULING'S CONTROL.** Migration 0056's trigger, reached by hand SQL.

    The Python check raises the message an operator can read. This is the one that
    cannot be argued with: the nineteen were written by a script, and a rule only
    `broker/knowledge.py` enforces is a rule the next script does not get.
    """
    with pytest.raises(psycopg.errors.RaiseException) as raised, admin.cursor() as cur:
        cur.execute(
            "INSERT INTO compliance_library_entry "
            "  (venture_id, entry_ref, framework, jurisdiction, applicability_rule, "
            "   agent_behavior_implication, escalation_trigger, citation, "
            "   authored_by) "
            "VALUES (%s, 'test/by-hand-v1', 'FTC_TSR', ARRAY['FEDERAL'], 'r', "
            "        'i', 't', 'c', %s)",
            (VENTURE, FIXTURE),
        )
    admin.rollback()
    assert "real author" in str(raised.value) or "stand behind" in str(raised.value)
    assert _rows(admin) == 0


def test_the_foreign_key_is_not_valid_and_stays_that_way(admin):
    """*"Report the 21 existing rows; don't rewrite them."*

    A VALIDATED constraint would have required deleting or reassigning Greenstone's two
    before the migration could run, and the rows it would fail on are the evidence. This
    reads `pg_constraint` so that "we should just validate it" is a failing test rather
    than a tidy-up somebody does on a Friday.
    """
    with admin.cursor() as cur:
        cur.execute(
            "SELECT convalidated FROM pg_constraint "
            " WHERE conname = 'compliance_entry_author_is_an_account'"
        )
        row = cur.fetchone()
    assert row is not None, "the foreign key is missing"
    assert row[0] is False, (
        "the author foreign key was validated, which can only have happened by "
        "rewriting or deleting the rows entry 162 says to leave alone"
    )


async def test_an_update_is_refused_too(admin):
    """The loader re-running over the nineteen is an UPDATE, and it is now refused.

    A refusal, not a rewrite: the row keeps its text and its existing `authored_by`.
    What stops is the pretence that a fixture re-authored it today.
    """
    await _author(PERSON)
    with pytest.raises(psycopg.errors.RaiseException), admin.cursor() as cur:
        cur.execute(
            "UPDATE compliance_library_entry SET authored_by = %s "
            " WHERE venture_id = %s",
            (FIXTURE, VENTURE),
        )
    admin.rollback()

    with admin.cursor() as cur:
        cur.execute(
            "SELECT authored_by FROM compliance_library_entry WHERE venture_id = %s",
            (VENTURE,),
        )
        assert cur.fetchone()[0] == PERSON


# ------------------------------------------------------------------- the report

async def test_the_report_names_the_author_and_how_it_is_wrong(admin):
    """`test_fixture` and `unresolved` are separate words for separate mistakes."""
    await _author(PERSON)
    # Two rows the controls would refuse, planted as the existing twenty-one exist.
    _plant(admin, "test/by-a-fixture", FIXTURE)
    _plant(admin, "test/by-nobody", NOBODY)

    async with connection() as conn:
        report = await knowledge.compliance_authorship(conn, VENTURE)

    by_ref = {e["entry_ref"]: e for e in report["entries"]}
    assert by_ref["test/real-author-v1"]["author_origin"] == account_origin.HUMAN
    assert by_ref["test/real-author-v1"]["names_a_person"] is True
    assert by_ref["test/by-a-fixture"]["author_origin"] == account_origin.TEST_FIXTURE
    assert by_ref["test/by-a-fixture"]["author_name"] == "smoke-author-0162"
    assert by_ref["test/by-nobody"]["author_origin"] == knowledge.AUTHOR_UNRESOLVED
    assert by_ref["test/by-nobody"]["author_name"] is None

    assert report["total"] == 3
    assert report["names_a_person"] == 1
    assert report["names_a_fixture"] == 1
    assert report["author_unresolved"] == 1


async def test_the_report_rewrites_nothing(admin):
    """**THE RULING.** *"Report the 21 existing rows; don't rewrite them."*

    Asserted by reading every column before and after, because "rewrites nothing" is a
    statement about what is NOT written and there is no one field to watch.
    """
    await _author(PERSON)
    with admin.cursor() as cur:
        cur.execute(
            "SELECT * FROM compliance_library_entry WHERE venture_id = %s", (VENTURE,)
        )
        before = cur.fetchall()

    async with connection() as conn:
        await knowledge.compliance_authorship(conn, VENTURE)
        await knowledge.compliance_authorship(conn)

    with admin.cursor() as cur:
        cur.execute(
            "SELECT * FROM compliance_library_entry WHERE venture_id = %s", (VENTURE,)
        )
        assert cur.fetchall() == before


async def test_an_entry_with_no_account_still_appears_in_the_report(admin):
    """**Load-bearing.** A LEFT JOIN, so the failure cannot hide in the query's shape.

    An inner join would drop Greenstone's two entries from a report whose whole subject
    is that they have no author.
    """
    _plant(admin, "test/orphan-author", NOBODY)

    async with connection() as conn:
        report = await knowledge.compliance_authorship(conn, VENTURE)

    assert [e["entry_ref"] for e in report["entries"]] == ["test/orphan-author"]
    assert report["author_unresolved"] == 1


async def test_the_report_returns_no_verdict(admin):
    """It counts. It never passes or fails.

    A boolean would read `fail` today and for as long as the twenty-one sit in the
    table, which is a signal that stops carrying information the moment it is first
    seen. What is useful is the list.

    Asserted on the returned shape rather than by grepping the source, so that a
    docstring explaining why there is no verdict does not fail the test that says so.
    """
    await _author(PERSON)
    async with connection() as conn:
        report = await knowledge.compliance_authorship(conn, VENTURE)

    top_level = {k: v for k, v in report.items() if k != "entries"}
    assert all(isinstance(v, int) for v in top_level.values()), (
        f"the report carries a non-count at the top level: {top_level}"
    )
    assert not any(isinstance(v, bool) for v in top_level.values())


# ------------------------------------------------- the rule, stated where it is shared

async def test_assert_named_human_by_id_is_the_shared_rule():
    """Beside `assert_named_human`, and asking the same question of a different input.

    `assert_named_human` takes the account that turned up with a token, so it can only
    vouch for the caller. `authored_by` is an id written about somebody by somebody
    else, which is the half nobody was checking.
    """
    async with connection() as conn:
        await humans.assert_named_human_by_id(
            conn, human_id=PERSON, act="author a compliance library entry"
        )
        for bad in (FIXTURE, NOBODY):
            with pytest.raises(NotAuthorized):
                await humans.assert_named_human_by_id(
                    conn, human_id=bad, act="author a compliance library entry"
                )


def test_the_sibling_authoring_functions_are_deliberately_untouched():
    """Entry 162 rules on compliance entries. `author_playbook` and `author_persona`
    take the same unchecked `authored_by` and are left alone, because extending a rule
    by analogy is inventing its scope rather than recording it.

    Asserted so the omission reads as a decision rather than as something missed.
    """
    import inspect

    for name in ("author_playbook", "author_persona"):
        source = inspect.getsource(getattr(knowledge, name))
        assert "assert_named_human_by_id" not in source, (
            f"{name} now checks its author, which entry 162 did not rule on - if that "
            "is wanted, it needs its own ruling and its own ledger entry"
        )
