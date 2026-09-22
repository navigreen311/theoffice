"""An entry with no `status` is a draft, and all three places say so - entry 104.

**They did not.** The loader defaulted a missing status to `draft` and the quality checker
defaulted it to `approved`, so one file read two ways: an author who omitted the field got
a green line from the checker and a draft row in the database, and whichever they looked
at last was the answer.

Ivan's ruling of 15 September is the tie-breaker: an entry no lawyer has reviewed must
never read as settled. **Silence is not approval.** This pins the agreement between the
three defaults - the column's, the function's and the checker's - because the defect was
not any one of them being wrong, it was two of them disagreeing.
"""

from __future__ import annotations

import uuid

import pytest

from broker import knowledge
from broker.db import connection
from scripts.check_compliance_library import (
    APPROVED_STATUS,
    DEFAULT_STATUS,
)
from tests.conftest import declare_author, requires_db, undeclare_author

pytestmark = [requires_db, pytest.mark.db]

AUTHOR = uuid.UUID("00000000-0000-5000-8000-0000000000d4")
VENTURE = "test-missing-status"

ENTRY = {
    "framework": "FTC_TSR",
    "jurisdiction": ["FEDERAL"],
    "applicability_rule": "Outbound cold calls to property owners in this venture.",
    "agent_behavior_implication": (
        "State identity, the company and the purpose of the call before anything else."
    ),
    "escalation_trigger": "The called party asserts a do-not-call registration.",
    "citation": "16 CFR 310.4(d)",
}


def test_the_checker_does_not_read_a_missing_status_as_approved():
    """The checker's half. `DEFAULT_STATUS` is what an absent field is taken to be."""
    assert DEFAULT_STATUS != APPROVED_STATUS, (
        "a missing status must not read as approved: silence is not a review"
    )
    assert DEFAULT_STATUS == "draft"


async def test_the_loader_path_does_not_read_a_missing_status_as_approved(admin):
    """The database's half, through the function the loader calls.

    Asserted against a written row rather than a signature, because the default that
    matters is the one that reaches the table - the column carries one too, and this
    fails if either drifts.
    """
    # Entry 162: `authored_by` must resolve to an `origin='human'` account.
    declare_author(admin, AUTHOR, "Missing-Status Test Author")
    try:
        async with connection() as conn:
            await knowledge.author_compliance_entry(
                conn, venture_id=VENTURE, entry_ref="test/no-status-v1",
                authored_by=AUTHOR, **ENTRY,
            )
            entries = await knowledge.compliance_entries(conn, VENTURE)

        assert entries[0]["status"] == DEFAULT_STATUS, (
            "the row a file with no status produces must be a draft, and must agree "
            "with what the checker reports about that same file"
        )
        assert entries[0]["status"] != APPROVED_STATUS
        assert entries[0]["counsel_reviewed_at"] is None
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM compliance_library_entry WHERE venture_id = %s", (VENTURE,)
            )
        admin.commit()
        undeclare_author(admin, AUTHOR)
