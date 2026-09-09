# Gate 2 pools supply, Gate 4.5 splits it — prediction, before the build

**9 September 2026, P-09 / B25.** Written before anything was run. Scored below the line
without editing a word above it. Each claim says whether it was **reasoned from the code**
or **assumed**.

## What is being built

B25 offers two fixes and says the second is probably right:

1. the two gates share one aggregation helper, or
2. **Gate 2's pooling is stated as a deliberate simplification, with the reason.**

**Option 2 is what this package builds.** The arithmetic in `v13` is not touched. What
changes is that the pooling stops being an accident a reader discovers by holding the two
functions side by side, and becomes a choice the function declares — plus tests that pin
the choice, so a later silent change to Gate 2's aggregation fails a test instead of
re-opening B25.

Option 1 was considered and rejected for a reason that is itself a prediction, tested at
Q4 below: **a shared helper cannot be written without touching `validate_gate_4_5`**,
which is on this package's MUST NOT TOUCH list because B24 just fixed it.

## The two aggregations, read out of the code rather than out of the item

`generators/validator.py::v13` (Gate 2, line ~320):

```
approvals         = sum(headcount where trust_tier_ceiling != auto_execute)
                    * max(1.0, agent_days_per_week / 7)
minutes_needed    = mean(median_review_minutes over ALL humans) * approvals
minutes_available = sum(coverage_hours * 60 * 0.6 over ALL humans)
```

`generators/validator.py::validate_gate_4_5` (the recheck, line ~1595): per role, demand
from `approval_projection.projected_daily_approvals[role]`, review minutes weighted by each
person's coverage share **within the role**, coverage summed **within the role**.

**The difference that matters is not the weighting. It is the role split.** Gate 2 has no
per-role demand figure at all — its `approvals` is one pooled headcount number with no role
attribution — so it has nothing to set a per-role supply figure against.

## Predictions

### Q1 — no verdict moves, at either gate, for either venture · REASONED

The change is comments, a docstring, a console reason string and new tests. **No expression
that produces a number is edited.** So Gate 2 stays PASS for both Packs and Gate 4.5 stays
whatever it was.

If any verdict moves, this package did something it did not intend and the PR needs the
written explanation the card demands — not a silent pass.

### Q2 — Gate 2's exact numbers, computed by hand before running · REASONED

Reported as numbers rather than as PASS, because a PASS at 12 minutes and a PASS at
4½ hours print the same word.

**Burkham** (`packs/burkham-wickmont.draft.yaml`) — positions below `auto_execute`:
Intake Concierge 2, Diagnostic Analyst 2, Placement Strategist 2, Compliance Reviewer 1,
Stack Manager 1 = **8**. `agent_days_per_week: 40` → `max(1.0, 40/7)` = 5.714.

- approvals = 8 × 5.714 = **45.7** (prints as `46`)
- pooled unweighted mean of (4, 3) = **3.5**
- needed = 45.714 × 3.5 = **160.0**
- available = 12h × 60 × 0.6 = **432**
- → **PASS, `160 of 432 review-minutes used`, margin 272 minutes**

**Greenstone** (`packs/greenstone.yaml`) — below `auto_execute`: Deal Underwriter 2,
Buyer Network Manager 2 = **4** (Acquisition Analyst is `auto_execute`).
`agent_days_per_week: 35` → 5.0.

- approvals = **20**
- pooled unweighted mean of (4, 6) = **5.0**
- needed = **100**
- available = (6+4)h × 60 × 0.6 = **360**
- → **PASS, `100 of 360 review-minutes used`, margin 260 minutes**

### Q3 — Gate 4.5 verdicts · GREENSTONE REASONED, BURKHAM ASSUMED

**Greenstone: FAIL.** `docs/generators.md` records it verbatim — `compliance_officer:
192 approvals × 6 min = 1152 against 144 available`. Dana alone is the role: 4h × 60 × 0.6
= 144. One person in the role, so B24's weighting leaves 6.0 unchanged.

**Burkham: PASS at 420 of 432, 12 minutes.** This is **ASSUMED, not reasoned**: the 120
approvals come from the Pack's own comment and from `test_human_held_discharge.py`, which
asserts the *prose* says twelve minutes. **I have not seen a run that produces 120 from
Burkham's Task Ledger** — no golden test runs the pipeline on Burkham. If measuring is
cheap I will measure it; if it is not reachable without running generators the card does
not scope, I will say so rather than report the Pack's own comment back as a measurement.

