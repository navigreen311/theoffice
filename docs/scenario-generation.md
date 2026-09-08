# Classed scenario generation — the maps, the caps, and where role coverage went

**Written by P-05, 8 September 2026. T-035.** The companion to
`docs/scenario-contract.md`, which says what a scenario *is*. This says what The Office
can actually produce, what it cannot, and why the second list is longer than anybody
expected.

Read `docs/scenario-contract.md` first, especially §7 (a rule is not an occasion), §11
A2.1 (the key), and A1.3 (the escalation migration). This file does not restate them.

---

## 1. The three caps, stated before anything else

A reader who finds a module at `demonstrated` rather than `certified` should find these
three before concluding somebody left work undone.

**Cap one — seven of nine, structurally.** `never_do_violation` and `silent_failure` are
in SimForge's `HELD_OUT_CLASSES` and The Office may never submit either. It cannot reach
the nine that `classify_certification_level` requires, at any level of effort. This is a
process control and not a gap: SimForge cannot certify an agent against scenarios the
agent's own authoring system wrote, so the two classes that most directly test refusal
and concealment are kept unseen. Carried in the artifact as the coverage dimension
`scenario_classes_the_office_may_submit`, 7 of 9, with both names listed as uncovered.

**Cap two — six of nine, in practice, for every module but one.** `rate_limited` has no
source anywhere. See §3.

**Cap three — the richest material in every manual feeds the class The Office may not
submit.** `record_consent`'s never-do list has thirteen entries and every one of them is
a scenario somebody could write in an afternoon. None of them may be written here. The
`never_do` section is also the best-written section of most of these manuals, because it
is the one the author had the most to say about. **The correlation between how good the
material is and how unusable it is here is not a coincidence** — the same property that
makes a rule sharp enough to grade is what makes it the thing an authoring system must
not grade itself on.

---

## 2. The maps

### 2.1 The three that are mechanical, and what makes them so

| class | instruction section |
|---|---|
| `happy_path` | `correct_sequence` |
| `permission_denied` | `failure_signatures` (its hard failure) |
| `escalation_required` | `retry_vs_escalate` |

All three sources are in `broker.instructions.REQUIRED_SECTIONS`, are refused empty by
`validate_sections`, and are refused empty again by a CHECK constraint on
`forge_operating_instruction`. **So a module with a live instruction has a source for all
three, unconditionally** — which is what makes the map mechanical rather than a guess
about content. The generator emits these three for every such module whether or not
anybody has authored content for it.

**A mechanical scenario is not an authored one.** It has a class, a section and an
instruction hash, and its `expected_behavior` and `expected_escalation` are empty until
somebody writes them. An empty required field is a violation on submission and not a
pass, so SimForge refuses it and names it. That refusal is the honest report that the
scenario is unwritten — and it is a different report from the module not having the
behaviour at all, which is what `not_applicable` is for.

### 2.2 `malformed_input` — a fourth mechanical map that deliberately is not one

`malformed_input` maps to `inputs`, which is *also* a required non-empty section. By the
argument above it could have been a fourth mechanical map, and it is not one.

**The reason is that three were ruled and four were not.** Widening a frozen interface by
inference is the failure this whole run is built to resist, and "the fourth one obviously
works the same way" is exactly how it would read in a commit. It is supported as an
authored class (`DEFAULT_SECTIONS` in `generators/scenario_content.py` gives it its
section) and it is not emitted mechanically.

**Open question for whoever holds the contract next:** should it be? Six of the eleven
CapitalForge modules have a genuine malformed-input occasion and several are the most
instructive scenarios in their manual — `submit_application`'s `approvedByUserId`
arriving as an empty string and surfacing as a *gate refusal* rather than a missing-field
error is the single best "the error you get is not the error you have" case in the
portfolio. Nothing is lost by leaving it authored-only; the question is whether the
mechanical floor should be four.

### 2.3 The four that do not map

**`partial_failure`.** Source is the `failure_signatures.partial_failure` split landed by
`scripts/split_silent_partial.py` on **three** CapitalForge modules:
`compliance_manifest_assemble`, `regulator_dossier_export`, `statement_pull`. The other
eight have `silent_partial` sections that are entirely about over-reading a success —
shared rule 1 restated per module — which is the `silent_failure` competency and is held
out. **Do not manufacture partial-failure content for the eight.** The script's own note
is the rule: *a thin section is a fact about the module, not a gap to fill.*

**`recovery_after_failure`.** Mandatory in practice — the default `OPERATION_DIMENSIONS`
carries the `recovery` dimension, so "when the rubric carries recovery" reads as "always"
unless a caller passes a custom rubric. **And it is degenerate for ten of eleven
modules.** For a pure read, recovery is the retry that `retry_vs_escalate` already
permits; for a never-retry module, the recovery procedure is written inside the escalate
section and is the same act the `escalation_required` scenario already tests.

`submit_application` is the one that is not degenerate, and the reason is worth keeping:
its second call is **refused by the state machine**, so the retry does not become harmless
— it becomes impossible. What is left for the agent is a genuinely separate act: read the
application's status, and if it is `submitted` the call landed. That is a recovery
behaviour with its own occasion and its own failure mode, and it is the only one here.

