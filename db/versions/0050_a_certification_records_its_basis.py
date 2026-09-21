"""A certification records its basis

Revision ID: 0050
Revises: 0049

Ruled 21 September 2026 (Ivan Green), three rulings on Unit B attestation:

  * *"A certification records its basis: attested or tested, the attester by name, and
    the reasons. A reader can always tell them apart."*
  * *"Who attests: a human holding founder authority, recorded by name."*
  * *"What ends it: when a real hand-over test ships, attested Unit B certifications stop
    counting at Gate 9 and must be re-earned."*

WHY THE BASIS COULD NOT BE READ OFF THE ROW BEFORE
==================================================

    `attested_by` has always been a PARAMETER of `record_result` and never a column. The
    structural expression of "SimForge said so" was `simforge_verdict IS NOT NULL`, which
    separated a bootstrap row from a real verdict and nothing else.

    That was enough while there were two kinds. An attested unit B is a third: The Office
    posts `department_outcomes` to SimForge's gate-result callback, SimForge writes an
    `OperationCertification`, and The Office reads back a PASS **that is byte-identical to
    one a battery earned**. Entry 146 sized this and named it the question that mattered:
    a stop-gap nobody can identify later is the permanent state with a note on it.

THREE VALUES, AND THE BACKFILL IS A MEASUREMENT
===============================================

    tested      a verdict SimForge produced by running something
    attested    a named human with founder authority said the two things were verified
    bootstrap   Phase 0.8, no battery, `simforge_verdict IS NULL` by design

    Backfilled from the column that already answered it: `simforge_verdict IS NULL` is
    `bootstrap`, anything else is `tested`. **No existing row is attested** - the
    mechanism does not exist yet - so nothing is inferred and nothing is guessed.

WHAT "RECORDS THE ATTESTER AND THE REASONS" MEANS HERE
======================================================

    `attestation_ref`, and that is an interpretation worth stating so it can be
    overruled. The reasons and the human live on `department_attestation`, which is
    APPEND-ONLY: no row is ever updated or deleted, so a pointer to it cannot go stale
    and cannot disagree with a second copy. That is the same relationship
    `agent_forge_grant.operation_cert_ref` has to the certification it names.

    Copying the two reasons onto `certification` was the literal reading and it buys a
    reader one less join at the cost of two strings that can drift apart from the ones
    somebody actually wrote. If Ivan meant the columns, this is the line to change.

WHO ATTESTS, MEASURED RATHER THAN INVENTED
==========================================

    **No new role.** `office_human_role` has held `('venture_operator',
    'compliance_officer', 'ivan')` since 0010, `ROLE_RANK` puts `ivan` top at 3, and on
    this database exactly three accounts hold it: Ivan Green, Ira Green, and a
    `dev-all build check` fixture. `ivan` IS founder authority; it is named for the
    founder and it is the role the Forge-scope revocation already requires.

    The fixture holding it is a real finding and is not this migration's to fix. It is
    recorded in decisions entry 146.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------ the attestation itself
    op.execute("""
        CREATE TABLE department_attestation (
          attestation_id  UUID PRIMARY KEY,
          venture_id      TEXT NOT NULL,
          department      TEXT NOT NULL,
          -- NO FOREIGN KEY HERE EITHER, and for the reason above rather than by
          -- oversight. An append-only table with a RESTRICT reference is a table that
          -- prevents the thing it points at from ever being removed, and a register of
          -- what somebody attested must not become the reason a Forge cannot be
          -- de-registered. The id is recorded; the row it named is somebody else's
          -- lifecycle.
          forge_id        TEXT NOT NULL,
          -- THE ATTESTER BY NAME, AND THE NAME IS CAPTURED RATHER THAN JOINED.
          --
          -- Ruled: "the attester by name". A display name can change and an account can
          -- be closed, and an attestation has to keep saying who made it either way -
          -- so the name is written down at the moment it is made, beside the id that
          -- resolves the account while the account exists.
          --
          -- NO FOREIGN KEY, deliberately, and `audit_log.actor_id` is the precedent: an
          -- append-only register that cannot be edited must not also become the reason
          -- an account cannot be closed. With a RESTRICT the two rules deadlock - the
          -- attestation cannot be deleted and the human cannot be either.
          attested_by      UUID NOT NULL,
          attested_by_name TEXT NOT NULL,
          attested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

          -- The two things `DepartmentRunOutcome` carries, and the two things ruled.
          -- Each is a verdict AND its reason, in one column pair, because a verdict
          -- without a reason is the shape this project keeps refusing.
          escalation_path_verified     BOOLEAN NOT NULL,
          escalation_path_reason       TEXT NOT NULL,
          compliance_coupling_verified BOOLEAN NOT NULL,
          compliance_coupling_reason   TEXT NOT NULL,

          CONSTRAINT an_attestation_gives_reasons CHECK (
            length(btrim(escalation_path_reason)) > 0
            AND length(btrim(compliance_coupling_reason)) > 0
            AND length(btrim(attested_by_name)) > 0
          )
        )
    """)
    op.execute("""
        COMMENT ON TABLE department_attestation IS
        'A named human with founder authority attesting, per department and Forge, that '
        'the escalation path and the compliance coupling are verified - with reasons. '
        'APPEND-ONLY: a correction is a new row, and the latest row for a pair is the '
        'one in force. A STOP-GAP until a real hand-over test ships (entry 146).'
    """)
    # Read by `current_attestation`, which takes the latest row per pair.
    op.create_index(
        "ix_department_attestation_current",
        "department_attestation",
        ["venture_id", "department", "forge_id", "attested_at"],
    )

    # APPEND-ONLY BY TRIGGER, not by convention. `audit_log` is the precedent and the
    # argument is its: a table whose immutability depends on nobody writing the wrong
    # statement is not immutable, and the one statement that matters is the one somebody
    # writes at 2am to "fix" a reason.
    op.execute("""
        CREATE FUNCTION department_attestation_is_append_only() RETURNS TRIGGER AS $$
        BEGIN
          RAISE EXCEPTION
            'department_attestation is append-only: % is refused. A correction is a new '
            'attestation by a named human, not an edit to the one on file.', TG_OP
            USING HINT = 'INSERT a new row; the latest row for a pair is the one in force.';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER department_attestation_no_update
          BEFORE UPDATE OR DELETE OR TRUNCATE ON department_attestation
          FOR EACH STATEMENT EXECUTE FUNCTION department_attestation_is_append_only()
    """)

    # ----------------------------------------------------- the basis, on the certification
    op.add_column(
        "certification",
        sa.Column("basis", sa.Text(), nullable=False, server_default="tested"),
    )
    op.add_column(
        "certification",
        sa.Column(
            "attestation_ref",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_certification_attestation",
        "certification", "department_attestation",
        ["attestation_ref"], ["attestation_id"],
    )

    # THE BACKFILL IS THE COLUMN THAT ALREADY ANSWERED IT. See the docstring.
    op.execute(
        "UPDATE certification SET basis = 'bootstrap' WHERE simforge_verdict IS NULL"
    )
    # Dropped once the existing rows are correct: a default would let the next writer
    # omit the basis and have one chosen for it, which is the whole failure this closes.
    op.execute("ALTER TABLE certification ALTER COLUMN basis DROP DEFAULT")

    op.create_check_constraint(
        "basis_is_one_of_three", "certification",
        "basis IN ('tested', 'attested', 'bootstrap')",
    )
    # A reader can always tell them apart, and the two directions are both enforced: an
    # attested row names its attestation, and nothing else may.
    op.create_check_constraint(
        "an_attested_certification_names_its_attestation", "certification",
        "(basis = 'attested') = (attestation_ref IS NOT NULL)",
    )
    # Unit A is EXAMINED, never attested. An attestation covers a department's escalation
    # path and compliance coupling; there is no per-agent, per-module version of that, and
    # allowing one would let an agent be certified to operate a module by assertion.
    op.create_check_constraint(
        "only_unit_b_is_attested", "certification",
        "basis <> 'attested' OR unit = 'B'",
    )
    # AN ATTESTED CERTIFICATION NAMES NO MODEL, because none answered.
    #
    # 0044's `certification_names_its_model` demands a digest and the generation settings
    # whenever a SimForge verdict sits on a certified row, and it is right: a tested
    # certification that cannot name the model it was earned on cannot expire when the
    # model moves. An attested one was not earned on a model at all - no battery ran -
    # and the exemption is the same one `simforge_verdict IS NULL` already gives a
    # bootstrap, stated against the column that now says which is which.
    #
    # `simforge_verdict` STAYS 'PASS' on an attested row, and that is not a fiction:
    # SimForge really did return it, from the outcome The Office posted. What tells a
    # reader it was not a battery is `basis`, which is the whole of the first ruling.
    op.execute(
        "ALTER TABLE certification DROP CONSTRAINT IF EXISTS certification_names_its_model"
    )
    op.execute("""
        ALTER TABLE certification ADD CONSTRAINT certification_names_its_model
        CHECK (
          simforge_verdict IS NULL
          OR basis = 'attested'
          OR state <> ALL (ARRAY['certified', 'provisional'])
          OR (agent_model IS NOT NULL AND model_digest IS NOT NULL
              AND model_temperature IS NOT NULL AND model_max_tokens IS NOT NULL)
        )
    """)
    op.execute("""
        COMMENT ON CONSTRAINT certification_names_its_model ON certification IS
        'A tested certification names the model it was earned on, or it cannot expire '
        'when the model moves (0044). An attested one is exempt because none answered '
        'it - the same exemption a bootstrap has, stated against basis (entry 146).'
    """)

    op.execute("""
        COMMENT ON COLUMN certification.basis IS
        'tested: SimForge ran something. attested: a named human with founder authority '
        'said so, and attestation_ref names who and why. bootstrap: Phase 0.8, no '
        'battery. A reader can always tell them apart (entry 146).'
    """)

    # SELECT AND INSERT, AND NOTHING ELSE. The trigger above refuses UPDATE and DELETE
    # whoever writes them, and this refuses the app role the privilege as well - two
    # controls over one invariant, the way `obligation_discharge` is granted INSERT and
    # `UPDATE (superseded_at)` and no more. A privilege the app does not hold is one a
    # bug cannot use.
    op.execute("GRANT SELECT, INSERT ON department_attestation TO office_app")

    # ------------------------------------------- which attestation a submission was posted with
    op.add_column(
        "curriculum_submission",
        sa.Column(
            "attestation_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_curriculum_submission_attestation",
        "curriculum_submission", "department_attestation",
        ["attestation_id"], ["attestation_id"],
    )
    op.execute("""
        COMMENT ON COLUMN curriculum_submission.attestation_id IS
        'The attestation Gate 8 posted as this department unit''s outcome, or NULL. It '
        'is what lets the verdict sweep record the certification it produces as '
        'attested rather than tested - the verdict SimForge returns is identical '
        'either way (entry 146).'
    """)


def downgrade() -> None:
    op.drop_constraint(
        "fk_curriculum_submission_attestation", "curriculum_submission",
        type_="foreignkey",
    )
    op.drop_column("curriculum_submission", "attestation_id")
    op.drop_constraint("only_unit_b_is_attested", "certification", type_="check")
    op.drop_constraint(
        "an_attested_certification_names_its_attestation", "certification", type_="check"
    )
    # The model constraint goes back to 0044's form, which has no `basis` to mention.
    op.execute(
        "ALTER TABLE certification DROP CONSTRAINT IF EXISTS certification_names_its_model"
    )
    op.execute("""
        ALTER TABLE certification ADD CONSTRAINT certification_names_its_model
        CHECK (
          simforge_verdict IS NULL
          OR state <> ALL (ARRAY['certified', 'provisional'])
          OR (agent_model IS NOT NULL AND model_digest IS NOT NULL
              AND model_temperature IS NOT NULL AND model_max_tokens IS NOT NULL)
        )
    """)
    op.drop_constraint("basis_is_one_of_three", "certification", type_="check")
    op.drop_constraint("fk_certification_attestation", "certification", type_="foreignkey")
    op.drop_column("certification", "attestation_ref")
    op.drop_column("certification", "basis")
    op.execute("DROP TRIGGER IF EXISTS department_attestation_no_update ON department_attestation")
    op.execute("DROP TABLE IF EXISTS department_attestation")
    op.execute("DROP FUNCTION IF EXISTS department_attestation_is_append_only()")
