"""Approval and counsel review are separate acts

Revision ID: 0057
Revises: 0056

Ruled 22 September 2026 (Ivan Green), decisions entries 163, 164 and 165:

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

WHAT `status` WAS
=================

    A column in the same INSERT as the text, set by whoever wrote it, defaulting to
    'draft' and reachable as 'approved' from one place: a field in a YAML file read by
    `scripts/load_compliance_library.py` over the admin DSN. No second party, no role,
    no audit event. An author could approve their own entry in the statement that
    created it - and the only reason none ever did is that no file carries the word.

    `counsel_reviewed_at` was worse: added by 0039, read by V28 and by the console, and
    **written by nothing at all.** A column that only ever reads NULL is a question the
    schema asks and no surface answers.

WHAT THE COLUMNS SAY NOW
========================

    approved_by             who approved. NOT the author - a CHECK, on the same row.
    approved_at             when.

    counsel_reviewed_at     already existed, and now means what it says: **the date the
                            lawyer reviewed it.** Kept rather than renamed because V28
                            and the console already read it, and a rename would move
                            what those resolve to for no gain.
    counsel_reviewer_name   the lawyer. A person, not a firm.
    counsel_reviewer_firm   who they practise with.
    counsel_recorded_by     the named human who wrote this down on their behalf. NOT the
                            author.
    counsel_recorded_at     when they wrote it down - a different fact from when counsel
                            read it, and conflating them is how a review dated last
                            March gets recorded today with no trace of the gap.
    counsel_claims_confirmed  WHICH claims counsel confirmed, as a JSON array. Never
                            empty when present.

WHY THE CLAIMS ARE A LIST AND NOT A BOOLEAN
===========================================

    `claim_provenance` is already per-claim rather than per-entry, for the reason stated
    in the authoring file: *"an entry is a mixture, and an entry-level tag would round
    the mixture to whichever tag the author felt best about."* A counsel review is the
    same mixture. "A lawyer read this entry" rounds four sourced claims and one
    reconstructed one into a single yes.

TWO CHECKS, ON THE SAME ROW, WHICH IS WHY THEY CAN BE CHECKS
============================================================

    `approved_by <> authored_by` and `counsel_recorded_by <> authored_by` both compare
    two columns of one row, so a CHECK constraint can do it - no trigger needed, and no
    denormalised copy of anything. That is the whole reason the approver lives on this
    table rather than in a side table of approvals.

    What a CHECK cannot ask is whether those ids are PEOPLE. That goes in the trigger
    0056 already installed, which grows two cases and keeps its name.

VALIDATED FOREIGN KEYS, UNLIKE 0056'S
=====================================

    `authored_by`'s foreign key is NOT VALID for ever, because twenty-one existing rows
    would fail it. These two are validated normally: no row has ever carried an approver
    or a counsel recorder, so there is nothing to grandfather. The difference is worth
    seeing in the DDL - a NOT VALID constraint should look unusual.

NO BACKFILL, AND THE 21 STAY DRAFT
==================================

    Every existing row has `status = 'draft'` and NULL in all seven new columns, so both
    CHECKs hold on arrival. Nothing is approved by this migration. Under entry 165 that
    means **no compliance library entry in this system is currently relied on**, which
    is a true statement about where the work stands and not a regression.
"""
from __future__ import annotations

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

NEW_COLUMNS = (
    ("approved_by", "UUID"),
    ("approved_at", "TIMESTAMPTZ"),
    ("counsel_reviewer_name", "TEXT"),
    ("counsel_reviewer_firm", "TEXT"),
    ("counsel_recorded_by", "UUID"),
    ("counsel_recorded_at", "TIMESTAMPTZ"),
    ("counsel_claims_confirmed", "JSONB"),
)

#: The trigger 0056 installed, restated whole each time it grows. `CREATE OR REPLACE`
#: needs the entire body, and a migration that patched it would be a migration nobody
#: could read without opening the previous one.
AUTHOR_CLAUSES = """
          SELECT h.origin, h.display_name INTO who_origin, who
            FROM office_human h WHERE h.human_id = NEW.authored_by;
          IF who_origin IS NULL THEN
            RAISE EXCEPTION USING MESSAGE =
              'compliance entry ' || NEW.entry_ref || ' names an author ('
              || NEW.authored_by || ') that is not an account on this Office. '
              || 'Entry 162: a compliance entry names a real author.';
          END IF;
          IF who_origin <> 'human' THEN
            RAISE EXCEPTION USING MESSAGE =
              'compliance entry ' || NEW.entry_ref || ' names ' || who
              || ' as its author, which is a ' || who_origin || ' account. '
              || 'Entry 162: a compliance entry is a claim about the law that '
              || 'somebody has to stand behind, and a fixture cannot be asked '
              || 'about it.';
          END IF;
"""

