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

### Corrected 2026-09-08 — both SimForge blockers were retired on 6 September, and this entry did not notice

**The table above is wrong, and has been for two days.** It is left standing because
the correction is the point. What it says:

| | |
|---|---|
| `forge_registry.base_url` | `https://example.invalid` — a deliberate placeholder |
| `SIMFORGE_TOKEN` in `.env` | **absent** — not unset in a shell, missing from the file |

**Both were false by 6 September 2026.** Verified live on 8 September, by response
body rather than by a port answering:

- `forge_registry.base_url` for simforge is `http://127.0.0.1:8110/office`. It was
  moved on 4 September — the same day this entry's correction was written, and
  `docs/port-allocation.md` records the move in detail. This entry cited the
  placeholder anyway.
- `SIMFORGE_TOKEN` is present in `.env` (written 6 September) and is byte-identical
  to `OFFICE_TENANT_TOKEN` in SimForge's own `.env`. The two sides hold the same
  credential.
- `GET http://127.0.0.1:8110/office/_modules` with that credential returns **200**
  and a manifest naming `simforge` and three modules: `gate_result`, `run_start`,
  `submit_curriculum`. The same request with no credential returns 401, so the
  authentication is real and not an open surface.

### The shape, which is worth more than the correction

**An entry whose subject is "what retires this blocker" went stale while the blocker
was being retired, and nothing pointed at it.**

This entry names, in its own words, the exact conditions that would retire it. Two of
those conditions were met by other work — a port move recorded in one document, a
credential added to a file — and neither piece of work came back here. The entry kept
being read, and kept describing a state that no longer existed, because a document
that states its own exit criteria has no way to notice when they are satisfied.

That is the same failure mode this entry already documents twice — a blocker named
one layer too shallow, found by fixing the named thing and watching nothing happen.
The variant here is worse in one respect: **the named thing was fixed, something did
happen, and the entry still said otherwise.** Nobody was misled by an unfixed
blocker; they were misled by a fixed one.

**No process is proposed here.** A convention that every change greps the decision
record for what it might retire is the kind of rule that is followed twice. What is
recorded is the failure, so that the next reader of an entry stating exit criteria
treats those criteria as a claim with a date on it rather than as current fact.

### What is actually true, 2026-09-08

**SimForge — reachable, credentialled, answering.** The half of this blocker that was
described as unscoped, uncosted and not even described is done.

**But that is not V32 clearing, and this entry's own hypothesis says why.** The
third reading above requires SimForge's manifest to contain `run_scenario_pack` and
`gate_result` under those exact spellings. **The live manifest does not contain
`run_scenario_pack`** — it has `gate_result`, `run_start` and `submit_curriculum`.
Entry 5 decided that deliberately and predicted the consequence in those words:
*"V32 will FAIL, not NOT_RUN, once SimForge is reachable."* SimForge is now
reachable. **The predicted change in kind has arrived and has not yet been observed
in a run.** Anyone reading a red V32 after this should read entry 5 before treating
it as the old blocker.

**CapitalForge — the blocker is a missing token, not a missing adapter.** This is the
third time this entry's subject has had its cause named one layer too shallow, and it
is being written down before it is discovered a fourth time. The adapter exists, is
running on `127.0.0.1:4000`, and serves eleven modules. What is missing is
configuration, on **both** sides:

- The Office: `forge_tenant_credential` for capitalforge holds
  `env://CAPITALFORGE_TOKEN`, and **no such key exists in `.env`.**
- CapitalForge: `OFFICE_SHARED_SECRET`, `OFFICE_VENTURE_TENANTS` and
  `OFFICE_SERVICE_PRINCIPAL_ID` are all absent from its `.env`. Its
  `officeBridgeConfigured()` requires all three, so **the office router is not
  mounted at all.**

The value The Office should present is whatever `OFFICE_SHARED_SECRET` is set to on
CapitalForge's side. Neither side has one yet, so this is a value to be chosen and
set in two places, not a value to be found.

**voiceforge is now the only `https://example.invalid` left in `forge_registry`.**

### A defect found while verifying the above

**An unconfigured CapitalForge bridge does not 404. It 401s, and the 401 is not the
adapter's.**

`capitalforge/.env.example` states the intended behaviour in its own comment: *"When
any is absent the adapter is NOT MOUNTED and /api/office 404s, which The Office reads
as 'serves no manifest' - the truth."* That is not what happens. Probed live:

```
GET /api/office/_modules              -> 401 UNAUTHORIZED       "Authentication token required."
GET /api/office/definitely-not-a-route -> 401 UNAUTHORIZED       "Authentication token required."
GET /api/definitely-not-a-route        -> 401 AUTH_TOKEN_MISSING "Authorization token is required."
GET /api/health                        -> 200
```

The office path is exempted from the user auth gate by `PUBLIC_API_PATHS`, so
`requireAuth` does not run. The office router is not mounted, so nothing matches.
The request then falls through to one of the routers mounted at `/` inside
`apiRouter`, which applies `tenantMiddleware` at router level — and that is what
returns `UNAUTHORIZED` from `tenant.middleware.ts:55`.

**The distinguishing evidence:** a mounted bridge rejects an unauthenticated caller
with `OFFICE_CREDENTIAL_REJECTED`. That code never appeared. And the generic gate
returns `AUTH_TOKEN_MISSING`, a different code, on a path outside `/office`. Three
distinct responses, and the one the bridge would give is absent.

**Why it matters here rather than in CapitalForge's tracker.** The design intends
absent configuration to be legible to The Office as "serves no manifest". It is
instead legible as "your credential was refused" — which is the reading that produced
the question this correction was written to answer, and which would have sent the
next person looking for a token that does not exist rather than for configuration
that was never set.

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

## 6. `place_call` — corrected 2026-09-07, and the correction was itself wrong

**The original finding stands and was the wrong reason.** Recorded 4 September as
*"a capability VoiceForge was never built to have"*, which is true and is not the
governing fact.

`burkham-wickmont-marketing-plan-intake.md` §3.4 is a locked founder decision:

> **Explicit V1 ban:** no worker (agent) may initiate an outbound phone call as
> principal. Voice AI (VoiceForge) may assist a human on a call (transcription,
> coaching, note-taking) but does not dial or speak as principal. **Enforced at
> middleware layer** per Pack Section 3.

So `place_call` is not an unbuilt capability awaiting a decision about whether to build
it. **It is an act Burkham has ruled no agent may perform**, with the reasoning recorded
— TSR, TCPA, state two-party consent, DNC — and a V1.5 revisit that is explicitly
human-only and non-recorded.

**Why the distinction changes what to do.** "Unbuilt" invites building. A hand-written
`forge_module_registry` row naming a banned act is worse than one naming an absent one:
if VoiceForge ever grew telephony, the row would resolve, V32 would go quiet, and the
only thing standing between an agent and a prohibited act would be a middleware layer in
a different system. The row should not exist regardless of what VoiceForge can do.

`transcribe_call` is unaffected — assisting a human on a call is expressly permitted.

The original text follows.

### As recorded 4 September: a capability VoiceForge was never built to have

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

### Amended 2026-09-07 (second time, same day) — the ban is Burkham's and the Pack is Greenstone's

**The correction above applied a Burkham document to a Greenstone Pack.** §3.4 is
`burkham-wickmont-marketing-plan-intake.md`. Every Pack version that operates
`place_call` is **greenstone** — `0.0.1-smoke`, `1.0.0`, `1.1.0`, `1.2.0` (live) and two
abandoned drafts. Burkham's Pack is not among them.

I read a Burkham document and ruled on a Greenstone Pack without noticing the venture
changed. The heading said so in its own words — *"an act Burkham forbids"* — sitting above
a finding about a Pack Burkham does not own.

### What is actually known

**For Greenstone, the governing fact is the original one: VoiceForge has no telephony.**
Zero occurrences of `place_call` in its source, no telephony provider, no outbound path.
That was the 4 September finding, it was never wrong, and the correction demoted it in
favour of something that does not apply here.

**Whether §3.4 binds Greenstone is not written down anywhere.** It is a locked founder
decision recorded inside one venture's intake document, under a heading that refers to
"Pack Section 3". Nothing in this repository says whether a ban recorded that way is
scoped to its Pack or is founder-tier and binds every venture. **That question decides
which fix is right**, and it is not answerable from what exists.

### The two consequences, named

**If Burkham-scoped:** Greenstone may operate `place_call` the day VoiceForge grows a
phone. Nothing would be violated. The only thing standing in the way today is the missing
capability — and a missing capability is not a control. It stops being an obstacle the
moment somebody builds the feature, and nobody building telephony in VoiceForge would have
reason to look at a Greenstone Pack first.

