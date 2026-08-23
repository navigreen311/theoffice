"""Human identity, roles and gate sign-offs.

Master prompt Part 14. Every governance action built so far takes a `UUID` for the actor
and a role *string*, and trusts the caller about both. That was survivable while the only
callers were tests. It stops being survivable the moment a console exists.

Three things here are the control:

  * **A role is scoped to a venture.** A venture operator operates *a venture*, not the
    platform. `venture_id IS NULL` means all ventures and is what Ivan holds. The
    domain's authority matrix could not express this because it only ever saw a role
    string - so a venture operator could revoke in a venture they had nothing to do with.

  * **`token_hash`, never a token.** Same rule as `credential_ref`: the column holds
    something that proves possession without being the thing possessed.

  * **A sign-off binds to an artifact hash.** Part 14: "artifact change voids signature."
    The signature is void by *comparison* rather than by somebody remembering to revoke
    it - the same principle that makes certification staleness reliable.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE office_human (
          human_id     UUID PRIMARY KEY,
          display_name TEXT NOT NULL,
          email        TEXT NOT NULL UNIQUE,
          auth_method  TEXT NOT NULL CHECK (auth_method IN ('sso_mfa','mfa_only')),
          token_hash   TEXT UNIQUE,
          status       TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active','suspended')),
          created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          suspended_at TIMESTAMPTZ,
          suspended_by UUID,

          CONSTRAINT suspension_names_who CHECK (
            status <> 'suspended' OR (suspended_at IS NOT NULL AND suspended_by IS NOT NULL)
          )
        )
    """)
    op.execute("""
        COMMENT ON COLUMN office_human.token_hash IS
        'A hash, never a token. Same rule as forge_tenant_credential.credential_ref: '
        'the column proves possession without being the thing possessed.'
    """)
    op.execute("""
        COMMENT ON COLUMN office_human.auth_method IS
        'Part 14 declares sso_mfa | mfa_only. Recorded as intent; the API currently '
        'authenticates a bearer token because real SSO is an external provider that '
        'does not exist yet. ASSUMPTION, see docs/plans/console-api-PLAN.md.'
    """)

    op.execute("""
        CREATE TABLE office_human_role (
          human_id   UUID NOT NULL REFERENCES office_human ON DELETE CASCADE,
          role       TEXT NOT NULL CHECK (role IN
                       ('venture_operator','compliance_officer','ivan')),
          venture_id TEXT,
          granted_by UUID NOT NULL,
          granted_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # COALESCE in the key so "all ventures" is one row, not a row per venture that
    # someone has to remember to add when a venture is created.
    op.execute("""
        CREATE UNIQUE INDEX ux_human_role ON office_human_role
          (human_id, role, COALESCE(venture_id, '*'))
    """)
    op.execute("""
        COMMENT ON COLUMN office_human_role.venture_id IS
        'NULL means every venture, which is what Ivan holds. A venture operator is an '
        'operator OF A VENTURE - scoping the role here is what stops one revoking in a '
        'venture they have nothing to do with.'
    """)

    op.execute("""
        CREATE TABLE signoff_record (
          signoff_id     UUID PRIMARY KEY,
          gate           TEXT NOT NULL,
          venture_id     TEXT NOT NULL,
          human_id       UUID NOT NULL REFERENCES office_human,
          role_signed_as TEXT NOT NULL,
          artifact_hash  TEXT NOT NULL,
          artifact_kind  TEXT NOT NULL,
          signed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          note           TEXT
        )
    """)
    op.execute("""
        COMMENT ON COLUMN signoff_record.artifact_hash IS
        'Part 14: artifact change voids signature. The hash is what was signed, so the '
        'signature is void by comparison rather than by somebody remembering to revoke '
        'it - the same principle that makes certification staleness reliable.'
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_signoff_gate ON signoff_record (venture_id, gate, human_id)
    """)
    op.execute("CREATE INDEX ix_signoff_venture ON signoff_record (venture_id, gate)")

    for table in ("office_human", "office_human_role", "signoff_record"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO office_app")
    # A sign-off is evidence. Deleting one would make an unsigned gate indistinguishable
    # from a gate whose signature was removed.
    op.execute("REVOKE DELETE ON signoff_record FROM office_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS signoff_record CASCADE")
    op.execute("DROP TABLE IF EXISTS office_human_role CASCADE")
    op.execute("DROP TABLE IF EXISTS office_human CASCADE")
