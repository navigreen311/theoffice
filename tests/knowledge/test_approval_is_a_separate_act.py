"""Approval, counsel review, and what it takes to be relied on.

RULED 22 SEPTEMBER 2026 (decisions entries 163, 164 and 165)
============================================================

    163. *"Approval is a separate act by a different named human. A compliance entry's
         approver is never its author. Approving writes its own audit event. Measured:
         status travels in the same statement as the text, with one writer and no
         event."*

    164. *"Counsel review is recorded by a named human on the lawyer's behalf, naming
         the reviewer, their firm, the date, and the specific claims confirmed. Never
         self-recorded alongside authorship. Measured: `counsel_reviewed_at` has no
         writer anywhere."*

    165. *"An entry is relied on only when approved and counsel-reviewed. Anything
         treating a draft as authoritative refuses. Measured: all 21 are draft, zero
         counsel-reviewed."*

THE THREE THAT CARRY THE RULINGS
================================

    `test_an_author_may_not_approve_their_own_entry` - 163. The defect was that they
    could, in the statement that created it.

    `test_a_review_without_its_claims_is_refused` - 164. A bare date is the boolean the
    rule exists to refuse, and the database refuses it too.

    `test_re_authoring_clears_both` - the one that makes the other two mean something.
    An approval surviving a rewrite is an approver's name on words they never read.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from broker import knowledge
from broker.db import connection
from broker.errors import NotAuthorized
from tests.conftest import declare_author, requires_db, undeclare_author

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "test-approval"
REF = "test/approval-v1"

AUTHOR = uuid.UUID("b0b0b0b0-0000-4000-8000-000000000163")
APPROVER = uuid.UUID("b0b0b0b0-0000-4000-8000-000000000164")
FIXTURE = uuid.UUID("b0b0b0b0-0000-4000-8000-000000000165")

REVIEWED_ON = datetime(2026, 9, 1, tzinfo=UTC)
CLAIMS = [
    "NRS 599B does not reach a call to a commercial property owner.",
    "Two-party consent applies to the recording, not to the transcript.",
]

ENTRY = {
    "framework": "FTC_TSR",
    "jurisdiction": ["FEDERAL"],
    "applicability_rule": "Outbound cold calls to property owners.",
    "agent_behavior_implication": "State identity and purpose before anything else.",
    "escalation_trigger": "The called party asserts a do-not-call registration.",
    "citation": "16 CFR 310",
}

#: An entry written straight into the table, so a CHECK is the only thing in its way.
#: The column list is the six required fields plus whatever the test is testing.
_BY_HAND = (
    "INSERT INTO compliance_library_entry "
    "  (venture_id, entry_ref, framework, jurisdiction, applicability_rule, "
    "   agent_behavior_implication, escalation_trigger, citation, authored_by{extra}) "
    "VALUES (%s, %s, 'FTC_TSR', ARRAY['FEDERAL'], 'r', 'i', 't', 'c', %s{values})"
)


@pytest.fixture(autouse=True)
def _accounts(admin: psycopg.Connection):
    declare_author(admin, AUTHOR, "Approval Test Author")
    declare_author(admin, APPROVER, "Approval Test Approver")
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin, token_hash) "
            "VALUES (%s, 'smoke-approver-0163', 'smoke-0163@approval.invalid', "
            "        'bearer_token', 'test_fixture', %s) "
            "ON CONFLICT (human_id) DO NOTHING",
            (FIXTURE, f"fixture-{FIXTURE.hex}"),
        )
    admin.commit()
    _wipe(admin)
    yield
    _wipe(admin)
    undeclare_author(admin, AUTHOR, APPROVER, FIXTURE)


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM compliance_library_entry WHERE venture_id = %s", (VENTURE,)
        )
    conn.commit()


def _refuses_by_hand(
    admin: psycopg.Connection, ref: str, extra: str, values: str, params: tuple
) -> None:
    """The CHECK fires on the statement, not on the commit, so the raise goes there."""
    with pytest.raises(psycopg.errors.CheckViolation), admin.cursor() as cur:
        cur.execute(
            _BY_HAND.format(extra=extra, values=values),
            (VENTURE, ref, AUTHOR, *params),
        )
    admin.rollback()
    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM compliance_library_entry WHERE entry_ref = %s", (ref,)
        )
        assert cur.fetchone()[0] == 0


async def _write(ref: str = REF, **overrides: Any) -> str:
    async with connection() as conn:
        return await knowledge.author_compliance_entry(
            conn, venture_id=VENTURE, entry_ref=ref, authored_by=AUTHOR,
            **{**ENTRY, **overrides},
        )


async def _approve(ref: str = REF, by: uuid.UUID = APPROVER) -> dict[str, Any]:
    async with connection() as conn:
        return await knowledge.approve_compliance_entry(
            conn, venture_id=VENTURE, entry_ref=ref, approved_by=by
        )


async def _review(
    ref: str = REF, by: uuid.UUID = APPROVER, **overrides: Any
) -> dict[str, Any]:
    async with connection() as conn:
        return await knowledge.record_counsel_review(
            conn, venture_id=VENTURE, entry_ref=ref, recorded_by=by,
            **{
                "reviewer_name": "Marta Reyes",
                "reviewer_firm": "Reyes & Okonkwo LLP",
                "reviewed_on": REVIEWED_ON,
                "claims_confirmed": CLAIMS,
                **overrides,
            },
        )


async def _entry(ref: str = REF) -> dict[str, Any]:
    async with connection() as conn:
        entries = await knowledge.compliance_entries(conn, VENTURE)
    return next(e for e in entries if e["entry_ref"] == ref)


# ============================================================== 163. approval

async def test_an_author_may_not_set_approved_while_writing():
    """**The defect, named.** `status` travelled in the same statement as the text.

    `author_compliance_entry` took it as a parameter, and the one caller that passed
    anything read it from a YAML field. So an author approved their own entry by typing
    a word above it, and nothing recorded that an approval had happened.
    """
    with pytest.raises(knowledge.KnowledgeError) as raised:
        await _write(status="approved")

    assert "may not approve their own entry" in str(raised.value)
    assert "163" in str(raised.value)


async def test_an_author_may_not_approve_their_own_entry():
    """**THE RULING.** *"A compliance entry's approver is never its author."*"""
    await _write()
    with pytest.raises(knowledge.KnowledgeError) as raised:
        await _approve(by=AUTHOR)

    assert "never its author" in str(raised.value)
    assert (await _entry())["status"] == "draft", "the refusal approved it anyway"


async def test_somebody_else_may():
    """**Load-bearing.** A rule that refused everybody would pass the test above."""
    await _write()
    approved = await _approve()

    assert approved["status"] == "approved"
    assert approved["approved_by"] == APPROVER
    assert approved["approved_at"] is not None
    assert approved["relied_on"] is False, "approved is half of it, not all of it"


async def test_a_fixture_may_not_approve():
    """Entry 148's distinction, at a third act. A fixture holds its roles honestly and
    is not somebody who can be asked about a decision recorded against them."""
    await _write()
    with pytest.raises(NotAuthorized) as raised:
        await _approve(by=FIXTURE)
    assert "test_fixture" in str(raised.value)


async def test_approving_twice_is_refused():
    """A second approval records nothing that was not already true.

    The same rule entries 149 and 159 apply to a re-grant and a repeated receipt, at the
    act where it matters most: an entry with two approvers is an entry where the second
    one's name is on a decision somebody else made.
    """
    await _write()
    first = await _approve()
    with pytest.raises(knowledge.KnowledgeError) as raised:
        await _approve()
    assert "already approved" in str(raised.value)
    assert (await _entry())["approved_at"] == first["approved_at"]


async def test_approving_an_entry_that_does_not_exist_is_refused():
    with pytest.raises(knowledge.KnowledgeError) as raised:
        await _approve(ref="test/never-written")
    assert "no entry" in str(raised.value)


def test_the_database_refuses_a_self_approval_over_the_admin_connection(admin):
    """**The control.** Migration 0057's CHECK, on the same row.

    `approved_by <> authored_by` compares two columns of one row, which is why it can be
    a CHECK at all - and why the approver lives on this table rather than in a side
    table of approvals that a script could write around.
    """
    _refuses_by_hand(
        admin, "test/self-approved",
        extra=", status, approved_by, approved_at",
        values=", 'approved', %s, now()", params=(AUTHOR,),
    )


def test_the_database_refuses_approved_with_no_approver(admin):
    """The status and the record cannot drift apart. A row reading `approved` with a
    NULL `approved_by` is the state before entry 163, preserved in one column."""
    _refuses_by_hand(
        admin, "test/bare-approved",
        extra=", status", values=", 'approved'", params=(),
    )


def test_the_database_refuses_an_approver_who_is_a_fixture(admin):
    """The FK asks whether the approver is an account. This asks whether it is a person,
    which a foreign key cannot - so it lives in the trigger 0056 installed."""
    with pytest.raises(psycopg.errors.RaiseException), admin.cursor() as cur:
        cur.execute(
            _BY_HAND.format(
                extra=", status, approved_by, approved_at",
                values=", 'approved', %s, now()",
            ),
            (VENTURE, "test/fixture-approved", AUTHOR, FIXTURE),
        )
    admin.rollback()


# ======================================================== 164. counsel review

async def test_a_counsel_review_names_the_reviewer_their_firm_and_the_claims():
    """**The column that had no writer for two weeks, written.**

    0039 added `counsel_reviewed_at`. V28 read it, the console read it, and no statement
    in the repository ever set it.
    """
    await _write()
    reviewed = await _review()

    assert reviewed["counsel_reviewed_at"] == REVIEWED_ON
    assert reviewed["counsel_reviewer_name"] == "Marta Reyes"
    assert reviewed["counsel_reviewer_firm"] == "Reyes & Okonkwo LLP"
    assert reviewed["counsel_recorded_by"] == APPROVER
    assert reviewed["counsel_claims_confirmed"] == CLAIMS
    assert reviewed["relied_on"] is False, "reviewed is the other half, not all of it"


async def test_the_two_dates_are_different_facts():
    """When counsel read it, and when somebody wrote that down.

    One column would let a review dated last March be recorded today with no trace of
    the gap - and the gap is what a reader needs to judge whether the review is current.
    """
    await _write()
    reviewed = await _review()

    assert reviewed["counsel_reviewed_at"] == REVIEWED_ON
    assert reviewed["counsel_recorded_at"] > REVIEWED_ON


@pytest.mark.parametrize("omit", ["reviewer_name", "reviewer_firm", "claims_confirmed"])
async def test_a_review_missing_any_of_its_fields_is_refused(omit: str):
    """Named, not counted, so the refusal says which one."""
    await _write()
    blank: dict[str, Any] = (
        {"claims_confirmed": []} if omit == "claims_confirmed" else {omit: "  "}
    )
    with pytest.raises(knowledge.KnowledgeError) as raised:
        await _review(**blank)
    assert omit in str(raised.value)


async def test_a_review_without_its_claims_is_refused():
    """**THE RULING'S SHARP EDGE.** *"...and the specific claims confirmed."*

    An entry is a mixture - the authoring format already says so about
    `claim_provenance`: *"an entry is a mixture, and an entry-level tag would round the
    mixture to whichever tag the author felt best about."* "A lawyer reviewed this
    entry" rounds the same mixture the same way.
    """
    await _write()
    with pytest.raises(knowledge.KnowledgeError):
        await _review(claims_confirmed=[])
    with pytest.raises(knowledge.KnowledgeError) as raised:
        await _review(claims_confirmed=["  "])
    assert "confirms nothing" in str(raised.value)
    assert (await _entry())["counsel_reviewed_at"] is None


async def test_an_author_may_not_record_the_review_of_their_own_entry():
    """*"Never self-recorded alongside authorship."*"""
    await _write()
    with pytest.raises(knowledge.KnowledgeError) as raised:
        await _review(by=AUTHOR)
    assert "self-recorded alongside authorship" in str(raised.value)


async def test_a_fixture_may_not_record_a_review():
    await _write()
    with pytest.raises(NotAuthorized):
        await _review(by=FIXTURE)


async def test_recording_a_second_review_is_refused():
    """There is nowhere here to keep two readings of one text, and silently replacing
    the first would lose a lawyer's name from the record."""
    await _write()
    await _review()
    with pytest.raises(knowledge.KnowledgeError) as raised:
        await _review(reviewer_name="Someone Else")
    assert "already carries a counsel review" in str(raised.value)
    assert (await _entry())["counsel_reviewer_name"] == "Marta Reyes"


