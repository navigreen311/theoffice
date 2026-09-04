# Decision record — The Office

Decisions that are not about one module and would otherwise live in a commit
message. Appended, never rewritten; a reversal gets a new entry that says so.

CapitalForge keeps one of these per module in `docs/decisions/`. The Office has
fewer and broader ones, so they share a file until that stops being true.

---

## 1. #16 stays unmerged until there is a Forge to ask

**Decided 2026-09-03.**

`ai-feature/pack-module-conformance` is green on six of seven jobs and red on
Smoke, and the cause is its own rules working. V32 resolves a Pack's modules
against a Forge's `_modules` manifest and V11 resolves the modules its curriculum
teaches; the smoke environment has no adapter to ask, so both report NOT_RUN,
Gate 2 blocks, and the gate-ladder checks fail against a run that stopped at
gate 2.

**Decision.** Leave #16 unmerged. Do not build a stub Forge for the smoke
environment.

A stub Forge is the same work as the real one — a dispatch map, a `_modules`
endpoint, the identity headers — and building it twice means the smoke
environment tests a fixture while the bridge stays untested. The stub Village was
worth it because the Village is a separate system The Office only reads from; a
Forge adapter is the thing the bridge exists to reach.

**What reverses it.** A CapitalForge Office adapter. That is the same item that
unblocks the Burkham Pack, `suitability_check`'s Pack declaration, and every
module registry row — so it is one build, not four.

**Rejected — merging #16 with Smoke red.** The repository has no branch
protection, so it is possible. The rules in #16 exist to stop a Pack being
validated against a Forge nobody asked, and merging them past a job saying
exactly that would be the first thing a reader cites when arguing the rule is
optional.

---

### Corrected 2026-09-03 — the blocker was never "no adapter"

**The CapitalForge adapter now exists, and #16 is still blocked.** Anyone reading
the entry above will expect the opposite, so the reasoning is corrected here rather
than left to mislead.

What the entry said reverses it: *"A CapitalForge Office adapter. That is the same
item that unblocks the Burkham Pack…"* That was wrong by one word. The blocker was
never **no adapter** — it was **no adapter CI can reach**.

The adapter is real, serves `_modules`, dispatches nine modules and has carried
brokered calls end to end. It runs on `127.0.0.1:4000` from a dev checkout. The
Smoke job runs on a GitHub runner with no such host, so V32 and V11 still report
NOT_RUN there, Gate 2 still blocks, and the gate-ladder checks still fail against a
run that stopped at gate 2. **Nothing about the Smoke failure has changed.**

The entry's other claim did hold: one build unblocked Gate 0, the Pack's module
reconciliation and every registry row. It unblocked everything except the thing this
entry is about.

**The decision stands, for its original reason.** #16 stays unmerged. A stub Forge
is still the same work as the real one, and the real one existing does not make a
stub in CI any less of a fixture.

### The three options, and what each actually costs

**Merge #16 with Smoke red.** Still rejected, unchanged.

**Merge #16 first, then the branch stacked on it.** The same rejection, one step
later.

**Wait until the adapter has somewhere CI can reach.** This reads as waiting and it
is not — **it is unscoped work with no owner**, and calling it waiting is how it
stays unscoped. Reaching the adapter from CI means at minimum a deployed
CapitalForge instance or a container the Smoke job can start, a reachable
`base_url` in the smoke environment's `forge_registry`, and a credential CI can
resolve — plus whatever seeded tenant data the modules need in order to answer.
None of that is estimated and none of it is assigned.

**So it is deferred indefinitely with the reason attached**, not pending. It becomes
real work the day somebody wants it, and it needs an estimate before it is
scheduled.

**What that leaves #16 as:** a branch whose rules are correct, whose failure is
those rules working, and which cannot be green in CI until the bridge has an address
in CI. It is not close to merging and should not be described as close.


---

## 2. `/agents/<id>` renders identifiers where labels belong — queued, not dropped

**Decided 2026-09-03.**

The Agents list was rendering the normalized `department` where the Village's
`label` belongs, so `ai_data`, `media_production` and `music_production` appeared
as headings. Fixed on the list, the filters, the roster-sync picker and the
empty-departments list.

