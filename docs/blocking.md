# Blocking — what must exist before the ventures this page names can serve a client

Not deferred. Deferred items are in `capitalforge/docs/decisions/deferred.md` and
each one has a reason it can wait. **Nothing on this page can wait**, because each
is a thing the system currently claims and does not have.

The distinction matters more than the list. A deferred item is work not yet done.
An item here is a **capability the vocabulary already assumes** — ten operating
instructions, the Business Pack and the compliance library all use words that mean
nothing until these exist, so every document that reads correctly today is
overstating the system until they do.

## Scope — widened 2026-09-08 (T-101)

**This page was titled for Burkham Wickmont, and its contents stopped being only
Burkham's some time ago.** An item here is **venture-scoped** or **cross-cutting**, and
from today a new one says which, on its own line under the heading:

```
**Scope:** venture-scoped: burkham-wickmont
**Scope:** venture-scoped: greenstone
**Scope:** cross-cutting
```

**The existing seventeen are not retro-filed.** Going back to tag B1 through B17 would be
seventeen judgements made in one pass by whoever happened to be here, and several of them
are not obvious — which is the same guessing that produced the department mapping in
decisions entry 12. They stay as they are. **B-numbering continues unbroken**: the next
item is B18 and nothing is renumbered.

### The drift, recorded because the shape recurs

Nothing announced that the scope had moved. The page kept a title naming one venture while
it accumulated items that are not about that venture at all:

- **B4** is SimForge's own bootstrap certification — SimForge's, not Burkham's.
- **B13** is a defect in V33, a validator rule — every Pack's, not one venture's.
- **B17** is a git command's output misread as a backlog — not a venture fact at all.

**It was only visible when something arrived that obviously did not fit.** A stated scope
drifts from its contents without being wrong on any single day: each individual addition is
defensible, and nobody re-reads the title while adding to the body. That is the same shape
as decisions entry 3 going stale — a statement true when written, left in place while the
thing it described moved, and correct-looking the entire time.

**The tag is not a filing system.** It exists so that the next item that does not fit is
visible when it arrives rather than three months later.

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

### Updated 2026-09-08 — the manuals are authored, and this item's headline is false

**`forge_operating_instruction` now holds 11 live rows for capitalforge, not none.**

| forge | live | total |
|---|---|---|
| capitalforge | **11** | 17 |
| cre-forge | 5 | 9 |
| simforge | 2 | 4 |
| voiceforge | 1 | 2 |

**Consequence 1 above is retired.** V11 does not fail for CapitalForge modules any
more, and it does not fail on `generate_loi` either. Against both Packs on 8 September
it reports, in its own words, *"instructions are authored for all 10 module(s)"*
(Burkham) and *"instructions are authored for all 6 module(s)"* (Greenstone).

**Consequences 2 and 3 are not assessed here.** Whether existing Unit A certifications
are still bound to the synthesised hash from the bootstrap is a separate question about
`certification` rows, not about whether an instruction exists, and nothing in this
update looked at it. Item B2 stays open on that basis alone.

**The reason this is worth writing down is what it was costing.** See the note under B6.

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

### Updated 2026-09-08 — V11's NOT_RUN was read as unfinished curriculum for a week, and the curriculum is finished

**This is a correction to what was left, not to a rule.** The **V11** row in the
table above is superseded by this section: it reads `FAIL here` on `generate_loi`
having no instruction, and neither the verdict nor the cause is current.

V11 has reported NOT_RUN since the beginning, and NOT_RUN on a curriculum rule reads as
*the curriculum is not finished.* It read that way on the board all week. **It is
finished.** Every module on both Packs has an authored operating instruction — 10 of 10
on Burkham, 6 of 6 on Greenstone, and V11 says so in its own message before it declines.

What actually blocks it is **one unresolvable credential per Pack**, and nothing else:

| Pack | V11 | what it could not resolve |
|---|---|---|
| greenstone | NOT_RUN | `voiceforge: tenant credential unavailable` |
| burkham-wickmont | NOT_RUN | `capitalforge: tenant credential unavailable` |

Both are a missing environment variable. Neither is a document anybody has to write.

**Why it survived a week.** V11's verdict is one word and its cause is in the sentence
after it, and a rule whose subject is *whether the modules the curriculum teaches exist*
declines for a reason that has nothing to do with the curriculum. The verdict was read
and the sentence was not — and the run output that carries the sentence is a thing
nobody re-reads. B2's headline said the manuals were unwritten, which agreed with the
misreading and kept it alive after it stopped being true.

**What this changes on the board.** Authoring work that was believed outstanding is
done. What remains in its place is configuration — the same two credentials named in
`docs/decisions.md` entry 3's 2026-09-08 correction, one of which is a value that has to
be chosen and set on two sides rather than found.

### And a control observed working, which is rarer than a control failing

The table above says V32's message *"distinguishes modules it asked about from
voiceforge it could not ask"* — written on 6 September as reasoning about a message,
before any run had put it under load.

**On 8 September it faced a genuinely mixed verdict and held.** Four Forges reachable,
one unconfigured, and a real failure in the same rule at the same time:

```
V32 FAIL: 1 declared module(s) the Forge does not dispatch: simforge/run_scenario_pack.
A grant over one of these is a grant on a capability that is not there. SEPARATELY, and
not covered by this failure: could not ask capitalforge: tenant credential unavailable
— those bindings are unverified rather than verified, and fixing the modules named above
will not resolve them.
```

It did not fold the unverified bindings into the FAIL. It named the failure, named the
unasked Forge separately, and said in advance that fixing the first will not resolve the
second — which is the exact wrong inference a reader would otherwise draw from a single
verdict word.

**Worth recording because the entry 13 class is a list of controls that were reasoned
about and then found wanting.** This is one that was reasoned about and then observed
holding, the first time a real mixed case arrived. The distinction that survived is the
one that class exists to protect: *which subjects were compared* is a different question
from *what the verdict says*, and here the message answered both.

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


### RESOLVED 2026-09-08 — the refusal moved to scoring time, and there is no 422 to take

**This item is closed by `simforge` PR #134 (P-03), merged at `2ce2f5d`.** Flagged by P-03
itself as E-4: the text above is now false in a specific way, and a reader arriving here
would act on it.

**What changed.** The submission-time demand is gone. A declared `module_never_do` entry is
recorded as an outstanding obligation, written to the instruction set and echoed back;
coverage of it is decided at **scoring** time against SimForge's held-out scenarios, where
`never_do_status` already lived. **The refusal moved. It was not deleted** — and P-03
asserts that with a test rather than a sentence
(`test_the_never_do_refusal_moved_to_scoring_time_and_was_not_deleted`).

**The mirror image was closed in the same ruling.** The validator used to silently *accept*
a submitted `never_do_violation` as evidence — letting the certified party supply its own
refusal test. It is now refused. Ivan ruled both halves as one, because the trap and its
mirror are the same mistake about **who the rule asks**. See `simforge` ADR-0048, Resolved.

**Where the text above was wrong, and how it was found.** B9 said The Office "declares its
never-do lists honestly and takes the 422". **There is no 422 to take.** The trap was also
living in a test fixture — `test_office_bridge.py` had to author a `never_do_violation`
scenario to get a 200, and that had been read as a fixture rather than as the defect.

**An honest consequence, not a defect.** Every declared never-do entry is now an open
obligation, because SimForge's held-out authoring pipeline does not exist. Modules
declaring a never-do list will sit at `provisional`. **That is a real coverage hole
reported as one, rather than a 422 naming work nobody was allowed to do** — and building
held-out authoring is now the next piece of work rather than a blocked one.

## B10 — a position's modules are not all on the venture's Forge

**Found 2026-09-07**, by the first real hand-over against a live SimForge. Not found by
974 passing tests, and it could not have been.

`RoleDefinition.positions[].forge_modules_operated` is a list of **bare module ids**.
Gate 8 resolved each one's operating instruction under
`pack.forge_dependencies.operating_forge` — the venture's Forge — which is wrong whenever
a position operates a module belonging to another Forge. Greenstone's roles operate
`place_call` and `transcribe_call`, which are **voiceforge** modules.

### The failure it produced was specific, and it read as work

Not a crash, not a 500, not an empty result. It reported:

```
modules_skipped: ['assign_contract', 'place_call', 'transcribe_call']
    SKIPPED: no live operating instruction for this module
```

**Two of those three have a live operating instruction.** They were looked up under
`cre-forge`, found nothing, and were reported as uninstructed — which reads as a backlog
item: *somebody needs to write two operating manuals.* Acting on it would have meant
authoring instructions that already exist, and the duplicates would have gone in under the
wrong Forge, where they would have been found by nothing and used by nothing.

**A wrong answer that names plausible work is worse than one that names nothing**, because
the work gets done.

`assign_contract` was the true skip, and V11 says the same thing at Gate 2 — so one third
of the report was right, which is what made the rest of it credible.

### Why nothing caught it

The test world's roles operate the test world's modules, all on one Forge. Every fixture
agreed with the assumption, so every test passed under it. **The assumption was only
false against real data**, and it took a real submission to a real service to find it.

Fixed: each module's Forge is resolved from `forge_module_registry`. A module id
registered by two Forges is ambiguous and `forge_modules_operated` cannot say which was
meant — the first by `forge_id` wins, deterministically rather than correctly, and the
module id is the thing to fix if it ever happens.

**The general shape.** A composite key flattened to one of its parts, where the other part
was constant in every fixture. Ask of any lookup: **is this identifier unique on its own,
or unique within something the caller assumed?**


## B11 — a record written for something that did not happen, third instance in one day

**Found 2026-09-07.** Gate 8 wrote a `curriculum_submission` row for a module with no live
operating instruction — a module nothing was sent for, because there was nothing to bind a
certification to.

That row is not inert. `overdue_submissions` selects submissions with
`result_received_at IS NULL` past a deadline, so it would have surfaced **forever**, as a
run awaiting a verdict that could never arrive because no run was ever requested. The
sweep would have reported a hung hand-over that never happened.

### The shape, named because it is the third today

Three defects, one form: **a record whose existence asserts an event, written before or
without the event.**

| | |
|---|---|
| B8 | Gate 8 wrote a submission row and never set `simforge_run_ref`, so the sweep could find rows it could not resolve |
| entry 16 / `live` | a Pack marked live carries no record of whether it passed its gates |
| B11 | a submission row for a module nothing was submitted for |

And the near-miss in the same change: `handed_over_to_simforge` was hard-coded `False`
with a comment saying a record that read as a handover would record a fiction. **That one
was got right on the first try, by someone who thought about exactly this.** The other
three were not, in the same file.

**The rule.** A row in a table whose name is a past-tense event is a claim that the event
occurred. Write it when it does, and not when the attempt begins, is skipped, or fails.
If a record of the attempt is genuinely wanted, that is a different table or a different
column — not the same row with a NULL where the outcome goes.

## B12 — V11 will demand a manual for a forbidden module, and entry 20 is the trigger

**Found 2026-09-07**, checked before anyone hit it.

`V11` requires a live, teaching instruction for **every** module in
`positions_required[].forge_modules_operated`. It has no concept of
`forge_module_exclusion` — no join, no filter, no mention.

`voiceforge/place_call` is in Greenstone's operated set **and** in the exclusion table.

**Today V11 does not name it**, because its placeholder instruction exists and
`curriculum_quality.assess` rates that text `complete` — it is real prose, just not about
any module. V11 currently names only `assign_contract`.

**Entry 20 instructs that the placeholder be removed.** The moment it is, V11 reports:

```
no Forge Operating Instructions authored for: place_call
```

And the natural response to a validator naming a module is to write its manual — **which
the exclusion row now forbids in capital letters.** One rule would be asking for the thing
another rule prohibits.

**This is B9's shape**, arriving on a delay: two controls, each correct where written, that
cannot both be satisfied. The difference is that B9's conflict was inherited from another
system and this one is ours, created today, with the trigger written into our own
instruction. Nothing has fired yet only because a placeholder nobody wants is holding the
line.

**Not fixed here.** The fix is a ruling: either V11 skips excluded modules — with the
argument that a module no agent may hold needs no curriculum — or `place_call` comes off
`forge_modules_operated` entirely, which is a Pack change and a different conversation.
Both are defensible and they are not the same decision.

**Second defect in the same query, unrelated to exclusions.** V11 reads
`SELECT module_id, content FROM forge_operating_instruction WHERE superseded_at IS NULL`
and keys the result by `module_id` alone, with **no `forge_id`**. Two Forges with a
same-named module would silently satisfy each other's requirement, and the manual an agent
is certified against would be the other Forge's. That is B10 exactly — a composite key
flattened to one part — in a rule rather than in a gate.


## B13 — V33 is Pack-scoped, so a collision is invisible to Packs that don't bind the Forge

