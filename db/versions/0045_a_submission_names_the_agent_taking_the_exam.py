"""A curriculum submission names the agent taking the exam

Revision ID: 0045
Revises: 0044

Ruled 17 September 2026 (Ivan Green): **every exam submission names the agent taking
it.** Until now none did, and the column this adds is what makes the sentence true.

RENUMBERED FROM 0044 TO 0045, AND THE COLLISION IS WORTH THE PARAGRAPH
======================================================================

    This was written as `0044` while another session wrote a different `0044` -
    `certification.model_digest` and its siblings, PR #173. Both branched from 0043 and
    neither could see the other.

    **Alembic catches that and `docs/decisions.md` did not.** Two revisions sharing a
    `down_revision` give alembic two heads and it refuses to run, by name, on the first
    command anybody types, so this cost a rename. Four ledger entry numbers were claimed
    twice in the same week and nothing failed at all, because git has no opinion about a
    markdown heading. Entry 117 gives the ledger the equivalent; entry 118 is the rule
    about the sessions.

    Ruled by Ivan Green: whichever of the two merges second renumbers. #173 merged
    first, so this is 0045.

WHAT THE ABSENCE COST
=====================

    `sweeps._grant_holders` opens with the reason: *"`curriculum_submission` records a
    venture, a Forge and a module and names no agent; `GateResult` names none either."*
    So the sweep recovered the population from `agent_forge_grant` and wrote one
    certification per holder from a single verdict.

    That was the best available answer while nobody took the exam. It stops being one
    the moment somebody does: SimForge's battery scores `run.agentId` - one agent - and
    fanning that one agent's verdict across every holder of the module would certify
    agents who never sat it.

    Gate 8 also sent `agent_id` only when a module had exactly one candidate. Measured
    on greenstone before this was written: `assign_contract` and `buyer_match` had ten
    candidates each, `comp_analysis` and `property_lookup` had none. Never one. So the
    field was NULL on every run ever opened, and SimForge skipped every one of them
    (`battery.py::SKIP_NO_MODULE`, which requires `run.agentId`).

NULLABLE, AND THAT IS NOT A LOOPHOLE
====================================

    A unit-B submission is about a department and has no agent, so the column is NULL
    on every one of them by construction - the same shape `module_id` and `department`
    already have, where exactly one is set and `submission_unit` is the rule.

    It is also NULL on every row written before this migration. Those are real rows the
    sweep may still be waiting on, and back-filling them from `agent_forge_grant` would
    write today's grant holders into a record of who was asked in the past. The sweep
    keeps its old behaviour for a row that names nobody and uses the name when there is
    one, which is the only reading that does not invent history.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "curriculum_submission",
        sa.Column("office_agent_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  nullable=True),
    )
    op.create_foreign_key(
        "fk_curriculum_submission_agent",
        "curriculum_submission", "office_agent_identity",
        ["office_agent_id"], ["office_agent_id"],
    )
    op.create_index(
        "ix_curriculum_submission_agent", "curriculum_submission", ["office_agent_id"]
    )
    op.execute("""
        COMMENT ON COLUMN curriculum_submission.office_agent_id IS
        'The agent this exam was submitted for. NULL on a unit-B submission, which is '
        'about a department, and on any row written before 0044. The verdict for this '
        'submission certifies THIS agent and no other.'
    """)


def downgrade() -> None:
    op.drop_index("ix_curriculum_submission_agent", table_name="curriculum_submission")
    op.drop_constraint(
        "fk_curriculum_submission_agent", "curriculum_submission", type_="foreignkey"
    )
    op.drop_column("curriculum_submission", "office_agent_id")
