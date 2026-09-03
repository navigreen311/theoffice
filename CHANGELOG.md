# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Module exclusion — a module that must never be granted.** Onboarding CapitalForge
  found endpoints that return a plausible success for work that never happens: rules no
  runner consumes, a `TwilioStubClient` returning fabricated SIDs from the endpoint named
  "initiate outbound call", and ten 501s. Granting one gives an agent a 200 and gives the
  ledger a row that reads afterwards as evidence the work was done.
  - `forge_module_exclusion` (migration 0030), deliberately with **no foreign key** to
    `forge_registry`: an exclusion must be recordable before a Forge is onboarded, which
    is the only moment at which it prevents rather than reacts.
  - BEFORE INSERT trigger on `agent_forge_grant` — the guard holds for a writer that
    never heard of it, which is the point, since two production paths write grants.
    INSERT only: an excluded grant must stay revokable.
  - `broker.errors.ModuleExcluded`, raised by `grants.resolve_grant` ahead of every
    per-agent refusal, audited as `call_refused_module_excluded`.
  - `broker/module_exclusions.py` — the declared list with per-module evidence, and
    `scripts/apply_module_exclusions.py` to apply it (`--check` for CI).
  - 17 exclusions recorded for `capitalforge`; `docs/module-exclusions.md`, and a fourth
    silent-failure section in `docs/forge-adapter.md`.

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

- **Phase 3, increment 1 — Business Pack schema v3 and the Pack Validator.**
  - `generators/pack.py` — pydantic models for schema v3, `extra="forbid"` throughout.
  - `generators/validator.py` — all 27 rules. Returns a report naming the offending
    value, in deterministic V1..V27 order.
  - V2 (Gate 0), V6 and V11 read the database, not the document. Without a connection
    they report `NOT_RUN`, and NOT_RUN is not a pass.
  - `packs/greenstone.yaml` — the first venture Pack, hand-authored.
  - `python -m generators validate <pack>` — exits 1 on FAIL or NOT_RUN.
  - 65 validator tests: every FAIL rule has both a must-fail and a must-pass fixture,
    plus a meta-test that fails the build if a rule ships without one. 247 tests total.

