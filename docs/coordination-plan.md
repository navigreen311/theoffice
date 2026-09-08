# Parallel Build Coordination Plan — Revision 6

**Burkham Wickmont: from here to a certification run.** Planned 8 September 2026.

This document is authoritative for **what** the parallel build contains. Every package
agent may read it and check its own card against it. **No package agent may modify it.**

---

## TWO THINGS THIS RUN RESTS ON

**1. The scenario contract is the whole run.**

Workstream B exists because The Office and SimForge never agreed what a scenario is.
`docs/scenario-contract.md` is that agreement, landed by P-00 and frozen thereafter.
P-03 and P-05 never talk to each other — they only talk to that file. If it is wrong,
both build correctly against different shapes, both pass their own tests, and the
mismatch stays invisible until P-06/07/08 try to pour eleven modules of authorship into
an interface that does not fit. **That is the worst-timed failure available in this run:
it surfaces after the critical path is spent, and the work it wastes is the authorship.**

If you believe the contract is wrong: **STOP and escalate. Do not edit it. Do not work
around it.**

**2. `theoffice`'s red `main` is deliberate.**

The Smoke job fails because V11 and V32 report NOT_RUN in CI, where no runner can reach
a Forge. That is `docs/decisions.md` entry 3's accepted precedent — a control knowingly
merged while green nowhere, written down as a precedent precisely so a later reader would
not mistake it for neglect.

**Do not fix it. Do not weaken V11, V22, V32 or V33 to make Smoke green.** Doing so
destroys the thing this run exists to establish, **and it would look like progress** — a
green board, a closed job, a commit that reads like a cleanup.

The gate everywhere is **no NEW failures against the P-00 baseline.** Never a green
board, which is not available.

---

## WHAT THIS RUN DOES AND DOES NOT DELIVER

**Delivers:** V11 clears · Burkham V32 PASSES · the scenario contract is agreed and
enforced · SimForge accepts the curriculum for the first time · eleven modules of
scenarios authored · a CapitalForge 401 that lied about its cause stops lying.

**Does not deliver:** Gate 2 does not pass. It stays BLOCKED on V22 by ruling T-080 —
`referral_fee_permitted_in_state` is a real obligation held by a human, not an agent, and
deleting the flag to green the gate would assert the obligation does not exist. Because
Gate 2 stays blocked, the ladder cannot reach Gate 5, `runtime_config.apply` never runs,
and **workstream E does not happen. E is blocked by a ruling, not by packages.**

**This run does not end in a simulation.** It ends in a red gate with one failure that is
supposed to be red.

---

## RULINGS IN FORCE

| ID | Ruling |
|---|---|
| **T-050** | Domain scenarios are **Pack-validation-only** for this run. Workstream C closes. The fifteen scenarios keep satisfying V22/V23 and describing what each role must handle in prose a human reads. Reopens when someone decides what a domain scenario is in executable terms — a source for `testedAgentVillageId`, `seed` and `yamlPath`, and a decision to touch the domain cert tables |
| **Q-1** | A pack-level run gives this run **nothing**. `OperationCert` keys on `unitType`, `forgeId`, `agentId`, `moduleId` and has **no `packId`** — no pack-level unit exists for a pack-level verdict to attach to. `OperationRun` is already the battery record. Gate 8 submits per module and gets one `runRef` per module by construction. **P-04 and P-10 are deleted; the run has no migrations.** `run_scenario_pack` comes off both Packs instead of being built |
| **T-080** | `referral_fee_permitted_in_state` stays declared. **Some declared obligations are held by humans, not agents.** Cost: V22 fails until the compliance surface can distinguish a venture-carried obligation from an agent-carried one — a schema question nobody has asked |
| **T-081** | Placement Strategist gains `fair_treatment_required` and `advance_placement_prohibited`. The other six orphaned flags stay recorded — each needs someone who knows which role's duties touch it, and guessing is how the department mapping went wrong |

---

## ALWAYS-FORBIDDEN LIST — every package, no exceptions

