# Coordination Plan — Gate 4.5 to a certified agent

**9 September 2026 · Revision 3 — distribution-ready.** Plan artifact only. No code written, no branches created,
no build or test commands run.

**Revision 2 corrects five things in Revision 1**, all found by reading the schema and the
receiving side rather than reasoning from names. Every correction made the plan longer or
moved a package to a different repo; none made it shorter, and one of them was the plan's own
premise. They are listed in §0.2 rather than folded in silently.

---

## §0 — A0 is answered, and the answer has two halves

The attachment poses A0 as a fork: *either certification is a flow outside the provisioning
ladder, or the first run bootstraps somehow, or the ordering means something not yet
understood.*

**The ordering is fine. Certification has two producers and neither is built.**

Gate 9's docstring settles the ordering outright:

> *"Readiness Gate per role per domain — **read from the certification record. Not a live
> call to SimForge, deliberately.** A Readiness Gate verdict reaches The Office by being
> recorded as a certification."*

Certification is **out of band**. Gate 8 hands over a curriculum; Gate 9 reads rows. Gate 4.5
reads the same `certification` table. No deadlock.

### Half one — unit A has no writer

| fact | evidence |
|---|---|
| `certification.record_result` has **one** non-test caller | `broker/bootstrap_phase0.py`, twice |
| **`attested_by="simforge"` appears nowhere in the codebase** | grep, whole repo, tests excluded |
| `SimForgeClient.gate_result(run_ref)` exists and **nothing outside tests calls it** | `broker/simforge.py:181` |

**No code turns a SimForge verdict into a certification row.**

### Half two — unit B has no submitter, and appointment requires it

Two DB constraints decide what each unit is, without any reasoning from names:

```
unit_targets_match:   A → office_agent_id AND module_id NOT NULL
                      B → department NOT NULL
rubric_matches_unit:  (A AND rubric_kind='operation') OR (B AND rubric_kind='domain')
```

The code already agrees — `broker/simforge.py`, `timeout_gate_result`:

```python
unit="A" if submission.get("module_id") else "B",
rubric_kind="operation" if submission.get("module_id") else "domain",
```

**A submission is one or the other, keyed on `module_id`. Never both.** Gate 8 submits one
curriculum *per module*, so **Gate 8 produces unit-A submissions exclusively.**

`curriculum_submission` today: **10 rows, 10 with `module_id`, 0 with `department`.**

**And unit B gates appointment.** `generators/appointment.py`:

```python
missing_unit_b = [f for f in forges_touched if unit_b.get(f) != "certified"]
```

The only unit-B rows in existence are three bootstrap rows, all `department='engineering'`.
**Burkham's positions declare `administration`, `banking` and `operations`.** Every Burkham
candidate is rejected `missing_unit_b` **even after the unit-A path exists.**

### What this does to the plan

**A2 is necessary and not sufficient, twice over.** A perfect held-out authoring pipeline
produces a unit-A verdict that nothing ingests, for agents that would be refused on unit B
anyway.

**The attachment does not name either producer.** Of C it says: *"Repo: theoffice. Downstream
of A and B. **No new code expected.**"* That is the one claim the code contradicts. **C needs
two builds, and both are on the critical path.**

**Neither is blocked by A2.** Both can be built and exercised against verdicts for modules
with no never-do list. **The two last miles can be built in parallel with the first.**

---

## §0.1 — Unit B does not require executable domain scenarios · the entry-5 ruling stands

Recorded explicitly because the opposite finding would have reversed a ruling.

`apps/api/src/services/operation/run_registry.py:135`:

```python
own_states = agent_states if run.unit == "A" else department_states
state = weakest_state(own_states)
```

**A unit-B run closes on department certification *states*, supplied as a parameter — not on
scenario execution of Office-submitted content.** The domain view reads `cert.status` and
`cert.tier` from a SimForge-side record carrying its own `DOMAIN_RUBRIC_VERSION`, and
`dimensions_passed` is `None`, *"not stored per-cert; shown as unknown, never faked as a
number."*

`OperationRunStart` already accepts `unit="B"` with `rubric_kind="domain"` and
`department_id`.

**So the 6 September ruling — Office domain scenarios are Pack-validation-only — is
unaffected, and its reopening condition has not fired.** The `{role, domain, summary}` prose
scenario and SimForge's hashed-YAML-with-a-seed still *"share `scenario_id` and nothing
else"*, and unit B never asks for the bridge that ruling declined to build.

**Unit B is a submitter to build, not a ruling to reverse.** P-04.

**Open question the package must answer first, not this plan:** whether SimForge holds domain
certifications for `administration`, `banking` and `operations`. If it holds only
`engineering`, P-04 delivers a submitter that correctly reports three departments as
uncertified — **which is the honest outcome and still blocks C.** Flagged as [GAP-5].

---

## §0.2 — What Revision 1 got wrong