**Found 2026-09-07**, answering why the 4 September fix stopped at two modules.

V33 scopes itself to the Pack's own bindings:

```python
forges = sorted({b.forge.lower() for b in pack.forge_dependencies.forge_bindings}
                | {pack.forge_dependencies.operating_forge.lower()})
```

and groups collisions **by `forge_id`**. Two consequences, both live today:

**Burkham's V33 PASSES** — *"every live instruction on a bound Forge has its own
content_hash"* — while four cre-forge instructions are byte-identical. Burkham binds
capitalforge and simforge; cre-forge is simply not in its scope. **The same defect is FAIL
for one Pack and PASS for another, at the same instant, over the same table.**

**A cross-Forge collision is structurally invisible.** The hash `9711528544710550…` is
shared by six modules across *two* Forges, and V33 reports it as two separate collisions
because it groups by Forge. Had each Forge held only one module with that hash, V33 would
have passed on both while a certification still could not say which module an agent was
certified on — which is the exact question the rule exists to answer.

**Neither is why 46cd4f0 stopped at two.** That commit is titled `fix(simforge)` and its
own message says *"Zero certifications on any Forge are bound to 9711528544710550"* — the
author knew the hash spanned Forges and fixed the SimForge pair as that day's scope. **Out
of scope, not a rule limitation**, and worth saying plainly so nobody re-derives it.

The scoping is still a defect, and it is a different one: per-Pack scope is right for a
rule that gates a Pack, and it means **no rule anywhere asks the whole question**. A
Forge nobody currently binds can hold six identical instructions and nothing reports it.

## B14 — every ARV CRE Forge returns to an agent is the seller's asking price

**Found 2026-09-07**, while reading `underwrite_deal`'s source to author its manual.
**This is a Forge defect. It is recorded here and raised where the fix lives:
`navigreen311/medlink-wholesale`.**

### What happens

The Office adapter calls `DealAnalysisService.analyze_deal(deal_id)` and passes **no
comps**. `analyze_deal` accepts a `comps` argument; the adapter has no parameter for it
and an agent cannot supply one. So `calculate_arv` takes its no-comps branch on **every
call through this bridge**:

```python
if not comps:
    base_price = property.asking_price or Decimal("0")
    if base_price == 0:
        sqft = property.square_feet or 2000
        base_price = Decimal(str(sqft)) * Decimal("150")
    return (base_price, base_price * 0.85, base_price * 1.15, NO_COMPS_CONFIDENCE)
```

- **`arv` is the property's asking price.** The number being evaluated, returned as the
  evaluation.
- **Where no asking price is recorded it is `(square_feet or 2000) × $150`.** A property
  with neither analyses at exactly **$300,000**, a constant indistinguishable in the
  response from a computed figure.
- `arv_confidence` is `NO_COMPS_CONFIDENCE = 0.10`, against a `MAX_COMP_CONFIDENCE` of
  `0.80`. **0.10 is not an outlier here, it is the only value this path produces.**

**And everything downstream inherits it.** `max_allowable_offer = (ARV × multiplier) −
repairs − wholesale fee − closing costs`; `potential_profit`, `roi`, `deal_score` and
`deal_grade` are all functions of the same ARV. **None of them carries a confidence field
of its own.** An agent reading `max_allowable_offer` sees a bare number with nothing
attached saying what it rests on.

`estimated_repairs` compounds it separately: `_estimate_repair_scope` buckets
`year_built or 1980`, so a property with no recorded build year is silently priced as
`EXTENSIVE`.

### Why the manual is not the answer

`underwrite_deal`'s manual is being written and its `silent_partial` and `never_do`
sections state all of the above plainly. **That is the strongest argument for leaving the
module exactly as it is, and it is why this entry exists.**

Somebody reads a good `never_do` list, sees the hazard is known, documented and handled —
and the pressure to fix it goes. The documentation becomes the resolution. **A wrong
number with a permanent caveat is worse than one that gets corrected**, because the caveat
is load-bearing forever and is only as good as the last agent who read it.

The manual makes the defect legible to an agent holding the grant **today**, which is
worth doing and is why it is being written anyway. It does not make the number right.

### The two candidate fixes — a decision, not sympathy

**A. The adapter supplies comps.** `analyze_deal` already accepts them and
`calculate_arv` already weights and adjusts them. This is the intended path and it needs a
comps source the adapter can reach — `comp_analysis` is a bound module on the same Forge
and returns exactly this kind of data. Plausibly small; unconfirmed.

**B. The module refuses when it has none.** `underwrite_deal` answers 422 or a declared
`insufficient_comps` rather than returning a figure. **A valuation module that always
returns the asking price should not be answering.**

They are not exclusive — B is the correct floor whether or not A is built, because A can
still be reached with an empty comps list.

**Not a candidate: lowering the confidence further, or renaming the field.** The problem
is not that 0.10 is badly labelled. It is that a number derived from the seller's price is
being returned in a field named after an independent valuation.

### Scope

`cre-forge/property_lookup` holds the one live grant on this Forge and does not touch
this path. **No agent holds `underwrite_deal` today**, and its Unit A certification does
not exist. So this is a defect with no current victim — and the module is in Greenstone's
`forge_modules_operated`, so the first `underwrite_deal` grant issued is when it acquires
one.

## B15 — nothing cross-checks `compliance_flags_in_scope` against the declared surface

**Found 2026-09-07**, enumerating Burkham's flags before authoring scenarios against them.

A Pack states compliance obligations in two places that are never compared:

```
market.compliance_surface[].runtime_flag        what the venture is subject to
positions_required[].compliance_flags_in_scope  what a position is held to
```

**The gap runs both ways, and each direction is a different failure.**

### Direction 1 — a flag in scope with no framework

An agent holds an obligation that does not exist. It has a name, it appears on the
position, it reaches the runtime, and there is nothing behind it: no `applies_when`, no
jurisdiction, no library entry, nothing to be right or wrong against.

**This one has already been fixed, once, by hand, because somebody happened to notice.**
Burkham's own Pack records it at line 216:

> *Both of these were already in scope on a position and declared by no framework. The
> Compliance Reviewer and the Stack Manager carry `trigger_term_disclosure_required`, the
> Diagnostic Analyst carries `sb_lending_data_collection`, and the flag is the join
> between a position and an entry — so an agent held a flag with nothing behind it, and
> nothing reported that because no rule reads `compliance_flags_in_scope`.*

`REG_Z_ADVERTISING` and `CFPB_1071` were re-added to the surface to close it. **The fix
was correct and it was a person reading two lists side by side.** Nothing stops the next
one.

### Direction 2 — a framework with no role in scope

An obligation nobody is held to. The venture declares it is subject to a law; no position
carries it; no agent can violate it because no agent is measured against it.

**Eight of Burkham's twenty declared flags are in this state today:**

```
advance_placement_prohibited        facilitator_status_required
fair_treatment_required             outbound_contact_boundary_required
privacy_request_handling            recording_consent_required
referral_fee_permitted_in_state     tax_advice_boundary_required
```

Several are not marginal. `facilitator_status_required` says *"every engagement, in every
state, from intake through placement"* — declared as universal, carried by nobody.
`recording_consent_required` covers *"any recorded call, whoever dialled"*.

**And two of them are not orphans in the ordinary sense.** `fair_treatment_required`
governs *"any decision on which lenders a client is shown, or whether to serve them"*, and
`advance_placement_prohibited` governs *"any point at which a merchant cash advance could
be recommended, applied for or submitted"*.

**Both describe acts that are specifically the Placement Strategist's**, and neither is in
that position's `compliance_flags_in_scope`. It carries
`per_application_authorization_required`, `application_truthfulness_required`,
`estimate_not_offer_required` and `card_product_discipline_required` — four obligations
about how an application is prepared, and none about **who it is sent to** or **what may
not be placed at all**.

So this is not eight obligations distributed thinly across a Pack. **It is the role whose
acts are most consequential carrying neither of the two obligations that govern them** —
the ECOA one and the absolute one. Written up here because scenario `ps-003` in the Pack
exercises both, and a reader finding those flags on a Placement Strategist scenario would
reasonably assume the position declares them.

### Why V22 does not catch either

V22 compares the declared flags against the flags **scenarios claim to exercise**. It
never reads `compliance_flags_in_scope`. So a Pack passes V22 with every flag exercised by
a scenario attached to a role that does not carry it — and passes equally with a position
holding a flag no framework declares.

**The two lists that would answer the question are the two lists nothing compares.** This
is the V6 shape one table over: comparing two claims, where the third artefact that would
settle it is never asked.

### Not building a rule for this

Recorded, not fixed. A rule here needs a ruling first — whether a position's in-scope
flags must be a subset of the surface (direction 1), whether every declared flag must be
carried by at least one position (direction 2), and what the honest answer is for a
framework that genuinely applies to the venture and to no single role. Those are three
decisions and a rule would silently take all three.

### Updated 2026-09-08 (T-093, T-096) — the title names one direction and the defect is both

**Scope:** cross-cutting. *The heading says "against the declared surface", which is
direction 1. The body has always covered both. That asymmetry is worth stating, because a
reader who reads only headings takes away half of this item.*

**Nothing cross-checks the two lists in either direction, and that is why both failures are
silent.** No rule reads `compliance_flags_in_scope` at all — not to check it against the
surface, and not to check the surface against it. So:

```
direction 1   a position holds a flag no framework declares    nothing reports it
direction 2   a framework is declared and no position holds it  nothing reports it
```

**One direction has already been fixed once, by hand, because somebody happened to notice.**
`REG_Z_ADVERTISING` and `CFPB_1071` were re-added to Burkham's surface after a person read
the two lists side by side. That fix was correct, and **it is the only mechanism there is.**
The next instance depends on the next person happening to look, which is not a control.

That is the argument for this staying open rather than being marked half-done: **the
direction that was fixed is not safer than the direction that was not.** It was found once,
and it is no more findable now than it was before.

### T-081 assigns two of the eight orphans; six stay recorded and unassigned

Ruled 2026-09-08. The **Placement Strategist gains `fair_treatment_required` and
`advance_placement_prohibited`** — both govern acts that are specifically that role's
(which lenders a client is shown, and what may not be placed at all), and the position
carried neither. The Pack amendment is P-09's; the reasoning is decisions entry 24.

**The other six stay orphaned, deliberately:**

```
facilitator_status_required         outbound_contact_boundary_required
privacy_request_handling            recording_consent_required
referral_fee_permitted_in_state     tax_advice_boundary_required
```

**Each needs somebody who knows which role's duties actually touch it, and guessing is how
the department mapping in decisions entry 12 went wrong** — ten Burkham departments mapped
onto twelve Village ones that intersect at zero names, every assignment but one recorded as
a guess. Assigning six compliance obligations by plausibility is the same move with a worse
blast radius: an agent held to an obligation on somebody's hunch is then measured against
it in a certification.

**And one of the six is not an orphan at all.** `referral_fee_permitted_in_state` is held
by a human rather than by any agent, so there is no assignment waiting to be found — it is
B18's subject, not this item's. **Two flags move, one is reclassified, and five are
genuinely waiting on somebody who knows.**

## B16 — a pure-read module cannot satisfy SimForge's mandatory `escalation_required`

**Found 2026-09-07**, mapping instruction sections onto scenario classes for
`portfolio_health`.

`validate_curriculum_submission` makes one class mandatory for every module:

```python
if ScenarioClass.ESCALATION_REQUIRED not in classes_present:
    violations.append(f"module {mod}: no escalation_required scenario (mandatory)")
```

**`capitalforge/portfolio_health` has no escalation path.** Its `retry_vs_escalate` reads,
in full: *"RETRY FREELY. It is a pure read. Nothing is written, nothing is sent, and a
retry after a timeout costs nothing and duplicates nothing."* There is no failure this
module produces that an agent must hand to a human. It takes no identifier, so it cannot
be asked about something that does not exist; it writes nothing, so nothing can be half
done.

So its curriculum will be refused for lacking a class **whose honest content is that the
class does not apply here**. Authoring one anyway means inventing an escalation trigger
the module does not have — and that scenario would then be graded, and an agent certified
on responding to a situation that cannot occur.

**This is B9's shape a third time.** A validator requiring something a truthful submitter
cannot provide:

| B9 | `never_do_violation` required for a declared never-do list, and the class is held out |
| B14/#75 | (a Forge defect, different shape) |
| B16 | `escalation_required` mandatory for a module with no escalation |

**Not the same as B15's `rate_limited` ruling** (decisions entry 21), and the difference
matters. `rate_limited` is absent from every manual because no module rate-limits — a
uniform absence with one honest answer. `escalation_required` is present and rich for most
modules and structurally impossible for one, so no blanket ruling covers it.

