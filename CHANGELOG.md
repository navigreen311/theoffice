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

### Fixed
- **Blueprint §2 defect:** `agent_call_ledger` declared `call_id UUID PRIMARY KEY`
  on a RANGE-partitioned table. PostgreSQL requires every partitioning column in a
  unique constraint, so the migration could not run. Corrected to
  `PRIMARY KEY (call_id, ts_start)`. The blueprint should be amended.