def test_the_database_refuses_a_review_that_is_only_a_date(admin):
    """**The control.** All six fields or none - migration 0057's CHECK.

    This is the shape the column had for two weeks: a timestamp with nothing attached.
    It is now unrepresentable rather than merely unwritten.
    """
    _refuses_by_hand(
        admin, "test/bare-review",
        extra=", counsel_reviewed_at", values=", now()", params=(),
    )


def test_the_database_refuses_an_empty_claims_array(admin):
    """Six fields present and one of them saying nothing is the boolean again."""
    _refuses_by_hand(
        admin, "test/no-claims",
        extra=", counsel_reviewed_at, counsel_reviewer_name, counsel_reviewer_firm, "
              "counsel_recorded_by, counsel_recorded_at, counsel_claims_confirmed",
        values=", now(), 'M Reyes', 'Reyes LLP', %s, now(), '[]'",
        params=(APPROVER,),
    )


def test_the_database_refuses_a_review_recorded_by_the_author(admin):
    _refuses_by_hand(
        admin, "test/self-reviewed",
        extra=", counsel_reviewed_at, counsel_reviewer_name, counsel_reviewer_firm, "
              "counsel_recorded_by, counsel_recorded_at, counsel_claims_confirmed",
        values=", now(), 'M Reyes', 'Reyes LLP', %s, now(), '[\"a claim\"]'",
        params=(AUTHOR,),
    )