**The fix is SimForge's, like B9's.** Either the mandatory class admits a declared
`not_applicable` with a reason — SimForge already treats `not_applicable` as a
first-class verdict elsewhere, *"a not_applicable dimension carries NO score (it is not a
zero)"* — or the rule reads the module's declared `is_mutating` and stops requiring
escalation of pure reads.

**How many modules this reaches is unmeasured.** `portfolio_health` is the one that
surfaced it. The other read-only modules — `client_read`, `client_read_pii`,
`client_read_credit`, `comp_analysis`, `buyer_match`, `property_lookup` — have not been
checked against it, and several do have escalation paths (a 404 on a read is still a
question for a human). Not all pure reads are escalation-free; this one is.

### This is why the eleven module reads are parked

Sizing the operation curriculum needs one read per module: what fraction of the seven
authorable classes each manual already supplies. Three are done and the ratio swings —
`submit_application` 5 of 7, `record_consent` 3 of 7 with a caveat, `portfolio_health` 2
of 7 — so a total cannot be extrapolated and the remaining eight would need reading
individually.

**That work is parked, and B16 is the reason.** Authoring against a validator that will
refuse at least one of the eleven regardless of how well it is authored is work done
twice: the scenarios get written, the submission is refused for a mandatory class the
module cannot honestly supply, SimForge changes the rule or admits a `not_applicable`,
and the affected manuals are revisited.

**The reads would not be wasted** — every class that maps stays mapped. What would be
wasted is the number they produce, because it is a number for a target that is going to
move. Sizing against a contract with a known open defect prices the wrong contract, and
the price is the thing the sizing exists to produce.

**What unparks it:** a SimForge ruling on B16, either way. If the mandatory class admits a
declared `not_applicable` with a reason, the eleven reads produce a real number. If it
does not, the answer for `portfolio_health` is that it cannot be certified through this
path at all — which is also an answer, and a different one to size against.

Recorded rather than left as a stalled task, because "we were going to read eleven
modules" reads afterwards as forgotten rather than deferred.

**Closed 2026-09-09, P-06.** The ruling B16 waited for went SimForge's way and it is
ADR-0049: **a mandatory class admits a declared `not_applicable` carrying a reason in
prose.** `capitalforge/portfolio_health` now declares `escalation_required` absent in
`scenarios/portfolio_health.yaml`, in 242 words that give the three facts the argument
rests on — it takes no identifier, it writes nothing, and its RETRY VS ESCALATE section
reads *"Retry freely."* in full. **The item is closed by a declaration, not by a
scenario.** Authoring one would have certified an agent for handling an escalation this
module cannot produce, which is the outcome B16 was written to avoid rather than a way
to clear it.

**Measured against SimForge's own validator, not predicted from the shape.** The real
payload The Office builds for this module was run through
`validate_curriculum_submission` in the `simforge` checkout:

| submission | violations | `module_levels` |
|---|---|---|
| with the declaration | **`[]`** | `demonstrated` |
| declaration stripped | **1** — *"module portfolio_health: no escalation_required scenario (mandatory)"* | `demonstrated` |
| with the declaration, empty reason | **3** — *"declared not_applicable with no reason"* | — |

The first row is B16 closed: the submission this module could not make is now accepted.
The second is the counterfactual it rests on. The third is the required prose refusing a
declaration without one, which is the property that keeps the first row from being a
loophole.

**The level is `demonstrated` today and that is the honest answer, not a shortfall.**
`classify_certification_level` reaches `certified_with_declared_absence` when supplied
and declared classes together cover all nine, and it strikes the held-out pair from the
declarations first — so `never_do_violation` and `silent_failure` must be *supplied*,
and only SimForge can supply them. Run with that pair present, the same function returns
**`certified_with_declared_absence`**. `certified` is unreachable in either state and
must stay so: it means all nine were exercised, and a declaration does not buy it. That
is §1.1's ceiling, structural, and it is the reason the third level exists at all.

**Two things were found on the way and neither is B16.** First, the declaration prose had
already landed in `37ede70` on 8 September — B16 stayed open for a day after the thing
that closes it was committed, because nothing tested it and nobody came back to the item.
**A blocker is closed by evidence, not by a commit that happens to satisfy it.** Second,
the required-prose rule is implemented on both sides as *non-empty after stripping*, so a
one-word reason passes. The four accidental empties that motivated the rule are caught;
a lazy sentence is not. Recorded here rather than fixed, because tightening either side's
refusal is a change to the mechanism and this item's scope was the declaration.

**What this unparks.** The eleven module reads were parked because at least one of them
would be refused regardless of how well it was authored. That is no longer true — a module
that genuinely cannot supply a class may say so and be accepted — so the sizing they exist
to produce is now a number for a target that has stopped moving.

## B17 — `--no-merged` reports a squash-merged branch forever, and a reader hears a backlog

**Found 2026-09-07**, taking an inventory of unmerged work before deciding what to merge.

`git branch -r --no-merged origin/main` listed **eighteen branches**. Seventeen had
already landed. The command was correct every time.

**Squash merging is why.** `gh pr merge --squash` writes one new commit onto `main` and
the branch's own commits never become ancestors of it, so the ref answers "not merged"
for as long as it exists — regardless of whether every line of it is on `main`.

**The command answers *has this ref been merged as a commit*. A reader hears *is this work
outstanding*.** Those are different questions and the second is the one somebody asks when
they run it.

### How to tell, and why the list did not

The direction of the diff separates them in one line:

```
ai-docs/v30-wrong-population        216 deletions,    0 insertions   ← behind main
ai-feature/simforge-pack-execution   4312 deletions,  71 insertions  ← behind main
ai-feature/simforge-client            261 deletions, 3568 insertions ← genuinely ahead
```

A branch whose content is on `main` is *behind* it. Seventeen of the eighteen were, and
not one added a file `main` lacked. **`--no-merged` cannot show that, because it compares
ancestry rather than content.**

### The second half, which was worse

Several of the eighteen did not exist on the remote at all. They had been deleted on
GitHub and the local `refs/remotes/origin/*` still held them, because nothing had run
`git fetch --prune`. **So part of the inventory was refs to branches that were gone**, and
a report was written from it before that was checked.

`git fetch --prune` collapsed the list from eighteen to one.

### Same class as the rollups

This is the family named in decisions entries 11, 14 and 16: **a true answer that loses the
distinction a reader needs.** Gate 4.5's summary line, V30's message, V32's verdict,
`produced_not_yet_certified`'s name, `live`'s meaning — and now a git command's output.

The tell is the same each time: **the artefact answers the question it was built to answer,
and the reader is asking a neighbouring one.** Nothing is wrong, and acting on it is wrong.

### What was done

Fifteen local and seven remote refs deleted, each verified individually first — deletions
heavier than insertions against `main`, and zero files added — rather than trusting the
list that produced them. `ai-feature/module-exclusion-registry` was kept despite being
merged: it is checked out in another session's worktree, and deleting a branch someone
else has open breaks their tree.

**What would prevent the next hour spent on this:** prune before listing, and read the
diff direction rather than the ref name. Neither is a control; both are habits, and this
entry exists because the habit did not fire.

## B18 — the compliance surface cannot say an obligation is held by a human

**Scope:** cross-cutting. **Found 2026-09-08 (T-092)**, ruling on T-080 during the parallel
build. The schema question nobody has asked.

**A compliance flag has exactly one meaning today: an obligation, carried by a position,
exercised by a scenario.** There is no way to declare an obligation the venture holds that
no agent carries — and Burkham has at least one.

### The instance

`referral_fee_permitted_in_state`. Whether a referral fee may be taken in a given state is
real, Burkham Wickmont is subject to it, and somebody has to be right about it. **That
somebody is a person.** No module places a referral fee, no position decides one, and no
scenario could exercise it without inventing an agent act that does not exist.

Both states the vocabulary can express are wrong:

```
declared and uncarried   V22 fails, correctly, on a flag that is correctly declared
not declared             the Pack denies an obligation the venture actually has
```

**When both available states are wrong, the missing thing is a word, not a value.** V22 is
not defective — it checks precisely what it says it checks. What is short by one
distinction is the surface: a **venture-carried** obligation as against an
**agent-carried** one.

### Why it is not being fixed here

Ruled T-080: the flag **stays declared** and V22 **keeps failing**, knowingly. Deleting it
to green the gate would assert the obligation does not exist. A Pack that then says Burkham
is subject to nineteen things when it is subject to twenty would validate cleanly, and that
is worse than the twenty failing — **the failure is the only thing pointing at the gap.**

A rule or a schema change written now would silently take three decisions nobody has taken,
the same three B15 names:

1. must a position's in-scope flags be a subset of the surface;
2. must every declared flag be carried by at least one position;
3. **what is the honest representation of a framework that applies to the venture and to no
   single role** — which is this item, and the one B15 recorded without a candidate answer.

### What it blocks, and what a reader must not conclude

**Blocks:** V22 on Burkham, and therefore Gate 2, for as long as this is open. That state
is intended for this run and is recorded in `PARALLEL_BUILD.md` so that a red V22 is not
diagnosed as an unfinished package.

**A green Gate 2 would mean something went wrong** — most likely that somebody deleted this
flag to make a check pass. **Read an unexpected pass here as a defect, not a win.**

### What retires it

A decision on how the compliance surface represents an obligation with no agent holder —
a third state, a holder field, or something else — followed by a rule that can then
distinguish the two cases. **Not** a rule alone: a rule written before the decision is the
decision, taken by whoever wrote the rule.

## B19 — Greenstone cannot ask voiceforge, and removing the FAIL in front of it changed nothing

**Scope:** venture-scoped: greenstone. **Found 2026-09-08 (T-100)** during the parallel
build, at the moment T-097b made it the only thing left in V32's message.

**Greenstone binds three Forges — `cre-forge`, `simforge`, `voiceforge` — and one of them
has never been asked a question.** `place_call` and `transcribe_call` are declared at
`criticality: soft` with `fallback_behavior: manual_handoff`, and every rule that would
resolve them against the Forge declines, because there is nothing at the other end to
decline from.

This is one Forge, one cause and one fix. It is not one setting.

### The cause, stated honestly: two things to set, and the order is the point

voiceforge has a row in `forge_registry` and is not registered in any sense that matters:

```
forge_registry.base_url   https://example.invalid
VOICEFORGE_TOKEN          absent
```

The clause the validator actually prints is `voiceforge: tenant credential unavailable`.
That is `broker/forge_modules.read()` failing at the credential resolver — **before any
request is made.** The base URL is never dialled, because nothing gets far enough to dial
it.

So `https://example.invalid` is **latent, not absent.** It is a second wrong value hidden
behind the first wrong value, in exactly the way this whole item is about.

**Which means setting the token alone moves the clause without moving the Pack.**
`tenant credential unavailable` becomes `unreachable: ...`, the verdict stays NOT_RUN,
nothing has been verified, and whoever set it has a changed message to show for an
unchanged fact. **Anyone retiring this item sets both, or has not started.**

### What it blocks

| Rule | Verdict | Cause |
|---|---|---|
| **V11** | NOT_RUN | `voiceforge: tenant credential unavailable`. Recorded in B6's 2026-09-08 update. Not an unfinished curriculum — Greenstone's is 6 of 6 authored. |
| **V31** | NOT_RUN | `voiceforge/place_call` is a hand-written `forge_module_registry` row never verified against the Forge, so the rule has no shape to check a tier against. |
| **V32** | NOT_RUN, **as of today** | `could not ask: voiceforge`. It was a FAIL until `run_scenario_pack` came off the SimForge binding. See below — the verdict moved and the Pack did not. |

Three rules, one missing pair of values. Gate 2 stays blocked on Greenstone for as long as
this is open.

### Why V32's verdict change today is not progress

**T-097b removed `simforge/run_scenario_pack` from this Pack (ruling Q-1,
`docs/decisions.md` entry 25, superseding entry 5). Greenstone's V32 goes FAIL -> NOT_RUN.
That is not movement, and it must not be read as movement.**

Both facts were in V32's message before the edit, and the rule was careful to keep them
apart — that separation is a control somebody built on purpose:

```
V32 FAIL: 1 declared module(s) the Forge does not dispatch: simforge/run_scenario_pack.
A grant over one of these is a grant on a capability that is not there. SEPARATELY, and
not covered by this failure: could not ask voiceforge: tenant credential unavailable -
those bindings are unverified rather than verified, and fixing the modules named above
will not resolve them.
```

Read the last clause again: **"fixing the modules named above will not resolve them."** The
message said in advance exactly what today's edit would and would not accomplish. The FAIL
was about a module that does not exist. The NOT_RUN is about a Forge nobody can ask. **The
second fact was always true — it was standing behind the first, and removing the first is
what makes it visible.**

**Nothing was fixed. One obstacle was removed from in front of another.** Greenstone's
Gate 2 is exactly as far from passing as it was this morning.

