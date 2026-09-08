# Human-held obligations — prediction, written before the build

**8 September 2026.** Recorded before `HumanHeld` exists, so the result can be scored
against it rather than described after the fact. Same discipline as the identity-issuance
rounds: a wrong prediction is the point of writing one down.

## State before

Burkham Wickmont, `packs/burkham-wickmont.draft.yaml`, against the real database with
both Forges reachable:

```
compliance flags declared      20
compliance flags exercised     19
missing                        ['referral_fee_permitted_in_state']

V22  FAIL     runtime flag(s) never exercised by a scenario:
              referral_fee_permitted_in_state
V11  PASS     V32  PASS     V33  PASS

totals   31 PASS / 1 FAIL / 1 NOT_RUN   of 33 rules
Gate 2   BLOCKED
```

`referral_fee_permitted_in_state` is `REFERRAL_FEE_REGULATION`, jurisdiction `ALL`,
`applies_when: Any payout to a partner or referrer`, and it already carries
`library_gap: true` — a declared absence on a different axis of the same row.

## What is being built, and why the two halves are one change

**`HumanHeld(why=...)` on a compliance-surface entry, and a world rule that checks every
human-held obligation has a current discharge, land together or not at all.**

This is not a sequencing preference. **`HumanHeld` on its own is the cheap escape.** Any
flag nobody wants to write a scenario for could be marked human-held and V22 would go
quiet. Today V22 **fails loudly and wrongly** — it says a scenario is missing when the
truth is that no agent role holds the duty. With `HumanHeld` and no discharge rule it
would **pass silently and wrongly**, and that is worse: a loud wrong answer is at least
read, and this project has spent a week establishing that a quiet one accumulates.

So the coupling is the design, not a note attached to it.

## Predictions

Written before running. Each is falsifiable and scored below.

### P1 — V22 on Burkham, after `HumanHeld`, before any discharge exists

**PASS.** Twenty flags declared: nineteen exercised by a scenario, one declared
human-held. All twenty accounted for, so `declared − accounted` is empty.

**V22's message changes in kind**, from naming a missing scenario to naming what was
counted. It should no longer mention `referral_fee_permitted_in_state` at all — that flag
is now some other rule's subject.

### P2 — the new world rule on Burkham, before any discharge exists

**FAIL**, naming `referral_fee_permitted_in_state`, the obligation's holder, and that no
current discharge exists.

Not NOT_RUN when a database is present: the rule can ask and the answer is "no row."
**An absent discharge is a fact, not an unanswerable question.** NOT_RUN is reserved for
the case where the rule could not ask at all.

### P3 — Gate 2 on Burkham

**STILL BLOCKED.** The block moves from V22 to the new rule and does not lift.

This is the prediction most likely to be misread as a regression later, so it is stated
plainly: **building this unblocks nothing on the day it lands.** No discharge record
exists, and none can exist until a named human files one. What changes is that the
failure stops saying "somebody forgot a scenario" and starts saying "a real obligation is
held by a human and has not been verified."

### P4 — Burkham totals

**32 PASS / 1 FAIL / 1 NOT_RUN of 34.**

Rule count goes 33 → 34. V22 moves FAIL → PASS (+1 pass, −1 fail); the new rule arrives
as a FAIL (+1 fail). Net: passes +1, failures unchanged at 1, NOT_RUN unchanged at 1.

### P5 — Greenstone

**Unchanged: 29 PASS / 0 FAIL / 4 NOT_RUN, and one more rule.**

Greenstone declares no human-held obligation, so the new rule has no subject there. It
should report a pass-with-nothing-to-check rather than a vacuous PASS that cannot be told
from a real one — the distinction P-09 drew when its own V33 passed against an empty
table.

Expected: **30 PASS / 0 FAIL / 4 NOT_RUN of 34.**

### P6 — CI

**Unchanged.** V22 stays a pure function of the Pack and gains no database access, so the
Smoke job's eight failing checks stay byte-identical. The new rule is a world rule and
reports NOT_RUN in CI, joining V11 and V32 — **it does not add a new failing check name,
because Smoke's V11/V32 line names unevaluable rules as a set.**

If a ninth check name appears, this prediction was wrong and the cause needs finding
before anything merges.

## What would falsify the design rather than the prediction

- **V22 passing while the new rule also passes, with no discharge filed.** That would mean
  `HumanHeld` had become the escape hatch the coupling exists to prevent.
- **The new rule reporting NOT_RUN with a database present.** An absent row is an answer.
- **Gate 2 clearing.** Nothing about this change should clear a gate.

## Scored

*(filled in after the run, below the line, without editing anything above it)*
