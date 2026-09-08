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
| P-01 | | | | |
| P-02 | | | | |
| P-03 | | | | |
| P-05 | | | | |
| P-06 | | | | |
| P-07 | | | | |
| P-08 | | | | |
| P-09 | | | | |
| P-12 | | | | |

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
