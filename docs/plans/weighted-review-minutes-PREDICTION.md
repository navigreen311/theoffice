# Weighting `median_review_minutes` by coverage share — prediction, before the build

**8 September 2026.** Written before the change. Scored below the line without editing
anything above it. Each item says whether it was **reasoned from the code** or **assumed**.

## What is being built

`review_minutes_by_role` stops being *whoever is listed first* and becomes **weighted by
each person's coverage share within their role**. Two people at 6h, one at 4 minutes and
one at 3, gives **3.5** — which is what *"how long does a review take here"* means when
two people share the load.

**Mean would be defensible. First-in-the-list is the one option nothing chose** (B24).

## Two things checked before predicting

### Every other `setdefault` in the validator is the correct idiom

Six occurrences. **Only one is a first-wins policy.**

| line | shape | verdict |
|---|---|---|
| 473 | `escalations.setdefault(s.role, 0)` then `+=` | counter init — correct |
| 715, 1013, 1165 | `setdefault(k, set()).add(...)` | collection build — correct |
| 1509 | `out.setdefault(rule_id, blocks)` | a **deliberate fallback**: use the declared blocks only when source introspection found nothing. Correct, and intentional |
| **1570** | `review_minutes_by_role.setdefault(role, mins)` | **the bug** |

**So B24 is one instance, not a family.** Stated because the opposite — finding five more —
would have changed the size of this change materially.

### The two V13s do not aggregate the same way, and neither did before this change

**Gate 2 (`v13`, line 320)** pools **every** human regardless of role and takes a plain
**unweighted mean**: `sum(median_review_minutes) / len(human_capacity) × approvals` against
`sum(all coverage_hours)`. **No role split at all.**

**Gate 4.5 (the recheck, line 1597)** splits **by role**, sums coverage per role, and takes
the **first-listed** review time per role.

They were already inconsistent — one pools and averages, the other splits and takes first.
`LATER_GATE_REASONS` calls the Gate 2 one *"the estimate… the optimistic one"*, which
covers the headcount estimate but says nothing about the two using different aggregations.
**This change fixes the 4.5 one and leaves that inconsistency standing**, which is worth
naming rather than quietly half-fixing.

## Predictions

### Q1 — no verdict changes anywhere, for either venture · REASONED

**This is the load-bearing one and it is the answer to the P-12 question.**

Both Packs declare **one person per role**: Ivan as `venture_operator` (6h, 4 min), Dana
as `compliance_officer` (4h, 6 min). With one person in a role, **weighted average equals
that person's value** — 6 stays 6, 4 stays 4.

So: **Burkham 33 PASS / 0 FAIL / 1 NOT_RUN of 34. Greenstone 30 PASS / 0 FAIL / 4 NOT_RUN
of 34.** Unchanged.

**Greenstone does not flip.** The ambiguity B24 describes cannot arise with one person in
a role, so there is no verdict for the fix to change — **the fix is invisible until the
declaration that motivates it.** If Greenstone's verdict does move, this prediction was
wrong and the change is doing something it should not.

### Q2 — Gate 4.5 for Greenstone still fails V13 · REASONED

Greenstone fails the 4.5 recheck at 192 approvals against 144 minutes. Its
`compliance_officer` is one person, so the multiplier stays 6 and **the failure stands
unchanged**.

That matters for the same reason: **a verdict that changed here would be a verdict
changing without anything getting better**, which is P-12's lesson, and it would need the
same treatment — a written explanation that the number moved and the situation did not.

### Q3 — the declaration this unblocks · REASONED FROM THE ARITHMETIC

With two `compliance_officer` entries at 6h each, 4 min and 3 min:

- **Today:** 4 or 3 depending on list order → 480 or 360 against 432 → **FAIL or PASS**
- **After:** weighted `(6×4 + 6×3) / 12 = 3.5` → `120 × 3.5 = 420` against 432 → **PASS**,
  and the same answer whichever order the two lines are in

**The declaration becomes order-independent**, which is the point. It also passes — by 12
minutes, which is close enough that it should be said plainly rather than presented as
comfortable headroom.

### Q4 — tests · REASONED FROM GREP, AND MARKED AS SUCH

`grep` finds `median_review_minutes` in the two Packs, `pack.py`, both V13 sites,
`proposals.py` (display), the template, and `test_rules.py`. **Per Caveat 13 I have not
read each hit**, so I predict only this: **some test asserting a V13 message or a
capacity figure may need updating, and I will find out by running rather than by the
count.**

### Q5 — CI · NARROW

**Smoke's failing-check list stays byte-identical.** V13's Gate 2 path is untouched and
Smoke runs Greenstone, whose per-role arithmetic does not change. **I am not predicting
the rest of the board** — last time that claim was the wrong size.

## What would falsify the design rather than a prediction

- **A verdict moving for a single-person role.** Weighted average of one value is that
  value; anything else is a bug.
- **The result depending on list order after the change.** That is the entire point.
- **Zero coverage hours in a role producing a division by zero** rather than a stated
  answer.

## Scored

*(filled in after the run, below the line, without editing anything above it)*

*Nothing above this line was edited after the run.*

### Q1 and Q2 — CORRECT. Nothing flipped, for either venture

Gate 2 for both Packs: **0 FAIL**, V13 PASS, unchanged — that path was never touched.
Gate 4.5: `test_gate_4_5_catches_what_gate_2_could_not` still passes, which asserts
Greenstone **FAILS** V13 there.

**So the P-12 treatment is not needed.** The fix changed no verdict anywhere, because
both Packs declare one person per role and a weighted average of one value is that value.
**The fix is invisible until the declaration that motivates it** — which is the right
shape for it to have, and the opposite of a verdict moving while nothing got better.

### Q3 — CORRECT, and now pinned by a test rather than by arithmetic on paper

Two officers at 6h, 4 min and 3 min: weighted **3.5**, `120 × 3.5 = 420` against **432**
available → **PASS**, byte-identical message in either order. **12 minutes of headroom**,
which is thin and should be said that way.

### Q4 — WRONG, in the direction that costs nothing

Predicted *"some test asserting a V13 message or a capacity figure may need updating."*
**None did.** Collected tests went **1042 → 1046**, exactly the four added; the full suite
is **1046 passed**.

The hedge was honest but it was still a guess dressed as a range. The reason no test broke
is the one the prediction should have reasoned to: **no existing test constructs two people
in one role**, which is precisely why the defect survived this long.

### Q5 — Smoke: reported, not predicted

*(filled in when CI runs)*

### The check the prediction did not think to make

A passing new test proves the code does something; it does not prove the test would have
caught the old code. So the pre-fix validator was restored and the four run against it:

| test | pre-fix |
|---|---|
| order independence | **FAILED** |
| weights by coverage share | **FAILED** |
| no coverage at all | **FAILED** |
| one person in a role | **passed** |

**Three of four fail without the fix, and the one that passes is the one whose whole claim
is that nothing should change.** That is the shape it should have — and it was worth thirty
seconds to measure rather than assert, which is the same lesson as Caveat 12 arriving from
a different direction.

### The divergence this leaves standing, named rather than half-fixed

**Gate 2 and Gate 4.5 still aggregate review minutes differently.** Gate 2 pools every
human regardless of role and takes an unweighted mean; Gate 4.5 now splits by role and
weights by coverage share. The docstring explains why the two gates *see* different
approval counts — it says nothing about them *aggregating* differently.

Not fixed here, because changing Gate 2 would move a verdict that B24 is not about.
**Recorded so the next person finds it written down rather than by arithmetic.**
