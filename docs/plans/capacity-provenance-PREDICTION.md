# A provenance field on `human_capacity` — prediction, written before the build

**8 September 2026.** Written before the field exists. Scored below the line without
editing anything above it. Predicted narrowly: each item says whether it was **reasoned
from the code** or **assumed**, because P6 was wrong for exactly one reason — it reasoned
about one thing and claimed the board.

## What is being built

A required, non-empty provenance declaration on every `HumanCapacity` entry, saying **who
established the value and on what basis**, with `declared` / `inherited` / `measured` as
the distinction that does not currently exist.

**The third application of a pattern this codebase already has twice** — `NoFramework(why)`
and `HumanHeld.why` / ADR-0049's `not_applicable`. In each, the fix is not "allow a
comment" but **a distinct type that carries a reason**.

**Two things it must force rather than record:**

1. **Every existing value declares which it is.** Both Burkham entries and both Greenstone
   entries. **A field that new entries must fill while old ones sit exempt is a field that
   documents nothing** — and it is what retires B20 and B21 by construction rather than by
   trust.
2. **`inherited` names its source.** *"Copied from Greenstone's `human_capacity` block"* is
   a checkable claim. *"Historical"* is the cheap escape wearing a third costume, and the
   schema should refuse it the way `PendingActivation` refuses a one-word trigger.

## State before

```
burkham-wickmont   33 PASS / 0 FAIL / 1 NOT_RUN   of 34   (run 6a97fbe1 at gate 4)
greenstone         30 PASS / 0 FAIL / 4 NOT_RUN   of 34

human_capacity entries: Burkham 2 (Ivan, Dana) · Greenstone 2 (Ivan, Dana)
Burkham's block is byte-for-byte identical to Greenstone's.
```

## Predictions

### P1 — making it required breaks Pack loading until every entry is filled · REASONED

`HumanCapacity` is a `Strict` pydantic model, so a required field with no default makes
**both Packs fail `load_pack` with a `ValidationError`** until all four entries carry one.

**That is the forcing function, and it is the point.** A run cannot start, the validator
cannot report, and no rule returns NOT_RUN — the Pack does not load at all. Predicted
loudly rather than as a side effect, because it is the difference between a field that
documents and a field that decorates.

### P2 — four construction sites outside the Packs break · REASONED FROM GREP

`human_capacity` is constructed in **four** places besides the three Pack files:
`broker/pack_templates.py` (the new-venture template), `tests/provisioning/conftest.py`
(twice), `tests/validator/test_rules.py`, `tests/contract/test_approvals_api.py`.

**All four must be updated in the same commit.** The template's entry is all
`PLACEHOLDER`s and `0`s, so its provenance is honestly `declared` with a basis saying it
is a template placeholder — the template is the one place where an unfilled value is
correct.

### P3 — Burkham and Greenstone verdicts do not move · REASONED

No rule reads provenance. After the four entries are filled: **Burkham 33 PASS / 0 FAIL /
1 NOT_RUN of 34; Greenstone 30 PASS / 0 FAIL / 4 NOT_RUN of 34.** The rule count stays 34
— **no rule is added.**

### P4 — the goldens do not move · REASONED FROM GREP

`human_capacity` appears in **no** file under `tests/golden/snapshots/`. The generators
consume it (approval projection) but do not serialise it into an artifact, so a
`git diff --numstat` on the snapshots should be `0 0`.

**Stated as a prediction rather than assumed** because Caveat 6, as amended, says any
change that alters what a generator emits moves the goldens — and this changes a generator
*input*. The grep says it does not reach an artifact. If a snapshot moves, this prediction
was wrong and the cause needs finding before anything merges.

### P5 — what the four entries will say · REASONED FROM THE EVIDENCE ALREADY GATHERED

- **Greenstone × 2 — `declared`**, with a basis recording that no provenance was ever
  written and that these are the originals B21 is about. **Not `measured`:** nothing
  measured them. **Not `inherited`:** they are the source.
