# P-15 — the run_ref contract. PREDICTION.

Written 9 September 2026, before any source file was changed, on branch
`feature/p-15-run-ref-contract` off `main @ 8d526b1`. Everything above the scoring line
stays as written; the score is appended below it.

Private database: **`theoffice_test_p15`**, created for this package and migrated from
zero to head. CAVEAT 15 — a contended suite is indistinguishable from a broken branch,
so this package shares its database with nobody.

---

## What I believe is true before I start

### The premise I have been handed, and the one part of it I doubt

The package brief says SimForge's `/run/start` is behind
`require_role("compliance_analyst")`, that The Office calls with its tenant credential,
and that a refusal is the finding. **I predict that route is not the one The Office
should call, and that the credential question does not arise.**

Reason, from the receiving side rather than from the names (CAVEAT 14):
`submit_curriculum` already posts to `{base_url}/submit_curriculum`, and SimForge mounts
its Office adapter at `/office` with a single catch-all `POST /{module_id}`. `run_start`
is bound in that adapter's `MODULES` dict. So `{base_url}/run_start` is the *same
surface, same credential, same footing* as the hand-over — which is exactly what
`NOT_AGENT_FACING` already says it is ("on the same footing as the hand-over that
precedes it"). `require_role("compliance_analyst")` guards `POST /api/operation/run/start`,
a route The Office has no reason to touch.

**Prediction 1: run_start succeeds on the tenant credential, and there is no
authorization finding.** If I am wrong, the finding is reported, not worked around.

### What SimForge actually returns from `submit_curriculum`

Read off `apps/api/src/routers/operation.py`, not off P-01's summary:
`accepted`, `module_levels`, `module_declared_absences`, `never_do_obligations`,
`coverage_declaration`, `gate_9_5_flag`. **No `run_ref`. No `scenario_count`. No
`rejected_reason`.**

**Prediction 2: the five undeclared fields P-01 measured are exactly the six above minus
`accepted`, which the manifest already names.** I expect no seventh.

### The `run_ref` entry in the manifest

The brief says the manifest should "stop requiring `run_ref`". **Prediction 3: it never
required it** — `validate_response` is field-set equality *in the unexpected direction
only*, so a manifested field that never arrives changes nothing. The requirement lived
entirely in `SimForgeClient.submit_curriculum`'s `raise`.

**Prediction 4: I will not be able to delete `run_ref` from the `submit_curriculum`
manifest entry anyway**, because `tests/golden/stub_simforge.py::HONEST_SUBMIT` carries
it and `test_honest_responses_satisfy_the_manifest` would fail — and that stub is not on
my allowed-modify list. So the honest change is to *re-document* the field, saying it is
not what The Office correlates on and is not expected to arrive. Removing a name from an
allow-list is a tightening; leaving it is not a weakening.

### A new endpoint means a new manifest section

**Prediction 5: `run_start` needs its own manifest entry** — `manifested_fields` raises
on any endpoint the manifest does not name, so `validate_response("run_start", ...)`
cannot run without one. Fields: `run_ref`, `unit`, `started_at`, `window_minutes`,
`already_open`, read off `OperationRunStarted`.

### The ref must be deterministic, and this is the part I expect to be argued with

SimForge's `open_run` is idempotent on `run_ref` and answers `already_open: true` with
**the clock untouched** — ADR-0044, so that a retried hand-over cannot extend the window
of a run that is already hanging. A freshly minted uuid on every retry would defeat that
control from the caller's side: two runs, two windows, and the second one young.

So the ref is derived from the submission's natural key — venture, forge, module, and
the instruction content hash — which is the same key SimForge upserts the instruction set
on. **Prediction 6: a re-run of Gate 8 against an unchanged instruction lands on the same
`run_ref`, and a changed `content_hash` mints a new one.** That is not an accident of the
format; it is the reason for it.

### What happens when `run_start` fails

**Prediction 7: I will store NULL, not the ref.** A ref SimForge never heard of
correlates to nothing — the sweep would poll `gate_result` and take 404 forever. The
existing invariant in `_submit_one_module` is `run_ref is not None ⟺ this landed`, and
`handed_over_to_simforge` is already documented as "true only when every module SimForge
was asked about answered with a ref". Opening the run is now part of landing.

---

## What I predict will break

1. **`tests/provisioning/test_simforge_handover.py`** — four tests. Its fakes
   (`SimForgeAccepts`, `SimForgeIsDown`, `SimForgeRefuses`) implement
   `submit_curriculum -> str` and none implements `run_start`. Every one of them fails
   once the client returns a body and Gate 8 opens a run. This file is the test file for
   the code I am changing and sits in a directory I am permitted to write in; I will
   update it and flag it explicitly in the PR as the one judgment call against the
   allowed list. Leaving it as-is would be a false red, and contorting production code to
   keep a stale fake passing would be worse.
2. **Possibly `tests/provisioning/test_pipeline.py`** if it drives Gate 8 with a fake.
3. Nothing in `tests/golden/` — the manifest gains fields and an endpoint, and gains no
   name matching a forbidden fragment, so `test_no_manifested_field_name_matches_a_forbidden_fragment`
   and `test_every_manifested_field_declares_a_purpose` should both still pass. **Prediction 8.**

**Prediction 9: the collected count rises by 6–10** (the four required tests plus the
cases that prove the control was not weakened), and no test outside
`tests/provisioning/` changes verdict.

## The one I am least sure of

`module_declared_absences` and `never_do_obligations` echo back **prose The Office
authored** — a `not_applicable` reason and a never-do line. `assert_no_scenario_content`
recurses into a manifested field's value and fires on anything ≥200 chars / ≥30 words.
**Prediction 10: a long enough authored reason will trip the prose tripwire on a field
that is legitimate.** If it does, the right answer is the one the docstring already gives
— narrow the field, not widen the check — and it is a finding for whoever authors those
reasons, not a licence to relax anything here.

---

## SCORING LINE — nothing above this is edited after the fact