- **Weakening a validator rule to turn a check green.** V11, V22, V32, V33.
- **`docs/scenario-contract.md`** — frozen interface. Escalate, never edit.
- **`docs/coordination-plan.md`** — this file. Read-only for every agent.
- **`theoffice/generators/artifacts.py`** — frozen interface, landed by P-00.
- **`.env` in any repo** — gitignored in all three. Editing it produces an invisible
  change that cannot be reviewed, merged or reverted. Bridge configuration is operator
  runbook R-1, not a package.
- **`PARALLEL_BUILD.md`** — coordinator only.
- **`docs/decisions.md` / `docs/blocking.md`** unless your card names them. Append-only.
- **Any `packs/*.yaml`** unless your card names it. Live Packs version-bump and republish.
- **Alembic migrations.** There are none in this run. One appearing in a PR is an
  automatic hand-back.
- **`simforge/apps/api/src/routers/office.py`** unless your card names it — the adapter's
  dispatch map and its naming authority.
- Shared dependency/config files: `package.json`, `pyproject.toml`, `tsconfig.json`,
  `tailwind.config.*`, CI workflow files.

---

## SHARED-FILE RISK MAP

| File | Why shared | Owner |
|---|---|---|
| `simforge/.../services/operation/scenarios.py` | B1 and B2 both rewrite `validate_curriculum_submission`; holds `HELD_OUT_CLASSES` and `classify_certification_level` | **P-03 exclusively** |
| `simforge/.../schemas/operation_payloads.py` | `OperationScenarioSubmission` | **P-02 exclusively** |
| `simforge/.../services/operation/never_do.py` | The declaration mechanism being generalised | **P-02 exclusively** |
| `simforge/.../routers/operation.py` | Validator caller | **P-03 exclusively** |
| `simforge/.../routers/office.py` | Dispatch map / naming authority | **nobody this run** |
| `theoffice/generators/curriculum.py` | B3 and B4 would both land here | **P-05 exclusively** |
| `theoffice/generators/artifacts.py` | `CurriculumScenario` — imported downstream | **P-00, then frozen** |
| `theoffice/packs/burkham-wickmont*.yaml` | T-095 and T-097a | **P-09 exclusively** |
| `theoffice/packs/greenstone.yaml` | T-097b | **P-12 exclusively** |
| `theoffice/docs/decisions.md` | Ruling records; entry 23 | **P-00, then P-09 (append only)** |
| `theoffice/docs/blocking.md` | Ruling records; B18 | **P-00, then P-12 (append only)** |
| `capitalforge/src/backend/api/routes/index.ts` | Issue #92's fix | **P-01 exclusively** |
| `.env` (x3) | Gitignored, not mergeable | **no package — operator R-1** |

**Why Pack files are split across two packages:** both Packs are live (burkham@0.2.0,
greenstone@1.2.0). Every change is a version bump and a republish. One agent editing two
live Packs in one pass is one review over two ventures, and the declared count is whatever
that agent computed last. Two packages means two diffs, two publishes, two declared
counts, and a reviewer who can refuse one without refusing the other.

---

## PACKAGE CARDS

### P-00 — Coordinator: freeze the contract, the baselines, and the rulings

- **Repo:** theoffice · **Complexity:** M · **Branch:** `feature/p-00-coordinator`
- **Creates:** `docs/scenario-contract.md` (**theoffice only — see amendment R6a**),
  `PARALLEL_BUILD.md`
- **Modifies:** `generators/artifacts.py` (add `CurriculumScenario` fields:
  `scenario_class`, `instruction_section`, `never_do_entry`, `expected_behavior`,
  `expected_escalation_prose: str`, `not_applicable_reason` — all defaulted; the existing
  `expected_escalation: bool` is left untouched, see amendment R6a),
  `docs/decisions.md`, `docs/blocking.md`
