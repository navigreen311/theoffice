# Ask to SimForge: repeating an exam without changing the submission

From The Office, 23 September 2026. Asked by Ivan Green.

This is a question, not a design. SimForge owns the battery, and every
mechanism named below exists for a reason SimForge wrote down. Nothing
here proposes which one should move.

## The question

**What would it take to run an already-graded exam a second time, with
the submission unchanged, so two sittings of the same exam can be
compared?**

## Why it matters now

The Office has spent a day reading score changes as evidence about
instruction text. Today alone:

    assign_contract  1.000 -> 0.667   showing the instruction sections
    assign_contract  0.667 -> 0.833   revising correct_sequence
    assign_contract  0.833 -> 0.333   adding a precedence paragraph
    property_lookup  0.600 -> 0.400   the same paragraph

Each was read as the text having an effect. **None of them is separable
from the noise floor, because the noise floor has never been measured.**

## What is measured

The spread WITHIN one sitting, across seeds, on the six exams currently
recorded:

    property_lookup  Victor Serath      0.778, 1.000, 0.667    spread 0.333
    assign_contract  Ronan Valek        0.714, 0.714, 0.571    spread 0.143
    assign_contract  Seraphine Valek    0.571, 0.571, 0.429    spread 0.142
    buyer_match      Seraphine Valek    1.000, 0.909, 1.000    spread 0.091
    buyer_match      Ronan Valek        1.000, 1.000, 1.000    spread 0
    comp_analysis    Victor Serath      1.000, 1.000, 1.000    spread 0

So seeds move a result materially — `property_lookup` by 0.333 inside a
single exam, which is larger than every instruction effect listed above.

## What is not measured

Whether **two whole sittings** of the same exam agree. The attempt
spread above is within one battery; the exam score is not the mean of
those attempts and does not vary with them in a way The Office can
derive. A second sitting is the only thing that answers it.

**Until it is answered, The Office cannot say how large a score change
must be to mean anything**, and every conclusion in the paragraph above
is provisional.

## What The Office verified blocks it, on SimForge's side

Read from SimForge's tree at `ee6c627`, not assumed. Four links, each
documented:

    OperationRun.runRef        UNIQUE. One row per ref, permanently.
    open_run                   idempotent on run_ref; "returns the row
                               untouched rather than restarting its clock"
    unscored_runs              selects verdict IS NULL AND endedAt IS NULL,
                               so a graded run is never picked up
    battery_sweep              triggerable=False, scheduler only (ADR-0050),
                               hourly at :20

And one on The Office's side, which is also deliberate:

    mint_run_ref               deterministic over the submission's natural
                               key, so a retried hand-over lands on the run
                               already open instead of starting a second
                               window with a young clock (your ADR-0044)

**The Office cannot reach past any of these, and should not.** A ref is a
function of the submission; an unchanged submission is the same ref; the
same ref is the same run; a graded run is never re-scored. That chain is
what makes a verdict mean something, and the last thing this ask wants is
for it to be loosened from this side.

## What an answer would have to preserve

Stated so that a shape that breaks one of these can be ruled out early.

1. **The Office must not be able to re-run an exam at will.** A caller
   that can re-sit a failed certification until it passes is a
   certification bypass with a polite name. Whatever this is, the
   decision to repeat should not be The Office's alone.

2. **Neither sitting may overwrite the other.** The comparison IS the
   result. A repeat that replaces the first verdict answers nothing and
   destroys the baseline.

3. **The submission must be provably identical.** If anything about the
   curriculum, the instruction, the keys, the protocol or the rubric
   differs, the two sittings are not the same exam and the number is not
   a noise floor. The Office's ref already carries a digest of each of
   those — content hash, scenario-set hash, sections hash, protocol,
   rubric — so the evidence exists on both sides.

4. **Nothing new crosses the boundary.** Whatever comes back is read
   through `simforge_response_manifest.json` and
   `assert_no_scenario_content` unchanged. Two scores and a run
   reference would be enough.

5. **Idempotence must survive.** Whatever distinguishes a deliberate
   repeat from a retried hand-over, it cannot be something a retry can
   produce by accident — that is the guard `open_run` exists to be.

## What The Office is not asking for

- Not a way to re-run on demand from the provisioning path.
- Not a change to `mint_run_ref`. Determinism is the control.
- Not the held-out partition. Separate question, separate contract.
- Not an answer today. A stated position is enough to stop The Office
  reading score changes as though the floor were zero.

## What The Office will do in the meantime

Report score changes with the measured within-sitting spread beside
them, and stop calling a change smaller than that spread an effect.
Entry 180 already requires a control module to be held unrevised on
every revision; three controls held exactly today, which is the only
reason three simultaneous drops could be attributed to one paragraph.

That control is weaker than a noise floor and is not a substitute for
one: it says the day did not move, not that the number is reliable.
