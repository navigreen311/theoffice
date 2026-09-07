# Blocking — what must exist before Burkham Wickmont serves a client

Not deferred. Deferred items are in `capitalforge/docs/decisions/deferred.md` and
each one has a reason it can wait. **Nothing on this page can wait**, because each
is a thing the system currently claims and does not have.

The distinction matters more than the list. A deferred item is work not yet done.
An item here is a **capability the vocabulary already assumes** — ten operating
instructions, the Business Pack and the compliance library all use words that mean
nothing until these exist, so every document that reads correctly today is
overstating the system until they do.

---

## B1. Approving a proposal does not execute it

**Every Burkham position is `trust_tier_ceiling: propose`.** All five. So `propose`
is not one path among several — it is the only tier any Burkham agent will ever
hold, and it is the tier that does not complete.

What works: a call below `auto_execute` is refused, a `proposal` row is written
with the payload and trace, and `POST /api/proposals/{id}/decide` records an
approval. Verified end to end on 3 September 2026 against `scan_communication` —
no Forge call, no ledger row on either side, nothing written at CapitalForge.

What does not exist: **any path from an approved proposal to the call it
describes.** `proposals.mark_executed` — the function that links an approved
proposal to the call that carried it out — has no production caller. Only its
tests call it.

So an operator approves a proposal and nothing happens. The proposal sits
`approved` forever, which is indistinguishable from a queue that has not reached
it yet.

**Interim state, 3 September 2026.** The refusal now names the gap instead of
saying "a proposal was created", and `proposals.decide` stamps the same fact into
`decision_reason` on every approval. That makes the gap unmistakable. It does not
close it.

**What "tier vocabulary means nothing" refers to.** Ten operating instructions
declare `Trust tier: propose`. The Pack sets five ceilings to `propose`. The
compliance library is written around a human approving before an agent acts.
Every one of those is describing a workflow whose last step is not built.

**Blocks:** any Burkham agent doing anything. There is no tier at which an agent
can complete an act — `auto_execute` is not granted anywhere in this Pack, and
`propose` stops at the proposal.

---

## B2. Nine operating instructions exist as files and none is authored

`forge_operating_instruction` holds live rows for simforge (2), cre-forge (4) and
voiceforge (2). **CapitalForge has none.** All nine manuals are markdown in
`docs/instructions/` and have never been loaded.

Three consequences, and the third is the one that was hiding:

1. **V11 fails for every CapitalForge module**, which is Gate 2 blocked.
2. **Unit A certification has nothing to bind to.** A certification is earned
   against an instruction's `content_hash`; with no instruction, the bootstrap
   used a synthesised hash that corresponds to no text.
3. **Staleness could not fire.** `recompute_staleness` skipped any cert whose
   module had no live instruction, so a certification bound to nothing was the one
   thing that could never go stale. Fixed 3 September 2026 — a Unit A cert with no
   live instruction is now `stale_instructions`, and the call path refuses it.

**That fix stopped the bridge dispatching, which is the correct state.** The
adapter, manifest, credential, venture-to-tenant map and the ledger join on both
sides are all proved and that evidence stands. What is no longer true is that a
CapitalForge module can be called, and it should not be until a real instruction
exists to certify against.

**Blocks:** Gate 2, and every grant.

---

## B3. No SimForge verdict for any CapitalForge module

Every CapitalForge certification was written by a script. They carry
`simforge_verdict IS NULL` and a `scenario_pack_ref` beginning `NO SCENARIO RUN -`.
See `certification.md`, which carries this above the fold.

**Blocks:** a real client. Not the bridge — a bootstrap was the right call to prove
the plumbing — but the two must not be confused, and a bootstrapped certification
looks identical to an earned one everywhere except that column.

---

## B4. SimForge's own certification was issued by nothing, and could not have been otherwise

On 4 September 2026 The Office made its first brokered call to SimForge. It required a
Unit A and a Unit B certification, and both are bootstraps:

    unit A   agent x simforge x gate_result    attested_by = 'bootstrap'
    unit B   engineering x simforge            attested_by = 'bootstrap'
             rubric_version = 'phase0.9-simforge'
             simforge_verdict IS NULL

Same shape as B3, and one degree worse in a way worth stating plainly.

### The circularity

A Unit A certification answers *"may this agent operate this module?"*, and the thing that
answers it is a SimForge scenario run. **The module here is SimForge's own.** So the
certification that permits the first call to SimForge would have to come from SimForge,
which cannot be called until the certification exists.

There is no ordering of those two events that is not a bootstrap. This is not a corner
that was cut; it is the base case of a recursive definition, and the only honest thing to
do with it is write it down where somebody will find it.

### Why that circularity is the argument FOR scenarios, not against them

