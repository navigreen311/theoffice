"""A department may be certified for simulation

Revision ID: 0059
Revises: 0058

Ruled 22 September 2026 (Ivan Green), decisions entry 167:

    *"A department may be certified for simulation. A distinct Unit B basis, never
    'verified', recorded with the declaration that permitted it. Gate 9 accepts it while
    the venture is in simulation and refuses it the moment the venture leaves, and every
    simulation certification is void at that point. Any surface showing a grant, a gate
    or a sign-off says which of its certifications are simulation-only. Measured: under
    entry 166 coupling can never be TRUE, so Unit B has no route and Gate 9 cannot
    clear."*

THE DEAD END ENTRY 166 CREATED, MEASURED
========================================

    Unit B reaches a certification two ways. Both are shut:

        tested     SimForge's `department_context` unit is read by nothing in
                   `routers/operation.py::submit_curriculum`. Greenstone's three
                   department units have sat at IN_PROGRESS since anybody started
                   watching, and a run that never answers resolves to TIMEOUT.
        attested   Gate 8 posts `passed = escalation_path AND compliance_coupling`.
                   Entry 166 refuses `compliance_coupling_verified = TRUE` while a
                   venture is in simulation, so `passed` is false by construction.

    Measured 22 September 2026, every Unit B certification in the system: three
    `bootstrap` rows serving 45 burkham-wickmont grants, three `tested` rows stuck at
    IN_PROGRESS, and **zero** with an `attestation_ref`. The attested path has never
    produced a certification at all.

    So a venture in simulation could not pass Gate 9, and simulation - which exists so
    that mock runs can happen before real clients - stopped the mock runs.

A FOURTH BASIS, NOT A FOURTH WAY TO SAY 'CERTIFIED'
===================================================

    `basis` has said `tested | attested | bootstrap` since 0050, whose ruling was *"a
    reader can always tell them apart."* This adds `simulation`, and every constraint
    below exists so that it cannot be mistaken for one of the other three.

        simulation_ref              the declaration that permitted it. NOT NULL exactly
                                    when the basis is `simulation`, both directions -
                                    the same shape `an_attested_certification_names_
                                    its_attestation` has.
        no verdict, no model        a simulation certification records
                                    `simforge_verdict IS NULL`, `agent_model IS NULL`
                                    and `model_digest IS NULL`, because nothing ran and
                                    no model answered. Recording any of them would be
                                    the false statement entry 118 found on two Phase 0.8
                                    grants that claimed a SimForge PASS against no run.
        unit B only                 mirrors `only_unit_b_is_attested`, and for the same
                                    reason: Unit A is a per-agent, per-module exam and
                                    there is no version of that a declaration can stand
                                    in for.

VOID IS DERIVED, NEVER STORED
=============================

    *"...and every simulation certification is void at that point."*

    A certification is void exactly when its own `simulation_ref` names a declaration
    that has been left. That is a join, not a column, and there is deliberately no
    `voided_at` here: a stored flag would mean a row reading valid until somebody
    remembered to run a job, which is entry 158's argument about overdue escalations
    applied to a stronger claim.

    It follows that a certification is bound to ONE declaration. A venture that leaves
    simulation and declares again does not revive the old certifications - the new
    declaration is a new row (entry 166) and needs new certifications. That is the
    ruling's *"void at that point"* read as permanent, which is the only reading under
    which leaving means anything.

NOTHING IS BACKFILLED AND NOTHING IS CONVERTED
==============================================

    No existing certification becomes a simulation one. The three bootstrap Unit B rows
    stay bootstrap: they were written before any of this and converting them would put a
    declaration's name on certifications it did not permit.
"""
from __future__ import annotations

from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE certification ADD COLUMN simulation_ref UUID")
    op.execute("""
        ALTER TABLE certification
          ADD CONSTRAINT fk_certification_simulation
          FOREIGN KEY (simulation_ref) REFERENCES venture_simulation(simulation_id)
    """)
    op.execute("""
        COMMENT ON COLUMN certification.simulation_ref IS
        'The declaration of simulation that permitted this certification. Entry 167. '
        'The certification is VOID once that declaration is left - derived by join, '
        'never stored, so it cannot read valid while somebody forgets to run a job.'
    """)

    # A FOURTH BASIS. 0050 named the constraint for the count, so the count changes.
    op.execute(
        "ALTER TABLE certification DROP CONSTRAINT basis_is_one_of_three"
    )
    op.execute("""
        ALTER TABLE certification
          ADD CONSTRAINT basis_is_one_of_four CHECK (
            basis IN ('tested', 'attested', 'bootstrap', 'simulation')
          )
    """)

    op.execute("""
        ALTER TABLE certification
          ADD CONSTRAINT a_simulation_certification_names_its_declaration CHECK (
            (basis = 'simulation') = (simulation_ref IS NOT NULL)
          )
    """)
    op.execute("""
        COMMENT ON CONSTRAINT a_simulation_certification_names_its_declaration
             ON certification IS
        'Entry 167. Both directions: a simulation certification names the declaration '
        'that permitted it, and nothing else may name one. Without the second half a '
        'tested certification could carry a declaration and read as covered by it.'
    """)

    # ONLY UNIT B, mirroring `only_unit_b_is_attested` and for its reason.
    op.execute("""
        ALTER TABLE certification
          ADD CONSTRAINT only_unit_b_is_certified_for_simulation CHECK (
            basis <> 'simulation' OR unit = 'B'
          )
    """)

    # NOTHING RAN, SO NOTHING IS RECORDED AS HAVING RUN.
    op.execute("""
        ALTER TABLE certification
          ADD CONSTRAINT a_simulation_certification_claims_no_exam CHECK (
            basis <> 'simulation'
            OR (simforge_verdict IS NULL
                AND agent_model IS NULL
                AND model_digest IS NULL
                AND score IS NULL)
          )
    """)
    op.execute("""
        COMMENT ON CONSTRAINT a_simulation_certification_claims_no_exam
             ON certification IS
        'Entry 167. No verdict, no model, no score: nothing sat an exam. Two Phase 0.8 '
        'grants once carried simforge_verdict = PASS against no scenario run at all, '
        'and that is the state this makes unrepresentable for the new basis.'
    """)

    op.execute("""
        CREATE INDEX ix_certification_simulation ON certification (simulation_ref)
          WHERE simulation_ref IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_certification_simulation")
    # The rows go, not just the column. A simulation certification whose basis was
    # rewritten to 'bootstrap' would be a certification claiming a different origin from
    # the one it has, which is exactly what entry 147's basis column exists to prevent.
    op.execute("DELETE FROM certification WHERE basis = 'simulation'")
    for constraint in (
        "a_simulation_certification_claims_no_exam",
        "only_unit_b_is_certified_for_simulation",
        "a_simulation_certification_names_its_declaration",
        "basis_is_one_of_four",
        "fk_certification_simulation",
    ):
        op.execute(
            f"ALTER TABLE certification DROP CONSTRAINT IF EXISTS {constraint}"
        )
    op.execute("""
        ALTER TABLE certification
          ADD CONSTRAINT basis_is_one_of_three CHECK (
            basis IN ('tested', 'attested', 'bootstrap')
          )
    """)
    op.execute("ALTER TABLE certification DROP COLUMN IF EXISTS simulation_ref")
