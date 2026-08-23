# The Seven Generators — Phase 3, increment 2

Master prompt Part 5. **Deterministic transformers: same Pack in, same artifacts out.**

There is no LLM in `generators/` at all. Structural generation must be reproducible or
the golden snapshots are theatre — a diff that only sometimes appears is a diff nobody
investigates.

| # | Generator | In | Out |
|---|---|---|---|
| 5.1 | Role Definition | Pack | positions fully specified, implied compliance flags resolved |
| 5.2 | Appointment | positions + roster + certification | named agents + the three capacity numbers |
| 5.3 | Workflow | lifecycle stages + positions | ordered steps: module, flag-or-NONE, escalation |
| 5.4 | Task Ledger | Workflow + Appointments | tasks + projected approvals per human role |
| 5.5 | Curriculum | Pack + Workflow + Instructions | Scenario Pack with coverage denominators |
| 5.6 | Forge Manifest | bindings + Workflow + Ledger | BOM + three-way reconciliation |
| 5.7 | Runtime Config | all above | idempotent deployment |

## Determinism

- **No `uuid4`.** `grant_id` and `task_id` are UUIDv5 over their natural key, which
  makes 5.7's idempotency structural rather than a code path someone must remember.
  A test greps every artifact for a v4 UUID and fails if one appears.
- **No wall-clock timestamps inside artifacts.**
- **Every collection sorted by an explicit key.** Postgres promises no ordering without
  `ORDER BY`, and a snapshot that passes locally and fails in CI teaches people to
  re-record snapshots rather than read them.

Snapshots live in `tests/golden/snapshots/`. Re-recording requires `UPDATE_GOLDEN=1`,
and the failure message says so.

## Why the snapshots earn their keep

A generator regression that silently alters an appointment roster produces a
**plausible-looking wrong answer**. Nothing crashes, nothing logs, the JSON reads fine.

That is not hypothetical here. Reading the first recorded snapshot is what caught the
cross-Forge bug below.

## Finding: a position can span Forges

Greenstone's Acquisition Analyst operates `property_lookup` and `comp_analysis` on
**CRE Forge** and `place_call` on **VoiceForge**. Certification Unit A is
`agent x forge x module`.

The first version of 5.2 took a single `forge_id` and checked every module against it.
Result: `place_call` was never certifiable, and two of three positions came back empty
with `reason: never_certified` — which reads exactly like a certification backlog.
Nothing failed. The artifact was valid JSON describing a venture with nobody in it.

Fixed by resolving `module -> forge` from the registry and threading it through 5.2, 5.4
and 5.7. Unit B is now required for **every Forge the position touches**, not one
nominated "operating Forge".

**There is deliberately no `forge_id` override in the pipeline.** The registry is the
only authority on which Forge owns a module; letting a caller assert otherwise would let
a venture certify an agent against the wrong Forge and never notice.

## Finding: Gate 2 capacity is the optimistic estimate

**Greenstone passes V13 at Gate 2 and fails it at Gate 4.5.**

V13 at Gate 2 estimates approvals from Pack headcount — it is all it has, because the
workflow does not exist yet. The Task Ledger computes the real number from the real
workflow. For Greenstone as authored those disagree by an order of magnitude:

```
GATE 4.5 V13 FAIL: compliance_officer: 192 approvals x 6 min = 1152 minutes
                   against 144 available
```

Neither check is buggy. This is exactly why the blueprint puts a second capacity gate
after the generators run, and Gate 4.5 now implements it — resolving V24 (unfilled
positions) at the same time, since that is appointment output too.

**Greenstone as authored is not staffable.** The fix is to raise a trust-tier ceiling,
add reviewer coverage, or reduce scope — not to lower the utilisation factor.

## Generator notes

**5.1** derives `implied_compliance_flags` from `forge_module_registry`, kept separate
from `declared_compliance_flags`. An author who omits `recording_consent_required` from
a position that operates `place_call` has not escaped Nevada's two-party consent
statute, and the gap between the two lists is itself the finding.

**5.2** never fills a position with an uncertified agent, names the specific shortfall
reason per candidate (`never_certified` is not `in_training` is not `missing_unit_b` —
three different fixes), and reports all three §7.2 capacity numbers. A shortfall flags
to Ivan; it does not auto-reject the Pack, auto-appoint, or reduce scope.

**5.3** needs `Position.lifecycle_stages_owned` — **schema divergence #3**. Nothing in
schema v3 maps a position to a stage, and without it the generator can only guess.
Stage order is the author's; a workflow running Close before Source is not a workflow.
Compliance flag is a flag or the literal `NONE`, never blank.

**5.4** emits a task for an unfilled position with `assigned_agent: null` rather than no
task — the work still exists, and hiding it makes the shortfall invisible downstream.

**5.5** keeps domain and operation scenarios separate (Part 10.1: two rubrics, never
merged) and binds every operation scenario to its `instruction_content_hash`, which is
what makes certification staleness computable.

**5.6** fails on `REQUIRED_NOT_DECLARED` rather than auto-declaring the missing module.
Silently adding it would let a workflow grant itself access to any Forge module by
referencing one, inverting the point of a Bill of Materials.

**5.7** consumes the **Manifest, not the Pack**, so a Pack that would provision and a
Manifest that would not cannot disagree. A blocked reconciliation produces a config with
**zero grants**, not grants plus a warning. `apply()` is the only writer; `generate()` is
pure so the config is reviewable at Gate 4 before anything touches the database.

## Run

```bash
.venv/Scripts/python -m pytest tests/golden -q
UPDATE_GOLDEN=1 .venv/Scripts/python -m pytest tests/golden -q   # re-record, then READ the diff
```

## Known gaps

- **Volumes are guesses.** `DEFAULT_DAILY_VOLUME_PER_HEADCOUNT = 8` and the SLA table
  are placeholders. The Gate 4.5 failure above is only as real as that number.
- **Nothing runs the pipeline in production.** `run_all` exists and is tested; wiring it
  to Gates 3–11 with human sign-off is not built.
- **Shift assignment and PHI flush** are increment 3.
- **The roster is seven fixtures**, not the 106 real agents (Phase 0.2).