- **Will not touch:** every other file in the risk map
- **Depends on:** NONE (PRs #37/#38/#39 already merged)
- **Tasks:** T-090 (record C's deferral **with its reopening condition** — a closed
  workstream with no reopening condition becomes a thing nobody remembers was
  deliberate), T-091 (obligations held by humans), T-092 (the schema question, as a
  blocking item), T-093 (six deferred flags), T-096 (nothing cross-checks the compliance
  surface against `compliance_flags_in_scope` in either direction — which is why both
  failures are silent; one direction was already fixed once by hand), T-101 (widen
  `blocking.md` scope)
- **T-101 detail:** opening line becomes venture-scoped; note that items may be
  venture-scoped or cross-cutting and that new ones carry a scope tag; **do not retro-file
  the existing seventeen**; B-numbering continues unbroken. Record the drift: the stated
  scope had drifted from the contents and was only visible when something arrived that
  obviously did not fit — B4 is SimForge's bootstrap, B13 a validator defect, B17 a git
  command's output. Same shape as entry 3 going stale.
- **Test scope:** `artifacts.py` round-trips with new fields defaulted; existing generator
  tests still pass; **CI baselines for all three repos recorded verbatim in
  `PARALLEL_BUILD.md`**
- **`PARALLEL_BUILD.md` must carry four caveats:** (1) the two load-bearing assumptions,
  verbatim, as its opening section; (2) Gate 2 will not pass this run, by ruling — do not
  read a red V22 as an incomplete package; (3) the certification caveat — the first certs
  will be issued by a system certifying against instructions it received from the system
  being certified, and SimForge's own `gate_result` cert is a human-issued bootstrap;
  retired only by a pack run by a different SimForge instance; (4) **a validator verdict
  that changes is not a validator verdict that improved** — read the clause, not the
  absence of a FAIL.
- **Merge order: 1. Requires Ivan's contract review before merge.**

### P-01 — CapitalForge: an unmounted bridge returns 404

- **Repo:** capitalforge · **Complexity:** M · **Branch:** `feature/p-01-unmounted-bridge-404`
- **Modifies:** `src/backend/api/routes/index.ts` · **Creates:** tests for three states
- **Will not touch:** `.env`, `config/office.ts`, `routes/office.routes.ts`,
  `middleware/tenant.middleware.ts`
- **Depends on:** P-00 · **Tasks:** T-006, T-007
- **Context:** `.env.example` states *"When any is absent the adapter is NOT MOUNTED and
  /api/office 404s."* It does not. `PUBLIC_API_PATHS` exempts `/office` from
  `requireAuth`, the router is never mounted, and the request falls through to a router
  mounted at `/` whose `tenantMiddleware` returns `401 UNAUTHORIZED`. Filed as
  `navigreen311/Capitalforge#92`; the class is `decisions.md` entry 22.
- **Test scope, one per state:** unconfigured → **404**; configured + bad credential →
  401 `OFFICE_CREDENTIAL_REJECTED`; configured + good credential → 200. All three
  asserted separately — only two are distinguishable today.
- **Flags:** auth-adjacent. **Do not widen `PUBLIC_API_PATHS`.** Independent of R-1 and
  must not be skipped because configuring the bridge makes the symptom stop.
- **Merge order: 2**

### P-02 — SimForge: the `not_applicable` primitive

- **Repo:** simforge · **Complexity:** M · **Branch:** `feature/p-02-not-applicable-primitive`
- **Modifies:** `schemas/operation_payloads.py`, `services/operation/never_do.py`
- **Will not touch:** `scenarios.py`, `routers/operation.py`, `routers/office.py`, ADRs
- **Depends on:** P-00 · **Tasks:** T-010, T-011
- **Context:** ADR-0049, Proposed, nothing built. `never_do.py` already tells
  `STATUS_NONE` from `STATUS_UNTESTED` by a declaration — for one class of nine.
  Generalise it. Same shape as `NoFramework(why)`.
- **Test scope:** a declared `not_applicable` requires a reason; the generalisation
  preserves `STATUS_NONE` vs `STATUS_UNTESTED` for `never_do`
- **Merge order: 3**

### P-03 — SimForge: the validator admits declared absence, and the never-do trap closes

- **Repo:** simforge · **Complexity:** L · **Branch:** `feature/p-03-validator-admits-absence`
- **Modifies:** `services/operation/scenarios.py`, `routers/operation.py`,
  `docs/adr/ADR-0048-*.md`, `docs/adr/ADR-0049-*.md`
- **Will not touch:** `operation_payloads.py`, `never_do.py`, `routers/office.py`,
  `models/operation_run.py`
- **Depends on:** **P-02** · **Tasks:** T-012, T-013, T-014, T-020, T-021, T-022
- **Carries the B1/B2 file collision.** Both rewrite `validate_curriculum_submission`.
- **B1 half:** three classes mandatory — `escalation_required` always,
  `recovery_after_failure` when the rubric carries recovery, `never_do_violation` when a
  list is declared. Every other class is a label, and `classify_certification_level` needs
  all nine for certified, so a missing one **caps the module silently and permanently
  rather than refusing it.** Acceptance case: `capitalforge/portfolio_health` cannot
  supply `escalation_required` at any level of effort — a pure read taking no identifier,
  writing nothing, whose `retry_vs_escalate` is "RETRY FREELY" in full.
- **B2 half:** the validator rejects a submission whose declared `module_never_do` has no
  matching `never_do_violation` scenario — but that class is in `HELD_OUT_CLASSES`, so the
  submitter is forbidden to author it. **There is no correct submission.** Fix on
  SimForge's side: either it authors the scenarios for a declared list, or the validator
  stops requiring what it will not accept. **Telling submitters to omit the list is not a
  candidate** — if that were acceptable the column should be deleted rather than left
  silently empty. **Choose, and record the choice in ADR-0048.**
- **Test scope:** three mandatory classes enforced; **a class nobody considered is still
  refused**; no silent cap on a declared n/a; a declared never-do list has a correct
  submission; empty `neverDo` still distinguishes n/a from a coverage hole
- **Merge order: 4**

### P-05 — Office: classed scenario generation + the B4 content interface

- **Repo:** theoffice · **Complexity:** L · **Branch:** `feature/p-05-classed-scenario-generation`
- **Modifies:** `generators/curriculum.py` · **Creates:** the per-module content interface
  (schema + loader + one worked example module)
- **Will not touch:** `generators/artifacts.py`, `broker/simforge.py`, `db/`, `packs/`
- **Depends on:** P-00 only — it builds against the frozen contract, which is what keeps
  it off P-03's chain
- **Tasks:** T-030, T-031, T-032, T-033, T-034, T-035 (doc), T-037, **T-102**
- **T-102 (added by amendment R6a):** migrate `generators/curriculum.py` from
  `expected_escalation: bool` (hardcoded `True` at ~:83) to
  `expected_escalation_prose: str`, then **delete the bool from `CurriculumScenario`**.
  P-00 leaves both fields in place deliberately; you are the package that collapses them.
  P-00's PR description carries the grep of every bool consumer — inherit that list, do
  not re-derive it. This is the one sanctioned edit to `generators/artifacts.py` after
  P-00 freezes it, and it is sanctioned only for removing the superseded field.
- **Three mechanical maps:** `happy_path` ← `correct_sequence`; `permission_denied` ←
  `failure_signatures.hard_failure`; `escalation_required` ← `retry_vs_escalate`.
- **The rest do not map.** `partial_failure` uses the `silent_partial` split already
  landed on three CapitalForge manuals — only 3 of 11 have genuine content, the other
  eight restate shared rule 1. `recovery_after_failure` is degenerate for most modules and
  non-degenerate for `submit_application`. `rate_limited` has **no source in any of 19
  live instructions** except `voiceforge/transcribe_call` — **ruled: no ninth section.
  Emit a recorded cap, do not invent nineteen sections.** `never_do_violation` is held out
  and not authorable by The Office.
- **Sizing:** the ratio swings 29%–71% across modules and tracks whether a module writes,
  filters or assembles. **Not extrapolable from samples — sizing means eleven reads.**
- **This package defines the interface P-06/07/08 fill. If it is wrong, B4 cannot be
  parallelised at all.**
- **Merge order: 5**

### P-06 / P-07 / P-08 — Office: per-module scenario authorship

- **Repo:** theoffice · **Complexity:** L each
- **Branches:** `feature/p-06-authorship-writes`, `feature/p-07-authorship-filters`,
  `feature/p-08-authorship-assembles`
- **Creates:** per-module content files only · **Modifies:** nothing
- **Will not touch:** `generators/curriculum.py`, `artifacts.py`, any shared file
- **Depends on:** **P-05** · **Tasks:** T-040, T-041, T-042, T-043, partitioned by module
- **Partition** by module behaviour, because the ratio tracks it: modules that **write**
  (P-06), that **filter** — pure reads (P-07), that **assemble** (P-08).
- **The work:** the manual sections give **rules**; a scenario needs an **occasion**.
  `never_do[2]` reads *"Never record a channel that was not named."* That is a rule. The
  scenario needs: a human forwards a note saying they are happy for us to reach out, the
  file has a mobile and an email, and the agent is asked to record consent. Then
  `expected_behavior` is what the agent does with that. **Two things are missing per
  scenario: the precipitating situation, and the escalation as prose rather than a bool.**
- **Test scope:** every scenario carries a precipitating situation, not a restated rule;
  `expected_escalation` is prose; no boilerplate `summary` survives; schema-validates
  against P-05's loader
- **Merge order: 6, 7, 8** — order among them is irrelevant, they share no files
- **These are the only packages where adding agents adds throughput.** Split further
  (one per module) if more concurrency is wanted — the files are disjoint by construction.

### P-09 — Burkham Pack amendments

- **Repo:** theoffice · **Complexity:** M · **Branch:** `feature/p-09-pack-amendments`
- **Modifies:** `packs/burkham-wickmont.draft.yaml`, `docs/decisions.md` (**entry 25** — see amendment R6c),
  and `packs/burkham-wickmont.split.draft.yaml` — **header comment only**
- **Will not touch:** `packs/greenstone.yaml` (P-12 owns it)
- **Depends on:** P-00 · **Precondition: R-1 complete** · **Tasks:** T-095, T-097a, T-098
- **Three commits, one version bump 0.2.0 → 0.3.0**, through the diff control with counts
  declared:
  1. Placement Strategist gains `fair_treatment_required`, `advance_placement_prohibited`
     (`:314`). Its current four are all about *how an application is prepared*; neither of
     the two governing *who it goes to* is there. The Pack's own comment at `:709` calls
     this "the sharpest instance of B15's second direction".
  2. `run_scenario_pack` off `modules_expected` (`:417`).
  3. Split-draft header note.
- **T-098 — the split draft note.** Nothing in the repo reads that file (verified) and it
  has no `business_pack` row — it has never been published. **Do not remove
  `run_scenario_pack` from it.** Correcting it would start maintaining a second copy of a
  source, which is what the publish-diff control exists to prevent. The note says:
  superseded by the main draft, not maintained, never published, declares
  `run_scenario_pack` which was removed 8 September 2026 — see entry 23.
- **Entry 25 must supersede entry 5 explicitly**, and record: what was asked and what came
  back; that this differs from entry 4's removals because `lender_match` had no
  implementation *and no description of one* while this has both; **what returns it —
  something that needs a verdict spanning modules**, and that reopening starts at
  `OperationCert` needing a pack-level unit, not at the adapter, because
  `OperationRun.moduleId` is already nullable.
- **Test scope:** V33 still passes; both flags in a position's scope; **V32 PASSES**. If
  V32 reports NOT_RUN instead, **R-1 did not land — stop and report, do not record a
  cleared FAIL.**
- **Merge order: 9**

### P-12 — Greenstone: removal, and why the verdict change is not progress

- **Repo:** theoffice · **Complexity:** M · **Branch:** `feature/p-12-greenstone-pack`

> **THIS PACKAGE'S DELIVERABLE IS THE WRITE-UP.** The YAML change is one line and it is
> the easy half. If you finish in ten minutes you have written the note as an
> afterthought — which is exactly the outcome the note exists to prevent.

- **Modifies:** `packs/greenstone.yaml` (`:176`, one line), `docs/blocking.md` (append
  **B19** only — see amendment R6c)
- **Will not touch:** any burkham Pack file; `docs/decisions.md` (entry 25 is P-09's —
  reference it, do not append); `generators/*`; `broker/*`
- **Depends on:** **P-09** · **Precondition: R-1 complete** · **Tasks:** T-097b, T-099, T-100
- **One version bump 1.2.0 → 1.3.0**, own publish, own declared counts
- **T-099 — the write-up.** V32 on Greenstone goes FAIL → NOT_RUN, **and that is not
  movement.** The FAIL was about a module that does not exist. The NOT_RUN is about Forges
  nobody can ask. **The second fact was always true — it was hidden behind the first**, and
  removing the first is what makes it visible. Greenstone's Gate 2 is exactly as far from
  passing as it was. This is the inverse of entry 22's instance and belongs in the same
  family: there a quiet truth was replaced by a loud falsehood; here a loud truth is
  replaced by a quiet one. **Both make the reader worse off, and only one of them looks
  like a problem.**
- **T-100 — B19**, tagged `venture-scoped: greenstone`: Greenstone has no resolvable
  credential for voiceforge (`https://example.invalid`, `VOICEFORGE_TOKEN` absent).
  Before workstream A the clause named two Forges and read as general unreachability;
  after A it names voiceforge alone — one Forge, one cause, one fix.
- **ACCEPTANCE CRITERION — not "V32 stops saying FAIL":** this package is done when
  **someone reading the next validator run cannot mistake the NOT_RUN for progress.**
- **Test scope:**
  1. `greenstone.yaml` no longer declares `simforge/run_scenario_pack`.
  2. **Expected verdict is NOT_RUN.** A PASS means something unexpected happened —
     investigate, do not celebrate.
  3. **R-1 verification, asserted not observed:** the `unread` clause must name
     **voiceforge alone**. If it names voiceforge *and* capitalforge, R-1 has not taken
     effect — **fail the package and report it against R-1, not against this change.**
- **Merge order: 10 — last**

---

## R-1 — OPERATOR RUNBOOK (not a package, no branch, no PR)

`.env` is gitignored in all three repos. These produce no diff and cannot be done by an
agent. **On the critical path: gates P-09 and P-12.**

```
capitalforge/.env
  OFFICE_SHARED_SECRET=<choose>          # read lazily in config/office.ts, no default
  OFFICE_VENTURE_TENANTS=burkham-wickmont:<real tenant UUID>
  OFFICE_SERVICE_PRINCIPAL_ID=<real User row id>

theoffice/.env
  CAPITALFORGE_TOKEN=<same string as OFFICE_SHARED_SECRET>
```

The shipped example uses all-zeros for the middle two; they need real values from the
database. `forge_tenant_credential` already holds `capitalforge -> env://CAPITALFORGE_TOKEN`.

**Done when:** `GET /api/office/_modules` with the token returns 11 modules, **and a
no-token control returns `OFFICE_CREDENTIAL_REJECTED` — not `UNAUTHORIZED`. That code
appearing is the proof the bridge is actually mounted.** V11 clears for Burkham.

---

## WAVES AND DEPENDENCY GRAPH

```
  [PRs #37/#38/#39 merged]
            |
        Wave 0:  P-00                     (theoffice)  <- Ivan reviews contract
            |
        Wave 1:  P-01     P-02     P-05   (capitalforge, simforge, theoffice)
            |               |        |
        Wave 2:            P-03   P-06 P-07 P-08
            |
        Wave 3:  R-1                      (operator — Ivan)
            |
        Wave 4:  P-09                     (theoffice, 0.2.0 -> 0.3.0)
            |
        Wave 5:  P-12                     (theoffice, 1.2.0 -> 1.3.0)
            |
   V11 clears · Burkham V32 PASSES · Greenstone V32 NOT_RUN (voiceforge)
            |
   GATE 2 STILL BLOCKED — V22, by ruling.  E does not run.
```

**Critical path:** `P-00 → P-05 → P-06/07/08 → R-1 → P-09 → P-12`.
**Merge order:** P-00, P-01, P-02, P-03, P-05, P-06, P-07, P-08, P-09, P-12.
**Never a parallel merge into any `main`. Never a force-push to `main`.**

---

## MERGE CHECKLIST — every PR passes all of these or it is handed back

- [ ] PR title is `[P-NN] <package title>`
- [ ] Description confirms files created/modified are exactly what the card allowed — no
      scope creep
- [ ] Test results attached, compared to the P-00 baseline — **no NEW failures**
- [ ] No forbidden file touched (see the always-forbidden list)
- [ ] **No validator rule weakened** — V11, V22, V32, V33 unchanged in behaviour
- [ ] Escalations from `PARALLEL_BUILD_ESCALATION.md` surfaced in the PR description, not
      buried
- [ ] All dependencies merged before the PR was opened

**If any item fails:** revert if already merged, hand back to the originating agent with
the failing item spelled out, **do not fix it yourself**, move to the next non-blocking PR.

**If a critical-path package fails twice: HALT the build and escalate to Ivan.**

Every merge appends to `PARALLEL_BUILD.md`: package ID, PR link, merge SHA, test results
against baseline, timestamp.

**One standing rule:** any PR that removes a `compliance_flag`, a `modules_expected` entry,
or a validator rule is an **automatic hand-back** unless its card explicitly authorises it
and a decision entry accompanies it. T-097 is the only authorised removal in this run.

---

## ACKNOWLEDGMENT RITUAL — every agent, before any work

1. Package ID, repo, branch name.
2. Confirmation that P-00 has merged and its dependencies are on `main` (Wave 0 skips).
3. Confirmation it has read FILES YOU MUST NOT TOUCH and the always-forbidden list.
4. The CI baseline for its repo, quoted from `PARALLEL_BUILD.md`.
5. **Its restatement of the two load-bearing assumptions in its own words.** If it cannot
   say why the contract matters and why the red `main` is deliberate, it is not ready.
   **An agent that paraphrases "the red main is deliberate" as "the tests are flaky" has
   just identified itself before touching anything.**
6. Any clarifying question about scope.

If any point is missing or point 5 is soft, **re-brief before letting it proceed**.

---

## POST-MERGE SEQUENCE

1. Full regression, lint, type check, build — all three repos, **against the recorded
   baselines**, not against green.
2. **R-1** if not already done, and its verification.
3. **Gate 2 check, with the expected result written down in advance:** V11 cleared, V32
   cleared on Burkham, **V22 still failing, Gate 2 BLOCKED.** A green Gate 2 here would
   mean something went wrong — most likely that someone deleted the flag to make a check
   pass. **Treat an unexpected pass as a defect, not a win.**
4. Stop. Record the state. E waits on a schema question nobody has asked yet.

---

## OUT OF SCOPE

- Village clock (2027Q4 against a tick of 0) — deferred.
- `medlink-wholesale` #75 (CRE Forge's `underwrite_deal` returns the seller's asking price
  as the ARV) — real and open, but Greenstone's, not Burkham's.