`/agents/<id>` has the same defect and is not fixed. It renders
`identity.department` and `cert.department`, and neither payload carries a label —
so it is API plumbing on a different endpoint rather than a word swap. The
identifier smoke check does not scan that route, so nothing reports it.

**Decision.** Queued, not dropped. It is the same defect, it is still there, and
`broker/departments` states the distinction the page is on the wrong side of:
`department` is what a row is grouped and filtered by, `label` is the word an
operator reads.

**Recorded because a fix that stops at the first surface reads as a fix.** The
Agents list is right and the agent detail page is not, and the difference is
invisible to anyone who only opened the list.

**Deferred 2026-09-03**, with nine CapitalForge items - see
`docs/decisions/deferred.md` in that repository, which explains why the ten were
left as a group and what would change each answer. Deferred is not dropped: it is
written down so it is not raised again as new.

---

## 3. #16 merged with a check that has never run in CI

**Decided 2026-09-03**, reversing entry 1 the same day it was corrected. Recorded as
an entry rather than a note in the pull request, because it is a precedent: it is
the first time this repository has merged a control that is green nowhere.

### What is being accepted

**V11 and V32 have never run in CI.**

They pass locally against a dev-checkout Forge on `127.0.0.1:4000`. CI has no such
host, so they report NOT_RUN rather than fail — and the Smoke job says so in those
words:

```
run b786295c stopped at gate 2 (blocked)
  rule(s) ['V11', 'V32'] did not run. NOT_RUN is not a pass - this Pack has not
  been validated.
FAIL unevaluable rules with no gate named: ['V11', 'V32']
```

**And the smoke test says the blocker is not the manuals.** On #19, which authored
nine operating instructions, the same job prints:

```
==> V11 refuses a Pack whose instructions teach nothing
  instructions are real and V11 says NOT_RUN
```

The instructions exist and are real, and V11 still cannot answer — because what it
resolves them against is a Forge address CI does not have. Nothing about authoring
changes this, which is worth having in the entry rather than discovering twice.

**The conformance guards are on `main` and unverified there.** Six of seven jobs are
green; the seventh is these two rules correctly reporting that they could not run.

This is not a caveat to read past. The rule that resolves a Pack against a Forge's
own dispatch map, and the rule that resolves its curriculum against the same, are
now merged on the strength of a laptop.

### Why

**A check that structurally cannot run in the environment it runs in does not gate
anything.** It is not protecting `main` — it is reporting its own absence, every
time, to nobody who can act on it. Holding twenty-three commits behind it proves
nothing about those commits and nothing about the rules.

The alternative was to keep everything downstream unmerged until the environment
changed, and the environment is not scheduled to change. That is the shape entry 1
was in, and it was mistaken for progress.

### What retires this entry

**Corrected 2026-09-04. It said "a Forge address CI can reach." That is wrong, and
wrong in a specific way worth naming.**

**TWO Forge addresses CI can reach, and one of them exists only as a placeholder.**

The Burkham Pack binds two Forges at `criticality: hard`, and V32 resolves every
module of every binding. CapitalForge now answers — eleven modules, all bound, all
called. **SimForge cannot be asked at all:**

| | |
|---|---|
| `forge_registry.base_url` | `https://example.invalid` — a deliberate placeholder |
| `forge_tenant_credential.credential_ref` | `env://SIMFORGE_TOKEN` |
| `SIMFORGE_TOKEN` in `.env` | **absent** — not unset in a shell, missing from the file |

So V32 reports NOT_RUN with `simforge: tenant credential unavailable`, and it would
report that with CapitalForge fully deployed and reachable. **Fixing the
CapitalForge half does not turn this check green.** SimForge has no adapter, and
building one is a second piece of unscoped work that nobody has costed either.

Concretely, what retires this: a reachable CapitalForge **and** a reachable SimForge
— a deployed instance or a container the Smoke job starts, a `base_url` that is not
`example.invalid`, a credential CI can resolve, and enough seeded data for the
modules to answer. Entry 1 records the first as **unscoped work with no owner**; the
second is not even that, because it has not been described until now.

### The same error, twice, on the same check

**This is the second time this check has had its blocker described one layer too
shallow.**

Entry 1 said the blocker was *no adapter*. It was *no adapter CI can reach* — the
adapter arrived and nothing moved.

