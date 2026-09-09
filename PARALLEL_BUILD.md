# PARALLEL_BUILD.md — baselines, caveats and the merge ledger

**Owned by P-00 (coordinator). Every other package reads it; only the coordinator writes
it, except the merge ledger row appended at each merge.**

Established 2026-09-08. Authoritative for **what the board looked like before this run
started**. Every package's gate is measured against what is recorded here.

---

## TWO THINGS THIS RUN RESTS ON

*Reproduced verbatim from `docs/coordination-plan.md` (Revision 6). If these two
paragraphs and the plan ever disagree, the plan is authoritative and this file is stale —
say so rather than reconciling them quietly.*

> **1. The scenario contract is the whole run.**
>
> Workstream B exists because The Office and SimForge never agreed what a scenario is.
> `docs/scenario-contract.md` is that agreement, landed by P-00 and frozen thereafter.
> P-03 and P-05 never talk to each other — they only talk to that file. If it is wrong,
> both build correctly against different shapes, both pass their own tests, and the
> mismatch stays invisible until P-06/07/08 try to pour eleven modules of authorship into
> an interface that does not fit. **That is the worst-timed failure available in this run:
> it surfaces after the critical path is spent, and the work it wastes is the authorship.**
>
> If you believe the contract is wrong: **STOP and escalate. Do not edit it. Do not work
> around it.**
>
> **2. `theoffice`'s red `main` is deliberate.**
>
> The Smoke job fails because V11 and V32 report NOT_RUN in CI, where no runner can reach
> a Forge. That is `docs/decisions.md` entry 3's accepted precedent — a control knowingly
> merged while green nowhere, written down as a precedent precisely so a later reader would
> not mistake it for neglect.
>
> **Do not fix it. Do not weaken V11, V22, V32 or V33 to make Smoke green.** Doing so
> destroys the thing this run exists to establish, **and it would look like progress** — a
> green board, a closed job, a commit that reads like a cleanup.
>
> The gate everywhere is **no NEW failures against the P-00 baseline.** Never a green
> board, which is not available.

---

## CI BASELINES — recorded 2026-09-08

**Every package compares its results against the rows below.** The gate is **no NEW
failures**, never a green board.

### theoffice — `main` @ `8a4ae66`