### Q4 — THE TWELVE MINUTES IS AT GATE 4.5, NOT GATE 2, AND NO GATE 2 CHANGE CAN REACH IT · REASONED

The card's compliance flag says a Gate 2 change that moves the pooled mean can move the
twelve-minute margin. **Read out of the code, it cannot**, and the flag is worth answering
precisely rather than reassuringly:

1. **420/432 is a Gate 4.5 number.** It is `120 × 3.5` where 120 comes from the Task
   Ledger, which does not exist at Gate 2. Gate 2's Burkham demand is 45.7 approvals, not
   120 (Q2). The two gates cannot share a margin because they do not share a demand.
2. **Burkham's two aggregations agree to the digit anyway.** Both officers declare
   **6 coverage hours**. Coverage-weighted mean = (6×4 + 6×3)/12 = **3.5**. Pooled
   unweighted mean = (4+3)/2 = **3.5**. Both humans are `compliance_officer`, so the role
   split is a no-op too. **Even option 1 — one shared helper — would leave Burkham's number
   byte-identical.** The twelve minutes is not at risk from this package under either fix.
3. **Greenstone is the only venture where the two aggregations disagree numerically:**
   pooled unweighted (4+6)/2 = **5.0** against coverage-weighted (6×4 + 4×6)/10 = **4.8**.
   4% apart, and it would move Gate 2's Greenstone figure from 100 to 96 against 360 —
   a PASS either way, in the **optimistic** direction, for no gain. Another reason option 2
   is the right one.

**Falsifies this package if wrong:** if Burkham's Gate 4.5 margin is anything other than
12 minutes after the change, the change reached somewhere it was not supposed to.

### Q5 — direction of the pooling error, stated honestly · REASONED, AND IT IS NOT ONE DIRECTION

The docstring's existing claim is that **Gate 2 is the optimistic one**. The tempting move
is to say pooling is optimistic too and be done. Half of that is true and half is not, and
writing only the true half would be the same failure B25 is about:

- **The role split is optimistic in one direction only.** Pooling lets a slack role absorb
  a saturated one; it can hide a bottleneck, and can never invent one. This agrees with the
  documented direction.
- **The unweighted mean is not directional.** It can land either side of the coverage-
  weighted mean — above it for Greenstone (5.0 vs 4.8, more demanding), equal for Burkham.
  It is bounded by the smallest and largest declared review time either way.

So the stated simplification must say **pooling errs optimistic, the unweighted mean errs
either way but is bounded**. Predicting this here because the writing is the deliverable,
and a prediction about the prose is still a prediction.

### Q6 — tests · REASONED FROM THE SCOPE, COUNT ASSUMED

Baseline **1049**. I expect to add **4** tests → **1053**: Gate 2's pooling pinned as
declared behaviour (a fixture where pooled and per-role disagree), the unweighted mean
pinned against the coverage-weighted one, Burkham's and Greenstone's Gate 2 figures pinned
as numbers, and the docstring asserted to actually state the choice — a comment nothing
checks is a comment that rots.

**A test that reads a docstring is unusual and I am predicting it will look like
over-reach.** It is the only thing that makes option 2 durable: option 1 would have been
enforced by the shared helper, and option 2 has nothing enforcing it unless something reads
the words.

No existing test should break. **REASONED, weakly:** no test pins `v13`'s message text —
`test_rules.py` only asserts `"V13 FAIL" in text` on a mutated Pack — and no test pins the
`LATER_GATE_REASONS["V13"]` string, only that it is non-empty
(`test_a_rule_rechecked_at_a_later_gate_says_so`). I have read both hits rather than
counted them.

### Q7 — CI · NARROW

**Smoke's ten failing lines stay byte-identical.** V13 does not appear in them. I am not
predicting the rest of the board.

## What would falsify the design rather than a prediction

- **Any verdict moving anywhere.** The change edits no arithmetic; a moved verdict means it
  did.