| # | Revision 1 said | Actually |
|---|---|---|
| 1 | Unit A vs B unknown — blocking question | **Answered from the schema.** Keyed on `module_id`; never both. And **unit B has no submitter at all** — a second missing producer Revision 1 did not see |
| 2 | `silent_failure` may be out of scope; T-005 deferred | **In scope, not deferrable.** One `HELD_OUT_CLASSES` frozenset, one refusal path, one flag naming both. `classify_certification_level` does `declared - HELD_OUT_CLASSES` — **neither class can be declared away.** One pipeline, two classes |
| 3 | B (ADR-0049) is a `simforge` mechanism to build, Cx M | **Already built on both sides.** `NotApplicableDeclaration`, `declarations_from_map`, required prose reason, three certification levels; The Office already emits `not_applicable_reason`. **Only the `portfolio_health` declaration remains, and it is `theoffice`, not simforge** |
| 4 | The sweep might be the ingester | **Confirmed.** Four of five pieces exist; only the caller is missing |
| 5 | *"`simforge_run_ref` is now populated by Gate 8"* (from the attachment) | **All 10 rows have it NULL.** P-05 put the fields on the wire; Gate 8 has not run since. **B8's condition is retirable, not retired** — A1 is the precondition for judging the sweep usable |

**The attachment's own premise (#5) and Revision 1's package count both moved.** Recorded
here rather than fixed silently, because a plan that quietly absorbs its corrections teaches
nobody where it was weak.

---

## §0.3 — Recommended package count: **15**, not 30

Revision 1 said 13. **P-04 (unit-B submitter) added; P-06 shrinks M→S and changes repo;
P-14 added as a record once AnimaForge was ruled.** Net 15, of which **two build nothing**
(P-00, P-14) and **two are operational** (P-11, P-12).

**The reason for not-30 is unchanged and now stronger:** the critical path is serial and it
got *longer*, not wider. A1 → {A2, unit-A ingest, unit-B submit} → C → D, with A2 now serving
two held-out classes instead of one.

- **Splitting A2 across agents puts them in the same scorer.** It is one pipeline serving two
  classes that share a frozenset, a refusal path and an isolation requirement.
- **Everything genuinely parallel is small.** F is six recorded items; G is blocked on a
  ruling; E is two operator actions and a merge.
- **Adding agents does not shorten the critical path.**

**Real width: seven packages can start the moment P-00 lands.** Beyond that, more agents means
more contention over `docs/blocking.md` for no schedule gain.

---

# PART 1 — Remaining Work Inventory

Complexity: **S** ≤ half a day · **M** a day or two · **L** multi-day or unscoped.

## A — Held-out authoring · `simforge`

| ID | Title | Description | Cx | Depends |
|---|---|---|---|---|
| **T-001** | A0: the certification ordering question | **ANSWERED — §0.** Out of band by design; **two producers missing, not one.** Deliverable is a finding plus an ADR. | S | none |
| **T-002** | **Unit-A verdict return path** (the sweep as ingester) | `gate_result(run_ref)` → `record_result(attested_by="simforge")`. **Repo `theoffice`.** See §2. | **L** | T-004 |
| **T-003** | **Unit-B department submitter** | Start a unit-B run per (department, forge) and read the verdict. **Nothing does this.** Repo `theoffice`. | **L** | T-004 |
| **T-004** | A1: verify the Gate 8 handover is accepted | Six 422s on `scenario_class`/`instruction_section`; P-05 put both on the wire; **nobody has run Gate 8 since, and no row carries a `run_ref`.** | M | none |
| **T-005** | A2: held-out authoring — **`never_do_violation` AND `silent_failure`** | One pipeline, two classes. Material: eleven CapitalForge manuals; `record_consent` alone has 13 never-do entries. **Neither class is declarable away.** | **L** | T-004 |

## B — Declared `not_applicable` (ADR-0049)

| ID | Title | Description | Repo | Cx |
|---|---|---|---|---|
| **T-006** | ADR-0049 mechanism | **ALREADY BUILT, both sides.** simforge: `NotApplicableDeclaration`, `declarations_from_map`, required reason, `certified` / `certified_with_declared_absence` / `demonstrated`. theoffice: `not_applicable_reason` on the curriculum artifact, emitted by `generators/curriculum.py`. **No build task.** | — | — |
| **T-007** | Declare `escalation_required` not-applicable on `capitalforge/portfolio_health` | Unsatisfiable there — takes no identifier, writes nothing, `retry_vs_escalate` is *"RETRY FREELY"* in full. **A declaration in `theoffice`, using machinery that exists. Closes B16.** Gates Stack Manager. | theoffice | **S** |
| **T-008** | ADR-0048 consequence, restated | P-03 (`2ce2f5d`) moved the never-do refusal to scoring time; every declared entry is an open obligation until T-005. **A record, not a build.** | theoffice | S |

## C — Certification run · `theoffice`

