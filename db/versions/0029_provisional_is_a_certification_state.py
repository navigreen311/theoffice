"""`provisional` — the eighth state, and why The Office had to learn it.

SimForge emits eight operation-cert states. The CHECK constraint written in 0007 knows
seven. The eighth, `provisional`, was added by SimForge's Rev-2 audit and means
something none of the seven can say:

    The agent passed the threshold, but the rubric did not discriminate — every
    dimension scored the same, or a required never-do dimension was never tested. Full
    certification is WITHHELD.

WHY IT IS STORED RATHER THAN REJECTED
=====================================

    The alternative was asking SimForge to stop emitting it, and that is strictly worse.
    A collapsed rubric is not a property of the agent; it is a property of the test. If
    SimForge had to pick one of our seven it would have to pick `certified`, because the
    agent did pass — and an unassignable governance hold would arrive here as an
    assignable certification. The information would be destroyed at the only place that
    can observe it.

    Every other mapping is wrong in a way that matters:

        failed            says the agent scored badly. It did not.
        never_certified   says nothing was attempted. A battery ran.
        in_training       says a battery is running now. It finished.

    That is the same not-run-versus-failed distinction Part 10.1 already insists on, one
    level further in, and the reason `state` is an enumeration and not a score.

WHAT IT MEANS FOR ASSIGNABILITY — the part that must be decided, not inherited
=============================================================================

    **`provisional` is NOT assignable.** `grants.resolve_grant` requires state
    `certified` on both units and nothing else passes, so storing this state grants
    nothing on its own. That is the correct behaviour and it is now also a tested one
    (`tests/contract/test_simforge_vocabulary.py`) rather than a happy consequence of
    an equality check.

    A state The Office can store but cannot reason about would be worse than one it
    rejects, so the reasoning is written down here rather than left implicit:

        - it does not permit a call, because the tier gate never sees a grant
        - it is not a failure, so it must not feed a failure metric
        - it is resolved by a fresh battery, exactly as a stale cert is
        - it is a governance hold, so it belongs on the escalation surface next to
          `stale_instructions`, not next to `failed`

    `certified_records_its_basis` is extended to cover it. A provisional cert DID run
    against a specific instruction hash and Forge api_version, so staleness is
    computable for it and must be recorded — otherwise a provisional hold outlives the
    text it was measured against and nobody can tell.

    `certified_tier` is deliberately NOT required. A provisional cert has withheld
    certification, so it has no certified tier to cap with; requiring one would invite
    a placeholder, and a placeholder tier on an unassignable cert is the value somebody
    later reads as real.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE certification DROP CONSTRAINT IF EXISTS certification_state_check")
    op.execute("""
        ALTER TABLE certification ADD CONSTRAINT certification_state_check
        CHECK (state IN (
          'certified','provisional','stale_instructions','stale_forge',
          'in_training','never_certified','failed','revoked'
        ))
    """)
    op.execute("""
        COMMENT ON CONSTRAINT certification_state_check ON certification IS
        'Eight states, never collapsed. `provisional` is SimForge''s governance hold: '
        'passed the threshold, rubric did not discriminate. Not assignable - '
        'resolve_grant requires `certified`.'
    """)

    # A provisional cert ran against something. Recording what makes its staleness
    # computable; omitting it would make the hold permanent by accident, which is the
    # same defect `certified_records_its_basis` was written to prevent for `certified`.
    op.execute(
        "ALTER TABLE certification DROP CONSTRAINT IF EXISTS certified_records_its_basis"
    )
    op.execute("""
        ALTER TABLE certification ADD CONSTRAINT certified_records_its_basis
        CHECK (
          (state <> 'certified'
           OR (instruction_content_hash IS NOT NULL
               AND forge_api_version IS NOT NULL
               AND certified_tier IS NOT NULL))
          AND
          (state <> 'provisional'
           OR (instruction_content_hash IS NOT NULL
               AND forge_api_version IS NOT NULL))
        )
    """)
    op.execute("""
        COMMENT ON CONSTRAINT certified_records_its_basis ON certification IS
        'A certified cert records hash, api_version and tier. A provisional cert records '
        'hash and api_version - it ran - but has no certified_tier, because certification '
        'was withheld and a placeholder tier is a number somebody later reads as real.'
    """)


def downgrade() -> None:
    # Any provisional row is deleted rather than remapped. There is no honest
    # seven-state value for it: `certified` would make an unassignable hold
    # assignable, and `failed` would record a failure that did not happen.
    op.execute("DELETE FROM certification WHERE state = 'provisional'")

    op.execute(
        "ALTER TABLE certification DROP CONSTRAINT IF EXISTS certified_records_its_basis"
    )
    op.execute("""
        ALTER TABLE certification ADD CONSTRAINT certified_records_its_basis
        CHECK (
          state <> 'certified'
          OR (instruction_content_hash IS NOT NULL
              AND forge_api_version IS NOT NULL
              AND certified_tier IS NOT NULL)
        )
    """)

    op.execute("ALTER TABLE certification DROP CONSTRAINT IF EXISTS certification_state_check")
    op.execute("""
        ALTER TABLE certification ADD CONSTRAINT certification_state_check
        CHECK (state IN (
          'certified','stale_instructions','stale_forge',
          'in_training','never_certified','failed','revoked'
        ))
    """)