**If founder-tier:** it belongs in `forge_module_exclusion`, for every venture. That is the
one mechanism on the whole path that actually refuses a grant, and a ban that lives in a
markdown file while the trigger table has no row for it is a ban that is enforced nowhere.

### What the proof established — stronger than the original claim

Entry 6 said a grant over the `place_call` row *would* authorize an agent to place calls
through a system with no phone. That was an inference. **It has now been executed**, in a
rolled-back transaction:

```
attempting a grant over voiceforge/place_call (rolled back):
  *** INSERT SUCCEEDED - nothing refused it ***
```

- `forge_module_exclusion` holds **20 rows, every one `capitalforge`**. None for voiceforge.
- The `BEFORE INSERT` trigger on `agent_forge_grant` is **the only guard on the entire
  path**, and it fires on that table alone.
- V6 passes: *"all 9 module reference(s) resolve"*. V32 does not name it — voiceforge
  serves no `/_modules`, so it is never asked. V31 answers `NOT_RUN`, which stops an
  unattended grant and not a grant.

**Nothing between `forge_modules_operated` and a live grant refuses anything.**

And the path is one step longer than entry 6 described. On 7 September Gate 8 **built and
submitted a curriculum for `place_call`** to a live SimForge. A curriculum is what a
certification is earned against and a certification is what makes a grant assignable, so
the chain entry 6 called hypothetical now has its first real link. What stopped it was a
422 on `scenario_class: Field required` — the same refusal every other module got.
**Nothing anywhere noticed what the module was.**

### V33: what was submitted teaches nothing about `place_call`

Six live operating instructions share content hash `9711528544710550...`:

```
cre-forge   buyer_match, comp_analysis, property_lookup, underwrite_deal   v1.0.0
voiceforge  place_call, transcribe_call                                    v1.0.0
```

Every CapitalForge instruction has a distinct hash. These six are one generic text under
six names.

**This weakens the certification path's own guarantee, independently of the ban question.**
A certification binds to `instruction_content_hash` — that binding is the mechanism that
makes staleness computable and that SimForge *voids* a run on if the hashes disagree. It is
one of the stronger controls here. But a hash shared by six modules binds a certification
to generic text: an agent certified on `property_lookup` and an agent certified on
`place_call` would be certified against **the same words**, and the hash could not tell
them apart.

So even had the submission been accepted, the resulting certification would have said
nothing about `place_call` specifically. **The control is sound and its input is not**,
which is the B8 shape again in a different place: a mechanism reasoned about carefully,
keyed on a field that nothing populated meaningfully.

### Status

**Both questions are the founder's to decide and neither is decided here.**

1. Is §3.4 Burkham-scoped or founder-tier and binding on every venture?
2. Given the answer, does `voiceforge/place_call` come off Greenstone's Pack, gain a
   `forge_module_exclusion` row, or stay as it is?

Nothing has been changed. The six shared instruction hashes are a separate item and are
not blocked on either answer.

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

---

## 8. The identity probe was the same missing question, answered too narrowly

**6 September 2026.** The Village ran for the first time since it was bridged. The probe
written to protect it rejected it.

### The mirror

On 4 September a container from an unrelated project held the Village's port. It answered
`401`, The Office reported that as the Village refusing a credential, and V29 and V30 sat
NOT_RUN for a week. `VillageIdentityError` was the fix: a responder that cannot be
identified as the Village is not treated as the Village.

On 6 September the Village came up, and that same check rejected it on two of its six
surfaces — `/api/objectives/board` and `/api/agents/{id}/overview` — because it held one
marker tuple, the roster vocabulary, and applied it to every path. `village.quarter()`
raised, `shifts.current_quarter()` turned that into `QuarterUnknown`, and **`assign_shift`
refused every assignment for as long as the Village was running correctly.**

|  | 4 September | 6 September |
|---|---|---|
| what answered | the wrong system | the right system |
| what The Office concluded | it is the Village | it is not the Village |
| what the operator was told | "the Village refused your credential" | "nothing at this address identified itself as the Village" |
| how it was answered | too loosely | too narrowly |

**Both are the same missing question — *is this response actually from the thing I asked?*
— and the fix for the first answered it once, globally, for six surfaces that do not speak
the same way.** Getting an identity check wrong in the permissive direction admits an
impostor. Getting it wrong in the strict direction denies the real thing. Neither is the
safe side; there is no safe side to be on, only a correct answer per surface.

### The ruling

**An identity check is per surface, and a surface nobody has recorded is not judged.**

`_SURFACE_MARKERS` maps path prefix to the keys a running Village actually returns, and
`markers_for()` returns `None` for anything unrecorded. An unrecorded path is not
shape-checked at all — the alternative, reaching for some other surface's vocabulary, is
precisely the defect. `test_every_path_the_client_calls_has_a_recorded_shape` reads the
`_get` call sites out of the source and fails if any has no entry, so a new endpoint has
to record its own shape rather than inherit one.

The 401/403 half is unchanged and still applies to every path. It is the half that caught
the real incident, and it is derived rather than guessed: the Village serves these paths
open, verified against a running Village on all six.

### The test that was green the whole time

`test_a_real_village_answer_passes` asserted that a real Village answer is accepted. It
passed throughout, because it tested the single surface the markers had been written from.
It proved that the markers matched the example they were derived from, which is not a
property of the Village — it is a property of the author's belief.

**Third instance this week of a passing test that proved only what its author already
believed:**

