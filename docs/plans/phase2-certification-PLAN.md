# Phase 2 — Instructions and Certification — PLAN

**Blueprint Phase 2.** Forge Operating Instructions (author, version, `content_hash`,
`version_sensitivity`, diff, staleness) · SimForge held-out partition, SimForge-owned ·
**the automated no-read-path check, shipped with the partition** · curriculum
submission + Gate result callback · grants gated on both certification units.

**Acceptance (blueprint, verbatim):** an agent is certified for one module and becomes
assignable; an uncertified agent cannot be granted; rewriting the instructions flips
affected certs to `stale_instructions` and removes assignability; the no-read-path test
fails the build if a new response field is added without manifest update.

---

## Mini-PRD

**Problem.** Phase 1 gates every call, but the certification gate is currently a
non-null check on a free-text column. Any string satisfies it. Nothing binds a
certification to *what the agent was actually taught*, so rewriting a module's
instructions leaves every certification against the old text silently valid.

**Users.** Instruction authors (humans, per Pack `authored_by`), SimForge (issues
verdicts), venture operators (see assignability), the call path (reads cert state live).

**Success metrics.**
1. A grant whose certs are not both `certified` cannot execute.
2. Rewriting instructions flips affected certs to `stale_instructions` **and the very
   next call fails**.
3. A Forge version bump flips certs to `stale_forge` **only at or above** the module's
   declared `version_sensitivity`.
4. `TIMEOUT` never becomes `certified`; `NOT_RUN` is never reported as a failure.
5. Certified tier caps declared tier, live.
6. The no-read-path check fails the build when a response field appears that the
   manifest does not enumerate.

---

## The load-bearing part: the no-read-path check

Master prompt Part 10.1, verbatim: *"Because Green Companies operates both sides of
this boundary, self-attestation is the weakest possible enforcement for the one control
whose entire purpose is preventing one side from seeing the other's content."*

The Office's obligation is **negative**: there is no read path to build, only one never
to build. That is unusually hard to test, because you cannot test the absence of a thing
by exercising it.

The check therefore has three parts, and all three are needed:

1. **Manifest completeness.** Every field in every SimForge → Office response is
   enumerated in `simforge_response_manifest.json`. The test walks actual responses and
   fails on any field the manifest does not name. *This is the part that fails the build
   when someone adds a field.*
2. **No enumerated field may carry scenario content.** Each manifest entry declares a
   type and a purpose. A field whose name or declared purpose implies scenario content
   fails. A field whose observed value looks like scenario prose fails.
3. **No endpoint returns scenario bodies under any parameter combination.** The test
   sweeps a matrix of the parameters an attacker or a careless caller would reach for —
   `include_scenarios`, `expand`, `fields=*`, `verbose`, `debug` — and asserts none of
   them produces scenario content.

Part 1 alone catches drift but not a field deliberately named innocuously. Part 2 alone
catches naming but not a new field. Part 3 alone catches parameter smuggling but not a
default response change. Together they are a machine verifying continuously what two
parties would otherwise assert about themselves.

**Failure blocks release of both operation certification and Gate 9.5.** The check lives
in `tests/golden/` and runs on every build.

---

## Design decisions

### Instructions are curriculum, not a filing cabinet (Part 6.1)

Content is JSONB with **eight required sections**, enforced by a CHECK constraint:

`what_it_does` · `what_it_does_not_do` · `inputs` · `correct_sequence` ·
`failure_signatures` · `retry_vs_escalate` · `never_do` · `compliance_coupling`

A constraint rather than a convention because Part 6.1 elevates instructions "from
filing cabinet to curriculum" — and a curriculum missing its failure signatures is a
document that reads fine and teaches nothing about the case that matters.

`content_hash` is computed from canonical JSON, in the database, so a caller cannot
supply a hash that does not match its content.

### Certification binds to what was taught