**Authoritative run: [`34263050339`](https://github.com/navigreen311/theoffice/actions/runs/34263050339)**
— "Merge pull request #40 from navigreen311/chore/coordination-plan", push to `main`,
2026-09-08T18:26:30Z. **Conclusion: failure.** This is the run at `main` HEAD.

```
X main CI · 34263050339
✓ No committed secrets            5s
✓ Console                        52s
X Smoke - the console actually renders   4m10s   <-- the only failing job
✓ Lint and types                 25s
✓ Tests                        1m39s
✓ Migrations are reversible      41s
✓ Images build                  3m3s
```

Smoke's failure, verbatim from `gh run view 34263050339 --log-failed`:

```
rule(s) ['V11', 'V32'] did not run. NOT_RUN is not a pass - this Pack has not been validated.
a stopped run says what did not run because of it
unevaluable rules are counted separately from passes
FAIL unevaluable rules with no gate named: ['V11', 'V32']
instructions are real and V11 says NOT_RUN
8 check(s) failed
##[error]Process completed with exit code 1.
```

**The eight failing checks, in full**, so a downstream package can diff against the list
rather than against the count:

```
FAIL the Gate 4 review form did not render
FAIL the review form rendered without the artifacts summary above it - that is a rubber-stamp machine
FAIL detail page lost: This gate waits. It does not pass on its own, and nothing ad
FAIL detail page lost: Runs from gate 4 until a gate stops it. Gates are not skippa
FAIL detail page lost: Required. Recorded against your name in the append-only log.
FAIL the raw evidence is gone entirely - engineers need it
FAIL recording a review and advancing are still two unrelated controls
FAIL unevaluable rules with no gate named: ['V11', 'V32']
```

**Read the causal chain before diagnosing any of these.** Only the last one is about V11
and V32 directly. The other seven are Gate 4 console checks that fail **because the run
never reached Gate 4** — V11 and V32 report NOT_RUN, Gate 2 blocks, and the ladder stops.
They are downstream of the deliberate red, not seven separate defects. **A package that
"fixes" one of them has almost certainly changed something it should not have.**

**Prior confirming instance:**
[`34187594670`](https://github.com/navigreen311/theoffice/actions/runs/34187594670) —
"SimForgeClient, and Gate 8 hands over per module (#36)", 2026-09-08T04:36:34Z, failure,
**identical shape**: six of seven jobs green, Smoke alone red, same V11/V32 NOT_RUN text,
same `8 check(s) failed`. Two runs thirteen hours and four merges apart producing the same
failure is what makes this a baseline rather than a snapshot.

*(Runs `34262589294` (#37), `34262602207` (#38) and `34262616438` (#39) were all
**cancelled** by the next push before completing. They are not baseline evidence and
should not be quoted as such.)*

#### theoffice local suite — a second baseline, and it is NOT a substitute for CI

**Corrected 2026-09-08 after P-00's first PR was handed back. Read this before predicting
a CI result.**

**Without a database** — the state of a fresh clone with no `.env`:

```
376 passed, 540 skipped, 59 errors
```

All 59 are `AssertionError: OFFICE_ADMIN_DSN not set` at `tests/conftest.py:182`, and the
540 skips are `requires_db`. **This configuration is not evidence about anything.** It
does not run the golden snapshots, the contract tests, the isolation suite or the ledger
suite — which is to say it does not run the tests most likely to notice a generator
change.

**With a database** — the real local baseline, and the one to compare against:

```
974 passed, 1 failed
FAILED tests/isolation/test_sweeps.py::test_restore_drill_restores_and_verifies_the_chain_in_the_copy
```

**That one failure is pre-existing and environmental.** Verified on `main` @ `8a4ae66` and
on `feature/p-00-coordinator`, same container, minutes apart, identical. CI's Tests job is
**green**, so this failure is local-only — do not chase it and do not report clearing it.

*(Running `tests/golden/test_generators.py` alone also fails
`test_runtime_config_apply_is_idempotent`, on `main` as well as on any branch. It is
order-dependent and passes in a full run. Another reason to compare full-suite totals
rather than single-file runs.)*

#### How to get that database — every package in `theoffice` needs it

`.env` is on the always-forbidden list, so this is shell environment only, and it matches
CI's service container exactly (`postgres:16`, the blueprint target; local development
runs 17.x and the pin is deliberate). Pick a port nothing else is on:

```bash
docker run -d --name p00-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=theoffice -p 55439:5432 postgres:16

export OFFICE_APP_PASSWORD=ci-office-app-not-a-secret
export OFFICE_ADMIN_DSN="postgresql://postgres:postgres@127.0.0.1:55439/theoffice"
export OFFICE_APP_DSN="postgresql://office_app:ci-office-app-not-a-secret@127.0.0.1:55439/theoffice"
export STUB_FORGE_TOKEN=stub-forge-test-token

python -m alembic upgrade head          # migration 0002 creates the office_app role
# then the two ensure_ledger_partition() calls from ci.yml's "Ledger partitions" step
python -m pytest -q
```

### THE FINDING: a package whose local suite cannot run has no evidence about CI

**P-00's first PR predicted "Smoke red on V11/V32, all six other jobs green." Two jobs were
red. `Tests` failed on the curriculum golden snapshot, which the DB-less local suite skips
by construction.**

The prediction was not careless about the tests — the suite had been run, twice, on both
branches, and the numbers matched. **It was careless about what the suite covered.** 540
skips and 59 errors was recorded in this very file as "not a CI result", and then a CI
result was asserted anyway a few paragraphs later. **"Expect green" was a prediction stated
as an observation**, and the words that would have caught it were already written down.

The general form, which is worth more than the fix: **the absence of a failure in a suite
that did not run the relevant test is not evidence of anything.** It is the same shape as
NOT_RUN not being a pass — the thing this entire run exists to establish — arriving one
level down, in a local terminal, wearing a green number.

**CI has a control for exactly this.** The Tests job carries a step named *"Refuse a green
run that skipped the database suite"*, whose comment reads: *"`requires_db` skips every
database test when the DSNs are unset or wrong, and a skipped test is reported as a pass by
every summary."* The control exists, it works, and it did not help — **because it runs in
CI, and the claim was made before CI ran.** A control cannot catch a prediction.

**The rule for every package here: do not describe an expected CI outcome in a PR
description. Open the PR, let CI run, then write what it did.** If you must predict, say
"predicted" in the sentence.

### simforge — `main` @ `5e83cdd`

**[`34188122387`](https://github.com/navigreen311/simforge/actions/runs/34188122387)** —
"Correct the pack-level-unit claim, record entry 18, index ADR-0048 (#132)", push to
`main`, 2026-09-08T04:45:27Z, 2m27s. **Conclusion: success.**

```
✓ main ci · 34188122387
✓ api        2m24s
✓ validator    14s
✓ web         1m1s
```

The five most recent `main` runs are all success. **simforge's baseline is green, and P-02
and P-03 are therefore held to green.** A red job in either package is a new failure with
nothing to hide behind.

### capitalforge — **`master`**, not `main`, @ `25bd359`

**The default branch is `master`.** `gh run list --branch main` returns zero rows in this
repo, and that is the absence of a branch, not the absence of CI. **P-01 branches from
`master` and compares against `master`.**

**[`33907801375`](https://github.com/navigreen311/Capitalforge/actions/runs/33907801375)**
— "Merge PR #89: the Office adapter, eleven modules, and a holding refusal on credit-union
placements", push to `master`, 2026-09-04T18:47:50Z, 28m2s. **Conclusion: success.**

```
✓ master CI · 33907801375
✓ Lint & Type Check     2m5s
✓ Detect docs-only change  7s
✓ Browser Tests       23m45s
✓ Unit Tests            1m1s
✓ Integration Tests     1m7s
✓ Build                 2m4s
```

**Note the 23m45s browser job** — a capitalforge CI round trip is roughly half an hour, not
three minutes. Budget for it rather than reading a slow run as a hung one.

The local checkout sits on `ai-fix/one-bureau-per-pull` @ `ea6991b`, two commits ahead of
the `25bd359` master merge; its PR run
[`34149692614`](https://github.com/navigreen311/Capitalforge/actions/runs/34149692614) is
also success. **capitalforge's baseline is green.**

**Read the plan's "never a parallel merge into any `main`" as "into any default branch."**
For capitalforge that is `master`. The rule is about serialising merges, and a repo that
spells its default branch differently is not exempt from it.

---

## CAVEAT 1 — Gate 2 will not pass this run, by ruling

**A red V22 at the end of this run is the expected result. It is not an incomplete
package, and it is nobody's bug to fix.**

Ruling **T-080**: `referral_fee_permitted_in_state` stays declared. Some declared
obligations are held by humans, not agents. Deleting the flag to green the gate would
assert the obligation does not exist — see `docs/decisions.md` entry 24 and
`docs/blocking.md` B18.

Because Gate 2 stays blocked, the ladder cannot reach Gate 5, `runtime_config.apply` never
runs, and **workstream E does not happen. E is blocked by a ruling, not by packages.** No
package is late because E did not run.

**This run does not end in a simulation. It ends in a red gate with one failure that is
supposed to be red.**

**And the converse, which is the dangerous direction:** a **green** Gate 2 at the end of
this run means something went wrong — most likely that somebody deleted the flag to make a
check pass. **Treat an unexpected pass as a defect, not a win.** Write the expected result
down before running the check, then compare; do not form the expectation after seeing the
output.

---

## CAVEAT 2 — the certification caveat

*From the plan's OUT OF SCOPE section; `docs/blocking.md` B4.*

**The first certifications will be issued by a system certifying against instructions it
received from the system being certified.** SimForge grades The Office's agents against a
curriculum The Office authored and handed over. That circularity is real and it is not
resolved by anything in this run.

**SimForge's own `gate_result` certification is a human-issued bootstrap** — it was issued
by nothing, and could not have been otherwise, because the first certifier has no
certifier.

**It is retired only by a scenario pack run by a *different* SimForge instance.** Not by
more scenarios, not by better scenarios, and not by anything in this run.

**Carried here as a reading caveat, not as work.** It is on nobody's card. What it changes
is how a cert issued this month should be read: as evidence the machinery runs end to end,
**not** as independent assurance about an agent.

---

## CAVEAT 3 — a validator verdict that changes is not a validator verdict that improved

**Read the clause, not the absence of a FAIL.**

A rule that stops saying FAIL has not necessarily started saying anything better. The
worked example is P-12, and it is the reason that package's deliverable is the write-up
rather than the one-line YAML change:

**Greenstone's V32 goes FAIL → NOT_RUN, and that is not movement.** The FAIL was about a
module that does not exist. The NOT_RUN is about Forges nobody can ask. **The second fact
was always true — it was hidden behind the first**, and removing the first is what makes it
visible. **Greenstone's Gate 2 is exactly as far from passing as it was.**

This is the inverse of `docs/decisions.md` entry 22 and belongs in the same family: there a
quiet truth was replaced by a loud falsehood; here a loud truth is replaced by a quiet one.
**Both make the reader worse off, and only one of them looks like a problem.**

**The operational rule:** when a verdict changes, read the sentence after it. V11's verdict
is one word and its cause is the sentence following, and that is exactly how a curriculum
rule failing on a missing credential was misread as an unfinished curriculum for a week —
see `docs/blocking.md` B6's 2026-09-08 update. **The verdict is not the finding. The clause
is.**

---

## CAVEAT 4 — the contract lives in one repo, and two packages are bound by a file they cannot see

**`docs/scenario-contract.md` exists once, in `theoffice`. Ruled 2026-09-08.**

Absolute path, because the agents that need it work elsewhere:

```
C:\Users\ivann\Projects\theoffice\docs\scenario-contract.md
```

**P-02 and P-03 work in `simforge`, which does not contain the file that binds them.**
Their briefs must carry that absolute path. An agent that cannot find the contract will
build against `operation_payloads.py` and `scenarios.py` as they stand — which is building
against the current shape rather than the agreed one, and is the exact failure the contract
exists to prevent.

**Why not a copy in each repo.** Two copies of a contract in two repos is **a second copy
of a source**: frozen during the run by a rule, and free to drift the moment the run ends
and the rule stops applying. It is the same reasoning that leaves
`packs/burkham-wickmont.split.draft.yaml` uncorrected rather than maintained in parallel —
correcting a second copy is what starts maintaining a second copy.

**Anyone who wants a simforge-local copy is proposing a second source and should say so out
loud rather than adding a file.**

---

## CAVEAT 5 — the two-field escalation window on `CurriculumScenario` is deliberate

**Ruled 2026-09-08.** `generators/artifacts.py` deliberately carries **two** escalation
fields right now:

| field | type | status |
|---|---|---|
| `expected_escalation` | `bool` | **on its way out.** Live today, hardcoded `True`, deleted by P-05 |
| `expected_escalation_prose` | `str` | **canonical.** What the contract means. Empty until P-05 fills it |

**This is not a defect and it is not a duplicate to be tidied.** The type could not be
changed in place: `generators/curriculum.py:83` passes `True` and belongs to **P-05**, and
`broker/provisioning.py:774` reads it as a bool and belongs to **no package this run**. A
type change inside P-00's diff would have broken two files P-00 may not touch and would
have appeared as a NEW failure against the baseline this very file records.

**P-05 migrates `curriculum.py` onto the prose field and deletes the bool. Anyone who
collapses the two outside P-05 has broken a package boundary** — and will have done it in a
commit that reads like a cleanup, which is the recurring shape this whole run is built to
resist.

### Every reader of the bool, so P-05 inherits the list rather than re-deriving it

Grepped 2026-09-08 across `theoffice` at `8a4ae66`. **Two objects share the name
`expected_escalation` and they are not the same field** — that distinction is the most
important thing in this list.

**`CurriculumScenario.expected_escalation` (`generators/artifacts.py:239`) — P-05's
migration set, three sites:**

```
generators/curriculum.py:60      expected_escalation=s.expected_escalation   # copied from the Pack Scenario, domain scenarios
generators/curriculum.py:83      expected_escalation=True                    # hardcoded, every operation scenario
broker/provisioning.py:774-776   bool -> string widening for the SimForge submission
```

`broker/provisioning.py` is the one that matters and it is **outside P-05's card**. It
currently sends *"escalation is expected; the Office's generator does not say which"* when
the bool is `True` and `""` when it is `False` — the true statement available from a bool,
and the thing the prose field replaces. **P-05 cannot change it without an escalation.**

**`Scenario.expected_escalation` (`generators/pack.py:338`) — the Pack DSL, a DIFFERENT
class. NOT in the migration set:**

```
generators/validator.py:452      if s.expected_escalation:   # V23's truthiness check, reads pack.scenarios
generators/validator.py:467      the ">=1 expected_escalation per role" failure message
packs/burkham-wickmont.draft.yaml     15 scenarios, expected_escalation: true/false   (P-09)
packs/greenstone.yaml                  9 scenarios, expected_escalation: true/false   (P-12)
packs/burkham-wickmont.split.draft.yaml:457   comment only, never published            (P-09, header note only)
```

**V23 reads the Pack DSL's bool, not `CurriculumScenario`'s.** Had the type been changed in
place on the wrong class, V23's `if s.expected_escalation:` would have silently become "at
least one scenario with non-empty prose" instead of "at least one scenario expecting
escalation" — **a validator rule changing meaning with no diff to the validator.** Nothing
in this run touches V23, the Pack DSL, or the YAML booleans.

**Documentation references** (no code impact, listed for completeness):
`docs/pack-validator.md:373`, `docs/plans/phase3-pack-validator-PLAN.md:102`,
`docs/reference/master-prompt-v4.md:562` — all describing V23, all about the Pack DSL bool.

---

## CAVEAT 6 — the curriculum golden, and fifty-four empties that do not mean unfinished

**Any package that changes what a generator emits changes
`tests/golden/snapshots/greenstone_curriculum.json`, and the Tests job goes red until the
snapshot is re-recorded.** P-00 hit this; **P-05 will hit it harder**, because it changes
what the generator actually produces rather than only the fields available to it.

**Read the diff before re-recording. That is the substance; `UPDATE_GOLDEN=1` is the
trivial part.** The snapshot's own failure message says so, and re-recording a golden is
the single easiest way to bury a real regression: nothing crashes, the artifact reads fine,
and the wrong answer is plausible. **If the diff is not what you intended, stop and report
— do not re-record.**

The check that settles it in one line is `git diff --numstat`: a purely additive change has
**zero deletions**. P-00's was `108 0` — 108 insertions, 0 deletions, being exactly six new
keys at empty defaults across all 18 scenarios, with every pre-existing value byte-identical
including `expected_escalation`. A modified value would have shown as a deletion.

### The fifty-four empties, and why they are not a to-do list

`CurriculumScenario` backs both `domain_scenarios` and `operation_scenarios`, so the six
contract fields serialise onto **every** scenario. Greenstone's nine domain scenarios now
each carry six empty strings, and **nothing will ever fill them** — workstream C is closed
by ruling T-050 and a domain scenario is never submitted to SimForge.

**An empty string reads as "not yet filled in", not "does not apply here" — which is the
exact ambiguity ADR-0049 exists to remove.** Not a live defect today: nothing reads those
fields on a domain scenario. **It is the shape that becomes a defect when somebody counts**
— a coverage view or a completeness report will see nine incomplete scenarios and be wrong
in the direction that looks like work.

`docs/scenario-contract.md` §8 states which fields are operation-only and what emptiness
means per kind, and records the recommendation — that they probably should not be
serialised onto domain scenarios at all — as a question for Ivan. **It is deliberately not
implemented. Do not restructure the dataclass to fix it.**

---

## NUMBERING — two numbers in the plan are already taken

**P-00 merges first, so its appended records take the next free numbers and the plan's
forward references shift by one place.** Neither is a renumbering: nothing existing moved.

| the plan says | what to actually write | why |
|---|---|---|
| P-09 appends `docs/decisions.md` **entry 23** | **entry 25** | P-00 landed 23 (workstream C's deferral) and 24 (obligations held by humans) |
| P-12 appends `docs/blocking.md` **B18** | **B19** | P-00 landed B18 (the compliance-surface schema question) |

**P-09:** entry 25 must still supersede entry 5 explicitly, as the card says. The
requirement is about content, not about the number.

**P-12:** B19, still tagged `venture-scoped: greenstone`. The scope tag is now the
convention for every new item — see `docs/blocking.md`'s Scope section, widened by T-101.

---

## MERGE LEDGER

**Every merge appends one row, at merge time, by whoever merged.** Test results are
compared against the CI baselines above, never against green.

**A row is not complete without the comparison.** "Tests passed" is not a result in this
run; "Smoke red on V11/V32 as baseline, all other jobs green, no new failures" is.

| Package | PR | Merge SHA | Test results vs baseline | Timestamp (UTC) |
|---|---|---|---|---|
| P-00 | [#43](https://github.com/navigreen311/theoffice/pull/43) | `35bb8af` | run `34266438265`: **Smoke alone red**, its 8-check list diffed **byte-identical** to baseline `34263050339`; `Tests` green; six other jobs green. **No new failures.** One hand-back before merge — see below. | 2026-09-08T19:26:42Z |
| P-01 | [#94](https://github.com/navigreen311/Capitalforge/pull/94) | `81c2d95` | run `34270839863` **success**, same six jobs as baseline `25bd359`, no new failures. Log proves the new tests ran rather than skipping into green: `office-bridge-unmounted.test.ts (11 tests) 3674ms`. Purely additive, 437/0. | 2026-09-08 UTC |
| P-02 | [#133](https://github.com/navigreen311/simforge/pull/133) | `2337442` | `ci` `34270886088` **success** + `contract-tests` `34270886081` **success**; `742 passed, 2 skipped` vs local-before `708 passed`; +34 is exactly the new test file. Green baseline, no new failures. | 2026-09-08 UTC |
| P-03 | [#134](https://github.com/navigreen311/simforge/pull/134) | `2ce2f5d` | `ci` `34276557037` + `contract-tests` `34276557074`, **all four jobs green** (`api`, `validator`, `web`, `contract`). Green baseline, nothing green turned red. Local `767 passed, 2 skipped`; 25 added, no pre-existing test changed status. | 2026-09-08 UTC |
| P-05 | [#48](https://github.com/navigreen311/theoffice/pull/48) | `f32e70d` | run `34276249027`: Smoke alone red, 8-check list **string-identical** to baseline; six jobs green incl. `Tests` and `Images build`. Local `1025 passed, 1 failed` (the recorded environmental `test_restore_drill`). Four golden re-records, each predicted before `UPDATE_GOLDEN=1` and verified after. | 2026-09-08 UTC |
| P-06 | [#52](https://github.com/navigreen311/theoffice/pull/52) | `85e5a76` | run `34278884205`: Smoke alone red, failing-check list **byte-identical**; six jobs green. Diff `541 / 0`. Greenstone golden did not move — proved by running the suite with its files removed and getting an identical result. | 2026-09-08 UTC |
| P-07 | [#54](https://github.com/navigreen311/theoffice/pull/54) | `7dda882` | run `34279098923`: Smoke alone red, list **byte-identical**; six jobs green. Diff `1048 / 0`, six files, nothing outside `scenarios/`. 16 authored + 26 declared across all 42 (module, class) pairs. | 2026-09-08 UTC |
| P-08 | [#53](https://github.com/navigreen311/theoffice/pull/53) | `a966a6c` | run `34278996637`: Smoke alone red, list **byte-identical**; six jobs green. Diff `572 / 0`. Golden did not move; ruled out *inert* content by running `_operation_scenarios` over both files — 7 rows each, no held-out class emitted. | 2026-09-08 UTC |
| P-09 | [#55](https://github.com/navigreen311/theoffice/pull/55) | `c49d99f` | run `34281227353`: Smoke alone red, list **byte-identical**; six jobs green incl. `Tests`. **Coordinator ran the authoritative validation** (P-09 had no credentials): real DB, both Forges up — V11 PASS, **V32 PASS**, V33 PASS, V22 FAIL. Burkham 30/2/1 → **31 PASS / 1 FAIL / 1 NOT_RUN of 33**. | 2026-09-08 UTC |
| P-12 | [#56](https://github.com/navigreen311/theoffice/pull/56) | `90433f5` | run `34283599954`: Smoke alone red, failing-check list **byte-identical** to baseline; six jobs green incl. `Tests`. Local `1025 passed, 1 failed` (the recorded environmental `test_restore_drill`). **Coordinator ran the authoritative validation**: Greenstone **29 PASS / 0 FAIL / 4 NOT_RUN** — no red, and no closer. Two goldens re-recorded under Caveat 6; every deleted line is the single JSON object whose `module_id` is `run_scenario_pack`, verified by the coordinator. | 2026-09-08 UTC |

*P-04 and P-10 are deleted by ruling Q-1 — a pack-level run gives this run nothing, and
there are no migrations in this build. Their absence from this table is deliberate; do not
add rows for them.*

**Merge order:** P-00, P-01, P-02, P-03, P-05, P-06, P-07, P-08, P-09, P-12.
**Never a parallel merge into any default branch. Never a force-push to one.**

---

## WHAT A PACKAGE MUST REPORT

Enough for a reviewer to check the claim without re-running anything:

1. **The CI run link and its conclusion**, against the baseline row above.
2. **Which jobs failed, by name** — and for each, whether it appears in the baseline.
3. **The files created and modified**, against what the card allowed. No scope creep.
4. **Any escalation**, from `PARALLEL_BUILD_ESCALATION.md`, surfaced in the PR description
   rather than buried.

5. **What CI actually did — not what you expect it to do.** Open the PR, let the run
   finish, then write the result. A predicted outcome stated as an observation is how
   P-00's first PR passed its own checklist while two jobs were red. If you genuinely must
   write a prediction, put the word "predicted" in the sentence.

**"Green" is not a report.** It is not available in `theoffice` this run, and a package
that claims it has either broken something or is looking at the wrong branch.

**And neither is a local run.** Without a database the suite skips 540 tests and errors on
59 more, including every golden snapshot — see the local-suite section above for how to
stand one up. **A package that has not run the database suite has no evidence about the
Tests job**, and should say so rather than inferring.


---

## HAND-BACKS AND RETRIES

**The plan's post-merge audit flags any package needing more than one revert-and-retry.
This records the ones that happened, whether or not they reached that bar.**

### P-00 — one hand-back, before merge, not a revert

**What failed:** the merge checklist item *"no NEW failures against the baseline"*. CI run
`34264952484` had **two** jobs red — `Smoke` (baseline, expected) and **`Tests`** (green in
the baseline, therefore new). Six defaulted fields on `CurriculumScenario` serialise into
the curriculum artifact, which is golden-snapshotted, and the snapshot was not re-recorded.

**Why it was not caught before the PR opened:** P-00's local suite cannot run — it errors
out on `OFFICE_ADMIN_DSN`, which P-00 itself had recorded, in this file, as *"not a CI
result, in either direction"*. It then asserted a CI result in its PR description a few
paragraphs later. **The failure was not ignorance of the gap; it was not applying a rule it
had just authored.**

**The control that exists and could not help:** the Tests job carries a step named
*"Refuse a green run that skipped the database suite"*, commented *"a skipped test is
reported as a pass by every summary."* It works. It did not fire, **because it runs in CI
and the claim was made before CI ran. A control cannot catch a prediction.**

**What changed as a result:** every subsequent brief in this run carries *"do not predict
CI — open the PR, let it run, then write what it did"*, and item 5 of the reporting
requirements above. The fix itself was one re-recorded golden, verified purely additive at
`108 0` — **zero deletions**, which is the proof no existing value moved.

---

## COORDINATOR MERGES TO `main`

Not packages, so not ledger rows. Recorded because they changed `main` during the run and a
package agent diffing against a moving base needs to know why it moved.

| PR | What | Merge SHA |
|---|---|---|
| [#40](https://github.com/navigreen311/theoffice/pull/40) | the coordination plan, on disk — Revision 6 had lived only in conversation | `8a4ae66` (via `17d989c`) |
| [#41](https://github.com/navigreen311/theoffice/pull/41) | amendments R6a (two rulings) and R6b (every agent gets a worktree) | `5e14436` |
| [#42](https://github.com/navigreen311/theoffice/pull/42) | R6c — the later cards move to entry 25 / B19, and the two-classes-one-name near-miss | `b102836` |
| [#44](https://github.com/navigreen311/theoffice/pull/44) | R6d — R-1 verified, and a P-12 check that could never have fired | `1d6a885` |
| [#45](https://github.com/navigreen311/theoffice/pull/45) | **contract amendment A1** — four things the frozen contract did not decide | `a22e2dc` |
| [#46](https://github.com/navigreen311/theoffice/pull/46) | **contract amendment A2** — operation scenarios key on the module | `1fed3bc` |

**Two of these amend the frozen contract.** They were made by the coordinator on Ivan's
rulings and written into the contract file itself rather than relayed in briefs, because an
interface amended verbally is an interface two packages will remember differently. The
contract remains frozen to package agents: escalate, never edit.

---

## CAVEAT 7 — the contract path a brief cites can be stale, and a stale frozen file is worse than none

**Found by P-03, 8 September 2026, before it wrote a line.**

Briefs cited the contract by working-tree path in the primary `theoffice` checkout. That
checkout went **six commits behind `origin/main`**, and its working-tree copy of the
contract **contained no §10 and no §11** — neither amendment A1 nor A2. An agent reading
only the path it was given would have missed both and had no way to know they existed.

**How it was caught, which is the part worth keeping:** P-03 noticed that P-02's merged
`never_do.py` docstring cited "Contract §10 A1.1" for a section **that was not in the file
it was reading**. A cross-reference to something absent is a louder signal than the absence
itself.

**Who was exposed.** P-02 built the correct shape (`module_not_applicable`) — but from the
orchestrator's message, not from the file. That is precisely the *"interface amended
verbally"* mechanism amendment R6e was written to prevent, performed by the person who
wrote it. P-05 had pulled and could see both. Only P-02 was affected, and only its
mechanism, not its output.

**The rule now:** briefs cite `git show origin/main:docs/scenario-contract.md`, never a
working-tree path. A frozen interface must be read from the ref that froze it. **An agent
told to read a path and finding no amendment cannot distinguish "there is no amendment"
from "this copy is behind."**

---

## CAVEAT 8 — a git worktree shares the stash list with the primary checkout

**Found by P-01, the hard way, and fully recovered.**

After committing its fix, P-01 ran `git stash push -- <file>` to redo a revert control. The
file was already committed, so **nothing was stashed and no entry was created** — and the
following `git stash pop` therefore popped a **pre-existing stash belonging to an unrelated
branch**, landing three foreign files in conflict in P-01's worktree.

Because the pop conflicted, git kept the entry. P-01 restored the three paths from HEAD and
verified `stash@{0}` intact and unchanged. **Nothing was lost, nothing committed, nothing
pushed.**

**The hazard generalises to every agent in this run:** worktrees share one stash list with
the primary checkout, so a no-op `stash push` followed by `stash pop` reaches into another
branch's work — including a human's.

**Use `git checkout <ref> -- <path>`. Do not use `git stash` in a shared repo.**

---

## CAVEAT 9 — a CI job that only runs on pull_request cannot appear in a push baseline

**Found by P-02, verified independently by P-03.**

simforge's `contract-tests.yml` is `on: pull_request` with a path filter on `apps/api/**`.
A baseline recorded from a **push to `main`** structurally cannot contain it — the trigger
never fired.

**Packages touching `apps/api/**` see four jobs, not three:** `api`, `validator`, `web`,
`contract`. Its absence from the baseline is **not drift and not permission to treat it as
optional.**

This is the run's own central lesson arriving inside the baseline itself: **a job that did
not run left no failure, and the absence of a failure is not evidence.**

---

## CAVEAT 10 — the branch names in the plan and the branch names in the run disagree

The plan's card names `feature/p-06-authorship-writes`, `-filters`, `-collects`-style suffixes.
The branches actually created and merged are `feature/p-06-authorship`,
`feature/p-07-authorship`, `feature/p-08-authorship`.

**Coordinator drift, not agent drift** — the worktrees were created with the short names and
all three agents flagged the mismatch in their acknowledgments rather than silently picking
one. Recorded here so the ledger rows and the plan's cards are not read as two different
packages. Nothing was renamed mid-flight, because renaming a branch under a reviewed PR is
worse than the inconsistency.

---

## CAVEAT 11 — a package cannot honestly declare a publish-diff count, and must not try

`broker/packs.py`'s `store(..., expect_changed_lines=, change_summary=)` computes
`_changed_lines` **positionally, not as a semantic diff** — its own docstring says an
insertion that shifts every following line *should* read as a large change, because "a
caller declaring three changed lines is declaring that nothing moved."

**The count must be computed against the live `business_pack.yaml_source`**, not against a
`git diff` and not against the file on disk — those can disagree, which is the drift the
control exists to catch.

**P-09 worked out that it could not do this and stopped.** `broker/*` and `db/*` are
forbidden to a Pack package, a fresh DB from Caveat 6's recipe has no `business_pack` row
for the live version, and `.env` is always-forbidden. A number derived from `git diff`
instead would have been *exactly the drift the control was built to catch, declared as
though it were the real thing.*

**The division that follows, and it applies to P-09 and P-12 alike:** the package supplies
the `change_summary`; **the coordinator computes `expect_changed_lines` against the live
row and runs the republish.** The ledger says which half was whose.

And the corollary P-09 asked for and got: **do not contort the YAML to keep the line count
stable.** Write the change legibly and declare an honest larger number. A declaration
optimised to look tidy is a declaration about the wrong thing.

---

## CAVEAT 6 — AMENDED 8 September 2026, on P-12's escalation

**Caveat 6 was stated by mechanism and illustrated by a package list, and it got read off
the list.** P-12 raised this against its own escalation and it is a fair criticism of how
the caveat was written.

As written, Caveat 6 names **P-00 and P-05** and reasons about packages that change **a
generator**. P-12 changed a generator's **input** — one line of Pack YAML — and landed in
exactly the same place: `tests/golden/snapshots/greenstone_forge_manifest.json` and
`greenstone_runtime_config.json` moved, and without re-recording them `Tests` would have
gone red as a NEW failure.

**The rule, restated by mechanism only:** *any* change that alters what a generator emits
moves the goldens, whether the change is to the generator or to what the generator reads.
A Pack edit, a scenario file, a registry row and a generator function are all upstream of
the same snapshot. **If your diff can change a generated artifact, the goldens are in
scope for you** — read the diff, run `git diff --numstat`, predict it in writing before
`UPDATE_GOLDEN=1`, and enumerate every changed and deleted key in the PR.

**P-12's re-record, verified by the coordinator:** `forge_manifest` `1/11`,
`runtime_config` `0/9`; the other five snapshots byte-identical; and every deleted line is
the single JSON object whose `module_id` is `run_scenario_pack` — its fields and braces,
not a substring match. Reversible with `git checkout origin/main -- tests/golden/snapshots/`.

---

## THE TWO REPUBLISHES — coordinator acts, recorded here because they are not ledger rows

Both Packs were live and every change to a live Pack is a version bump and a republish
through `broker/packs.py::store`, with the count declared. Per Caveat 11 the **package
supplied the `change_summary`** and the **coordinator computed `expect_changed_lines`
against the live `business_pack.yaml_source`** and ran the publish.

| venture | from → to | content_hash | positional count | why the count is large |
|---|---|---|---|---|
| `burkham-wickmont` | 0.2.0 → **0.3.0** | `c3e19c31…` | **513** | 811 → 831 lines; 18 inserted comment lines shift every line below |
| `greenstone` | 1.2.0 → **1.3.0** | `b9f141db…` | **210** | 380 → 393 lines; 13 inserted comment lines shift every line below |

Both were accepted without raising, which is the control confirming nothing moved beyond
what was described. **Neither count is "three changes" or "one change", and neither should
be** — `store`'s own docstring says a caller declaring three changed lines is declaring
that nothing moved.

**On `authored_by`.** Both were published under the `office_human` row that authored 0.2.0
and 1.2.0 — Ivan's. That is accurate in that he owns the Packs and both changes are his
rulings (T-081, Q-1), and it is the only identity available: there is no coordinator or
agent principal in `office_human`, and minting one would be the `origin=human` problem
SimForge's own Gate 8 docstring names — *an actor named in a record as though it acted,
indistinguishable afterwards from one that did.* **What actually happened is that Ivan
ruled, package agents wrote, and the coordinator executed the publish.** The
`change_summary` carries the substance; this note carries the part the schema cannot hold.

---

## CAVEAT 12 — a `tail -3` on a three-command chain is a prediction dressed as a measurement

**Caveat 5 said "do not predict CI: open the PR, let it run, then write what it did."
That was always the special case.** The general form was found by breaking it a different
way, on 8 September, by whoever wrote it.

`ruff check . && mypy … && pytest -q 2>&1 | tail -3` returns three lines. Those three
lines were mypy's success and pytest's summary. **Ruff's output was never on screen, ruff
was failing, and "ruff clean" was reported twice.** The lint job went red in CI on three
`UP017` violations that had been failing locally the entire time.

**The rule:** do not report any result whose output you piped away. A command that has not
run yet and a command whose output you discarded are the same epistemic state — you are
describing what you expect, and the expectation is usually right, which is what makes the
habit survive.

**Practically:** chain commands only when you will read all of it. Otherwise run them
separately and look at each, or capture to a file and grep for the failure signature
rather than the last N lines. `tail` is for logs you are watching, not for results you are
about to assert.

**Companion finding, same session:** V34 entered the rule registry with **no test file**,
and nothing caught it. The only signal was a pass count that did not move — 1026 before
the rule, 1026 after — which is luck, not a control. `test_rules.py` asserts the registry
is contiguous and that its length matches a literal; V34 satisfied both while untested.
**No check exists that a rule has a test.** Recorded rather than built, so whoever adds
V35 knows the gap is theirs to notice.

---

## CAVEAT 13 — a grep finds mentions, not construction

**Caveat 12's habit in a second form, found the same way: by doing it.**

`human_capacity` was made a required field, and the prediction named **four construction
sites** that would break, taken from a grep's hit list. **One broke.** The failure
surfaced in a fifth file the prediction never named.

| hit | predicted | actual | what it really was |
|---|---|---|---|
| `broker/pack_templates.py` | breaks | **broke** | a literal dict — a real construction site |
| `tests/provisioning/conftest.py` | breaks | fine | **a copy** of a loaded entry, `dict(officers[0])` |
| `tests/validator/test_rules.py` | breaks | fine | **a mutation** of a loaded pack |
| `tests/contract/test_approvals_api.py` | breaks | fine | **a docstring** |
| `tests/contract/test_packs_api.py` | not named | **broke** | where the template's failure surfaces |

**Three of four hits were a copy, a mutation and prose.** The grep found the string; the
prediction read the count as a list of places that build the object.

**The shared habit.** Caveat 12 is reporting a result whose output you piped away.
This is reasoning from a hit count without reading what each hit does. **Both substitute
a cheap proxy for the thing itself, and both are held confidently** — the proxy is
usually close enough, which is exactly why the habit survives.

**Practically:** a grep tells you where to look. It does not tell you what you will find,
and a prediction built on the count rather than on the reading is a guess wearing
evidence's clothes. Read each hit, or say the number is unread.

---
---

# ARCHIVE NOTE — 9 September 2026

**Run 1 is everything above this line. Run 2 is everything below it.**

This file was briefly overwritten rather than appended to when Run 2 opened: 715 lines of
Run 1's record — its baselines, caveats 1 through 13, the twelve-row merge ledger, the
hand-backs and the coordinator's own merges — were replaced wholesale by Run 2's opening
section. Restored here from `5e39956`.

**Nothing was lost; it was recoverable from git and is back.** It is recorded because the
mistake is one this file already warns about in another form: *before overwriting, look at
the target.* A write to a path that already holds something is a delete plus a create, and
the delete is the half nobody announces.

**Run 1's caveats stay in force for Run 2.** Run 2's list carries 12, 13 and a new 14, and
does not restate 1 through 11 — they are above, and they did not stop being true.

---
---

# RUN 2 — Gate 4.5 to a certified agent

**Opened 9 September 2026 by P-00.** Governed by `docs/coordination-plan-gate45.md`
Revision 3; the fifteen package prompts are in
`docs/coordination-plan-gate45-packages.md`.

**One coordinator merges, never in parallel. No force-push to main, ever.**

---

## Baselines — the gate is *no new failures against these*, never a green board

Recorded before any package started, because a board that was already red cannot be
judged against green and a package that tries will "fix" something deliberate.

### Starting SHAs

| repo | SHA | branch |
|---|---|---|
| `theoffice` | `5e39956` | main |
| `simforge` | `2ce2f5d` | main |

### Test counts at those SHAs

| repo | collected |
|---|---|
| `theoffice` | **1049** |
| `simforge` | **769** |

**A package that changes the count must say why in its PR.** The missing-V34-tests gap was
caught only because a pass count did not move when it should have — nothing checks that a
new rule has a test, and the count is the only signal.

### `theoffice` CI — six green, Smoke alone red, deliberately

| job | state |
|---|---|
| Console | pass |
| Images build | pass |
| Lint and types | pass |
| Migrations are reversible | pass |
| No committed secrets | pass |
| Tests | pass |
| **Smoke — the console actually renders** | **FAIL — the baseline below** |

**Do not fix Smoke. Do not weaken V11, V22, V32 or V33 to make it green.** It fails because
V11 and V32 report NOT_RUN in CI, where no runner can reach a live Forge. That is the
correct answer to a question CI cannot ask.

### The Smoke baseline capture — ten lines, verbatim

Reference run `34263050339`. **Diff byte-for-byte against this before merging anything.**

```
  FAIL the Gate 4 review form did not render
  FAIL the review form rendered without the artifacts summary above it - that is a rubber-stamp machine
  FAIL detail page lost: This gate waits. It does not pass on its own, and nothing ad
  FAIL detail page lost: Runs from gate 4 until a gate stops it. Gates are not skippa
  FAIL detail page lost: Required. Recorded against your name in the append-only log.
  FAIL the raw evidence is gone entirely - engineers need it
  FAIL recording a review and advancing are still two unrelated controls
  FAIL unevaluable rules with no gate named: ['V11', 'V32']
  1 check(s) could not run
  8 check(s) failed
```

**A zero-line diff of two empty captures is not a comparison.** Verify the capture is
non-empty and ten lines long before you conclude anything from it. This has already been
caught once in this project: two empty greps compared equal and read as a pass.

---

## Caveats carried forward

Each was paid for once. They are here so it is not paid for twice.

**Caveat 12 — a `tail -3` on a three-command chain is a prediction dressed as a
measurement.** "Ruff clean" was reported twice from an unread `tail`, while ruff was failing
on three `UP017` violations the whole time. **Read the output you report.**

**Caveat 13 — a grep finds mentions, not construction.** Four construction sites were
predicted from a grep hit list; one broke, and the failure surfaced in a fifth file never
named. Three of the four hits were a copy, a mutation and a docstring. **Read each hit
before claiming what it does.**

**Caveat 14 — read a claim out of the schema or the receiving side, not out of the names.**
New this run. The coordination plan's own premise was wrong twice, and both times a name was
doing the reasoning: *"unit B"* looked like it needed domain scenarios and does not, and
*"no new code expected"* described a path with no writer at all.

**Caveat 15 — file-atomic is not test-atomic. The packages share one database, and a
contended suite is indistinguishable from a broken branch.** Found by P-09 mid-run, and it is
a defect in this plan rather than in any package.

Every package works in its own worktree on its own files — and every one of them runs pytest
against the **same** `OFFICE_ADMIN_DSN`, a single `theoffice` database. The suite's fixtures
delete `office_human`, the Forge registry and every venture-scoped table, which is correct in
isolation and is exactly what makes it uninhabitable by two agents at once.

P-09 measured full-suite runs at **118 failed / 80 errors**, then **91 failed / 86 errors**,
against a 1049-passed baseline recorded twenty minutes earlier. It diagnosed the cause by
running the same file on a **pristine merge-base worktree** back to back — **unmodified main
came back redder than the branch under test** — and worked around it by cloning the database.

**The consequence for this run: a package's local suite result is not evidence while other
packages are running.** The merge gate — *no new failures against the recorded baseline* —
cannot be evaluated from a contended run, and a package that measures during a burst will
report a catastrophe that is not there. Worse in the other direction, a package could read a
neighbour's wreckage as its own and "fix" it.

**What the coordinator does about it, starting now:**

1. **CI is the arbiter, not a local run.** CI provisions its own database per job. A PR's
   `Tests` job is the measurement; a local count is a hint.
2. **The coordinator re-runs the suite serially before each merge**, with no agents working,
   and that run is what the ledger records.
3. **A package reporting a large failure count states whether other agents were running.**
   An unqualified count is not a measurement.

**Caveat 16 — a stamped `alembic_version` is not a migrated schema, and the suite does it to
itself.** Found by P-08 as E-012; **confirmed by the coordinator within the hour, on itself.**

`tests/deployment/test_probes.py` sets `alembic_version` directly as its restore step. A
migration-adding branch therefore leaves a database **stamped at the new revision with the old
schema underneath** — and `alembic upgrade head` then reports `0033 (head)` and does nothing,
because the stamp says the work is done.

Measured on `theoffice_test` during P-08's merge window: stamped `0033`, `review_seconds`
present, `queue_to_decision_seconds` absent. Eleven tests failed with
`UndefinedColumn: column "queue_to_decision_seconds" does not exist` **against a migration
alembic said was applied.** The remedy is `alembic stamp 0032` then `upgrade head`.

**Two separate traps in one window, and the coordinator hit both:**

1. **`alembic` migrates `OFFICE_ADMIN_DSN`; the suite runs against `OFFICE_TEST_ADMIN_DSN`.**
   Migrating the dev database and running the tests is not the same act, and the failure
   arrives as eleven red contract tests rather than as "you migrated the wrong database".
2. **Then the stamp hid the second half**, so the obvious fix reported success and changed
   nothing.

**The lesson is the one this file already carries in another form:** a status field is not a
measurement of the thing it describes. `alembic current` reports what was *written to a table*,
not what is *in the schema* — the same shape as B26's `status = 'live'` on twelve unreadable
rows, and as the polled `in_progress` P-07 mistook for a hung job.

**Check the column, not the version.** Both are one query.

**What would fix it properly, not built here:** a per-worktree database, cloned from a
template at session start and dropped at the end — which is what P-09 did by hand under the
name `theoffice_test_p09`. The plan should have specified it. **File isolation was designed
carefully and database isolation was not designed at all**, which is the same class of miss
as B26: the thing in git was made atomic and the thing in force was not.

**Every agent gets its own git worktree.** `git checkout -b` in a shared checkout collides
with whatever another agent has uncommitted. This cost a recovery on the previous run.

**A migration or a rule moves `EXPECTED_SCHEMA_REVISION` and every rule-count assertion, in
the same commit.** CI catches it, and the assertion's own message tells you to.

**A moved golden snapshot is a finding, not a chore.** `UPDATE_GOLDEN=1` is the
coordinator's call, never a package's.

---

## Ruling — T-014 is dropped from P-00's blockers and stays owed

**9 September 2026, by Ivan. Recorded as a ruling rather than an edit, so the next reader
meets a decision instead of a blocker that quietly vanished.**

P-00's card required **both** T-013 (rotate `OFFICE_SHARED_SECRET`) and T-014 (create Ira
Green's `office_human` row) before merge. **T-013 is verified. T-014 is not met** — no row
matching "Ira" exists under any origin, and the newest `console_human_created` audit event
is from 26 August. The call never reached the endpoint.

**T-014 is removed as a blocker because nothing on the critical path reads Ira's row:**

- **Unit-B certification is what blocks C**, not the Pack's reviewer list. Every Burkham
  candidate is refused `missing_unit_b` for `administration`, `banking` and `operations`
  regardless of who is named in `human_capacity`.
- **B22's second half: Gate 4 never reads `human_capacity` at all.** `record_human_review`
  authorizes on role strength and venture scope and never asks whether the reviewer is one
  the venture declared. A named reviewer with no account changes nothing there.

**T-014 stays owed. It is not cancelled and it is not done.** It gates nothing, which is
exactly why it is at risk of being forgotten — so it is written here rather than left in a
card nobody reopens.

### T-013 — verified after the rotation, all three states distinct

| control | result |
|---|---|
| valid token | **`HTTP 200`, 11 modules** |
| no token | `HTTP 401` · **`OFFICE_CREDENTIAL_REJECTED`** |
| wrong token | `HTTP 401` · **`OFFICE_CREDENTIAL_REJECTED`** |

The eleven: `client_read`, `client_read_credit`, `client_read_pii`,
`compliance_manifest_assemble`, `portfolio_health`, `record_consent`,
`regulator_dossier_export`, `restack_recommend`, `scan_communication`, `statement_pull`,
`submit_application`.

**Counted from the parsed body, not from the status.** The code is present on both 401s,
which is the distinguishing evidence: an unmounted bridge and a rejected credential share a
status, and only the absence of `OFFICE_CREDENTIAL_REJECTED` tells them apart.

---

## Number pre-allocation

So two agents never claim the same entry. **Write into your allocated number; do not choose
your own.**

**`theoffice` has no `docs/adr/` directory — `docs/decisions.md` is the mechanism here.**
`simforge` has `docs/adr/`. P-00's own card said "an ADR"; on this side that is an entry, and
the correction is noted rather than silently applied.

| package | `docs/decisions.md` | `simforge/docs/adr/` |
|---|---|---|
| **P-00** | **entry 27** — A0: certification is out of band, both producers missing · **WRITTEN** | ADR number to be claimed by P-01 or P-05, whichever lands first |
| **P-00** | **entry 28** — unit B does not require executable domain scenarios; entry 23 stands · **WRITTEN** | — |
| **P-14** | **entry 29** — AnimaForge: zero for V1 | — |
| **P-10** | **entry 30**, if the reviewer-exists rule warrants one | — |
| any other package | **ask the coordinator before writing to `decisions.md`** | — |

`docs/blocking.md` is **append-only, one section per package.** A closure is an appended
paragraph; it never rewrites the item above it.

**No interface file is needed this run.** No package imports another's new code — P-05 is in
a different repo from everything it serves. Stated so nobody invents one to be safe.

---

## Merge ledger

Every merge gets a row: package, PR, merge SHA, test result, timestamp.

| package | PR | merge SHA | tests | Smoke vs baseline | timestamp |
|---|---|---|---|---|---|
| — | [#69](https://github.com/navigreen311/theoffice/pull/69) | `c4671fa` | 1049 pass | 10 lines, identical | 2026-09-09 |
| — | [#70](https://github.com/navigreen311/theoffice/pull/70) | `5e39956` | 1049 pass | 10 lines, identical | 2026-09-09 |
| **P-00** | [#71](https://github.com/navigreen311/theoffice/pull/71) | `1063802` | 1049 pass | 10 lines, identical | 2026-09-09 |
| P-01 | | | | | |
| P-02 | | | | | |
| P-03 | | | | | |
| P-04 | | | | | |
| P-05 | | | | | |
| P-06 | | | | | |
| P-07 | | | | | |
| P-08 | | | | | |
| P-09 | | | | | |
| P-10 | | | | | |
| P-11 | | | | | |
| P-12 | | | | | |
| P-13 | | | | | |
| **P-14** | [#73](https://github.com/navigreen311/theoffice/pull/73) | `a334e6b` | 1049 pass, count unchanged | 10 lines, identical | 2026-09-09 |

**P-14 merged out of numeric order, deliberately.** Its card puts it fifteenth, but that number is a merge-order slot, not a dependency. P-14 depends only on P-00, touches exactly one file (`docs/decisions.md`, +84/-0), and no other package in this wave writes to that file. Holding a records-only package behind an unscoped one (P-13) would have bought nothing and risked the entry going stale against a ruling made the same day. **Verified by the coordinator rather than taken from the agent's report:** file scope from the PR's own file list, and the Smoke capture re-pulled from run `34383553084` and diffed byte-for-byte — ten lines, non-empty, identical.

*(#69 and #70 predate P-00 and are listed because they changed `docs/blocking.md`, which
every package appends to. #69 is T-015.)*

---

## Two results wanted the day they happen, not in a summary

**Ivan's standing instruction, 9 September.**

**P-01's result — within the hour if Gate 8 still fails.** Four packages are aimed at a
handover nobody has seen work: P-02, P-03, P-04 and P-05 all assume a submission is
accepted. If it is not, they are aimed at nothing and the wave stops rather than continuing
on an assumption.

**GAP-5 — does SimForge hold domain certifications for `administration`, `banking` and
`operations`?** **P-04's first task, before any code — not P-11's discovery.** Only
`engineering` exists on The Office's side. If SimForge holds none for Burkham's three, P-04
still ships a submitter that correctly reports them uncertified, and C stays blocked on
something true. **Finding this at P-11 would mean four merged packages before anyone learned
the run could not finish.**

---

## Escalation

- A package needing a file outside its list writes `PARALLEL_BUILD_ESCALATION.md` on its
  branch and flags it in the PR. **It does not modify the file.**
- **A critical-path package failing twice halts the entire run** and escalates to Ivan.
- Any package requiring more than one revert-and-retry gets a post-mortem entry here.