- `blocking.md` B4 — the first certifications will be issued by a system certifying against
  instructions it received from the system being certified. Retired only by a scenario pack
  run by a **different** SimForge instance. Carried as a reading caveat in
  `PARALLEL_BUILD.md`, not as work.


---

## AMENDMENT R6a — 8 September 2026

Two rulings made during Wave 0, after P-00 found that its card could not be executed as
written. Recorded here rather than in a brief, because a card an agent cannot follow is a
card the next agent will also not be able to follow.

**1. The contract lives in `theoffice` only. There is no simforge copy.**

The card said "an identical copy for simforge" and named no path and no merge slot. Two
copies in two repos is **a second copy of a source** — frozen during the run by rule, free
to drift the moment the run ends. That is the same reasoning that refused to maintain the
Burkham split draft in parallel with the main draft.

`docs/scenario-contract.md` in theoffice is the single source. **P-02 and P-03 work in
simforge, a repo that does not contain the file they are bound by** — their briefs carry
the absolute path, and that obligation is on the orchestrator, not on them.

**2. `expected_escalation` becomes a new field alongside the bool, not a type change.**

`CurriculumScenario` already carries `expected_escalation: bool`, hardcoded `True` in
`generators/curriculum.py` at ~:83 — **a file P-05 owns and P-00 may not touch.** A type
change therefore lands in P-00's PR, breaks strict mypy, and appears as a NEW failure
against the baseline P-00 is itself recording. Unresolvable inside P-00's card.