**And the board now looks better than the venture is.** On the totals recorded before this
change — 29 PASS / 1 FAIL / 3 NOT_RUN of 33 — moving the one FAIL into NOT_RUN leaves
**29 PASS / 0 FAIL / 4 NOT_RUN: a Greenstone board with no red on it at all, and a Gate 2
that is still blocked.** That arithmetic follows from the recorded totals; it is not a run
anybody has performed. It is written down here because a reader who sees zero failures and
concludes zero problems will have made the only mistake this item exists to prevent — and
they will have made it from a screen that agreed with them.

### The inverse of entry 22, and why it is the harder half

`docs/decisions.md` entry 22 separated two defects that had been treated as one: a state
that is **honest and invisible**, which accumulates, and one that is **dishonest and loud**,
which misdirects. Its instance was a `401 UNAUTHORIZED` from a bridge that was not mounted -
a quiet truth replaced by a loud falsehood, and it cost somebody a morning because a
specific error is what a careful person follows.

**This is the same family running the other way. A loud truth is replaced by a quiet one.**
Nothing here asserts anything false. V32's NOT_RUN is scrupulously accurate and says so in
its own words — *"NOT_RUN is not a pass."* It is simply quieter than what it replaced, and
it is quieter about a fact that has not improved.

| | entry 22's instance | this one |
|---|---|---|
| before | a quiet truth | a loud truth |
| after | a loud falsehood | a quiet truth |
| what the reader does | follows a specific wrong cause | stops looking, because the red went away |
| how it is caught | somebody acts on the message | **nobody acts at all — that is the failure** |

**Both make the reader worse off, and only one of them looks like a problem.** A loud
falsehood gets investigated. A quiet truth gets filed. The second is harder to catch
precisely because every individual statement in it is correct, and because the direction of
travel looks right.

### What retires it — and the honest answer is that it may go red

**Register voiceforge for real: a reachable `base_url` and a resolvable `VOICEFORGE_TOKEN`,
both, on both sides.** That is operator configuration of the shape R-1 already did for
capitalforge — not a document anybody has to write, and not a package.

**What that buys is that the Pack becomes askable. It does not buy a PASS, and the person
who does it should expect a new failure.**

`docs/decisions.md` entry 6 records `voiceforge/place_call` as **a capability VoiceForge
never had**, and V31 is NOT_RUN today precisely because that registry row was hand-written
and never checked against the Forge. So the likely sequence when the credential resolves is
**V32: NOT_RUN -> FAIL on `voiceforge/place_call`.**

**That is the rule finally doing its job. It is not a regression, and it is not something
this item's fix broke.** The Pack has declared an unverified module for as long as it has
existed; a credential is what lets anybody find out. **Do not put the placeholder back, and
do not read the fresh red as evidence the change was wrong** — the red is the first real
answer this binding has ever produced.

**There is a second reason to expect a surprise, and it is independent of `place_call`.
B6 states it as a general rule:** *"Every rule that has only ever been NOT_RUN is untested
where it matters."* **V32 has never resolved a single voiceforge binding — not once, on any
Pack.** That comparison has never executed against this Forge, so nothing about it has been
exercised beyond the branch that declines. B6's own evidence is V30, whose pass path had
been wrong for its entire life and was found to be wrong on the day the Village came up and
the code finally ran.

So the first real answer here is two things at once: **probably a FAIL about `place_call`,
and certainly a first execution** — which is exactly where B6 says the surprises live. Read
whatever comes back as a first result, not as a regression.

Written here rather than left to be discovered, for the same reason entry 25 records what
returns `run_scenario_pack`: a future reader should meet reasoning where they would
otherwise meet an absence.

### The pattern, said once, so three instances are not read as three coincidences

**A verdict that changed has not necessarily improved. Read the clause, not the verdict.**
`PARALLEL_BUILD.md` Caveat 3 states it as an operational rule. This item is the third place
in one month, in one repo, in one rule family, where it decides what somebody does next:

1. **It already happened.** V11 reported NOT_RUN and it was read as *the curriculum is
   unfinished* — for a week, on the board, while the curriculum was finished: 6 of 6 on
   Greenstone, 10 of 10 on Burkham, and V11 said so in its own message before declining.
   The real blocker was one missing environment variable. B6's 2026-09-08 update is the
   record. **The verdict is one word; the cause is the sentence after it, and the sentence
   was not read.**
2. **It is happening now.** V32 FAIL -> NOT_RUN on this Pack, above. The absence of red
   read as the presence of progress.
3. **It will be available again the moment somebody starts on this item.** Setting
   `VOICEFORGE_TOKEN` and leaving `https://example.invalid` changes
   `tenant credential unavailable` to `unreachable`, which is a different sentence under
   the same verdict, reporting the same unverified state.

The same misreading, three times, at three depths, on the same Forge. It is not a lapse of
attention by three people — **it is what a one-word verdict does to a reader when the
finding lives in the sentence underneath it.** That is why each of these is written down
with its clause rather than its verdict.

---

## B20 — V13's verdict is unactionable: real demand against a placeholder supply

**`venture-scoped: burkham-wickmont`** · Found 2026-09-08, at Gate 4.5 of run `6a97fbe1`.

V13 fails on Burkham: *"The compliance officer would receive 120 approvals a day. At 6
minutes each that is 720 minutes of review against 144 minutes available - 5 times over."*
It names three fixes — raise a trust-tier ceiling, add reviewer coverage, or cut scope.

**None of them can be chosen yet, because only one side of that ratio is Burkham's.**

| side | where it comes from |
|---|---|
| **120 approvals** | **Burkham's own structure.** 15 generated workflow steps × 8 decisions/day, every position at `trust_tier_ceiling: propose`, so nothing is skipped |
| **144 minutes** | **Greenstone's staffing, borrowed.** The Pack says so: *"INVENTED, and modelled on Greenstone's staffing so the Gate 4.5 comparison in the report is like for like. Burkham names no reviewer anywhere."* |

**Choosing between raise-a-tier, add-coverage and cut-scope on those numbers would be
deciding against a stand-in.** Cutting scope because a placeholder reviewer is overloaded
changes a real venture to fit an invented denominator.

### The same class as entry 15, one layer in

Entry 15 recorded that **every capacity number in this system is Greenstone's** — Burkham
has never been provisioned. That was about the numbers themselves. This is the same
borrowing surviving into a **verdict**: the Pack's comment is honest, and by the time it
reaches V13's message the provenance is gone. What the reviewer reads is *"144 minutes
available"*, stated as flatly as the 120 beside it, and nothing in the sentence says one
was measured and the other assumed.

**A rule that mixes a derived number and a placeholder in one comparison produces a
verdict with no honest reading.** It is not wrong — it is unactionable, which is a
different thing and needs saying differently.

### What retires this

Burkham's real reviewer coverage, declared in `human_capacity`: for each reviewer,
`human_name`, `role`, `coverage_hours`, `median_review_minutes`, `max_daily_approvals`,
`timezone`, `auth_method`, and a `backup_human`. **`role` is the field that matters most**
— `_reviewer_for` routes by it, and it is what decides whether a second reviewer relieves
anybody.

**Not code.** Until then V13's verdict should be read as *"this venture has more approval
demand than its declared reviewers can absorb, and its reviewers are not declared."*

### Is a real `median_review_minutes` measurable, or must it be declared?

**Measurable in principle, unmeasured in fact, and the column that looks like the answer
measures something adjacent.**

`proposal.review_seconds` exists and is well built: `proposals.decide` computes it **in
the database** as `EXTRACT(EPOCH FROM (now() - created_at))` rather than accepting it from
the caller, *"so a caller cannot report a review time it did not take."* There is even a
`RUBBER_STAMP_SECONDS = 5.0` guard on approvals below it.

**But it is null on every row that exists.** The `proposal` table holds two rows, both
`pending`, created 3 September and never decided. **No human has ever decided a proposal
in this system**, so there is not one observation to take a median of.

**And when it is populated it will not be `median_review_minutes` as V13 means it.**
`review_seconds` is wall-clock from `created_at` to the decision — it includes queue time.
A proposal raised overnight and approved next morning records ~50,000 seconds of "review",
of which the review was a minute. V13's multiplier is **how long a review takes**;
`review_seconds` is **how long a proposal waits**. They coincide only when a reviewer is
sitting on the queue.

That gap is structural rather than incidental: B1 records that approving a proposal
executes nothing and `mark_executed` has no production caller, so proposals are not
decided in any normal flow — which is also why there are two of them, pending, from five
days ago.

**So `median_review_minutes` is a declaration, like the coverage hours.** It can become
measured later, and the honest path to that is: decided proposals accumulate, and
something separates review effort from queue latency. Until both, it is asserted — and it
should be asserted by a named person on a stated basis rather than inherited.


### Two facts that hold whatever the supply side turns out to be

Both are levers that cost nothing and are currently unused. **Neither is a fix on its own.**

**1. 360 reviewer-minutes exist and 60% of them are idle.** `_reviewer_for` routes all five
positions to `compliance_officer`. Dana has 144 min/day; Ivan, as `venture_operator`, has
216 min/day and receives **nothing**. Moving the two all-read positions to Ivan gives
Dana 528 vs 144 and Ivan 128 vs 216 — Ivan fits, Dana is still 3.7× over. It does not
solve it and it is free.

**2. 32 of 120 approvals are pure reads.** Diagnostic Analyst (`statement_pull`) and Stack
Manager (`portfolio_health`, `restack_recommend`) operate nothing that writes. A human
approving them is approving a lookup. **They are freeable only as whole positions**,
because `trust_tier_ceiling` is per position and not per module — which is also why the
other 88 cannot be freed: each of those positions holds at least one write, and
Compliance Reviewer's is `regulator_dossier_export`, `at_most_once`, on the artefact that
goes to a regulator.

### Coverage hours sum across people; review speed does not average

`review_minutes_by_role` is built with `setdefault`, so **the first declared human of a
role sets the per-review minutes for that entire role.** `coverage_by_role` accumulates
with `+=`.

Anyone picking staffing numbers would reasonably assume both averaged, **and would be
wrong in the direction that makes the plan look feasible**: adding a fast second reviewer
buys coverage hours and buys nothing on the multiplier. A 6-minute first reviewer and a
2-minute second one is still a 6-minute role.

### The multiplier is borrowed too — B20's shape on the other side of the equation

**`median_review_minutes: 6` is not Burkham's either.** Burkham's entire `human_capacity`
block is **byte-for-byte identical to Greenstone's** — same two people, same roles, same
`coverage_hours` of 6 and 4, same `max_daily_approvals` of 60 and 30, same
`median_review_minutes` of 4 and 6, same timezone, same backups.

So V13's ratio for Burkham is **one real number over two borrowed ones**: 120 derived
from Burkham's own structure, divided by a coverage figure and multiplied by a review-time
figure, both of which are Greenstone's.

**And Greenstone's own numbers have no recorded provenance.** Its `human_capacity` block
carries no comment, and nothing in `docs/` records where 4 and 6 minutes came from. The
Burkham copy is at least labelled INVENTED; the original is not labelled at all, which
makes it the more dangerous of the two — **a number nobody flagged is one nobody
re-examines.**

### What the sensitivity actually shows, stated carefully

**At 6 minutes a review, correcting only the coverage side does not clear V13 for any
staffing anyone would plausibly declare**: two people at six hours each is still 1.7×
over, and it takes roughly 20 coverage-hours a day to pass. On that reading the
placeholder was **hiding a real shortfall rather than manufacturing one.**

**But that conclusion rests on the 6, and the 6 is borrowed.** At 3 minutes a review, two
people at six hours **passes**. The difference between failing and passing at plausible
staffing is entirely inside a number nobody measured.

**So the honest statement is narrower than "the shortfall is real":** the shortfall is
real *if* six minutes is right, and nothing establishes that it is. **Both inputs to that
judgement have to be declared before either can be trusted** — which is what makes this
item about the verdict being undecidable rather than wrong, on both sides rather than one.

---

## B21 — Greenstone's capacity numbers carry no provenance, and it has been failing on them since it was authored

**`venture-scoped: greenstone`** · Found 2026-09-08 while writing B20.

B20 records that Burkham's `human_capacity` is invented and borrowed. **This is the item
about where it was borrowed from, and it is the worse of the two.**

`packs/greenstone.yaml` declares Ivan at 6 coverage-hours / 4 median review minutes and
Dana at 4 / 6. **The block carries no comment.** Nothing in `docs/` records where any of
those four numbers came from — not the decision record, not the validator docs, not the
plans. They are asserted and unattributed.

**Burkham's copy is byte-for-byte identical and is labelled `INVENTED`.**

### The copy is more honest than the source