**A degenerate recovery is NOT a `not_applicable`.** "This scenario would test nothing the
escalation scenario did not" and "this module has no recovery behaviour" are different
claims, and only the second is a declaration. Where the recovery genuinely does not exist
— `record_consent` forbids the retry in §6 and forbids the read-back in §7, leaving the
agent nothing it may do — declare it, with that reasoning. Where it merely repeats the
escalation, say so in the reason rather than pretending the behaviour is absent, or
author the scenario and accept that it is thin.

**`never_do_violation`.** Held out. See cap three.

---

## 3. `rate_limited` — the recorded cap, and what was refused

**RULED: there is no ninth instruction section, and none will be added.**

There is no source for `rate_limited` in the eight Part 6.1 sections, and there is no
material for one in any live instruction in the portfolio except
`voiceforge/transcribe_call`. Not a thin source — no source. No manual describes a rate
limit, a quota, a 429 or a backoff, because with one exception none of these modules has
one.

**What was considered and refused: adding a ninth section and authoring it across every
instruction.** That would lift a label into the coverage count without changing anything
an agent knows, and it would then be *graded* — an agent certified on how it handles a
429 that its module has never returned. The label would move; the competence would not.

So the cap is emitted rather than closed. Every module declares `rate_limited` as
`not_applicable` with the reason, which reaches the cert as `VERDICT_NOT_APPLICABLE` and
never as a zero, and the declaration is a *statement* rather than a silence.

**The one that is not a cap:** `voiceforge/transcribe_call` has the material. It is a
Greenstone module, not a Burkham one, so it is outside this run's authorship — worth
knowing, because it means the one place the class is real is the one place nobody is
currently writing it.

---

## 4. Sizing — eleven modules, eleven reads

**Not extrapolable from samples.** The ratio swings 29% to 71% and it tracks what the
module does with what it is given. Counted as *authorable classes out of the seven The
Office may submit*; the remainder are `not_applicable` declarations, which still have to
be written and still have to say why.

| module | behaviour | authorable | the classes | ratio |
|---|---|---|---|---|
| `client_read_pii` | filters | 2/7 | happy_path, permission_denied | 29% |
| `portfolio_health` | filters | 2/7 | happy_path, permission_denied | 29% |
| `restack_recommend` | filters | 2/7 | happy_path, permission_denied | 29% |
| `client_read` | filters | 3/7 | + escalation_required | 43% |
| `client_read_credit` | filters | 3/7 | + malformed_input | 43% |
| `statement_pull` | filters | 4/7 | + malformed_input, partial_failure | 57% |
| `compliance_manifest_assemble` | assembles | 4/7 | + malformed_input, partial_failure | 57% |
| `regulator_dossier_export` | assembles | 4/7 | + escalation_required, partial_failure | 57% |
| `record_consent` | writes | 4/7 | + malformed_input, escalation_required | 57% |
| `scan_communication` | writes | 4/7 | + malformed_input, escalation_required | 57% |
| `submit_application` | writes | 5/7 | + malformed_input, escalation_required, recovery_after_failure | 71% |

**37 authorable scenarios and 40 declared absences, across 77 (module, class) pairs.**
Both halves are work: a declaration without a sentence is refused, and the sentence has
to be true.

### What the ratio actually tracks

**Whether the module can be given something wrong.** A pure read that takes no parameter
cannot be handed a malformed input, cannot fail partly, and — if its
`retry_vs_escalate` says *"Retry freely"* in full — has no juncture at which an agent
hands anything to a human. `portfolio_health` is the extreme: no path segment, no query
string, no body, no 404 because it takes no identifier, and a `retry_vs_escalate` section
that reads *"Retry freely."* **The section that exists to say when an agent stops and
asks a person says, completely, that there is never such a moment.** That is not an
authoring gap; it is what the module is.

**Two `escalation_required` findings that a sampler would have missed**, and they are why
this had to be eleven reads:

- **`client_read` has one despite "Retry freely".** Its §5 distinguishes `NOT_FOUND` from
  `CLIENT_NOT_FOUND` — the second means the mount guard resolved the client and the
  handler then did not find it, so a record disappeared underneath a read — and the manual
  says **"Escalate this one."** A module can be retry-free and still have an escalation
  juncture. Reading only the retry section would have declared this class absent on a
  module that has it.
- **`client_read_pii` and `client_read_credit` do not**, despite being the same shape and
  the same router. Their equivalent distinctions (`ACH_AUTHORIZATION_NOT_FOUND`, the 403
  that is not an absence) are *reporting* disciplines, not hand-offs. Three sibling
  modules, one escalation between them.

---

## 5. `compliance_flags_exercised` — the grep, and what it cost

**Contract A2.2(a) required this established by grep before anything was done with it.**

Readers of `CurriculumScenario.compliance_flags_exercised`, portfolio-wide:

```
generators/curriculum.py:129    the _coverage aggregation, in this same file
```

