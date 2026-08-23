# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Phase 0.1 — core schema, append-only ledger, tamper-evident hash chain.**
  - Blueprint §2 tables: `office_agent_identity`, `forge_registry`,
    `forge_module_registry`, `forge_tenant_credential`, `agent_forge_grant`,
    `shift_assignment`, `agent_call_ledger` (RANGE-partitioned), `audit_log`.
  - Append-only enforcement on both ledger tables: role grants as the control,
    guard triggers as defense in depth.
  - `audit_log` hash chain with `audit_log_verify_chain()`, detecting content
    tampering, link tampering, mid-chain deletion, and tail truncation.
  - `ensure_ledger_partition()` — idempotent monthly partition provisioning that
    grants append-only privileges on each new partition.
  - Structural invariant enforcement: `is_assignable` generated column
    (certification gates grants); `no_overlapping_shifts_per_agent` exclusion
    constraint (one venture per agent per shift); `break_glass_min_two`;
    `api_version_pinned`; `revocation_is_complete`.
  - `scripts/bootstrap.sh` — idempotent end-to-end local setup.
  - 42 tests across schema, append-only, and hash-chain suites.
- AI development setup: `CLAUDE.md`, `PROJECT_RULEBOOK.md`, five commands.

- **Phase 0.4 + 0.5 — identity broker and client library.** The bridge's call path.
  - `broker/grants.py` — authorization resolved live on every call. One query checks
    identity status, grant existence, revocation, and both certification units.
    No cache, by design: this query is the kill switch.
  - `broker/credentials.py` — `CredentialResolver` protocol with an env-backed dev
    implementation. `Credential` prints redacted; `.reveal()` is the only way out.
    The Vault backend raises rather than silently falling back.
  - `broker/executor.py` — presents the Forge's tenant credential and stamps
    `X-Office-Agent-Id`, `X-Office-Venture`, `X-Office-Trace`, `Idempotency-Key`.
  - `broker/audit.py`, `broker/ledger.py` — pre-call intent entry, post-call outcome
    row, derived idempotency keys, payload hashing.
  - `broker/errors.py` — a named refusal type per failure mode, each carrying the
    audit event it writes.
  - `client/office_client.py` — the mandatory call path in seven ordered steps.
  - Fail-closed audit on compliance-flagged actions; degrade otherwise.
  - `at_most_once` modules escalate to a human instead of auto-retrying.
  - Nothing names a Forge: base URL, API version, auth model, credential mode and
    idempotency class are all registry rows.
  - 20 contract tests against an in-process stub Forge. 62 tests total.
  - `ruff` and strict `mypy` wired into `bootstrap.sh` as gates.

- **Phase 1 — governance in the path.** Every guardrail Phase 0 recorded is now enforced.
  - **Four revocation scopes** (`agent_module` | `agent` | `venture` | `forge`), each
    with a required authority, checked live on every call. A separate table, so a
    venture-wide stop covers grants issued after it. Reinstatement requires the same
    authority plus a named human and a documented reason.
  - **Forge Manifest reconciliation.** `required` proceeds; `declared_only` proceeds
    with a HIGH `in_use_not_required` incident and a throttle; `UNDECLARED` is blocked
    with a HIGH incident and a throttle.
  - **Trust-tier enforcement.** `propose` and `suggest` create a proposal and make no
    Forge call. Proposal decisions name a human and record `review_seconds`;
    sub-5-second approvals raise a MEDIUM `rubber_stamp_approval` incident.
  - **Rate limiting.** Postgres token buckets, per agent and per Forge, both must
    admit. Throttles extend but never shorten.
  - **Budget ladder.** Per-task ceiling, per-agent daily cap, soft cap (downgrades
    `auto_execute` to `propose` engagement-wide) and hard cap (Ivan-only reversal).
  - `incident` table, append-only.
  - 31 governance tests; 93 total.

- **Phase 2 — instructions and certification.** The certification gate was previously
  a non-null check on a free-text column; any string satisfied it.
  - **Forge Operating Instructions** with eight required sections enforced by CHECK,
    `content_hash` computed by database trigger, exactly one live set per module,
    and section-level diff.
  - **Two certification units**, both required. Unit A (agent x forge x module,
    operation rubric), Unit B (department x forge, domain rubric). A CHECK pairs unit
    to rubric so a merged score cannot be written.
  - **Seven states, never collapsed.** `TIMEOUT` maps to `in_training`, never
    `certified`; `NOT_RUN` maps to `never_certified`, never `failed`. An unknown
    verdict raises rather than defaulting.
  - **Staleness by comparison**, not by flag. Rewriting instructions flips affected
    certs to `stale_instructions` and the next call fails. A Forge version bump flips
    to `stale_forge` only at or above the module's declared `version_sensitivity`.
    `major.minor.patch` requires a written rationale.
  - **Certified tier caps declared tier, live** in `resolve_grant` rather than at
    grant issuance.
  - **THE NO-READ-PATH CHECK** (`tests/golden/test_no_read_path.py`) — SimForge's ship
    condition, verified by machine. Manifest completeness, forbidden field names and
    prose-shape detection, and a parameter-smuggling sweep. Needs no database and no
    SimForge instance. Includes a deliberately leaky stub so the check is provably not
    vacuous.
  - `curriculum_submission` records refs and counts, never scenario bodies.
  - 182 tests total.

### Changed
- **Second blueprint gap:** Part 12 mandates a per-task USD ceiling, but
  `agent_call_ledger` carries no task identifier and `idempotency_key` is a one-way
  hash that cannot be grouped by task. Per-task spend was not computable as specified.
  `task_id` added in migration 0006. The blueprint should be amended.
- **Blueprint J4 superseded:** CapitalForge bridges first, not CRE Forge (Ivan's
  decision). Consequence: Gate 0 blocks a Greenstone-first Phase 3 until CRE Forge is
  also bridged.

### Fixed
- **Blueprint §2 defect:** `agent_call_ledger` declared `call_id UUID PRIMARY KEY`
  on a RANGE-partitioned table. PostgreSQL requires every partitioning column in a
  unique constraint, so the migration could not run. Corrected to
  `PRIMARY KEY (call_id, ts_start)`. The blueprint should be amended.
- Windows: psycopg's async driver cannot run on asyncio's default
  `ProactorEventLoop`. Without the selector policy the pool does not fail fast — it
  retries to `PoolTimeout`, so the symptom is a 30-second hang rather than an error
  naming the cause. Set once in `broker/__init__.py`, platform-guarded.