# ================================================= 165. relied on, or not

async def test_an_entry_is_relied_on_only_when_both_are_true():
    """**THE RULING.** Neither half implies the other.

    Approval is this Office saying the entry is the one to use. Counsel review is a
    lawyer saying the law in it is right. An entry approved and unreviewed is a decision
    about an unchecked claim; one reviewed and unapproved is a checked claim nobody
    adopted.
    """
    await _write()
    assert (await _entry())["relied_on"] is False

    await _approve()
    assert (await _entry())["relied_on"] is False, "approved alone is not relied on"

    await _review()
    entry = await _entry()
    assert entry["relied_on"] is True
    assert knowledge.is_relied_on(entry) is True


async def test_reviewed_but_unapproved_is_not_relied_on():
    """The other order, because the two halves are independent."""
    await _write()
    await _review()
    assert (await _entry())["relied_on"] is False


async def test_a_draft_explains_no_flag():
    """What Gate 6 reads. A flag reaches an agent as a constraint only if something
    behind it says what to do; a draft nobody adopted says nothing."""
    await _write(runtime_flag="tsr_disclosure_required")
    async with connection() as conn:
        assert await knowledge.flags_with_entries(conn, VENTURE) == set()

    await _approve()
    await _review()
    async with connection() as conn:
        assert await knowledge.flags_with_entries(conn, VENTURE) == {
            "tsr_disclosure_required"
        }


