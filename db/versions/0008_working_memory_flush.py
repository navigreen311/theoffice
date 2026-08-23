"""Agent working memory, and the evidence a shift-boundary flush actually happened.

Master prompt Part 8: the PHI wall is temporal. There is one Village, and the same agent
may serve MedLink and Collingswood across consecutive shifts. So the wall runs at the
boundary, inside a single agent.

Two things here are the control, and both are structural rather than procedural:

  * `data_classification` is NOT NULL **with no default**. Part 8 requires PHI to be
    "tagged at write time, not inferred at flush time" — so a caller cannot write memory
    without deciding what it is. Inferring at flush means scanning content with a
    heuristic, and a heuristic that misses once has leaked PHI across a venture boundary
    permanently.

  * `flush_evidence` records the counts before and after. A boolean that says the flush
    succeeded is a claim; a count of PHI rows before and a count of zero after is
    evidence. Part 8 says "flush verified", and verified means someone can check.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE agent_working_memory (
          memory_id           UUID PRIMARY KEY,
          office_agent_id     UUID NOT NULL REFERENCES office_agent_identity,
          shift_id            UUID REFERENCES shift_assignment,
          venture_id          TEXT NOT NULL,
          data_classification TEXT NOT NULL CHECK (data_classification IN
                                ('phi','pii','financial','recording','internal','public')),
          content_ref         TEXT NOT NULL,
          written_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        COMMENT ON COLUMN agent_working_memory.data_classification IS
        'NOT NULL and no DEFAULT, deliberately. Part 8: PHI is tagged at write time, '
        'never inferred at flush time. A caller must decide what it is writing.'
    """)
    op.execute("""
        COMMENT ON COLUMN agent_working_memory.content_ref IS
        'A reference, never the content. Working memory that stored PHI bodies would '
        'make this table the thing the PHI wall exists to protect.'
    """)
    op.execute("""
        CREATE INDEX ix_working_memory_agent ON agent_working_memory
          (office_agent_id, data_classification)
    """)
    op.execute("""
        CREATE INDEX ix_working_memory_phi ON agent_working_memory (office_agent_id)
          WHERE data_classification = 'phi'
    """)

    # Evidence, not a claim. A boolean saying the flush worked is worth nothing; a
    # count before and a count of zero after is checkable by someone who was not there.
    op.execute("ALTER TABLE shift_assignment ADD COLUMN flush_evidence JSONB")
    op.execute("ALTER TABLE shift_assignment ADD COLUMN flush_attempted_at TIMESTAMPTZ")
    op.execute("""
        COMMENT ON COLUMN shift_assignment.flush_evidence IS
        'Counts of classified rows before and after the flush. Part 8 requires the '
        'flush to be verified; verified means a third party can check it.'
    """)
    op.execute("""
        COMMENT ON COLUMN shift_assignment.flush_attempted_at IS
        'Attempted is not verified. A flush that ran and left PHI behind sets this and '
        'leaves flush_verified false, which blocks the next assignment.'
    """)

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON agent_working_memory TO office_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_working_memory CASCADE")
    op.execute("ALTER TABLE shift_assignment DROP COLUMN IF EXISTS flush_evidence")
    op.execute("ALTER TABLE shift_assignment DROP COLUMN IF EXISTS flush_attempted_at")