The tempting reading is that a certification which cannot be earned proves the requirement
is ceremonial. It proves the opposite.

Every other certification in this system is supposed to mean *an agent was put through
scenarios it could fail and did not*. This one means **a human decided**. Those two things
are indistinguishable in the `certification` table except for one column — which is exactly
why `attested_by` was added on 3 September, and exactly why B3 exists. If the distinction
did not matter, there would be nothing to record here.

The moment SimForge can run a scenario pack against its own `gate_result` module, this row
should be replaced by one that column can vouch for. Until then, an agent holds
`auto_execute` on a Forge because somebody said so.

### What retires it

**A SimForge scenario pack for `simforge/gate_result`, run by a DIFFERENT SimForge
instance than the one being certified.** That is the part that is not obvious: running the
pack on the same instance certifies the thing against itself, which is where this entry
started. A second instance — a staging deployment, or a container the CI job starts — is
what makes the verdict mean something, because the certifier and the certified are then
two systems that can disagree.

That is also the strongest argument yet for SimForge having a deployment. It has never had
one (`simforge/docs/adr/ADR-0045`), and this is the first requirement that a compose file
on a developer's laptop cannot satisfy.

**Until then:** the row says `bootstrap` and carries its reason. A reader who filters
`attested_by = 'simforge'` will not find it, which is the whole point of that column.

**Blocks:** nothing today — the bridge is proved, and a bootstrap was the right call to
prove plumbing, exactly as B3 says. It blocks **any claim that SimForge is certified**, and
it will block a real client for the same reason B3 does.

---

## B5. The Village quarter is a counter that drifted from its clock, and The Office stamps it

**Found 6 September 2026, the first time the Village was running and The Office could
read it.**

`shift_assignment.quarter` is the agent-quarter an assignment belongs to, and
`one_venture_per_agent_quarter` is enforced against it. The value comes from
`village.quarter()` — the Village's own `QuarterBoundary`, read over HTTP. **The Office
has no other source for it and no way to sanity-check it.**

### What the Village currently reports

```
quarter_state.json    current_quarter: 2027Q4   transitions: 7
board clock           tick: 0   day_number: 0   village_date: "Day 1 of Month 1, Year 1"
```

`QuarterBoundary` advances one quarter per 90 elapsed Village days, where
`elapsed_days = current_tick // day_length`. **At tick 0 it can never advance.** Seven
transitions are recorded against a clock that has not moved.

Corroborating, and independent of the arithmetic:

- `config/objectives/` contains **only `2026Q1.yaml`**. Each of the seven transitions
  called `_load_quarter_objectives` for a quarter with no file and loaded zero targets.
- All 27 objectives on the board are `2026Q1`. **The Village's current quarter contains
  no objectives at all.**

`run_harness --fresh` deletes `positions.json`, `school_state.json`, `lodge_state.json`
and `homes_state.json`. It does not delete `quarter_state.json`, so the counter is
monotonic across every reset of the world it is supposed to be measuring. (Not the test
suite: `tests/test_quarter_plan.py` passes `tmp_path` throughout.)

### Why this blocks

**Issuing a shift now binds it to `2027Q4`** — a label produced by a counter that drifted
from its tick, naming a quarter with no objectives, while every real thing in the Village
sits in `2026Q1`. The agent-quarter is not a display value: it is the unit
`one_venture_per_agent_quarter` enforces on, so a wrong one silently partitions
assignments against a boundary that corresponds to nothing.

Nothing has been stamped from it. The Phase 0 shift is in `2026Q1` and stays there.

### The two fixes, and the one that is not available

Both real options are Village-side:

1. **Reset the counter to agree with the tick**, and make `--fresh` clear
   `quarter_state.json` with the rest of the world state.
2. **Drive the quarter from the tick on read** rather than persisting a transition count
   that can outlive its clock.

**Not available: keeping it as a monotonic sequence number.** A sequence number spelled
`2027Q4` is read as a date by everyone who sees it — and already was, by Ivan, on the
morning of 6 September, from The Office's own output. A value whose format asserts
"fourth quarter of 2027" cannot also mean "the seventh time a counter incremented"; the
format is the claim. If it is a sequence number it has to be spelled like one, and then
The Office's `quarter_is_a_village_quarter` CHECK (`^[0-9]{4}Q[1-4]$`) rejects it, which
is the schema correctly refusing to store a sequence number in a date-shaped column.

---

## B6. Every rule that has only ever been NOT_RUN is untested where it matters

**V30 is the evidence, and the generalisation is the point.**

V30 had been NOT_RUN for its entire life — the Village was never reachable, so
`depts.seats()` always returned `None` and the rule returned early every time. On
6 September the Village came up, the rule reached its comparison for the first time, and
**its pass path was wrong**: it filtered its subjects with `if name in seats`, compared
none of them, and reported `len(wanted)` as the number verified. It answered *"3
department(s) have seats for what the Pack asks"* about three departments the Village
does not have.