| ID | Title | Description | Cx | Depends |
|---|---|---|---|---|
| **T-009** | Certify agents against the 11 CapitalForge modules | 54 identities; `produced_not_yet_certified` was 63 at Gate 4. **Needs T-002 *and* T-003 — the attachment's "no new code expected" is wrong twice.** | M | T-002, T-003, T-005, T-007 |
| **T-010** | `produced_not_yet_certified` semantics note | Counts **candidates examined for positions being appointed**, not uncertified identities in the venture (B23). Folded into T-017. | S | none |

## D — Gate 5 and the manifest · `theoffice`

| ID | Title | Description | Cx | Depends |
|---|---|---|---|---|
| **T-011** | Advance the ladder to Gate 5 | `runtime_config.apply` is the only generator and runs at Gate 5. No run has ever reached it. **Running the ladder, not a code change.** | M | T-009 |
| **T-012** | Do **not** hand-write manifest rows | 2 rows against 7 declared modules, both hand-placed by Phase 0. Four more leaves the same defect one module wider. **A constraint, not a task.** | — | — |

## E — Small and owed

| ID | Title | Description | Repo | Cx |
|---|---|---|---|---|
| **T-013** | Rotate `OFFICE_SHARED_SECRET` | Exposed in a transcript. Both `.env` files, restart, re-run the three bridge checks. **`.env` is gitignored — an Ivan action, never a package.** | capitalforge + theoffice | S |
| **T-014** | Create Ira Green's `office_human` | `POST /api/humans`, real email — `.invalid` stamps `test_fixture` permanently. **Needs Ivan's token.** | theoffice | S |
| **T-015** | Merge `docs/b22-second-half-and-b29` | Pushed, unmerged. Folded into P-00. | theoffice | S |

## F — Recorded, none blocking · `theoffice`

| ID | Title | Description | Cx |
|---|---|---|---|
| **T-016** | B22 — reviewer-exists check at Gate 1/2 | Pack↔human join is a display-name string match. Both halves: the Pack can name a reviewer nobody has heard of, and the system accepts a review from someone the Pack never named. **Needs a name-vs-id decision.** | **L** |
| **T-017** | B23 — four names asserting more than the code does | `produced_not_yet_certified`, `live` on a Pack, `review_seconds`, `max_daily_approvals`. Carries T-010. | M |
| **T-018** | B25 — Gate 2 pools, Gate 4.5 weights | Gate 2 takes an unweighted mean across all humans; Gate 4.5 splits by role and weights. **Fixing Gate 2 moves a verdict — P-12 treatment.** | M |
| **T-019** | B26 — the round-trip test | Publish, read back through `live()`, parse, assert. **Named-not-built; the fixture must simulate an earlier build.** | S |
| **T-020** | B27 — the false exception | `not a schema-v3 Business Pack`, on a row that is schema-v3. | S |
| **T-021** | B29 — the discarded role | `authorize()` returns it, `sign_off` keeps it, `record_human_review` discards it. `evidence` is `jsonb` — **no migration.** | S |

## G — Not started

| ID | Title | Description | Cx | Blocked by |
|---|---|---|---|---|
| **T-022** | FunnelForge — nine modules | Module-gated. **The module must refuse a non-autonomous template and a non-Pass state inside the handler, verified by tests.** | **L** | — |
| **T-023** | The six-step price of a seventh template | Adapter binding, registry row, manifest row, operating instruction, curriculum, certification. **Steps 4 and 5 are not automatable.** | M | T-022 |
| **T-024** | AnimaForge — **RULED 9 September: zero for V1** | No agent-facing act in the marketing plan produces video; everything creative is human-authored and **the worker's share is distribution.** **A ruling now, not an inference from silence.** Packaged as a record — P-14. | S | — |
| **T-025** | Ports | FunnelForge's fifteen containers publish **no host ports**. AnimaForge wants 4000/3001/3002/5432/8001; **5432 is The Office's own database.** | S | T-022 or T-024 |

## H — Open elsewhere

| ID | Title | Description | Cx |
|---|---|---|---|
| **T-026** | `medlink-wholesale#75` | `underwrite_deal` returns the asking price as ARV at 0.10 confidence, and a $300,000 constant where none is recorded. Five downstream fields inherit it **with no confidence of their own.** **B is the floor whether or not A is built.** | M |

**[OUT OF SCOPE: T-026]** — not in Burkham's path, different repo, no dependency either way.
In the inventory because the attachment lists it; **in no package**, so it does not compete
with critical-path work for the merge queue.

**[OUT OF SCOPE: the Village clock; the Office/Village/Console ownership question]** —
deferred by the attachment.

## Gaps

**[GAP-1] RESOLVED — `silent_failure` is in scope.** Same frozenset, same refusal, and
`declared - HELD_OUT_CLASSES` means it cannot be declared away. **One pipeline, two classes.**
It lengthens T-005 and therefore the critical path.

**[GAP-2] RESOLVED — two producers, both named.** T-002 and T-003.

**[GAP-3] RESOLVED — the unit question.** Keyed on `module_id`; never both.