- **Phase 3, increment 2 - the seven generators.** Deterministic transformers with
  golden snapshots; no LLM anywhere in `generators/`.
  - 5.1 Role Definition derives implied compliance flags from the module registry.
  - 5.2 Appointment: never fills a position uncertified, names the specific shortfall
    reason per candidate, reports all three capacity numbers.
  - 5.3 Workflow: every step names a module, a flag or explicit NONE, and an escalation.
  - 5.4 Task Ledger: projected daily approvals per human role.
  - 5.5 Curriculum: domain and operation scenarios kept separate, coverage denominators
    on every dimension, operation scenarios bound to the instruction content hash.
  - 5.6 Forge Manifest: three-way reconciliation with four mismatch handlers.
  - 5.7 Runtime Config: consumes the Manifest not the Pack; idempotent by construction
    via UUIDv5 keys.
  - **Gate 4.5** capacity re-check against real Task Ledger output, resolving V24.
  - `Position.lifecycle_stages_owned` added (schema divergence #3).
  - 76 golden tests; 274 total.

- **Phase 3, increment 3 - shift assignment and the verified PHI flush.** The temporal
  wall, which existed only as a column comment.
  - `agent_working_memory` with `data_classification` NOT NULL and no default: tagged
    at write time, never inferred at flush time.
  - `flush_phi()` destroys `phi` and `recording` rows, re-counts to verify, and records
    before/after evidence. Attempted and verified are separate columns.
  - **A failed flush blocks the next assignment**, in `assign_shift` - the one function
    that creates them.
  - `rotate()` performs the Part 7.5 boundary in order and stops at a failed flush
    without creating a new shift.
  - Runs regardless of certification state; a revoked agent still flushes.
  - **Gate 3a in the call path**: a call whose venture is not the agent's on-shift
    venture is refused, closing the mid-shift-switch hole the schema could not see.
  - A test asserts `OfficeClient` exposes nothing that could skip a boundary.
  - 293 tests total.

- **Phase 4, increment 1 - continuous verification.** Three controls shipped fully
  tested and completely inert because nothing ran them; a control nobody runs exists in
  the repository, not in the system.
  - `audit_chain` sweep - CRITICAL incident on a break, `tail_gap` stays advisory.
  - `certification_staleness` sweep - HIGH incident when a newly-stale cert backs a
    live grant. Finding staleness reports `passed`: it is the sweep working.
  - `manifest_reconciliation` sweep (Gate 15) - opens a `manifest_disposition` per
    UNDECLARED in-use module and **fails while any is pending**. Resolution requires a
    named human and a stated reason, enforced by CHECK. `accepted_risk` is a real
    option so nobody has to mislabel a tolerated finding as `declared`.
  - `restore_drill` (Gate 13) - a real `pg_dump`, a real restore into a scratch
    database, and the hash chain verified **in the copy**.
  - `broker health` reports `never_run | fresh | stale | failing` per control and exits
    non-zero on any of the first three. **A stale pass is not a pass.**
  - `python -m broker sweep|health`, one advisory lock per sweep kind, cron-safe.
  - 311 tests total.

- **Console, increment 1 - human identity and the Operations API.**
  - `office_human`, `office_human_role` (scoped to a venture), `signoff_record`
    (bound to an artifact hash, void by comparison).
  - `broker/app.py` - FastAPI. Thirteen read routes and seven write routes, each
    delegating to the guarded domain function that owns its rule.
  - Authorisation asks two questions: is the role strong enough, and is this person
    an operator of *this venture*. The second could not exist before.
  - A test pins the write surface and rejects any path touching certification,
    flush, ledger, shift, memory, grant or audit. A companion test greps the module
    for raw SQL mutation.
  - `python -m broker serve` runs uvicorn with loop=none, because uvicorn installs
    ProactorEventLoop on Windows and psycopg then hangs every request rather than
    failing.
  - 337 tests total.

- **Console, increment 2 - the Next.js application.** Five screens: Compliance
  Dashboard, Agent Registry, Revocation Controls, Forge Map, Audit Log Explorer.
  - **Every API call is server-side.** The token lives in an httpOnly,
    sameSite=strict cookie; the browser never talks to the API. That removes CORS
    entirely and keeps the token out of JavaScript. `lib/api.ts` imports
    `server-only`, so importing it from a client component is a build error.
  - `lib/severity.ts` - the rule this increment adds: anything not verifiably
    healthy renders as not-healthy. `never_run` and `stale` are red, not grey.
    12 unit tests, because this is the logic a UI can get wrong in a way that
    misleads.
  - `scripts/console-smoke.sh` - starts both servers, checks every route, asserts
    the cookie is httpOnly and that no page leaks the token, then tears down.
  - shadcn primitives hand-written; its init CLI is interactive and would hang.

- **Console, increment 3 - six more screens.** Venture Directory, Venture Dashboard
  (three capacity numbers + readiness gates), Agent Identity & Grants detail,
  Approval queue, Instruction authoring index and detail (versions, diff, staleness,
  certification impact).
  - Two new read routes: `GET /api/forges` and the instruction diff. The write
    surface is unchanged and still pinned at seven routes.
  - The approval queue is built so it does not erode the rubber-stamp control:
    payload expanded by default, threshold named on screen with a live counter,
    reason required to reject. Enforcement stays in the API.
  - **Pack Editor, Provisioning Console and KB Manager are deliberately not built** -
    each needs backend that does not exist, and a screen over nothing implies the
    thing exists.
  - 18 console tests; 337 python tests.

### Changed
- **Second blueprint gap:** Part 12 mandates a per-task USD ceiling, but
  `agent_call_ledger` carries no task identifier and `idempotency_key` is a one-way
  hash that cannot be grouped by task. Per-task spend was not computable as specified.
  `task_id` added in migration 0006. The blueprint should be amended.
- **Connection-pool lifecycle.** `open_pool()` recreates a pool that has been closed;
  handing back a closed pool raised at the point of use rather than the point of
  closing, turning a lifecycle mistake into a failure in unrelated code. The per-test
  reset fixture moved to the root conftest - it existed in two directories and not in
  the two others that use the pool, so those left one bound to a dead loop and the next
  suite's first test paid for it.
- **A venture that did not exist rendered a dashboard of zeroes**, indistinguishable
  from a real venture that had not started. `/ventures/[venture]` now 404s unless the
  venture appears in the directory.
- **A smoke check passed for the wrong reason** - it scraped HTML for a venture slug
  and matched a Next.js chunk filename. It now asks the API for real ids.
- **React 19 hook in a React 18 project.** `/revocations` used `useActionState`,
  which does not exist in React 18.3.1. `tsc --noEmit` and `next build` both passed;
  the page threw at render. Now `useFormState` from react-dom. A green build is not
  proof the app runs, which is why the smoke script exercises a real server.
- **Cross-Forge appointment bug.** 5.2 assumed one Forge per position and checked every
  module against it, so a position operating modules on two Forges came back
  unfillable - as valid JSON describing a venture with nobody in it. Found by reading a
  golden snapshot. Module-to-Forge is now resolved from the registry throughout.
- **V22 semantics corrected.** The rule compared scenario coverage against compliance
  *framework names*, but "compliance flag" means the `runtime_flag` everywhere else in
  the system. The framework name never appears at runtime, so the rule was
  unsatisfiable by construction.
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
