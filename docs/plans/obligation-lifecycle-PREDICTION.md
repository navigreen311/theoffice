# The four states of a human-held obligation — prediction, written before the build

**8 September 2026.** Written before `pending_activation` exists. Scored below without
editing anything above the line.

**Predicted narrowly, per the P6 lesson.** Each prediction says whether it was *reasoned
from the code* or *assumed*, because P6 was wrong for exactly one reason: it reasoned
carefully about one job and then claimed the whole board. Everything reasoned about held;
the part asserted by extension did not.

## The model, as ruled

These are states of **the obligation**, not of a discharge row.

| state | meaning | V34 |
|---|---|---|
| `pending_activation` | real, trigger has not fired, no verification due | **PASSES** |
| `live_unverified` | trigger fired, no current discharge | **FAILS** |
| `live_verified` | current discharge covering the venture's jurisdictions | **PASSES** |
| `verification_expired` | lapsed, or scope no longer reaches | **FAILS** |

The bottom two are what V34 already derives. **The new distinction is *not yet due* versus
*due and nobody has done it*.**

`pending_activation` is declared on the Pack beside `human_held`. **Not stored in a table,
not derived: a clock cannot know whether a partner exists.**

### Why this is not the cheap escape in a fourth costume

It requires **a checkable activation condition**. Burkham's is real: no referral fee has
ever been paid, no partner relationship exists, and Partner Agreement & Payout Center is
deferred to V1.5. *"Module 8.2 activates and a referral relationship is being structured"*
is a condition a person can check. *"When it becomes relevant"* is not.

The schema can require the sentence to exist and be substantial. **It cannot judge
whether the condition is checkable** — that is a reviewer's job, and the docstring says so
rather than pretending otherwise.

## State before

```
burkham-wickmont   32 PASS / 1 FAIL / 1 NOT_RUN   of 34
   V22 PASS · V34 FAIL (no discharge record exists) · V24 NOT_RUN (Gate 4.5 by design)
   Gate 2 BLOCKED

greenstone         30 PASS / 0 FAIL / 4 NOT_RUN   of 34
```

## Predictions

### Q1 — V34 passes on `pending_activation` · REASONED

**PASS**, with a message that names the state and the trigger rather than reporting a
discharge it did not look for. Reasoned: I am writing the branch, so this is a statement
about intent, and it is listed to be scored rather than assumed correct.

### Q2 — Burkham totals · REASONED (arithmetic on the current run)

**33 PASS / 0 FAIL / 1 NOT_RUN of 34.** V34 moves FAIL → PASS; nothing else changes; the
rule count does not move because no rule is added.

### Q3 — Gate 2 clears · REASONED FROM THE CODE

**PASSES.** `broker/provisioning.py:170-185` blocks on `report.failures`, then on
`[r for r in report.not_run if r.rule_id != "V24"]`. With zero failures and V24 the only
NOT_RUN, neither branch fires.

**This is the first time Gate 2 will have passed for any venture in this system.**

### Q4 — Gate 5 does NOT run on its own · REASONED FROM THE CODE, AND IT QUALIFIES THE EXPECTATION

`_gate_4` returns `AWAITING_HUMAN` unless `ctx.human_review_recorded`:

> *"Human review. Waits — it does not pass."*

So a run advanced after this change **stops at Gate 4**, not at Gate 5. Gate 2 clearing
removes the block that has stopped every run so far; **it does not carry the run to the
manifest.** A named human has to record a review of the artifacts first, which is the
gate's whole purpose.

**Predicted: the run reaches `awaiting_human` at gate 4.** The manifest does not generate
until somebody reviews.

### Q5 — what happens after a human review · NOT REASONED, EXPLICITLY

I have **not** established what Gate 3, Gate 4.5 or Gate 5 do for Burkham. Specifically:

- **Gate 3** (generators ran) — not examined for this Pack.
- **Gate 4.5** (V24, the real Task Ledger) — `decisions.md` entry 15 records that *every
  capacity number in this system is Greenstone's* and Burkham has never been provisioned;
  Greenstone passes V13 at Gate 2 and **fails at Gate 4.5**. Whether Burkham does the same
  is unknown to me and I have not looked.
- **Seven manifest rows** — I have not verified that seven is what Gate 5 would generate,
  only that `venture_forge_manifest` currently holds two hand-placed rows against seven
  declared modules.

**These are the parts I am not predicting.** If the run gets past Gate 4 and something
downstream fails, that is not a falsified prediction — it is a region I declined to
predict, and saying so now is the point.

### Q6 — Greenstone · REASONED

**Unchanged at 30 PASS / 0 FAIL / 4 NOT_RUN of 34.** It declares no human-held obligation,
so no state applies and V34 keeps saying *nothing to discharge*.

### Q7 — CI · REASONED, AND NARROWLY

**Smoke's failing-check list stays byte-identical.** V22 and V34's Pack-side inputs change,
but Smoke runs against Greenstone in a database-only world where V34 reports NOT_RUN, and
Greenstone declares nothing human-held either way.

**I am not predicting the rest of the board.** P6 claimed "CI unchanged" from Smoke
reasoning and was wrong because `Tests` counts things. This time: **I expect to have to
update whatever counts states or asserts on V34's message, and I will find out by running
it, not by asserting it.**

## What would falsify the design rather than a prediction

- **`pending_activation` accepted with a vague or empty trigger.** That is the escape in a
  fourth costume.
- **V34 passing on `live_unverified`.** The state whose entire job is to fail.
- **A state that can be set without a reviewer being able to check the condition.**

## Scored

*(filled in after the run, below the line, without editing anything above it)*