**[GAP-4] B4's bootstrap limitation is stated and has no task — deliberately.** SimForge's own
`gate_result` certification is human-issued and the row says so; retiring it needs a scenario
pack run by a *different* SimForge instance. **No task raised**, so the first green verdict is
not read as more than it is.

**[GAP-5] NEW — do Burkham's three departments hold SimForge domain certifications?** Only
`engineering` appears in The Office's rows. If SimForge holds none for `administration`,
`banking` or `operations`, **P-04 correctly reports three uncertified departments and C stays
blocked** — an honest outcome, and a different piece of work. **P-04's first task, not this
plan's to answer.**

---

# PART 2 — Shared-File Risk Map

## `theoffice`

| File | Why shared | Strategy |
|---|---|---|
| **`docs/blocking.md`** | **Highest-contention file.** T-001, T-008, T-010, T-016–T-021 all append. Caused repeated conflicts last run. | **Append-only, one section per package, coordinator resolves.** A closure is an appended paragraph, never a rewrite of the item above. |
| **`docs/decisions.md`** | T-001, T-016 add entries; numbers collide. | **P-00 pre-allocates numbers.** |
| **`broker/simforge.py`** | **T-002 and T-003 both live here** — `overdue_submissions`, `timeout_gate_result`, the client. | **Serialize: P-03 merges before P-04.** They are the same file and the same sweep. |
| **`broker/certification.py`** | T-002, T-003. | Sole owner P-03; P-04 inherits after merge. |
| **`broker/provisioning.py`** | T-002, T-021, T-011. | **P-03 owns it.** T-021 is *one line inside `record_human_review`* — folded into P-03 because the file is shared, not because the tasks relate. |
| **`generators/validator.py`** | T-018 (Gate 2 V13), T-016 (a new rule). | **Serialize: P-09 before P-10.** |
| **`broker/packs.py`** | T-020, and T-019's test reads it. | P-07 owns the file and both tasks. |
| **`generators/curriculum.py`** | T-007 emits the declaration. | Sole owner P-06. **Does not overlap P-03/P-04**, which touch the submission and verdict paths, not curriculum generation. |
| **`tests/golden/snapshots/*`** | **Any change altering generator output moves these.** T-007, T-009, T-011, T-017 are candidates. | **Stable interface — no package regenerates.** A moved snapshot is a finding; `UPDATE_GOLDEN=1` is the coordinator's call. |
| **`EXPECTED_SCHEMA_REVISION` + rule-count assertions** | Bit this project last run. | **Any package adding a migration or a rule bumps both in the same commit.** |
| **`PARALLEL_BUILD.md`** | Merge ledger. | **Coordinator only.** |
| **`.env` / `.env.example`** | T-013. | **`.env` is gitignored and must NEVER be edited by a package.** `.env.example` is P-00 only. |

## `simforge`

| File | Why shared | Strategy |
|---|---|---|
| **`services/operation/scenarios.py`** | `HELD_OUT_CLASSES` and the refusal path. T-005 authors both held-out classes. | **Sole owner P-05.** ADR-0049 is built, so **no second package contends for this file** — the Revision 1 P-04/P-05 serialization is no longer needed. |
| **`services/operation/never_do.py`** | The scoring-time coverage check T-005 resolves. | Sole owner P-05. |
| **`services/operation/run_registry.py`** | Read by P-01 and P-04's counterpart work. | **Read-only for every package.** No Office package modifies simforge. |
| **`docs/adr/`** | T-001 adds one. | **P-00 pre-allocates the number.** |

## Cross-repo

| Risk | Strategy |
|---|---|
| **A package spanning both repos** | **Forbidden.** T-002, T-003, T-007 are `theoffice` though all three concern SimForge; T-005 is `simforge`. |
| **`OFFICE_SHARED_SECRET` desync** | T-013 changes both `.env` files and restarts both **before the wave**, by Ivan. A package that hits a 401 mid-run must not "fix" it. |

---

# PART 3 — Package Design

## P-00 · Coordinator — foundations
- **Tasks:** T-001, T-008, T-010, T-012, T-015, number pre-allocation · **Repo:** theoffice (+ one simforge ADR)
- **Creates:** `PARALLEL_BUILD.md`; the A0 ADR
- **Modifies:** `docs/blocking.md`, `docs/decisions.md`
- **Will not touch:** any `broker/`, `generators/` or `tests/` file
- **Depends on:** NONE · **Blocked by:** T-013, T-014 by Ivan
- **Cx:** M · **Branch:** `feature/p-00-coordinator` · **Order:** 1

## P-01 · A1 — verify the Gate 8 handover ★ critical path
- **Tasks:** T-004 · **Repo:** simforge
- **Creates:** an end-to-end submission test · **Modifies:** nothing in production — **a needed production change is the finding**
- **Depends on:** P-00 · **Cx:** M · **Branch:** `feature/p-01-verify-handover` · **Order:** 2
- **Test scope:** one real submission accepted, asserted on the response body, not on a 200
- **Flags:** **may report the handover still fails — a valid outcome, never worked around.** **Everything downstream waits on this**, because no `curriculum_submission` row has ever carried a `run_ref` and the sweep cannot be judged until one does.

