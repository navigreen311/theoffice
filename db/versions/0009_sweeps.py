"""Sweep runs and manifest dispositions — continuous verification.

Blueprint Phase 4, Gates 13/14/15. Master prompt Part 13 and Part 15.

The Office has controls whose correctness depends on someone running them, and until now
nothing did. Three of them shipped fully tested and completely inert: the audit hash
chain verifier, the certification staleness recompute, and the manifest reconciliation.

Worse than inert — indistinguishable from healthy. An absence of incidents looks the
same whether the chain verified this morning or has not been checked since March. That
is what `sweep_run` exists to make impossible: every run records when it happened, how
many things it checked, and what it found.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sweep_run (
          sweep_run_id  UUID PRIMARY KEY,
          sweep_kind    TEXT NOT NULL CHECK (sweep_kind IN (
                          'audit_chain','certification_staleness',
                          'manifest_reconciliation','restore_drill')),
          started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          completed_at  TIMESTAMPTZ,
          status        TEXT NOT NULL CHECK (status IN
                          ('running','passed','failed','error')),
          denominator   INT,
          findings      JSONB NOT NULL DEFAULT '{}',
          incident_id   UUID,

          -- A finished run must say how many things it checked. "Chain OK" is not a
          -- result; "chain verified over 41,882 entries" is. Same rule as the coverage
          -- denominators and the flush evidence.
          CONSTRAINT finished_runs_report_a_denominator CHECK (
            status = 'running' OR status = 'error' OR denominator IS NOT NULL
          ),
          CONSTRAINT finished_runs_are_completed CHECK (
            status = 'running' OR completed_at IS NOT NULL
          )
        )
    """)
    op.execute("""
        COMMENT ON TABLE sweep_run IS
        'One row per sweep execution. The absence of incidents proves nothing on its '
        'own - this table is what distinguishes "verified this morning" from "not '
        'checked since March".'
    """)
    op.execute("""
        CREATE INDEX ix_sweep_latest ON sweep_run (sweep_kind, started_at DESC)
    """)

    op.execute("""
        CREATE TABLE manifest_disposition (
          venture_id        TEXT NOT NULL,
          forge_id          TEXT NOT NULL,
          module_id         TEXT NOT NULL,
          first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          call_count        INT NOT NULL DEFAULT 0,
          disposition       TEXT NOT NULL DEFAULT 'pending' CHECK (disposition IN
                              ('pending','declared','revoked','accepted_risk')),
          dispositioned_by  UUID,
          dispositioned_at  TIMESTAMPTZ,
          reason            TEXT,
          PRIMARY KEY (venture_id, forge_id, module_id),

          -- Gate 15 blocks on undispositioned UNDECLARED. Resolving one is an act with
          -- an owner and a stated reason, not a status flip.
          CONSTRAINT resolution_names_a_human_and_a_reason CHECK (
            disposition = 'pending'
            OR (dispositioned_by IS NOT NULL
                AND dispositioned_at IS NOT NULL
                AND reason IS NOT NULL
                AND length(trim(reason)) > 0)
          )
        )
    """)
    op.execute("""
        COMMENT ON COLUMN manifest_disposition.disposition IS
        'accepted_risk exists deliberately. Without it, the only way to clear a finding '
        'someone has decided to live with is to mislabel it as declared - and a '
        'disposition vocabulary that forces a lie produces a register nobody trusts.'
    """)
    op.execute("""
        CREATE INDEX ix_disposition_pending ON manifest_disposition (venture_id)
          WHERE disposition = 'pending'
    """)

    for table in ("sweep_run", "manifest_disposition"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO office_app")
    # Sweeps append; nothing deletes a run. A sweep history with gaps is a sweep
    # history that cannot answer "when was this last verified".
    op.execute("REVOKE DELETE ON sweep_run FROM office_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS manifest_disposition CASCADE")
    op.execute("DROP TABLE IF EXISTS sweep_run CASCADE")