1. The CapitalForge adapter's unit tests asserted the request the adapter *built* — the
   adapter's own belief about upstream, checked against itself. Two of seventeen bindings
   were wrong and every test passed. (`docs/forge-adapter.md`, trap #4.)
2. The CU tripwire's alias test exercised the alias the author had in mind, so the
   tripwire read as broader than it was.
3. This one.

The common shape: **the fixture and the code under test come from the same head at the
same time, so the test can only confirm the assumption it was written from.** All three
were found by contact with something the author did not write — a real upstream, a second
Forge, a running Village.

The instruction that follows, and it is a testing instruction rather than a Village one:
**when a test asserts "the real thing is accepted", the fixture must come from the real
thing, and from every variant of it.** The parametrised replacement records six captured
responses and names the surface in the failure, so the next failure says which one rather
than saying "the Village".

---

## 9. A source file drifts ahead of what is in force, and "publish the file" ships the drift

**6 September 2026.** Three department names were approved for the Greenstone Pack.
`packs/greenstone.yaml` on disk carried those three edits **and** a second, unpublished
change: `generate_loi` removed on 2 September, with an open `# DECISION NEEDED` in the
comment directly above it saying whether that role still circulates an assignment package
is Ivan's call.

Publishing the file would have shipped that decision as a side effect of a rename.

### What made it dangerous

Not that the file had drifted — that is normal and often correct; the disk version was
*ahead*, and its extra change was good work. The danger is the shape of the approval
against the shape of the act:

**The approval was for three lines. The act was "publish this file." Nothing in the
publish path connected the two.** `store()` computed no diff, reported no count, and —
until this entry — wrote **no audit entry at all**. A publish recorded a new
`content_hash` and nothing whatever about what it had done. There was no point, before or
after, at which anybody would have been shown that more than three lines changed.

A publish is not a small act: it changes what the next provisioning run builds and voids
every Gate 10 signature taken against the previous version's artifacts. It was the least
observable write in the system.

### What was done that day, and why that is not good enough

The caller asserted the diff by hand — rewrote the three lines against the *published*
source rather than the file, then checked that exactly three lines differed before
publishing. That was the right instinct and it is worthless as a control, because it
lived in a one-off script that somebody remembered to write. The next publish is a
different script by a different author, and the property it protected is not a property
of that author's care.

### The ruling

**Assert-the-diff belongs to the publish path, and the diff is recorded whether or not
anybody asked for it.**

`packs.store()` now:

- computes the changed lines against whatever it is replacing, before writing;
- accepts `expect_changed_lines`, and raises `PackDiffUnexpectedError` **before writing
  anything** when the actual count differs — the message names the differences;
- writes `pack_published` / `pack_drafted` naming the replaced version, the change count,
  what the caller declared, and the changed lines themselves.

Declaring the count is optional, because the console has a human editing a draft freehand
and cannot know it in advance. **Recording what changed is not optional.**

The comparison is positional, not a real diff, and that is deliberate: this control
answers *"did exactly the edits I intended land"*, and for that an inserted line SHOULD
read as a large change rather than as one. A caller declaring three changed lines is
declaring that nothing moved.

### The general form

**Any path that promotes a file into force has this problem.** The file is edited
continuously and promoted occasionally, so at any moment it may contain work that was
never approved and was never meant to go out with the next thing that does. Where such a
path exists, the promotion must state what it believes it is changing and refuse when it
is wrong — and it must leave a record either way, because a promotion nobody can
reconstruct is one nobody can review.


---

## 10. `generate_loi` named the wrong module for work CRE Forge already does — a fourth class, and the question that finds it is different

**Ruled 2026-09-06.** The duty stands. `generate_loi` comes off the Pack. Something binds
to the assignment capability.

### The finding

`generate_loi` does not exist: CRE Forge has no letter-of-intent service, route or
template. That much matches entries 4, 5 and 6, and on 2 September it was removed on that
basis with the duties left unnarrowed and an open `# DECISION NEEDED` above them.

**But CRE Forge can already do the work the duty describes.** Asked directly rather than
read — `GET /api/v1/contracts/templates` on the running instance:

```json
"assignment": {
  "name": "Assignment of Contract",
  "description": "Assignment of purchase contract to end buyer",
  "required_fields": ["contract_price", "assignment_fee", "buyer_contract_price"],
  "signers": [{"role": "assignor", "description": "Assignor (Company)"},
              {"role": "assignee", "description": "Assignee (End Buyer)"}]
}
```

The template's own fields settle it. **Assignor is the company, assignee is the end buyer,
and `assignment_fee` is the wholesaler's spread.** That is Buyer Network Manager's
"circulate the assignment package", exactly. Behind it: contract creation from template
with required-field validation, PDF generation, send-for-signature, signing URL, status
sync, void, and a deal-package PDF.

**The Pack asked for a letter of intent to describe an assignment contract.** Not a
missing capability — a misnamed one.

### Why this is its own class

Entries 4, 5 and 6 are names with nothing behind them. The question that finds those is
**"does this module exist?"** — asked of the Forge, answered no, and the fix is to remove
the name or build the thing.

**This one survives that question.** `generate_loi` genuinely does not exist. Removing it
looks correct and is correct. And at that point the position keeps a duty —
*"Circulate the assignment package"* — with no module behind it, and **no rule notices,
because duties are prose.** V6, V11, V29, V31 and V32 all reason about modules. Nothing
reads a duty and asks what it would take to do it.

So the failure mode is not a Pack that claims a capability the estate lacks. It is a Pack
that **quietly stops claiming a capability the estate has**, and reads correctly
afterwards. The removal is locally right and globally wrong, and every automated check
agrees with it.

**The question that finds this is "what does this duty need?", not "does this module
resolve?"** The first is asked of the Pack's prose and answered against the Forge's
catalogue. Nothing asks it today; the `# DECISION NEEDED` comment left in the Pack on
2 September is what carried the question forward, and it worked because a person read it.

### The detection asymmetry, stated plainly

| | entries 4, 5, 6 | this one |
|---|---|---|
| the module | does not exist | does not exist |
| removing it | correct | correct |
| after removal, the Pack | claims less, truthfully | claims less, **untruthfully** |
| what a rule sees | a failure, then a clean Pack | a clean Pack, both times |
| what finds it | "does this module exist?" | "what does this duty need?" |
| who can ask it | a check | a person reading the duty against the catalogue |

### What follows

- The duty is unchanged. Buyer Network Manager still circulates the assignment package.
- `generate_loi` comes off `forge_modules_operated` and off the cre-forge binding's
  `modules_expected`, where it sat at `criticality: hard` — so the Pack had asserted the
  workflow could not run without a module that will never exist.
- A module binds to the assignment capability in CRE Forge's adapter, declared honestly
  at the binding site: **contract creation writes and sends for signature, so it is not a
  read.**
- Published through the diff control of entry 9, with the change count declared.


---

## 11. Adding a module to a Pack decertifies the position, and Gate 4.5 names the wrong cause

**Learned 2026-09-06, at a cost of 50 test failures**, binding `assign_contract` into
Greenstone.

### What happens

An agent is certified per `(agent, forge, module)`. A position is fillable when its
occupant is certified for **every** module the position operates. So adding one module to
a position's `forge_modules_operated` makes **every agent certified for the old set
unfillable for it** — instantly, and without any certification changing.

That much is correct and is the point of Unit A. The problem is what the system then says.

### The symptom names the wrong cause

Gate 4.5 reported:

```
V24: unfilled positions: Buyer Network Manager (2 of 2)
V13: The compliance officer would receive 128 approvals a day ...
```

**"Unfilled positions" reads as "not enough people."** The fact was "these two people are
not certified for what the role now does" — a different problem with a different fix.
Nobody adds headcount to solve a missing certification, and the V13 figure *fell* at the
same time (160 → 128), because an unfillable position contributes no approvals, which
makes the capacity picture look better while the venture became less able to operate.

Both numbers moved in the direction that reads as "smaller problem". The cause was a
module binding half an hour old.

### AMENDED 7 September 2026 — the data is not dropped. The summary flattens it.

**The claim below was wrong and is corrected here rather than deleted.**

It said *"the information exists one layer down and is dropped on the way up."* Tested by
issuing 14 banking identities and running appointment:

```
Deal Underwriter:      need 2, unfilled 2, candidates-with-shortfall 14
                              14 x never_certified
Acquisition Analyst:   need 3, unfilled 3, candidates-with-shortfall 0
Buyer Network Manager: need 2, unfilled 2, candidates-with-shortfall 0
```

`PositionAppointment.requires_certification` carries the reason **per position**, and the
escalation reports all three capacity numbers separately. An operator reading the artifact
can already tell *nobody exists* from *fourteen exist, none certified*.

**What actually flattens is Gate 4.5's summary line** — `V24: unfilled positions: Buyer
Network Manager (2 of 2)`. That sentence loses a distinction the artifact beneath it
preserves.

**Narrower defect, different fix.** Not a missing signal to be plumbed through: a message
that should read what is already there. The original diagnosis pointed at the wrong layer,
and would have sent somebody to add instrumentation that exists.

### The class this belongs to — a rollup that loses what the layer beneath kept

Three instances now, which is enough to name it:

| where | the rollup says | what the layer beneath holds |
|---|---|---|
| **Gate 4.5 summary** | `unfilled positions: X (2 of 2)` | `requires_certification`, 14 × `never_certified` vs 0 candidates |
| **V30's message** (entry 14) | `3 department(s) have seats` | which population was counted — Village roster, not `office_agent_identity` |
| **V32's verdict** | `FAIL` | the message distinguishes modules it *asked about* from voiceforge it *could not ask*; the verdict does not |

**The shape:** a summary is computed correctly from data that is correct, and the summary
drops a distinction that decided the answer. Nothing is missing, nothing is wrong, and the
sentence an operator reads is less true than the structure behind it.

**Why it is worth its own name.** It looks like the failures this project keeps finding —
a control that does not hold, a check passing for the wrong reason — and it is not. The
control ran. The data is right. The fix is a sentence, and diagnosing it as a missing
signal costs the wrong work: entry 11 as first written would have sent somebody to plumb
`CandidateShortfall` up through a layer it already reaches.

**How to tell them apart:** read the layer beneath before believing the summary. If the
distinction is there, it is a message defect. If it is not, it is a signal defect. That
check is one query and it is the difference between a wording change and a schema change.

### A fourth instance, 7 September — and it extends the class

`produced_not_yet_certified` is not a summary line. It is a **field name**, and it is
wrong in the same way.

It reads as a fact about the venture: *how many agents have been produced and are not yet
certified.* It is a fact about **an appointment run** — it increments inside the
per-position candidate loop in `generators/appointment.py`, once per candidate examined for
a position being appointed. An uncertified identity in a department no position draws on
is never counted, because it is never examined.

**How it was separated, and it was nearly not.** Issuing 12 operations identities moved it
14 → 26, exactly +12. Both readings predict that, because operations feeds Greenstone's
Buyer Network Manager — every new identity was also a candidate. The operations prediction
stated the wrong reading — *"it counts identities that exist and are uncertified across the
venture"* — and **scored correct by coincidence.**

Issuing 25 administration and marketing identities moved it **26 → 26**. Greenstone has no
position in either department, so nothing examined them, so the counter did not see them.

**The round that separated the two readings is the one dismissed in advance as the weaker
test.** Banking and operations each had a Greenstone position and could only ever confirm;
a department with no position was the only thing that could discriminate, and it was run
only because a round predicting nothing is still worth running.

### The extension

**A rollup can lose a distinction. So can a name.**

A summary line is read once, by whoever is looking at that screen. **A field name is read
by everyone who touches the field, forever**, and it carries its claim into every call
site, every message built from it, and every prediction made about it — including the two
in this repository's own planning documents.

The check is the same one, aimed differently: *read the code that produces the value before
believing what it is called.* For `produced_not_yet_certified` that is one loop, and it
says `for row in candidates` where the name says "in the venture".

**Not renamed here.** It appears in `CapacityNumbers`, in the §7.2 three-number contract,
in the escalation text and in golden snapshots, and a rename is a change to an artifact
shape that Gate 4.5 signatures are taken against. Recorded first; the rename is its own
change with its own diff to declare.

### What still stands from the original finding

The mechanism is unchanged and correct: **adding one module to a position makes every
agent certified for the old set unfillable for it**, instantly, without any certification
changing. That is what Unit A is for, and it will happen again on the next module added to
any position.

What changes is where to look when it does — the appointment artifact names the cause; the
gate's summary line does not.

### Original text, as recorded 6 September

Nothing connects the two facts. `appointment` knows a position is unfilled and knows which
certifications were missing — `CandidateShortfall` carries the reason per agent, naming
`never_certified` rather than collapsing to "not eligible". **V24's message does not carry
it.** The information exists one layer down and is dropped on the way up.

The next module added to any position does this again, and the operator sees a capacity
shortfall.

V24's message should distinguish *no candidate exists* from *candidates exist and are
uncertified for the module just added*, and name the module. The data is already in
`Appointment.appointments[].shortfalls`. Not done here — it is a message change to a
blocking gate and belongs with the capacity work rather than tacked onto a module binding.


---

## 12. Channel Partnerships maps to `marketing`. The other nine stay open, and here is what that costs

**Ruled 2026-09-07**, one mapping only. The rest is recorded as open because it is a
decision about how Burkham's structure sits inside the Village's, and it should not be
settled as a side effect of wanting to bind a Forge.

### The two lists intersect at zero

| Burkham (10, from `blueprint-v2.md` ownership lines) | Village (12, live roster) |
|---|---|
| Compliance & Evidence · CapitalForge Ops · Funding Strategy · Concierge Desk · Risk & Defense · **Channel Partnerships** · Capital Operations · Founder / Executive · Capital Readiness · CFO Advisory | administration 11 · ai_data 14 · banking 14 · engineering 26 · executive 8 · infrastructure 17 · **marketing 14** · media_production 20 · music_production 20 · operations 12 · publishing 16 · research 14 |

Not a near-miss. **No name appears on both sides.** `source_department` must name a
Village department because V29 checks it against the live roster, so every Burkham
position names a Village department chosen as the nearest fit, and the draft marks each
one a guess.

(The draft's own header lists eight Burkham departments. There are ten — it omits
**Capital Readiness** and **CFO Advisory**.)

### The one ruled

**Channel Partnerships → `marketing`.** The Village's `marketing` department has 14 seats
and Burkham uses none of them. It costs nothing that exists, and it is what makes a
marketing role authorable at all — until some mapping exists, no marketing position can
be written, because a position must name a department the roster has.

Channel Partnerships and Concierge Desk jointly own §4.5 Marketing Ops in the blueprint.
Only the first is ruled here; Concierge Desk keeps its open question below.

### What the current guesses do, and why it is not visible

Ten Burkham departments compress into **three** Village ones:

| Village dept | Burkham departments landing on it | seats | positions |
|---|---|---|---|
| `banking` | **CapitalForge Ops** + **Funding Strategy** | 14 | Diagnostic Analyst (2), Placement Strategist (2) |
| `operations` | **Concierge Desk** + **Capital Operations** | 12 | Intake Concierge (2), Stack Manager (1) |
| `administration` | Compliance & Evidence | 11 | Compliance Reviewer (1) |

**Two Burkham departments sharing one seat pool is invisible to every check that would
catch it.** V30 compares requested headcount against the Village department's size, and
Gate 4.5 asks whether those seats are uncommitted — both read `source_department`, and
neither can see that two distinct Burkham departments are competing for the same 14. Four
Burkham departments are drawing on two pools and the arithmetic reports three
departments comfortably within their size.

That is a lossy mapping presented as a clean one, and the loss is exactly the kind V30
and Gate 4.5 exist to surface. They will keep passing while it is wrong.

### The five with no mapping at all

No position uses them, so nothing has forced a choice:

**Risk & Defense · Founder / Executive · Capital Readiness · CFO Advisory** — and
**Concierge Desk**, which is mapped for intake work but is also a Marketing Ops owner,
where `operations` is the wrong home.

`executive` (8 seats) is the obvious candidate for Founder / Executive and is untouched.
Risk & Defense has no natural Village counterpart; `administration` already carries
Compliance & Evidence.

### Why the rest stays open

Each remaining mapping decides which seat pool a Burkham department competes in, and
therefore what Gate 4.5 says about capacity. Ruling them one at a time as each Forge
binding needs one produces a mapping nobody designed — which is how `banking` came to
hold two departments. The right shape is one decision covering all ten, made once,
against the seat counts above.

### Compression is right. New Village departments are not the answer — 7 September

The obvious alternative — give Burkham's ten departments their own names in the Village —
was checked and rejected.

Departments are not a fixed set. They come from `config/agentsrole.yaml`, a top-level
`departments:` mapping whose keys are the names; `/api/org/departments` derives its answer
by counting agents under each. Adding a key with agents under it flows through to V29 with
no code change.

**But `modules/heredity/education.py` holds a second list, and it is not a list.**
`DEPARTMENT_NAMES` carries eleven — `executive` is excluded as *"leadership, not a
production department"* — and every name in it needs an entry in
`DEPARTMENT_CONSTELLATIONS`: a weight vector over nine personality traits deciding which
agents are suited to that department.

The file states its own design constraints: 2–3 traits each, weights ±0.40–0.55,
deliberately anti-correlated pairs (`engineering↔marketing`, `banking↔ai_data`), and a
uniform weight sum *"so no department is inherently noisier"* — the whole thing tuned to
produce a particular aptitude spread against an unemployment threshold of 0.354.

**So a new production department is a design decision about agent aptitude**, not a naming
one. Ten new departments would mean ten new personality profiles placed in a space
designed to hold eleven without distorting the distribution that governs whether agents
find work at all.

**Compression onto existing names is therefore right.** The problem was never that the
mapping compresses; it is that the compressions were guessed. The draft says so itself —
*"EVERY `source_department` below is a GUESS"* — and a guess is what put two Burkham
departments on `banking` without anyone weighing it.

**What the remaining nine need is not a Village change. It is somebody who knows what each
Burkham department actually does**, mapping each onto the Village department whose agents
do the nearest thing — the way `Channel Partnerships → marketing` was ruled, and the way
`operations`' Client Liaisons settled Buyer Network Manager for Greenstone. That is a
question about Burkham, and nobody has answered it yet.

(A *leadership* department, following `executive`'s precedent, skips the constellation
entirely — which is the one case where a new Village department would be cheap. Founder /
Executive is the candidate if it ever needs one.)
## 13. `is_mutating` answers whether state changes, not whether the act is consequential

**Found 2026-09-07**, sizing `generate_document` for CapitalForge.

### The declaration is honest and the guard is blind

`POST /documents/generate` produces one of sixteen client-facing letters. Every `await`
in its 304-line handler is a read — `checkRestackEligibility`, `getConsentStatuses`,
`findMany` on `cardApplication` and `statementRecord`. No `create`, no `update`, no
`upsert`, no transaction. It returns the document text in the response body and persists
nothing.

So **`is_mutating: False` is the correct declaration** and `idempotency_support: natural`
is correct with it. Two identical calls produce identical text and change nothing.

**V31 decides unattended `auto_execute` on that field.** Its rule is: no `auto_execute`
grant over a mutating `at_most_once` module. A read is outside the guard entirely — so an
`auto_execute` grant on this module lets an agent produce client-facing letters, about a
client's own eligibility and consent status, with nobody in the path.

### The field is standing in for something it does not mean

`is_mutating` is a fact about the Forge's own state. What V31 needs is whether the act is
**consequential** — whether something leaves the system and reaches a person. Those
coincide for most modules, which is why the substitution has held:

| | mutates | consequential |
|---|---|---|
| `property_lookup`, `client_read` | no | no |
| `assign_contract`, `submit_application` | yes | yes |
| **`generate_document`** | **no** | **yes** — its output is a letter a client is handed |

A read whose output is an external artefact is the gap. The guard cannot see it, and
nothing else in the call path asks the question.

### Not proposing a third field yet

The obvious move — a `produces_external_artifact` flag — is a schema change plus a
migration plus a value for every existing module, and every value would be somebody's
judgement rather than something derived. `is_mutating` and `idempotency_support` are at
least checkable against a Forge's own dispatch map. Recording the gap first.

The interim answer is the trust tier, which is per position: a position operating
`generate_document` should not be ceilinged at `auto_execute` on the strength of the
module being a read.

### What Burkham's own decisions already settle, and the dependency they create

`burkham-wickmont-marketing-plan-intake.md` §3.3 and §4.6 have ruled on exactly this act,
and they agree with how the code is split:

- §3.3, engagement letter delivery: **"Worker generates, Human approves send"** — each
  engagement letter goes through **Deliverable Approval Workflow (Pack module 3.4)**
  before sending.
- §4.6, worker-autonomous send: **templated deliverable cover emails** (Blueprint
  delivered, Capital Command Brief delivered) in **Pass** state.

`generate_document` does not send. The code already splits generation from sending, so
**unattended generation matches the locked decision** rather than contradicting it.

**But the control that makes it safe is not in The Office.** Deliverable Approval Workflow
is Console module 3.4, and the Console is not connected to the bridge. Today an agent
granted `generate_document` at `auto_execute` generates a letter and nothing stands
between that letter and a client except a human remembering to route it — the approval
gate exists as a design, in a system with no connection to the one issuing the grant.

**Written down rather than assumed:** binding `generate_document` at `auto_execute` takes
a dependency on a Console module that does not yet reach The Office. Either the grant
waits for that connection, or the position's tier carries the restraint instead.


---

## 14. V30 measures the wrong population, and it is the rule that was supposed to catch this

**Found 2026-09-07**, checking whether two Burkham departments sharing one Village seat
pool was a live problem. It is not, and the reason is worse than the collision.

### The two numbers

```
department        Village roster seats    Office identities
banking                             14                    0
marketing                           14                    0
operations                          12                    0
engineering                         26                    3
TOTAL                              186                    3
```

**V30 reads the left column. Appointment reads the right one.**

`depts.seats()` resolves through `broker/departments.py` to the Village's
`/api/org/departments`, which counts roster positions — `entry["seats"] += 1` per agent in
`config/agentsrole.yaml`. That is the Village's population.

`appointment._candidates` selects `FROM office_agent_identity WHERE status = 'active' AND
department = %s`. That is The Office's population, and it contains an agent only once
somebody has issued an identity for them.

**Different tables, different populations, and V30 has no way to see the difference.**

### What that makes V30's answer

A Pack asking for 2 positions in `banking` gets:

- **V30: PASS** — *"banking has 14 seats for what the Pack asks"*
- **Appointment: zero candidates.** There are no `banking` identities. There have never
  been any.

The number V30 reports is not the number that decides whether a position can be filled. It
is a fact about the Village, presented in answer to a question about The Office.

### This is entry 11's shape, arriving in the rule meant to catch it

Entry 11 records that adding a module makes a position unfillable and Gate 4.5 reports it
as a capacity shortfall — the symptom naming the wrong cause. **V30 is the earlier check
that exists to catch capacity problems at Gate 2, before appointment runs.** It cannot,
because it is looking at a different population than the one appointment draws from.

So the sequence is: V30 passes at Gate 2 on 14 Village seats, and Gate 4.5 fails on 0
appointable candidates, and neither message says the word *identity*.

### The collision was real and is not the live problem

`banking` carries two Burkham departments — CapitalForge Ops and Funding Strategy — and
`operations` carries two more. Entry 12 records that as a lossy mapping that V30 and Gate
4.5 cannot see.

**That is still true and it is not what is stopping anything.** Two Burkham departments
competing for 14 seats would matter if 14 were a constraint. It is not: `banking` has zero
appointable candidates, so the competition is between two departments for nothing.

Worth stating because it changes what to fix first. The mapping is a design question with
time to spare. The population mismatch makes a passing rule misleading today.

### What the fix is not

Not "make V30 read `office_agent_identity`." That would trade one wrong answer for
another: at Gate 2 a Pack is being validated before any identity has been issued for it,
so a rule reading identities would fail every Pack for a reason that is about provisioning
order rather than about the Pack.

The two populations answer two different questions, and both are worth asking:

| question | population | when |
|---|---|---|
| is this department big enough to staff this Pack at all? | Village roster | Gate 2 — V30's job, correctly |
| is anybody actually appointable? | `office_agent_identity` | Gate 4.5 — V24's job |

**The defect is that V30's message does not say which one it answered.** *"3 department(s)
have seats for what the Pack asks"* reads as a statement about availability. It is a
statement about the Village's headcount, and it would read the same on a database with no
identities at all — which is the database it was read on.

### Recorded rather than fixed

The message change is small and the surrounding question is not: V30, V24 and Gate 4.5
each hold part of an answer about capacity, and none of them names the thing that is
actually missing. Fixing V30's wording alone would make it honest and still leave the
operator without the sentence they need, which is *"no agent in this department has an
Office identity."*

That sentence belongs with the identity-issuance work, not with a validator message.

---

## 15. Every capacity number in this system is Greenstone's — Burkham has never been provisioned

**Recorded 7 September 2026**, after the identity work, because the reasoning error is
instructive and was caught by protocol rather than by knowing better.

### The trap

Operations was chosen as the second department to issue identities into, and the stated
reason was that **Stack Manager needs only 1** — so unlike banking's two-of-two positions,
there was a position that could plausibly be filled.

**Stack Manager is a Burkham position, and Burkham is not in `business_pack`.** It exists
only as `packs/burkham-wickmont.draft.yaml`, whose first line says `DRAFT, NOT LIVE`.
Nothing evaluates it: no provisioning run, no gate, no validator invocation in normal
operation.

The operations position that actually moved was **Greenstone's Buyer Network Manager**,
which needs 2 — so the reasoning that selected operations was about arithmetic no gate
computes.

### The general statement

**Every capacity number this system reports today is Greenstone's.** V13's review-minutes,
V24's unfilled positions, V30's seats, Gate 4.5's shortfall, `produced_not_yet_certified`
— all of it resolves against `packs.live(conn, "greenstone")`, because greenstone is the
only venture with a published Pack.

So **reasoning about a Burkham position moving a gate's arithmetic is reasoning about a
Pack that is not there.** The position exists in a file; the number it would move does not
exist at all.

Easy to do, because the draft is detailed, internally consistent, and reads exactly like a
Pack. Nothing about looking at it says "no gate will ever see this."

### How it was caught

Not by knowing better. The prediction protocol required naming which evaluation path each
prediction would be scored against, and there was no path — `validate()` and `appointment`
both take the *live* Pack, and greenstone is the only one. Writing the prediction is what
surfaced it.

That is the second time the protocol caught something the author knew and had not applied:
the first was testing V24, a Gate 4.5 rule, through a Gate 2 call.

### What it means for the identity work

**51 agents are now appointable and there is still no Burkham Pack to appoint them into.**

```
banking         14      operations      12
administration  11      marketing       14      = 51, plus 3 engineering = 54
```

Greenstone draws on three departments — `research` (nobody), `operations` (12 uncertified),
`banking` (14 uncertified) — and has no administration or marketing position at all.
Issuing those 25 changed no appointment output whatsoever, which the round confirmed:
`produced_not_yet_certified` stayed at 26.

**Identities were never the blocker on their own.** They were *a* blocker — banking had
zero candidates and now has fourteen — but for Burkham the chain is longer and identity is
not the first link missing.

### What publishing a Burkham Pack would actually require — tested, not read

The draft says its values are placeholders and that the placeholders are the finding. Both
halves were tested by parsing it and running the validator against it.

**Publication is not blocked.** `packs.parse_only` accepts it as a schema-v3 Pack with
`venture_id='burkham-wickmont'`. `store(publish=True)` requires nothing more, so it could
be published today — and Gate 2 would then refuse it, which is the correct place for a
Pack to be refused.

**Gate 2 gives 3 FAIL, 2 NOT_RUN, 0 WARN:**

| rule | verdict | what it is |
|---|---|---|
| **V23** | FAIL | *no scenarios for: Compliance Reviewer, Diagnostic Analyst, Intake Concierge, Placement Strategist, Stack Manager* — **the draft contains zero scenarios** |
| **V22** | FAIL | runtime flags never exercised by a scenario — the same absence, from the compliance side |
| **V32** | FAIL | `simforge/run_scenario_pack` not dispatched — a standing ruling (entry 5), not a Burkham problem |
| V11 | NOT_RUN | instructions authored for all 10 modules; module existence uncheckable because CapitalForge answered 401 |
| V24 | NOT_RUN | Gate 4.5, by construction |

**So the blocking placeholder is exactly one thing: the scenario set, and it is empty
rather than invented.** The draft header lists it among the invented values —
*"the whole scenario set"* — and it is not invented, it is absent. 22 declared frameworks
and 5 roles, against 0 scenarios. V23 wants ≥3 per role × domain with ≥1 expected
escalation each; V22 wants every declared runtime flag exercised.

**What is cosmetic, in the sense that it does not block:** `human_capacity`, `budget`,
`capacity_demand`, `availability`, KPI measurement sources and `data_retention` all pass
their rules on invented values. That is the draft's own warning restated with evidence —
*"a rule that PASSES here may be passing on an invented value"* — and it is the more
dangerous half, because those passes are indistinguishable from earned ones.

**The order of work, therefore:** scenarios first (authorship, 5 roles × domains × 22
frameworks), then the invented values replaced by real ones, then the department mapping
from entry 12. Identity issuance is done and was never the constraint.

---

## 16. `live` means published, not validated — the fifth instance, and the first signal defect

**Found 7 September 2026**, within the hour of publishing a second Pack.

### The class test returns *not there*

The four instances in entry 11 share a fix: the distinction exists one layer down, and the
rollup or the name fails to carry it. The test is *read the layer beneath before believing
the summary* — if the distinction is there it is a message defect.

**For `live` it is not there.** `business_pack` carries
`venture_id, pack_version, schema_version, yaml_source, parsed, content_hash, authored_by,
authored_at, superseded_at, status`, and `status` is `draft | live | superseded |
abandoned` — a **publication lifecycle**. No column, no other table, and no audit
projection records whether a Pack passed its gates.

So `live` cannot be read correctly by any reader however careful. The fact that would
justify the inference is not written down anywhere.

**That makes this the first signal defect of the five.** The previous four were fixable
with a sentence or a rename. This one needs a fact to exist first.

### How it was found, which is the part worth keeping

**`live` and `validated` were the same set while one Pack existed**, and both were true of
it. Greenstone passed its gates and was in force; every reader treating `live` as *usable*
was correct, and had been correct for as long as the system had been running.

Publishing Burkham — a Pack Gate 2 refuses, published deliberately so the refusal would be
legible — **separated the two sets within the hour**, and it surfaced in a query about
reviewer capacity rather than anywhere near provisioning.

It would have surfaced whenever the second venture arrived. Later, with more built on top,
and probably by somebody acting on the number rather than by somebody looking for it.

**The argument that publishing Burkham was right is that it did this.** A Pack sitting in a
draft file could not have separated the sets.

---

## 17. Two defects in `proposals.queue`, and they are independent

**Read this first, because "display only" reverses here.**

The question asked of both defects was *what acts on the number* — expecting that "display
only" would mean low stakes. It does not. The number feeds one consumer, a banner on
`/proposals`, and **the banner is the whole consequence**:

> *N pending against M remaining approvals in today's coverage. The overflow will not be
> reviewed before the window closes.*

**An inflated denominator does not cause a wrong action. It suppresses a warning.** The
failure mode is not a bad decision anybody could point at afterwards — it is **silence**,
and silence is the hardest thing to notice missing. Nobody investigates a banner that did
not appear.

Both found while checking entry 16. Recorded separately because fixing either leaves the
other standing.

### One — reviewer capacity is read from every live Pack with no gate check

```python
await cur.execute("SELECT venture_id FROM business_pack WHERE status = 'live'")
# Reviewer capacity comes from each venture's live Pack, which is where
# `human_capacity` is declared... There is no reviewer table: the Pack is the
# source of truth for who reviews and how much they can take.
```

**Burkham's `human_capacity` is INVENTED** — its own header says so — and Burkham is now
live, so those invented figures are real input to this view:

```
greenstone         Ivan  capacity=60      Dana  capacity=30
burkham-wickmont   Ivan  capacity=60      Dana  capacity=30     <- Gate 2 refuses this Pack
```

This is instance five above, seen from the consuming end.

### Two — the same human is counted once per venture, and the view sums him

Independent of the gate question and **survives fixing it.** `human_capacity` is declared
per Pack; a human who reviews for two ventures appears in two Packs; nothing
de-duplicates by person.

```
capacity.remaining_today  180        summed across both live Packs
                           90        greenstone alone
inflation                  90
```

Ivan is one person and contributes 60 twice.

**Even with both Packs validated and both figures real, this number is wrong.** It is a
sum over Pack rows presented as a sum over people.

**And it scales with ventures.** `human_capacity` is declared per Pack, so every venture a
reviewer covers adds their full daily figure again: **+90 per venture Ivan and Dana both
review for**, against a real capacity that does not move at all. Three ventures reads 270,
four reads 360, and the same two people are doing the reviewing throughout.

That matters because more ventures is the plan, not a hypothetical. The error is not a
fixed 90 to be remembered — it grows with exactly the thing the system is built to do,
and it grows in the direction that keeps the warning quiet.

### What acts on it — display only, and it is a warning that fails to fire

`capacity_remaining` feeds exactly one thing:

```python
"over_capacity": len(pending) > capacity_remaining and len(pending) > 0,
```

which renders a banner on `/proposals`: *"N pending against M remaining approvals in
today's coverage. The overflow will not be reviewed before the window closes."*

Nothing refuses, throttles, routes or blocks on it. **No control consumes it.**

**But the harm is not zero, and it is the shape that is easy to dismiss.** An inflated
denominator does not cause a wrong action — it **suppresses a warning**. The banner exists
to tell a human that work will not be reviewed before the window closes, and a capacity
figure 90 too high is 90 proposals of silence before it appears.

A false negative on an alert, not a bad decision. Smaller than "something acts on it",
larger than "display only" suggests, and the two words are not synonyms.

Today: 2 pending against a claimed 180, so the banner is nowhere near firing under either
figure. The defect is latent and will stay latent until proposal volume approaches
reviewer capacity — which is the point at which the banner is the only thing that would
say so.

**No fix proposed for either.** The size of the second is what decides whether the first is
worth a column.

## 18. A module can be dispatched and deliberately not agent-facing

**Decided 2026-09-07.**

SimForge will bind `submit_curriculum` and `run_start` on its `/office` adapter so The
Office can reach them with the tenant credential. **Neither gets a `forge_module_registry`
row, and that is permanent rather than pending.**

### Why no row

**A registry row exists so a grant can be issued over a module.** That is what the table
is for: `resolve_grant` joins it, `is_mutating` on it decides whether an agent may run
unattended, `agent_forge_grant` references it, and V31 reads it. Everything a row does,
it does for an agent.

Neither of these is an agent act. `submit_curriculum` hands a curriculum over during
provisioning — Gate 8 runs before any agent exists for the venture, and the actor is the
human who provisioned. That is exactly why it is signed with the Office's own tenant
credential rather than through the brokered path. `run_start` opens the run a verdict is
later read by; it is bookkeeping between two systems.

**Rows would make them look grantable.** A row is the thing a person reads to decide what
an agent may be given, and two rows nobody may ever grant is an invitation to grant them.

### The verifier said the right thing for the wrong reason

`scripts/verify_forge_modules.py` reports a dispatched module with no row as:

```
DRIFT simforge/submit_curriculum: dispatched by the Forge and unknown to the registry.
Not added - a Forge does not enlarge its own agent-facing surface.
```

**The verdict is right and the sentence is wrong.** "Unknown to the registry" describes a
gap somebody should close. The truth is "deliberately not in it" — a decision, already
made, that nothing is meant to change.

Left alone, that is **two permanent DRIFT lines on every run**. A finding nobody can act
on is how a report becomes something people skim, and the cost is not the noise: it is the
real DRIFT line that appears beside them one day and gets skimmed with them.

### What was built

`broker.forge_modules.NOT_AGENT_FACING` — `(forge_id, module_id)` to the reason it is
dispatched without a row. The verifier prints those as **NOT AGENT-FACING**, with the
reason, and does not count them toward its exit status.

**This does not weaken the rule beside it.** *"A Forge does not enlarge its own
agent-facing surface"* holds exactly as before: an entry here makes nothing callable by an
agent, creates no grantable capability, and touches no table. It records that a person
decided this name is not agent-facing, and why. Adding one is an edit to a source file
under review, which is the control.

### The general shape

**A check with only two verdicts will file a third thing under whichever fits worse.**
This one had DRIFT and MISMATCH, and a deliberate absence is neither — it is not a
disagreement about whether the module exists, and not a disagreement about what it does.
It got DRIFT because DRIFT was closer.

Worth asking of any conformance check: **is there a legitimate steady state it has no
verdict for?** If there is, that state will be reported as a fault forever, and the report
loses its readers before it loses its correctness.

## 19. §3.4 is founder-tier and binds every venture — and nothing said so

**Ruled 2026-09-07**, resolving the question entry 6's second amendment left open.

### The ruling

**No worker may initiate an outbound phone call as principal. This binds every venture,
not only Burkham.**

> A worker not initiating an outbound call as principal is a statement about what agents
> in this system do, not about how Burkham markets. It was written in a marketing intake
> because that is where the question arose, not because that is its scope.

VoiceForge may assist a human on a call — transcription, coaching, note-taking. It may not
dial or speak as one. `transcribe_call` is expressly permitted and stays grantable; the
whole shape of the ban is initiate-versus-assist, and excluding the assisting half would
over-apply it.

### The part worth more than the ruling

**The document gave no way to tell.** A founder decision binding every venture was
recorded inside one venture's intake document, under a heading referring to "Pack Section
3". Nothing about its placement, its wording or its surroundings distinguishes it from a
Burkham marketing rule — and I read it, ruled on a Greenstone Pack with it, and did not
notice the venture had changed. The heading of entry 6 said *"an act Burkham forbids"*
above a finding about a Pack Burkham does not own.

That was a real mistake and it was not a careless one. **There was no signal to miss.**

**A cross-venture decision recorded in one venture's document is findable only by whoever
reads that document.** Everyone else — including anyone writing a second Pack, onboarding a
third Forge, or reviewing a grant — has no reason to open it and no way to know it is
there. The failure mode is silent in both directions: the rule gets applied where it does
not belong, and it fails to be applied where it does.

**What would have made it legible: founder-tier decisions need a home that is not a
venture's Pack or plan.** One document, read by anyone touching any venture, where the
scope is the location. A decision that binds everything cannot live somewhere that
implies it binds one thing, and no amount of careful wording inside a venture document
fixes that — the reader who needs it is the reader who never opens it.

That home does not exist yet. Creating it is not done here, and this entry is the second
item that would go in it.

### The fix, and why it is this one

`voiceforge/place_call` is now in `forge_module_exclusion`.

**That table is the fix because it is the only mechanism on the path that refuses
anything.** Proven the same day rather than argued: a grant over `voiceforge/place_call`
was inserted in a rolled-back transaction and **succeeded**, with V6 passing, V32 never
asking voiceforge, and V31 answering NOT_RUN. After the row:

```
voiceforge/place_call:      REFUSED - module place_call on forge voiceforge is
                            excluded and cannot be granted: forbidden: a founder
                            decision binds every venture ...
voiceforge/transcribe_call: INSERT SUCCEEDED
```

### `forbidden` is a fourth kind of exclusion, and the distinction matters

`module_exclusions.py` recorded three shapes — `inert`, `stubbed`, `refuses` — all of them
findings about an implementation that does not do its job. Each names the evidence that
would retire it: the stub is replaced, the runner is built, the 501 becomes a 200.

**A `forbidden` exclusion has no such evidence.** The act is prohibited whether or not the
module works, and building the capability is precisely the case it exists for. The header
now says so, because the table's own instruction is *"Remove the row only with the evidence
that it no longer applies"* — and under the first three shapes, working code is that
evidence.

### What the ruling reaches, checked rather than assumed

Every module in every registry, against the act §3.4 forbids:

| | |
|---|---|
| `voiceforge/place_call` | **forbidden** — row added |
| `voiceforge/transcribe_call` | expressly permitted |
| the other 18 registry modules | none initiates a call |

**One row, as expected.** But the check found something outside the registries that is not
settled by it.

### Open: four CapitalForge modules excluded for a reason that expires

`capitalforge/voice_call_initiate`, `voice_call_end`, `outreach_apr_expiry` and
`outreach_restack` are already excluded — every one as **`stubbed`**, on the evidence that
`VoiceForgeService` uses a `TwilioStubClient` that dials nobody. They are not in any
registry yet, so no grant is possible today.

**Their acts are what §3.4 forbids, and their recorded reason is that they do not work.**
The real Twilio client exists in that codebase and is imported by the SMS path. The day
somebody wires it to the voice path, the `stubbed` evidence stops applying — and the
documented, correct procedure is to remove the row. Someone following the process exactly
would re-open a forbidden act, and the exclusion would have done its job right up to the
moment it mattered.

`voice_call_end` is the ambiguous one: terminating a call is not initiating one, and
whether it is reached depends on whose call it ends.

**Not changed here.** Amending those reasons rewrites recorded findings with source
citations behind them, and `voice_call_end` needs a ruling of its own. Reported rather than
done.

## 20. Three CapitalForge voice modules become `forbidden`; `voice_call_end` gets a question

**Ruled 2026-09-07**, applying entry 19's founder-tier ruling to what entry 19 reported
and did not settle.

### The three

`voice_call_initiate`, `outreach_apr_expiry` and `outreach_restack` initiate outbound
calls as principal. §3.4 covers them, and the ruling reaches them.

**Their reason changes shape; the original finding is kept.** Each row now says both:
forbidden by §3.4, **and** separately recorded as stubbed when it was first excluded.

That is not belt-and-braces. **Losing the stub finding would lose why anyone looked.**
The 1 September reconnaissance is what surfaced these modules at all — somebody read
`services/voiceforge.service.ts` and found a `TwilioStubClient` declared inside the
service, and that reading is the provenance of the whole exclusion list. A row that said
only *forbidden* would be correct and would have no history.

**And the trap entry 19 named is now closed.** The stub reason expires: the production
Twilio client exists in that codebase and the SMS path already imports it, so wiring the
voice path is an afternoon's work. Under the old rows, the table's own instruction —
*"remove the row only with the evidence that it no longer applies"* — would have had
somebody correctly delete all three the day it was wired. Now the evidence retires the
second reason and not the first, and the rows say so in those words.

### `voice_call_end` stays `stubbed`, and carries a question

**Ending a call is not initiating one.** §3.4 bans initiating as principal, and applying
it here by inference would over-apply a founder ruling to an act it does not name.

**The question, recorded and deliberately not answered:**

> If no agent may start a call, what act does this end?

Either it is dead alongside `voice_call_initiate` — a control for calls that can no longer
exist — or there is a case nobody has written down: a human's call an agent is assisting
on, where ending it is part of the assistance §3.4 expressly permits. **Those are
different modules with the same name**, and which one it is decides whether the row
becomes `forbidden` or whether the module needs a described purpose.

Deciding it by inference goes wrong in both directions: guess forbidden and a permitted
assisting capability is banned by implication; guess permitted and a call-control module
sits grantable with no stated reason to exist. The question is in the exclusion row where
whoever next reads it will find it.

### `place_call`: the exclusion is the instruction

Added to its row, so nobody authors one later:

> **NO OPERATING INSTRUCTION IS TO BE AUTHORED FOR THIS MODULE. This row is its
> instruction.**

The eight required sections ask for the correct sequence, the failure signatures and the
retry-vs-escalate rule **of an act no agent may perform**. Writing them produces a manual
teaching how to do a prohibited thing, and its content hash would then bind a
certification to it. The instruction it has today is placeholder text shared with five
other modules; **that placeholder should be removed, not completed.**

`transcribe_call` is permitted and waits on a VoiceForge adapter — there is no dispatch
map to write a manual against, which is the material every CapitalForge manual was written
from.


## 21. No ninth instruction section for rate limiting

**Ruled 2026-09-07**, while mapping the eight `REQUIRED_SECTIONS` onto SimForge's seven
authorable scenario classes.

### The ruling

**`rate_limited` gets no section.** SimForge's operation curriculum has a `rate_limited`
scenario class and nothing in a Forge Operating Instruction supplies material for it. The
obvious move is a ninth required section; it is refused.

**Two reasons, and the second is the one that decides it.**

It would void every content hash. `content_hash` is computed over the whole content
object, a certification binds to it, and SimForge voids a run whose hash does not match —
*"never softened to a warning"*. Adding a section rewrites all nineteen live instructions
and decertifies everything bound to them. That is a cost, and today it is survivable:
**zero certifications are bound to any live hash** (the three that exist are already
`stale_instructions` against superseded ones). So this reason alone would not settle it.

**It would be authored to satisfy a class rather than because anyone found something
missing.** One of nineteen live instructions mentions anything rate-limit-shaped —
`voiceforge/transcribe_call`, on `429` and backoff. Eleven CapitalForge manuals were
written from source by an author reading each module's code, and not one of them found
rate limiting worth teaching.

**That is a fact about these modules, not a gap in the template.** A section added now
would be filled, per module, by people with nothing to say — which produces exactly the
padding the `correct_sequence` rules were written to stop: *"a thin section is a fact
about the module, not a gap to fill, and padding it is what produces the next failure."*

### What it costs — corrected 2026-09-07, the same day

**The first version of this section said the cost was a refusal. It is not.** Recorded as
a correction rather than an edit, because the ruling survives and the reason it is
acceptable does not — and a reader who took the original at face value would be waiting
for something red that never appears.

**`rate_limited` is unauthorable for every module until one actually has rate-limiting
behaviour worth teaching.** Not hard to author — impossible to author honestly, because
there is nothing to describe. That part was right.

**What follows from it is a cap, not a rejection.** `validate_curriculum_submission`
rejects only its named violations and a missing non-mandatory class is not among them.
The classification is a separate function:

```python
def classify_certification_level(classes_present):
    """A module is certifiable only if EVERY scenario class is present. A module tested
    only on happy_path (or missing any class) is "demonstrated", never "certified"."""
    return "certified" if set(ALL_SCENARIO_CLASSES) <= present else "demonstrated"
```

and the validator's own docstring draws the line: *"Not a rejection (a LABEL): a module
missing some non-mandatory class → demonstrated."*

**So the submission is accepted, nothing fails, and every module stays at `demonstrated`
forever.** `escalation_required` is the hard rejection — that is B16, and it is a
different problem. `rate_limited` is a label that quietly lowers a ceiling.

**Corrected statement of what we are accepting: a silent cap we have recorded, over a
section authored to lift it.**

**A silent permanent cap is worse than a refusal in the one way that matters: nothing goes
red, so nobody fixes it.** A refusal announces itself every time it happens and eventually
somebody acts on it. A cap is a value in a field on a response nobody reads, and it holds
for as long as the system runs.

That is an argument for recording it, not against the ruling. **The fix for the cap is a
module that genuinely rate-limits** — nineteen invented sections would lift the label
without changing anything an agent knows, which is a worse outcome than the cap: a
`certified` earned by describing behaviour that does not exist.

### What changes it

A module that genuinely rate-limits. Then one manual has something to say, the section is
added because an author found it missing, and the ninth section arrives with content
rather than with a schema change looking for some.

### Where the cap should be legible — named, not built

Eleven modules sitting below `certified` forever, for a class no manual has material for,
is a fact somebody should be able to see without reading this entry. Three places, in the
order they would have to be done, because the first is a precondition for the other two.

**1. `broker/simforge_response_manifest.json`, under `submit_curriculum`.** The cap
cannot reach The Office at all today. SimForge's `/office` adapter returns
`{accepted, module_levels, coverage_declaration, gate_9_5_flag}`; the manifest declares
`{run_ref, accepted, scenario_count, coverage_denominator, rejected_reason}`. So
**`module_levels` — the field that carries the cap — is undeclared, and `validate_response`
would refuse the response for containing it.** Adding it is exactly the reviewable act
that manifest exists to force, and the question it asks has a clear answer: the field is a
module id mapped to one of two fixed words and can carry no scenario content.

**2. `curriculum_submission`, beside `simforge_run_ref`.** The table records what was
handed over and holds nothing about what came back. A `module_level` column makes the cap
durable and queryable rather than a value that existed once in a response. **This is
`simforge_run_ref`'s own shape — see docs/blocking.md B8 — so adding the column without
the code that populates and reads it would repeat that defect exactly.** Column, writer
and reader in one change or not at all.

**3. The console's instruction page, `/instructions/{forge}/{module}`.** Where the cap
should be *read*, because it is where somebody deciding whether to author more looks.
Today that page shows curriculum quality, which says the manual is good. A manual assessed
`complete` and nonetheless capped at `demonstrated`, with the class responsible named, is
the one screen where both facts sit together — and the only place the difference between
"this manual is thin" and "this manual is finished and the ceiling is elsewhere" is
visible.

**Not built here.** Item 1 is a manifest change carrying a boundary question, item 2 is a
migration with two pieces of code attached, item 3 is a page. Naming them is the point: a
cap recorded only in a decision entry is a cap nobody sees, which is the failure this
correction is about.

---

## 22. A state that is honest and invisible accumulates; one that is dishonest and loud misdirects — and they are not the same defect

**Decided 2026-09-08.** Filed as `navigreen311/Capitalforge#92` on the side that owns the
fix. Recorded here because the class is ours and we have been collecting it.

### The instance

An unconfigured CapitalForge Office bridge answers `401 UNAUTHORIZED / "Authentication
token required."` Its own `.env.example` states the intended behaviour: *"When any is
absent the adapter is NOT MOUNTED and `/api/office` 404s, which The Office reads as
'serves no manifest' - the truth."*

The 401 does not come from the bridge. `PUBLIC_API_PATHS` exempts `/^\/office(?:\/|$)/`
from `requireAuth`; `officeBridgeConfigured()` is false so the router is never mounted;
the request falls through to a router mounted at `/` inside `apiRouter` whose
router-level `tenantMiddleware` rejects it at `tenant.middleware.ts:55`.

**The three codes are what separate the readings, and the diagnostic one is the absent
one:**

```
/api/office/_modules                -> 401  UNAUTHORIZED        (neither gate)
/api/office/definitely-not-a-route  -> 401  UNAUTHORIZED        (neither gate)
/api/definitely-not-a-route         -> 401  AUTH_TOKEN_MISSING  (the generic gate)
/api/health                         -> 200
```

`OFFICE_CREDENTIAL_REJECTED` is what a **mounted** bridge returns to an unauthenticated
caller. It never appears. Its absence is the proof that nothing on that side is checking
a credential at all.

### Why this is not the rollup class

The class named at entry 13 and extended through entry 16 is a **summary that drops a
distinction the layer beneath still holds** — the message defect, and its harder sibling
where the distinction was never recorded. Every instance so far has the same moral shape:
**the reader is told less than is true.** Nothing asserted is false. A rollup that says
`3 department(s) have seats` is not lying about which population it counted; it is silent
about it. That silence is why they accumulate — nobody is stopped by one, so nobody
fixes one, and they pile up until a number is acted on.

**This defect is the opposite failure and needs its own name.** The reader is not told
less than is true. **The reader is told something specific and false.** `401
UNAUTHORIZED / "Authentication token required."` is a claim: a credential was presented
or required, and it was not accepted. The truth is that there is no bridge here and no
credential is being checked by anyone. The response does not omit the cause — it names a
different one, confidently, in a well-formed error envelope with a code.

**The costs run opposite ways.**

| | honest and invisible | dishonest and loud |
|---|---|---|
| what the reader is told | less than is true | a specific wrong cause |
| how it is found | someone acts on the number | someone acts on the message |
| what it costs | accumulates quietly, unbounded | one wrong investigation, immediately |
| why it survives | nobody is stopped by it | it looks like a finished answer |

A quiet defect wastes the time of whoever eventually trips on it. **A loud one spends
somebody's time on the wrong question the first time it is read, and it spends it
efficiently, because a specific error is exactly what a careful person follows.** This one
cost the morning of 8 September: the whole of it went to tracing where
`CAPITALFORGE_TOKEN` comes from and what value belongs in it, because a 401 said a
credential was the subject. No value exists on either side. The question was wrong and the
error is why it was asked.

### The test that separates them

Both classes are found by reading the layer beneath. The question differs:

- **Rollup class:** *is the distinction present underneath?* Present → message defect,
  fix is a sentence. Absent → signal defect, fix is a schema.
- **This class:** *does the responder that produced this actually know the thing it is
  asserting?* `tenantMiddleware` asserts that a credential was required. It does not know
  whether a bridge exists — it was never asked, and it answers for paths it was never
  meant to see.

**A wrong answer from a component that was not asked the question.** That is the
compressed form, and it is worth carrying: the middleware is not buggy. It did its job on
a request that should never have reached it.

### What this does not license

**Not a rule that every 401 must be audited.** The generic gate returning
`AUTH_TOKEN_MISSING` on an unknown path is correct — that path does require a token.

The property worth holding, and it is narrow: **where a surface has two distinguishable
absent states — not configured, and configured-but-refused — they must not return the same
status.** Collapsing them is what turns a missing configuration into a credential hunt.
Every Forge adapter has exactly these two states, `docs/forge-adapter.md` is the guide for
the seven remaining, and this is now a thing that guide has to say.

### Where this leaves the entry that found it

Entry 3's 2026-09-08 correction records the same defect as the reason its own
CapitalForge half was described one layer too shallow for a third time. That is not a
coincidence: **an error that names a wrong cause produces documentation that names a wrong
cause.** The 401 is upstream of the mis-description, not parallel to it.