So: P-00 adds `expected_escalation_prose: str = ""` and leaves the bool alone. **P-05
migrates and deletes the bool (T-102).** The contract declares the string canonical and
names the transition, so a reader finding two escalation fields can tell immediately which
is live and which is leaving.

**There is a deliberate transitional two-field window on `CurriculumScenario`. It is not a
defect and not a duplicate to be tidied.** Anyone who cleans it up outside P-05 has broken
a boundary.

---

## AMENDMENT R6b — 8 September 2026 · EXECUTION MODEL

**Every agent gets its own git worktree. Agents must not share a working directory.**

Found the hard way in Wave 0: the orchestrator ran `git checkout -b` in the primary
`theoffice` checkout while P-00 held uncommitted work there, and moved P-00's branch out
from under it. Nothing was lost — P-00 had not committed and both branches sat at the same
SHA — but the next occurrence would not be so cheap.

**Branches in one checkout are serialised, not parallel.** The plan assumed per-branch
isolation and never said where each agent works. That is the gap.

- Wave 2 puts **P-06, P-07 and P-08 in `theoffice` simultaneously**. Three agents, one
  checkout, is a guaranteed collision.
- P-01 (capitalforge) and P-02 (simforge) are naturally isolated by being in other repos.
- **P-05 is theoffice** and overlaps any coordinator activity there.