Reading it had not found that. Nothing had, because the code had never executed.

### The general statement

**A rule that has only ever reported NOT_RUN has never had its pass path run.** NOT_RUN
exits early by construction; everything after that exit is unexecuted. So the rule is not
"passing once unblocked" and it is not "known good pending a connection" — **it is
untested in the only direction that decides anything.**

Treat the first PASS of a newly reachable rule as unverified until you have watched it
compare something, and check what it counted.

### Which rules this currently applies to

Verdicts below are against `greenstone` 1.1.0 on 6 September, Village up:

| Rule | State | What has never executed |
|---|---|---|
| **V24** | NOT_RUN by construction at Gate 2 | Its whole body. It is evaluated at Gate 4.5 against appointment output — and **no provisioning run has ever reached Gate 4.5**, so neither path has run anywhere. |
| **V31** | NOT_RUN | Its comparison. `voiceforge/place_call` is a hand-written registry row never verified against the Forge, so the rule has no shape to check a tier against. |
| **V32** | FAIL here, **NOT_RUN in CI** | In CI the world is database-only and no adapter is running, so V32 cannot ask and reports NOT_RUN — documented in `tests/world.py::dispatch_from_registry`. Its pass path has only ever run locally. |
| **V11** | FAIL here | Not NOT_RUN today — it fails on `generate_loi` having no instruction. Listed because its voiceforge subjects have never been reached in a passing state. |

**NOT_RUN is not always whole-rule, and that matters for reading this list.** V32 today
reports FAIL on the two modules it could ask about *and separately* states it could not
ask voiceforge at all — one rule, a verdict for part of its subject and NOT_RUN for the
rest. A rule can be green on what it reached and silent on what it did not, so "which
rules are NOT_RUN" is not the whole question; "which subjects were compared" is.

That is the same question B5's counter fails and the same question V30 failed. The
general rule for writing these is in `docs/pack-validator.md`.

---

## B7. The venture_forge_manifest was never generated — two hand-placed rows look like one that was

**Found 2026-09-06**, while confirming that a Pack republish had produced a manifest row.
It had not, and checking is what found this: the row was expected to be missing, and the
other four were the surprise.

### What is there

```
venture_forge_manifest, venture_id = 'greenstone'
    cre-forge / property_lookup     is_required, hard
    simforge  / gate_result         is_required, hard
```

**Two rows against seven declared modules.** Both were written by hand — `property_lookup`
by `bootstrap_phase0` so the Phase 0.8 call would not be UNDECLARED, and `gate_result` by
the equivalent SimForge bootstrap. Neither was generated.

`runtime_config.apply` is the only thing that writes this table, and it runs at **Gate 5**
of the provisioning ladder. **No run has ever reached Gate 5.** So the manifest for
greenstone has never been generated at all.

### Why this is worse than an empty table

An empty manifest is obviously unconfigured. **Two rows look like a working manifest with
something missing** — which is how it read this morning, when the question was "did
`assign_contract`'s row appear" and the answer looked like "no, just that one".

These five declared modules are UNDECLARED, and **every call to any of them is blocked
with a HIGH incident** at step 4 of the call path, before the tier gate:

    buyer_match · comp_analysis · underwrite_deal · assign_contract · run_scenario_pack

`property_lookup` works. It is the only module anybody has called, and the only one with a
row, and those two facts have the same cause: somebody placed the row by hand to make one
call succeed.

**Pre-existing, and not caused by today's publish.** Publishing has never written this
table and was never going to.

### What running `runtime_config.apply` for greenstone would take

It is reached at Gate 5, so everything before it must pass first:

| gate | state today |
|---|---|
| 2 | **blocked** — V11 FAIL (five CRE instructions unauthored, `PENDING_AUTHORING` is a Pack placeholder not a row), V32 FAIL (`simforge/run_scenario_pack`, which decision 5 rules stays declared and unbound), V31 NOT_RUN (`voiceforge/place_call`, which decision 6 records as a capability VoiceForge never had) |
| 4.5 | **blocked** — V24 unfilled positions, and V13 at 192 approvals a day against the declared reviewer coverage |

So it is not a command to run. It is: author five operating instructions, resolve two
standing rulings about modules that do not exist, and settle Greenstone's capacity — which
has failed Gate 4.5 since it was first authored, by design of the check rather than by
accident.

### What it writes when it does run

| table | what |
|---|---|
| `venture_forge_manifest` | one row per declared module — the thing missing here |
| `agent_forge_grant` | grants, **inactive** (`activated_at IS NULL`, so `is_assignable` is false and the call path refuses them until Gate 11 activates them) |
| `venture_budget` | the Pack's budget block |
| `rate_limit_bucket` | per-agent and per-Forge buckets |

