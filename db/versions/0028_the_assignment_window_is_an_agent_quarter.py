"""A shift assignment belongs to a Village quarter, and one agent works one venture in it.

The window used to be two wall-clock timestamps a caller chose. That is not a unit of
anything: the Village runs at 5 minutes to 720, so an eight-hour window here spans a
stretch of Village time nobody can name, and two assignments that look adjacent on our
clock can sit a Village month apart.

`quarter` names the window in the Village's own terms. It is the string the Village
reports on its objectives board - `2026Q1` - and it shares a name with a calendar quarter
and nothing else.

THE RULE THIS ENFORCES

    One agent, one venture, one quarter.

    Part 7.5 already ruled out mid-shift venture switching, and `assert_on_shift_for`
    enforces that per call. What nothing enforced was the wider version: an agent could
    hold a morning shift on one venture and an evening shift on another, inside the same
    quarter, with a flush in between. Each individual shift was clean. The agent-quarter
    was not.

    The exclusion constraint says it in the schema rather than in application code,
    because the check that lives in one function is the check the second caller forgets -
    and there is not yet a second caller, which is the moment to write it down.

WHY AN EXCLUSION CONSTRAINT AND NOT A UNIQUE INDEX

    An agent may work several shifts in a quarter - MORNING and EVENING are separate
    rows. A unique index on (agent, quarter) would forbid that. What must be forbidden
    is two rows for the same agent and quarter that *disagree* about the venture, which
    is `WITH <>`. btree_gist is already required by `no_overlapping_shifts_per_agent`.

THE FLUSH IS UNCHANGED

    Still every boundary, still in the order `flush -> verify -> resolve -> switch ->
    audit`. Tying it to venture change would make it conditional, and this file's
    neighbouring rule exists because "a single uniform rule is enforceable where a
    conditional one is not". What the quarter adds is that a venture change now *has* a
    boundary to happen at, rather than being possible inside a window with no name.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0026 deleted every shift with the identities that held them, so there is nothing
    # to backfill and no default to invent. A default would have been the wrong answer
    # anyway: an assignment whose quarter nobody set is an assignment in no window.
    op.execute("ALTER TABLE shift_assignment ADD COLUMN quarter text")
    op.execute("ALTER TABLE shift_assignment ALTER COLUMN quarter SET NOT NULL")

    op.execute("""
        ALTER TABLE shift_assignment ADD CONSTRAINT quarter_is_a_village_quarter
        CHECK (quarter ~ '^[0-9]{4}Q[1-4]$')
    """)

    op.execute("""
        ALTER TABLE shift_assignment
        ADD CONSTRAINT one_venture_per_agent_quarter
        EXCLUDE USING gist (
            office_agent_id WITH =,
            quarter WITH =,
            venture_id WITH <>
        )
    """)

    op.execute("""
        COMMENT ON COLUMN shift_assignment.quarter IS
        'The Village quarter this assignment falls in, e.g. 2026Q1, read from the '
        'Village objectives board. The assignment window is an agent-quarter: one agent '
        'works one venture for the whole of it, enforced by '
        'one_venture_per_agent_quarter. Wall-clock timestamps still bound the individual '
        'shift; they do not name a window, because the Village runs at 5/720.'
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE shift_assignment DROP CONSTRAINT IF EXISTS one_venture_per_agent_quarter"
    )
    op.execute(
        "ALTER TABLE shift_assignment DROP CONSTRAINT IF EXISTS quarter_is_a_village_quarter"
    )
    op.execute("ALTER TABLE shift_assignment DROP COLUMN IF EXISTS quarter")