APPROVER_AND_RECORDER_CLAUSES = """
          -- Entry 163. The foreign key asks "is an account"; this asks "is a person".
          IF NEW.approved_by IS NOT NULL THEN
            SELECT h.origin, h.display_name INTO who_origin, who
              FROM office_human h WHERE h.human_id = NEW.approved_by;
            IF who_origin <> 'human' THEN
              RAISE EXCEPTION USING MESSAGE =
                'compliance entry ' || NEW.entry_ref || ' was approved by ' || who
                || ', which is a ' || who_origin || ' account. Entry 163: approval is '
                || 'an act by a named human, and a fixture cannot be held to one.';
            END IF;
          END IF;

          -- Entry 164. Recording a review on a lawyer's behalf is the same kind of act.
          IF NEW.counsel_recorded_by IS NOT NULL THEN
            SELECT h.origin, h.display_name INTO who_origin, who
              FROM office_human h WHERE h.human_id = NEW.counsel_recorded_by;
            IF who_origin <> 'human' THEN
              RAISE EXCEPTION USING MESSAGE =
                'compliance entry ' || NEW.entry_ref || ' has a counsel review '
                || 'recorded by ' || who || ', which is a ' || who_origin
                || ' account. Entry 164: a review is recorded by a named human on '
                || 'the lawyer''s behalf.';
            END IF;
          END IF;
"""


def _trigger_function(body: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION compliance_entry_author_is_a_person() RETURNS trigger
        AS $$
        DECLARE
          who         TEXT;
          who_origin  TEXT;
        BEGIN
{body}
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """


def upgrade() -> None:
    for name, kind in NEW_COLUMNS:
        op.execute(f"ALTER TABLE compliance_library_entry ADD COLUMN {name} {kind}")

    op.execute("""
        ALTER TABLE compliance_library_entry
          ADD CONSTRAINT compliance_entry_approver_is_an_account
          FOREIGN KEY (approved_by) REFERENCES office_human(human_id)
    """)
    op.execute("""
        ALTER TABLE compliance_library_entry
          ADD CONSTRAINT compliance_entry_counsel_recorder_is_an_account
          FOREIGN KEY (counsel_recorded_by) REFERENCES office_human(human_id)
    """)

    # ------------------------------------------------------------------ entry 163
    op.execute("""
        ALTER TABLE compliance_library_entry
          ADD CONSTRAINT approval_is_a_separate_act CHECK (
            (status = 'approved') = (approved_by IS NOT NULL)
            AND (approved_by IS NOT NULL) = (approved_at IS NOT NULL)
            AND (approved_by IS NULL OR approved_by <> authored_by)
          )
    """)
    op.execute("""
        COMMENT ON CONSTRAINT approval_is_a_separate_act
             ON compliance_library_entry IS
        'Entry 163. Three clauses: approved means somebody approved it, an approver has '
        'a date, and the approver is never the author. The third is the ruling; the '
        'first two stop the status and the record drifting apart.'
    """)

    # ------------------------------------------------------------------ entry 164
    #
    # ALL SIX OR NONE. A review missing its firm is a review nobody can chase, and a
    # review missing its claims is the boolean entry 164 exists to refuse.
    op.execute("""
        ALTER TABLE compliance_library_entry
          ADD CONSTRAINT counsel_review_names_its_source CHECK (
            num_nonnulls(counsel_reviewed_at, counsel_reviewer_name,
                         counsel_reviewer_firm, counsel_recorded_by,
                         counsel_recorded_at, counsel_claims_confirmed) IN (0, 6)
            AND (counsel_recorded_by IS NULL
                 OR counsel_recorded_by <> authored_by)
            AND (counsel_reviewer_name IS NULL
                 OR length(trim(counsel_reviewer_name)) > 0)
            AND (counsel_reviewer_firm IS NULL
                 OR length(trim(counsel_reviewer_firm)) > 0)
            AND (counsel_claims_confirmed IS NULL
                 OR (jsonb_typeof(counsel_claims_confirmed) = 'array'
                     AND jsonb_array_length(counsel_claims_confirmed) > 0))
          )
    """)
    op.execute("""
        COMMENT ON CONSTRAINT counsel_review_names_its_source
             ON compliance_library_entry IS
        'Entry 164. All six fields or none of them, the recorder is never the author, '
        'and the confirmed claims are a non-empty array. A review recorded as a bare '
        'date is the state this constraint exists to make unrepresentable.'
    """)

    op.execute("""
        COMMENT ON COLUMN compliance_library_entry.counsel_reviewed_at IS
        'The date THE LAWYER reviewed it - not the date somebody wrote that down, which '
        'is counsel_recorded_at. Added by 0039 and written by nothing until entry 164.'
    """)
    op.execute("""
        COMMENT ON COLUMN compliance_library_entry.counsel_claims_confirmed IS
        'Which specific claims counsel confirmed, as a non-empty JSON array of strings. '
        'Per-claim for the reason claim_provenance is: an entry is a mixture, and one '
        'yes rounds the mixture to whichever part the recorder felt best about.'
    """)

    op.execute(_trigger_function(AUTHOR_CLAUSES + APPROVER_AND_RECORDER_CLAUSES))


def downgrade() -> None:
    op.execute(_trigger_function(AUTHOR_CLAUSES))
    for constraint in (
        "counsel_review_names_its_source",
        "approval_is_a_separate_act",
        "compliance_entry_counsel_recorder_is_an_account",
        "compliance_entry_approver_is_an_account",
    ):
        op.execute(
            f"ALTER TABLE compliance_library_entry DROP CONSTRAINT IF EXISTS {constraint}"
        )
    # An entry approved under 0057 would keep its status and lose the record of who
    # approved it, which is the entry 163 defect exactly. So the status goes back with
    # the columns rather than surviving them.
    op.execute(
        "UPDATE compliance_library_entry SET status = 'draft' WHERE status = 'approved'"
    )
    for name, _kind in NEW_COLUMNS:
        op.execute(f"ALTER TABLE compliance_library_entry DROP COLUMN IF EXISTS {name}")
