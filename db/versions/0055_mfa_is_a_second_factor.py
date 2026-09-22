"""MFA is a second factor the person enrols themselves

Revision ID: 0055
Revises: 0054

Ruled 21 September 2026 (Ivan Green):

    *"MFA means a TOTP second factor the person enrols themselves. `attest`, `sign_off`
    and `revoke` refuse without a verified code. Only the person writes their own
    enrolment. Measured: 242 of 242 accounts claimed `sso_mfa`, zero enrolments."*

WHAT 0054 COULD NOT DO
======================

    0054 made `auth_method` honest: `bearer_token` for every account that had not
    enrolled, and a CHECK stopping `sso_mfa` being claimed without an enrolment date.
    What it could not do was let anybody enrol, because there was no second factor in
    the system to enrol - and entry 154 recorded that as a question rather than filling
    `mfa_enrolled_at` with a timestamp nobody had earned.

    This is the answer. A TOTP secret is a thing The Office cannot derive from the
    bearer token it issued, so a code produced from it is evidence about the person
    rather than about the credential.

TWO COLUMNS AND A TABLE
=======================

    `mfa_secret`      the shared secret, base32. Nullable: most accounts have none.
    `mfa_enrolled_at` already existed since 0025, and finally means something - it is
                      set only after a code has verified against the secret.
    `mfa_code_used`   which (person, 30-second step) pairs have been spent.

WHY A USED-CODE TABLE AND NOT A COLUMN
======================================

    A code is valid for its whole 30-second step, and TOTP is stateless, so the same six
    digits authorise every act inside that window. Two signatures taken with one code are
    one act, and the second is one nobody typed a code for - which is precisely the
    non-repudiation the second factor exists to provide.

    So the pair is recorded and refused afterwards. **The code itself is never stored**:
    it is a credential, and a table of live credentials is worse than the problem. The
    step number identifies the window without being usable in it.

    The PRIMARY KEY is the control. Two concurrent acts race on the insert and exactly
    one wins; a read-then-write would have the race this table exists to remove.

`auth_method` FOLLOWS THE ENROLMENT RATHER THAN LEADING IT
==========================================================

    `confirm_enrolment` sets `auth_method = 'mfa_only'` in the same statement as
    `mfa_enrolled_at`, and `begin_enrolment` puts both back. That keeps 0054's CHECK
    true by construction rather than by remembering, and it means the column continues
    to describe what is enforced - which is the whole of entry 154.
"""
from __future__ import annotations

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE office_human ADD COLUMN mfa_secret TEXT")
    op.execute("""
        COMMENT ON COLUMN office_human.mfa_secret IS
        'The base32 TOTP secret, RFC 6238. Returned to the person exactly once when they '
        'begin enrolment and never again - the same rule token_hash follows. NULL for an '
        'account that has never begun. Ruled 21 September 2026, entry 155.'
    """)

    # AN ENROLMENT NAMES A SECRET. Without this, `mfa_enrolled_at` could be set on a row
    # with nothing to verify against, which is the 242-of-242 state one column over.
    op.execute("""
        ALTER TABLE office_human ADD CONSTRAINT an_enrolment_has_a_secret CHECK (
          mfa_enrolled_at IS NULL OR mfa_secret IS NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE mfa_code_used (
          human_id  UUID NOT NULL REFERENCES office_human(human_id) ON DELETE CASCADE,
          step      BIGINT NOT NULL,
          used_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (human_id, step)
        )
    """)
    op.execute("""
        COMMENT ON TABLE mfa_code_used IS
        'Which (person, 30-second TOTP step) pairs have been spent, so one code cannot '
        'authorise two acts. The code is NOT stored - it is a live credential, and the '
        'step identifies the window without being usable in it. Entry 155.'
    """)
    op.execute("GRANT SELECT, INSERT, DELETE ON mfa_code_used TO office_app")

    # Old rows are of no use: a step is 30 seconds, so anything from a previous day can
    # never be replayed. An index over `used_at` so a sweep can prune without a scan.
    op.execute("CREATE INDEX ix_mfa_code_used_at ON mfa_code_used (used_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mfa_code_used")
    op.execute(
        "ALTER TABLE office_human DROP CONSTRAINT IF EXISTS an_enrolment_has_a_secret"
    )
    # The enrolments go with the secret, because an enrolment whose secret is gone is a
    # claim again - and restoring the exact state entries 154 and 155 removed is not
    # something a downgrade should quietly do. `auth_method` follows them back.
    op.execute("""
        UPDATE office_human
           SET mfa_enrolled_at = NULL, auth_method = 'bearer_token'
         WHERE mfa_secret IS NOT NULL
    """)
    op.execute("ALTER TABLE office_human DROP COLUMN IF EXISTS mfa_secret")