That is the finding. A reader of the Burkham Pack is told, in the file, that the numbers
are a stand-in modelled on Greenstone so the Gate 4.5 comparison is like for like. **A
reader of the Greenstone Pack is told nothing**, and there is nothing to find elsewhere.

**A number nobody flagged is one nobody re-examines.** Greenstone has been failing V13 at
Gate 4.5 on these figures since it was authored — 192 approvals against 144 reviewer
minutes, recorded in `decisions.md` entry 15 and in the Gate 4.5 finding that Greenstone
as authored is not staffable. **Every one of those verdicts was computed against a
denominator and a multiplier whose origin nobody wrote down**, and the failure has been
read as a fact about Greenstone's scope rather than as a fact about two unattributed
numbers.

That is not a claim the scope is fine. It is a claim that **nobody can currently tell**,
and that the not-staffable conclusion has been carrying more weight than its inputs
support.

### What retires this

Provenance for Greenstone's four numbers: measured, estimated by a named person on a
stated basis, or replaced. **A comment in the Pack saying which would retire it** — the
same sentence Burkham's copy already has.

If they turn out to be a stand-in too, then **every V13 verdict this system has ever
produced, for both ventures, has compared a derived demand to an undocumented supply**,
and the two Gate 4.5 halts on record are undecidable rather than settled.

### The trap for whoever returns to this

**A populated `review_seconds` must not be dropped into `median_review_minutes`.**

Once proposals start being decided that column will exist, be full, and look exactly like
the measured answer — while measuring **queue latency, not review effort**. It is
wall-clock from `created_at` to the decision; a proposal raised overnight and approved
next morning records ~50,000 seconds of "review", of which the review was a minute.

**The column's own quality is what makes it convincing.** It is computed in the database
rather than accepted from the caller, precisely so nobody can report a time they did not
take, and it carries a rubber-stamp guard. Everything about it says *trustworthy
measurement* — and it is one, of a different quantity than the one V13 multiplies by.

A number that is honest, well-built, full, and about something else is harder to catch
than a missing one.

---

## B22 — a venture can clear every gate to 10 with a reviewer who has no account

**`cross-cutting`** · Found 2026-09-08 while establishing what a real `human_capacity`
declaration would take. **Larger than the capacity question that surfaced it.**

`office_human` holds **one** non-fixture row: Ivan. Every other row is
`origin = 'test_fixture'`. **Dana is not a person in this system.** She is a string in two
Pack files — named as `compliance_officer` in Greenstone's `human_capacity` and, since
Burkham's block was copied wholesale, in Burkham's too.

### The join is a display-name string match

`broker/proposals.py` says so, in a comment that is honest and is the problem:

> *"The Pack names a reviewer; `decided_by` names an `office_human`. **The only link
> between them is the display name**, and when it does not match the page says the
> reviewer has no decisions rather than inventing a join."*

Refusing to invent a join is right. **The consequence is that a Pack can name anybody.**
"Dana" resolves to nothing, and the system reports that as *no decisions* — which is
indistinguishable from a real reviewer who has not decided anything today.

### What that costs, and it is not a display problem

**Nothing between Gate 0 and Gate 10 checks that a named reviewer exists.** V13 divides by
their `coverage_hours`; V15 and `separation_of_duties` reason about *distinct humans*;
the approval projection routes work to their `role`. **All of it runs on a name.**

`docs/console.md` already records where it ends:

> *"Greenstone's Pack names her as compliance officer under `separation_of_duties:
> distinct_humans`, and **she has no account, so Gate 10 cannot be signed.** Nothing said
> so — a run that cannot be finished looked exactly like one nobody had got to."*

So the failure is real, known, and **arrives at the last gate** — after provisioning has
issued grants, appointed agents and generated a manifest. A venture is carried nine gates
on the strength of a reviewer who cannot sign the tenth.

**It is in a docstring and a console page. It is not a tracked item, and it needed to be
one** — which is why this exists.

### Why it is cross-cutting rather than venture-scoped

It reaches Greenstone (Dana is named there first), Burkham (copied), and **any Pack
authored from here**: `pack_templates.py` emits `human_name: REPLACE_ME`, and nothing
refuses a Pack whose reviewer was never replaced with somebody real.

### What retires this

A check that every `human_capacity.human_name` resolves to an `office_human` row, at a
gate early enough to matter — **Gate 1 or Gate 2, not Gate 10**. And a decision about what
the link should be: a name match is what exists, and an id would be a schema change with a
migration behind it.

**Not built here.** Recorded so that the next reader meets it before a run does.

### The second half of the same gap, and it was never written down

Everything above is one direction: **the Pack can name a reviewer the system has never
heard of.** The mirror is equally true and has been sitting beside it unrecorded — **the
system will accept a review from someone the Pack never named.**

`record_human_review` asks `authorize(human, required_role="venture_operator",
venture_id=...)`. That question is *is this role strong enough, and does it reach this
venture*. It is **not** *is this person one of the reviewers this venture declared*, and
nothing else in the Gate 4 path asks that either.

So Burkham's Pack now names Ivan Green and Ira Green, and **any** human holding
`venture_operator` or stronger with scope over the venture — or with a global role, which
`strongest_role` treats as applying everywhere — can record the Gate 4 review. The Pack's
`human_capacity` has no say in who reviews. It is read by V13's arithmetic and by
`_reviewer_for`'s routing, and by nothing that gates the act.

**The two halves are one defect with two ends**, and either alone reads as smaller than it
is. A name in the Pack that reaches no account, and an account that reaches no name in the
Pack: the list of declared reviewers and the set of people who can actually review are
**two unconnected collections that both look authoritative.** Declaring real reviewers, as
Burkham now has, closes neither end — it makes the first end *look* closed, which is worse
than the state before, because the Pack now names two people who genuinely exist and still
does not mean they are the ones who signed.

**What retires it is the same join, used in both directions.** Once
`human_capacity.human_name` resolves to an `office_human`, the reverse check is available
for free: Gate 4 can ask whether the reviewer is among the declared ones. Whether it should
*refuse* a review from an undeclared human or *record* that it was undeclared is a separate
decision — an `ivan` doing an emergency review is a real case — but the current state does
not offer that choice, because it never knows.

---

## B23 — `max_daily_approvals` is decoration

**`cross-cutting`** · Found 2026-09-08.

**No gate and no validator reads it.** It appears in three places: the schema
(`generators/pack.py`), a template that sets it to `0`, and `broker/proposals.py`, which
uses it for a **display** — `remaining_today = max(0, max_daily_approvals - decisions)` on
a reviewer page.

**V13 does not use it.** The capacity check is
`approvals × median_review_minutes ≤ coverage_hours × 60 × 0.6`. `max_daily_approvals`
appears nowhere in it.

So Burkham declares Dana at **30** while the approval projection sends her **120 a day**,
and nothing anywhere notices. **A number that looks like a limit and is not one.**

### The fourth instance of a name asserting more than the code does

Alongside `produced_not_yet_certified` (a field name that reads as a fact about a venture
and is a fact about an appointment run), `live` on a Pack (publication state read as
validation state), and `review_seconds` (queue latency that will read as review effort the
moment it is populated — B21).

**Each is a name that is more specific than the thing behind it.** None is a lie; each
invites a reader to conclude something the code never claimed.

### What retires this

Either a rule reads it — a per-reviewer daily cap is a reasonable control and V13 does not
express one — or it comes off the schema. **What should not persist is a cap that looks
enforced and is not**, sitting in the same block as the numbers B20 and B21 are about.

**Half closed 2026-09-09 by P-08. Two of the four names renamed; two escalated, and the
escalations are the finding.**

| name | disposition |
|---|---|
| `max_daily_approvals` | **renamed** `advisory_daily_approval_ceiling` |
| `review_seconds` | **renamed** `queue_to_decision_seconds` (migration `0033`) |
| `produced_not_yet_certified` | **escalated** — E-010 |
| `live` on a Pack | **escalated** — E-009 |

**The third option B23 did not offer, and it is the one taken.** This entry says a rule
must read `max_daily_approvals` or it must come off the schema. Neither happened. The
number is now called `advisory_daily_approval_ceiling`, which says what it is: a figure a
venture declares, that nothing enforces, whose only consumer is a display. **A declared
ceiling nobody checks is still worth having in a Pack** — it is the reviewer's own
statement of what they can absorb, and a rule that reads it later is a smaller change than
authoring the number from scratch. What could not persist was a name claiming enforcement,
and that is what changed.

`tests/golden/test_generators.py::test_no_rule_reads_the_advisory_daily_approval_ceiling`
keeps the name true from the other side: it varies the value across five orders of
magnitude and asserts **every rule's verdict and message is byte-identical**, not just
V13's. If a rule ever does read it, that test fails and its message says to rename the
field rather than delete the test — because at that point `advisory_` is the part that
has become the lie.

**`review_seconds` is renamed rather than fixed, and the distinction matters.** B21's trap
is that the column measures queue latency and will read as review effort the moment it is
populated. **Separating the two is still unbuilt.** `queue_to_decision_seconds` does not
measure review effort any better than `review_seconds` did; it stops claiming to. Part 14
rubber-stamp detection reads the same column and is unaffected — an approval landing
under five seconds of wall clock from being raised is a rubber stamp under either name,
and that check never needed the distinction. `median_seconds` in the queue payload moved
with it (`median_queue_to_decision_seconds`), because it sat in the same dict as
`median_review_minutes` and was the trap in its most reachable form.

**What is left, and why neither was attempted.** Both remaining names change a serialized
artifact, which the package card separates from a rename that does not:

- **`produced_not_yet_certified`** is in `greenstone_appointment.json` and in
  `artifacts_hash`, which Gate 4.5 signatures are taken against. `decisions.md` reached
  this conclusion in September and declined the rename for the same reason.
- **`live`** is a `business_pack.status` value under a `CHECK` constraint and a partial
  unique index, and every write of it is in a file this package may not touch.

**And a fifth instance, found in the call sites of the first.** There are **two**
`produced_not_yet_certified`, counting different populations: the artifact field counts
candidates one appointment run examined, and `GET /api/ventures/{id}/capacity` counts every
active identity with no certified unit-A row, across every department. **The endpoint's
number is what the name says; the artifact's is not.** Both are now documented at their
definitions, and
`test_produced_not_yet_certified_counts_examined_candidates_only` pins the divergence with
the experiment that separates the two readings — an uncertified identity in a
department no position draws on. **Whoever takes the rename takes both**, because renaming
one leaves two numbers that no longer look related and are still consulted for the same
question.

---

## B24 — the order of two lines in a YAML file decides a gate verdict

**`cross-cutting`** · Found 2026-09-08, while establishing what declaring a second real
reviewer would take. **Recorded before any declaration, because the declaration cannot be
made honestly until this is settled.**

Two `compliance_officer` entries, same two people, same six coverage-hours each, same
**432** review-minutes available. V13's verdict depends on **which one is listed first**:

| listed first | min/review used | demand | available | V13 |
|---|---|---|---|---|
| Ivan (4 min) | 4 | 480 | 432 | **1.1× over — FAILS** |
| Ira (3 min) | 3 | 360 | 432 | **PASSES** |

`coverage_by_role` accumulates with `+=`. `review_minutes_by_role` uses `setdefault`, so
**the first entry of a role sets the multiplier for every person in it.**

### Its own class, and the opposite of B23's

B23 collects four names asserting more than the code does — `produced_not_yet_certified`,
`live` on a Pack, `review_seconds`, `max_daily_approvals`. Each is a name **more specific
than the thing behind it**.

**This one asserts nothing at all.** There is no field, no message, no name, and no
surface of any kind. **The order carries a decision nobody knows they are making** — and
the person who reorders that list for readability, or alphabetises it, or moves the
founder to the top out of courtesy, will be changing a gate outcome with nothing anywhere
telling them so.

A wrong name can at least be read and doubted. **An ordering cannot be doubted, because it
does not look like a claim.**

### `setdefault` almost certainly meant "do not overwrite"

That is the idiom's normal use in a dict-building loop, and it is a reasonable thing to
write. **It is not a reasonable policy**, and nothing marks the moment it became one. No
comment, no test, no docstring says *the first person decides for everyone* — which is
exactly what it does.

### What would fix it — not built here

**Either** `median_review_minutes` becomes a property of the **role** rather than of
whoever happens to be listed first — one declared value per role, and a per-person field
that no longer silently stands in for it.

**Or** the aggregation is **explicit and stated**: `min`, `max`, `mean`, or weighted by
each person's coverage share. Any of those can be argued with, and all of them are visible.

**Silently taking the first is the one option that cannot be right, because nothing chose
it.** A defensible aggregation is a decision somebody made; this is an artifact of a dict
idiom.

### Two adjacent facts, recorded here because the same declaration surfaces them

**The second compliance officer exists only through the first account.** `ROLE_RANK` is
`{venture_operator: 1, compliance_officer: 2, ivan: 3}`, and `assert_may_grant` requires
**strictly stronger** — *"not 'stronger or equal', which would let a compliance officer
mint another compliance officer and make the role self-propagating."* So `ivan` can grant
`compliance_officer`; a `compliance_officer` cannot grant one back. **Correct, and not
symmetric** — a two-officer arrangement is reachable only from the top role, and only the
top role can restore it if one is removed.

**V14 passes on the arrangement it exists to catch.** It fails a critical role with no
`backup_human` and checks nothing else: not that the backup is a different person, not
that they exist, not that they are not themselves a critical role, not that they have any
capacity. **Two compliance officers naming each other satisfy it** — while making both
critical-role backups the same two people, which is the concentration the rule was
presumably written to detect. And `backup_human` is a free string like `human_name`, so it
carries B22's problem too: it can name somebody with no account.

**Closed 2026-09-08.** `median_review_minutes` at Gate 4.5 is now **weighted by each
person's share of their role's coverage hours**. Two officers at six hours each, four
minutes and three, give **3.5** — the same answer in either order, which is the property
that matters more than the number. Where a role has no coverage hours at all there is no
share to weight by, so the fallback is the plain mean of the declared times and the rule
then fails on the thing that is actually wrong: nobody covers the role.

**Nothing flipped.** Both Packs declare one person per role, and a weighted average of one
value is that value, so Burkham and Greenstone are unchanged at every gate — Greenstone
still fails V13 at Gate 4.5 on the same arithmetic. **The fix is invisible until the
declaration that motivates it**, which is the right shape: it is not a verdict moving while
nothing got better.

**The survey the fix was worth doing for.** Six `setdefault` calls in the validator; five
are counter-init or `setdefault(k, set()).add(...)` collection builds, and the sixth
(`out.setdefault(rule_id, blocks)`) is a deliberate fallback for rules whose source cannot
be introspected. **B24 was one instance, not a family.**

**And the tests were checked against the old code, not just the new.** Three of the four
fail without the fix; the fourth — one person in a role — passes, because its whole claim
is that nothing should change.

## B25 — Gate 2 and Gate 4.5 aggregate review minutes differently, and nothing says so

**`cross-cutting`** · Found 2026-09-08, while fixing B24. **Not a defect on its own; a
divergence that was invisible until one half of it was written down.**

The two V13 implementations do not compute the same quantity:

| | roles | review minutes | coverage |
|---|---|---|---|
| **Gate 2** (`v13`) | **pooled — no role split at all** | unweighted mean across every human | sum of all coverage |
| **Gate 4.5** (recheck) | split per role | **coverage-weighted** within the role (B24) | sum per role |

The Gate 4.5 docstring explains at length why the two gates see **different approval
counts** — Gate 2 estimates from headcount, the Task Ledger computes from the real
workflow, *"and the Gate 2 estimate is the optimistic one."* That is deliberate and
documented. **It says nothing about the two aggregating their inputs differently**, and
that part is not deliberate — it is two authors, two moments, and no note.

**Why this is worth an item rather than a commit.** A reader who has read the docstring
comes away believing the difference between the gates is *which demand figure they use*.
It is also *which supply figure they use*, and that second difference has no explanation
anywhere. **A documented difference next to an undocumented one is worse than two
undocumented ones**, because the first one vouches for the second.

**What would fix it — not built here.** Either the two share one aggregation helper, or
Gate 2's docstring states its pooling as a deliberate simplification and says why. **The
second is probably right**: Gate 2 is explicitly the cheap estimate, and pooling is a
defensible thing for a cheap estimate to do. It just has to be a stated choice rather than
a difference somebody finds by reading both.

**Not fixed alongside B24 deliberately.** Changing Gate 2's aggregation would move a
verdict that B24 is not about, and B24's whole point was a verdict moving for a reason
nobody declared.

### Closed 2026-09-09 (P-09) — the second option, and no arithmetic

Of the two fixes above, **the second**: Gate 2's pooling is now stated in `v13`'s docstring
as a deliberate simplification, with the reason. **No expression that produces a number was
edited.** The whole diff to `generators/validator.py` deletes exactly one line, and that
line is a prose string.

**The reason, which is the part that makes it a choice rather than an apology.** Gate 2 has
no per-role demand figure to split against. `approvals` is one number off headcount and
agent-days, and the thing that would attribute it to a reviewer role — the workflow, and
the compliance flags on each step — is generator output that does not exist until Gate 3.
**The split is not skipped because it is expensive; at this gate there is no other half of
it.**

**Which way it errs, in both directions, because writing only the flattering one would be
this same item one level down.** *Pooling across roles errs optimistic and only optimistic*
— a slack role's spare coverage absorbs a saturated one, so it can hide a bottleneck and
never invent one, which agrees with the direction `LATER_GATE_REASONS` already declared.
*The unweighted mean errs either way and is bounded* — for Greenstone the pooled mean is
5.0 against a coverage-weighted 4.8, so here Gate 2 is the **more** demanding of the two;
for Burkham, whose two officers declare equal coverage, they agree exactly at 3.5.

`LATER_GATE_REASONS["V13"]` now carries the pooling to the editor too, so the sentence a
reviewer reads on the screen says a role can be over capacity on its own and still pass
here. The Gate 4.5 recheck body was not touched — B24 owns it, and the note works from the
Gate 2 side.

**Verdicts, measured before and after and byte-identical.** Gate 2: Burkham `160 of 432`
PASS, Greenstone `100 of 360` PASS. Gate 4.5: Burkham PASS at 120 approvals × the
coverage-weighted 3.5 = 420 against 432, **12 minutes**; Greenstone FAIL. Nothing flipped,
which is the required outcome for a change that edited no arithmetic.

**Tests: `tests/validator/test_v13_gate_2_aggregation.py`, six of them.** The one that
carries the item exhibits the divergence with *demand held equal* — same people, 20
approvals either way, Gate 2 PASS and Gate 4.5 FAIL — so the disagreement cannot be
attributed to the documented demand difference. The rest pin the choice: switching Gate 2
to coverage-weighting was applied experimentally and **two of the six fail**, with
Greenstone moving 100 → 96 and Burkham not moving at all. A stated choice is enforced by
nothing unless something reads it, which is the one respect in which the option B25
preferred is weaker than the shared helper it declined.

Suite: **1055 collected** (1049 + the six), **1045 passed, 10 failed, 0 errors** — and the
ten fail identically on the unmodified merge-base against the same database, so the delta is
zero. They are `test_approvals_api.py` and `test_governance.py`, none of them V13. The
prediction file records why the shared test database made that comparison necessary.

## B26 — every published Pack in the database is unreadable, and its status column says `live`

**`cross-cutting`** · Found 2026-09-08, attempting to republish Burkham after the
reviewer declaration. **This blocks the republish, blocks every new run for both
ventures, and blocks advancing the run currently sitting at Gate 4.**

Making `provenance` a required field on `HumanCapacity` was a schema change to the
**database**, and nothing treated it as one. The two on-disk Pack files were updated. The
twelve rows in `business_pack` were not:

```
burkham-wickmont  0.5.0  live        provenance: absent
greenstone        1.3.0  live        provenance: absent
(and ten superseded rows, all the same)
```

`parse_only` refuses both, so:

| call | result |
|---|---|
| `packs.live(conn, "burkham-wickmont")` | **raises** `PackStoreError` |
| `packs.live(conn, "greenstone")` | **raises** `PackStoreError` |
| `packs.get_version(conn, "burkham-wickmont", "0.5.0")` | **raises** |
| `provisioning.start_run` — *"against the venture's live Pack"* | **cannot start** |
| `provisioning.advance` on run `6a97fbe1` | **cannot advance** |
| `packs.store(...)` — reads `live()` first to compute its diff | **cannot republish** |

**The last row is the one that makes this a trap rather than a chore.** The publish-diff
control reads the previous Pack through `live()`, which parses it. So the schema change
disabled the only path that could fix the schema change — and it did so precisely in the
case the diff exists for, a change big enough to alter the shape of the file.

### The status column is the dishonest part

`status` still reads `live` on both rows. Nothing is flagged, nothing logged, no sweep
reports it. **A Pack that the parser says does not exist is recorded as the one in force**,
and the discrepancy surfaces only when somebody starts a run — the most expensive moment
to find out, and the one where the message will read as *this run failed* rather than
*this Pack was never migrated*.

### 1048 tests pass, and could not have caught it

Every test loads Packs from `packs/*.yaml` on disk. **Nothing in the suite reads a
published Pack back out of `business_pack` and parses it.** The capacity-provenance
prediction said *"making it required breaks Pack loading until every entry is filled"* and
scored that CORRECT — against the files. The same sentence was true of the rows and
nobody checked them, because the forcing function forces what is in git and the rows are
what is in force.

### The part that generalises, which is the finding

**A required field forces what is in git, not what is in force.**

Adding `provenance` with no default was designed as a forcing function, and it worked
exactly as designed on the two files in the repository — both Packs refused to load until
all four entries were filled, which is what the prediction called *"the difference between
a field that documents and a field that decorates."* That prediction was **scored CORRECT**,
and it was correct.

It was also, word for word, true of **ten published rows nobody looked at**. The same
sentence — *"making it required breaks Pack loading until every entry is filled"* —
described the database, and the database was never in anyone's view. **The forcing function
reached the source and stopped at the boundary of the repository**, and that boundary is
invisible from inside a diff.

Any schema tightening on a persisted document has this shape. The Pack is stored as text
and re-parsed on read, so a change that is a one-line schema edit in the code is a data
migration everywhere the text already exists — and unlike a column migration, **nothing
runs, nothing is stamped, and no version number moves.** Alembic knows about tables. It
does not know that `business_pack.yaml_source` is a document with a schema of its own.

### The check that does not exist

**Nothing reads a published Pack back out of `business_pack` and parses it.** Every one of
the 1048 tests loads from `packs/*.yaml` on disk. The suite verifies that the files satisfy
the schema and never asks whether the rows do.

**A round-trip test would have caught this on the provenance commit**: publish a Pack, read
the stored row back through `live()`, parse it, and assert it still loads. It fails the
moment a required field is added without republishing, and it names the right cause
because the failure arrives at the publish that broke it rather than at the run that
found it weeks later.

**Named here rather than built.** It is a small test and an easy one to write badly — a
version that publishes and re-reads within one transaction proves only that `store` and
`live` agree in the same process, which is not the property. The property is that rows
written by *an earlier build* still parse under this one, and that is a fixture problem
worth thinking about rather than a line to add today.

### Fixed 2026-09-08 — the minimum, and only the minimum

`store()` now reads the previous version's **raw `yaml_source`** through a small
`_previous_source` helper instead of through `live()`/`draft()`. The diff is textual —
`_changed_lines` compares two strings and never needed the previous Pack parsed.

**Nothing about what is being written is weaker.** `parse_only` still refuses any Pack that
does not satisfy the current schema, and it runs before the diff. What changed is only that
**the version being replaced is no longer required to satisfy a schema written after it was
stored** — which was never a coherent requirement, and which made the control that exists
to reveal a change refuse to run precisely when the change was largest.

`live()` and `get_version()` are untouched and still parse. That half is B27.

Regression test: `test_a_publish_can_replace_a_row_the_current_schema_cannot_parse`.
Confirmed to fail against the pre-fix code with B26's own error, and to pass after.

### Closed 2026-09-09 by P-07 — the round trip now exists, and it is not a tautology

`tests/contract/test_pack_round_trip.py`. **The suite now reads a published Pack back out
of `business_pack` and parses it**, which nothing did across all 1049 tests.

The check is one helper, `read_back_and_parse`, and it is deliberately pointed at *two*
kinds of row rather than one:

| the row | what the helper must do |
|---|---|
| published by this build through `store()` | **parse** |
| written before `provenance` existed | **raise** |

**The second is the test, not a scenario.** B26 named the way this gets written badly —
*"a version that publishes and re-reads within one transaction proves only that `store`
and `live` agree in the same process, which is not the property"* — and that version
would have passed on the provenance commit exactly as loudly as it passes now. So the
failing direction is asserted too, in CI, permanently: if someone loosens `parse_only` to
"fix" an old row,
`test_the_round_trip_fails_against_a_row_from_an_earlier_build` goes red and says why.

**The earlier-build row is constructed, not transcribed.** `packs/greenstone.yaml` with
the `provenance` keys removed — which is what the revision before the tightening would
have written, and differs from today's file in nothing else. A hand-written old Pack could
drift into something the earlier revision would *also* have refused, and the test would
then be demonstrating the wrong failure. The construction is checked rather than trusted:
the diagnosis must name `human_capacity[].provenance` **and nothing else**.

It is inserted with a raw `INSERT`, not through `store()`. `store()` is this build and
this build refuses the document — which is correct, and is exactly why the twelve stale
rows could only have been written by a build that did not.

**Demonstrated before it was committed.** The round-trip assertion, unwrapped, pointed at
the earlier-build row:

```
FAILED test_ROUNDTRIP_ASSERTION_AGAINST_AN_EARLIER_BUILD_ROW
broker.packs.PackPredatesTighteningError: greenstone@1.3.0 is a schema-v3 Business Pack
stored under an EARLIER REVISION of v3 ...
```

and the same row against the pre-change `broker/packs.py`, which is B27 verbatim:

```
broker.packs.PackStoreError: not a schema-v3 Business Pack: 2 validation errors for
BusinessPack
```

**What still is not covered, said plainly.** This asserts the round trip for a row this
suite writes. **It does not look at the twelve rows in the real database** — B28 is still
open, and `greenstone@1.3.0` in the development database is still `status = 'live'` and
still unreadable. The round trip is the forcing function for the *next* tightening; it is
not a migration for the last one.

## B27 — an unparseable old row is reported as "not a schema-v3 Business Pack", and it is schema-v3

**`cross-cutting`** · Found 2026-09-08, as the second half of B26. **The fix for B26
unblocked publishing and deliberately left this standing.**

`live()` and `get_version()` still call `parse_only` on the stored source, and when a row
was written under an earlier schema the caller gets:

```
PackStoreError: not a schema-v3 Business Pack: 2 validation errors for BusinessPack
```

The row **is** schema-v3. Its `schema_version` column says `3`, it was published as v3, and
it was valid v3 on the day it was written. What is actually true is narrower and more
useful: *stored under an earlier revision of the v3 schema, before `provenance` was
required.*

### This is B23's class, arriving in an exception — the fifth instance

B23 collects **names that assert more than the code does**: `max_daily_approvals` reads as
a limit and limits nothing, and the other three the same way. **This is the same defect in
a different surface.** The message asserts something false *about the data* — and unlike a
misleading field name, which sits still and can be read sceptically, **an exception message
is read at the exact moment the reader has least context and most urgency**, and it points
them at the file rather than at the migration.

It is worse than silence in the way entry 22's class is worse: it does not fail to explain,
**it explains incorrectly and confidently.** A reader who trusts it goes and inspects a Pack
that is fine.

### What would fix it — not built

A read that meets a row it cannot parse should say **which** revision it was stored under
and **what** the current one requires, and should distinguish *this document is malformed*
from *this document predates a tightening*. The `schema_version` column is already there and
already carries the coarse half of the answer; what is missing is a finer marker, and
deciding what that marker is is a design question rather than a message rewrite.

**Left standing deliberately.** Changing it changes what a run does when it meets an old
Pack, which is a larger decision than unblocking a publish, and B26 was the blocking half.

### Closed 2026-09-09 by P-07 — the finer marker is a ledger of tightenings

The design question this entry left open was *what the finer marker is*. **It is not a
revision number.** A number would have to be stamped by something, nothing stamps one, and
inventing one would put a name in the message asserting more than the code knows — which
is the class of defect this entry belongs to. Adding a column would say when a row was
written and still not say what the schema required that day.

`broker.packs.V3_TIGHTENINGS` instead: an ordered ledger of **the occasions on which v3
began requiring something v3 had not required before.** Each entry carries the field, the
date it landed, the blocking entry that argued for it, and one sentence of what this build
requires — four things a reader can go and check, and none of them a number nobody writes.
A revision is identified by what it added.

**The distinction is a type, not a turn of phrase.** `PackPredatesTighteningError`
subclasses `PackStoreError`, so nothing that catches the base narrows, and a caller
choosing between *halt this run* and *route somebody to a migration* no longer has to grep
an error string. `.predates` carries the machine-readable half of what the message says in
words.

Before, for `greenstone@1.3.0`:

```
PackStoreError: not a schema-v3 Business Pack: 2 validation errors for BusinessPack
```

After:

```
PackPredatesTighteningError: greenstone@1.3.0 is a schema-v3 Business Pack stored under an
EARLIER REVISION of v3. It is not malformed. `schema_version` says 3 and that is correct -
every field v3 required when this was written is present. What the column cannot say is
WHICH revision of v3, and this one was stored before this tightening:
  * `human_capacity[].provenance` - required since 2026-09-08 (blocking-log B21), absent
    from 2 entries here. This build requires that every `human_capacity` entry carries a
    `provenance` block: `basis` (declared / inherited / measured), `established_by` naming
    a person, a `detail` sentence, and - when the basis is not `declared` - a `source`
    naming what was copied or observed.
This build reads v3 as of 2026-09-08.
Do not go and inspect the Pack source; there is nothing wrong with it. This is a stored row
that was never migrated when the schema tightened. Republish the venture's Pack at a new
version - see docs/blocking.md B26 and B28.
```

**The other direction was the easy half to get wrong.** Reporting a broken document as
*merely old* would be this entry mirrored: the same false confidence, pointing the reader
at a migration that will not help. So `_predated_tightenings` returns nothing unless
**every** error is a `missing` at a ledgered path. One error no tightening explains and the
document is malformed whatever else is true of it — and it keeps the original sentence,
which for a genuinely malformed document was always the true one.
`test_a_genuinely_malformed_document_is_still_called_malformed` pins that half, and
`tests/provisioning/test_pack_store.py` still asserts the old wording for `venture_id:
nope`, unchanged and correct.

**Behaviour is otherwise unchanged, deliberately.** `live()` and `get_version()` still
raise on a row they cannot parse. This entry asked for an honest diagnosis, not for a read
that returns a Pack it could not parse — and B28 is the decision about the actual rows,
still Ivan's.

**The forcing function for the next tightening.** Appending to `V3_TIGHTENINGS` is now the
second half of adding a required field to `generators/pack.py`; without the entry, an old
row goes straight back to being reported as malformed.
`test_every_required_field_added_since_v3_has_a_ledger_entry` catches a rename that leaves
a ledger entry pointing at nothing. It cannot catch a tightening whose author never
appended at all — nothing inside one build can, which is the same boundary B26 found, and
it is written down here rather than papered over.

**Corrected 2026-09-09 by P-07, after B31.** Two sentences above were wrong within three
hours of being written, and they are corrected here rather than edited away.

**The ledger to append to is `V3_SCHEMA_CHANGES`, not `V3_TIGHTENINGS`.** The latter still
exists and still means exactly what it says — the tightenings — but it is now derived, and
appending to it is no longer the whole of the second half.

**And "catches a rename that leaves a ledger entry pointing at nothing" claimed more than
the code did.** The test walked `V3_TIGHTENINGS` checking that each named a field the model
still has. That catches a *tightening's* field being renamed out from under it. It could not
catch what actually happened — a rename arriving with **no ledger entry at all**, in a model
that had no way to express one — because a ledger nobody appended to is exactly what nothing
inside one build can check, which the paragraph above says correctly one sentence later and
then contradicts. **The claim was read off the test's name.** Caveat 14, in the closure note
of the item about names asserting more than the code does.

## B28 — Greenstone's live Pack is in the state B26 describes, and nothing has been done about it

**`greenstone`** · Found 2026-09-08, immediately after fixing B26 for Burkham.

`greenstone@1.3.0` is `status = 'live'` and was published before `provenance` existed, so
`parse_only` refuses it. **The next Greenstone run cannot start**: `start_run` reads the
venture's live Pack, and that read raises.

**And whoever hits it meets B27's message**, which will tell them the Pack is *not a
schema-v3 Business Pack*. It is schema-v3, and `packs/greenstone.yaml` on disk is fine.
The message sends the reader to inspect a file that has nothing wrong with it while the
actual fault is a row nobody migrated.

Burkham was in exactly this state and is out of it because it was republished as 0.6.0.
Greenstone was not, and this item exists so that is a recorded decision rather than an
oversight that surfaces at a run.

### Correction: the reason first given for leaving it was wrong

It was reported to Ivan that republishing *"voids Gate 10 signatures taken against 1.3.0's
artifacts, so the fix is currently worse than the fault."* **That is not true here.** It
is `store()`'s general warning, quoted without checking whether the situation it warns
about exists. Checked afterwards:

- **`signoff_record` holds zero rows.** No signature exists for any venture, at any gate.
- **No Greenstone run has ever used 1.3.0.** Every run is against 1.0.0 or 1.2.0.
- **No Greenstone run has ever passed Gate 4.** The highest gate any of them recorded is
  4; `provisioning_gate_result` has nothing above it.

So there is nothing to void. **The real reason it was not fixed is that it was not asked
for and was outside the request** — a fine reason to leave something, and not the reason
that was given. Recorded because a wrong reason in the record is worse than no reason: the
next reader would have weighed a risk that does not exist and left it alone again.

### What retires it

**A republish of `packs/greenstone.yaml` as 1.4.0, and nothing else.** The diff against the
live row is **two hunks, eighteen lines, pure addition** — the two `provenance` blocks the
capacity-provenance change added and never published. No other drift. No value changes, no
rule changes, no re-signing implied, because nothing is signed.

The check that made that statement safe to write is the publish-diff control doing its
job: a positional count plus a real text diff, read before publishing rather than after.

**Ivan's call, deliberately, rather than discovered mid-run.** It is being left open only
so the decision is made rather than inherited.

## B29 — Gate 4 computes the role the reviewer acted as, then throws it away

**`cross-cutting`** · Found 2026-09-08, answering *"which role is the signature attesting
under"* before a Gate 4 review. **A one-line loss, not a schema question** — which is what
separates it from B22.

`authorize()` does not return `None`. Its docstring says so:

> *"Check role strength AND venture scope. **Returns the role acted as.**"*

Two callers, two fates:

| caller | what it does with the return |
|---|---|
| `humans.sign_off` | `role_signed_as = authorize(...)` → written to `signoff_record.role_signed_as` |
| `provisioning.record_human_review` | **discards it** |

`record_human_review` writes `provisioning_gate_result` with verdict `passed`, a reason
reading `reviewed by {display_name}: {note}`, and evidence `{human_id, note}`. **The role
is computed one line earlier and never referenced.**

### Why this is not the same item as B22

B22 is about a **link that does not exist** — no join between a Pack's named reviewers and
`office_human`, in either direction. Building it is a schema decision with a migration
behind it.

This is about a value that **is already computed, already correct, and already has a home
on a sibling table.** Nothing needs designing. The column exists on `signoff_record`; the
concept is named; the function that produces it is called on the line above.

### What it costs

A Gate 4 review records *who* and *what they said*, and not *what authority they had when
they said it*. Reconstructing that later means reading `office_human_role` **as it is now**
and assuming it has not changed — and roles are grantable and revocable, so the assumption
is exactly the thing an audit record exists to avoid making.

It matters more now than it did last week. Burkham's Pack names Ivan Green as
`compliance_officer`; his account holds `ivan` with global scope; the review authorises
against `venture_operator`. **Three role names in three places for one act**, and the
record keeps none of them. A reader six months from now cannot tell whether the reviewer
signed as the venture's declared compliance officer or as an administrator who could have
signed for any venture — and those are different attestations.

### What retires it

Carry the return value. `provisioning_gate_result.evidence` is `jsonb` and already carries
`human_id` and `note`, so `role_acted_as` can join them **without a migration**.

**Whether Gate 4 should also write a `signoff_record` row is the larger question and is
deliberately not this item.** Gate 4 is a review, Gate 10 is a signature, and collapsing
them because one field is missing would be the wrong fix in the same shape as the
utilisation factor: the easiest change that makes the symptom go away.

## B30 — certification has two producers and neither exists

**`cross-cutting`** · Found 2026-09-09 by P-00, opening the Gate 4.5 parallel build.
**This is what actually blocks run `def65e4f` at Gate 4.5, and it is not what the brief for
that build said it was.**

Gate 4.5 refuses Burkham on V24: eight seats across five positions, zero certified
candidates. The assumed cause was held-out authoring — SimForge cannot grade a curriculum,
so nobody gets certified. **That is one of two causes and it is the smaller one.**

### Unit A — nothing writes a SimForge verdict into a certification row

`certification.record_result` has exactly one non-test caller, `broker/bootstrap_phase0.py`,
and `attested_by` accepts only `'simforge'` or `'bootstrap'`. **The string
`attested_by="simforge"` appears nowhere in this codebase.**
`SimForgeClient.gate_result(run_ref)` exists, fetches a verdict, and is called by nothing
outside its own test.

**So a perfect held-out authoring pipeline would produce a verdict nothing ingests.**

### Unit B — nothing submits a department curriculum at all

```
unit_targets_match:   A → office_agent_id AND module_id NOT NULL
                      B → department NOT NULL
```

A submission is one or the other, keyed on `module_id`. **Gate 8 submits one curriculum per
module, so it produces unit-A submissions exclusively** — `curriculum_submission` holds ten
rows, ten with `module_id`, zero with `department`.

**And unit B gates appointment.** `generators/appointment.py` refuses any candidate whose
forges lack a certified unit-B row for the position's department. The only unit-B rows in
existence are three bootstrap rows, all `department='engineering'`. **Burkham declares
`administration`, `banking` and `operations`, and holds none.**

**Every Burkham candidate is refused `missing_unit_b` even after the unit-A path is built.**

### Why this was invisible

Nothing reports it. The appointment generator folds both refusals into one shortfall count,
and `produced_not_yet_certified` — which B23 already flags as a name asserting more than the
code does — reads the same whether a candidate failed on unit A, on unit B, or was never
examined. **A run stops at Gate 4.5 saying "zero certified candidates", which is true and
names neither cause.**

### What retires it

**P-03** builds the unit-A ingester (the sweep, not an inbound route — see the reasoning in
`overdue_submissions`' own docstring). **P-04** builds the unit-B submitter, and its first
task is to establish whether SimForge holds domain certifications for Burkham's three
departments at all.

**Neither is blocked by held-out authoring.** Both can be exercised against a verdict for any
module with no never-do list, which is why this run builds the two last miles in parallel
with the first rather than behind it.

**A useful side effect for P-11 to keep:** report `missing_unit_b` refusals separately from
unit-A refusals. They are different failures with different owners, and collapsing them is
how this stayed hidden.

## B31 — a renamed Pack field reads as a malformed document, not an older one

**`theoffice`** · Found 2026-09-09 by the coordinator, merging P-07 and P-08 in the same
wave. **Neither package could have found it: each is correct alone, and the gap is between
them.**

P-07 closed B27 by giving `broker/packs.py` a ledger of **schema tightenings** — the occasions
on which v3 began requiring something v3 had not required before — so a row stored under an
earlier revision raises `PackPredatesTighteningError` and says *which* tightening it predates,
rather than the false *"not a schema-v3 Business Pack"*.

Its guard is deliberate and its docstring says why:

> *"Only an absent field can be explained by 'this predates the field'. A wrong type, a
> refused extra key or a failed validator is a document that disagrees with the schema, not
> one that is older than it."*

**That is right for every tightening except a rename.** P-08 renamed
`max_daily_approvals` to `advisory_daily_approval_ceiling`, and a rename produces **two** error
kinds per entry:

```
missing          human_capacity.0.advisory_daily_approval_ceiling
extra_forbidden  human_capacity.0.max_daily_approvals
```

The `extra_forbidden` disqualifies the whole diagnosis, so the message falls back to the
generic sentence — **the exact sentence B27 exists to eliminate**, on the exact class of row it
was built for.

### Measured, on a row that matters

`provisioning_run def65e4f` is halted at Gate 4.5 and pinned to pack `0.6.0`.
`packs.get_version(conn, "burkham-wickmont", "0.6.0")` now raises the generic
`PackStoreError`. **The run cannot read its own Pack version**, and the message points a reader
at a document that is fine.

The run was already `blocked` on V24 with zero certified candidates, so nothing was advancing
and no work was lost. **What was lost is the honest message**, three hours after it was built.

### Why it is worth an item rather than a quick fix

**The obvious fix is to add the rename to `V3_TIGHTENINGS`, and it does not work.** That was
tried and reverted: the entry is true, and it never fires, because the `extra_forbidden` guard
rejects the diagnosis before the ledger is consulted. A ledger entry that can never fire is
decoration — B23's class, in the machinery built to fix B27.

**The real fix is that `SchemaTightening` does not model a rename.** A rename is one change
that presents as two errors, and the pair has to be recognised together: *the new name is
missing AND the old name is present*. That is a small extension to a model P-07 reasoned about
carefully, and it belongs to whoever owns that model rather than to a coordinator patching
around it mid-merge.

**Not built here, deliberately.** The coordinator already broke a package's tests today by
acting on its own judgement inside someone else's work.

### What retires it

`SchemaTightening` gains a `renamed_from`, and `_predated_tightenings` treats a
`missing(new) + extra_forbidden(old)` pair at the same path as one explained change rather than
two disqualifying errors. Then `get_version` on `0.6.0` says what is actually true: **this row
predates the rename, and the document it names is fine.**

### Closed 2026-09-09 by P-07 — a sibling type, not a flag, and the pair is matched per entry

**`renamed_from` on `SchemaTightening` was not taken, and the reason is this item's own
finding.** A tightening is v3 asking for *more*; a rename is v3 asking for the *same value*
under another name. A `renamed_from` field on a class called `SchemaTightening` would make the
class name false for half its rows — **a name asserting more than the code does, which is B23's
class, appearing inside the machinery built to fix B27.** That is precisely the trap this item
warns about, and repeating it in the fix for it would have been the joke writing itself.

So `SchemaRename` is a sibling of `SchemaTightening`, and `SchemaChange` is the union. The
ledger is `V3_SCHEMA_CHANGES`. **`V3_TIGHTENINGS` keeps its old spelling and its old meaning** —
it is now derived, holding the tightenings and nothing else — because a public name that
silently grows a wider meaning is how the callers of one become the callers of the other.
`V3_RENAMES` is its counterpart.

### The pair is matched on the full location, list index included

Not on the field path. Five ways a document can carry a refused key without being an
unmigrated row, and only the first is the one anybody pictures:

| the document | verdict | why |
|---|---|---|
| a key the ledger has never heard of | **malformed** | the guard, unchanged |
| a real rename **plus** an unknown key | **malformed** | one unexplained error is enough; a diagnosis is all-or-nothing |
| **both** names present in one entry | **malformed** | no `missing` half — two migrations that half-ran, or a hand edit |
| **neither** name present | **malformed** | the field had no default under either revision; the value was never there |
| old name at entry 0, neither name at entry 1 | **malformed** | counted across the document the halves look like a pair; per entry, neither entry is unmigrated |
| old name at entry 0, entry 1 already migrated | **predates** | every failing entry fails as a complete pair — a half-fixed row is still an old row |

The fifth row is why the index is in the match. A path-only rule calls it *old* and sends the
reader to a migration that will not help, which is B27's false confidence pointing the other
way.

### Measured, on the row this item was found on

`packs.get_version(conn, "burkham-wickmont", "0.6.0")`, against the real row in the development
database, left exactly as it was because it is the evidence:

```
PackPredatesTighteningError: burkham-wickmont@0.6.0 is a schema-v3 Business Pack stored under
an EARLIER REVISION of v3. It is not malformed. `schema_version` says 3 and that is correct -
every field v3 required when this was written is present, under the name it had then. What the
column cannot say is WHICH revision of v3, and this one was stored before this change:
  * `human_capacity[].advisory_daily_approval_ceiling` - renamed from `max_daily_approvals` on
    2026-09-09 (blocking-log B23); 2 entries here still carry the old name. This build requires
    that every `human_capacity` entry declares its daily approval figure as
    `advisory_daily_approval_ceiling`. The value did not change and neither did its effect -
    nothing enforces it, and nothing ever did. What could not persist was a name that read as
    a cap.
This build reads v3 as of 2026-09-09.
Do not go and inspect the Pack source; there is nothing wrong with it. This is a stored row
that was never migrated when the schema changed. Republish the venture's Pack at a new version
- see docs/blocking.md B26, B28 and B31.
```

### The reverted attempt, reproduced rather than taken on trust

This item says the ledger entry alone does nothing. That was re-run rather than believed:
the `SchemaRename` entry left in place and **only** the guard's first line restored to its
pre-B31 form.

**Seven tests fail, and `test_the_ledger_entry_is_not_decoration` is one of them.** The other
**nine pass** — every one of the disqualifying cases above. That is the measurement that
matters in both directions at once: it confirms the entry is unreachable without the pair
rule, *and* it shows the guard's teeth are not what changed, because the cases that test them
never moved.

### What this does NOT do

**Nothing is republished and no Pack is edited.** `burkham-wickmont@0.6.0` is still stale and
`provisioning_run def65e4f` still cannot generate from it — it was `blocked` on V24 with zero
certified candidates before this and it is blocked on V24 now. **What is fixed is the message,
not the row.** B28's decision — which rows get migrated, and by whom — is still open and still
Ivan's.

## B32 — GAP-5: no `DeptCert` has ever existed, and SimForge holds a stale department copy

**`cross-cutting`** · Answered 2026-09-09 by the coordinator, read-only. **This was P-04's
first task and Ivan asked for it the day it was known rather than at P-11.**

**CORRECTED TWICE, THE SAME DAY. Both corrections were to the same kind of error: a true fact
with a wrong consequence hung on it.** The retracted claims are quoted rather than deleted.
This item is the least reliable thing in this file, and the third version says so at the top
rather than presenting itself as settled.

### What has been true throughout, and is the actual finding

**`DeptCert` holds zero rows.** Not zero for Burkham's departments — **zero for any department,
including Engineering.** No domain certification has ever existed in SimForge.

**The Office's three `certified` unit-B rows are all `engineering`, all
`attested_by='bootstrap'`** — *"a grant issued against no scenario run"* — **and correspond to
nothing in SimForge.** The one department carrying unit-B certification in The Office is the
one Burkham does not use.

**Unit B is therefore blocked harder than B30 said.** B30 recorded that unit B has no
submitter, with the implicit assumption that building one would let certification be earned.
**There is nothing on the other side to earn it from.**

### Correction 1 — the department mapping was never missing

The first version said `administration` and `banking` *"have no counterpart of any spelling"*
in SimForge, and put two questions to Ivan. He ruled **banking → Finance, administration →
Executive**. **No mapping was needed and that ruling must not be applied.**

The Village's twelve, read live from `broker.departments`:

```
Administration, AI_Data, Banking, Engineering, Executive, Infrastructure,
Marketing, Media_Production, Music_Production, Operations, Publishing, Research
```

`Administration`, `Banking` and `Operations` are all real Village departments. **Burkham's
three names are correct exactly as the Pack has them**, and V29/V30 validate against this live
list and pass.

**The error:** the coordinator compared The Office's departments against SimForge's
`Department` table and treated that table as the standard. The Office reads the list **live
from the Village**, and `generators/pack.py` says why, describing this exact failure —
*"a copy cannot know it has gone stale."* **The field is called `villageKey` and the name was
taken at its word instead of asking what wrote it.** Caveat 14.

### Correction 2 — the submission does not fail; the certification cannot be issued

The second version said:

> *"a unit-B submission for `Administration` will find no such department in SimForge — not
> because the mapping is wrong, but because SimForge's roster predates a Village rebuild."*

**Also wrong, and wrong in the same shape as the first: a true fact with the consequence hung
one step off.** Measured:

| column | type | consequence |
|---|---|---|
| `OperationRun.departmentId` | `String, nullable=True`, **no FK** | **a unit-B run opens fine** for any department string |
| `OperationCert.departmentId` | `String, nullable=True`, **no FK** | same |
| **`DeptCert.departmentId`** | `String, ForeignKey("Department.id")` | **a certification cannot be issued** for a department SimForge has no row for |

**So the stale roster does not block the submission. It blocks the certification at the end of
it.** Those are different failures at different points, and P-04 will be built against
whichever one this item names — which is why getting it wrong mattered enough to correct
rather than quietly sharpen.

### What this means for P-04, stated once and carefully

**P-04 can submit.** A unit-B run for `Administration`, `Banking` or `Operations` will open,
because `departmentId` is a free string on the run.

**P-04 cannot be satisfied.** No `DeptCert` exists for anything, and one cannot be created for
`Administration` or `Banking` while SimForge's `Department` table lacks those rows — `DeptCert`
has a real foreign key to it.

**Build it anyway.** A submitter that correctly reports three uncertified departments is a true
statement and better than B30's silence. **But it must be built knowing it cannot succeed
yet**, rather than discovering that at P-11 after four packages have merged behind it.

### What retires it

1. **SimForge stops holding a department copy**, or refreshes it from the Village and can say
   when it last did. Nine of its thirteen `villageKey` values are not current Village
   departments; seven current ones are absent. **The Office already made exactly this fix** —
   it deleted its copy and reads live, because a copy cannot know it has gone stale.
2. **A `DeptCert` is actually earned for a Burkham department.** Nothing has ever produced one,
   so that path is unexercised in exactly the way the Gate 8 handover was until P-01 ran it.

**Neither is a decision for Ivan.** The two questions this item originally asked him are
withdrawn.

### A note on this item's reliability

**Two retractions, both of the same class: an upstream fact established correctly, then a
downstream consequence asserted without following the path to where it bites.** The facts held
each time. The consequences did not.

**Anything else this item claims should be checked before it is acted on.** If a package's work
had this record it would have been handed back; the coordinator's own gets the same standard
written down instead.