This entry said the blocker was *a Forge address CI can reach*. It is *two Forge
addresses* — CapitalForge arrived, was reachable locally, and V32 still cannot run.

Both errors have the same shape: **a real blocker was identified, fixed, and the
check stayed red, because what was named was one layer inside what was true.** Both
were found the same way — by fixing the named thing and watching nothing happen.

Worth stating as a pattern rather than as two mistakes: when a check reports
NOT_RUN, the named cause is a hypothesis until the named cause is removed. V32 has
now falsified two.

**A third reading, offered as a hypothesis and labelled as one.** V32's resolution
path was read on 2026-09-04 rather than inferred: it needs a `forge_registry` row, a
`forge_tenant_credential` row, a credential that resolves, and a reachable
`{base_url}/_modules` answering with a parseable list. It touches no certification,
no instruction, no scenario pack and no grant - those are V11's and V22's business.
So two reachable addresses should clear it, with one condition that is the same
check working rather than a new layer: SimForge's manifest must contain
`run_scenario_pack` and `gate_result` under those exact spellings, because the
adapter's dispatch keys are the spelling of record. A different spelling turns V32
from NOT_RUN into FAIL.

**CLEARING V32 IS NOT CLEARING GATE 2, and the two must not be read as one.** Gate 2
requires no failures and no unrun rules other than V24. As of 2026-09-04, with
CapitalForge reachable locally, V29 and V30 are also NOT_RUN because the Village is
not running - and **whether CI's stub Village satisfies them has not been tested.**
That is a separate unknown from the Forge addresses, it has not been checked, and
nobody should read "V32 clears" as "Gate 2 clears" on the strength of this entry.

### What this does not license

**It is not a precedent for merging a failing check.** V11 and V32 do not fail in
CI; they decline to answer, and they decline for a reason that is a fact about the
runner rather than about the code. A check that *fails* in CI is a check that ran.

The distinction is the one these rules exist to enforce, and it would be a poor
irony to lose it here: **NOT_RUN is not a pass**, and merging past NOT_RUN is a
decision that has to be written down every time. This is that writing.

---

## 4. `lender_match` and `build_packet` come off the Pack — they do not exist

**Decided 2026-09-04.**

Both were on Burkham's `modules_expected`, and both were on V11's and V32's failure
lists as unauthored modules. **They are not unauthored. They are absent.**

### What was searched

No route, no service, no handler, nothing under any spelling: `lender_match`,
`lenderMatch`, `matchLender`, `build_packet`, `buildPacket`, `fundingPacket`,
`packetBuild` — zero matches across the whole CapitalForge backend. The nearest
things are card-**issuer** optimizers (`stacking-optimizer.service.ts`,
`issuer-rules-engine.ts`), which are a different act: CapitalForge matches clients
to card issuers, not to lenders, and there is no packet builder anywhere.

They held no `forge_module_registry` row and no `venture_forge_manifest` row. The
Pack was the only place they appeared.

### Why this is not the same removal as `bureau_pull` and `readiness_score`

Those two came off on 1 September and they **exist**. `readiness_score` is in
`forge_module_exclusion` because it scores a business from query parameters it never
reads; `bureau_pull` was removed because CapitalForge has no path to a bureau score
and its own specification says so. Both are capabilities that may not be granted.

These two are capabilities that are not there. **Different fact, different record.**

### Why leaving them was worse than removing them

`_modules` reports what the adapter dispatches. A module with no dispatch behind it
is not work somebody has not got to — it is a module that does not exist, and
sitting on V11's list misrepresented it as something somebody forgot to write.

The failure that invites is the one this whole exercise keeps finding: the cheapest
way to clear a name from V11 is to register it. A registered name with nothing
behind it would then resolve everywhere and be true nowhere — which is precisely
what `check_module_manuals.py` refuses to fail on, for the same reason.

### The role is left mismatched on purpose

The Placement Strategist's `forge_modules_operated` was
`[lender_match, build_packet, submit_application]` and is now `[submit_application]`.
Its duties still read *"Match a ready client to approved providers using sourced
issuer rules"* and *"Assemble the lender packet."*