- **Burkham's Gate 4.5 margin not being exactly 12 minutes afterwards.**
- **Finding that Gate 2 does have per-role demand available.** The whole stated reason for
  pooling is that it does not. If `approvals` can be attributed per role at Gate 2, option 2
  is the wrong fix and the honest answer is option 1 plus an escalation, because option 1
  needs a file this package may not touch.

## Scored

*(filled in after the run, below this line, without editing anything above it)*

*Nothing above this line was edited after the run. The prediction was committed in its own
commit before any command was executed, so the ordering is a fact in the history rather
than a claim in the prose.*

### Q1 — CORRECT. Nothing moved, at either gate, for either venture

Measured before and after, byte-identical both times:

| venture | gate | message |
|---|---|---|
| Burkham | 2 | PASS · `160 of 432 review-minutes used` |
| Greenstone | 2 | PASS · `100 of 360 review-minutes used` |
| Burkham | 4.5 | PASS · `projected approvals fit within reviewer capacity` |
| Greenstone | 4.5 | FAIL · compliance officer, 3 times over |

**The strongest evidence is not the measurement, it is the diff.** The entire branch —
five files, 611 insertions — deletes **exactly one line** across the whole repository, and
that line is the prose string `"optimistic one.",` inside `LATER_GATE_REASONS`. No
expression that produces a number was touched, so no verdict could move. The P-12
treatment is not needed.

### Q2 — CORRECT to the digit, all four numbers

Predicted by hand before running: Burkham `160 of 432`, margin 272; Greenstone
`100 of 360`, margin 260. Both exact, including the 45.714 approvals rounding to 46 and the
8-headcount count of Burkham's positions below `auto_execute`.

### Q3 — CORRECT, and the half marked ASSUMED became measured

Greenstone FAILs Gate 4.5, as reasoned. Burkham PASSes at 420 against 432.

The prediction said the 120 was **assumed** — taken from the Pack's own comment, with no
run behind it — and promised to measure it if measuring was cheap. **It was cheap and it
was measured:** Burkham's workflow generator emits **15 steps, none at `auto_execute`**, and
`approval_projection` charges `DEFAULT_DAILY_VOLUME_PER_HEADCOUNT = 8` per step, giving
`{'compliance_officer': 120}` — the whole projection, one role. 120 × the coverage-weighted
3.5 = 420 against 432. **Twelve minutes**, now pinned by
`test_burkhams_gate_4_5_margin_is_still_twelve_minutes` rather than by a YAML comment
quoting itself.

**One caveat that the prediction did not think to state.** That measurement uses an
**unappointed** roster, which is what `approval_projection` falls back to when nobody is
certified. Greenstone measured the same way gives 64 approvals to its compliance officer,
not the 192 in `docs/generators.md` — that figure comes from the fully-certified world
fixture, where appointed agents multiply the per-step count. Both are correct for their
roster; **the number is a function of the appointment state, and neither the Pack comment
nor the docs say which state theirs assumes.** Not this package's to fix; recorded because
"120" and "192" look like properties of a venture and are not.

### Q4 — CORRECT, AND MEASURED RATHER THAN LEFT AS AN ARGUMENT

This was the load-bearing claim and the one that answers the card's compliance flag, so it
was not left as reasoning. Gate 2 was switched to coverage-weighting experimentally and the
new tests re-run:

| | pooled unweighted (shipped) | coverage-weighted (the experiment) |
|---|---|---|
| Burkham Gate 2 | `160 of 432` | **`160 of 432` — unchanged** |
| Greenstone Gate 2 | `100 of 360` | `96 of 360` |

**Exactly as predicted: 100 → 96 for Greenstone, and Burkham does not move at all**, because
its two officers declare equal coverage so the weighted and unweighted means are both 3.5
and both are the same role. **Even the shared-helper fix B25 offered would have left
Burkham's twelve minutes byte-identical.** The card's flag — that a Gate 2 change moving the
pooled mean could move the twelve minutes — is answered: it could not, for two independent
reasons, and both were checked rather than argued.

Two of the six new tests fail under that experiment, which is the property that makes the
stated choice enforceable.

### Q5 — CORRECT, and it was the right call

The prose says both directions. Pooling across roles errs optimistic and only optimistic;
the unweighted mean errs either way and is bounded, and Greenstone is the worked example of
it landing on the **more demanding** side. Had only the flattering direction been written,
this document would have predicted a fix that reproduced the defect it was fixing.

