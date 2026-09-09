"""A fifth sweep kind: the verdict ingest.

`sweep_run.sweep_kind` is a CHECK over four literals, not free text, and that is
deliberate - migration 0009's whole argument is that a sweep nobody runs is
indistinguishable from a healthy system, so the set of controls that exist is a
reviewable list in the schema rather than whatever a caller happened to insert.

The consequence is that adding a control is a migration. `broker/sweeps.py` can define
`verdict_ingest`, lock it, give it a `MAX_AGE` and wire it into `run_all`, and its very
first `_start` still fails on the constraint. So the constraint moves with it.

WHAT THE FIFTH CONTROL IS
=========================
The path by which a SimForge verdict becomes a `certification` row. Until it existed,
`certification.record_result` had one non-test caller - the Phase 0.8 bootstrap, which
issues grants nobody earned - and `attested_by='simforge'` appeared nowhere in the
system. A verdict that arrived had nothing to arrive at.

WHY IT IS DAILY, WHICH IS THE PART WORTH ARGUING
================================================
The freshness argument runs opposite to the intuitive one. A missed PASS is loud: the
agent stays uncertified and every call it makes is refused by `resolve_grant`, so
somebody asks within a shift. **A missed REVOKED is silent** - SimForge withdrew the
certification, The Office never read the verdict, and the call path goes on enforcing a
`certified` row that is no longer true. An un-run verdict ingest is therefore an
authority-retention risk of exactly the shape an unverified hash chain is, and it gets
the daily interval the chain and the staleness recompute already have, not the monthly
reconciliation's.

REVERSIBLE
==========
The constraint is dropped and recreated in both directions. `downgrade` deletes any
`verdict_ingest` rows first, because the old constraint cannot be added back over them -
and losing sweep history is the honest cost of removing a control, not something to hide
behind a `NOT VALID`.
"""

from __future__ import annotations

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

_KINDS_BEFORE = "'audit_chain','certification_staleness','manifest_reconciliation','restore_drill'"
_KINDS_AFTER = _KINDS_BEFORE + ",'verdict_ingest'"


def upgrade() -> None:
    op.execute("ALTER TABLE sweep_run DROP CONSTRAINT sweep_run_sweep_kind_check")
    op.execute(
        "ALTER TABLE sweep_run ADD CONSTRAINT sweep_run_sweep_kind_check "
        f"CHECK (sweep_kind IN ({_KINDS_AFTER}))"
    )
    op.execute("""
        COMMENT ON COLUMN sweep_run.sweep_kind IS
        'The controls that exist, as a reviewable list rather than whatever a caller '
        'inserted. Adding one is a migration on purpose: a control nobody runs is '
        'indistinguishable from a healthy system, and a kind that can be invented at '
        'the call site cannot be audited for absence.'
    """)


def downgrade() -> None:
    # The old constraint cannot be added back over rows it forbids.
    op.execute("DELETE FROM sweep_run WHERE sweep_kind = 'verdict_ingest'")
    op.execute("ALTER TABLE sweep_run DROP CONSTRAINT sweep_run_sweep_kind_check")
    op.execute(
        "ALTER TABLE sweep_run ADD CONSTRAINT sweep_run_sweep_kind_check "
        f"CHECK (sweep_kind IN ({_KINDS_BEFORE}))"
    )
