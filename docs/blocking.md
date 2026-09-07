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
