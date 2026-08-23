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

### Changed
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