**Those duties are not edited.** They describe work Burkham wants done and no module
performs. Editing them to match the code would make the Pack self-consistent and
hide the gap; leaving them makes a role whose first two duties have no module the
visible form of the question. That question is a product decision — build these, or
change what the role does — and it is not answered here.

### What returns them

**Something that dispatches them.** The day a CapitalForge adapter answers
`lender_match` or `build_packet` in its `_modules` manifest, the name goes back on
`modules_expected`, a registry row is written from the manifest, and the role
regains it. Not before: the adapter's dispatch keys are the spelling of record, and
a Pack naming a module the Forge does not dispatch is exactly what V32 exists to
refuse.

### Amended 2026-09-04 — this rule has one exception, and it is entry 5

**Read literally, the paragraph above removes `run_scenario_pack` from the SimForge
binding too, and entry 5 decides not to.** The cross-reference ran one way — entry 5
cites this one — so a reader arriving here first would apply the rule and be wrong.

The difference is what is behind the name. `lender_match` and `build_packet` had **no
implementation and no description of one**; removal moved the gap to the Placement
Strategist's duties, where a human reads it. `run_scenario_pack` names a capability
that is **known, bounded and described** — SimForge runs scenarios one at a time and
does not aggregate them into a pack run — so leaving it on the Pack points V32 at it
on every run, which is louder and more durable than a duty line.

The exception is narrow and does not reopen this entry: it applies where the missing
capability is described and intended, and it does not license leaving speculative
module names on a Pack in the hope somebody builds them.

**Recorded because a removal with no record comes back next quarter as a mystery.**
Somebody reading the Pack in December will find a Placement Strategist who operates
one module and duties describing three, and this entry is the answer to why.


---

## 5. `run_scenario_pack` stays on the Pack, unbound — SimForge has no pack-level unit of execution

**Decided 2026-09-04.**

The Burkham Pack binds SimForge at `criticality: hard` with
`modules_expected: [run_scenario_pack, gate_result]`. A SimForge Office adapter is
being built. **Only `gate_result` is bound. `run_scenario_pack` is left on the Pack
with nothing behind it, and V32 will FAIL on it.**

### What is known, and how

Read on 2026-09-04, in SimForge's source rather than inferred from its docs:

| | |
|---|---|
| What runs | `POST /api/scenarios/{scenario_id}/run` → `services/runner/execute.py:run_scenario(session, scenario_id, ...)` |
| Its argument | **one** `scenario_id` |
| What a Pack is, in the run path | a **filter** (`routers/runs.py:111`, `Run.packId.in_(...)`) or a scenario's **parent** (`execute.py:170`, `select(Pack).where(Pack.id == scenario.packId)`) |
| Anything that iterates a Pack's scenarios into runs | **nothing**, in `routers/` or `services/runner/` |

So a Pack in SimForge is a grouping that runs are *labelled with*. It is not a thing
that executes. `run_scenario_pack` names a unit of execution that does not exist.

### Why it is not bound

The only handler that could be written today runs one scenario and returns. That is
a **plausible 200 for work that never happened** — the failure shape that took
`lender_match` and `build_packet` off this Pack in entry 4, and the shape
`GET /_modules` is structurally unable to detect: a handler that overclaims is bound
to its name exactly like one that does its job.

`/_modules` proves a handler is bound. It proves nothing about what the handler does.
Binding a name to a stub is therefore worse than leaving the name unbound, because it
converts a check that would have reported the gap into one that reports success.

### Why it is not removed either — and how that differs from entry 4

Entry 4 took two module names off this Pack and stated the rule as *"a Pack naming a
module the Forge does not dispatch is exactly what V32 exists to refuse."* Read
literally, that rule removes this one too. It is not being applied here, and the
difference is worth stating rather than leaving as an inconsistency for a later reader
to find.

`lender_match` and `build_packet` were names with **no implementation and no
description of one** — nothing had been built, nothing was planned, and a search found
no service behind either. Removing them moved the gap somewhere a human reads: the
Placement Strategist's duties, which still describe work no module performs.

`run_scenario_pack` is different in one specific way: **the gap is known, bounded and
described.** SimForge runs scenarios; it does not aggregate them into a pack run. That
is a day of work with a clear shape, not a fiction. Leaving the name on the Pack points
V32 at it every time the validator runs, which is a louder and more durable place for it
than a duty line in a role.