A cert stores the `instruction_content_hash` and `forge_api_version` it was tested
against. Staleness is a comparison, not a flag someone remembers to set:

- current instruction hash ≠ stored hash → `stale_instructions`
- current Forge api_version differs **at or above** `version_sensitivity` → `stale_forge`

`version_sensitivity` semantics (default `major.minor`):

| Sensitivity | 2.1.0 → 2.1.5 | 2.1.0 → 2.2.0 | 2.1.0 → 3.0.0 |
|---|---|---|---|
| `major` | fresh | fresh | **stale** |
| `major.minor` | fresh | **stale** | **stale** |
| `major.minor.patch` | **stale** | **stale** | **stale** |

`major.minor.patch` requires a written `sensitivity_rationale` — enforced by CHECK.
Declaring the strictest sensitivity means every patch release decertifies every agent
on that module, which is sometimes right and always expensive.

### States are never collapsed (Part 10.1)

`certified | stale_instructions | stale_forge | in_training | never_certified | failed | revoked`

A SimForge verdict maps to a state through an explicit table, and **`TIMEOUT` maps to
`in_training`, never `certified`**; **`NOT_RUN` maps to `never_certified`, never
`failed`**. Both are enforced in code with their own tests, because both are the kind of
thing a `verdict == "PASS"` check gets wrong by omission.

### Certified tier caps declared tier — live

Part 10.1: "The Pack declares a ceiling; SimForge sets the actual."

Resolved on **every call**, not at grant issuance. A cert downgraded after the grant was
written must take effect on the next call, for the same reason revocation does. This
supersedes the note in `broker/proposals.py`, which said issuance-time; that note is
corrected in this increment.

### Two rubrics, never merged

Unit A carries the **operation** rubric, Unit B the **domain** rubric. Separate version
stamps, separate re-cert triggers, no composite score. A CHECK constraint pairs unit to
rubric kind so a merged score cannot be written at all.

---

## Acceptance tests

| # | Test | Asserts |
|---|---|---|
| C1 | instructions missing a required section are rejected | curriculum, not filing cabinet |
| C2 | `content_hash` is computed, not supplied | a caller cannot lie about content |
| C3 | `major.minor.patch` without a rationale is rejected | the expensive choice is justified |
| C4 | diff between two instruction versions names changed sections | authoring UI input |
| C5–C7 | sensitivity matrix: `major`, `major.minor`, `major.minor.patch` | staleness precision |
| C8 | rewriting instructions → `stale_instructions` | acceptance criterion 3 |
| C9 | …and the very next call fails | staleness is live, not advisory |
| C10 | Forge bump below sensitivity leaves certs `certified` | no false decertification |
| C11 | Forge bump at/above sensitivity → `stale_forge` | |
| C12 | both units `certified` → assignable, call succeeds | acceptance criterion 1 |
| C13 | Unit A certified, Unit B missing → refused | department cert necessary, never sufficient |
| C14 | cert in any non-`certified` state → refused | states not collapsed |
| C15 | `TIMEOUT` verdict → `in_training`, never `certified` | Part 10.1 |
| C16 | `NOT_RUN` verdict → `never_certified`, never `failed` | Part 10.1 |
| C17 | certified tier caps declared tier, live | Part 10.1 |
| C18 | a cert downgraded mid-session applies to the next call | not cached |
| N1 | every response field is in the manifest | build fails on drift |
| N2 | an unmanifested field fails the check | the check actually catches it |
| N3 | no manifest field may carry scenario content | |
| N4 | no parameter combination returns scenario bodies | smuggling |
| N5 | a deliberately leaky stub is caught | the check is not vacuous |

---

## Out of scope

The authoring **UI** (Part 17, console). Real SimForge integration (needs an instance).
Gate 9.5 held-out execution — SimForge owns it; The Office's obligation here is only to
have no read path. Scenario Pack *generation* is Phase 3 (Generator 5.5).
