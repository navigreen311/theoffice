"""A venture may be declared in simulation

Revision ID: 0058
Revises: 0057

Ruled 22 September 2026 (Ivan Green), decisions entry 166:

    *"A venture may be declared in simulation by a named human, with a reason and a
    date. In simulation, an unreviewed compliance entry is recorded as deliberately
    deferred, not as verified, and does not fail a gate. Leaving simulation is a
    separate named act; every unreviewed entry fails again the moment it does. No
    attestation may ever read TRUE on the strength of simulation. Greenstone and Burkham
    Wickmont are both in simulation as of today, declared by Ivan Green, reason: mock
    runs and simulations before real clients."*

WHAT THIS IS FOR
================

    Entry 165 made a draft compliance entry fail Gate 2 and cover no flag at Gate 6.
    Measured the same day: all 21 entries are drafts, none is counsel-reviewed, and
    **there is no counsel until there are real clients** - so the drafts stay drafts for
    a long time and the rule as written moves every venture further from Gate 12.

    165 is not softened. What this adds is a declared, named, dated state in which the
    same fact is recorded as a **deliberate deferral** rather than as a passing entry.
    The entry is still not relied on and still not verified; what changes is that the
    gate does not fail on it, and the record says who decided that and why.

ONE ROW PER DECLARATION, AND LEAVING IS AN UPDATE TO IT
=======================================================

    A venture in simulation twice has two rows, so the history of declarations is
    readable. `one_live_simulation_per_venture` is a partial unique index over
    `left_at IS NULL`, so it can be in simulation once at a time.

    Leaving fills three columns on the live row rather than writing a fourth kind of
    row. Entering and leaving are the two ends of one interval, and a table where they
    were separate rows would need a rule about which row a reader pairs with which.

APPEND-ONLY EXCEPT FOR LEAVING, AND THE TRIGGER SAYS SO
=======================================================

    `department_attestation` refuses UPDATE outright (entry 147) because a correction
    there is a new row. This cannot: leaving is an update by construction. So the
    trigger allows exactly one transition - the three leaving columns going from NULL to
    not-NULL - and refuses every other change, including un-leaving.

    That is the schema half of *"every unreviewed entry fails again the moment it
    does"*. A venture cannot quietly re-enter the simulation it just left; it declares
    again, and the new declaration is a new row with its own name, reason and date.

WHO MAY DECLARE
===============

    A person. Both `declared_by` and `left_by` carry a validated foreign key to
    `office_human` and a trigger checking `origin = 'human'` - the same pair entries 162
    and 163 use, for the same reason: a declaration that suspends a compliance rule is a
    decision somebody has to answer for, and a fixture cannot be asked about one.

NO BACKFILL
===========

    No venture is in simulation when this migration runs. The two declarations the
    ruling names are written by `scripts/declare_simulation.py`, which resolves the
    declaring human by name against the live database - a thing a migration cannot do
    honestly, because the account exists on one deployment and not in CI.
"""
from __future__ import annotations