### Q6 — WRONG ON THE COUNT, RIGHT ON THE SHAPE

Predicted **4** tests, `1049 → 1053`. Actual **6**, `1049 → 1055`. The two unforecast ones
are `test_gate_2_pools_across_roles_even_when_the_roles_are_different` and
`test_burkhams_gate_4_5_margin_is_still_twelve_minutes` — the second exists only because Q3
promised to measure the 120 and a measurement worth making once is worth pinning.

The prediction that **no existing test would break** held, and the reasoning behind it was
right for the right reason: no test pinned `v13`'s message or the `LATER_GATE_REASONS`
string, and both hits were read rather than counted.

The self-conscious prediction that the docstring test "will look like over-reach" is
recorded as neither right nor wrong — nobody has reviewed it yet. It stays because the
argument for it survived writing the rest: **option 1 would have been enforced by the
helper; option 2 is enforced by nothing else.**

### Q7 — NOT MEASURED, and saying so rather than reporting the reasoning as a result

Smoke needs a live console and two servers; it runs in CI and was not run here. What was
done instead was to **read `scripts/console-smoke.sh`**: its V13 assertions are the Gate 4.5
message's utilisation-factor clause (line 646) and the presence of the reviewer-capacity
page (line 1801), neither of which this branch touches, and the only thing that reads
`why_not_here` (line 1346) checks presence for **unevaluable** rules — V13 is evaluable at
Gate 2, so the string this branch edited is not on that path.

**That is a reading, not a run.** CI is the measurement. Recorded this way deliberately:
Caveat 12 is about reporting a prediction as a measurement, and "Smoke is unaffected" would
have been exactly that.

### The thing the prediction had no way to foresee, and it cost an hour

**The shared `theoffice_test` database is contended by the other package agents in this run,
and a contended suite is indistinguishable from a broken branch.** Full-suite runs on this
branch returned `118 failed / 80 errors`, then `91 failed / 86 errors` — against a clean
pre-change baseline of **1049 passed** measured twenty minutes earlier with the same flags.
Every failure was a DB test and the set differed between runs.

**It was diagnosed by measurement, not by hope.** A pristine worktree at the branch's own
merge-base was created and the same file run on both, back to back:

| run | main `7ba5efc` | branch |
|---|---|---|
| first pair | **17 failed**, 11 passed | 28 passed |
| second pair, minutes later | 28 passed | 28 passed |

**Unmodified main was the redder of the two**, and both went green when the burst passed.
`tasklist` showed four other pytest processes started within the same minute; the fixtures
delete by `venture_id`, so concurrent agents delete each other's rows.

Resolved by cloning `theoffice_test` into a private `theoffice_test_p09` and pointing
`OFFICE_TEST_*_DSN` at it — the clone had to be retried in a loop because `CREATE DATABASE
… TEMPLATE` refuses while another session is connected, which is the same contention seen
from the other side. **The isolated result is the one reported in the PR.**

This is a finding for the coordinator rather than for this package: **the merge gate is "no
new failures against the recorded baseline", and on a shared database that gate cannot be
evaluated by an agent working while others run.** Any package that measured its suite during
a burst and reported the number would have reported a catastrophe that was not there — or,
worse, run during a quiet window, seen green, and drawn a conclusion about a board it never
actually tested.

### The suite, measured on the isolated clone

`1055 collected` (= 1049 + the six new), **1045 passed, 10 failed, 0 errors** in 93s.

The ten are `tests/contract/test_approvals_api.py` (7) and `tests/contract/test_governance.py`
(3), and **they are not this branch's.** The clone was taken from `theoffice_test` while
another agent's run was in flight, so it inherited that run's rows. Established the same way
as the contention above — run the same two files on the pristine merge-base worktree against
the same database:

| | main `7ba5efc` | branch |
|---|---|---|
| `test_approvals_api.py` + `test_governance.py` | **10 failed**, 31 passed | **10 failed**, 31 passed |

**Identical, deterministic, and on unmodified main.** The delta this branch contributes is
zero. None of the ten touches V13, the validator, or any file this package changed.

The six new tests pass. `ruff check .` clean; `mypy broker client generators` clean —
62 source files, CI's exact command.
