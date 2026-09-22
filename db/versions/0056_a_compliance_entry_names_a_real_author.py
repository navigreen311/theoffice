"""A compliance entry names a real author

Revision ID: 0056
Revises: 0055

Ruled 22 September 2026 (Ivan Green), decisions entry 162:

    *"A compliance entry names a real author. `authored_by` must resolve to an
    `origin='human'` account. Report the 21 existing rows; don't rewrite them."*

WHAT THE COLUMN HAS BEEN SINCE 0012
===================================

    `authored_by UUID NOT NULL` - and nothing else. No foreign key, no lookup, no reader
    that ever resolved it. NOT NULL guaranteed that *something* was written there, which
    is the weakest of the three things the column looks like it promises.

    Measured 22 September 2026, every row in the table:

        entries  venture            authored_by                           resolves to
        -------  -----------------  ------------------------------------  --------------
             19  burkham-wickmont   87c873da-15ca-402b-9cad-c788f4539100  smoke-operator-
                                                                          0eda802c
                                                                          (test_fixture)
              2  greenstone         00000000-0000-5000-8000-00000000aaaa  no such account

    Twenty-one of twenty-one, and **zero name a person.** The nineteen were written by
    the smoke script's operator account; the two carry the placeholder UUID that
    `scripts/dev-up.sh` passes, which has never corresponded to a row in `office_human`.

THE TWENTY-ONE STAY. THAT IS PART OF THE RULING
===============================================

    *"Report the 21 existing rows; don't rewrite them."* So there is no backfill here,
    and there is no `UPDATE`. Nobody knows who wrote those entries; assigning them to
    Ivan Green because he is the only person on the system would manufacture exactly the
    authorship this entry exists to require.

    That shapes both controls below. **Each constrains writes and validates nothing.**

        the foreign key    added `NOT VALID`, so it holds for every row written from now
                           on and never asks the existing twenty-one to justify
                           themselves. Left permanently un-validated on purpose: running
                           `VALIDATE CONSTRAINT` would fail on Greenstone's two, and a
                           constraint that a future operator is tempted to "fix" by
                           deleting rows is worse than one that honestly says what it
                           does and does not cover.

        the trigger        fires on INSERT and UPDATE only. Rows at rest are never
                           examined, because a trigger cannot examine them.

WHY A TRIGGER AND NOT A CHECK
=============================

    `origin` lives on `office_human`, and a CHECK constraint may not read another table.
    The alternative - denormalising the author's origin into this table - would store a
    fact that goes stale the moment an account is reclassified, which is the thing 0053
    was written to end.

WHAT THE TRIGGER MEANS FOR THE LOADER
=====================================

    `scripts/load_compliance_library.py` re-running over Burkham's nineteen is an UPDATE,
    so it will now be **refused** until the file names a real author. That is a refusal,
    not a rewrite: the rows keep their text and keep their existing `authored_by`, and
    what stops is the pretence that a fixture re-authored them today.

CHECKED TWICE ON PURPOSE
========================

    `broker/knowledge.py::author_compliance_entry` asks the same question in Python and
    raises a message naming the account. The database is the control and cannot be
    argued with; the Python check is the one an operator can read.
"""
from __future__ import annotations

from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOT VALID: binds every future write, asks nothing of the existing twenty-one.
    op.execute("""
        ALTER TABLE compliance_library_entry
          ADD CONSTRAINT compliance_entry_author_is_an_account
          FOREIGN KEY (authored_by) REFERENCES office_human(human_id)
          NOT VALID
    """)
    op.execute("""
        COMMENT ON CONSTRAINT compliance_entry_author_is_an_account
             ON compliance_library_entry IS
        'Entry 162. NOT VALID deliberately and permanently: Greenstone''s two entries '
        'carry a placeholder that resolves to no account, and the ruling says report '
        'them rather than rewrite them. Do not run VALIDATE CONSTRAINT - it will fail, '
        'and the rows it fails on are the evidence.'
    """)

    op.execute("""
        CREATE FUNCTION compliance_entry_author_is_a_person() RETURNS trigger AS $$
        DECLARE
          author_origin TEXT;
          author_name   TEXT;
        BEGIN
          SELECT origin, display_name INTO author_origin, author_name
            FROM office_human WHERE human_id = NEW.authored_by;

          -- The foreign key has this case, but it is NOT VALID and so does not cover an
          -- UPDATE of a pre-existing row that leaves authored_by alone. Stated here too.
          -- USING MESSAGE rather than RAISE's own format string: the `%` placeholder
          -- is a percent sign in a file that several layers rewrite percent signs in,
          -- and concatenation says the same thing without depending on any of them.
          IF author_origin IS NULL THEN
            RAISE EXCEPTION USING MESSAGE =
              'compliance entry ' || NEW.entry_ref || ' names an author ('
              || NEW.authored_by || ') that is not an account on this Office. '
              || 'Entry 162: a compliance entry names a real author.';
          END IF;

          IF author_origin <> 'human' THEN
            RAISE EXCEPTION USING MESSAGE =
              'compliance entry ' || NEW.entry_ref || ' names ' || author_name
              || ' as its author, which is a ' || author_origin || ' account. '
              || 'Entry 162: a compliance entry is a claim about the law that '
              || 'somebody has to stand behind, and a fixture cannot be asked '
              || 'about it.';
          END IF;

          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER a_compliance_entry_names_a_real_author
          BEFORE INSERT OR UPDATE ON compliance_library_entry
          FOR EACH ROW EXECUTE FUNCTION compliance_entry_author_is_a_person()
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS a_compliance_entry_names_a_real_author "
        "ON compliance_library_entry"
    )
    op.execute("DROP FUNCTION IF EXISTS compliance_entry_author_is_a_person()")
    op.execute(
        "ALTER TABLE compliance_library_entry "
        "DROP CONSTRAINT IF EXISTS compliance_entry_author_is_an_account"
    )