Idempotent by construction; it returns counts so a second run can be asserted to write
zero.

**The shortcut is the thing that created this.** Hand-writing four more manifest rows
would unblock the calls tonight and leave the same defect one module wider: a table that
looks generated and is not, disagreeing with the Pack the moment either changes. If rows
are placed by hand again, they should be placed knowing that.

---

## What is NOT on this page

**`lender_match` and `build_packet`.** They have no implementation under any
spelling, and the Pack declares both at `criticality: hard` with a role defined
around `lender_match`. That is blocking for the *Pack as written*, but the fix is
a ruling — build them, or take them out the way `bureau_pull` and `readiness_score`
were on 1 September — rather than work. It is not on this list because nobody
should do it without deciding first.

**`statement_pull` and `portfolio_health`.** Routes exist and are bindable. What is
missing is a manual, which is authorship, not engineering.

## B8 — the timeout sweep has never been able to run

**Found 2026-09-07**, while building the client that would have used it.

`broker/simforge.py` carries the longest argument in that module for why The Office,
not SimForge, must detect a run that never answered:

> *the case that matters most is the one where SimForge's worker died — and a process
> that has died cannot report that it has. A deadline held by the party that is
> waiting is the only version of this check that survives the failure it exists to
> catch.*

The mechanism is `overdue_submissions()`, which selects `curriculum_submission` rows
with `result_received_at IS NULL` past a deadline, and `timeout_gate_result()`, which
builds a TIMEOUT verdict keyed on `simforge_run_ref`.

**Gate 8 never set `simforge_run_ref`.** Its INSERT named eight columns and that was
not one of them, so every submission it wrote carried NULL there. A submission with no
run ref cannot be correlated to a verdict — there is nothing to look the verdict up by
— so the sweep had nothing it could resolve, and `VERDICT_TO_STATE[TIMEOUT] ->
in_training` stayed unreachable for a second reason after the first one was fixed.

**This is a control that was written, reasoned about at length, defended against an
alternative design, and dead the whole time** — because the field it keys on was never
populated by the only thing that writes those rows.

**Nothing reported it.** No test covered the sweep against a real submission, the
column is nullable so the INSERT was valid, and the reasoning in `simforge.py` reads as
a description of working behaviour. It was found by building the hand-over that would
have used it, which is the only reason it surfaced now rather than at the first hung
run.

**The general shape.** A control's argument being sound says nothing about whether it
can execute. This one was reviewed on the strength of its reasoning, which was correct,
and the reasoning never touched the question of whether its input arrives. **Ask of any
control: what populates the field it keys on, and has that code ever run?**

Fixed in the same change: Gate 8 now sets `simforge_run_ref` from SimForge's response,
and `handed_over_to_simforge` is true only when a ref came back rather than when the
row was written.

**Still open**: nothing calls `overdue_submissions()` on a schedule. The sweep can now
resolve a submission, and no timer invokes it. That is a separate gap and it is not
closed here.

## B9 — SimForge's never-do rule has no correct submission

**Found 2026-09-07**, building the Gate 8 hand-over against SimForge's validator.

`validate_curriculum_submission` rejects a submission whose declared `module_never_do`
carries an entry with no matching `never_do_violation` scenario. That class is in
SimForge's `HELD_OUT_CLASSES` — *"SimForge authors these classes as the HELD-OUT set
(not exposed to The Office)."*

**So declaring a never-do list honestly is rejected for missing scenarios The Office is
structurally forbidden to write.** Omitting the list passes, and leaves SimForge's
`ForgeInstructionSet.neverDo` empty — which its own comment says exists *"so an n/a can
be told from a coverage hole"*.

The honest path is refused; the passing path erases the distinction the field was added
for. Those are the only two.

**The Office declares its never-do lists and takes the 422.** A refusal naming a real
gap is a true statement; a submission that passes by withholding what it knows is not.

**The fix is on SimForge's side**, because both conflicting controls are: either SimForge
authors the `never_do_violation` scenarios for a declared list, or the validator stops
requiring what it will not accept from a submitter. Raised there as
`docs/adr/ADR-0048-the-never-do-trap.md`, open.

**Not the only reason submissions are refused today.** `curriculum.generate` produces one
unclassed scenario per (position, module), so every module also fails the
`escalation_required` rule. That is the Office's own work — and B9 would still be here
after it is finished, which is why it is recorded separately.

**The shape worth keeping.** Two controls, each correct where it was written, that cannot
both be satisfied. No review of either catches it, because neither is wrong on its own.
It surfaced only when something actually exercised both at once.