from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE venture_simulation (
          simulation_id  UUID PRIMARY KEY,
          venture_id     TEXT NOT NULL,
          declared_by    UUID NOT NULL REFERENCES office_human(human_id),
          declared_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          reason         TEXT NOT NULL CHECK (length(trim(reason)) > 0),
          left_by        UUID REFERENCES office_human(human_id),
          left_at        TIMESTAMPTZ,
          left_reason    TEXT,
          CONSTRAINT leaving_is_a_named_act CHECK (
            num_nonnulls(left_by, left_at, left_reason) IN (0, 3)
            AND (left_reason IS NULL OR length(trim(left_reason)) > 0)
          )
        )
    """)
    op.execute("""
        COMMENT ON TABLE venture_simulation IS
        'Entry 166. A venture declared in simulation by a named human, with a reason '
        'and a date. In simulation an unreviewed compliance entry is recorded as '
        'deliberately deferred rather than failing a gate - it is NOT recorded as '
        'verified, and no attestation may read TRUE on the strength of it.'
    """)
    op.execute("""
        COMMENT ON CONSTRAINT leaving_is_a_named_act ON venture_simulation IS
        'All three leaving columns or none. Leaving is a separate named act, so a row '
        'that carried a date and no name would be a venture that left simulation with '
        'nobody deciding to.'
    """)
    op.execute("""
        CREATE UNIQUE INDEX one_live_simulation_per_venture
            ON venture_simulation (venture_id) WHERE left_at IS NULL
    """)
    op.execute(
        "CREATE INDEX ix_venture_simulation_venture ON venture_simulation (venture_id)"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON venture_simulation TO office_app")

    # DECLARING AND LEAVING ARE ACTS BY PEOPLE. A foreign key says the id is an account;
    # only a lookup can say it is a person, and a CHECK may not read another table.
    op.execute("""
        CREATE FUNCTION simulation_is_declared_by_a_person() RETURNS trigger AS $$
        DECLARE
          who         TEXT;
          who_origin  TEXT;
        BEGIN
          SELECT h.origin, h.display_name INTO who_origin, who
            FROM office_human h WHERE h.human_id = NEW.declared_by;
          IF who_origin <> 'human' THEN
            RAISE EXCEPTION USING MESSAGE =
              'simulation for ' || NEW.venture_id || ' is declared by ' || who
              || ', which is a ' || who_origin || ' account. Entry 166: a venture is '
              || 'declared in simulation BY A NAMED HUMAN, and a declaration that '
              || 'suspends a compliance rule is a decision somebody answers for.';
          END IF;

          IF NEW.left_by IS NOT NULL THEN
            SELECT h.origin, h.display_name INTO who_origin, who
              FROM office_human h WHERE h.human_id = NEW.left_by;
            IF who_origin <> 'human' THEN
              RAISE EXCEPTION USING MESSAGE =
                'simulation for ' || NEW.venture_id || ' was left by ' || who
                || ', which is a ' || who_origin || ' account. Entry 166: leaving '
                || 'simulation is a separate NAMED act.';
            END IF;
          END IF;

          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER a_simulation_is_declared_by_a_person
          BEFORE INSERT OR UPDATE ON venture_simulation
          FOR EACH ROW EXECUTE FUNCTION simulation_is_declared_by_a_person()
    """)

    # THE ONLY UPDATE THIS TABLE ALLOWS IS LEAVING, ONCE.
    op.execute("""
        CREATE FUNCTION a_simulation_is_left_once() RETURNS trigger AS $$
        BEGIN
          IF OLD.left_at IS NOT NULL THEN
            RAISE EXCEPTION USING MESSAGE =
              'simulation ' || OLD.simulation_id || ' was already left on '
              || OLD.left_at || '. Entry 166: leaving is a separate named act and it '
              || 'does not un-happen. Declare simulation again if that is what is '
              || 'meant; the new declaration is a new row with its own reason.';
          END IF;
          IF NEW.simulation_id <> OLD.simulation_id
             OR NEW.venture_id <> OLD.venture_id
             OR NEW.declared_by <> OLD.declared_by
             OR NEW.declared_at <> OLD.declared_at
             OR NEW.reason <> OLD.reason THEN
            RAISE EXCEPTION USING MESSAGE =
              'a declaration of simulation is not editable. Entry 166: it names who '
              || 'declared it, when, and why, and those are the facts the deferral '
              || 'rests on. Leaving is the only update this row accepts.';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER a_simulation_is_left_once
          BEFORE UPDATE ON venture_simulation
          FOR EACH ROW EXECUTE FUNCTION a_simulation_is_left_once()
    """)
    # A DECLARATION IS NOT DELETED. `department_attestation`'s argument (entry 147),
    # and a RAISE rather than a rule that swallows the statement: a delete that quietly
    # does nothing is a delete somebody believes happened.
    op.execute("""
        CREATE FUNCTION venture_simulation_is_not_deleted() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION USING MESSAGE =
            'venture_simulation refuses DELETE. Entry 166: a declaration of simulation '
            'names who decided, when and why, and the gates that deferred on it read '
            'this row. Leave the simulation instead - that is the named act.';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER venture_simulation_is_not_deleted
          BEFORE DELETE ON venture_simulation
          FOR EACH STATEMENT EXECUTE FUNCTION venture_simulation_is_not_deleted()
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS venture_simulation_is_not_deleted ON venture_simulation"
    )
    op.execute("DROP FUNCTION IF EXISTS venture_simulation_is_not_deleted()")
    op.execute(
        "DROP TRIGGER IF EXISTS a_simulation_is_left_once ON venture_simulation"
    )
    op.execute("DROP FUNCTION IF EXISTS a_simulation_is_left_once()")
    op.execute(
        "DROP TRIGGER IF EXISTS a_simulation_is_declared_by_a_person "
        "ON venture_simulation"
    )
    op.execute("DROP FUNCTION IF EXISTS simulation_is_declared_by_a_person()")
    op.execute("DROP TABLE IF EXISTS venture_simulation")
