"""Let the runtime role read the schema revision.

`/api/ready` compares the migration the running build expects to the one the database
actually reports, so a container cannot serve traffic against a schema its code was
never written for. That check runs as `office_app`, and `office_app` could not read
`alembic_version` - alembic creates the table as the migration user and grants nothing.

The symptom would have been a readiness probe that never passes: the container starts,
answers `/api/live`, is never marked ready, and the deploy hangs waiting for a condition
that cannot become true. Found by calling the endpoint rather than by reading it.

SELECT only, on one column of one row containing a revision string. There is nothing to
learn from it that an operator holding the code does not already know, and the
alternative - having the readiness check connect as a superuser - would put admin
credentials in the API's environment to answer a question about a version number.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON alembic_version TO office_app")
    op.execute("""
        COMMENT ON TABLE alembic_version IS
        'Owned by alembic. office_app holds SELECT so /api/ready can compare the '
        'deployed schema to the one the running build expects; a container serving '
        'traffic against a half-migrated database answers, and answers wrong.'
    """)


def downgrade() -> None:
    op.execute("REVOKE SELECT ON alembic_version FROM office_app")
