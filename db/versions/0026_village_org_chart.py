"""Identities carry the Village's org chart, and the roster is a sync rather than an import.

The Village was rebuilt. It has 186 agents where The Office expected 106, normalized lore
names (`dr_brann_lorvik`) where The Office expected `alex_chen`, and twelve departments of
which nine did not exist under the names The Office had. The seven identities that existed
here were issued against the old roster.

WIPING RATHER THAN MIGRATING

    Nothing was worth keeping and no crosswalk exists. The seven identities held **zero
    grants**, had **never been assigned a shift**, and their 26 certifications were earned
    against instruction sets since found to be stubs - text that read fine and taught
    nothing. A crosswalk from `alex_chen` to a lore name cannot be built because the two
    namespaces were never related; the Village's own roster loader records that the
    mapping "did not survive the truncated transfer".

    So the identities go, and with them the certifications earned against stubs. This is
    done in a migration rather than by hand so that it is recorded, reversible in the
    sense that the rows are gone in a named revision, and identical on every database.

THREE NEW COLUMNS

    `role_key` and `reports_to` are the org chart, which The Office needs for two things
    it could not do before: sync an identity knowing where it sits, and walk an
    operational escalation up the reporting line to a department head. `department` was
    already here and now holds the Village's normalized form.

GRANTS KEY ON THE AGENT, NEVER ON THE POSITION

    Stated here because it is a property of the schema and not of any one function. There
    is no position column on `agent_forge_grant` or `certification`, and there must never
    be one. The Village auto-hires into a vacated seat: when an agent dies or retires, the
    replacement is a different agent with no history, and a grant keyed on the position
    would transfer silently to somebody who has never been certified for anything.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE office_agent_identity ADD COLUMN role_key TEXT")
    op.execute("ALTER TABLE office_agent_identity ADD COLUMN reports_to TEXT")
    op.execute("""
        COMMENT ON COLUMN office_agent_identity.role_key IS
        'The Village role ladder: department_head, deputy_head, senior_manager, '
        'team_lead, junior_manager, individual_contributor. Read from the Village; The '
        'Office does not assign it.'
    """)
    op.execute("""
        COMMENT ON COLUMN office_agent_identity.reports_to IS
        'The village_agent_ref of this agent''s manager, or NULL for the COO and the 11 '
        'department heads. That absence is the marker the Village itself uses, and it is '
        'preserved rather than filled with a sentinel. Operational escalation walks this '
        'column.'
    """)

    op.execute("ALTER TABLE village_agent ADD COLUMN role_key TEXT")
    op.execute("ALTER TABLE village_agent ADD COLUMN reports_to TEXT")
    op.execute("ALTER TABLE village_agent ADD COLUMN title TEXT")

    # The wipe. Certifications first, then the identities they hang from.
    #
    # `agent_forge_grant`, `shift_assignment`, `proposal`, `revocation` and
    # `agent_working_memory` all reference an identity and all are empty for these seven -
    # verified before writing this: 0 grants, 0 shifts. The deletes are unconditional
    # anyway, because a migration that silently leaves rows behind when its assumption is
    # wrong is worse than one that fails.
    # `proposal` references an identity too, and its 47 rows are all smoke-loop
    # fixtures written against agents that are about to stop existing. They cannot be
    # re-pointed - there is no crosswalk between `alex_chen` and a lore name - and a
    # proposal naming an agent nobody can look up is a record of a decision about
    # nobody. Incidents keep their rows and lose the reference: an incident is a
    # detection and the detection happened, so the agent id is cleared rather than the
    # row deleted.
    op.execute("UPDATE incident SET office_agent_id = NULL WHERE office_agent_id IS NOT NULL")
    op.execute("DELETE FROM proposal")
    op.execute("DELETE FROM certification")
    op.execute("DELETE FROM agent_working_memory")
    op.execute("DELETE FROM shift_assignment")
    op.execute("DELETE FROM agent_forge_grant")
    op.execute("DELETE FROM office_agent_identity")
    op.execute("DELETE FROM village_agent")

    op.execute("""
        COMMENT ON TABLE office_agent_identity IS
        'One row per Village agent that has been appointed into The Office. '
        'village_agent_ref is the Village''s normalized lore name and is the only '
        'identifier shared between the two applications. Grants and certifications key '
        'on office_agent_id and never on a position: the Village auto-hires into a '
        'vacated seat, and the new occupant inherits nothing.'
    """)


def downgrade() -> None:
    # The columns come off. The deleted identities do not come back - they were issued
    # against a roster that no longer exists, and inventing rows to satisfy a downgrade
    # would put unappointable agents back into a table whose whole purpose is to say who
    # may act.
    op.execute("ALTER TABLE village_agent DROP COLUMN IF EXISTS title")
    op.execute("ALTER TABLE village_agent DROP COLUMN IF EXISTS reports_to")
    op.execute("ALTER TABLE village_agent DROP COLUMN IF EXISTS role_key")
    op.execute("ALTER TABLE office_agent_identity DROP COLUMN IF EXISTS reports_to")
    op.execute("ALTER TABLE office_agent_identity DROP COLUMN IF EXISTS role_key")