**Rule:** before dispatching an agent, the orchestrator runs
`git worktree add <scratchpad>/wt-<pkg> -b <branch> main` and briefs the agent with that
path as its working directory. The coordinator does its own work in its own worktree too.
`git worktree list` is the check that no two agents share a path.

P-00 keeps the primary checkout for the remainder of its work — moving an agent mid-flight
is a worse risk than the one being avoided.


---

## AMENDMENT R6c — 8 September 2026 · numbering, and a near-miss worth keeping

**P-09 writes `decisions.md` entry 25, not 23. P-12 writes `blocking.md` B19, not B18.**

P-00 merges first and its ruling records took the next free numbers — entries 23 and 24 in
`decisions.md`, B18 in `blocking.md`. The plan was written before those existed. Nothing
was renumbered; the later cards move. Both cards above are corrected in place so those
agents read a right number rather than a wrong one plus a correction. **P-09's content
requirement is unchanged: entry 25 must still supersede entry 5 explicitly.**

`PARALLEL_BUILD.md` keeps P-00's note recording why the numbers moved.

### The near-miss, recorded because the ruling that avoided it was made for a different reason

Amendment R6a changed `expected_escalation` from a type change to a new field, on the
grounds that a type change would break strict mypy in a file P-00 may not touch. That
reasoning was correct and it was not the whole danger.

**Two different classes share the name `expected_escalation`:**

| class | where | who reads it |
|---|---|---|
| `CurriculumScenario.expected_escalation` | `generators/artifacts.py` | `generators/curriculum.py:60`, `:83`, and **`broker/provisioning.py:774-776`** — the last is outside P-05's card |
| `Scenario.expected_escalation` | `generators/pack.py:338` — **the Pack DSL** | **`generators/validator.py:452` (`if s.expected_escalation:`) and `:467`** — V23. Plus 15 rows in the Burkham Pack and 9 in Greenstone |

**Had the type been changed in place on the wrong class, V23's truthiness check would have
silently become "at least one scenario with non-empty prose" instead of "at least one
scenario expecting escalation" — a validator rule changing meaning with no diff to the
validator.** No test would necessarily have caught it; a Pack with prose on every scenario
passes either reading.

This is the entry 13 class arriving in a new place: not a summary dropping a distinction,
but **two distinctions wearing one name**, where the reader of either one cannot tell which
they have. It is recorded here rather than only in a PR because P-05 owns the migration and
`broker/provisioning.py:774-776` is not on its card — **P-05 must escalate rather than
touch it**, and must not migrate anything reached from `generators/pack.py`.
