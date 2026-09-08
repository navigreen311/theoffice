# PARALLEL_BUILD_ESCALATION.md

**Escalations raised by package agents during the parallel build.** One section per
item, newest package last. **Every entry here must also appear in its package's PR
description** — the merge checklist requires escalations surfaced rather than buried, and
a file nobody opens is a place to bury one.

An entry is either **BLOCKING** (the package cannot complete the task as written),
**RATIFY** (the package took a decision it was not clearly authorised to take, and is
declaring it rather than hiding it), or **RECORDED** (a finding for whoever holds the
contract next; nothing is waiting on it).

This file is created by the first package that needs it. That was P-05.

---

# P-05 — Office: classed scenario generation + the B4 content interface

---

## E-001 — BLOCKING the run's stated deliverable · `scenario_class` and `instruction_section` are still not sent

**What.** `broker/provisioning.py`'s `_curriculum_payload` builds each
`operation_scenarios` entry with `module_id`, `expected_behavior` and
`expected_escalation`, and no `scenario_class` or `instruction_section`.
`OperationScenarioSubmission` requires both. **SimForge therefore still rejects every
module at the Pydantic layer, before `validate_curriculum_submission` runs.**

**Why it is not already fixed.** Contract A1.2 puts that file on P-05's card **for
exactly two purposes** — the `expected_escalation` migration and the
`module_not_applicable` mapping — and says in terms that anything else there is still an
escalation. Adding two fields to the wire payload is neither. **So it was not done, and
this is the escalation instead.**

**What changed underneath it.** The reason those fields were absent has expired. The
code's own comment said they were absent because *"the generator produces one summary per
(position, module), not a classed probe of one instruction section"*. After this package
the generator produces exactly a classed probe of one instruction section, on every
operation scenario. The comment has been rewritten to say the true current reason
(package scope) and to point here; the fields are still not sent.

**The hunk it needs**, in `_curriculum_payload`, inside the `operation_scenarios`
comprehension:

```python
                "scenario_class": s.scenario_class,
                "instruction_section": s.instruction_section,
```

**What it unblocks.** `docs/coordination-plan.md`'s WHAT THIS RUN DELIVERS names
*"SimForge accepts the curriculum for the first time"*. This is what stands between the
payload and that sentence. It is two lines and it is not P-05's to write.

**What it does NOT unblock, so nobody reads the fix as more than it is.** Acceptance
still needs non-empty `expected_behavior` and `expected_escalation` per scenario, which
is B4 authorship — P-06/07/08. With these two lines and no authored content, the
submission moves from a **schema** rejection to a **validator** rejection, which is
progress of exactly one layer. That is still worth having: it is the first time
`validate_curriculum_submission` would run against a real Office payload at all, which
`docs/scenario-contract.md` opens by pointing out has never once happened.

`tests/provisioning/test_curriculum_payload.py::test_scenario_class_and_instruction_section_are_still_absent`
asserts the current absence, so the day it changes it is a decision somebody made rather
than a line that drifted in. **Delete that test with the fix.**

---

## E-002 — RATIFY · a third line changed in `broker/provisioning.py`

**What.** One line beyond A1.2's two purposes:

```python
-                "expected_behavior": s.summary,
+                "expected_behavior": s.expected_behavior,
```

**Why it could not be left.** This package made `summary` on an operation scenario carry
the **precipitating situation**. Left reading `summary`, the payload would send SimForge
the occasion in the field it grades the agent's response in. Both are prose, both are
non-empty, nothing raises, and no test in the repository would have failed. **That is the
identical failure mode A1.3 gives as its reason for deleting the ternary rather than
adapting it** — the payload gets worse while every test still passes — arriving one field
to the left.

**Why it is arguably inside the migration rather than beyond it.** P-00 froze the
distinction into `CurriculumScenario` when it added the field: `expected_behavior`
*"replaces `summary`'s generated boilerplate as the field SimForge reads"*. Making
`provisioning.py` read the field the frozen dataclass names as the one SimForge reads is
executing an instruction already in the interface, not adding a purpose to it.

**Asked for:** ratification, or an instruction to revert it and take the wrong payload —
in which case E-001's fix must not land either, because the two together would submit a
situation as a behaviour to a validator that would now actually read it.

---

## E-003 — RATIFY · `compliance_flags_exercised` has exactly one reader, and it is in P-05's own file

**Contract A2.2(a) required this established by grep, and required an escalation rather
than a substitute if something reads it. Something does.**

