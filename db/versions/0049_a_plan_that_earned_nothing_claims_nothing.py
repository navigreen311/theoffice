"""A plan that earned nothing claims nothing

Revision ID: 0049
Revises: 0048

Ruled 21 September 2026 (Ivan Green): **an uncertified module's planned tier reads as
none, not the declared tier. A plan that claims authority nothing earned reads as
authority.**

WHY THE COLUMN HAD TO CHANGE
============================

    `agent_forge_grant.trust_tier` has been NOT NULL since 0001, and until 21 September
    that was exactly right: a grant existed only for a module its holder was certified
    on, so there was always a certified tier to cap the declared one against.

    Entry 145 made the grant an exam ticket. An uncertified appointee now holds one, and
    `runtime_config` had nothing to write in this column but the tier the Pack declares -
    which is the ceiling, not an entitlement. Greenstone's `buyer_match` declares
    `auto_execute`, so the first run under entry 145 would have written `auto_execute`
    onto six grants nothing had earned.

    Not a live authority: `resolve_grant` refuses the call on certification state, and
    Gate 11 refuses to activate. **An authority-shaped value in the column the call path
    caps against**, which is the shape this codebase keeps refusing - the same argument
    `simforge.TIMEOUT_RUBRIC_VERSION` makes for not writing a plausible semver, and the
    same one `timeout_gate_result` makes for not writing a score of 0.0.

NULL, NOT A FLOOR
=================

    `suggest` was the tempting placeholder and it is still an authority level. Absent is
    the honest value, and it is the value the ruling names.

    The CHECK keeps its three-value vocabulary and gains NULL, so the column cannot hold
    a fourth word by accident. Nothing is backfilled: every existing grant was issued for
    a module its holder was certified on, and its tier was earned.

WHAT REFUSES IT
===============

    Gate 11 will not activate a grant with no planned tier, beside the certification test
    entry 145 added, and `resolve_grant` raises `NoTierPlanned` before it reaches
    `cap_tier`. Both are defence behind Gate 11's certification predicate rather than
    instead of it: a grant with no tier is always also uncertified today, and a control
    that depends on that staying true is a control that expires quietly.
"""

from __future__ import annotations

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_forge_grant ALTER COLUMN trust_tier DROP NOT NULL")
    op.execute("""
        COMMENT ON COLUMN agent_forge_grant.trust_tier IS
        'The tier this grant PLANS, capped at issuance by what the holder is certified '
        'to. NULL means no tier was planned: the holder is not certified for this '
        'module, so the grant is an exam ticket and confers nothing (entry 145). '
        'resolve_grant caps a live call against this and refuses a NULL outright.'
    """)


def downgrade() -> None:
    # A row the ruling created cannot be given a tier on the way back - inventing one is
    # the exact thing the ruling forbids - so the rows are removed rather than filled.
    # They are inactive exam tickets; the next Gate 5 re-issues them.
    op.execute("DELETE FROM agent_forge_grant WHERE trust_tier IS NULL")
    op.execute("ALTER TABLE agent_forge_grant ALTER COLUMN trust_tier SET NOT NULL")