## P-02 · A1b — Gate 8 from The Office's side
- **Tasks:** T-004 (mirror) · **Repo:** theoffice
- **Creates:** a Gate 8 harness test · **Will not touch:** `broker/provisioning.py`, `broker/simforge.py`
- **Depends on:** P-01 · **Cx:** S · **Branch:** `feature/p-02-gate8-harness` · **Order:** 3
- **Test scope:** Gate 8 submits and **`simforge_run_ref` is populated** — the exact condition B8 waits on

## P-03 · Unit-A verdict return path — the sweep as ingester ★ critical path
- **Tasks:** T-002, T-021 · **Repo:** theoffice
- **Creates:** the ingest caller
- **Modifies:** `broker/simforge.py`, `broker/certification.py`, `broker/provisioning.py`, the sweep registry
- **Will not touch:** `generators/`, `broker/packs.py`
- **Depends on:** P-02 · **Cx:** **L** · **Branch:** `feature/p-03-verdict-ingest` · **Order:** 4
- **Design, settled:** **a sweep, not an inbound route.** Four of five pieces exist — `overdue_submissions` (the query), `timeout_gate_result` (builds a `GateResult` and derives the unit correctly), `VERDICT_TO_STATE`, and `SimForgeClient.gate_result`. **Only the caller is missing**, and `overdue_submissions` is referenced by nothing but its own test. The reasoning is that function's own docstring: *"a control that depends on the failing component to announce its own failure is not a control."* An inbound route would have SimForge announcing a value that grants production authority — **the same shape that docstring rejects, at higher stakes.**
- **Test scope:** a verdict produces a row with `attested_by='simforge'`; a withheld verdict produces `provisional`, never `certified`; **the `certified_records_its_basis` guard is exercised, never bypassed**; an unanswered run still resolves to TIMEOUT and `in_training`
- **Flags:** **auth / trust boundary.** A verdict that certifies must not be constructible by the submitter.

## P-04 · Unit-B department submitter ★ critical path · NEW in Revision 2
- **Tasks:** T-003 · **Repo:** theoffice
- **Creates:** the unit-B submission path — start a run per (department, forge) with `unit="B"`, `rubric_kind="domain"`, `department_id`; read the verdict through the same sweep
- **Modifies:** `broker/simforge.py`, `broker/certification.py`
- **Depends on:** **P-03** — same file, same sweep · **Cx:** **L** · **Branch:** `feature/p-04-unit-b-submitter` · **Order:** 5
- **First task, before any code:** **[GAP-5] — does SimForge hold domain certifications for `administration`, `banking` and `operations`?** Only `engineering` exists on The Office's side.
- **Test scope:** a unit-B submission carries `department` and **no `module_id`**, satisfying `unit_targets_match`; the row lands with `rubric_kind='domain'`, satisfying `rubric_matches_unit`; **a department with no SimForge domain cert reports as uncertified rather than as an error**
- **Flags:** **Do not build an executable-domain-scenario bridge.** Unit B closes on department certification *states*, not on Office-submitted scenario content — see §0.1. The 6 September ruling stands and this package must not reverse it by accident.