**The grep, portfolio-wide.** The only reader of
`CurriculumScenario.compliance_flags_exercised` is `generators/curriculum.py:129` — the
`_coverage` aggregation, in this same file. `generators/validator.py:438` reads
`Scenario.compliance_flags_exercised` on the **Pack DSL**, a different class of the same
name and V22's surface, not this artifact's. `broker/provisioning.py` does not send the
field. Nothing in `console/`, `db/` or `broker/` reads it on an operation scenario.

**What was done.** Left empty, with a note — the disposition A2.2(a) prescribes for "if
nothing reads it there". **No substitute was chosen.** A union across the positions
operating a module was the obvious move and was not taken, for the reason the amendment
gives: it reads as "these flags were exercised" when the true statement is "some position
holding these flags could have exercised them".

**Why it is escalated anyway.** The literal reading of A2.2(a) is *escalate if something
reads it*, and something does. The reader needs no substitute — it needs a decision about
what its number now means — but the reading is the coordinator's to make, not P-05's.

**The consequence, so it can be checked rather than trusted.** The
`compliance_flags_exercised` coverage dimension now counts what **domain** scenarios
exercise, which are per-scenario lists a human wrote in the Pack. The previous value was
complete by construction: every flag a position held was stamped onto every module it
operated. **For Greenstone the number is unchanged at 2 of 2** — verified in the golden —
because both its flags are exercised by authored domain scenarios. **For a venture whose
domain scenarios do not between them exercise every declared flag, it goes down.** Down
is the correction; a dimension that was complete because of how it was computed was
telling nobody anything. Recorded in full in `docs/scenario-generation.md` §5.

---

## E-004 — RECORDED · the precipitating situation has no field on either side of the contract

**Not a request to change the contract. A finding, for whoever holds it next.**

`docs/scenario-contract.md` §7 says a scenario needs an occasion and names the
precipitating situation as one of the two things missing from every manual. §6 lists the
fields that reach SimForge, and **there is no field for it** —
`OperationScenarioSubmission` has `scenario_class`, `module_id`, `instruction_section`,
`expected_behavior`, `expected_escalation`, `never_do_entry`, and no situation.
`CurriculumScenario` has no such field either, and `generators/artifacts.py` is frozen.

So the thing P-06/07/08 are told to author is the one thing with nowhere to go.

**What P-05 did with it**, because it had to go somewhere and inventing a field on a
frozen dataclass was not available:

- On the Office artifact it rides in **`summary`**, which on an operation scenario is now
  the situation. (`summary` on a domain scenario is unchanged and is still the Pack's
  authored prose.)
- On the wire it rides **inside `expected_behavior`**, labelled, as
  `SITUATION: …\n\nEXPECTED: …` — `AuthoredScenario.wire_behavior()`. Labelled rather
  than blended so that a later contract revision can split them back out mechanically
  instead of by parsing prose.
- In the **content file** the two stay separate fields, so an author has to write the
  occasion as an occasion and a reviewer can check that it is not a restated rule.

**The honest objection, recorded not resolved.** `summary` now means one thing on a
domain scenario and another on an operation scenario, which is two distinctions wearing
one name — the shape amendment R6c was written about. It is documented in three places
rather than left to be discovered, and the alternative was worse: putting nothing in the
artifact, or blending the occasion into the behaviour irreversibly.

**The recommendation, deliberately not implemented:** a first-class `situation` field on
`OperationScenarioSubmission` (P-02's file) and on `CurriculumScenario`. That is a
cross-repo contract change, it is late, and nothing is blocked on it.

---

## E-005 — RECORDED · one line added to the `Dockerfile`

**What.** `COPY scenarios/ scenarios/`, immediately after the existing
`COPY packs/ packs/`, with a comment saying why.

**Why.** Authored scenario content is data, not code. The build stage wheels
`broker/`, `client/` and `generators/`, and a YAML file inside a package does not ride in
a wheel without package-data configuration in `pyproject.toml` — which is on the
always-forbidden list. `packs/` solves the same problem the same way, and `scenarios/` is
resolved the same way `packs/` is: by a path relative to the working directory, which is
`/app` in the image.

**What happens without it.** The image finds no authored scenarios and reports every
module as uncovered. That is true of the image and false of the repository, and it is the
kind of wrong number that reads as work to do.

**Why it is declared rather than assumed.** `Dockerfile` is not on P-05's card and not on
the always-forbidden list, which names `package.json`, `pyproject.toml`, `tsconfig.json`,
`tailwind.config.*` and CI workflow files. It is one line, it mirrors the line above it,
and the "Images build" job exercises it. **If the coordinator reads the Dockerfile as
shared infrastructure, the alternative is to make content Python modules under
`generators/` so it ships in the wheel** — worse for the humans authoring it, and P-05
will take that direction if given it.
