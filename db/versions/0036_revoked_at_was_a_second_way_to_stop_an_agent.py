"""Drop `agent_forge_grant.revoked_at` — it was a second way to stop an agent, with no writer.

B37. The column has been read on every brokered call since `resolve_grant` was written
and **has never been written by anything in the broker**. `revoke()` inserts a
`revocation` row and does not touch the grant. The only statement in the repository that
ever wrote this column set it to NULL — `clear_grant_tombstone`, which existed to undo
two values put there by hand during Phase 0 bootstrapping, with no reason, no named
actor and no audit event behind them.

So the column was a stop with no ritual: a value in it refused an agent for as long as it
sat there, and nothing in the system could explain why, reverse it through the declared
path, or show it on the revocations screen.

WHY DROPPING IT IS THE SMALL CHANGE AND THE OTHER TWO ARE NOT
=============================================================

    **Teaching `revoke()` to write it** materialises a declarative scope. A revocation
    names an agent, a Forge, a module or a venture, and grants issued *after* it are
    covered by it. A column stamped at revocation time covers the rows that existed then
    and silently misses the rest, so the column and the `revocation` table would answer
    "is this agent stopped" differently, which is the defect with one more writer.

    **Dropping only the `resolve_grant` read** leaves every other site filtering on a
    column nothing enforces. A stamped grant would be uncounted on four console screens
    and skipped by the activation UPDATE while calls against it succeeded. An
    inconsistent stop is worse than either a consistent one or none.

WHY NOW
=======

    Because it is non-lossy today and stops being so the moment anything sets a stamp.
    Both databases were checked before this was written: 6 grants in dev, 0 carrying a
    value; 0 rows in test. The downgrade below restores the column and the partial
    indexes, and **it cannot restore values** - there are none to restore now, and a
    downgrade run after something has written one would silently discard it. That is
    stated rather than implied, because a reversible-looking migration that quietly
    loses data is the shape `alembic downgrade` invites.

THE TWO PARTIAL INDEXES
=======================

    Both are defined on this column's predicate, and `ix_grant_lookup` is the path
    `resolve_grant` itself rides:

        ix_grant_lookup         (office_agent_id, forge_id, module_id)
                                WHERE revoked_at IS NULL
        ix_grant_lookup_active  (office_agent_id, forge_id, module_id)
                                WHERE revoked_at IS NULL AND activated_at IS NOT NULL

    With no writer the predicates are always true, so both are full indexes wearing a
    condition. They are rebuilt without the `revoked_at` term.

    **`ix_grant_lookup_active` keeps its second term.** Dropping both predicates would
    make it byte-identical to `ix_grant_lookup`, and Postgres would happily maintain two
    identical indexes forever - a duplicate is not a simplification.

`is_assignable` IS GENERATED FROM THIS COLUMN, WHICH IS WHY IT IS REDEFINED HERE
================================================================================

    Not predicted; found because `DROP COLUMN` refused:

        column is_assignable of table agent_forge_grant depends on column revoked_at

    `is_assignable` is `GENERATED ALWAYS AS ((operation_cert_ref IS NOT NULL) AND
    (dept_context_cert_ref IS NOT NULL) AND (revoked_at IS NULL) AND (activated_at IS
    NOT NULL))`. So the dead column has been a term in a live derived value the whole
    time - the one the console reads as "assignable grants". **No behaviour changes**,
    because `revoked_at IS NULL` has been TRUE on every row that ever existed, which is
    the same reason every other site here is a safe deletion.

    **Dropped and re-added rather than `ALTER COLUMN ... SET EXPRESSION`.** The latter
    is cleaner and is PostgreSQL 17+. This machine runs 17.9 and **CI runs
    `postgres:16`**, so `SET EXPRESSION` would pass locally and fail in CI - the local
    pass being the false signal. Nothing indexes or views this column, and nothing does
    `SELECT *` on the table, so re-adding it at the end of the column order is inert.

WHAT REPLACES IT
================

    Nothing new. `revocation.covered_grants()` already answers "which of these grants a
    live revocation covers", built by P-17 for Gate 7, using the same predicate and the
    same breadth ordering as the per-call check - so a grant appears there exactly when a
    call against it would raise `Revoked`. Gate 7's own docstring deferred this migration
    by name: *"`revoked_at IS NULL` stays in the SQL below as a term, and today it is a
    no-op. It is left because removing a column read that `broker/app.py` and
    `broker/grants.py` also perform is a wider change than this gate."* This is that
    wider change.
"""

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

_LOOKUP = "ix_grant_lookup"
_LOOKUP_ACTIVE = "ix_grant_lookup_active"
_COLS = "(office_agent_id, forge_id, module_id)"

#: What `is_assignable` means once revocation stops being a column. Everything else in
#: the expression is untouched, and the dropped term was TRUE on every row.
_ASSIGNABLE_AFTER = (
    "operation_cert_ref IS NOT NULL AND dept_context_cert_ref IS NOT NULL "
    "AND activated_at IS NOT NULL"
)
_ASSIGNABLE_BEFORE = (
    "operation_cert_ref IS NOT NULL AND dept_context_cert_ref IS NOT NULL "
    "AND revoked_at IS NULL AND activated_at IS NOT NULL"
)


def upgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_LOOKUP}")
    op.execute(f"DROP INDEX IF EXISTS {_LOOKUP_ACTIVE}")

    # `is_assignable` is GENERATED from `revoked_at`, so it blocks the drop. Dropped and
    # re-added rather than `SET EXPRESSION`, which is PG17-only and CI runs postgres:16.
    op.execute("ALTER TABLE agent_forge_grant DROP COLUMN is_assignable")
    op.execute("ALTER TABLE agent_forge_grant DROP COLUMN revoked_at")
    op.execute(
        "ALTER TABLE agent_forge_grant ADD COLUMN is_assignable boolean "
        f"GENERATED ALWAYS AS ({_ASSIGNABLE_AFTER}) STORED"
    )

    op.execute(f"CREATE INDEX {_LOOKUP} ON agent_forge_grant {_COLS}")
    # Still partial, on the term that is not going away: a grant is usable only once
    # activated, and that column IS written.
    op.execute(
        f"CREATE INDEX {_LOOKUP_ACTIVE} ON agent_forge_grant {_COLS} "
        "WHERE activated_at IS NOT NULL"
    )


def downgrade() -> None:
    """Restores the column and both predicates. **It cannot restore values.**

    There are none to restore at the time this is written. Run after something has
    written one and that value is gone - the column comes back empty and every
    `WHERE revoked_at IS NULL` reads TRUE for a grant that had been stopped.
    """
    op.execute(f"DROP INDEX IF EXISTS {_LOOKUP}")
    op.execute(f"DROP INDEX IF EXISTS {_LOOKUP_ACTIVE}")

    op.execute("ALTER TABLE agent_forge_grant DROP COLUMN is_assignable")
    op.execute("ALTER TABLE agent_forge_grant ADD COLUMN revoked_at timestamptz")
    op.execute(
        "ALTER TABLE agent_forge_grant ADD COLUMN is_assignable boolean "
        f"GENERATED ALWAYS AS ({_ASSIGNABLE_BEFORE}) STORED"
    )

    op.execute(
        f"CREATE INDEX {_LOOKUP} ON agent_forge_grant {_COLS} "
        "WHERE revoked_at IS NULL"
    )
    op.execute(
        f"CREATE INDEX {_LOOKUP_ACTIVE} ON agent_forge_grant {_COLS} "
        "WHERE revoked_at IS NULL AND activated_at IS NOT NULL"
    )