**That is the whole list.** `generators/validator.py:438` reads
`Scenario.compliance_flags_exercised` on the **Pack DSL** (`generators/pack.py:337`),
which is a different class wearing the same name — V22's surface, not this artifact's.
`broker/provisioning.py` does not send the field. Nothing in `console/`, `db/` or
`broker/` reads it on an operation scenario.

**What it used to be, and why that was the wrong value.** It was
`position.effective_compliance_flags` — every flag a position holds, stamped onto every
module that position operates. So `place_call` carried `recording_consent_required` *and*
`tsr_disclosure_required` because the Acquisition Analyst holds both, not because a
scenario exercised either. It read as *these flags were exercised* when the true statement
was *some position holding these flags could have exercised them*, and it made the
coverage dimension complete by construction rather than by evidence.

**What it is now: empty, with the coverage dimension counting domain scenarios only.**
Those carry per-scenario flag lists a human wrote in the Pack, which is what "exercised"
means. **A union across the positions operating a module was the obvious substitute and it
was not taken** — it would have reproduced exactly the claim that was wrong, one level up.

**The cost, stated because a number moving is a thing a reader must be able to check.**
For Greenstone the dimension is unchanged at 2 of 2: its two flags are both exercised by
authored domain scenarios, so the inflated source was never load-bearing there. **For any
venture whose domain scenarios do not between them exercise every declared flag, this
number goes down.** Down is the correction. A dimension that was complete because of how
it was computed was not telling anybody anything.

---

## 6. Where role coverage went

**Contract A2.2(b).** The operation key dropped the position, so `role` is empty on every
operation scenario. Role remains a live dimension — Gate 4.5, the approval projection and
the appointment path all reason about positions — so the question moved rather than
closing.

**It is now derived, and computed, as the coverage dimension
`positions_with_all_modules_covered`.** A position is covered when every module in its
`forge_modules_operated` has an operation scenario. The source is `RoleDefinition`, which
is where the position-to-module mapping has always lived; the operation scenario was only
ever carrying a copy of it.

**Computed rather than promised.** A note saying "role coverage is still derivable from
the roles artifact" would have been true and would have decayed silently. A dimension
that quietly stops being derivable is the shape `docs/blocking.md` B5's counter and V30's
population both failed on, and the way that gets found is somebody reading a denominator
two months later and being unable to reproduce it.

**What is genuinely gone:** nothing that was computed. There was no role-by-operation
coverage dimension before this change. What the artifact can no longer answer is "which
position's use of this module does this scenario describe" — and under A2.1 that question
has no answer, because the scenario describes the module.

---

## 7. For P-06, P-07 and P-08

**The interface is `generators/scenario_content.py`. The worked example is
`scenarios/record_consent.yaml`. Do not open `generators/curriculum.py`** — nothing you
need is in it, and the files are disjoint only for as long as that holds.

**Index by module, never by position.** A module operated by two positions is authored
once. That is what makes the three-way split add throughput rather than add merge
conflicts.

**Suggested partition, and the one place it does not follow the behaviour.**

| package | modules | authorable | declarations |
|---|---|---|---|
| P-06 · writes | `record_consent` (done), `scan_communication`, `submit_application` | 13 | 8 |
| P-07 · filters | `client_read`, `client_read_pii`, `client_read_credit`, `portfolio_health`, `restack_recommend`, `statement_pull` | 16 | 26 |
| P-08 · assembles | `compliance_manifest_assemble`, `regulator_dossier_export` | 8 | 6 |

**`regulator_dossier_export` writes — it mints an id, writes a row and emits an event —
and it is in the assembles group anyway.** Its manual and its sibling's are built as a
contrast: one is `at_most_once` and one is retry-free, and each says so by naming the
other. Splitting the pair across two packages would have two agents authoring the two
halves of one deliberate contrast, from two sides, with no way to see that the halves
disagree. That is a worse risk than a mislabelled partition.

**P-07 is the largest and it looks like the smallest.** Six modules, 16 authorable
scenarios, and **26 declarations** — more `not_applicable` prose than the other two
packages combined, because pure reads are where classes genuinely do not exist. A
declaration is not a shortcut: it needs the same reading of the manual, and the sentence
has to survive somebody checking it.

**Two things per scenario, and the generator supplies neither:**

1. **The precipitating situation.** `never_do[2]` reads *"Never record a channel that was
   not named."* That is a rule. The scenario is: a human forwards a note saying they are
   happy for us to reach out, the file has a mobile and an email, and the agent is asked
   to record consent. A `situation` that restates the rule has not been written.
2. **The escalation as prose**, on every class including `happy_path` — where the honest
   answer names the boundary the happy path stays inside, rather than claiming there is no
   boundary. A value that restates "escalation is expected" has not satisfied it.

**The situation has no field of its own on either side of the contract.** It rides in
`summary` on the Office artifact and inside `expected_behavior` on the wire, labelled
`SITUATION:` / `EXPECTED:` so a later revision can split them back out mechanically. That
is `AuthoredScenario.wire_behavior()`, and it is raised as **E-004** in
`PARALLEL_BUILD_ESCALATION.md` rather than left as a convention somebody discovers.
