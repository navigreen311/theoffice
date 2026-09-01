"""A module that must never be granted, recorded before the Forge is onboarded.

WHY THIS TABLE HAS NO FOREIGN KEY
=================================

    `forge_module_registry.forge_id` references `forge_registry`, so a module row
    cannot exist before its Forge is registered. That is exactly the wrong moment.
    An exclusion recorded after the registry rows are written is a reaction; one
    recorded before is a prevention, and the whole value is in preventing.

    So `forge_module_exclusion` references nothing. It is a finding about a
    codebase - "this endpoint returns 200 and does no work" - and a finding does
    not become true when somebody gets around to registering the Forge.

WHAT IT IS FOR
==============

    Onboarding CapitalForge found three shapes of endpoint that answer plausibly
    and do nothing:

      - `POST /api/platform/workflows` persists a rule no runner consumes. The
        platform's own GET says so: `execution: {runs: false}`.
      - The VoiceForge call endpoints dial nobody. The service uses a
        `TwilioStubClient` declared inside itself; the production Twilio client
        is imported only by the SMS path, which is live.
      - Ten endpoints answer 501 by design.

    An agent granted one of these gets a 200, a ledger row, and no work done.
    The ledger would then be evidence that something happened. It did not.

WHY A TRIGGER AND NOT A CHECK
=============================

    A CHECK constraint cannot see another table. Two production paths INSERT
    grants - `generators/runtime_config.py` at the end of the provisioning ladder
    and `broker/bootstrap_phase0.py` - and a guard that each of them has to
    remember to call is a guard that one of them will eventually not call.

    BEFORE INSERT ONLY. Revoking a grant is an UPDATE of `revoked_at`, and a
    grant for an excluded module must stay revokable - if the trigger fired on
    UPDATE, discovering an excluded grant would leave it permanently unrevokable,
    which is the opposite of what this is for.

Revision ID: 0030
Revises: 0029
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE forge_module_exclusion (
          forge_id     TEXT NOT NULL,
          module_id    TEXT NOT NULL,
          reason       TEXT NOT NULL,
          evidence     TEXT NOT NULL,
          recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          recorded_by  TEXT NOT NULL,
          PRIMARY KEY (forge_id, module_id)
        )
    """)
    op.execute("""
        COMMENT ON TABLE forge_module_exclusion IS
        'Modules that must never be granted to any agent. Deliberately has no FK to '
        'forge_registry: an exclusion must be recordable BEFORE a Forge is onboarded, '
        'which is the only moment at which it prevents rather than reacts.'
    """)
    op.execute("""
        COMMENT ON COLUMN forge_module_exclusion.evidence IS
        'Where the finding lives - file and symbol in the Forge codebase. An exclusion '
        'nobody can re-verify becomes folklore the first time somebody doubts it.'
    """)

    op.execute("""
        CREATE FUNCTION forge_module_exclusion_guard()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        DECLARE
          v_reason TEXT;
        BEGIN
          SELECT reason INTO v_reason
            FROM forge_module_exclusion
           WHERE forge_id = NEW.forge_id
             AND module_id = NEW.module_id;

          IF FOUND THEN
            RAISE EXCEPTION
              'module % on forge % is excluded and cannot be granted: %',
              NEW.module_id, NEW.forge_id, v_reason
              USING ERRCODE = 'integrity_constraint_violation',
                    HINT = 'This module answers without doing the work. Remove the row '
                           'from forge_module_exclusion only with the evidence that it '
                           'no longer applies.';
          END IF;

          RETURN NEW;
        END $$
    """)

    # INSERT only. See the header: revocation is an UPDATE and must stay possible.
    op.execute("""
        CREATE TRIGGER agent_forge_grant_exclusion_guard
          BEFORE INSERT ON agent_forge_grant
          FOR EACH ROW EXECUTE FUNCTION forge_module_exclusion_guard()
    """)

    # The runtime role reads exclusions (resolve_grant reports the reason) and never
    # writes them. Recording an exclusion is a deliberate act performed by the seeder
    # as admin, not something the broker does to itself mid-call.
    op.execute("GRANT SELECT ON forge_module_exclusion TO office_app")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS agent_forge_grant_exclusion_guard ON agent_forge_grant")
    op.execute("DROP FUNCTION IF EXISTS forge_module_exclusion_guard()")
    op.execute("DROP TABLE IF EXISTS forge_module_exclusion")
