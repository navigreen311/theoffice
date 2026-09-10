# P-04 — PREDICTION, written before any code

**Written 2026-09-09, before the first line of `broker/simforge.py` was edited.
Nothing above the line is edited afterwards. The score is appended below it.**

Package: P-04, the unit-B department submitter. Branch `feature/p-04-unit-b-submitter`.
Private database: `theoffice_test_p04`, created and migrated to head for this package.

---

## What I claim before building it

### 1. Unit B does not involve `submit_curriculum`. It is `run_start` alone.

Read off SimForge, not off the names:

* `ForgeOperationCurriculum.instruction_set_ref` is an `InstructionSetRef`, whose
  `module_id: str` is **required and non-optional**. A department-scoped curriculum is
  not expressible in the payload at all.
* `CertificationUnitRequest` does carry `unit_type="department_context"` and
  `department_id` — and SimForge's `submit_curriculum` reads **exactly one field** out
  of that list: `{u.module_id for u in body.certification_units_requested if u.module_id}`.
  `unit_type`, `department_id`, `forge_context` and `venture_context` are consumed by
  nothing in the endpoint.
* The endpoint's only write is `ForgeInstructionSet`, keyed `(forgeId, moduleId,
  contentHash)` — module-scoped.
* `unit` does not appear on the curriculum payload at all. It appears on
  `OperationRunStartRequest`, which already takes `unit="B"`, `rubric_kind="domain"`,
  `department_id` and a null `module_id`.

**Prediction:** the unit-B path is `run_start` + a `curriculum_submission` correlation
row, and calling `submit_curriculum` for a department would either 422 on a missing
`module_id` or, worse, upsert an instruction set under a fabricated module name.

### 2. The blocker B32 names is on the wrong table, and it is the sixth Caveat-14 error.

B32's central consequence — *"P-04 cannot be satisfied … one cannot be created for
`Administration` or `Banking` while SimForge's `Department` table lacks those rows —
`DeptCert` has a real foreign key to it"* — hangs on `DeptCert`.

**Unit B does not write `DeptCert`.** The operation-certification gate-result callback
writes `OperationCertification(unitType="department_context", departmentId=...)`, whose
`departmentId` is `String, nullable=True, index=True` with **no ForeignKey**.
`recert.py` says it in one line: *"The domain cert table (AgentCert/DeptCert) is a
different table and is never touched here."* `DeptCert` is the 8-dimension domain
lifecycle, issued through `POST /api/certs/dept` behind `require_role`, requiring ≥N
covering `AgentCert`s and a dept-wide scenario run.

**Prediction:** zero `DeptCert` rows is true and does not block unit B. The real reason
a Burkham department cannot be certified today is different, and named in §4.

### 3. What I will build

One unit-B `run_start` per **(department, forge)** pair, where `department` is
`position.source_department` and `forge` is a Forge whose modules that department's
positions operate — the same two keys `generators/appointment.py::_unit_b_certs` queries
on. `submission_unit(None)` is **called**, never restated, and returns `("B", "domain")`.

The correlation row is a `curriculum_submission` with `department` set and `module_id`
**NULL**, carrying `simforge_run_ref`, so `overdue_submissions` — which already selects
`department` — hands it to P-03's sweep. I do not enter the sweep.

### 4. What I predict will NOT work, and I will ship anyway

* **No unit-B verdict can arrive today.** Nothing calls SimForge's
  `POST /api/operation/gate-result` with `department_outcomes` for an Office-opened run,
  and that route is not on the Office bridge (`MODULES` binds `gate_result`,
  `submit_curriculum`, `run_start` and nothing else). So a unit-B run opens, sits
  `IN_PROGRESS`, and reads `TIMEOUT` once its window passes.
* **Even a PASS could not be recorded.** `sweeps._ingest_one` recovers
  `forge_api_version` only when `unit == "A"`, so a unit-B row reaches
  `certification.record_result` with `forge_api_version=None`, and the
  `certified_records_its_basis` guard refuses a `certified` row without one. A unit-B
  PASS would land in `findings["refused"]` and turn the whole sweep `failed`.
  I predict this is the real successor blocker and that it is one line away from an
  answer — `forge_registry.api_version` is exactly "the Forge's api version" for a
  department × forge unit — but `broker/sweeps.py` and `broker/certification.py` are
  P-03's and out of scope, so I will name it rather than reach for it.
* Therefore `missing_unit_b` stays the correct refusal at Gate 4.5, and
  `appointment.generate` will keep refusing every Burkham candidate. **That is the true
  statement this package is for.**

### 5. Frictions I predict I will hit

* `curriculum_submission` carries `CHECK (scenario_count > 0)` and
  `CHECK (coverage_denominator > 0)`. A unit-B run carries **no Office scenarios**, so
  the honest wire value on `run_start` is `scenario_count=0` — Gate 8's own precedent
  (*"Zero is the honest value and it is visible as one"*). The row cannot hold 0.
  I predict I will resolve this without a migration by recording, in the row, the count
  of what The Office actually sent for that department on that Forge — the accepted
  per-module submissions' scenarios — and by **refusing to open a unit-B run at all**
  when that count is zero, rather than clamping it to 1.
* `unit_targets_match` and `rubric_matches_unit` are constraints on **`certification`**,
  not on `curriculum_submission`. The submission table has no unit constraint at all —
  both `module_id` and `department` are nullable with no CHECK. So the tests the card
  asks for have to be written against the `certification` row the sweep writes, not
  against the submission row. I predict I will write both.
* Two existing tests in `tests/provisioning/test_simforge_handover.py` assert that
  **every** Gate 8 submission row names a module and every opened run is unit A. Those
  assertions are the exact falsehood this package removes. I predict I will amend them
  to scope themselves to the unit-A rows, and flag the amendment in the PR.

### 6. Numbers I predict

* Baseline on `theoffice_test_p04`: **1315 passed, 0 failed** (P-00's recorded baseline).
* After: **1315 + the new tests, 0 new failures.** I predict 6–9 new tests.
* CI: six green, Smoke alone red, unchanged. Nothing here touches V11, V22, V32 or V33.

---
## SCORED AFTER — nothing above this line was edited

**Scored 2026-09-09, after the build. Nothing above the line was edited.**

### 1. Unit B does not involve `submit_curriculum` — RIGHT, and it was the whole design

Confirmed on the receiving side, and it is what the package was built to.
`ForgeOperationCurriculum.instruction_set_ref.module_id` is required; SimForge's
`submit_curriculum` reads only `module_id` off `certification_units_requested`; the
endpoint's one write is a module-keyed `ForgeInstructionSet`. The unit-B path is
`run_start` and the correlation row and nothing else, and
`test_no_curriculum_is_submitted_for_a_department` asserts it as an absence rather than
as a shape.

### 2. B32's blocker is on the wrong table — RIGHT, and it is the sixth Caveat-14 error

`OperationCertification.departmentId` is `String, nullable=True, index=True` with no
foreign key, and it is what a unit-B gate result writes. `DeptCert` is untouched by the
entire operation-certification path — `recert.py` says so in a sentence and
`grep department_context` across `apps/api/src` returns nine hits, none of them near it.
Zero `DeptCert` rows is true and does not block unit B.

### 3. What I built — RIGHT, with one addition I did not predict

The (department, forge) grouping, the `submission_unit(None)` call and the correlation
row all landed as predicted. **What I did not predict was the ref collision**: without a
department segment, two departments operating the same module set on one Forge mint one
ref, `open_run` is idempotent on it, and P-03's sweep would write two certifications out
of one verdict. That is a defect the package would have shipped. `mint_run_ref` gained an
optional `department` and `test_two_departments_on_one_forge_do_not_share_a_run` proves
Greenstone actually contains that case.

### 4. What would not work — RIGHT, both of them, and the second is now locked

No unit-B verdict can arrive (the gate-result callback is not on the Office bridge), and
a unit-B PASS could not be recorded if one did (`forge_api_version` is recovered only for
unit A). Both hold.
`test_a_unit_b_pass_is_refused_rather_than_certified_without_a_basis` locks the refusal so
the day somebody rules where a department's Forge api_version comes from, the test says
the behaviour changed on purpose. `missing_unit_b` is still the correct refusal, and
`test_a_department_with_no_unit_b_certification_is_refused_not_appointed` asserts exactly
that against the real generator.

### 5. Frictions — one RIGHT, one HALF WRONG, and the half-wrong one is the interesting one

**`unit_targets_match` is on `certification`, not on `curriculum_submission` — RIGHT.**
The submission table has no unit constraint at all and both columns are nullable, so the
card's test ("a unit-B submission ... satisfying `unit_targets_match`") names a constraint
that cannot be exercised on the row it describes. Both tests were written: the submission
row is asserted directly, and the constraints are exercised on the `certification` row the
sweep writes, by handing PostgreSQL rows that break each one.

**The `scenario_count > 0` friction — RESOLVED DIFFERENTLY FROM THE PREDICTION.**
I predicted sending `scenario_count=0` on the wire and recording the department's real
count in the row. I sent the same number on both instead, and the reason changed my mind
during design: `run_start`'s `scenario_count` for a unit A is the scenarios The Office
submitted that the run's unit covers, and the exact analogue for a unit B is the scenarios
it submitted for that department's accepted modules on that Forge. Two different values
under one field name would have been a Caveat-14 trap for the next reader — the same
number, aggregated over the unit's own key, is one answer to one question.

**The refusal I predicted survived**: a department with nothing accepted gets no run and
no row rather than a count clamped to 1, and that case has its own test. **No migration
was needed and 0035 is unclaimed.**

### 6. Two existing tests would need amending — WRONG, it was four

`test_an_accepted_handover_stores_the_run_ref`,
`test_the_timeout_sweep_can_now_resolve_a_submission`,
`test_gate_8_populates_simforge_run_ref_on_the_stored_row` and
`test_the_ref_gate_8_mints_is_derived_from_the_submission`. Each asserted "every row names
a module" or "every run is unit A" — true of every row that had ever existed and not a
property of Gate 8. Each is scoped to its unit rather than widened; the last one was made
stronger, recomputing both units' refs from their own rows.

### 7. Numbers — baseline RIGHT, test count UNDER-PREDICTED

* Baseline on `theoffice_test_p04`: **1315 passed, 0 failed**. Predicted exactly.
* New tests: **17**, against a predicted 6-9. Under by roughly half, and the excess is
  the ref collision, the four amendments and the successor-blocker lock — none of which
  the prediction knew about.
