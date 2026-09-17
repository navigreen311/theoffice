"""A bootstrap grant is retired when the ladder issues its own, never revoked and never deleted

Revision ID: 0043
Revises: 0042

Run cb3a47f6 cleared Gate 4 and stopped at Gate 7 on *"3 grant(s) are already active
before Gate 11"*. The three were the Phase 0 grants `bootstrap-phase0` had issued hours
earlier for Victor Serath, Ronan Valek and Seraphine Valek - active by design, because
Phase 0 exists to prove the call path works and an inactive grant proves nothing.

WHY REVOCATION CANNOT EXPRESS THIS
==================================

    The obvious fix - revoke the three - was measured and refused. A revocation's
    narrowest scope is `agent_module`: agent, forge, module. Gate 5 had already issued the
    ladder's own grant for **the same three triples**, so `blast_radius` reported
    `grants=2` on each: the bootstrap grant AND its replacement. Gate 11 activates with
    `AND NOT (g.grant_id = ANY(covered))`, so revoking would have traded a Gate 7 block for
    a Gate 11 one and left three of six grants permanently unactivatable.

    **And it would have said the wrong thing.** Revocation means "this authority was
    wrong" - it is what Amelie Wystan's engineering-department grants got, with a reason
    naming why they should never have existed. A Phase 0 grant is not wrong. It did its
    job and has been replaced.

    Ruled 2026-09-16: retired, never deleted and never revoked, when the ladder issues its
    own grant for the same agent, forge, module and venture. Kept as history, refused at
    call time.

WHY `origin` HAS THREE VALUES AND ONE OF THEM IS `unknown`
==========================================================

    `bootstrap`   an audit `grant_issued` event carries `bootstrap: true` and names this
                  grant_id. Three rows today, all from 16 September.
    `ladder`      written by `runtime_config.apply`, going forward. Gate 5 retires a
                  bootstrap grant only against one of these.
    `unknown`     it existed before this migration and nothing machine-readable says which
                  wrote it.

    **The third value is the honest one.** Amelie Wystan's `cre-forge/property_lookup` was
    a Phase 0 grant - the revocation over it says so, in prose, naming commit d3c7573 - and
    marking it `bootstrap` would mean reading a sentence and writing it into a column as
    fact. Defaulting the rest to `ladder` would be worse: a claim that the sixteen gates
    issued rows they did not.

    So the backfill asserts only what the audit log proves, and everything else says it
    does not know. `unknown` behaves exactly as today: Gate 7 counts it, the call path
    allows it. Nothing is retired on a guess.

THE INVARIANT IS ESTABLISHED HERE AND MAINTAINED BY GATE 5
==========================================================

    Run cb3a47f6 has already passed Gate 5, so nothing will retire its three bootstrap
    grants on its own. Rather than leave that to a one-off script nobody will find again,
    this migration applies the rule once: **a bootstrap grant is retired where a
    non-superseded grant of another origin exists for the same (agent, forge, module,
    venture).**

    That is the same predicate `runtime_config.apply` will run after issuing, so the
    database leaves this migration in exactly the state Gate 5 would have left it in, and
    the rule has one definition rather than a migration's and a module's.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

#: `is_assignable` is a claim about one thing: whether `resolve_grant` can return this
#: row. It has meant "both certifications present AND activated" since 0011, and 0036
#: dropped `revoked_at IS NULL` from it when revocation left the row. `superseded_at` is
#: not revocation - it lives on the row, like `activated_at` - and `resolve_grant` now
#: refuses a retired grant, so leaving it out would make the column say `true` about a
#: grant the call path refuses. Gate 12, the console's grant badge, `roster` and
#: `ventures` all read this column and would all have been wrong in the same way.
_ASSIGNABLE_AFTER = (
    "operation_cert_ref IS NOT NULL AND dept_context_cert_ref IS NOT NULL "
    "AND activated_at IS NOT NULL AND superseded_at IS NULL"
)
#: What 0036 left it as.
_ASSIGNABLE_BEFORE = (
    "operation_cert_ref IS NOT NULL AND dept_context_cert_ref IS NOT NULL "
    "AND activated_at IS NOT NULL"
)

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_forge_grant", sa.Column("origin", sa.Text(), nullable=True))
    op.add_column(
        "agent_forge_grant",
        sa.Column("superseded_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Only what the audit log proves. `grant_issued` with `bootstrap: true` is written by
    # `bootstrap_phase0` and by nothing else.
    op.execute("""
        UPDATE agent_forge_grant g SET origin = 'bootstrap'
         WHERE EXISTS (
           SELECT 1 FROM audit_log a
            WHERE a.event_type = 'grant_issued'
              AND a.subject->>'bootstrap' = 'true'
              AND a.subject->>'grant_id' = g.grant_id::text
         )
    """)
    op.execute("UPDATE agent_forge_grant SET origin = 'unknown' WHERE origin IS NULL")
    op.alter_column("agent_forge_grant", "origin", nullable=False)
    # NOT NULL, and the default is the value that claims nothing. Both writers in the
    # codebase - `bootstrap_phase0` and `runtime_config.apply` - name their own origin,
    # so the default is only ever reached by something that has not said. `unknown`
    # retires nothing and is retired by nothing, so such a row behaves exactly as it did
    # before this migration, and the column shows plainly that nobody declared it.
    op.execute("ALTER TABLE agent_forge_grant ALTER COLUMN origin SET DEFAULT 'unknown'")
    op.create_check_constraint(
        "ck_grant_origin",
        "agent_forge_grant",
        "origin IN ('bootstrap', 'ladder', 'unknown')",
    )

    # The invariant, applied once. Identical predicate to `runtime_config.apply`'s.
    op.execute("""
        UPDATE agent_forge_grant b SET superseded_at = now()
         WHERE b.origin = 'bootstrap'
           AND b.superseded_at IS NULL
           AND EXISTS (
             SELECT 1 FROM agent_forge_grant l
              WHERE l.office_agent_id = b.office_agent_id
                AND l.forge_id        = b.forge_id
                AND l.module_id       = b.module_id
                AND l.venture_id      = b.venture_id
                AND l.grant_id       <> b.grant_id
                AND l.origin         <> 'bootstrap'
                AND l.superseded_at IS NULL
           )
    """)

    # Dropped and re-added rather than `SET EXPRESSION`, which is PG17-only while CI runs
    # postgres:16 - the same reason 0036 gave.
    op.execute("ALTER TABLE agent_forge_grant DROP COLUMN is_assignable")
    op.execute(
        "ALTER TABLE agent_forge_grant ADD COLUMN is_assignable boolean "
        f"GENERATED ALWAYS AS ({_ASSIGNABLE_AFTER}) STORED"
    )

    op.execute("""
        COMMENT ON COLUMN agent_forge_grant.superseded_at IS
        'When the ladder issued its own grant for this agent, forge, module and venture. '
        'A retired grant is kept as history and refused at call time with '
        'GrantSuperseded. It is NOT revoked: revocation means the authority was wrong, '
        'and a Phase 0 grant that has been replaced was not.'
    """)


def downgrade() -> None:
    # `is_assignable` is GENERATED from `superseded_at`, so it blocks the drop.
    op.execute("ALTER TABLE agent_forge_grant DROP COLUMN is_assignable")
    op.execute(
        "ALTER TABLE agent_forge_grant ADD COLUMN is_assignable boolean "
        f"GENERATED ALWAYS AS ({_ASSIGNABLE_BEFORE}) STORED"
    )
    op.drop_constraint("ck_grant_origin", "agent_forge_grant", type_="check")
    op.drop_column("agent_forge_grant", "superseded_at")
    op.drop_column("agent_forge_grant", "origin")
