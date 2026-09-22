"""The compliance library is per venture, and a draft says so - migration 0039.

Two properties, and the first is the one the change exists for.

**One venture cannot overwrite another's entry.** The table was keyed on `entry_ref`
alone, so authoring an entry under a ref another venture already used replaced that
venture's text - and every check stayed green, because they ask whether a ref resolves
and never whose entry answered. `broker/compliance_couplings.py` recorded the property;
`scripts/load_compliance_library.py` recorded it and said nothing structural prevented
it.

**A draft reads as a draft.** `status` and `claim_provenance` were in the files and not
in the table, so an entry written by hand, tagged `draft_pending_claim_library_approval`,
whose central claim its own author recorded as a contradiction between two artifacts,
read out of the database exactly like one taken from a statute.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import knowledge
from broker.db import connection
from tests.conftest import (
    declare_author,
    rely_on_entry,
    requires_db,
    undeclare_author,
)

pytestmark = [requires_db, pytest.mark.db]

AUTHOR = uuid.UUID("00000000-0000-5000-8000-0000000000e1")
#: Entries 163/164: neither the approver nor the counsel recorder is the author.
APPROVER = uuid.UUID("00000000-0000-5000-8000-0000000000e2")
MINE, THEIRS = "test-mine", "test-theirs"
REF = "test/shared-ref-v1"

ENTRY = {
    "framework": "FTC_TSR",
    "jurisdiction": ["FEDERAL"],
    "applicability_rule": "Outbound cold calls to property owners.",
    "agent_behavior_implication": "State identity and purpose before anything else.",
    "escalation_trigger": "The called party asserts a do-not-call registration.",
    "citation": "16 CFR 310",
}


@pytest.fixture(autouse=True)
def _clean(admin: psycopg.Connection):
    def wipe() -> None:
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM compliance_library_entry WHERE venture_id = ANY(%s)",
                ([MINE, THEIRS],),
            )
        admin.commit()

    # Entry 162: `authored_by` must resolve to an `origin='human'` account.
    declare_author(admin, AUTHOR, "Per-Venture Test Author")
    declare_author(admin, APPROVER, "Per-Venture Test Approver")
    wipe()
    yield
    wipe()
    undeclare_author(admin, AUTHOR, APPROVER)


async def test_two_ventures_hold_the_same_ref_with_different_text():
    """The regression this migration exists to prevent, stated as a property.

    On the single key the second write was an UPDATE of the first venture's row, and the
    loader reported it as a replacement - the overwrite, described as routine.
    """
    async with connection() as conn:
        await knowledge.author_compliance_entry(
            conn, venture_id=MINE, entry_ref=REF, authored_by=AUTHOR,
            **{**ENTRY, "agent_behavior_implication": "Mine says this."},
        )
        await knowledge.author_compliance_entry(
            conn, venture_id=THEIRS, entry_ref=REF, authored_by=AUTHOR,
            **{**ENTRY, "agent_behavior_implication": "Theirs says something else."},
        )

        mine = await knowledge.compliance_entries(conn, MINE)
        theirs = await knowledge.compliance_entries(conn, THEIRS)

    assert [e["entry_ref"] for e in mine] == [REF]
    assert mine[0]["agent_behavior_implication"] == "Mine says this."
    assert theirs[0]["agent_behavior_implication"] == "Theirs says something else.", (
        "writing one venture's entry must not touch another's under the same ref"
    )


async def test_a_flag_another_venture_explains_is_not_explained_here(admin):
    """What Gate 6 reads. Unscoped, Greenstone's entry explained Burkham's flag.

    The entry is approved and counsel-reviewed here because entry 165 added a second
    term to this same query: a flag is explained when a RELIED-ON entry carries it, and
    a draft carrying it explains nothing. Both terms are exercised - the venture term by
    `mine`, the standing term by the test below.
    """
    async with connection() as conn:
        await knowledge.author_compliance_entry(
            conn, venture_id=THEIRS, entry_ref=REF, authored_by=AUTHOR,
            runtime_flag="tsr_disclosure_required", **ENTRY,
        )
    rely_on_entry(admin, venture_id=THEIRS, entry_ref=REF, approver=APPROVER)

    async with connection() as conn:
        mine = await knowledge.flags_with_entries(conn, MINE)
        theirs = await knowledge.flags_with_entries(conn, THEIRS)

    assert "tsr_disclosure_required" in theirs
    assert "tsr_disclosure_required" not in mine


async def test_a_draft_explains_no_flag():
    """**Entry 165, on the query Gate 6 reads.**

    The entry exists, belongs to this venture, and names the flag. It is a draft, so it
    explains nothing - which is the whole rule, since the flag reaches an agent as a
    constraint only if there is something behind it to constrain by.
    """
    async with connection() as conn:
        await knowledge.author_compliance_entry(
            conn, venture_id=MINE, entry_ref=REF, authored_by=AUTHOR,
            runtime_flag="tsr_disclosure_required", **ENTRY,
        )
        assert await knowledge.flags_with_entries(conn, MINE) == set()


async def test_an_entry_is_a_draft_until_something_says_otherwise():
    """The default is the cautious direction, and it is the column's, not the caller's.

    A default of `approved` would assert a review that did not happen every time somebody
    omitted the field - which is the failure this closes rather than a shortcut round it.
    """
    async with connection() as conn:
        await knowledge.author_compliance_entry(
            conn, venture_id=MINE, entry_ref=REF, authored_by=AUTHOR, **ENTRY,
        )
        entries = await knowledge.compliance_entries(conn, MINE)

    assert entries[0]["status"] == "draft"
    assert entries[0]["counsel_reviewed_at"] is None, (
        "no loader and no file can supply this: a person reviews an entry"
    )
    assert entries[0]["claim_provenance"] == []


async def test_status_and_provenance_survive_the_round_trip():
    """The file's own standing, readable back out of the table.

    Burkham's library carries eighteen entries at `draft_pending_claim_library_approval`
    and a `claim_provenance` list per entry tagging each claim sourced, reconstructed or
    proposed. None of it had a column, so none of it reached anything that displays an
    entry.
    """
    provenance = [
        {"claim": "Nevada's regime is contradicted between two live artifacts",
         "tag": "sourced",
         "source": "Office entry says all-party; Console list includes NV as one-party"},
    ]
    async with connection() as conn:
        await knowledge.author_compliance_entry(
            conn, venture_id=MINE, entry_ref=REF, authored_by=AUTHOR,
            status="draft_pending_claim_library_approval",
            claim_provenance=provenance, **ENTRY,
        )
        entries = await knowledge.compliance_entries(conn, MINE)

    assert entries[0]["status"] == "draft_pending_claim_library_approval"
    assert entries[0]["claim_provenance"] == provenance


async def test_a_status_the_vocabulary_does_not_have_is_refused():
    async with connection() as conn:
        with pytest.raises(knowledge.KnowledgeError) as refusal:
            await knowledge.author_compliance_entry(
                conn, venture_id=MINE, entry_ref=REF, authored_by=AUTHOR,
                status="counsel_says_fine", **ENTRY,
            )
    assert "status must be one of" in str(refusal.value)


async def test_an_entry_with_no_venture_is_refused():
    """No default, at the one site that decides whose entry this is."""
    async with connection() as conn:
        with pytest.raises(knowledge.KnowledgeError) as refusal:
            await knowledge.author_compliance_entry(
                conn, venture_id="  ", entry_ref=REF, authored_by=AUTHOR, **ENTRY,
            )
    assert "venture_id" in str(refusal.value)


async def test_the_downgrade_refuses_rather_than_dropping_a_venture(
    admin: psycopg.Connection,
):
    """Migration 0039's downgrade, on the only case CI can never reach.

    The reversibility job round-trips on an EMPTY database, so it will never meet two
    ventures holding one ref - which is precisely the state a single-key table cannot
    represent. Left to choose, the downgrade would drop one venture's entry and say
    nothing; whoever lost it would find out later, from a gate.

    Run here as the SQL the migration runs, rather than by driving alembic: this asserts
    the guard's behaviour without tearing down the database the rest of the suite is
    using.
    """
    guard = """
        DO $$
        DECLARE dupes TEXT;
        BEGIN
          SELECT string_agg(entry_ref, ', ' ORDER BY entry_ref) INTO dupes
          FROM (SELECT entry_ref FROM compliance_library_entry
                 GROUP BY entry_ref HAVING count(*) > 1) d;
          IF dupes IS NOT NULL THEN
            RAISE EXCEPTION
              'cannot restore a single-key compliance library: % held by more than one '
              'venture.', dupes;
          END IF;
        END $$
    """
    async with connection() as conn:
        for venture in (MINE, THEIRS):
            await knowledge.author_compliance_entry(
                conn, venture_id=venture, entry_ref=REF, authored_by=AUTHOR, **ENTRY,
            )

    with admin.cursor() as cur, pytest.raises(psycopg.errors.RaiseException) as refusal:
        cur.execute(guard)
    admin.rollback()
    assert REF in str(refusal.value), "the refusal names the ref that is shared"