async def test_the_two_forms_of_the_predicate_agree():
    """`is_relied_on` in Python and `RELIED_ON_SQL` in the database, on the same rows.

    Two spellings of one rule is how a gate and a page come to disagree about whether an
    entry counts, which is the class of defect entry 153 measured on a different table.
    """
    await _write("test/none")
    await _write("test/approved-only")
    await _approve("test/approved-only")
    await _write("test/reviewed-only")
    await _review("test/reviewed-only")
    await _write("test/both")
    await _approve("test/both")
    await _review("test/both")

    async with connection() as conn:
        in_sql = await knowledge.relied_on_refs(conn, VENTURE)
        entries = await knowledge.compliance_entries(conn, VENTURE)

    in_python = {e["entry_ref"] for e in entries if knowledge.is_relied_on(e)}
    assert in_sql == in_python == {"test/both"}


# =============================================== the one that makes it mean something

async def test_re_authoring_clears_both():
    """**Load-bearing.** An approval that survived a rewrite is an approver's name on
    words they never read, and a counsel review that survived one is a lawyer's firm
    attached to claims they were never shown - which is worse than no review, because
    it reads as one.

    The same property `content_hash` gives certification: republishing decertifies.
    """
    await _write()
    await _approve()
    await _review()
    assert (await _entry())["relied_on"] is True

    await _write(citation="16 CFR 310, as amended")

    after = await _entry()
    assert after["citation"] == "16 CFR 310, as amended"
    assert after["status"] == "draft"
    assert after["approved_by"] is None
    assert after["approved_at"] is None
    assert after["counsel_reviewed_at"] is None
    assert after["counsel_reviewer_name"] is None
    assert after["counsel_reviewer_firm"] is None
    assert after["counsel_recorded_by"] is None
    assert after["counsel_claims_confirmed"] is None
    assert after["relied_on"] is False