**This is a deliberate exception to entry 4's rule, not an oversight, and it is narrow.**
It applies where the missing capability is described and intended. It does not license
leaving speculative module names on a Pack in the hope that someone builds them — that
is exactly what entry 4 refused, and this entry does not reopen it.

### What this costs, said plainly

**V32 will FAIL, not NOT_RUN, once SimForge is reachable.** That is a change in kind:
NOT_RUN means the check could not run, FAIL means it ran and the answer was no. Gate 2
blocks on both, so the Burkham Pack does not advance either way — but the reason in the
report becomes true instead of absent, and a FAIL naming `run_scenario_pack` is a
better artefact than a NOT_RUN naming a credential.

**Anyone reading a red V32 after this should not treat it as the old blocker.** The old
one was "nobody can ask SimForge". The new one is "SimForge was asked and does not
dispatch this". They look the same in a summary line and are not the same fact.

### What builds it

A pack-level execution unit in SimForge: something that takes a `packId`, iterates the
Pack's scenarios into `run_scenario` calls, and aggregates the outcomes into one result
with its own identity — a run of a pack, not a bag of scenario runs. It needs a decision
about partial failure (does one scenario erroring fail the pack run, or is the pack run
the record of what happened?) and about concurrency against SimForge's own rate limit.

**Not built here, and not costed.** Recording it so that the next person to see V32 fail
on this name finds the reason rather than re-deriving it.

---

## 6. `place_call` names a capability VoiceForge was never built to have

**Recorded 2026-09-04. Nothing built, nothing removed.**

Both Packs bind VoiceForge at `criticality: soft` with
`modules_expected: [place_call, transcribe_call]`. Reconnaissance on 4 September, read in
`C:\Users\ivann\Projects\voice-forge-ai` rather than inferred:

| | |
|---|---|
| Running? | **Yes** — `voice-forge-app` on `:3300`, `/health` → 200 |
| Answers `/_modules`? | **No.** Live probe returns 404. No adapter, no dispatch map |
| `place_call` in the codebase | **zero occurrences** |
| `transcribe_call` in the codebase | **zero occurrences** |
| Telephony of any kind | **none.** Zero Twilio references outside `node_modules` |
| `VOICEFORGE_TOKEN` | absent from `.env` **and** `.env.example`, while `forge_tenant_credential.credential_ref` is `env://VOICEFORGE_TOKEN` |

The two greps that looked like telephony were `dialogueState`, matched on `dial`. The
README describes the product plainly: *"speech in, a dialogue engine in the middle, speech
out, and a web console to design, test and watch the whole thing."* Its real surface is
`transcribe`, `synthesize`, `sessions`, `engines`, `evals`, `tenants`, `presets`, `designs`,
`ab-tests`, `metrics`.

### Why this is worse than `run_scenario_pack`

Entry 5 left a name on the Pack for a capability SimForge does not have **as a unit of
execution** — it runs scenarios one at a time and does not aggregate them into a pack run.
The ability is there; the assembly is not. That is a day of work with a clear shape.

`place_call` is not that. **VoiceForge has no phone.** There is no telephony provider, no
outbound path, and nothing in the product's description that suggests there was ever meant
to be. `transcribe_call` at least sits beside a real capability — `transcribeRoutes` is
registered at `/transcribe` behind auth, and it is genuine ASR — though "call" still
presupposes calls that this system does not place.

So the Pack declares one module adjacent to something real and one that describes a
different product.

### The part that is not merely documentation

`forge_module_registry` holds rows for both:

    voiceforge/place_call        is_mutating=t  idempotency_support=key  verification_method=hand
    voiceforge/transcribe_call   is_mutating=t  idempotency_support=key  verification_method=hand

`hand` means somebody typed them. Nothing has ever verified them against a Forge, because
there is no `_modules` endpoint to verify against.

**A grant issued over the `place_call` row would authorize an agent to place telephone
calls through a system with no phone**, and every piece of machinery downstream would
report that grant as valid: the row exists, so V6 resolves it; the manifest row and the
grant would satisfy the call path; the ledger would record the attempt. The only thing that
would say otherwise is the Forge itself, at the moment of a call that cannot be made.