- **Burkham × 2 — `inherited`**, naming Greenstone's block as the source, which is
  byte-for-byte checkable.

**This is the part that retires B20 and B21**, and it does so by making the four numbers
say what they are rather than by anyone deciding whether they are right.

### P6 — CI · REASONED, AND ONLY ABOUT WHAT I CHECKED

**`Tests` will fail before I update the four construction sites, and pass after.**

I am **not** predicting Smoke. `scripts/console-smoke.sh` seeds and publishes a Pack, and
I have not read what its `human_capacity` looks like or whether it constructs one at all —
so **that is a region I am declining to predict**, and I will find out by running it.

Last time P6 claimed "CI unchanged" from Smoke reasoning and was wrong because `Tests`
counts things. This time the shape is reversed and the discipline is the same: **predict
what was reasoned about, name what was not.**

## What would falsify the design rather than a prediction

- **A provenance that satisfies the schema while saying nothing** — `"historical"`,
  `"legacy"`, `"unknown"`. If `inherited` can pass without naming a source, the field is
  the fourth costume.
- **Old entries exempt.** A default value, or the field being optional, makes it decoration.
- **A rule reading it.** Nothing should gate on provenance yet; this records, and B20/B21
  say what the numbers must become. A rule would be a separate decision.

## Scored

*(filled in after the run, below the line, without editing anything above it)*

*Nothing above this line was edited after the run.*

### P1 — CORRECT

Both Packs refused, two validation errors each, one per entry:
`human_capacity.0.provenance  Field required`. The forcing function works, and it works
by making the Pack unloadable rather than by making a rule complain.

### P3, P4, P5 — CORRECT

Burkham **33 PASS / 0 FAIL / 1 NOT_RUN of 34**; Greenstone **30 PASS / 0 FAIL / 4
NOT_RUN of 34**; rule count unchanged at 34. Goldens: **`0 0`, no snapshot moved.**

The four entries read as predicted — Greenstone's two `declared` (nothing measured them,
and they are the source), Burkham's two `inherited` naming
`packs/greenstone.yaml human_capacity`.

### P2 — WRONG IN BOTH DIRECTIONS, and the error has a name

Predicted four construction sites would break. **One did**, and the failure surfaced in a
file I never named.

| site | predicted | actual | what it really does |
|---|---|---|---|
| `broker/pack_templates.py` | breaks | **broke** | builds a literal dict — a real construction site |
| `tests/provisioning/conftest.py` | breaks | fine | **copies** an entry from a loaded doc: `dict(officers[0])`, inherits provenance automatically |
| `tests/validator/test_rules.py` | breaks | fine | **mutates** a loaded pack, constructs nothing |
| `tests/contract/test_approvals_api.py` | breaks | fine | a **docstring** mentioning the field |
| `tests/contract/test_packs_api.py` | not named | **broke** | where the template's failure surfaces |

**The error: I grepped for a string and predicted breakage from the hit count.** Three of
four hits were a copy, a mutation and prose. A grep finds mentions; it does not find
construction, and I read one as the other.

**Cousin of Caveat 12.** There the failure was reporting a result whose output was piped
away; here it is reasoning from a count without reading what each hit does. Both are
**substituting a cheap proxy for the thing itself** — and both were confident.

### P6 — CORRECT as far as it went, and it went exactly as far as it claimed

`Tests` failed before the template was updated and passed after: **2 failed, 1035 passed**
→ green. Smoke was explicitly not predicted and remains so until CI runs.

### The test caught the validator, and the word it caught was the example

`test_inherited_without_a_named_source_is_refused` failed on `"legacy"`… no — on
**`"historical"`**, which is **exactly ten characters**, and the first cut refused
`len(source) < 10`.

**The precise word used to justify the field passed the check meant to refuse it.** Fixed
by refusing a single token regardless of length: a source names something, and naming
takes more than one word.

Worth keeping because the test that caught it was written from the docstring's own
example — **the argument for the field was specific enough to become a test, and the test
was specific enough to catch the implementation.**
