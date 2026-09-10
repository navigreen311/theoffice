"""A certification names the model that earned it.

`certified_records_its_basis` has existed since 0007 and its argument is in its name: a
certification whose basis is unknown is permanent by accident. It requires
`instruction_content_hash`, `forge_api_version` and `certified_tier` on a certified row,
so a later reader can say what the agent was measured against and recompute staleness
when any of those move.

It says nothing about the model - and the model is the thing that actually answered the
probe. Everything else the CHECK names describes the *exam*: which instructions, which
Forge version, which tier. The model is the *candidate*, and it went unrecorded.

    Certify an agent against `llama3.1:8b` today and the row says the agent passed.
    Swap the model tomorrow and the row still reads as current.

That is blocking.md B34's shape - an assertion wider than what was measured - in the row
where it costs most, because this row is what the call path enforces on every request.

WHY THE RULE IS NOT "CERTIFIED IMPLIES A MODEL"
==============================================

    Read out of the table before this was written:

        state=certified            simforge_verdict IS NULL   4 rows
        state=stale_instructions   simforge_verdict IS NULL   3 rows

    **Every certified row today is a bootstrap row.** It has no model because no battery
    ever ran - `attested_by='bootstrap'` means "a grant issued against no scenario run",
    and `record_result` demands a `bootstrap_reason` for exactly that case. Those rows
    have nothing to name and forcing them to invent one would be the opposite of this
    migration's point.

    So the rule is narrower and it is about evidence rather than state:

        a certification whose verdict means SOMETHING ANSWERED must name the
        model that answered

    Not "a real verdict" - that was the first draft and a test caught it. TIMEOUT,
    NOT_RUN and IN_PROGRESS are verdicts, and they are verdicts *about an open run*:
    `gate_result_for` derives them from the window when nothing was stored. A timed-out
    battery has no model for the same reason a bootstrap does not - nothing answered -
    and a CHECK that demanded one would force a timeout to name a candidate that never
    sat the exam.

    So the exempt set is `simforge_verdict IS NULL` (bootstrap) plus the non-terminal
    verdicts, and the required set mirrors `simforge.TERMINAL_VERDICTS`, which P-03
    named for exactly this distinction when it decided which results may stamp
    `result_received_at`.

WHY THE VALUE IS PROVIDER-QUALIFIED
===================================

    `llama3.1:8b` alone is weaker than it looks: the same tag can serve different weights
    over time, and an Ollama `llama3.1:8b` is not interchangeable evidence with a hosted
    one. The column holds `provider/model` - `ollama/llama3.1:8b` - so the row names
    both halves of what answered.

    Whether it should also carry a weight digest is deliberately NOT settled here.
    Ollama exposes one, and "the same tag, different weights" is precisely the staleness
    this table already tracks for instructions and API versions - so it is a real
    question, and a second migration is a smaller cost than a column that quietly means
    two things.

REVERSIBLE
==========

    The CHECK is dropped and recreated in both directions, and the column is dropped on
    the way down. Nothing is deleted to make the downgrade fit: no row can violate the
    OLD constraint by carrying an extra column, so unlike 0034 this reverses without
    losing history.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

_BASIS_BEFORE = """
    state <> 'certified'
    OR (instruction_content_hash IS NOT NULL
        AND forge_api_version IS NOT NULL
        AND certified_tier IS NOT NULL)
"""

#: The verdicts that mean SOMETHING ANSWERED. Mirrors `simforge.TERMINAL_VERDICTS`,
#: and the mirroring is the point rather than a coincidence: TIMEOUT, NOT_RUN and
#: IN_PROGRESS are computed by SimForge *about an open run* - `gate_result_for` derives
#: them from the window when no verdict is stored - so a row carrying one records that
#: nothing answered. Demanding a model there would make a timeout name a candidate that
#: never sat the exam, which is the same error as letting a certified row omit one.
_ANSWERED = "'PASS','PROVISIONAL','FAIL','REVOKED'"

#: The added clause is the second one, and it is keyed on EVIDENCE rather than on state:
#: something answered, therefore the row must say what. A `provisional` row earned from a
#: real battery is covered - it was measured by a model as much as a certified one was -
#: and a bootstrap (`simforge_verdict IS NULL`) and a timeout are both exempt, for the
#: same reason: no battery ran.
_BASIS_AFTER = f"""
    (state <> 'certified'
     OR (instruction_content_hash IS NOT NULL
         AND forge_api_version IS NOT NULL
         AND certified_tier IS NOT NULL))
    AND (simforge_verdict IS NULL
         OR simforge_verdict NOT IN ({_ANSWERED})
         OR agent_model IS NOT NULL)
"""


def upgrade() -> None:
    op.add_column("certification", sa.Column("agent_model", sa.Text(), nullable=True))
    op.execute(
        "COMMENT ON COLUMN certification.agent_model IS "
        "'provider/model that answered the battery, e.g. ollama/llama3.1:8b. "
        "NULL where nothing answered: a bootstrap grant (simforge_verdict IS NULL), or "
        "a verdict computed about an open run rather than earned in one - TIMEOUT, "
        "NOT_RUN, IN_PROGRESS.'"
    )
    op.execute("ALTER TABLE certification DROP CONSTRAINT certified_records_its_basis")
    op.execute(
        "ALTER TABLE certification ADD CONSTRAINT certified_records_its_basis "
        f"CHECK ({_BASIS_AFTER})"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE certification DROP CONSTRAINT certified_records_its_basis")
    op.execute(
        "ALTER TABLE certification ADD CONSTRAINT certified_records_its_basis "
        f"CHECK ({_BASIS_BEFORE})"
    )
    op.drop_column("certification", "agent_model")
