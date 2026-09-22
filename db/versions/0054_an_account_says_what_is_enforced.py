"""An account says what is enforced

Revision ID: 0054
Revises: 0053

Ruled 21 September 2026 (Ivan Green):

    *"An account's `auth_method` says what is enforced. Measured: Ira reads `sso_mfa`
    with `mfa_enrolled_at` NULL, and nothing reads the column."*

WHAT EVERY ACCOUNT CLAIMED
==========================

    Measured on the development database before this migration:

        auth_method  mfa enrolled  origin        count
        sso_mfa      NO            human             2
        sso_mfa      NO            test_fixture    240

    **All 242. Not one enrolment, ever.** `auth_method` has had exactly two permitted
    values since 0010 - `sso_mfa` and `mfa_only` - and both of them assert a second
    factor. There has never been a way for an account to say the true thing.

    0025 saw this coming and wrote it on the column it added:

        'When a second factor was actually enrolled. Deliberately separate from
        auth_method, which every account claims by default and nothing verifies: a
        signer whose MFA is a claim rather than an enrolment weakens the
        non-repudiation the Gate 10 signature is meant to carry.'

    That was correct and it was a comment. `mfa_enrolled_at` has **no writer anywhere in
    this repository** - it is read by the Access page, the roster query and the console,
    and set by nothing - so the separation 0025 created recorded the problem without
    being able to fix it.

WHAT THIS CHANGES, AND WHAT IT DELIBERATELY DOES NOT
====================================================

    **It does not build MFA.** There is no second factor in this system to enrol: the
    credential is a bearer token The Office issues and hashes, and no IdP, TOTP or
    WebAuthn path exists. Writing a timestamp into `mfa_enrolled_at` to make the
    constraint pass would be the same defect one level down - a column claiming an
    enforcement nobody performs - and the question of what enrolment would even MEAN for
    a token-authenticated account is left open in the ledger rather than answered here.

    **It stops the column lying.** `bearer_token` is added as a value an account can
    honestly hold, every account that has not enrolled is moved to it, and a CHECK makes
    `sso_mfa` and `mfa_only` unstateable without an enrolment date beside them.

    After this migration `auth_method` is a fact: it names the strongest thing that is
    actually enforced for that account. The Access page's existing amber "no MFA" marker
    becomes a statement about a specific account rather than about all of them.

WHY A CHECK RATHER THAN A CONVENTION
====================================

    A convention is what `sso_mfa` already was. `create_human` defaulted to it, the Pack
    template writes it, and 242 rows inherited a claim nobody made deliberately. The
    constraint is the only version of this that a future default cannot quietly undo.
"""
from __future__ import annotations

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. A VALUE AN ACCOUNT CAN HONESTLY HOLD. Dropped and recreated rather than
    #    altered: a CHECK is not alterable in place, and naming the replacement after
    #    what it now permits beats keeping a name that describes the old set.
    op.execute("ALTER TABLE office_human DROP CONSTRAINT office_human_auth_method_check")
    op.execute("""
        ALTER TABLE office_human ADD CONSTRAINT auth_method_is_one_of_three CHECK (
          auth_method IN ('bearer_token', 'sso_mfa', 'mfa_only')
        )
    """)

    # 2. EVERY ACCOUNT THAT HAS NOT ENROLLED NOW SAYS SO. On the development database
    #    that is all 242 of them, which is the measurement this migration exists for.
    #    Keyed on the enrolment column rather than on a list of accounts, so it stays
    #    correct on a database with a different population.
    op.execute("""
        UPDATE office_human
           SET auth_method = 'bearer_token'
         WHERE mfa_enrolled_at IS NULL
           AND auth_method IN ('sso_mfa', 'mfa_only')
    """)

    # 3. AND IT CANNOT BE CLAIMED AGAIN WITHOUT THE EVIDENCE. This is the part a default
    #    cannot undo: a row asserting `sso_mfa` must carry the date a second factor was
    #    actually enrolled.
    op.execute("""
        ALTER TABLE office_human ADD CONSTRAINT mfa_is_claimed_only_when_enrolled CHECK (
          auth_method = 'bearer_token' OR mfa_enrolled_at IS NOT NULL
        )
    """)

    op.execute("""
        COMMENT ON COLUMN office_human.auth_method IS
        'What is actually enforced for this account, not what it aspires to (ruled 21 '
        'September 2026, entry 154). bearer_token is the honest default: the credential '
        'is a token The Office issued and hashed, and there is no second factor. '
        'sso_mfa and mfa_only require mfa_enrolled_at beside them - measured before '
        'this migration, all 242 accounts claimed sso_mfa and none had ever enrolled.'
    """)


def downgrade() -> None:
    # The constraints go and the old two-value CHECK comes back. The VALUES do not: an
    # account moved to `bearer_token` was moved because it had never enrolled, and
    # writing `sso_mfa` back onto it would restore the claim this migration exists to
    # remove. A downgrade that reinstates a false statement about a credential is worse
    # than one that leaves a column more honest than it found it.
    op.execute(
        "ALTER TABLE office_human DROP CONSTRAINT IF EXISTS mfa_is_claimed_only_when_enrolled"
    )
    op.execute(
        "ALTER TABLE office_human DROP CONSTRAINT IF EXISTS auth_method_is_one_of_three"
    )
    op.execute("""
        ALTER TABLE office_human ADD CONSTRAINT office_human_auth_method_check CHECK (
          auth_method IN ('bearer_token', 'sso_mfa', 'mfa_only')
        )
    """)