V31 currently declines to rule on it — `nothing verified is known about the shape of
Acquisition Analyst: voiceforge/place_call (hand-written row, never verified against the
Forge)` — which is the rule working, and is a NOT_RUN rather than a refusal. **V31 stops an
unattended grant here. It does not stop a grant.**

### What is decided

Nothing is built and nothing is removed. This waits with entry 5.

**Three declared modules now have nothing behind them, and all three are recorded rather
than assumed:**

    lender_match, build_packet   entry 4 — removed from the Pack, gap moved to the role's duties
    run_scenario_pack            entry 5 — left on the Pack, V32 FAILs on it by design
    place_call                   here — left, and its registry row named as the live hazard

Which of the three treatments is right for `place_call` is a product decision — VoiceForge
gains telephony, or the Pack stops asking for it — and it is not answered here. What is
answered is that nobody should discover this from a 200 that never dialled.

### What retires it

A VoiceForge Office adapter whose `_modules` manifest answers `place_call`, backed by a
real telephony path. Until then the registry rows stay `hand` and V31 keeps declining. If
the decision goes the other way, the rows come off the way `bureau_pull` and
`readiness_score` did on 1 September.

---

## 7. The estate list is the one list with no upstream, and AnimaForge fell out of it

**Recorded 2026-09-04. AnimaForge added to `ESTATE` the same day.**

AnimaForge is a Forge — `navigreen311/animaforge`, video-making software, named in the
first group to be linked to The Office alongside CapitalForge and FunnelForge. It was not
in `broker/forge_map.py:ESTATE`, and had not been for as long as that list has existed.

### What that cost, stated plainly

**AnimaForge appeared in no state report at all.** Not as unbound, not as deferred, not as
blocked, not as a row with an empty status. Absent.

Every report The Office produces about Forge coverage — the estate view, the reconcile
diff, the gap tables — starts from `ESTATE` and adds whatever the registry knows.
AnimaForge was in neither, so every one of those reports was complete and correct on its
own terms and silent about a Forge that exists.

**It was not behind schedule. It was absent from the schedule.** Those look identical from
a distance and are not the same thing: the first is visible and gets prioritised, the
second cannot be prioritised because nobody is looking at it.

### Why nothing caught it, and why nothing was going to

Every other list in this system resolves against something upstream:

    forge_module_registry     resolves against the adapter's GET /_modules
    the adapter's manifest    is derived from the dispatch map - the name is there iff
                              a handler is bound to it
    a Pack's modules_expected resolves against the manifest
    the compliance library    resolves against library_entry_ref
    a certification           binds to an instruction_content_hash

`ESTATE` resolves against nothing. **There is nothing to resolve it against.** No system
holds the list of Forges that exist in the world; the repositories on disk are a claim, the
GitHub organisation is a claim, and a human's memory is the claim we are actually using.

This is not a control that failed. It is a place where there was never a control, and
saying so is more useful than inventing one — a check that compared `ESTATE` to a second
hand-written list would compare two claims, which is the shape entry 4 and V6 already
warn about.

### How it was found

**By accident.** A recon report on FunnelForge and AnimaForge was requested to size the
remaining wave of Forges to bridge. The FunnelForge half was routine. The AnimaForge half
opened with "it is not in ESTATE at all", which nobody had asked about, because nobody knew
to ask.

A list that stays correct only by somebody noticing was corrected by somebody noticing —
and it is worth being clear that this is the mechanism, not a lucky exception to it.

### What this changes, and what it does not

`ESTATE` now has nine entries. `test_the_estate_is_declared_but_its_status_never_is` still
holds: the entry names the Forge and says it has no bridge, and claims no status, because a
hardcoded status is a page that goes on claiming a Forge is unbridged after somebody
bridges it.

**No new check is added, because there is no upstream to check against.** What is added is
this entry, so the next person reading `ESTATE` knows it is somebody's memory rather than a
derived fact — and treats a Forge's absence from it as unproven rather than as evidence.

**The practical instruction:** when a Forge is named anywhere — a plan, a Pack draft, a
conversation, a repository that appears on disk — check `ESTATE` at that moment. That is the
only mechanism there is.
