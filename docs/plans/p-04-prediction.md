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