## P-05 · A2 — held-out authoring, both classes ★ critical path
- **Tasks:** T-005 · **Repo:** simforge
- **Creates:** the authoring pipeline · **Modifies:** `scenarios.py`, `never_do.py`, the scorer
- **Will not touch:** the submission validator (P-01's territory), `run_registry.py`
- **Depends on:** P-01 · **Cx:** **L, unscoped, and larger than Revision 1 assumed** · **Branch:** `feature/p-05-held-out-authoring` · **Order:** 6
- **Scope, corrected:** **`never_do_violation` AND `silent_failure`.** One frozenset, one refusal path, one `GATE_9_5_FLAG` naming both, and `classify_certification_level` does `declared - HELD_OUT_CLASSES` so **neither can be declared away.** One pipeline serving two classes — not two pipelines, and not one class with the other deferred.
- **Test scope:** a declared `module_never_do` entry produces a held-out violation scenario; **an equivalent path exists for `silent_failure`**; **the submitter cannot read either set**; a compliant agent passes and a violating agent fails
- **Flags:** **held-out integrity.** The isolation must be asserted by a test, not claimed in a comment — `GATE_9_5_FLAG` already records that the engine cannot self-prove it.

## P-06 · Declare `portfolio_health`'s `escalation_required` not-applicable
- **Tasks:** T-007 · **Repo:** **theoffice** (was simforge in Revision 1) · **Cx:** **S** (was M)
- **Modifies:** the `capitalforge/portfolio_health` scenario content / declaration
- **Depends on:** P-00 — **not on any mechanism, because ADR-0049 is already built on both sides**
- **Branch:** `feature/p-06-portfolio-health-na` · **Order:** 7
- **Test scope:** the declaration reaches SimForge as `module_not_applicable`; `escalation_required` reports declared-absent with its reason rather than untested; **the module classifies as `certified_with_declared_absence`, never as `certified`** — the level exists precisely so the cap stops being silent. **Closes B16.**
- **Flags:** the reason is required prose. A one-word reason is refused by machinery that already exists — **do not weaken it to pass.**

## P-07 · B27 + B26 — the false message and the round-trip test
- **Tasks:** T-019, T-020 · **Repo:** theoffice · **Modifies:** `broker/packs.py`; creates a test
- **Depends on:** P-00 · **Cx:** M · **Branch:** `feature/p-07-pack-read-honesty` · **Order:** 8
- **Test scope:** an old-schema row reports *stored before provenance was required*, not *not schema-v3*; **the round-trip test must be shown to fail against a row written before the field existed**, by constructing one

## P-08 · B23 — four names asserting more than the code does
- **Tasks:** T-017 (carries T-010) · **Repo:** theoffice
- **Will not touch:** `tests/golden/snapshots/` — **if a snapshot moves, STOP and escalate**
- **Depends on:** P-00 · **Cx:** M · **Branch:** `feature/p-08-honest-names` · **Order:** 9

## P-09 · B25 — the two gates aggregate supply differently
- **Tasks:** T-018 · **Repo:** theoffice · **Modifies:** `generators/validator.py`, Gate 2 V13 only
- **Depends on:** P-00 · **Cx:** M · **Branch:** `feature/p-09-v13-aggregation` · **Order:** 10
- **Test scope:** **predict both ventures' verdicts before running.** A flip is a verdict changing without anything getting better and needs the P-12 treatment — a written explanation, not a silent pass
- **Flags:** **Burkham's V13 margin is twelve minutes** — 420 against 432. Report the new margin explicitly rather than reporting PASS.

## P-10 · B22 — the reviewer-exists check
- **Tasks:** T-016 · **Repo:** theoffice · **Modifies:** `generators/validator.py`, `broker/provisioning.py`
- **Depends on:** **P-09 and P-03** · **Blocked by:** NONE — **ruled 9 September: name match**
- **Cx:** **M** (was L) · **Branch:** `feature/p-10-reviewer-exists` · **Order:** 11
- **The ruling, and the reasoning to carry into the code:** *the finding is not that the join is a string; it is that nothing checks the string resolves until Gate 10.* Moving the check to Gate 1 or 2 fixes **both halves** — a Pack naming a reviewer nobody has heard of, and a review from someone the Pack never named — **without a schema change, on a table P-03 and P-10 already contend for.**
- **The deferred option, and what would justify it:** an id with a migration behind it. **Two things would make the case: two humans sharing a display name, or a rename orphaning a reference. Neither has happened.** When one does, the case makes itself — so the package records the trigger and does not pre-build for it.
- **Test scope:** a Pack naming a reviewer with no account fails at Gate 1 or 2, **not Gate 10**; a review from an undeclared human is recorded as undeclared
- **Flags:** **the rule count changes — `EXPECTED_SCHEMA_REVISION` and every rule-count assertion move in the same commit.**

## P-11 · C — the certification run
- **Tasks:** T-009 · **Repo:** theoffice · **Operational**
- **Depends on:** **P-03, P-04, P-05, P-06** — all four · **Cx:** M · **Branch:** `feature/p-11-certification-run` · **Order:** 12
- **Test scope:** none new. **The deliverable is a report:** how many of the eight seats fill, how many candidates are refused `missing_unit_b` versus uncertified on unit A, and what `produced_not_yet_certified` reads versus what it means

## P-12 · D — Gate 5 and the manifest
- **Tasks:** T-011 · **Repo:** theoffice · **Operational**
- **Depends on:** P-11 · **Cx:** M · **Branch:** `feature/p-12-gate-5` · **Order:** 13
- **Flags:** **Do not hand-write manifest rows (T-012).** Fewer than seven from `runtime_config.apply` is the finding, not a gap to fill by hand.

## P-13 · G — FunnelForge binding
- **Tasks:** T-022, T-023, T-025 · **Repo:** theoffice
- **Depends on:** NONE — **fully independent** · **Cx:** **L** · **Branch:** `feature/p-13-funnelforge` · **Order:** 14, gates nothing
- **Test scope:** **the module refuses a non-autonomous template and a non-Pass state inside the handler**, asserted by tests
- **Flags:** **authorization boundary.** FunnelForge's containers publish no host ports — *running* and *reachable* are different states, and the probe must read a response body.

## P-14 · AnimaForge — the ruling, recorded
- **Tasks:** T-024 · **Repo:** theoffice · **Record only, no build**
- **Creates / modifies:** a `docs/decisions.md` entry at a P-00-allocated number
- **Depends on:** P-00 · **Cx:** S · **Branch:** `feature/p-14-animaforge-ruling` · **Order:** 15, gates nothing
- **What the entry must say:**
  - **Ruled: zero for V1.** No agent-facing act in the marketing plan produces video; everything creative is human-authored and **the worker's share is distribution.**
  - **This is a ruling, not an inference from silence.** The previous state — zero *inferred from what the intake does not say* — was weaker than §3.4's explicit ban, and the entry must record that the standing changed even though the number did not.
  - **Reopening condition: the day a marketing act produces generated video or creative.**
  - **What it does not mean.** AnimaForge is **first-wave by founder decision**, and V1's plan giving it nothing to do is **a fact about V1**, not about AnimaForge. Both sit side by side and the entry keeps them there rather than resolving one into the other.
- **Test scope:** `tests/test_docs.py` passes. No behavioural test — **a ruling that produced a test would be a ruling that changed the code, and this one does not.**

**Not packaged:** T-006 (built). T-013, T-014 — operator actions, Ivan before P-00 merges.
T-026 — **[OUT OF SCOPE]**.

---

# PART 4 — Dependency Graph & Merge Order

```
                             P-00 (coordinator)
                                    |
      +---------+---------+---------+---------+---------+---------+
      |         |         |         |         |         |         |
    P-01      P-06      P-07      P-08      P-09      P-13        |
  (verify)  (p_health) (B27+26)  (B23)     (B25)   (FunnelForge)  |
  simforge  theoffice  theoffice theoffice theoffice  theoffice   |
      |         |                                       |         |
   +--+--+      |                                       |         |
   |     |      |                                       |         |
 P-02  P-05     |                                       |         |
(harness)(A2 x2)|                                       |         |
theoffice simforge                                      |         |
   |       |    |                                       |         |
 P-03 *    |    |                                       |         |
(unit-A    |    |                                       |         |
 ingest)   |    |                                       |         |
   |       |    |                                       |         |
 P-04 *    |    |                                       |         |
(unit-B    |    |                                       |         |
 submit)   |    |                                       |         |
   +-------+----+                                       |         |
           |                                            |         |
         P-11 (certification run)                       |         |
           |                                            |         |
         P-12 (Gate 5 + manifest)                       |         |
                                                        |         |
         P-10 (B22) <-- depends on P-09 AND P-03 -------+---------+
```

**Merge order:** P-00 → P-01 → P-02 → P-03 → P-04 → P-05 → P-06 → P-07 → P-08 → P-09 →
P-10 → P-11 → P-12 → P-13

**Critical path — seven deep, one longer than Revision 1:**

```
P-00 -> P-01 -> P-02 -> P-03 -> P-04 -> P-11 -> P-12
        with P-05 (now two classes) joining before P-11
```

**Longest by effort:** P-00 → P-01 → P-05 → P-11 → P-12, because **P-05 is unscoped and now
serves two held-out classes.** P-03 and P-04 are both L and serialized on the same file, so
that branch is long too.

**Truly independent — start the moment P-00 lands:**
**P-01, P-06, P-07, P-08, P-09, P-13.** Six, plus P-05 once P-01 clears. **Seven of fourteen.**

**Acyclicity:** P-10's two parents (P-09, P-03) are both upstream; P-11's four parents are all
upstream; no node is its own ancestor. **DAG verified.**

---

# PART 5 — Coordinator Package (P-00)

**Must merge before any parallel package begins.**

1. **`PARALLEL_BUILD.md`**, recording before anything runs:
   - **Baselines, not green.** `theoffice` main is red on **Smoke alone** — V11 and V32 report
     NOT_RUN in CI where no runner can reach a live Forge. **The gate everywhere is *no new
     failures against the recorded baseline*.** Capture the failing-check list byte-for-byte,
     and record that **a comparison of two empty captures is not a comparison.**
   - Test counts per repo at the starting SHA.
   - Caveats carried forward: *a `tail -3` on a three-command chain is a prediction dressed as
     a measurement*; *a grep finds mentions, not construction*.
   - The empty merge ledger.
2. **The §0 finding and the §0.1 confirmation** into `docs/blocking.md` plus an ADR:
   certification is out of band by design; **two producers are missing**; and **unit B does not
   require executable domain scenarios, so decisions entry 5 stands and its reopening
   condition has not fired.**
3. **Number pre-allocation** — `docs/decisions.md` entries and `docs/adr/` numbers assigned
   per package.
4. **T-008, T-010, T-012** recorded as constraints.
5. **T-015** — merge the outstanding `docs/b22-second-half-and-b29` branch so every package
   starts from one `docs/blocking.md`.
6. **No interface file is needed.** No package imports another's new code — P-05 is in a
   different repo from everything it serves. **Stated so nobody invents one to be safe.**

**Blocked by, and Ivan clears before P-00 merges:** T-013, T-014, and question 1 below.

---

# PART 6 — Per-Package Prompt Template

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT (Per-Package Prompt)
READ THIS BEFORE DOING ANYTHING

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own
branch, in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed
in your package card. Reaching outside that scope — even for a "small fix" — corrupts
the parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            [FILL IN]
Title:                 [FILL IN]
Repo:                  [FILL IN — theoffice OR simforge. Never both.]
Tasks included:        [FILL IN — T-0xx ids]
Description:           [FILL IN — in operator language]

FILES YOU MAY CREATE:  [FILL IN]
FILES YOU MAY MODIFY:  [FILL IN]
FILES YOU MUST NOT TOUCH:
  [FILL IN, plus these always:]
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (see rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            [FILL IN — package IDs that must MERGE first, or NONE]
BLOCKED BY:            [FILL IN — decisions, credentials, or NONE]
BRANCH NAME:           feature/p-[NN]-[slug]
WORKTREE:              required — see rule 1
TESTS YOU MUST WRITE AND PASS: [FILL IN]
COMPLIANCE / SECURITY FLAGS:   [FILL IN]

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a
     shared checkout — that collides with whatever another agent has uncommitted.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently.
     Write PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why,
     complete what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes
     and are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately. Read PARALLEL_BUILD.md for
     the baseline before you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named
     specifically; the principle covers all of them. The same applies to SimForge's
     held-out refusal and to ADR-0049's required reason — both exist to refuse
     something, and a package that loosens either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every
     rule-count assertion IN THE SAME COMMIT.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This
     plan's own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any
     escalations; and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.
```

---

# PART 7 — Merge, Test & Push Protocol

1. Package agents work in parallel, each in **its own worktree**, on its own branch.
2. Each opens a PR when its package's tests pass **against the recorded baseline**.
3. **One coordinator instance, never parallel**, merges in dependency order:
   - Pull latest main → merge the PR → run the full suite for that repo
   - **No new failures** → push → next PR
   - **New failure** → revert, hand back with the failing output, move to the next
     non-blocking PR
4. After all merges: **full regression, lint, type check and build across both repos,
   compared to the recorded baselines rather than to green.**
5. Final push with a merge-window summary commit.
6. **Post-merge audit** — any package needing more than one revert-and-retry gets a
   post-mortem entry.

**Explicit rules**

- **Never parallel-merge into main. Ever.**
- **Never force-push to main.**
- Every merge writes a `PARALLEL_BUILD.md` row: package ID, PR link, merge SHA, test results,
  timestamp.
- **A critical-path package failing twice halts the entire run and escalates to Ivan.**
- **Smoke's failing-check list is diffed byte-for-byte against the baseline capture, and the
  capture must be non-empty.**

---

# Questions before distribution

Revision 1 raised five. **All five are now settled. Nothing blocks distribution.**

| # | Question | Status |
|---|---|---|
| 1 | **Who may write an `attested_by='simforge'` row — sweep or inbound route?** | **RULED: the sweep.** Ivan's lean, and `overdue_submissions`' own docstring supports it: *"a control that depends on the failing component to announce its own failure is not a control."* An inbound route would have SimForge announcing a value that grants production authority. **Recorded as settled; P-03 builds it.** |
| 2 | Unit A vs B mapping | **ANSWERED from the schema.** §0. |
| 3 | Is `silent_failure` in scope? | **ANSWERED: yes, and not declarable away.** §0.2. |
| 4 | **B22 — name match or id?** | **RULED: name match.** The finding is not that the join is a string; it is that nothing checks the string resolves until Gate 10. Both halves fix at Gate 1/2 with no schema change. **P-10 is M.** The id is deferred, and what would justify it is recorded: two humans sharing a display name, or a rename orphaning a reference — **neither has happened.** |
| 5 | **AnimaForge** | **RULED: zero for V1**, and now a ruling rather than an inference from silence. Reopening condition recorded. **P-14 carries it.** |

**New, and it does not block distribution:** **[GAP-5]** — whether SimForge holds domain
certifications for `administration`, `banking` and `operations`. **P-04's first task.** If it
holds none, P-04 still ships and C stays blocked on a different, honest thing.

---

## Self-audit

- ☑ Every task in the attachment appears in Part 1 — A0, A1, A2, B, C, D, E×3, F×6, G×4, H
- ☑ Out-of-scope items marked with reasons
- ☑ Every shared file appears in Part 2 with a strategy
- ☑ No two parallel packages modify the same file — `broker/simforge.py` serialized P-03→P-04;
  `validator.py` serialized P-09→P-10; `provisioning.py` sole-owned by P-03 then P-10;
  `scenarios.py` sole-owned by P-05 now that ADR-0049 needs no build
- ☑ Dependency graph is a DAG — verified; P-10 and P-11 are the only multi-parent nodes and
  every parent is upstream
- ☑ Merge order respects dependencies
- ☑ P-00 defined, with what must land first and an explicit note that no interface file is
  needed
- ☑ Per-package template is paste-ready in a single fenced block
- ☑ Merge protocol forbids parallel merges and force-pushes
- ☑ Package count justified — **15, not 30**, and the reason is stronger after revision: the
  critical path got longer, not wider
- ☑ Five gaps: three resolved, one deliberately taskless (B4), one new and non-blocking
- ☑ **Revision 1's five errors listed in §0.2 rather than absorbed silently**
