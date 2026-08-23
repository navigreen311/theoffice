"""Governance schema: revocation scopes, manifest, incidents, proposals, limits, budget.

Blueprint Phase 1. Phase 0 built the path; everything on it was permissive. These
tables are what turn recorded guardrails into enforced ones.

Blueprint gap corrected here: Part 12 mandates a per-task USD ceiling, and the Pack
schema marks `per_task_usd_ceiling` required - but `agent_call_ledger` in blueprint §2
carries no task identifier. `idempotency_key` is a one-way hash of
(task_id, module_id, payload) and cannot be grouped by task, so per-task spend is not
computable as specified. `task_id` is added below. The blueprint should be amended.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS_APPEND_ONLY = ("incident",)
GRANTS_FULL = (
    "revocation",
    "venture_forge_manifest",
    "proposal",
    "rate_limit_bucket",
    "venture_budget",
)


def upgrade() -> None:
    # ------------------------------------------------------------ LEDGER: task_id
    op.execute("ALTER TABLE agent_call_ledger ADD COLUMN task_id TEXT")
    op.execute("""
        COMMENT ON COLUMN agent_call_ledger.task_id IS
        'Added beyond blueprint section 2. Part 12 requires a per-task USD ceiling, '
        'which is not computable from idempotency_key (a one-way hash).'
    """)
    op.execute("""
        CREATE INDEX ix_ledger_task_cost ON agent_call_ledger (venture_id, task_id, ts_start)
    """)
    op.execute("""
        CREATE INDEX ix_ledger_agent_cost ON agent_call_ledger (office_agent_id, ts_start)
          WHERE usd_cost IS NOT NULL
    """)

    # ------------------------------------------------------------------ REVOCATION
    # A separate table rather than more nullable columns on agent_forge_grant: a
    # Forge-wide revocation is not a property of any one grant, and a venture-wide
    # one must apply to grants issued AFTER it was declared.
    op.execute("""
        CREATE TABLE revocation (
          revocation_id        UUID PRIMARY KEY,
          scope                TEXT NOT NULL CHECK (scope IN
                                 ('agent_module','agent','venture','forge')),
          office_agent_id      UUID REFERENCES office_agent_identity,
          forge_id             TEXT,
          module_id            TEXT,
          venture_id           TEXT,
          reason               TEXT NOT NULL,
          revoked_by           UUID NOT NULL,
          revoked_by_role      TEXT NOT NULL CHECK (revoked_by_role IN
                                 ('venture_operator','compliance_officer','ivan')),
          revoked_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
          reinstated_at        TIMESTAMPTZ,
          reinstated_by        UUID,
          reinstatement_reason TEXT,

          CONSTRAINT scope_targets_match CHECK (
            CASE scope
              WHEN 'agent_module' THEN
                office_agent_id IS NOT NULL AND forge_id IS NOT NULL
                AND module_id IS NOT NULL
              WHEN 'agent'   THEN office_agent_id IS NOT NULL
              WHEN 'venture' THEN venture_id IS NOT NULL
              WHEN 'forge'   THEN forge_id IS NOT NULL
            END
          ),

          -- Master prompt 1.4: "re-enable requires a documented ritual and a named
          -- human". A reinstatement with neither is not a ritual, it is an UPDATE.
          CONSTRAINT reinstatement_is_documented CHECK (
            reinstated_at IS NULL
            OR (reinstated_by IS NOT NULL AND reinstatement_reason IS NOT NULL)
          )
        )
    """)
    op.execute("""
        COMMENT ON TABLE revocation IS
        'The kill switch, at four scopes. Checked live on every call, never cached.'
    """)
    op.execute("""
        CREATE INDEX ix_revocation_active ON revocation
          (scope, office_agent_id, forge_id, module_id, venture_id)
          WHERE reinstated_at IS NULL
    """)

    # ------------------------------------------------------------------- MANIFEST
    op.execute("""
        CREATE TABLE venture_forge_manifest (
          venture_id     TEXT NOT NULL,
          forge_id       TEXT NOT NULL,
          module_id      TEXT NOT NULL,
          is_required    BOOLEAN NOT NULL DEFAULT FALSE,
          criticality    TEXT NOT NULL DEFAULT 'soft'
                           CHECK (criticality IN ('hard','soft')),
          module_gap     BOOLEAN NOT NULL DEFAULT FALSE,
          declared_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (venture_id, forge_id, module_id),
          FOREIGN KEY (forge_id, module_id) REFERENCES forge_module_registry,

          -- Validator V8 / generator 5.6: a hard dependency on a module that does
          -- not exist cannot provision. Enforced here so it cannot be inserted at
          -- all, rather than only caught by the Pack validator.
          CONSTRAINT hard_dependency_cannot_be_a_gap CHECK (
            NOT (criticality = 'hard' AND module_gap)
          )
        )
    """)
    op.execute("""
        COMMENT ON TABLE venture_forge_manifest IS
        'The venture Bill of Materials. Declared = a row exists. Required = is_required. '
        'In-Use is read from agent_call_ledger. Three states, reconciled.'
    """)

    # ------------------------------------------------------------------ INCIDENTS
    op.execute("""
        CREATE TABLE incident (
          incident_id     UUID PRIMARY KEY,
          severity        TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
          kind            TEXT NOT NULL,
          venture_id      TEXT,
          office_agent_id UUID,
          forge_id        TEXT,
          module_id       TEXT,
          trace_id        UUID,
          detail          JSONB NOT NULL DEFAULT '{}',
          raised_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        COMMENT ON TABLE incident IS
        'Append-only. Incidents are detections, not workflow - triage, containment and '
        'disclosure live in the console (Part 9). An incident is never edited; a '
        'later finding is a new incident referencing the trace.'
    """)
    op.execute("CREATE INDEX ix_incident_open ON incident (severity, raised_at DESC)")
    op.execute("CREATE INDEX ix_incident_venture ON incident (venture_id, raised_at DESC)")

    # ------------------------------------------------------------------ PROPOSALS
    op.execute("""
        CREATE TABLE proposal (
          proposal_id      UUID PRIMARY KEY,
          office_agent_id  UUID NOT NULL REFERENCES office_agent_identity,
          venture_id       TEXT NOT NULL,
          forge_id         TEXT NOT NULL,
          module_id        TEXT NOT NULL,
          task_id          TEXT NOT NULL,
          trust_tier       TEXT NOT NULL CHECK (trust_tier IN ('propose','suggest')),
          payload          JSONB NOT NULL,
          payload_hash     TEXT NOT NULL,
          idempotency_key  TEXT NOT NULL,
          trace_id         UUID NOT NULL,
          status           TEXT NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending','approved','rejected',
                                              'expired','executed')),
          created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
          decided_at       TIMESTAMPTZ,
          decided_by       UUID,
          decision_reason  TEXT,
          review_seconds   NUMERIC(10,3),
          executed_call_id UUID,

          CONSTRAINT decision_names_a_human CHECK (
            status IN ('pending','expired')
            OR (decided_at IS NOT NULL AND decided_by IS NOT NULL)
          )
        )
    """)
    op.execute("""
        COMMENT ON COLUMN proposal.payload IS
        'Stored because a proposal a human cannot inspect is not a proposal. This '
        'column inherits the venture retention and PHI obligations - see docs/governance.md.'
    """)
    op.execute("""
        COMMENT ON COLUMN proposal.review_seconds IS
        'Part 14 rubber-stamp detection: sub-5-second approval clusters raise a '
        'governance flag.'
    """)
    op.execute("""
        CREATE INDEX ix_proposal_pending ON proposal (venture_id, created_at)
          WHERE status = 'pending'
    """)
    op.execute("CREATE INDEX ix_proposal_reviewer ON proposal (decided_by, decided_at DESC)")

    # ---------------------------------------------------------------- RATE LIMITS
    # Token bucket in Postgres. No second datastore: the blueprint puts the queue on
    # Postgres at v1, and a counter store would be the same dependency renamed.
    op.execute("""
        CREATE TABLE rate_limit_bucket (
          bucket_key        TEXT PRIMARY KEY,
          tokens            NUMERIC(12,4) NOT NULL,
          max_tokens        NUMERIC(12,4) NOT NULL CHECK (max_tokens > 0),
          refill_per_second NUMERIC(12,4) NOT NULL CHECK (refill_per_second > 0),
          last_refill       TIMESTAMPTZ NOT NULL DEFAULT now(),
          throttle_factor   NUMERIC(6,4) NOT NULL DEFAULT 1.0
                              CHECK (throttle_factor > 0 AND throttle_factor <= 1),
          throttled_until   TIMESTAMPTZ,
          CONSTRAINT tokens_within_bucket CHECK (tokens >= 0 AND tokens <= max_tokens)
        )
    """)
    op.execute("""
        COMMENT ON TABLE rate_limit_bucket IS
        'Token bucket. Accessed under SELECT ... FOR UPDATE, which requires READ '
        'COMMITTED - under REPEATABLE READ the post-lock re-read raises a '
        'serialization failure. Same constraint as the audit chain.'
    """)

    # ------------------------------------------------------------------- BUDGET
    op.execute("""
        CREATE TABLE venture_budget (
          venture_id             TEXT PRIMARY KEY,
          monthly_usd_cap        NUMERIC(12,2) NOT NULL CHECK (monthly_usd_cap > 0),
          soft_cap_pct           INT NOT NULL DEFAULT 80
                                   CHECK (soft_cap_pct > 0 AND soft_cap_pct < 100),
          hard_cap_action        TEXT NOT NULL DEFAULT 'pause'
                                   CHECK (hard_cap_action IN ('pause','throttle')),
          per_agent_usd_daily_cap NUMERIC(12,2) NOT NULL CHECK (per_agent_usd_daily_cap > 0),
          per_task_usd_ceiling   NUMERIC(12,2) NOT NULL CHECK (per_task_usd_ceiling > 0),
          hard_cap_reversed_by   UUID,
          hard_cap_reversed_at   TIMESTAMPTZ,
          CONSTRAINT soft_cap_below_hard_cap CHECK (soft_cap_pct < 100)
        )
    """)
    op.execute("""
        COMMENT ON COLUMN venture_budget.hard_cap_reversed_by IS
        'Part 12: hard-cap reversal is Ivan-only. Authority is checked in the '
        'application; this column records who did it.'
    """)

    # --------------------------------------------------------------------- GRANTS
    for table in GRANTS_FULL:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO office_app")
    for table in GRANTS_APPEND_ONLY:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO office_app")
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM office_app")


def downgrade() -> None:
    for table in (*GRANTS_FULL, *GRANTS_APPEND_ONLY):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP INDEX IF EXISTS ix_ledger_task_cost")
    op.execute("DROP INDEX IF EXISTS ix_ledger_agent_cost")
    op.execute("ALTER TABLE agent_call_ledger DROP COLUMN IF EXISTS task_id")
