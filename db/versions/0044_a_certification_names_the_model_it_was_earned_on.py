"""A certification names the model it was earned on, not just the model's label

Revision ID: 0044
Revises: 0043

Ruled 17 September 2026 (Ivan Green): a certification records the model the agent passed
on - **name, exact digest, temperature and max tokens**. A certification that does not
name the model cannot enforce re-certification when the model changes.

THIS REVISION NUMBER COLLIDES WITH PR #166, AND ALEMBIC WILL SAY SO
===================================================================

    PR #166 also adds a `0044` (`curriculum_submission.office_agent_id`). Whichever of
    the two merges second must renumber to `0045` and set `down_revision` accordingly.

    **That is the ledger-numbering problem again, one directory over - and here it is
    already solved.** Two revisions sharing a `down_revision` give alembic two heads and
    it refuses to run, by name, on the first command anybody types. Markdown headings
    had no such check, which is why four ledger numbers were claimed twice before
    anybody noticed. The fix landing alongside this one gives `docs/decisions.md` the
    equivalent.

WHAT `agent_model` COULD NOT SAY
===============================

    0035 added `agent_model` and B34 made it mandatory on any row carrying an answered
    SimForge verdict, so the LABEL has been required for a while. The label is
    `ollama/llama3.1:8b`, and it reads identically whether the tag was re-pulled at a
    different quantization or served at a different temperature. Two certifications with
    the same `agent_model` can describe different candidates, and nothing could tell
    them apart.

    **Measured before this was written, and the gap is live rather than theoretical:**

        the exam        temperature 0.0, max_tokens 2048 - `EXAM_TEMPERATURE` and
                        `EXAM_MAX_TOKENS`, simforge `agent_runtime/runtime.py:23-24`,
                        passed explicitly so the values `generation_settings` records
                        are the values the call sends.
        production      temperature 0.7, num_predict 200 / 300 / 500 by route -
                        village `modules/agent_orchestrator.py:1035-1060`.

    Every generation setting differs, on every call. The weights are not pinned either
    (`phi4:latest`). So no certification on record describes the model the agent runs,
    and none of them could have said so.

WHY FIVE COLUMNS AND NOT ONE JSONB
==================================

    `model_identity` alone would carry everything, and `certification` would then hold a
    fact that no constraint can reach and no index can find. The four scalars are the
    ones the ruling names and the ones a CHECK can demand; the jsonb is kept beside them
    so a field nobody anticipated is not lost. `revocation.blast_radius` is the
    precedent - stored whole, with the parts that matter promoted.

    `agent_model` STAYS. It is the readable label, every row that has one keeps it, and
    replacing it would rewrite history to look as though it had always carried a digest.

THE CHECK IS VALIDATED, NOT `NOT VALID`, AND THAT WAS MEASURED
==============================================================

    A constraint demanding the digest on every answered row would fail to apply if any
    existing row lacked one. Counted first: `certification` holds 26 rows, all
    `certified`, all with `simforge_verdict IS NULL` and `agent_model IS NULL` - every
    one of them bootstrap-attested. **No row in this database carries a real SimForge
    verdict at all**, so nothing violates the new constraint and it is added validated.

    If that had not been true the honest move would have been `NOT VALID` - enforce on
    new rows, leave history alone, and say so in the schema. It is worth writing down
    that the strict version was available because the data allowed it, not because the
    rule is lenient.

WHAT THIS MIGRATION DELIBERATELY DOES NOT ADD
=============================================

    **No `stale_model` state.** The state vocabulary already carries
    `stale_instructions` and `stale_forge`, and model drift is the obvious third. It is
    not added here because **nothing can write it yet**: deciding a certification has
    gone stale needs the model the agent is running NOW, and The Office has no source
    for it - `broker/village.py` reads roster, departments, agent state, shifts,
    deputies and the board, and no model configuration at all.

    An enum value nothing writes is a control that looks correct in review and does
    nothing, which is the specific failure this codebase keeps finding. It goes in with
    the comparison that sets it, in one migration, when the Village exposes the current
    model.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

#: B34's constraint in shape, and deliberately narrower in scope.
#:
#: B34 keys on the VERDICT and demands the label on every answered one, including a
#: FAIL. This keys on the STATE and demands the model only on `certified` and
#: `provisional` - the two an agent can act under, and the two the ruling is about:
#: "the model the agent PASSED on".
#:
#: A FAIL is not asked, and that is a decision rather than an omission. It records that
#: an agent was tested and did not pass, which cannot go stale and so has nothing to
#: expire; demanding the digest would make an older SimForge's failure refused rather
#: than recorded. Losing a pass is safe. Losing a failure is not.
_NAMES_ITS_MODEL = """
    simforge_verdict IS NULL
    OR state <> ALL (ARRAY['certified', 'provisional'])
    OR (
        agent_model IS NOT NULL
        AND model_digest IS NOT NULL
        AND model_temperature IS NOT NULL
        AND model_max_tokens IS NOT NULL
    )
"""


def upgrade() -> None:
    op.add_column("certification", sa.Column("model_digest", sa.Text(), nullable=True))
    op.add_column(
        "certification", sa.Column("model_temperature", sa.Numeric(), nullable=True)
    )
    op.add_column(
        "certification", sa.Column("model_max_tokens", sa.Integer(), nullable=True)
    )
    op.add_column(
        "certification",
        sa.Column("model_identity", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
    )
    op.add_column(
        "certification", sa.Column("model_fingerprint", sa.Text(), nullable=True)
    )

    op.create_check_constraint(
        "certification_names_its_model", "certification", _NAMES_ITS_MODEL
    )

    # Every row that has one, so drift can be found without a table scan once there is
    # something to compare against. Partial, because the column is NULL on every
    # bootstrap row and those are the majority today.
    op.create_index(
        "ix_certification_model_fingerprint",
        "certification",
        ["model_fingerprint"],
        postgresql_where=sa.text("model_fingerprint IS NOT NULL"),
    )

    op.execute("""
        COMMENT ON COLUMN certification.model_digest IS
        'The exact weights file the exam ran against - the thing agent_model cannot '
        'say, because the same tag re-pulled at a different quantization produces the '
        'identical label. NULL on a bootstrap certification, which no model earned.'
    """)
    op.execute("""
        COMMENT ON COLUMN certification.model_fingerprint IS
        'SimForge hash over the whole model identity record, so re-certification on '
        'drift is a string comparison rather than a field-by-field argument. Nothing '
        'compares it yet: that needs the model the agent is running now, and The '
        'Office has no source for it. See docs/decisions.md.'
    """)


def downgrade() -> None:
    op.drop_index("ix_certification_model_fingerprint", table_name="certification")
    op.drop_constraint(
        "certification_names_its_model", "certification", type_="check"
    )
    for column in (
        "model_fingerprint", "model_identity", "model_max_tokens",
        "model_temperature", "model_digest",
    ):
        op.drop_column("certification", column)
