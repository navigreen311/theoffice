"""A gate review is corrected by a later entry

Revision ID: 0060
Revises: 0059

Ruled 22 September 2026 (Ivan Green), decisions entry 170:

    *"A gate review may be corrected by a later entry, never by editing. A correction
    names the reviewer, the correction and who made it. Gate 10's signature binds to the
    note plus its corrections."*

WHAT THERE WAS NO WAY TO DO
===========================

    Ira Green recorded the Gate 4 review on run 4637b946 at 17:16 on 22 September, on
    her own account, from a note drafted for Ivan Green. The note reads *"Greenstone is
    in simulation, declared by me today"* - and the declaration names Ivan.

    The record is not wrong. Every fact in it is true: Ira's account, Ira's human_id,
    her text. What it lacks is the one sentence that stops a reader taking "me" for the
    account that recorded it. **There was no way to add that sentence.** `audit_log` is
    append-only by trigger, `provisioning_gate_result` carries the note inside evidence,
    and nothing in the repository wrote a correction to either.

    The alternative to this table was editing the note, and that is the thing entry 159
    settled on a smaller record: *"a false entry is answered by a later one, never by
    editing the record."*

WHY IT NAMES THREE PARTIES AND NOT ONE
======================================

    reviewer_named    who the note was drafted FOR. On 4637b946 that is Ivan Green,
                      and it is the whole content of the correction.
    corrected_by      who wrote the correction down. Not necessarily either of the
                      other two.
    the review        `run_id` and `gate` - the review being corrected.

    A correction that named only its author would leave the reader to infer whose
    reading it fixes, which is the ambiguity it exists to remove.

APPEND-ONLY, AND CORRECTIONS OF CORRECTIONS ARE JUST MORE ROWS
==============================================================

    UPDATE and DELETE are refused by trigger, the same shape `department_attestation`
    uses. A correction that was itself wrong is answered by another correction, and the
    chain reads in `corrected_at` order.

    There is deliberately no `supersedes` column. Every correction on a review is in
    force; none replaces another. A reader of the Gate 4 note reads the note and then
    every correction, in order, and that is what Gate 10's signature covers.

WHY THE REVIEW IS NAMED BY (run_id, gate) AND NOT BY A ROW ID
=============================================================

    `provisioning_gate_result` has a `gate_result_id`, and a review writes TWO rows on
    that table - the `awaiting_human` one and the `passed` one - so a foreign key to
    either would be a foreign key to half the record. The review is the act, and the act
    is identified by the run and the gate it was recorded at.
"""
from __future__ import annotations

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE gate_review_correction (
          correction_id   UUID PRIMARY KEY,
          run_id          UUID NOT NULL REFERENCES provisioning_run(run_id),
          gate            TEXT NOT NULL,
          reviewer_named  UUID NOT NULL REFERENCES office_human(human_id),
          correction      TEXT NOT NULL CHECK (length(trim(correction)) > 0),
          corrected_by    UUID NOT NULL REFERENCES office_human(human_id),
          corrected_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        COMMENT ON TABLE gate_review_correction IS
        'Entry 170. A gate review is corrected by a later entry, never by editing. '
        'Names who the note was drafted for, the correction, and who wrote it down. '
        'Append-only: a correction that is itself wrong gets another correction.'
    """)
    op.execute("""
        CREATE INDEX ix_gate_review_correction_review
            ON gate_review_correction (run_id, gate, corrected_at)
    """)
    op.execute(
        "GRANT SELECT, INSERT ON gate_review_correction TO office_app"
    )

    # BOTH PARTIES ARE PEOPLE. The same pair entries 162, 163 and 166 use: a foreign key
    # says the id is an account, and only a lookup says it is somebody who can be asked.
    op.execute("""
        CREATE FUNCTION a_correction_names_people() RETURNS trigger AS $$
        DECLARE
          who     TEXT;
          origin  TEXT;
        BEGIN
          SELECT h.origin, h.display_name INTO origin, who
            FROM office_human h WHERE h.human_id = NEW.corrected_by;
          IF origin <> 'human' THEN
            RAISE EXCEPTION USING MESSAGE =
              'a gate review correction was written by ' || who || ', which is a '
              || origin || ' account. Entry 170: a correction names who made it, and '
              || 'a fixture is not somebody who can be asked about one.';
          END IF;

          SELECT h.origin, h.display_name INTO origin, who
            FROM office_human h WHERE h.human_id = NEW.reviewer_named;
          IF origin <> 'human' THEN
            RAISE EXCEPTION USING MESSAGE =
              'a gate review correction names ' || who || ' as its reviewer, which is '
              || 'a ' || origin || ' account. Entry 170: the correction says who the '
              || 'note was drafted for.';
          END IF;

          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER a_correction_names_people
          BEFORE INSERT OR UPDATE ON gate_review_correction
          FOR EACH ROW EXECUTE FUNCTION a_correction_names_people()
    """)

    op.execute("""
        CREATE FUNCTION gate_review_correction_is_append_only() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION USING MESSAGE =
            'gate_review_correction refuses UPDATE and DELETE. Entry 170: a review is '
            'corrected by a LATER entry, never by editing - and a correction is a '
            'record of the same kind. Write another correction.';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER gate_review_correction_is_append_only
          BEFORE UPDATE OR DELETE OR TRUNCATE ON gate_review_correction
          FOR EACH STATEMENT EXECUTE FUNCTION gate_review_correction_is_append_only()
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS gate_review_correction_is_append_only "
        "ON gate_review_correction"
    )
    op.execute("DROP FUNCTION IF EXISTS gate_review_correction_is_append_only()")
    op.execute(
        "DROP TRIGGER IF EXISTS a_correction_names_people ON gate_review_correction"
    )
    op.execute("DROP FUNCTION IF EXISTS a_correction_names_people()")
    op.execute("DROP TABLE IF EXISTS gate_review_correction")
