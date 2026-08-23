"""Forge Operating Instructions and the two certification units.

Blueprint Phase 2. Before this, the certification gate was a non-null check on a
free-text column - any string satisfied it. Nothing bound a certification to what the
agent was actually taught, so rewriting a module's instructions left every
certification against the old text silently valid.

Two things make that impossible now:

  * instruction content is hashed IN THE DATABASE, so a caller cannot supply a hash
    that disagrees with its content;
  * a certification stores the hash and Forge api_version it was tested against, so
    staleness is a comparison rather than a flag somebody has to remember to set.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Part 6.1. Instructions are curriculum, not a filing cabinet - and a curriculum
# missing its failure signatures is a document that reads fine and teaches nothing
# about the case that matters.
REQUIRED_SECTIONS = (
    "what_it_does",
    "what_it_does_not_do",
    "inputs",
    "correct_sequence",
    "failure_signatures",
    "retry_vs_escalate",
    "never_do",
    "compliance_coupling",
)


def upgrade() -> None:
    sections_check = " AND ".join(f"content ? '{s}'" for s in REQUIRED_SECTIONS)

    op.execute(f"""
        CREATE TABLE forge_operating_instruction (
          forge_id             TEXT NOT NULL,
          module_id            TEXT NOT NULL,
          instruction_version  TEXT NOT NULL,
          forge_api_version    TEXT NOT NULL,
          version_sensitivity  TEXT NOT NULL DEFAULT 'major.minor'
                                 CHECK (version_sensitivity IN
                                   ('major','major.minor','major.minor.patch')),
          sensitivity_rationale TEXT,
          content              JSONB NOT NULL,
          content_hash         TEXT NOT NULL,
          authored_by          UUID NOT NULL,
          authored_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
          superseded_at        TIMESTAMPTZ,

          PRIMARY KEY (forge_id, module_id, instruction_version),
          FOREIGN KEY (forge_id, module_id) REFERENCES forge_module_registry,

          CONSTRAINT instruction_has_all_sections CHECK ({sections_check}),

          -- Declaring patch-level sensitivity decertifies every agent on this module
          -- at every patch release. Sometimes right, always expensive, never accidental.
          CONSTRAINT patch_sensitivity_needs_a_rationale CHECK (
            version_sensitivity <> 'major.minor.patch'
            OR (sensitivity_rationale IS NOT NULL AND length(trim(sensitivity_rationale)) > 0)
          )
        )
    """)
    op.execute("""
        COMMENT ON TABLE forge_operating_instruction IS
        'Part 6.1: elevated from filing cabinet to curriculum. This is what agents are '
        'educated on and what SimForge tests against. content_hash binds certification.'
    """)
    op.execute("""
        COMMENT ON CONSTRAINT instruction_has_all_sections ON forge_operating_instruction IS
        'All eight Part 6.1 sections are required. A constraint rather than a convention.'
    """)

    # Exactly one live instruction set per module. Two would make "the current
    # content_hash" ambiguous, and staleness is defined by comparison against it.
    op.execute("""
        CREATE UNIQUE INDEX ux_instruction_live ON forge_operating_instruction
          (forge_id, module_id) WHERE superseded_at IS NULL
    """)

    # Hash computed here, not accepted from the caller. A supplied hash is a claim;
    # this is a fact.
    op.execute("""
        CREATE FUNCTION instruction_hash(p_content JSONB) RETURNS TEXT
        LANGUAGE sql IMMUTABLE AS $$
          SELECT encode(sha256(convert_to(p_content::text, 'UTF8')), 'hex')
        $$
    """)
    op.execute("""
        COMMENT ON FUNCTION instruction_hash(JSONB) IS
        'jsonb text output is key-sorted and duplicate-free, so logically identical '
        'content always hashes identically regardless of how it was written.'
    """)
    op.execute("""
        CREATE FUNCTION set_instruction_hash() RETURNS TRIGGER
        LANGUAGE plpgsql AS $$
        BEGIN
          NEW.content_hash := instruction_hash(NEW.content);
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER forge_operating_instruction_hash
          BEFORE INSERT OR UPDATE ON forge_operating_instruction
          FOR EACH ROW EXECUTE FUNCTION set_instruction_hash()
    """)

    # ------------------------------------------------------------- CERTIFICATION
    op.execute("""
        CREATE TABLE certification (
          cert_id                  UUID PRIMARY KEY,
          unit                     TEXT NOT NULL CHECK (unit IN ('A','B')),
          office_agent_id          UUID REFERENCES office_agent_identity,
          department               TEXT,
          forge_id                 TEXT NOT NULL,
          module_id                TEXT,
          state                    TEXT NOT NULL CHECK (state IN (
                                     'certified','stale_instructions','stale_forge',
                                     'in_training','never_certified','failed','revoked')),
          certified_tier           TEXT CHECK (certified_tier IN
                                     ('auto_execute','propose','suggest')),
          instruction_content_hash TEXT,
          forge_api_version        TEXT,
          rubric_kind              TEXT NOT NULL CHECK (rubric_kind IN ('operation','domain')),
          rubric_version           TEXT NOT NULL,
          score                    NUMERIC(6,3),
          threshold                NUMERIC(6,3),
          scenario_pack_ref        TEXT,
          simforge_verdict         TEXT,
          issued_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

          -- Unit A is agent x forge x module. Unit B is department x forge x context.
          CONSTRAINT unit_targets_match CHECK (
            CASE unit
              WHEN 'A' THEN office_agent_id IS NOT NULL AND module_id IS NOT NULL
              WHEN 'B' THEN department IS NOT NULL
            END
          ),

          -- Part 10.1: two rubrics, never merged. Pairing them here means a composite
          -- score cannot be written at all, rather than being discouraged in review.
          CONSTRAINT rubric_matches_unit CHECK (
            (unit = 'A' AND rubric_kind = 'operation')
            OR (unit = 'B' AND rubric_kind = 'domain')
          ),

          -- A certified cert must say what it was tested against, or staleness is
          -- uncomputable and the certification is permanent by accident.
          CONSTRAINT certified_records_its_basis CHECK (
            state <> 'certified'
            OR (instruction_content_hash IS NOT NULL
                AND forge_api_version IS NOT NULL
                AND certified_tier IS NOT NULL)
          )
        )
    """)
    op.execute("""
        COMMENT ON TABLE certification IS
        'Two units, both required for assignment. Unit A: agent x forge x module '
        '(operation competence). Unit B: department x forge x context (judgment). '
        'Department certification is necessary, never sufficient.'
    """)
    op.execute("""
        COMMENT ON COLUMN certification.certified_tier IS
        'Part 10.1: certified tier caps declared tier. The Pack declares a ceiling; '
        'SimForge sets the actual. Applied live in the call path, not at issuance.'
    """)

    op.execute("""
        CREATE UNIQUE INDEX ux_cert_unit_a ON certification
          (office_agent_id, forge_id, module_id) WHERE unit = 'A'
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_cert_unit_b ON certification
          (department, forge_id) WHERE unit = 'B'
    """)
    op.execute("CREATE INDEX ix_cert_state ON certification (state, forge_id, module_id)")

    # ------------------------------------------------- CURRICULUM SUBMISSION
    # The Office authors scenario content and hands it over. It records that it did so
    # and what came back. It records NOTHING about held-out scenarios, because there is
    # no read path to build - only one never to build.
    op.execute("""
        CREATE TABLE curriculum_submission (
          submission_id     UUID PRIMARY KEY,
          venture_id        TEXT NOT NULL,
          forge_id          TEXT NOT NULL,
          module_id         TEXT,
          department        TEXT,
          scenario_pack_ref TEXT NOT NULL,
          scenario_count    INT NOT NULL CHECK (scenario_count > 0),
          coverage_denominator INT NOT NULL CHECK (coverage_denominator > 0),
          instruction_content_hash TEXT NOT NULL,
          submitted_by      UUID NOT NULL,
          submitted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          simforge_run_ref  TEXT,
          result_received_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        COMMENT ON TABLE curriculum_submission IS
        'What The Office sent to SimForge and what came back. Deliberately holds no '
        'scenario bodies and no held-out content: The Office may not read the held-out '
        'set, and the obligation is structural, not procedural.'
    """)
    op.execute("""
        COMMENT ON COLUMN curriculum_submission.coverage_denominator IS
        '"Report the denominator." A scenario count without one is not coverage.'
    """)

    for table in ("forge_operating_instruction", "certification", "curriculum_submission"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO office_app")
    op.execute("GRANT EXECUTE ON FUNCTION instruction_hash(JSONB) TO office_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS curriculum_submission CASCADE")
    op.execute("DROP TABLE IF EXISTS certification CASCADE")
    op.execute(
        "DROP TRIGGER IF EXISTS forge_operating_instruction_hash "
        "ON forge_operating_instruction"
    )
    op.execute("DROP TABLE IF EXISTS forge_operating_instruction CASCADE")
    op.execute("DROP FUNCTION IF EXISTS set_instruction_hash()")
    op.execute("DROP FUNCTION IF EXISTS instruction_hash(JSONB)")
