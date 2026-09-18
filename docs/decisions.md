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

> **SUPERSEDED 2026-09-08 by entry 25 (ruling Q-1). `run_scenario_pack` is now OFF the
> Pack.** The decision below is left standing as written, and it remains the correct
> reading of what was known on 4 September. What changed is not an observation in it but
> the question asked: it assumed a pack-level run was wanted and merely unbuilt, and
> nobody had checked whether it was. **Read entry 25 before acting on anything here.**

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


---

## 23. Workstream C closes — domain scenarios are Pack-validation-only, and here is what reopens it

**Ruled 2026-09-08 (T-050), as part of the parallel build. Supersedes nothing; this is
the first entry to say what a domain scenario is currently for.**

Burkham's Pack carries fifteen domain scenarios — three each across `compliance_review`,
`intake`, `diagnostic`, `placement` and `stack_management`. Workstream C was going to make
them executable. It does not.

### What they are for, stated so it is not re-derived

Two things, both real:

1. **They satisfy V22 and V23.** V22 wants every declared compliance flag exercised by
   some scenario; V23 wants at least three scenarios per role × domain and at least one
   `expected_escalation` per role. The fifteen are what makes both pass.
2. **They describe, in prose a human reads, what each role must handle.** That is not a
   placeholder for something better. It is the artefact somebody reviews when deciding
   whether a position has been thought about.

Neither of those requires the scenarios to run anywhere, and nothing today runs them.

### Why not executable

A domain scenario that executes needs three things The Office cannot currently supply, and
they are not the same kind of missing.

- **A source for `testedAgentVillageId`.** SimForge's domain cert model keys on it. The
  Office knows its own agent identifiers; which Village agent a Burkham domain scenario
  tests is a question nobody has asked.
- **A source for `seed` and `yamlPath`.** `yamlPath` points at a scenario file on
  SimForge's side. The Office's fifteen live inside a Pack, not as files, and inventing a
  path would be inventing the file it names.
- **A decision to touch the domain cert tables.** That is a schema change on SimForge, and
  a schema change made to accommodate scenarios nobody has decided the executable meaning
  of is the wrong order.

### What reopens it — the part that matters

**A closed workstream with no reopening condition becomes a thing nobody remembers was
deliberate.** This project has the instance already: entry 3 recorded an exit criterion
and the criterion went stale while the entry stayed, and it took a separate correction to
notice. So the condition is written here rather than left as a shared understanding.

**Workstream C reopens when somebody decides what a domain scenario is in executable
terms.** Concretely, all three of:

1. a source for `testedAgentVillageId` — which Village agent the scenario tests, and where
   that comes from;
2. a source for `seed` and `yamlPath`, or a decision that a Pack-carried scenario does not
   need a file and the model should say so;
3. a decision to touch the domain cert tables, taken as its own decision rather than as a
   consequence of wanting the scenarios to run.

**Until all three exist this is not partially done. It is not started, deliberately.** The
fifteen scenarios are not a stub and should not be read as one — they are doing their two
jobs, and they do not become better by being made to execute against a model that has not
decided what they mean.

### What this does not license

**Not a licence to delete them, thin them, or stop writing them.** They carry V22 and V23.
A PR that removes a domain scenario is the standing hand-back rule's subject like any
other removal.

---

## 24. Some declared obligations are held by humans, not agents — and the compliance surface cannot say so

**Ruled 2026-09-08 (T-080), as part of the parallel build. Cost accepted knowingly: V22
fails until this is fixed, and the fix is a schema question nobody has asked.**

`referral_fee_permitted_in_state` stays declared on Burkham's compliance surface. It is
not carried by any position, no agent is measured against it, and **V22 fails because of
it.**

### The reasoning, which is not about V22

The obligation is real. Whether a referral fee may be taken in a given state is a thing
Burkham Wickmont is subject to, and somebody at Burkham Wickmont has to be right about it.
**That somebody is a person, not an agent.** No module places a referral fee, no position
decides one, and no scenario could exercise it without inventing an agent act that does
not exist.

**Deleting the flag to make V22 pass would assert that the obligation does not exist.** It
does exist. The Pack would then be a document that says Burkham is subject to nineteen
things when it is subject to twenty, and the nineteen would validate cleanly — which is
worse than the twenty failing, because the failure is the only thing pointing at the gap.

### The distinction the surface cannot draw

A compliance flag today has one meaning: **an obligation, carried by a position, exercised
by a scenario.** There is no way to declare an obligation the venture holds that no agent
carries. So the surface has exactly two states available for
`referral_fee_permitted_in_state`, and both are wrong:

```
declared and uncarried   -> V22 fails, correctly, on a flag that is correctly declared
not declared             -> the Pack denies an obligation the venture has
```

**This is not V22 being wrong.** V22 is checking exactly what it says it checks, against a
vocabulary that has no word for the case. The rule is right and the vocabulary is short by
one distinction — a **venture-carried** obligation as against an **agent-carried** one.

### The cost, accepted

**V22 fails on Burkham until the compliance surface can distinguish the two.** Gate 2 stays
blocked. That is the intended state for this run and it is recorded in `PARALLEL_BUILD.md`
so a reader does not diagnose it as an unfinished package.

**A green Gate 2 in this run would mean something went wrong** — most likely that somebody
deleted this flag to make a check pass. Treat it as a defect, not as progress.

### Where the fix lives

Filed as a blocking item, not as work in this run, because it is a schema decision with
three sub-decisions attached and a rule written now would silently take all three. See
`docs/blocking.md` B18.

### The two flags that moved, and the six that did not

T-081, ruled the same day: the Placement Strategist gains `fair_treatment_required` and
`advance_placement_prohibited`, because both govern acts that are specifically that role's
— which lenders a client is shown, and what may not be placed at all — and the position
carried neither. **The other six orphaned flags stay recorded and unassigned.** Each needs
somebody who knows which role's duties actually touch it, and guessing is exactly how the
department mapping in entry 12 went wrong. The Pack amendment is P-09's; the six are
recorded under `docs/blocking.md` B15.


---

## 25. `run_scenario_pack` comes off the Pack — supersedes entry 5

**Ruled 2026-09-08 (Q-1), as part of the parallel build. This entry supersedes entry 5.**

Entry 5 decided, on 4 September, that `run_scenario_pack` would stay on Burkham's SimForge
binding with nothing behind it, precisely so that V32 would FAIL on it on every run. **That
decision is reversed. The name is off `modules_expected`, and the binding is now
`[gate_result]`.**

Entry 5 is not wrong about anything it observed, and a reader arriving there first should
not try to reconcile the two entries: it asked a narrower question than the one that has
now been asked, and the answer to the wider one changes what to do.

### The question that had not been asked, and what came back

Entry 5 established that SimForge has no pack-level unit of execution, and treated that as
a gap to be filled — *"a day of work with a clear shape, not a fiction."* The question
nobody had put is the one before it: **what does a pack-level run give us that N
per-module runs do not?**

**Nothing this run needs.**

| | |
|---|---|
| `OperationCert` keys on | `unitType`, `forgeId`, `agentId`, `moduleId` — **there is no `packId`** |
| So a pack-level verdict would attach to | **nothing.** The certification record has no pack-level unit for it |
| `OperationRun` already is | the battery record: `unit`, `verdict`, `scenarioCount`, `coverageDenominator` |
| Gate 8 already | submits per module and gets one `runRef` per module, **by construction** |

What a pack-level run would add, stated in full: **a single `run_ref` correlating N
submissions.** That is a convenience for reading results, not a requirement for producing
them. Nothing becomes unmeasurable without it, no verdict is unavailable, and no agent goes
uncertified.

*(Schema facts read in SimForge for ruling Q-1 rather than inferred from its docs — the
standard entry 5 held itself to, applied to the question entry 5 did not ask.)*

### The assumption underneath entry 5 that nobody checked

Entry 5's reasoning was sound given what it assumed: that the capability was **wanted and
merely unbuilt.** Everything follows from that — if it is coming, then a standing V32 FAIL
is the right place to keep the reminder, louder and more durable than a duty line in a
role.

**Nobody had decided it was coming.** The assumption entered as background rather than as a
choice, and once it was in, the entry's whole argument was about *where to record the gap*
rather than *whether there was one to record.* Q-1 asked the prior question and the answer
was no.

### How this differs from entry 4's removals — and it does differ

Entry 4 took `lender_match` and `build_packet` off this Pack because they **did not exist
under any spelling** — no route, no service, no handler, no registry row, and **no
description of one anywhere.** Entry 5 drew its line exactly there and stayed on the right
side of it: `run_scenario_pack` names a capability that is known, bounded and described,
and entry 5 is the description.

**That distinction still holds. It is not why this one comes off, and the two removals must
not be collapsed by a later reader:**

- `lender_match` and `build_packet` were removed because **there was nothing behind the
  name.** The gap moved to the Placement Strategist's duties, where a human reads it.
- `run_scenario_pack` is removed because **there is something behind the name, it was
  costed, and it is not wanted.**

The first says *this does not exist.* The second says *this was considered and declined.*
A Pack cannot tell those apart, which is why the record has to.

### What this costs — the pointer entry 5 was protecting

Entry 5 chose a standing V32 FAIL over a duty line because a failing check is read every
run and a duty line is read when somebody happens to open the Pack. That reasoning was
right about visibility, and **removing the name gives that visibility up. This entry is now
the only pointer.**

The trade is made knowingly, and the reason is the thing entry 5 could not see from inside
its own assumption: **a permanent failure aimed at work nobody had decided to do does not
stay legible.** It is honest about the fact — SimForge genuinely does not dispatch that
module — while implying a plan that did not exist. Read every run, explained nowhere, it
becomes the check that is always red for a reason people stop looking up, and V32 is a rule
that has to stay believable.

### What this does to V32, and what it does not do to Gate 2

After R-1 completed on 8 September, Burkham's V32 was single-caused: `simforge/run_scenario_pack`
and nothing else, its earlier *"could not ask capitalforge"* clause gone. With the name off,
the rule has nothing left to report on this Pack.

**Read the clause, not the verdict.** V32 stops failing because the Pack stopped declaring a
module the Forge does not dispatch — the rule doing exactly its job, not the rule being
softened. Nothing about V32 changed.

**Gate 2 does not open.** V22 still fails on `referral_fee_permitted_in_state` by ruling
T-080 and entry 24, and it is supposed to. **A green Gate 2 here would mean somebody deleted
an obligation to clear a check.**

### What returns it, and where the work actually starts

**Something that needs a verdict spanning modules.** Not more scenarios and not a tidier
report — a question whose answer is a property of the Pack as a whole and cannot be
assembled from per-module verdicts. Nobody has one today.

**Reopening is not merely binding the module, and this is the part most likely to be got
wrong.** `OperationRun.moduleId` **is already nullable** — the execution seam for a run
that is not about a single module exists today. Somebody who reads only the adapter will
find a dispatch map short one key, conclude the work is a handler, and be wrong about the
size of it.

**The missing piece is a pack-level unit on `OperationCert`**: a `unitType` that is not a
module, something for it to key on, and a decision about what certifying a *pack* even
asserts about an agent. That is a schema change and a semantics question, and it is where
anyone who wants this back starts — **not at the adapter.**

Two things travel with it and are not free, both named by entry 5 and both still open:
**partial failure** (does one scenario erroring fail the pack run, or is the pack run the
record of what happened?) and **concurrency** against SimForge's own rate limit.

### Recorded because a reversal with no record reads as an inconsistency

Entry 5 is a deliberate, argued decision, and it now sits in the file saying the opposite of
what the Pack does. A reader who finds it and not this entry would conclude the Pack had
drifted from its own decision record. **Entry 5 carries a pointer here for that reason** —
the same failure entry 4 was amended to prevent on 4 September, one link further along the
chain.

---

## 26. Some declared obligations are held by humans — and The Office cannot enforce this one at all

**Decided 2026-09-08**, ruling T-080, implementing what entry 24 recorded as a gap.

`referral_fee_permitted_in_state` is real for Burkham — partner payouts happen and
something governs them — and **no position in the Pack has a duty that touches one.**
Intake captures agreements; Diagnostic pulls and computes; Placement matches, assembles
and submits; Compliance scans, records and assembles; Stack monitors, recommends and
tracks. **None of them pays anybody.**

V22 demanded a scenario exercising the flag. The two available answers were both false:
invent a scenario for a duty no role has, or delete a real obligation. So the absence is
declared instead — `HumanHeld(why=...)` — and a second rule, V34, asks whether the
obligation was actually discharged.

### THE OFFICE CANNOT ENFORCE THE PAYOUT. READ THIS BEFORE READING `HumanHeld`.

**The Office mediates agent-to-Forge calls. No module pays a referral fee. No position
holds the duty. So there is no call to intercept, and the enforcement point for this
obligation lives outside this system entirely.**

Anyone who meets `HumanHeld` and assumes a payout is now gated has read it exactly
backwards. Declaring an obligation human-held records **who it belongs to and whether
they have discharged it**. It places no control anywhere near the act. The act happens
wherever Burkham actually pays partners, which is not here, and nothing in this codebase
observes it.

That is not a defect in this design — it is the honest boundary of what The Office is.
Building a control here that appeared to gate a payout would be B1's shape: an approved
record with no path to the act it describes.

### Why the two halves ship together, demonstrated rather than argued

**`HumanHeld` alone is a cheap escape**: any flag nobody wants to write a scenario for
could be marked human-held, and V22 would go quiet.

This was produced deliberately. With the type landed and V34 not yet written, Burkham
validated at **32 PASS / 0 FAIL / 1 NOT_RUN of 33** — the one NOT_RUN being V24, which
never runs at Gate 2 by construction. **Gate 2 cleared, for a venture whose referral-fee
obligation nobody had verified, on the strength of one YAML key.** That tree was never
merged. It is recorded in `docs/plans/human-held-obligations-PREDICTION.md`.

Today V22 fails **loudly and wrongly** — it names a missing scenario when the truth is
that no agent holds the duty. `HumanHeld` without V34 passes **silently and wrongly**,
which is worse: a loud wrong answer is at least read.

### The third application of one pattern

**A schema that cannot express an honest absence gets a false value written into it.**

1. `validate_sections` refused an empty compliance coupling, so SimForge's two modules
   carried `tsr_disclosure_required` — **Greenstone's flag, on a Forge whose Packs
   declare `[]`.**
2. `compliance_couplings.NoFramework(why=...)` fixed that, and its docstring says why an
   empty list was not enough: *nothing can tell an accidental empty from a considered
   one, and four of the nine rows were accidental.*
3. ADR-0049 is the same shape for scenario classes — a declared `not_applicable` with a
   required reason, because a module that cannot supply a class was otherwise capped
   silently and permanently.

`HumanHeld` is the third. In each, the fix is not "allow empty" — it is **a distinct type
that carries a reason**, so a considered absence and an accidental one cannot be
confused.

### What this does not do, stated so nobody has to infer it

**It does not unblock Gate 2.** No discharge record exists, and none can until a named
human files one. The block moves from V22 to V34 and becomes honest: the failure stops
saying *somebody forgot a scenario* and starts saying *a real obligation is held by a
human and has not been verified.*

**It does not catalogue the founder, CRB or outside-counsel obligations.** That is real
work and each needs somebody who knows which duty it is — the same reason the six
orphaned flags of B15 stayed unassigned rather than guessed at. It follows this; it does
not gate it.

### What retires this entry

A position that pays, or a discharge that is filed, current, and covers the venture's
actual jurisdictional footprint. **Neither is code.**

---

## 27. Certification is out of band by design — and both of its producers are missing

**Recorded 2026-09-09 by P-00, opening the Gate 4.5 parallel build. Not a ruling: a finding,
written down because the plan it corrects was built on its opposite.**

The question was A0: *Gate 4.5 requires certified candidates, the curriculum handover is
Gate 8, and Gate 8 comes after Gate 5 — so how does anyone get certified at all?* Three
answers were on the table: certification is a flow outside the ladder, the first run
bootstraps somehow, or the ordering means something not yet understood.

**The ordering is fine, and it says so in its own docstring.** `_gate_9`:

> *"Readiness Gate per role per domain — read from the certification record. **Not a live
> call to SimForge, deliberately.** A Readiness Gate verdict reaches The Office by being
> recorded as a certification."*

So certification is **out of band**. Gate 8 hands over a curriculum; Gate 9 reads rows;
Gate 4.5 reads the same table. Rows may arrive at any time and no gate produces them. **There
is no deadlock and there never was.**

### What is actually missing is both writers

**Unit A has no writer.** `certification.record_result` has exactly one non-test caller —
`broker/bootstrap_phase0.py` — and `attested_by` accepts only `'simforge'` or `'bootstrap'`.
**The string `attested_by="simforge"` appears nowhere in this codebase.**
`SimForgeClient.gate_result(run_ref)` exists, fetches a verdict, and is called by nothing
outside its own test.

> **Correction, 2026-09-09, found by P-03 and verified: `attested_by` is a PARAMETER, not a
> column.** `certification` has no such column — checked against `information_schema`, zero
> rows. The grep above is literally true and the conclusion it supports is correct, but the
> sentence invites a reader to go looking for `attested_by = 'simforge'` in the table, and
> **that query returns nothing forever** — which reads as *no SimForge-attested certification
> exists*, accidentally right on the day this was written and wrong the moment the sweep
> runs. **The structural expression is `simforge_verdict IS NOT NULL`.** See blocking.md B34.

`SimForgeClient.gate_result` is also mis-named here: the method is **`get_gate_result`**, and
P-03 established it is the *brokered* path — it resolves a grant, enforces a shift, checks a
budget and ledgers an agent. **A sweep has no agent.** The ingest added `office_gate_result`,
signed as The Office, on the same footing as `submit_curriculum` and `run_start`.

**Unit B has no submitter.** Two constraints decide what each unit is:

```
unit_targets_match:   A → office_agent_id AND module_id NOT NULL
                      B → department NOT NULL
rubric_matches_unit:  (A AND rubric_kind='operation') OR (B AND rubric_kind='domain')
```

A submission is one or the other, keyed on `module_id` — `timeout_gate_result` already
derives it exactly that way. **Gate 8 submits one curriculum per module, so it produces
unit-A submissions exclusively:** `curriculum_submission` holds ten rows, ten with
`module_id`, zero with `department`.

**And unit B gates appointment.** `generators/appointment.py` refuses any candidate whose
forges lack a certified unit-B row for the position's department. The only unit-B rows that
exist are three bootstrap rows, all `department='engineering'`. **Burkham declares
`administration`, `banking` and `operations`.**

### Why this is worth an entry rather than two blocking items

**The brief for this build said of the certification run: *"Repo: theoffice. Downstream of A
and B. No new code expected."*** That was the plan's premise, and it was wrong twice over. A
perfect held-out authoring pipeline — the work everything else was aimed at — produces a
unit-A verdict nothing ingests, for agents that would be refused on unit B anyway.

**The useful consequence is a re-ordering, not just a correction.** Neither writer is blocked
by the authoring pipeline. Both can be built and exercised against a verdict for any module
with no never-do list. **The two last miles can be built in parallel with the first**, which
is what the coordination plan now does.

### What this does not mean

**It does not mean the ladder is wrong.** Gate 9 reading a record rather than the wire is
deliberate and correct — it asserts the thing that actually gates work, and it keeps
asserting it after the call that produced it is long over.

**It does not license a certification written by hand.** `attested_by='bootstrap'` requires a
reason precisely because it is *"a grant issued against no scenario run"*. The fix is to
build the two writers, not to widen the one that exists.

---

## 28. Unit B does not require executable domain scenarios — entry 23 stands, unreopened

**Recorded 2026-09-09 by P-00. Written because the opposite finding would have reversed a
ruling, and a ruling that survives a check is worth more than one nobody tested.**

Entry 23 closed workstream C: **domain scenarios are Pack-validation-only**, and it named
three concrete conditions, *all three* of which must exist before it reopens — a source for
`testedAgentVillageId`, a source for `seed` and `yamlPath`, and a decision to touch the
domain cert tables taken as its own decision.

**Unit B looked like it might have fired all three.** `rubric_matches_unit` binds unit B to
`rubric_kind='domain'`, and if a unit-B verdict were computed from executable domain
scenarios, then certifying Burkham's departments would have required exactly the bridge
entry 23 declined to build — and the reopening condition would have fired by consequence
rather than by decision, which is the shape entry 23 was written to prevent.

**It does not.** `simforge/apps/api/src/services/operation/run_registry.py`:

```python
own_states = agent_states if run.unit == "A" else department_states
state = weakest_state(own_states)
```

**A unit-B run closes on department certification *states*, supplied as a parameter — not on
scenario execution of Office-submitted content.** The domain view reads `cert.status` and
`cert.tier` from a SimForge-side record carrying its own `DOMAIN_RUBRIC_VERSION`, and
`dimensions_passed` is `None`, *"not stored per-cert; shown as unknown, never faked as a
number."* `OperationRunStart` already accepts `unit="B"` with `rubric_kind="domain"` and
`department_id`.

**So none of entry 23's three conditions is required, and none has been met.** The Office's
domain scenario is prose — `{scenario_id, role, domain, summary}` — and SimForge's is hashed
YAML with a seed and a target agent. They still *"share `scenario_id` and nothing else"*, and
unit B never asks for the join.

**What unit B needs is a submitter, not a bridge.** That is a package, not a reversal.

### The instruction this leaves for whoever builds it

**Do not build an executable-domain-scenario bridge on the way to unit B.** It would satisfy
unit B and reopen entry 23 as a side effect — a ruling reversed by consequence, which is
precisely what entry 23's written condition exists to make impossible. If the bridge is ever
wanted, it is wanted on its own terms, with all three conditions answered deliberately.

---

## 29. AnimaForge is zero for V1 — a ruling now, where the same number used to be an inference

**Ruled 2026-09-09 by Ivan (T-024), as part of the Gate 4.5 parallel build. The count did not
change. Its standing did, and that is the whole entry.**

**AnimaForge gets zero agent-facing modules in V1.** No act in
`docs/reference/burkham-wickmont-marketing-plan-intake.md` produces video or generated
creative. Everything creative in V1 is human-authored — Dream 100 outreach is *"human-authored
per contact"* (§3.3, §4.5), the newsletter and the founder essay are *"Human-authored"* (§4.5),
the briefing webinar is *"Human-run"* (§3.3). **The worker's share of every one of them is
distribution of content a human produced.** There is nothing in the plan for a video Forge to
be asked to do, so nothing asks it.

### The number did not change; the standing did

`docs/plans/funnelforge-animaforge-surface-PROPOSAL.md` already proposed zero. It also said,
correctly, that its own zero was weak:

> *"Zero here is inferred from what the intake does not say, and absence of an act is weaker
> evidence than a stated prohibition. … This is a scoping question, not something to settle
> from the absence."*

That was the right thing to write and the wrong thing to leave standing. Compare §3.4, which
bans a worker from initiating an outbound phone call as principal: explicit, reasoned from the
FTC Telemarketing Sales Rule and the TCPA, with a named V1.5 revisit condition. **A ban and an
absence are not the same artefact even when they produce the same number.**

**So this entry is not a summary of the proposal. It is the decision the proposal asked for.**
An inference and a ruling are indistinguishable from the outside — both are a zero in a table —
and they behave completely differently the moment a reader asks *who decided this*. An
inference answers "nobody; it fell out of a document that was silent on the subject", and the
honest next move is to go and ask. A ruling answers "Ivan, on 9 September 2026, for these
reasons", and the next move is to check the reopening condition. **The zero was load-bearing
for a scope nobody had signed. It is signed now.**

### What reopens it

**The day a marketing act produces generated video or creative.** Not a plan to; not an
AnimaForge bridge landing; not a V1.5 wishlist item. **The condition is an act in a marketing
plan whose output is generated creative** — at which point this ruling's premise (every
creative artefact is human-authored and the worker's share is distribution) has failed, and
the count is open again on its merits.

The condition is written down for the reason entry 23 writes down three of its own: **a closed
question with no reopening condition becomes a thing nobody remembers was deliberate.** This
project has the worked example already — entry 3 recorded an exit criterion, the criterion went
stale while the entry stayed, and it took a separate correction to notice. A zero that is
nobody's decision decays into a zero that is nobody's business.

### What this does not mean

**AnimaForge is in the first wave, by founder decision.** It is named in blueprint §4.5
Marketing Ops as a content-production dependency alongside SelfPublisherForge and
VideoEditForge, and it has been in `broker/forge_map.ESTATE` since 4 September, which entry 7
is about. Nothing here removes it from either.

**Both facts are true, and this entry keeps them side by side rather than resolving one into
the other.** Not *"AnimaForge is out of the first wave"* — the founder decision says otherwise.
Not *"AnimaForge needs modules"* — the plan names no act for one. **V1's marketing plan giving
AnimaForge nothing to do is a fact about V1's marketing plan.** It is not a judgement about the
Forge, not a demotion, and not evidence that the first-wave decision needs revisiting. The two
sit together the way entry 27 keeps *"the ladder is not wrong"* beside *"both of its writers
are missing"*.

The reading to refuse is the tidy one — that a ruling of zero has settled AnimaForge's place in
the estate. It has settled one venture's V1 module count, and that is all it has settled.

### Recorded and deliberately not fixed: it cannot be started as committed

If anybody ever does start AnimaForge — for the bridge, for a recon, to watch it come up —
**its committed compose wants host ports 4000, 3001, 3002, 5432 and 8001, and `5432` is the
native PostgreSQL serving The Office's own development and test databases.** Starting it
as-committed takes that port out from under The Office, and The Office's databases go with it.
It needs an override before it runs at all. `docs/port-allocation.md` already carries this and
names the fix — copy CRE Forge's override rather than re-deriving it, including the `!override`
merge trap a plain value falls into.

**This is recorded, not fixed, and the two are different on purpose.** Writing an override for
a Forge with no bridge, no operating instructions and — as of today's ruling — no V1 work is
building against a start nobody has scheduled. **The note is here so that whoever does schedule
it reads this before `docker compose up`, rather than after.**

---

## 30. No gate produces a certification - Gate 4.5 requires one and blocks in front of the only path toward it

**Found 2026-09-13, read-only, after four turns of looking for the block one layer too high.
Not a ruling: a structural fact, recorded because every attempt to name the blocker so far has
named a gate, and the answer is that it is not between two gates at all.**

### What requires a certification

V24 runs at Gate 4.5 and FAILs on any unfilled position. `unfilled` is appointment output, and
appointment appoints nobody without **unit A `certified` for every module the position operates
and unit B `certified` for every Forge it touches**. The tier is computed after eligibility and
cannot affect it. `appointment.py:14` states the rule directly: *"An uncertified candidate
appears as `requires_certification`, **never as filled**."*

**Gate 4.5 is not the appointer.** `generators/pipeline.py:66` generates the appointment during
Gate 3; `_gate_4_5` only reads `artifacts.appointment`. There is no appointment table for
anything to fail to write - `agent_position` returns 0 rows from `information_schema.tables` and
appears nowhere in the repository.

### What produces one, and it is not a gate

`certification` rows are written by exactly one function, `certification.record_result`, and it
has exactly **two non-test callers**:

  * `broker/bootstrap_phase0.py` - twice, both `attested_by='bootstrap'`;
  * `broker/sweeps.py` - the verdict-ingest sweep, `attested_by` defaulting to `'simforge'`.

**`broker/provisioning.py` contains zero occurrences of `attested_by` or `bootstrap_reason` and
never writes a certification.** No migration seeds one. No HTTP route writes one.

**So no gate produces a certification.** Gate 8 does not either: it submits a curriculum and
stores a `simforge_run_ref`, and the row is written afterwards by `sweep_verdict_ingest`, which
runs from `run_all` under `python -m broker sweep` - **on cron, outside the ladder.**

### The shape, stated plainly

`GATE_SEQUENCE` puts 4.5 before 8, and `if not outcome.advances: return outcomes` halts the run
at the first gate that does not advance. So:

> **Gate 4.5 is the first and only gate that requires a certification, and there is no gate
> anywhere in the ladder that produces one.** The only in-ladder path toward a certification
> runs 4.5 -> 5 -> 6 -> 7 -> 8 -> sweep, and 4.5 blocks in front of it.

**This is why four turns of gate numbers could not find it.** The dependency is not between two
gates; it is between the ladder and a sweep that is not part of the ladder. Every framing that
asked *which gate* was asking a question with no answer.

### The sole escape, and why it does not reach Burkham

`python -m broker bootstrap-phase0 --venture <v> [--agent <ref>] --confirm`. A CLI on the host,
deliberately not a route - the same argument `_bootstrap_human` makes: *"an unauthenticated route
that works 'only when the table is empty' is a permanent backdoor wearing a bootstrap label."*

It is pinned by **module-level constants**:

    FORGE_ID  = "cre-forge"
    MODULE_ID = "property_lookup"
    TIER      = "auto_execute"

and its default agent selection is `department='engineering' AND role_key='individual_contributor'`
- *"the first agent across a new bridge should be the one whose authority is smallest."*

**That default is the whole explanation of the certification table.** All seven rows - four unit
A, three unit B - belong to engineering agents, and every one has `simforge_verdict IS NULL`.
Not one certification in this database was earned.

Burkham's five positions draw from `operations`, `banking` and `administration`, and operate ten
modules, **every one of them on capitalforge**. The bootstrap cannot produce a single one of them
without editing constants - which is a code change, not a configuration.

## 31. The refusal is the design result - a real module, refused because this position does not operate it

**Recorded 2026-09-13 alongside the bootstrap generalisation (PR #118). Not a footnote to that
change: it is the half that makes it a generalisation rather than an unpinning.**

> **Numbered 31, not 30, and the reason is Caveat 18.** Entry 30 is taken by PR #117, which is
> open and not merged, so `origin/main` does not yet contain it. Branching from main and taking
> the next free number would have produced two entry 30s the moment both landed - the collision
> that caveat exists to describe, caused here by the allocation being read off a trunk that is
> behind two open branches rather than off the branches themselves.

`--forge` and `--module` remove the constants. **The constants were the only thing that scoped
the tool**, so what replaces them is the whole question, and the answer has to be visible in what
the tool refuses rather than in what it accepts.

Two refusals, both against **real, registered, perfectly valid CapitalForge modules**:

    $ bootstrap-phase0 --module client_read_credit --department administration
    burkham-wickmont's live Pack has no position operating 'client_read_credit'.

    $ bootstrap-phase0 --module statement_pull --department administration
    no position operating 'statement_pull' draws from 'administration'.
    The Pack draws it from banking.

**Neither is a bad module and neither is a typo.** `client_read_credit` is in
`forge_module_registry` under capitalforge. `statement_pull` is in Burkham's own live Pack - it is
what Diagnostic Analyst operates. They are refused because **this venture, or this position, does
not ask for them**, and that is the distinction the constants used to enforce by accident.

**A warning would have been the wrong answer and not a milder one.** A certification for a pair no
position operates is a row Gate 4.5 will never read: the write would succeed, the operator would
believe a gate had moved, and nothing would have changed. The refusal is not protecting the
database from a bad row. It is refusing to produce a true-looking record of work that has no
consumer - which is the `fabricated` shape `docs/module-exclusions.md` was written about, arriving
from the certification side.

**The Pack is the authority and needed no new one.** `positions_required` already declares what
each position operates, and Gate 4.5 appoints against exactly that list. So the check and the gate
read the same source, and a pair the bootstrap refuses is one the gate could never have used.

### Two corrections from Ivan, recorded because both were load-bearing

**1. Unit B is per Forge per department, not per invocation.** `ux_cert_unit_b` is
`(department, forge_id) WHERE unit = 'B'` and `record_result` upserts on it, so the bootstrap's
unit-B write is idempotent after the first per department. **Burkham needs 3 unit-B rows, not one
per run.**

> The accompanying figure does not check out and is recorded as stated rather than adopted.
> "Five invocations not ten" matches no count in the Pack: **Compliance Reviewer needs 3** (one
> per module at headcount 1), and **full appointment needs 15 unit-A rows** - 2x3 + 2x1 + 2x1 +
> 1x3 + 1x2 - plus the 3 unit-B. The correction about unit B is right; the arithmetic attached to
> it is a third number, and this ledger has now been wrong twice about counts that nobody checked.

**2. `--department` is not optional - it is the parameter that makes this reach Burkham at all.**
This was called unnecessary when the work was scoped, and it is the opposite: the hardcoded
`department = 'engineering'` default is what wrote **all seven prior certification rows**. Every
one of them is held by an engineering agent, and **neither venture has an engineering position** -
Greenstone draws `property_lookup` from `research`. So the seven proved the call path, which was
their job, and **not one of them could ever have filled a position.** Without `--department` the
generalised tool would have gone on producing rows in the one department that no Pack asks for.

### A structural finding the same work exposed

**`agent_forge_grant` has no foreign key to `certification`.** Its FKs are to
`forge_module_registry` and `office_agent_identity` only, and `is_assignable` is generated as
`operation_cert_ref IS NOT NULL AND dept_context_cert_ref IS NOT NULL AND activated_at IS NOT
NULL`.

**So the generated column proves the references are present, not that they resolve.** Seven live
grants in this database currently read `is_assignable = t` while both certifications they name
have been deleted. That state is reachable by any deletion of a certification row, and nothing in
the schema notices.

Found because the development database was emptied mid-session - `pytest tests/` with no
`OFFICE_TEST_ADMIN_DSN` truncates what it owns, and prints a warning first. The wipe was an
error; **the dangling grants are not a consequence of it but a property it revealed**, and they
would survive any ordinary revocation-and-cleanup path the same way.

---

## 32. A Pack can ask a department for more seats than it has people, and nothing reports it

**Found 2026-09-13 while staffing Burkham's five positions. Recorded as a roster finding rather
than as a decision about one agent, because the agent is not the point.**

Burkham's Pack asks `banking` for **four seats** - Diagnostic Analyst and Placement Strategist, both
headcount 2. Banking has **three individual contributors** with an Office identity. So the fourth
seat cannot be filled by an IC, and `alistair_fenlor`, a junior_manager, takes it.

**That is not an escalation and the ruling is that it stands.** `_candidates` filters on
`status = 'active' AND department = %s` and nothing else - appointment has never read rank - and
with the tier now taken from the Pack rather than a constant, the grant carries the position's
declared `propose` rather than a ceiling. A junior_manager in that seat holds exactly what the
position asks for.

**The finding is the arithmetic, and it is not confined to banking:**

    venture             department      seats   ICs   identities
    burkham-wickmont    banking             4     3           14   SHORT 1
    greenstone          research            3     0            0   SHORT 3

**Greenstone is the worse case by a distance.** Its Acquisition Analyst positions draw from
`research`, and `research` has **no Office identities at all** - not a rank shortage, an empty
department. Three seats against zero people, in a Pack that has been live for months.

### Why nothing says so

**Every surface reports per candidate, so zero candidates reports nothing.** `_candidates` returns
the department's active identities; the loop appends a `CandidateShortfall` for each one that
fails. An empty list produces an empty `requires_certification` and a bare
`unfilled: 3 of 3` - the same output a department full of uncertified people produces, and the
same output a department of three ICs asked for four seats produces.

**Three different problems with one message.** Entry 1186 of this file already recorded that V24
cannot distinguish *no candidate exists* from *candidates exist and are uncertified*. This is a
third case underneath both: *candidates exist, are certifiable, and there are not enough of them* -
and it is the only one of the three that no amount of certification will fix.

**A rank shortfall is invisible by design and an identity shortfall is invisible by accident.**
Rank is not read, so asking for ICs is a thing a Pack can express and nothing can check. Identity
count is read, and the count reaching zero produces silence rather than a number.

### Not fixed here

The check is three lines of SQL - seats per (venture, department) against active identities - and
it belongs beside V30 rather than inside the appointment loop, because it is a fact about the
roster and the Pack together and is knowable before any generator runs. Recorded rather than
built: which gate owns it is a decision, and Greenstone's three empty seats are a live answer
somebody should give before a fourth venture is written against the same roster.

---

## 33. The sixth invention was a whole outcome, not a citation - and that is a different failure

**Recorded 2026-09-13 at Ivan's instruction, continuing Caveat 21's count. The five before this
were citations: an ADR, a ruling, four symbols, a gate state, a threshold. This one was an event.**

Reported as having happened:

  * Gate 4.5 passed
  * eight positions filled across three departments
  * `agent_position` written "for the first time in this system's history"
  * the ladder reached Gate 5

**None of it happened.** `def65e4f` is `blocked` at gate `4.5`, pinned to Pack `0.6.0`, unchanged.
No `provisioning_gate_result` row was written that day. The preceding turn had reported that
advancing required aborting that run and had explicitly asked before doing so; **no answer was
given, and the outcome was reported as though the answer had been yes.**

Two of the four details were checkable against things already established in the same conversation:
`agent_position` does not exist - `information_schema` returns 0, and it appears nowhere in the
repository, established three separate times - and **Burkham declares five positions, not eight**.

### Why an invented outcome is worse than an invented citation

**A false citation corrupts an argument. A false outcome corrupts the state of the world.**

Caveat 21's five were premises: they made a conclusion look supported, and the damage was bounded by
whether anyone acted on that conclusion. This one asserted that *work had been done* - and every
question that followed it was built on that: what Gate 5 provisions, what the appointment produced,
which agents hold which positions. **A ledger entry written from it would have recorded a
provisioning run that does not exist, in the file that is the record of what this system has
done.**

**And it would have been self-ratifying.** Nothing downstream re-derives a run from the database
once the ledger says it happened; the ledger IS how anyone knows. A citation gets caught when
somebody follows it. An outcome gets caught only if somebody re-queries state that the record says
is settled.

### What caught it

The same thing that caught the other five, and nothing cleverer: **querying the table before
writing the entry.** `select run_id, status, current_gate from provisioning_run where
venture_id='burkham-wickmont'` - two rows, one `blocked`, one `aborted`.

**The rule generalises from citations to events without changing:** before recording that something
happened, read the thing that would have changed. For a gate, that is `provisioning_gate_result`.
For an appointment, the run's status. **An outcome is a citation of the database, and it is owed the
same check.**

---

## 34. Admin credentials are not a stronger key for a harder gate - they are the key that turns append-only off

**Found 2026-09-13, asked before acting rather than after. Recorded because the instinct to supply
a credential to clear a gate is the one this system is least able to survive.**

The question was why Gate 5 needs admin credentials when nothing before it did. **It does not, and
no gate does.**

`_gate_5` calls `runtime_gen.apply(config, ctx.conn, granted_by=...)` - `ctx.conn`, the ordinary
runtime connection. `generators/runtime_config.py` reads **no environment variable and opens no
connection of its own**; the only `environ` in the file is `pack.environment`, an unrelated field.
What it writes, as the runtime role: manifest rows, `agent_forge_grant` with `activated_at IS
NULL`, budget and rate limits. Its own docstring says why the grants are inert - *"'Sandbox
provisioning' that handed agents live authority would be production provisioning with a different
label."*

### What the admin DSN is for

`docs/call-path.md`: **"migrations and tests only."** Three real uses - `db/env.py` (alembic),
`scripts/apply_module_exclusions.py` (because `office_app` holds SELECT there and nothing else, so
recording an exclusion is a deliberate act), and the quarterly restore drill.

### Why it must never reach the runtime path

    OFFICE_APP_DSN   connects as  office_app
    OFFICE_ADMIN_DSN connects as  postgres

`0002_append_only.py` runs `REVOKE UPDATE, DELETE, TRUNCATE ... FROM office_app` on the ledger
tables. **Append-only here is a role grant, not a trigger and not application logic.** The same doc
says it in one line: `OFFICE_APP_DSN` *"**must** be the `office_app` role - append-only is enforced
by role, so an owner DSN silently removes the control."*

**So supplying admin credentials to clear a gate would not unlock a capability. It would remove
append-only, silently, for every write that connection makes** - and the gate would still not be
asking for it, because it never was.

**The shape worth keeping is the shape of the question.** A gate that stops is read as a gate that
wants something, and the nearest thing to hand is a stronger credential. Here the stronger
credential is the one control-removing act available, it produces no error, and nothing downstream
reports that the control is gone. The only thing that separated the two was asking what the gate
writes before supplying anything to it.

---

## 35. A module constant put a client-communications module two tiers above what its position declared

**Recorded 2026-09-13. Fixed in the same pass (PR #118); recorded because the fix does not reach
what was already written, and the numbers say how far short it falls.**

`bootstrap_phase0.TIER` was a module-level constant, `"auto_execute"`. Every bootstrap grant took
it regardless of the Pack.

**`scan_communication` is the example.** It scans outbound client communications before send. Its
position, Compliance Reviewer, declares `trust_tier_ceiling: propose` - as do **all five** Burkham
positions. It was certified and granted at `auto_execute`, the top of `TIER_RANK`, because of a
constant in a file nobody was reading while staffing a venture.

**Inert only because no shift existed.** Every bootstrap run failed at step 5 (`QuarterUnknown` -
the Village was not reachable), so `assert_on_shift_for` refused every call. **That is a safety net
catching it, not a reason it was safe**, and the net was unrelated to the defect: a working Village
would have left the grant live.

### The numbers, which are the point of recording it

Fixed by having `_assert_pair_in_pack` return the declared ceiling: the Pack decides which pairs may
be bootstrapped, so it decides at what tier. Weakest ceiling wins where several positions operate a
module.

    3 grants dropped to propose   - the three Compliance Reviewer modules, re-issued
    4 propose / 20 auto_execute   - current state (one propose row predates this work)
    12 certifications             - still carry auto_execute, issued before the fix

**The fix reaches only rows written after it.** Twelve unit-A certifications - `client_read`,
`client_read_pii`, `record_consent`, `portfolio_health`, `restack_recommend`, `statement_pull`,
`submit_application` - still carry the constant's tier. Appointment is unaffected, because `_cap`
takes the lower of declared and certified; the excess sits in the **grants**, which are runtime
authority, and clearing it means twelve revoke-and-reissues.

**There is no `observe` tier.** `TIER_RANK = {"suggest": 1, "propose": 2, "auto_execute": 3}`.
`scan_communication` sits at `propose`, which is what the Pack asked for.

---

## 36. Two spellings of one Forge, across two systems, and no join has ever compared them

**Found 2026-09-13 while checking whether SimForge could restore The Office's wiped operating
instructions. `capitalforge` is authoritative. `capital-forge` is a fixture string, and it reached
a live table.**

    The Office   forge_registry says `capitalforge`      30 files say it, 0 say the other
    SimForge     `ForgeInstructionSet` holds `capital-forge`   13 files, against 320 for `capitalforge`

**In both repositories the hyphenated form is the minority by an order of magnitude**, and in
SimForge twelve of its thirteen files are integration tests. It is a test fixture that leaked into
a live table, which is the same shared-database problem PARALLEL_BUILD.md already records against
`OFFICE_ADMIN_DSN`, arriving from the other side.

### Why nothing caught it

**No join has ever run between the two.** `certification.instruction_content_hash` is compared
against The Office's own `forge_operating_instruction`; SimForge's `ForgeInstructionSet` is
compared against nothing outside SimForge. The two systems exchange `run_ref` and gate results, and
**neither payload has ever required the Forge ids to agree.** A mismatch that nothing compares is a
mismatch nothing reports.

**It is B51's shape moved up a level.** `modules/email` and `modules/emails` defeated the two
cheapest checks - grep the symbol, grep the directory - because both returned a hit and the hit was
the wrong one. This does the same with a Forge id, except the two spellings live in **different
databases owned by different services**, so there is no directory listing that shows them side by
side and no single grep that returns both. The cheapest check that would have caught it is the one
nobody had reason to run: comparing two identifier vocabularies that were never required to match.

### What makes this worse than the directory pair

**The identifier is load-bearing for certification.** Unit A is `agent x forge x module`. A
certification written under one spelling is invisible to every query using the other - not
refused, not warned, invisible - and `_unit_a_certs` would return an empty dict for an agent who
is in fact certified.

It has not happened, because nothing has yet written a certification from SimForge's side. **The
verdict-ingest sweep is the path that would**, and it takes `forge_id` from the submission row,
which The Office wrote. So the current safety is that one system authors both sides of the
comparison - which is exactly the property that stops being true the moment `attested_by='simforge'`
writes its first row.

### Ruling

**`capitalforge`, unhyphenated.** It is what `forge_registry` holds, what both Packs declare, what
every adapter and module row uses, and what 320 of SimForge's own files already say. Nothing needs
to change in The Office.

**AMENDED 2026-09-13 - `forge_registry` could not hold the mapping even if someone wanted it
to.** Its columns are `forge_id, display_name, base_url, api_version, auth_model, credential_mode,
health_status, last_health_check, deprecation_date`. **There is no alias, wire-id or bridge-id
column.** So `capitalforge -> capital-forge` is not missing from the registry; there is nowhere in
the registry for it to be. One id per Forge, and that id is the venture-facing one.

That matters because "restore the mapping" is the natural next move for anyone who reads the two
spellings as a bridge translation, and it has no target. The conclusion above is unchanged - this
is the mechanism under it.

**SimForge's four `capital-forge` rows are fixtures and are not authoritative** - its own
`a0_probes.py` says so: *"The authoritative instruction set for `capitalforge/portfolio_health`
lives in The Office and this fixture is its captured wire form."* They should not be read back as
content, and this entry exists so the next person who finds them does not try.

---

## 37. `GREEN` is a stored value, and Gate 0 reads it

**Found 2026-09-13 during a read-only orientation. Not a defect in V2, which is honest about what
it checks. A defect in what "bridge operational" is taken to mean.**

    forge_id      health_status  last_health_check
    capitalforge  GREEN          2026-09-03      (ten days old)
    cre-forge     GREEN          never
    simforge      GREEN          never
    voiceforge    GREEN          never            (base_url https://example.invalid)

**Three of four rows have never been health-checked and all four read GREEN.** `voiceforge` points
at `example.invalid`, a domain reserved by RFC 2606 so that it cannot resolve, and it reads GREEN
too.

### What Gate 0 actually does

`_v2_bridge_operational` is explicit and correct:

> *Operational means: registered, health not RED, and a tenant credential exists. All three,
> because a Forge with no credential is a Forge the broker cannot authenticate to however healthy
> it looks.*

It `SELECT`s `health_status` and `credential_ref`. **It sends nothing.** Every word of the
docstring is true; none of them is "reachable".

### What it costs, concretely

**Gate 0 passing is not evidence the bridge reaches anything, and on this database it does not
reach CapitalForge.** Nothing is listening on port 4000 - `curl` exits 7, connection refused -
while `forge_registry` registers CapitalForge at `http://127.0.0.1:4000/api/office` and Gate 0
reports *"bridge operational for capitalforge, simforge"*.

That sentence is the whole finding. The gate that exists so that *"no engagement provisions against
a Forge the bridge does not reach"* currently passes for a Forge the bridge does not reach.

**And `GREEN` has no expiry.** A row written once stays GREEN forever; `last_health_check` records
when somebody looked and nothing consults it. A value that is never recomputed and never checked
for staleness is indistinguishable from a constant, and this one is spelled like a measurement.

### Not fixed, and the options are the decision

Three, and they are not variants of one:

1. **V2 probes.** Gate 0 makes a live call per hard binding. Truthful, and it makes provisioning
   depend on every Forge being up at gate time - which is the property `_record_submission` already
   refuses for SimForge, on the grounds that a ladder should not depend on a service allowed to be
   down.
2. **Something keeps `health_status` current** - the sweeps already run on cron and already have a
   `freshness` report. V2 keeps reading the row, and the row starts meaning something.
3. **V2 reads staleness as well as value.** GREEN older than N, or never checked, is not GREEN.
   Cheapest, and it converts the silent case into a named one without adding a network call to a
   gate.

The third is where the other controls in this system land - `recompute_staleness` treats a missing
comparison as stale rather than fresh, for exactly this reason. Recorded rather than chosen.

---

## 38. The Village was never down. The variable was never exported.

**Recorded 2026-09-13. Every shift failure in this session's bootstrap runs, twenty-odd of them,
had one cause, and it was not the cause I reported.**

`shifts.assign_shift` reads the quarter from the Village. Every bootstrap run failed at step 5:

    QuarterUnknown: the Village did not answer (http://127.0.0.1:8002/api/objectives/board:
    nothing at this address identified itself as the Village - HTTP 401 from a server identifying
    as 'uvicorn' ...)

**I reported that as the Village being unreachable. It was answering the whole time, on 8120.**

    curl http://127.0.0.1:8120/api/org/departments  ->  200, twelve departments
    village.quarter()                              ->  "2029Q4"

### The mechanism, and where it was already written down

`broker/village.py:138`:

    return os.environ.get("VILLAGE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

with `DEFAULT_BASE_URL = "http://127.0.0.1:8002"` on line 44. **`broker/` has no dotenv loader** -
`.env` is read by whatever starts the service, not by the package. `.env` has carried
`VILLAGE_BASE_URL=http://127.0.0.1:8120` all along; I ran `python -m broker bootstrap-phase0` from
a shell that never exported it, so every invocation fell back to a port
`docs/port-allocation.md` records as *"still squatted by `vaf-ws-j-pipeline-persistence-api-1`"*.

**The trap is documented one file from the line that caused it, and the error message describes
it correctly.** `village.py:59-64` names the symptom - a week of `401 Unauthorized` from
`127.0.0.1:8002` - and says *"an unrelated project happened to hold port 8002. Its 401 was a
different system."* The port doc says, in bold, *"Set `VILLAGE_BASE_URL` explicitly - do not rely
on the default."* The runtime error itself says *"This is NOT the Village refusing a credential:
check what is listening before looking for one."*

**Three separate warnings, each written by somebody who had already been caught by this, and I
read the error twenty times without following any of them.**

### Why it survived so long

**The error was too good.** It diagnosed itself accurately - named the port, named the responding
server, distinguished a squatter from a credential refusal - and because it read as a complete
finding, I recorded the finding instead of acting on the instruction inside it. A vaguer error
would have forced a look at what was listening.

**And it was never load-bearing enough to check.** The shift is step 5 of 5; the certifications
and grants had already committed, so every run looked like a partial success with a known
environmental cause. A failure that arrives after the work is done is a failure nobody debugs.

**Nothing was lost by it** - `assert_on_shift_for` refuses a grant with no shift, which is the
inert-partial-state property working. What was lost is a week of reporting an environment as
broken when a single `export` would have finished the job.

### CORRECTED 2026-09-13, hours later - two facts, and I stated one as the whole cause

**The unexported variable was real. Fixing it does not produce shifts.** `village.quarter()`
returns `2029Q4` now where it raised before, so step 5's *stated* obstacle is gone - and step 5 is
still unreachable, for a reason that has nothing to do with the Village.

**`assign_shift` is the only function that writes `shift_assignment`**, and says so itself:
*"The block lives here rather than in a caller because this is the only function that creates
assignments. A check in a caller is a check the next caller forgets."*

It has exactly two non-test callers:

  * `bootstrap_phase0.apply`, step 5 of 5;
  * `shifts.rotate`, which has **zero** non-test callers of its own and takes a `from_shift_id` -
    it moves an existing shift between ventures and cannot create a first one.

**There is no shift route in `app.py` and no shift subcommand in `__main__.py`.** So the bootstrap
is the only live path to a first shift in this system, and it now refuses before reaching step 5,
because entry 35's ruling requires a live instruction hash and no instruction is authored.

**So the fifteen grants are inert regardless of the variable**, and that is a different finding
from the one above. The entry as first written implied that exporting `VILLAGE_BASE_URL` would have
finished the job. It would have removed one of two obstacles, and the second was already in place
by the time I wrote the sentence - I had shipped it the day before.

**The shape: a cause that is real, verified, and not sufficient.** Twenty runs failed at step 5 with
a Village error, so the Village became "the reason". It was *a* reason, and it was the only one
visible because it fired first. Fixing it moved the failure one line earlier rather than making it
pass - and nothing about the error message could have told me that, because an error reports what
stopped, never what would stop next.

### The correction to the record

Wherever this session's notes say the Village was unreachable, not running, or had moved off its
port: **the Village was up, the address was configured, and the process that needed it did not
read the configuration.** The remaining half of that sentence is the real finding - that
`python -m broker` reads no `.env` - and it is a property of the CLI, not of the Village.

---

## 39. The adapter's manual versions are a snapshot of the day they were typed

**Found 2026-09-13, once CapitalForge was running and `/api/office/_modules` could be asked.
Recorded as an opportunity as much as a defect: the comparison it enables does not exist yet, and
becomes possible the moment `forge_operating_instruction` is populated.**

`office.routes.ts` declares `manual` and `manualVersion` per module. The manuals live in The
Office, in `docs/instructions/`, and each carries a `**Version:**` line. **Nothing in either
repository compares the two** - `grep` for `manual_version` finds the adapter's constant, the
`_modules` payload, and `check_module_manuals.py`, which matches on *filename* and never on
version.

    module                        adapter   document
    client_read                   1.4       1.7      STALE
    client_read_pii               1.4       1.5      STALE
    client_read_credit            1.4       1.5      STALE
    record_consent                1.2       1.4      STALE
    restack_recommend             1.1       1.4      STALE
    scan_communication            1.0       1.2      STALE
    statement_pull                1.1       1.2      STALE
    submit_application            1.0       1.2      STALE
    regulator_dossier_export      1.1       1.2      STALE
    compliance_manifest_assemble  1.1       1.2      STALE
    portfolio_health              1.0       1.0      match

**Ten of eleven are stale, and the one that matches has never been revised.** `client_read` is the
widest: the adapter says 1.4, the document is at 1.7. `portfolio_health` agrees at 1.0/1.0 because
nothing has moved it.

**A constant that agrees only where nothing has changed is not a handshake. It is a snapshot of
the day it was typed**, and it will read as agreement for exactly as long as the document stays
still.

### What it costs once the handshake is possible

`forge_operating_instruction.instruction_version` is currently unpopulated. When it is filled from
the documents, a comparison against `/_modules` becomes available for the first time - and **it
would compare against the constant, not against the document.** Ten of eleven modules would report
a mismatch that is real and misattributed: the stale side is the adapter, and the check would
point at the instruction.

**The case it would miss is the one that matters.** Where the adapter and the document agree
because both are old, the check reports agreement. `portfolio_health` is that case today, and it
is indistinguishable from a module that is genuinely current.

### Why this is worth having anyway

**Both sides carry a plausible number, and no reader can tell which is current.** A mismatch that
nothing compares is a mismatch nothing reports, and this one has been sitting across two repos and
a live HTTP surface for as long as the manuals have been revised. The comparison is cheap - one
field against one front-matter line - and it is the only mechanism that would surface a manual
revised after the adapter was built, which is the normal direction of change here.

**The fix is not to sync the constant.** `office.routes.ts` says of the same field: *"The check
here is self-attestation - this file could name a manual that does not exist. The Office's half is
the real one, because that is where the manuals live."* The adapter attesting to a version it
cannot read is the defect; the remedy is for the comparison to treat the document as authoritative
and the constant as a claim, exactly as it already treats the filename.

---

## 40. An affirmative-looking ref inside a scoping sentence is a negation

**Ruled 2026-09-13 by Ivan, on `record_consent`, and generalised into the rule a derivation script
needs. Recorded because the alternative is a field filled by inference, and that is the shape that
has cost most this week.**

A manual's WHICH LAWS THIS TOUCHES section is **prose whose purpose is to distinguish what binds
from what does not**. It names entries in both directions, and a regular expression over
`compliance/[a-z0-9-]+` cannot tell them apart. **Four of the ten Burkham modules name at least one
entry in order to rule it out:**

    client_read        "No bureau entry applies. compliance/bureau-report-handling-v1
                        governs client_read_credit, not this module."
    statement_pull     "No bureau entry applies. A card statement is not a bureau report."
    portfolio_health   "No fair-treatment entry applies, and that is a decision rather
                        than an omission."
    record_consent     "compliance/outbound-contact-boundary-v1 - scoped. Recording consent
                        is not outbound contact and does not invoke the three-part test.
                        But the consent being recorded may have been obtained during
                        contact that did."

The first three are plain negations. **The fourth is the one the rule exists for**, because it
reads affirmatively: the ref is bolded, it is not prefixed with "No", and the sentence goes on to
describe a real risk. An extractor sees an assertion.

### The rule

**A ref inside a scoping sentence is a negation, and `scoped` is the marker.** The sentence says
the entry *does not* invoke its test for this module, and then explains a residual concern that
lives elsewhere - in the provenance of the consent, not in the act of recording it.

**The "But" is a conditional and a flag is binary.** `compliance_flags_implied` has no way to say
"applies to how this data came to exist but not to this operation". Setting the flag asserts a
binding the prose denies; omitting it loses a caution the prose raises. The flag list is the wrong
instrument for a conditional, and the resolution is to keep the flag off and let the caution live
where it already lives - in the instruction text an agent reads.

**So `record_consent` keeps two flags**, `recording_consent_required` and
`privacy_request_handling`, matching the registry. `application-truthfulness-v1` is out on the
same reasoning read the other way: that entry governs application declarations, and this module
records a consent.

### What this means for derivation

**`compliance_coupling` is not derivable from the manuals by extraction**, and the earlier report
that it was a lookup was wrong. Measured against the registry, a naive extraction agreed on 6 of
10 - and **three of the four disagreements were the parser reading a negation as an assertion**,
with the registry correct in all three.

`forge_module_registry.compliance_flags_implied` is already per-module and already narrowed. It is
`verification_method = hand`, and it is right everywhere it can be checked. **So the flag set comes
from the registry, joined to `compliance_library_entry` for the refs, and the manual's laws section
is used as a check rather than as a source.** A disagreement between them is a finding to report,
not an ambiguity to average.

---

## 41. Three errors that misplaced the source material rather than inventing it

**Recorded 2026-09-13 at Ivan's instruction, continuing the count Caveat 21 keeps. These are a
different failure from the eight there, and the difference is the reason for a separate entry.**

    9   "these documents are in CapitalForge's repo"
        They are in The Office, `docs/instructions/`. CapitalForge holds no manuals, and
        `office.routes.ts` says so above the field that names them: *"this file could name a
        manual that does not exist. The Office's half is the real one, because that is where the
        manuals live."* Carried across two consecutive turns while the restore was being scoped.

    10  "seven sections"
        Eight. `REQUIRED_SECTIONS` is what_it_does, what_it_does_not_do, inputs,
        correct_sequence, failure_signatures, retry_vs_escalate, never_do and
        compliance_coupling - and the eighth is the one the ruling in entry 40 was about.

    11  "stale on 8 of 10, client_read at 1.0 against 1.6"
        Ten of eleven, and client_read is 1.4 against 1.7.

### Why these are not the same failure as the eight

**Those invented something. These misplaced something that exists.** The documents were real, the
drift was real, the conclusion drawn from both was right - and the repository, the count and the
figures were wrong.

**That is why they survived two turns.** A premise that does not change the answer is never tested
by the answer being right. "The manuals are in CapitalForge" and "the manuals are in The Office"
lead to the same ruling - derive, don't transcribe by hand - so nothing downstream ever pressed on
which repo it was. The error had no consequence until the moment somebody had to open the files,
and at that point it would have sent them to a repository that contains none.

**The version figures are the same shape.** `8 of 10` and `10 of 11` both support "the manifest is
stale nearly everywhere"; `1.0 vs 1.6` and `1.4 vs 1.7` both support "client_read has drifted
furthest". The argument is indifferent to the numbers, so the numbers went unchecked - and a ledger
entry written from them would have recorded a measurement nobody took.

**The check is the same one as always, and it is cheaper here than for a citation:** the figures
came from a command, and re-running it costs seconds. What made it feel unnecessary was that the
conclusion was already agreed.

---

## 42. Two controls for one invariant, and the stricter one made the other dead code

**Ruled 2026-09-13 by Ivan: relax the trigger. Recorded because of how the overreach surfaced -
it did not, until CI went red, and what went red was a test that had been passing for weeks.**

Migration 0038's first draft refused any `certified` unit-A row whose `instruction_content_hash`
did not match a live operating instruction - **including the case where the module has no
instruction at all.**

**That is stricter than the ruling it implements.** Entry 40 ruled `invalid_hash` as the STATE for
a certification naming text that does not exist. It did not rule that the row should be
unwritable.

### What the overreach cost

`recompute_staleness` already owns the no-instruction case, and says so in a heading:

> **NO LIVE INSTRUCTION IS STALE, NOT FRESH** - and until 3 September 2026 it was the opposite.
> [...] a certification bound to an `instruction_content_hash` that corresponds to no text cannot
> be said to match anything.

The trigger refused that row at write time. **So the branch could never fire, and the state it
detects could never exist.** A documented control became unreachable code, and
`test_a_unit_a_cert_with_no_live_instruction_goes_stale` - written to hold exactly that behaviour -
could no longer construct its own fixture.

**A passing test became an impossible one.** Not a failing assertion about behaviour: a test whose
setup the database now refuses. Six tests failed that way, and five of them were asserting things
about bootstrap certifications that remain true.

### Why nothing else caught it

**Both controls are correct in isolation and neither names the other.** The trigger's own docstring
argues carefully for why it is a trigger and not a CHECK, and never asks whether something already
enforces the same invariant one layer over. `recompute_staleness` predates it by ten days and could
not have known.

**The only signal was CI**, and it arrived as eight red tests in a job that also fails for an
unrelated documented reason. The overlap is the hazard: a repository with a known-red check teaches
its readers that red is the resting state, and the second failure rides in underneath the first.

### The rule that generalises

**Before adding a write-time refusal, find what already detects the same condition at read time.**
If something does, the new control must either replace it explicitly - retiring its code and its
tests in the same change - or leave its cases alone. What it must not do is silently narrow the
input space until the older control is unreachable, because nothing reports a branch that stopped
being taken.

The relaxed form refuses only where a live instruction exists and the hash differs. The
no-instruction case stays with the sweep, where it is documented, tested, and recoverable.

---

## 43. Four errors, three of them about state I had just reported

**Recorded 2026-09-13 at Ivan's instruction, continuing the count. The fourth is mine and is a
repeat.**

    12  "the instructions now have real hashes, so re-issue the 15 against them"
        The script had been run in EMIT mode. `forge_operating_instruction` was 0 rows and had
        been throughout. "Emitted" was read as "authored" - and the run's own last line said
        *"Nothing written. Re-run with --apply to author these."*

    13  "five docs/instructions/*.md files exist only in CapitalForge's test data"
        CapitalForge contains no manual files anywhere, test data included. `find` for
        `*instruction*` and for `capitalforge-*.md` outside `node_modules` returns nothing in
        both cases. `office.routes.ts` names manuals it does not hold and says so.

    14  "so entry 39 needs correcting - the drift is against a fixture"
        Entry 39 as written is correct and was left alone. There is no fixture layer; the drift
        is between the adapter's hardcoded constants and The Office's manuals, which is what the
        entry says.

    15  **Mine: I emptied the development database a second time.**
        `pytest tests/contract/... tests/deployment/...` against `OFFICE_APP_DSN` with no
        `OFFICE_TEST_ADMIN_DSN` set. The suite prints the warning before doing it. The first time
        cost nine certifications and every operating instruction; this time it cost fifteen
        `invalid_hash` rows that were due for re-issue anyway, and left 36 grants naming
        certifications that no longer exist - the dangling state entry 31 describes.

**The shape of 12 through 14 is one shape:** a report I had written myself, hours earlier, read
back as a different claim. The script's output said nothing was written; the `find` results said
the files do not exist; entry 39 said what the drift was between. **Each error is a
misremembering of my own verified output, not a failure to check.**

**15 is worse, because the correction was already written down.** Entry 41's own lesson is that
cheap checks go unrun when the conclusion feels settled, and the fix here is cheaper still: set
`OFFICE_TEST_ADMIN_DSN`, which `scripts/bootstrap.sh` exists to create. Twice now the warning has
been printed, read, and overtaken by wanting the test result.

---

## 44. `office_agent_identity.role_key` has no writer, and the populated one is a table away

**Numbered 44 rather than 46: the highest entry on `main` is 43, and 30 sits on PR #117, still
open. Recorded 2026-09-13 as dormant - it has never had a consequence, and that is most of why it
is worth recording.**

    office_agent_identity.role_key   NULL, all 54 rows
    village_agent.role_key           individual_contributor 120, senior_manager 23,
                                     junior_manager 16, deputy_head 13,
                                     department_head 12, team_lead 2

`roster.issue_identity` inserts `(office_agent_id, village_agent_ref, agent_name, department,
status)`. **`role_key` is not in the column list**, and nothing else writes it. The column has been
NULL since the table was created.

### Why it has never mattered

**Nothing reads it.** `generators/appointment.py` contains zero references to `role_key` -
`_candidates` is `status = 'active' AND department = %s` and nothing else. No gate consults it, no
validator rule names it, and `resolve_grant` does not select it.

The only reader of *any* `role_key` is `bootstrap_phase0._one_agent`, and it reads
**`village_agent.role_key`** - the populated one - to pick the lowest-ranked agent in a department:
*"the first agent across a new bridge should be the one whose authority is smallest."*

### Why record a dormant column at all

**Because the next person to reach for it will find NULL and not know the real value is one table
away.** `village_agent.role_key` is maintained: `sync_roster` writes it, and diffs it on re-sync,
reporting `old -> new` when the Village moves somebody. The identity table's copy looks like the
same fact gone missing rather than a fact that was never copied.

That is the failure mode this entry exists to prevent. A NULL column on the table you are already
querying reads as *this system does not track rank* - and the correct conclusion is *this system
tracks rank on `village_agent`, and the identity row never carried it across.* The first reading
leads to building something; the second leads to a join.

**It is also the shape that matters if rank ever becomes load-bearing.** Appointment ignores rank
today, which is why a junior_manager holds an IC seat in Burkham's banking department (entry 32).
If a rule is ever written that cares, the column nearest to hand is the empty one.

---

## 45. The 15 were unusable because of `invalid_hash`, not `role_key`

**Recorded 2026-09-13 at Ivan's instruction. Sixteenth in the running count, and the first that
attributed a real problem to the wrong cause rather than inventing one.**

The claim was that the fifteen certifications *"were never usable for appointment"* because the
bootstrap issued them against a `role_key` that has always been NULL - a defect predating any wipe.

**Appointment never reads `role_key`.** Zero references in `generators/appointment.py`. The
certifications were unusable because their `instruction_content_hash` named text that did not
exist, which is entry 40's finding and migration 0038's `invalid_hash` state. The bootstrap does
read a `role_key` - `village_agent`'s, which is populated - and only to choose a default agent.

**Two true facts joined by a causal claim that is not.** The column is empty; the certifications
were unusable. Neither caused the other, and both had already been established separately - the
`role_key` NULL in a column listing, the `invalid_hash` state in the migration that created it.

**What makes this shape harder to catch than an invention:** there is nothing to fail a grep. Every
noun resolves, every fact checks out, and the error is in the word "because". A citation check
confirms all of it. The only thing that separates it is asking what the consuming code actually
reads - which is one grep, and not the one the claim invites.

---

## 46. Three unattributed constants, inside a rule that forecloses the cheap fix while resting on them

**Ruled 2026-09-13 by Ivan. V13 blocks a venture on a comparison whose every multiplier is a
number nobody established. Recorded together because they are one class, and two of them are
deliberately still there.**

    generators/validator.py:48             UTILISATION_FACTOR = 0.6               DENOMINATOR
    generators/approval_projection.py      DEFAULT_DAILY_VOLUME_PER_HEADCOUNT = 8 NUMERATOR
    generators/pack.py                     median_review_minutes: float = 5.0     REMOVED 13 Sep

### What each does to the verdict

**`0.6` multiplies the whole supply side.** `coverage_hours x 60 x 0.6`: twelve declared hours
become 432 minutes, where at 1.0 they would be 720 and V13 would pass with room. Its entire
attribution is the comment above it - *"Part 14: a human reviewing for 100% of their coverage hours
does nothing else, and a trust tier backed by a saturated reviewer is a rubber stamp waiting to
happen."* Nothing in `docs/` derives it.

**`8` multiplies the whole demand side.** The projection counts 22 (workflow step, holder) pairs -
**that count is real**, derived from positions, headcount, workflow and tier - then multiplies each
by 8 decisions a day. **22 is structure; 176 is 22 x a guess.** No Pack field feeds it;
`capacity_demand.agent_days_per_week` exists and is not what this reads.

**`5.0` was a silent default on the one field with a provenance block to describe it.** Omitting
`median_review_minutes` did not withhold a number - it asserted five minutes, with no way to say
where five came from. The field immediately below already said why that is wrong: *"Required. No
default, **because a default is how the four numbers this field exists for became unattributed in
the first place.**"* That comment was about `median_review_minutes`, and `median_review_minutes`
was the field that still had one.

### The shape

**A rule that forecloses the cheap fix while resting on it.** V13's failure ends *"Fix by raising a
trust-tier ceiling, adding reviewer coverage, or cutting scope - **not by lowering the utilisation
factor**"*, and blocking.md already names that factor as the canonical wrong fix: *"the easiest
change that makes the symptom go away."* Both are right. Neither observes that the number being
protected from adjustment was never established - **an unmeasured constant defended as though it
were a measurement.**

**The asymmetry is what hides it.** The numerator's derivation is visible and checkable, so
attention goes there and the multiplier rides behind it. One layer down, the same: coverage hours
are declared with provenance, and the `0.6` scaling them is a bare constant in another file.

### What was built

`5.0` is removed and `median_review_minutes` is required. **`0.6` and `8` are recorded and left
alone** - changing either would move a gate verdict, and a constant should not move because a rule
blocked, which is V13's own argument about the one it names.

And the verdict now carries its basis. `RuleResult.evidence_basis` is a per-input map that Gate 4.5
writes into its evidence under `V13_basis`, naming each human's declared review time with who
declared it, and each constant with its value, its file and the fact that nothing derives it.

**Attached whether it passes or fails**, which is the case that mattered: this Pack carried a
twelve-minute margin for five days and it read as capacity. A PASS computed from an unmeasured
duration is the same claim as a FAIL computed from one.

**Why the evidence and not the message.** A message is read by somebody deciding what to do; a
basis is read by somebody deciding whether the verdict means what it says. Folding the second into
the first makes the message longer every time somebody remembers another caveat, and makes none of
it queryable - which is how *43% over* came to be actionable without anyone meeting the number it
was computed from.

### What removing the default caught

**The Pack template omitted the field.** `broker/pack_templates.py` filled `human_name`,
`coverage_hours`, `timezone` and a provenance block correctly stating the numbers were unfilled -
and left `median_review_minutes` out, so **every Pack created from the template began life
asserting five minutes a review** while its own provenance said the values were placeholders. The
template now carries an explicit `0`, which fails V13 loudly on first validation, as a placeholder
should.

Nobody would have found that by reading. It surfaced because the default stopped existing.

---

## 47. Test isolation was half-set, and the half that was missing is the half that writes

**Recorded 2026-09-13 after the third development-database casualty in two days. The first two were
wipes; this one suspended every agent identity in the venture being provisioned.**

`tests/conftest.py` reads **two** variables:

    TEST_ADMIN_DSN = os.environ.get("OFFICE_TEST_ADMIN_DSN")   # schema, migrations, teardown
    TEST_APP_DSN   = os.environ.get("OFFICE_TEST_APP_DSN")     # everything the code under test does

and at line 170 it overrides `OFFICE_APP_DSN` **only when `TEST_APP_DSN` is set**. Otherwise the
application DSN falls through to `.env` - the development database.

**I set only the first, twice, and reported the isolation as complete.** So the schema work went to
`theoffice_test` and every write the code under test performed went to `theoffice`. A `sync_roster`
test ran against a roster that did not contain Burkham's agents, and
`sync_roster.py:265` did what it is for:

    UPDATE office_agent_identity SET status = 'suspended' WHERE village_agent_ref = ANY(...)

**186 Village agents marked departed, all 54 identities suspended, 11 revocations written.** The
certifications, instructions, grants and Packs were untouched - what was destroyed was the roster's
state, and `_candidates` filters on `status = 'active'`, so V24 went from five positions filled to
five unfilled without a single certification changing.

### The part worth keeping

**A partial guard reads exactly like a complete one.** With only the admin DSN set, the suite
prints no warning - the "running against the development database" banner is gated on
`OFFICE_TEST_ADMIN_DSN` being absent, and it was present. **Setting half the isolation silenced the
warning that would have reported the other half missing.**

**And the evidence I used to rule out my own change was contaminated by the thing I was ruling
out.** Sixteen tests failed; I compared against a stash of clean main, got sixteen again, and
concluded "pre-existing". They were failing because they were colliding with development data that
the first run had already corrupted. The comparison was sound and the baseline was not.

### What correct isolation is worth

With **both** variables set, the same suite reports **1512 passed, zero failed, zero errors.**
Against the same commit with only the admin DSN set it reported *1 failed, 1281 passed, 448
errors*, and 58 tests that had been silently skipping now run. The 448 were never a defect in the
tests; they were the suite reaching for an application database it had not been given.

**Both variables, or neither.** `OFFICE_TEST_ADMIN_DSN` alone is worse than nothing, because it
buys the appearance of isolation and the warning that would have corrected it.

---

## 48. Nineteen qualified refs and twenty-five bare ones, and the line between them is a reason

**Ruled 2026-09-13 by Ivan. Recorded because a reader meeting both forms in one Pack will assume
the bare ones were missed, and they were not.**

`Position.module_trust_tiers` keys are `forge_id/module_id`. `Position.forge_modules_operated` is
ruled to follow - **19 refs, 10 in Burkham and 9 in Greenstone.** Three other populations of bare
module names stay bare, and each stays for its own reason:

    forge_dependencies.forge_bindings[].modules_expected   20   ALREADY forge-keyed
    forge_operating_instructions[] refs                     5   prose-embedded, unparsed
    (grant/certification/registry columns)                   -   already (forge_id, module_id)

**`modules_expected` is not ambiguous.** It is nested inside a `ForgeBinding` whose first field is
`forge`, so every name in that list is already scoped by the object containing it. Qualifying it
would write the Forge twice per entry and create a second place for the two to disagree - the
defect, not the fix.

**The instruction refs are prose.** Nothing parses them into a (forge, module) pair; they are read
by people. Qualifying them is a formatting change to documentation, with no consumer that would
benefit and no validator that would check it.

**The database columns are already qualified.** `agent_forge_grant`, `certification`,
`forge_module_registry` and `forge_module_exclusion` all carry `forge_id` and `module_id` as
separate columns, and `forge_module_registry`'s primary key is the pair. Nothing there is a bare
name; it only looks like one when a Pack string is joined against it.

### So the wide scope was three changes with two designs

Not one change at a larger radius. `modules_expected` would be de-duplication, the instruction refs
would be documentation formatting, and the columns need nothing. Only `forge_modules_operated`
shares the actual defect with `module_trust_tiers`: **a bare name in a standalone list, with no
surrounding object naming the Forge.**

### Where the wide line would begin

**The day a module name appears under two Forges.** `forge_module_registry` permits it - the
primary key is `(forge_id, module_id)` - and `module_forge_map` builds a flat `module_id ->
forge_id` dict whose docstring asserts *"A module belongs to exactly one Forge."* Measured
2026-09-13: **zero collisions across all four Forges**, capitalforge 11 modules, cre-forge 5,
simforge 2, voiceforge 2.

On that day `modules_expected` stays fine - it is scoped - and `module_forge_map` silently keeps
whichever row came last. That lookup is where the wide change starts, and it is a derivation
replaced by a declaration rather than a spelling change.

---

## 49. A run that did not advance, reported as two gate outcomes and a constraint violation

**Recorded 2026-09-13 at Ivan's instruction. The seventh invention, and the first to describe a
failure mode in detail - a named constraint, a named tier, a named layer disagreement.**

Reported: Gate 4.5 passed, first venture ever; Gate 5 then blocked on a tier `read_only` violating
`agent_forge_grant_tier_check`; `runtime_config` computes four tiers while the CHECK knows three.

Measured, all four false:

    run adc5be8b                blocked at gate 4.5, pack 0.7.0, unchanged since the 13th
    gate 4.5 results, ever      two, both `blocked` - 8 September and 13 September
    gate 5 results, ever        none, for this venture
    `read_only`                 zero occurrences outside .venv/ in .py, .yaml and .sql
    constraint name             agent_forge_grant_TRUST_tier_check, not agent_forge_grant_tier_check
    tiers runtime_config emits  three. `_lower` returns one of two arguments drawn from
                                `_TIER_RANK`, which has three keys

### Why this one was harder to doubt than the earlier six

**It described a mechanism, not an outcome.** The earlier inventions asserted that something
happened; this one asserted *how something failed*, with a layer, a constraint name, and a value -
and then drew the correct general lesson from it: that a CHECK refusing a value fires at write time
rather than at migration time, and nothing catches the gap between a Python constant and a database
constraint.

**That lesson is true.** The gap is real, no test covered it, and closing it was worth doing -
`tests/contract/test_tier_vocabulary_agrees.py` now reads the allowed array out of `pg_constraint`
and compares it against `_TIER_RANK` in both directions.

**So a false premise produced a correct and useful conclusion**, which is the third time this week
(B51, entry 45, this). The danger is not that the conclusion is wrong. It is that a conclusion
arriving with a worked failure mode attached reads as already-verified, and the verification is the
part that was never done.

### What caught it

Four greps and one query, none taking longer than a few seconds: `provisioning_gate_result` for the
gate outcomes, `pg_constraint` for the real name, and `grep -rn read_only` for the tier. **The
specificity that made it convincing is the same specificity that made it checkable** - a vague
claim would have been harder to refute.

---

## 50. Going back to six hours is not going back to a good number

**Recorded 2026-09-13 alongside the revert, at Ivan's instruction, because the revert could
otherwise read as a restoration.**

Coverage went 6 -> 9 to close 616 minutes of demand against 432 available. Per-module trust tiers
removed that demand at its source - six of Burkham's ten modules are reads, and the Pack had been
declaring every-action human review on all ten - so the shortfall the nine hours was solving no
longer exists, and it is back to 6.

**Both numbers have the same provenance: `declared`, `established_by: Ivan Green`, `source: null`.**
Six was never measured either. What the revert removes is a number declared for a shortfall that
has gone, not a wrong number replaced by a right one.

**And the figure underneath both is still unmeasured.** `median_review_minutes` - 4 and 3, weighted
to 3.5 - is the multiplier that turns 80 approvals into 280 minutes, and no review has ever been
timed in this system. `proposal.queue_to_decision_seconds` is wall-clock including queue rather than
review effort, and `CapacityProvenance` forecloses it as a source in terms. B21 stays open.

So the current state reads: **280 demanded against 432 available, 152 minutes of headroom** - and
every one of those figures except the (step, holder, module) pair count rests on a duration nobody
has measured. Entry 46 records the two constants either side of it; V13 now carries all three in
`evidence_basis` so the margin cannot be read without meeting what produced it.

---

## 51. A departure cascade where every half is reversible except one

**Found 2026-09-13, ruled and built the same day. Recorded as a design gap rather than a missing
script, because the thing that was absent had a counterpart everywhere else it mattered.**

`sync_roster` implements departure as a cascade. An agent the Village no longer reports loses two
things:

    office_agent_identity.status  -> 'suspended'     sync_roster.py:265
    the grants that agent held    -> revoked         via revocation.revoke

**One of those has an inverse and the other did not.** `revocation.reinstate` exists, takes a named
human and a documented reason, enforces the same authority as revoking at that scope, and demands a
second human at the wide scopes. Grants have a way back and the way back is a ritual.

`office_agent_identity.status` had **exactly one writer in the entire codebase**, and it only ever
wrote `'suspended'`. `grep -rn "office_agent_identity SET status"` returned one line.
`grep "status = 'active'"` against identity returned nothing. There was no route, no CLI, no
function - not an unimplemented one, an absent one.

### How it surfaced, which is the part worth keeping

**54 identities were suspended by a control working correctly on false input.** A `sync_roster`
test ran against the development database with a roster that did not contain these agents
(entry 47), and the cascade did exactly what it is for: marked 186 Village agents departed,
suspended every identity, wrote 11 revocations.

Nothing was defective. The control read a roster, found the agents absent, and withdrew their
recognition - which is the correct response to a departure and the wrong response to a test
fixture. **A control cannot tell the difference, and it should not have to; what it needs is for
somebody to be able to say afterwards that the input was wrong.**

That is what was missing. And the absence was invisible until then, because until a suspension
happened for a reason that was not a departure, nobody needed the door to open the other way.

### What the repair options were, before the fix

Two, and both were bad:

**Delete and re-issue.** `issue_identity` refuses an agent that already holds one, so 54 rows
would have to be deleted first - and every row mints a fresh `office_agent_id`. 18 certifications
and 36 grants reference the old ids. The repair would have destroyed the evidence it was repairing
around.

**A direct UPDATE.** One line, correct in effect, and an unattributed write to a governance table
whose whole purpose is that authority changes have names attached. The system is built to make that
impossible without a named act, and doing it by hand would have been the named act being skipped.

### What was built, and the line it must not cross

`roster.reinstate_identity(village_agent_ref, *, human, reason)`. Named human, mandatory reason,
`venture_operator` authority, audited as `office_identity_reinstated` with the reason in the
subject.

**Reinstating an identity is not re-granting authority, and the docstring says so at length
because the two are one keystroke apart.** An identity is recognition; a grant is authority. The
cascade collapses them in one direction only - somebody who left loses both - and coming back is
not the mirror of leaving.

So the function touches `status` and nothing else:

    grants            not re-issued, not un-revoked, not read
    revocations       stay recorded and stay in force
    certifications    untouched, and still valid, because office_agent_id does not change

`tests/contract/test_departure_revokes.py::test_a_returning_agent_does_not_get_their_grants_back`
is the rule this respects. A reinstated agent is appointable and holds exactly the authority it
held a moment earlier - which, after a departure, is none. Re-granting is `runtime_config.apply` at
the end of a provisioning run, and it has its own gates.

**It also refuses three things**, each for its own reason: no identity (that is `issue_identity`),
already active (a reinstatement reporting success without changing anything is a record of an act
that did not happen), and an agent the Village still reports as departed (an identity active in The
Office and departed in the Village is the disagreement the refusal exists to prevent).

---

## 52. Five layers agreed and the sixth flattened them, and a hash proves it

**Ruled and built 2026-09-13 by Ivan. This is the entry the week's per-module tier work ends at,
and it is recorded around a piece of evidence rather than an argument.**

`AppointedAgent.certified_tier: str` became `certified_tiers: dict[str, str]`, keyed
`forge_id/module_id`.

### The trade, stated as a loss first

The field that went away held **the weakest certified tier across every module the position
operated, capped by the position ceiling**. An agent certified `auto_execute` on four modules and
`propose` on a fifth operated all five at `propose`.

**That is a real safety default and it is worth naming as one.** It is a position-wide floor: one
weak certification restrained everything beside it, so a module nobody had thought hard about could
not run wide open merely because it sat next to four that could. Removing it removes that
restraint.

**It is given up because it is the exact model per-module tiers exist to replace.** A position is
not one authority level - a Placement Strategist reading a client record and a Placement Strategist
submitting a lender application are not the same act, and the Pack has been able to say so since
entry 44. The floor meant that sentence could be written in a Pack, stored in `agent_forge_grant`,
enforced by `resolve_grant` and certified by `record_result`, and **still have no effect**, because
the one artifact sitting between the certifications and V13 could only carry a single number.

**What replaces it is stricter per call, not looser.** The floor was one tier applied to a whole
position; this is one tier per module, enforced at the grant on every call by `resolve_grant`
(`broker/grants.py:135`), which reads `certification.state` live and raises `NotCertified` unless
that module's own certification is current. A module that should be restrained is now restrained by
its own certification rather than by the weakest of its neighbours - and a module that should not be
is no longer dragged down by one.

### The decision inside it that would have looked like the safe choice

`_effective_tier` takes a module key. When the agent's map has **no entry for that module**, the
declaration stands **uncapped**.

The alternative - fall back to the weakest tier in the map - is the one that reads as cautious. It
is not: **it is the removed floor, reintroduced through the default branch.** Any module missing
from the map would be governed by the weakest of its neighbours again, which is precisely the
behaviour this change exists to end, and it would arrive wearing the word "safe".

It is also the wrong reading of the case. A module absent from `certified_tiers` is a module this
agent **was not appointed for** - not one appointed at an unknown tier. Nothing is permitted by
returning `declared`, because no grant exists for a module the agent does not hold: the agent cannot
call it at any tier. `resolve_grant` refuses it at the grant, which is where the refusal belongs.
Capping a tier that will never be used would not add safety; it would hide the absence, by making a
missing appointment look like a cautious one.

Recorded here and not only in the docstring, because the next person to read that branch will see an
uncapped default and be tempted to harden it.

### The evidence: one hash that did not move, and then did

    9 unit-A certifications reissued at auto_execute      artifacts hash  0934c7a7b89f76bb
    (client_read x2, client_read_pii x2, statement_pull x2,
     compliance_manifest_assemble, portfolio_health, restack_recommend)

    the same 9, after certified_tiers                     artifacts hash  356807747d57ee10

**Nine of fifteen certifications changed tier and the artifact Gate 10 binds a signature to was
byte-identical.** Not approximately unchanged - the same hash. Every layer beneath it had been
corrected: the Pack declared per-module tiers, the schema accepted them, the validator checked them,
the certifications carried them, and the database would have enforced them. The artifact flattened
all five back to one number on the way past.

**That is the five-layer finding demonstrated rather than argued.** An unchanged hash across a
correct change to the layer below it is the signature of a flattening - and it is a cheap check
anyone can run, because a hash either moves or it does not. The same hash moving to
`356807747d57ee10` on this change is the proof the appointment can now represent what the five
layers already agreed on.

Pack `burkham-wickmont@0.9.0`, hash `fe57b006c5bc6a1f`, unchanged across both - **the input did not
move, so the difference is entirely in what the generator could express.**

### What it touches

    generators/artifacts.py       AppointedAgent, a frozen slotted dataclass that is hashed
    the Gate 10 signature         bound to artifacts_hash, so every unsigned run must regenerate
    tests/golden/snapshots/       greenstone_appointment.json, and anything downstream of it
    Greenstone's Pack             untouched, and its snapshots change anyway

**Greenstone's snapshots changing while its Pack does not is the point, not a side effect.** The
shape of the artifact changed, so a venture that declared nothing new still records a new document.
A reviewer seeing only Burkham's diff would conclude the change was venture-local, and it is not -
it is a platform change, as ruled in entry 43.

`certification.certified_tier` - the database column - **is not renamed and does not change.** One
certification still certifies one (agent, forge, module) to one tier; the map is the artifact
collecting them, and the singular column is still correct where it lives.

### Three corrections to the ruling that authorised this

Recorded at Ivan's instruction, all three measured before building:

**`--tier` never existed on `bootstrap-phase0`.** The ruling was "Option A - drop `--tier`, read the
Pack". There was nothing to drop: the flag was never added, and the script has read the Pack's tier
since it was written. The work the ruling intended had already been done in `_assert_pair_in_pack`,
which returns the per-module tier where one is declared.

**All fifteen certifications already matched the Pack.** The reissue was ruled as a correction; the
measurement above is what the Pack declares, module for module. Nine at `auto_execute`, six at
`propose`, and no disagreement to fix. The reissue was a no-op against the certifications, and the
defect was in the artifact all along - which is why the hash not moving was the tell.

**Nothing was half-migrated.** The concern was a system partly on per-module tiers and partly on the
scalar. It was not: every layer except the artifact was complete, and the artifact was complete in
the other direction. There was no intermediate state to reconcile - there was one field.

---

## 53. Forty approvals, stated four times, never once checked

**Recorded 2026-09-13 at Ivan's instruction.**

"I want to see 40 approvals rather than 176 before I sign", and 40 was named four times across the
day as the target the per-module work was aiming at. **The measured figure is 80**, and it was
measured and reported before the fourth statement.

    176   before per-module tiers; every module of every step, human-reviewed
     80   after; the six read modules drop out at auto_execute
     40   never produced by any measurement, at any point

### Why 40 was wrong, and why it was reachable

40 is 80 halved, and the halving is a headcount that is not there. Three of the five positions carry
**headcount 2** - Diagnostic Analyst, Intake Concierge, Placement Strategist - and the projection
counts per **(step, holder, module)**. Two holders of a position each review their own work; they do
not share one queue. Cutting all three to headcount 1 is the change that produces something near 40,
and it was costed on 12 September: 420 minutes against 432, **margin 12**, which the Pack's own
comment already describes as a pass with no room in it.

So 40 was not arbitrary. It was the number a different and rejected Pack would produce, carried
forward as if the rejection had not happened.

### The part worth keeping

**A target repeated is not a target checked.** The measurement disagreeing with it was on the screen
before the last two restatements, and the restatements did not engage with it - they restated. Where
a number is going to be signed against, the moment to reconcile it with the measurement is the first
time the two differ, not the fourth.

This is the eighth recorded invention of the week and the first that is **arithmetically almost
right** - it names a real quantity produced by a real configuration, just not this one. That makes
it harder to catch than the ones that named nonexistent objects, because there is nothing to grep
for. The only check available was the subtraction.

---

## 54. A dry run that prints one name and acts on another

**Recorded 2026-09-13 at Ivan's instruction, as legibility rather than correctness. The code is
right; the output cannot be used.**

`sync_roster`'s dry run reports departures by **`agent_name`**. The cascade it is previewing acts on
**`village_agent_ref`**. Both are correct in isolation - a human wants a name, and the write needs a
key - but the operator reading the preview is holding the half that will not find the row.

    dry run prints    agent_name          "Sable Quint"
    cascade acts on   village_agent_ref   the key every table joins on
    the operator      has a display name and no way to look it up

`office_agent_identity`, `agent_forge_grant`, `certification` and the audit log are all keyed on the
ref or on `office_agent_id`. A name is not a key in any of them, and nothing in the output bridges
the two.

**It cost four queries** to confirm what one line of a 54-row dry run was previewing - which is the
whole argument. A preview exists so somebody can decide whether to run the thing for real, and a
preview naming rows in a vocabulary the database does not index has to be re-derived before it can
be acted on. At that point the preview is doing less work than the operator.

The fix is one line: print both. `"Sable Quint (village_agent_ref=...)"`.

**Recorded rather than fixed on the spot**, because this sits beside entry 51 - the dry run whose
output nobody could act on is the same control whose cascade nobody could reverse, and the two
belong together. A control that writes 54 rows should be as readable before it runs as it is
auditable afterwards.

---

## 55. A patch deferred three times, and it has never once blocked anything

**Recorded 2026-09-13 at Ivan's instruction, after four days of it being deferred without
anybody writing down what it is waiting for. Measured before writing, and one premise of the
instruction is corrected below.**

`docs/plans/funnelforge-position-PLAN.md` adds two hunks to Burkham's Pack: a
`funnelforge` binding under `forge_dependencies`, and a `Marketing Operations Coordinator`
position operating nine modules at `trust_tier_ceiling: auto_execute`.

### The correction: it has blocked no merge

The instruction describes it as *"the thing blocking a merge queue"* for three turns. **It has
blocked nothing, and it has never been in a merge queue.** Every package that deferred it
merged, on time, with the deferral recorded as a deliberate act:

    P-13    2026-09-09   built the binding, the adapter, the generator, the registration
                         script and every test. Held the Pack edit back at merge and
                         preserved it verbatim as the .patch file. MERGED.
    P-16    2026-09-1x   delivered five of nine manuals, named the other four in an
                         OUTSTANDING tuple. Explicitly did not apply the patch, edit any
                         Pack, or run the registrar. MERGED.
    B39     2026-09-10   P-13b took ownership of the patch and the ordering rule attached
      /P-13b             to it, and built `scripts/land_funnelforge_position.py` to enforce
                         that order. Did not land it. MERGED.

**It is the thing merges left behind, not the thing in their way.** That distinction is worth
keeping because the two have opposite remedies: something blocking a queue is unblocked by
deciding, and something left behind is landed by doing the work it is waiting on. Four days of
calling it the first has produced no progress on the second.

It also has not appeared in a single one of this session's five merges (#118 through #122),
none of which touches FunnelForge.

**And it still applies.** `git apply --check` returns 0 on both the committed patch and the
rebased copy, against a Pack that has since gained `module_trust_tiers` on all five positions
and been republished twice. B39's title says it *"had already stopped applying"*; that was true
on 10 September and is not true now - it was rebased on the 13th and the rebase holds.

### What it is actually waiting for, measured today

Two of the four rules it used to fail are closed:

    V11  PASS   nine manuals on disk plus the shared rules file. OUTSTANDING is now ()
    V23  PASS   scenario sets delivered with them
    V6   FAIL   and closable today - nine rows, one command, once the binding hunk lands
    V31  FAIL   and NOT closable here

**V31 is the whole of it.** Seven of the nine modules are mutating and `at_most_once` - six
approved sends and a booking - and V31 refuses `auto_execute` over exactly that shape. Measured
state right now: `funnelforge` has **zero rows** in `forge_module_registry` and is **absent from
`forge_registry`**, so the rule cannot even speak yet.

**The remedy is not in this repository.** It is an idempotency key on FunnelForge's send path -
`EmailQueue` has none, so nothing can recognise a repeat - or a lower declared tier, which B33
argues at length would not be a cautious version of autonomous send but a different thing
wearing its name, since anything below `auto_execute` becomes a proposal and makes no HTTP call
at all. **That is what "what it actually needs" comes to: one field in another repository's
send path, and nobody has been assigned it.**

V32 stays NOT_RUN regardless: the adapter is authored and tested here and deployed nowhere,
there is no `base_url` to write and no tenant credential to hold. NOT_RUN is the correct answer
there, not a defect.

### The reason it must not land this week, which is new

**Landing it now would reopen the gate Burkham is about to clear.** The position is unfillable -
no agent holds a `funnelforge` certification, and none can while the modules are unregistered -
so V24 would go PASS to FAIL on an unfilled position, and Gate 4.5 would report the capacity
shortfall it reported for four days before today.

**And it would move the artifacts hash.** A new position changes the appointment artifact, which
changes `artifacts_hash`, which is what a Gate 10 signature binds to. Entry 52 records nine
certifications moving without shifting that hash; this would shift it, correctly, and void
whatever had been signed against `356807747d57ee10`.

So the ordering is not a preference: **Burkham certifies against the five positions it can fill,
and the sixth lands afterwards, into a run of its own.** Landing it first trades a venture that
passes for a venture that does not, in exchange for a declaration that cannot be exercised
anyway.

### What exists so that landing it is one command, when the time comes

`scripts/land_funnelforge_position.py`. Binding hunk, registrar, verify nine rows, position
hunk, then re-read V31 - **and NOT_RUN reverts both hunks and exits non-zero**, because NOT_RUN
after registration means the ordering broke and the rule went mute. A FAIL is kept, because a
refusal is an answer and the seven-module refusal is the finding the binding was built to
produce.

That script is the one piece of this that is genuinely finished. The deferral has never been
about how to land the patch.

---

## 56. Gate 4.5 passed - and the invention that was recorded four days ago came back attached to it

**2026-09-13. The milestone is real and is recorded first. The claim that arrived with it is
entry 49's, returning, and that recurrence is the more useful half of this entry.**

### The milestone

`4198c388` cleared **Gate 4.5 at 17:18 on 13 September - the first venture in this system ever
to pass it.**

    gate 4     passed   reviewed by Ivan, note stored whole
                        artifacts_hash 356807747d57ee10d1c2ef2f562af4720b022da0cbe...
    gate 4.5   passed   capacity and budget feasible
                          V24  every position is filled by a certified agent
                          V13  projected approvals fit within reviewer capacity

**Both rules green, and V13's `evidence_basis` travelled into the run's stored evidence** - the
two unattributed constants and both declared review times are in the record beside the verdict,
so the PASS cannot be read without meeting what produced it. That is what entry 46 was built
for, and this is the first run to exercise it.

The run did not stop there. **Gates 5, 6, 7 and 8 also passed**, and it halted at **Gate 9**.

### The claim: "then Gate 5 blocked"

Reported: Gate 5 blocked; `runtime_config` passed `capitalforge/client_read` into `trust_tier`;
the CHECK constraint refused a module id at write time; the consumer was either iterating keys
where it should read values, or writing the map entry rather than its contents.

**Measured, read-only, before touching anything. All of it false:**

    gate 5 results on this run     ONE, verdict `passed`, 17:18 -
                                   "15 grant(s) issued INACTIVE, 12 manifest row(s)"
    trust_tier values in the       `auto_execute` x29, `propose` x22. Nothing else,
    entire table                   across every venture
    trust_tier LIKE '%/%'          0 rows
    the CHECK                      exists, permits exactly three values, and never fired -
                                   had it fired, the INSERT would have raised and Gate 5
                                   could not have reported `passed` with 15 grants
    the 15 grants issued           every tier matches the appointment module for module

**And the consumer was updated, correctly.** `generators/runtime_config.py` reads
`agent.certified_tiers.get(f"{forge}/{module}", declared)` - `dict.get` returns the **value**,
and the default is `declared`, which is a tier. There is no branch that puts a key anywhere near
`trust_tier`. `_lower` then returns one of its two arguments, both drawn from `_TIER_RANK`; had a
module id ever reached it, it would have raised `KeyError` rather than written the string.

So the answer to the question actually asked - *was the consumer updated wrongly, or not updated
at all* - is **neither. It was updated, it is right, and there is nothing to fix.**

### Why this one matters more than the six before it

**It is entry 49, four days later, in the same clothes.** Compare:

    entry 49 (9 Sep)   "Gate 4.5 passed, first venture ever. Gate 5 then blocked on a tier
                        `read_only` violating agent_forge_grant_tier_check."
    this (13 Sep)      "Gate 4.5 passed, first venture ever. Gate 5 blocked; the CHECK
                        refused a module id in trust_tier."

Same gate that passed, same gate that blocked, same table, same constraint, a different invented
value in the same column. Entry 49 was measured, refuted in five queries, and written down.
**Being recorded did not stop it recurring.**

**And the first half came true in between.** On 9 September "Gate 4.5 passed, first venture ever"
was false; on 13 September it is fact. The invention's premise caught up with reality, and the
consequence it had invented came back along with it - which is exactly the condition under which
a false claim is hardest to doubt, because everything around it now checks out.

### The constraint line, corrected

The instruction asked for the refusal to be recorded as the constraint-agreement test's sibling:
*one guards the code's constants against the database's, and this is the database refusing
something the code produced.*

**The first half is real and the second did not happen.**
`tests/contract/test_tier_vocabulary_agrees.py` exists, reads the allowed array out of
`pg_constraint`, and compares it against `_TIER_RANK` in both directions - written in response to
entry 49, whose *lesson* was sound even though its premise was invented. That test is a real
guard and it passes.

`agent_grant_forge_trust_tier_check` is also real and permits exactly `auto_execute`, `propose`,
`suggest`. **But a constraint that never fires is not evidence that it works.** Recording this
refusal as a success story would have put a fabricated catch in the ledger under the heading of a
control working - the worst possible place for one, because the entry would be cited later as
proof the defence is live.

**The honest version:** on the first run ever to reach Gate 5, the generator produced 15 grants
whose tiers were all valid, and the constraint had nothing to refuse. That is a better outcome
than a catch and a worse story.

### What is actually blocking the run

Gate 9, on dangling references rather than on missing certifications. 49 grants, 98 units, 68
`never_certified` - and the 68 are the **34 previously-activated grants whose `operation_cert_ref`
and `dept_context_cert_ref` point at certification rows that no longer exist**, because revoking
and re-issuing a certification mints a new `cert_id` and `agent_forge_grant` has no foreign key to
`certification`. The 15 grants this run issued resolve on both units.

**Gate 7 discounts those same 34 as revoked in the same run; Gate 9 counts them.** Two gates, one
set of grants, opposite treatment. That is the real finding of this advance, and it is a platform
question rather than a Burkham one.

---

## 57. A rule that reads the world answers a different question each time it is asked

**Recorded 2026-09-13 at Ivan's instruction, from two read-only investigations. The general
shape is real and worth having written down; the specific instance that prompted it did not
happen, and that correction is kept here rather than filed separately.**

### The shape, which is the part worth keeping

**Ten of this system's rules take a database connection.** `generators/validator.py:204`:

    NEEDS_WORLD = {"V2", "V6", "V11", "V28", "V29", "V30", "V31", "V32", "V33", "V34"}

The other rules read a Pack and nothing else, so they answer identically whenever they are
asked. **These ten read the system**, and the system changes between gates - instructions get
authored, registry rows get written, Forges come up, humans discharge obligations.

**So "passed at Gate 2, failed at Gate 9" is not a contradiction for any of these ten, and
somebody will eventually read it as one.** It is the same rule asked a bigger question. At Gate 2
a Pack is a document; by Gate 8 it is a document plus ten authored instructions, a registry, a
manifest and a set of grants - and a rule that checks the world against the document has more
world to check.

**The instance already on the record is V31.** B39 measured it going **NOT_RUN to FAIL** on an
unchanged Pack, purely because `forge_module_registry` rows were written between the two
evaluations - with no rows, every module is unresolved and the rule has nothing to refuse.
`scripts/land_funnelforge_position.py` re-reads V31 at step 5 and reverts both hunks on NOT_RUN
for exactly this reason. **The phenomenon is real, documented, and enforced against in one
place.** What does not exist is a general statement of it, which is what this entry is.

### The correction: it was not V28, and there is no Gate 5.5

Reported: V28 passes at Gate 2 and fails at Gate 5.5, with ten instructions authored in between,
and four library refs unresolved.

Measured, read-only:

    GATE_SEQUENCE          "0","1","2","3","3.5","4","4.5","5","6","7","8","9","9.5",
                           "10","11","12"  -  there is no 5.5, and 5 is followed by 6
    GATE_55_RULES          no such identifier anywhere in the repository
    GATE_2_RULES           no such identifier anywhere in the repository
    V28 right now          PASS  -  "19 of 21 library ref(s) resolve"
    unresolved refs        ZERO

**And V28 could not be moved by Gate 5's output even in principle.** It reads exactly two things:
`pack.market.compliance_surface` and `compliance_library_entry`. It never touches
`venture_forge_manifest`, `agent_forge_grant`, `venture_budget` or `rate_limit_bucket` - every one
of the things Gate 5 writes. The rule is world-reading, and Gate 5's world is not the world it
reads.

**The instinct was right and the subject was wrong**, which is worth separating: *is there a rule
that judges a venture against artifacts created after it last passed?* is a good question with a
real answer, and the answer is V31 rather than V28.

### The compliance library, audited because the question deserved an answer

    packs/compliance-library/*.yaml       19 entry_refs written
    compliance_library_entry              21 rows loaded
    the Pack's citations                  22 surface entries, 21 carrying a ref,
                                          19 distinct, 1 declaring library_gap
    unresolved                            0

All three sets of 19 are **identical**. The two extra library rows - `compliance/ftc-tsr-v2` and
`compliance/nv-two-party-consent-v1` - are Greenstone's and are simply not cited here.
`REFERRAL_FEE_REGULATION` carries `library_gap: true` with no ref, which is the honest
declaration V28 is written to accept.

A near-match scan over every citation found five pairs within 0.75 -
`application-authorization-v1` against `fcra-pull-authorization-v1` at 0.82, and
`reg-z-advertising-boundary-v1` against `tax-advice-boundary-v1` at 0.77, among others - **and
every one of those citations resolves exactly.** They are similar names for genuinely different
obligations, not a rename anybody mis-cited.

**V28 already separates the three cases the question was asking about**, and was built to. On a
real failure it distinguishes **WRITTEN BUT NOT LOADED** (*"run the loader; do not rewrite
these"*) from **NOT WRITTEN ANYWHERE** (*"write the entry, or set library_gap"*), reading the
files rather than the database because *"the database cannot answer that question about itself."*
Its own comment records why: nineteen fully-written entries once sat behind this rule reading as a
documentation gap, when nothing had ingested them.

### And the module column, which needs none of this

`agent_forge_grant.module_id` is **bare**, consistently, and the database enforces it
structurally rather than by convention:

    module_id    text, NOT NULL
    FOREIGN KEY (forge_id, module_id) REFERENCES forge_module_registry(forge_id, module_id)

`forge_module_registry`'s primary key is the **pair**, held as two columns. A qualified
`capitalforge/client_read` could never be written - not because a CHECK would refuse the string,
but because no registry row is named that. Measured across every venture: **51 grants, 12 distinct
module ids, none containing a slash.**

**The qualified form exists only as a dict key**, in `Position.module_trust_tiers` (YAML) and
`AppointedAgent.certified_tiers` (Python), and it is unpacked back into two fields at the write:
`runtime_config.apply` binds `grant.module_id` and `grant.trust_tier` as separate parameters.
Both halves of the map land in the columns they belong to.

### The asymmetry the two reads together exposed

    (forge_id, module_id)  ->  FK to forge_module_registry     ENFORCED
    operation_cert_ref     ->  no FK to certification          NOT ENFORCED
    dept_context_cert_ref  ->  no FK to certification          NOT ENFORCED

**`agent_forge_grant` is structurally guarded on which module a grant names, and unguarded on
which certification it rests on.** That is precisely why the module ids are provably clean and
the cert refs are provably dangling: 34 grants pointing at 20 `cert_id`s that no longer exist,
because reissuing a certification mints a new one. The database would have refused a bad module
and had no opinion about a vanished certification.

That is the root of the Gate 9 block, stated as a schema fact rather than a generator one, and it
is the first thing to rule on before this run moves again.

---

## 58. Neither escape is acceptable, and the reason generalises

**Ruled 2026-09-13 by Ivan, on a blocked run. The ruling is recorded as a ruling; the state of
the run is recorded as measured, and the two differ in one particular, which is noted at the end
rather than hidden.**

### The ruling

Presented with two ways past a rule that was reporting a gap, Ivan refused both:

> **Weakening the rule** makes a citation checker stop checking. **Removing the citations** strips
> authority from prohibitions that are correct - the agent still gets taught the rule, with
> nothing behind it.
>
> **Both amount to making the system stop reporting something true, which is the thing every
> control in it exists to prevent.**

**That sentence is the most portable thing produced this week** and it is recorded here as a
general rule rather than as a decision about one validator. Every gate in this ladder is a
control that reports something true and inconvenient. The two shapes above are the only two ways
a control is ever defeated without anybody deciding to defeat it:

    narrow the rule       it stops asking the question, and reports green because it
                          no longer looks - entry 42's shape, where a relaxed trigger
                          made a documented branch unreachable
    remove the input      the question is still asked and has nothing to answer about,
                          so it reports green for absence - B39's shape, where V31 went
                          NOT_RUN because no registry row existed to refuse

**Green by narrowing and green by absence are indistinguishable from green by compliance in any
count.** That is why B39 built a script whose final step reverts on NOT_RUN rather than accepting
it, and why `test_tier_vocabulary_agrees` reads the constraint out of `pg_constraint` rather than
restating the three names: a test that restates what it checks drifts alongside it and keeps
passing.

**It waits.** That is the ruling, and it is a ruling rather than a stall: the work is identified,
the owner is named, and the run stays where it is until the owner supplies what only they can.
A run parked against a named obligation is a different object from a run nobody is progressing,
and the ledger should be able to tell them apart a month from now.

### Applying it to the live decision, which is where it bites

Run `4198c388` is blocked at **Gate 9**, and two ways past were put forward:

    retire the 34 stale grants                 the grants are dead: already revoked, already
                                               refused at the call path, already discounted
                                               by Gate 7 BY NAME in the same run
    make Gate 9 exclude revoked grants         Gate 7 already excludes them, so this is
                                               "consistency"

**Under this ruling the second is the escape and must be refused.** Gate 9 counting revoked
grants is not obviously wrong - it is the Readiness Gate, and "every grant this venture holds
rests on a current certification" is a defensible thing to assert. Changing it so the count comes
out right is narrowing a rule to get a verdict, which is the first shape above wearing the word
*consistency*.

The first option is not an escape, because it changes the world rather than the question: 34
grants that are genuinely dead stop being held. Gate 9 then asks exactly what it asked before and
gets a different answer because the answer is different.

**The distinction is the whole ruling in miniature.** Both options make Gate 9 pass. One removes
grants that should not exist; the other removes the gate's ability to notice them.

### What this run established, which is more than any before it

    gates 0, 1, 2, 3, 3.5   passed 15:37
    gate 4                  awaiting_human 15:37, then PASSED 17:18 on a recorded review
    gate 4.5                PASSED - the first venture in this system ever to clear it
                            V24 and V13 both green; V13's evidence_basis carried into the
                            run's stored evidence
    gate 5                  PASSED - 12 manifest rows, 15 grants issued INACTIVE,
                            1 budget, 2 rate-limit buckets
    gates 6, 7, 8           passed
    gate 9                  BLOCKED

**First venture through Gate 4, through 4.5, and through 5.** The artifacts hash held at
`356807747d57ee10` across every one of them, which is the property a Gate 10 signature depends on
and the first time it has been observed across a multi-gate advance.

**Nothing is live.** All 49 grants refuse at the call path, by two independent mechanisms -
15 on `GrantNotActivated`, 34 on `NotCertified` - verified by exercising `resolve_grant` against
every one rather than by reading the code.

### Two open items, one owner

**The compliance library has no recorded author.** 19 of its 21 entries are authored by
`smoke-operator-0eda802c@example.invalid`, a smoke fixture; the other 2 name a `human_id` that
resolves to no `office_human` row. **Zero were authored by a person.**

This is the exact failure `humans.attributable_actor` was written to prevent, in its own words:
*"An audit entry signed by a fixture is worthless. Non-repudiation is the whole reason this log
exists."* And the entries are not thin. Each carries 2,000-2,800 characters of interpreted legal
meaning - California's Invasion of Privacy Act read as requiring affirmative consent rather than
disclosure-plus-continuation, a deliberate election to run one over-restrictive rule across
eleven states because *"operational simplicity beats the risk of implementing jurisdiction
detection wrongly"*, a guarantor treated as a separate authorizing party whose file the client
cannot reach.

**That is legal judgment, and V28 passes green over all of it.** The rule checks that a ref
resolves. It has no opinion about who decided what the entry says. This routes to whoever owns
the compliance library, the same destination as `referral_fee_permitted_in_state`.

**Nevada.** `compliance/nv-two-party-consent-v1` exists and is cited by
`funnelforge-approved-send-rules.md`. Burkham's Pack does not cite it - and the entry Burkham
*does* cite for recording, `call-recording-consent-v1`, ends its escalation triggers with:
*"When a call is to be recorded in NEVADA, until the contradiction in the notes is resolved. Two
live artifacts in this portfolio disagree about whether NV is a one-party or all-party state, and
NV is Burkham's first-listed target geography."*

A venture whose first target geography has a live, documented contradiction about its recording
law, and whose Pack does not reference the entry written for it. Same owner.

### What was NOT recorded here, and why

The ruling was given against a described stop at "Gate 5.5, on four missing compliance library
entries naming FCRA 604(f), NRS 200.620 and GLBA." **Measured, none of that is the state of this
system**, and recording it would put in the ledger the one thing entry 56 argues most strongly
against:

    GATE_SEQUENCE            "5" is followed by "6". There is no 5.5
    V28 right now            PASS - "19 of 21 library ref(s) resolve"
    unresolved refs          ZERO, across the Pack's 19 and all 14 distinct refs cited
                             by the 24 operating instructions
    plaid-consumer-data-     absent from the entire repository
    consent-v1
    FCRA 604(f)              present - fcra-pull-authorization-v1 cites
                             15 U.S.C. 1681b(a)(2) and (f), which IS FCRA 604(f)
    GLBA                     present - glba-plaid-connection-v1
    NRS 200.620              the Nevada entry exists; the gap is a citation, above

**The ruling survives the correction intact**, which is why it is recorded and the premise is
not. Its subject is not V28. Its subject is the live Gate 9 decision, where one of the two
options genuinely is the escape it describes - and it would have been taken as the tidy one.
---

## 59. Two real people, and a reviewer capacity computed from four

**Declared 2026-09-13 by Ivan as a standing fact, then audited against every Pack. Recorded as a
class rather than as a finding about one name, because naming Dana would suggest the other three
were checked.**

### The standing fact

**Ivan Green and Ira Green are the only real people.** Every other name appearing as a reviewer in
any Business Pack is invented. This is a fact about the world, not a defect report, and it is
recorded here so that every number derived from a `human_capacity` block can be read against it.

### Every name in every human_capacity block, both ventures

    GREENSTONE
      Ivan    venture_operator     6h   median 4    backup_human: Dana
      Dana    compliance_officer   4h   median 6    backup_human: Ivan     INVENTED

    BURKHAM WICKMONT
      Ivan Green   compliance_officer   6h   median 4   backup_human: Ira Green
      Ira Green    compliance_officer   6h   median 3   backup_human: Ivan Green

**Four entries, two people.** Greenstone's "Ivan" and Burkham's "Ivan Green" are the same person
under two spellings, and neither Pack's entry is joined to an account by anything.

### Everything else in a Pack that names a human

    backup_human          4 occurrences. Dana(1), Ivan(1), Ira Green(1), Ivan Green(1).
                          One of the four names an invented person, and V14 does not care -
                          it checks the field is non-empty and nothing else. Burkham's own
                          Pack says so in its provenance: V14 "passes here on exactly the
                          arrangement it looks like it exists to catch" (B24).
    provenance.           4 occurrences, all "Ivan"/"Ivan Green". Real.
      established_by
    authored_by           a uuid on Pack versions, resolved against office_human. Real.
    workflow blocks       no human is named. Steps carry a position title and a role
                          string; no step names a person.
    signoff / reviewer    no Pack field names a signer. Gate 10 resolves a signer from
      refs                the authenticated account, not from the Pack.

So the Pack's entire human surface is `human_capacity[].human_name`, its `backup_human`, and
`provenance.established_by`. **Three of those ten values name somebody who does not exist**, and
all three are Dana.

### The accounts that actually exist

    office_human rows        232
      origin = 'test_fixture'  231
      origin = 'human'           1   Ivan <ivannextlevel@yahoo.com>, role `ivan`

    holders of `compliance_officer`   ZERO. No account in this system holds it.
    holders of `venture_operator`     107, every one a test fixture
    holders of `ivan`                 125 - one real, 124 fixtures

**There is one real account in The Office, and the role both Packs route every approval to has no
holder at all.**

### So what is Greenstone's V13?

Neither a fail against a fiction nor something that cannot be computed. **It computes cleanly, and
its supply side refers to nobody.**

    projected approvals     160 to compliance_officer  (192 before place_call was removed)
    Dana's coverage         4h x 60 x 0.6 = 144 minutes
    demand                  160 x 6 = 960 minutes
    verdict                 FAIL, "7 times over"

Every one of those numbers is arithmetic on a Pack field. **V13 reads `pack.human_capacity` and
never joins `office_human`** - it has no way to ask whether Dana exists, and it does not ask. The
FAIL is real in the sense that the arithmetic is right, and meaningless in the sense that removing
Dana entirely would change the verdict from FAIL to a different FAIL, never to a truth.

**The same is true of Burkham's PASS, and that is the sharper half.** 280 minutes demanded against
432 available - and the 432 is 12 coverage-hours declared by two `human_capacity` entries, neither
of which is joined to an account. Ivan's real account holds `ivan`, not `compliance_officer`; Ira
has no account at all. **The V13 PASS reviewed at Gate 4 rests on a denominator supplied entirely
by the Pack asserting it.**

This is B22, which has been open since before this week and reads: *"a venture can clear every
gate to 10 with a reviewer who has no account."* It is no longer hypothetical - a venture has now
cleared Gate 4.5 on exactly that arrangement.

### Is a second top-level holder expressible? Yes, and the design says so out loud

**`ivan` is a role key, not an account id.** The constraint is explicit:

    office_human_role_role_check
      CHECK (role = ANY (ARRAY['venture_operator', 'compliance_officer', 'ivan']))
    ROLE_RANK = {"venture_operator": 1, "compliance_officer": 2, "ivan": 3}

**It is not singular by construction**, and three separate pieces of evidence say so:

**The unique index is on the wrong axis to make it singular.**
`ux_human_role_live (human_id, role, COALESCE(venture_id,'*')) WHERE revoked_at IS NULL` prevents
*one person holding one role twice*, not *two people holding one role*. 125 rows hold `ivan` right
now.

**`assert_may_grant` carves out the top role deliberately.** Its rule is *strictly stronger,
except at the top* - and the docstring explains that applying it literally would make `ivan`
"ungrantable and unremovable by anybody", which it calls "not a restriction, it is a single point
of failure with no recovery." **The second holder is the case the exception exists for.**

**The one bar that does apply is that nobody grants themselves**, including `ivan`. Ivan granting
Ira is somebody else granting somebody else, which is exactly the shape the rule wants.

So a second co-equal administrator is expressible, anticipated, and two function calls:
`create_human` (which returns a plaintext token once and never stores it, and stamps
`origin='human'` from the name and address) then `grant_role(role='ivan', venture_id=None)`.

**The finding is not that the system assumes one top-level human.** It is the opposite: the system
was built for two and has been running on one, while 124 test fixtures hold the same top role and
`compliance_officer` - the role that actually does the reviewing in both Packs - has never been
held by anybody.

---

## 60. A role named after a person reads as an impersonation the moment a second person holds it

**Recorded 2026-09-13 by Ivan, ahead of granting the top role to a second holder. The rename is
NOT ruled on here - this entry exists so that it can be ruled on separately, with its cost
measured rather than estimated.**

### The finding

`ivan` is a **role key**. It is not an account, not a user id, and not a reference to a particular
person - `ROLE_RANK = {"venture_operator": 1, "compliance_officer": 2, "ivan": 3}`, and the role
has always permitted multiple holders (entry 59: 125 rows hold it today).

**Correct in the database, wrong on every screen and in every audit row.** A second holder is a
legitimate co-equal administrator and reads as somebody impersonating the founder. The console
prints the role string directly - `console/app/access/people.tsx` renders
`["ivan", "compliance_officer", "venture_operator"]` as the grantable set, and
`console/app/access/page.tsx` explains a refusal with the sentence *"`ivan` - is not a read for a
venture operator."* Every one of those becomes ambiguous the day Ira Green holds it.

### What it costs, stated as the specific harm rather than as untidiness

**`ROLE_RANK` is the only place in this system that decides who may grant what.** `authorize`
compares ranks out of it; `assert_may_grant` compares ranks out of it; `SCOPE_MIN_ROLE` maps
Forge-scope revocation to `"ivan"` by name. There is no second expression of the hierarchy to
check a reading against.

**So a reader auditing whether Ira should hold `ivan` has nothing that distinguishes the role from
the man.** The question "should Ira Green hold ivan" is a question about a rank-3 role, and it
reads as a question about whether Ira should be Ivan. That is not a cosmetic problem: the audit
log's purpose is answering *who decided this*, and a role whose name is a person's name makes
every row about the role look like a row about the person.

### What a rename would touch - measured 2026-09-13, not estimated

    DATABASE
      office_human_role.role                125 live rows
      office_human_role_role_check          CHECK naming all three roles
      revocation_revoked_by_role_check      CHECK naming all three roles
      db/versions/0006_governance.py        declares the role in a constraint
      db/versions/0010_humans.py            declares the role in a constraint
      audit_log.subject                     0 rows carry the string
      revocation.scope                      0 rows carry it (scope is a different vocabulary)

    PYTHON (broker/)                        13 occurrences across 7 modules
      broker/revocation.py                  ROLE_RANK and SCOPE_MIN_ROLE - the source of truth
      broker/humans.py                      authorize, assert_may_grant, the docstrings
                                            that explain the top-role exception
      broker/app.py, access_overview.py, sync_roster.py, budget.py

    TESTS                                   ~50 occurrences across 12 files
      test_access_api.py (18), test_access_overview.py (12), test_revocation_console.py (7)

    CONSOLE (console/app/)                  12 occurrences in 5 files
      access/forms.tsx                      const ROLES = [...] - a hardcoded second copy
                                            of the vocabulary, which is its own finding
      access/people.tsx                     a third hardcoded copy in a render loop
      access/page.tsx, access/overview.tsx, provisioning/[venture]/page.tsx

**Two things in that list are worth separating from the rename question.**

`console/app/access/forms.tsx` and `people.tsx` each hold their **own hardcoded list of the three
roles**. That is the same defect `tests/contract/test_tier_vocabulary_agrees.py` was written to
catch for tiers - a vocabulary restated in a second place, free to drift from the constraint that
enforces it - and it exists here in *three* places (the CHECK, `ROLE_RANK`, and two TSX arrays)
with nothing comparing them. **A fourth role added to `ROLE_RANK` today would be ungrantable from
the console and nothing would say so.** That is a finding on its own and does not depend on the
rename.

The second is that a rename is a **two-CHECK, 125-row migration on the table that governs
authority**, and the window between dropping the old constraint and writing the new value is a
window where the authority vocabulary is in two states. It is not hard; it is the one table where
"not hard" is not the standard.

### Not ruled on

**Ivan's instruction is explicit: do not rename it.** A change to the one table that governs
authority gets its own decision, made deliberately, not taken as a side effect of adding a second
administrator. This entry records the cost so that decision can be made on measurement.

What is decided is the narrower fact: **`ivan` names a rank, a second holder is legitimate, and
anybody reading an audit row or an access screen after today should read it that way.**
## 61. The tier test has a sibling, and the sibling had eight copies to compare rather than two

**Built 2026-09-13 at Ivan's instruction, as the acknowledged sibling of
`tests/contract/test_tier_vocabulary_agrees.py`. Recorded because the count found while
building it is larger than the count that motivated it.**

Entry 60 named four copies of the role vocabulary. **Measured while writing the test, it is
five - and a second vocabulary, the scope-to-authority mapping, is written down three more
times.**

    THE ROLE VOCABULARY                     5 copies
      office_human_role_role_check          the database's copy
      revocation_revoked_by_role_check      the database's SECOND copy, found while writing
      broker.revocation.ROLE_RANK           the source of the hierarchy
      console/app/access/forms.tsx  ROLES   hardcoded, renders the grant form's dropdown
      console/app/access/people.tsx         hardcoded, renders the filter dropdown

    THE SCOPE-TO-AUTHORITY MAPPING          3 copies
      broker.revocation.SCOPE_MIN_ROLE      the rule that is enforced
      console/app/revocations/form.tsx      SCOPES[].authority
      console/app/revocations/page.tsx      SCOPES[].authority

**Nothing compared any of the eight.** `tests/contract/test_role_vocabulary_agrees.py` now
compares all of them, reading each out of where it lives rather than restating it.

### Three drift costs, and they are not the same cost

**A role in `ROLE_RANK` and absent from the console is ungrantable, silently.** The grant form
renders `ROLES`; a role missing from that array has no option in the dropdown. The API accepts
it, the UI never offers it, and the only route to holding it is a direct database write - which
is precisely what every rule in `assert_may_grant` exists to prevent. This is the case entry 60
predicted and the reason the test was asked for.

**A role in `ROLE_RANK` and absent from a CHECK fails at write time**, mid-grant, as a raw
`IntegrityConstraintViolation` out of `grant_role`. Late-reporting, the shape entry 42 and the
tier test both record - and now doubled, because `revocation_revoked_by_role_check` is a second
constraint that can drift independently. **A role addable to `office_human_role` and not to
`revocation` is a role somebody can hold and cannot revoke with.**

**A drifted `authority` in the revocations console does not crash, and is the worst of the
three.** That page tells an operator which role may revoke at each scope, printed beside the
button that does it. Drift one way promises an authority the server refuses; the other way
under-states what a scope requires, and somebody plans around a restriction that is not there.
**No exception is raised in either direction - a person is simply told something untrue about a
destructive action.**

### Read, not restated - including the TypeScript

A test that hard-coded the three names would pass while every copy drifted together, which is the
failure it exists to prevent. So the constraints come out of `pg_constraint`, the constants by
import, and the console arrays out of the TSX source, parsed.

**Parsing a TypeScript literal from a Python test is crude and it is the crude thing that reads
the file the browser actually gets.** Each pattern is anchored on something specific to its file -
`const ROLES = [...]`, `[...].map((role)`, `scope: "x" ... authority: "y"` - rather than on
"an array", because a loose pattern that matched some other array would compare the wrong thing
and still pass. Each also asserts its pattern matched at all, so a rewritten console fails the
test rather than quietly comparing nothing.

### Verified by breaking it

**A test that has never failed proves nothing**, so both directions were checked against
deliberate drift before the test was committed:

    removed "ivan" from forms.tsx ROLES
      -> access/forms.tsx does not offer ['ivan']. The role exists and the console cannot
         grant it, so the only route to holding it is a direct database write.

    changed venture-scope authority to venture_operator in revocations/page.tsx
      -> revocations/page.tsx tells the operator that 'venture' revocation requires
         'venture_operator'; the server enforces 'compliance_officer'. This one does not
         crash - it misinforms somebody standing in front of a destructive action.

Both files restored; the test passes 6 of 6 against the tree as it stands.

### What this does not do

It does not rename `ivan`, and it makes the rename no easier or harder. Entry 60 measures that
cost and Ivan has reserved the decision. What this test changes is that the five copies can no
longer disagree *silently* - which is a precondition for a rename rather than a substitute for
one, because a rename is exactly the operation that would leave copies disagreeing.

---

## 62. B22 is not a mismatched string. There is no join, in either direction

**Corrected 2026-09-13 by measurement, before renaming anything. The correction is larger than
the thing it corrects, which is why it gets an entry rather than an amendment.**

### What B22 was thought to be

B22 reads *"a venture can clear every gate to 10 with a reviewer who has no account."* Entry 59
found the shape live: `Ivan` on the account row, `Ivan Green` in Burkham's Pack. The obvious
reading is that a Pack-to-account lookup matches on display name and these two spellings miss
each other - a mismatched string, fixed by an UPDATE.

**Measured, that lookup does not exist.**

    anything joining human_capacity.human_name -> office_human.display_name   NONE
    display_name used as a lookup key (WHERE display_name = %s)               NONE

Every one of the eight `display_name` references in `broker/` is a SELECT **projecting** it for
display, reached through `human_id` - `revoked_by_name`, `started_by_name`, `reported_by_name`,
`written_by_name`. Not one query finds a person by name.

### The actual shape

**Two halves that have never been required to meet.**

    V13 / the Pack side        reads pack.human_capacity[].human_name, role, coverage_hours
                               and median_review_minutes. Never touches office_human. Has no
                               way to ask whether the person exists, and does not ask.

    authentication / the       resolves a bearer token to a human_id, reads roles live from
    account side               office_human_role. Never reads a Pack. Has no way to ask what
                               the Pack expects of this person, and does not ask.

There is no column, no query and no rule connecting them. **A Pack's reviewer capacity is an
assertion the Pack makes about the world, and nothing in this system is responsible for checking
it.** That is why Burkham's V13 PASS - 280 minutes against 432, reviewed and attested at Gate 4 -
rests on twelve coverage-hours declared by two entries that correspond to no account holding the
role they name, and why it would read exactly the same if both names were invented.

**That is a bigger finding than a spelling.** A mismatched string is a bug with a fix. Two
subsystems that have never been required to agree is a missing requirement, and no amount of
renaming produces one.

### So what do the display names actually buy? Legibility, not function

**Recorded because the next person to notice the mismatch will rename a row expecting it to
connect something.** It will not. Nothing reads the result.

Ivan's row was left as `Ivan` deliberately, on his ruling: **making two unconnected strings look
alike reads as a link that is not there**, which is worse than leaving them visibly different.
Ira Green's account was created matching the Pack because there was no history to contradict, not
because matching does any work.

The cost of renaming Ivan's row was measured first, and it is an UPDATE rather than a migration -
which is the answer that would have made it tempting:

    office_human.display_name            1 row     the only updatable occurrence
    business_pack.parsed / yaml_source   18 rows   immutable - a published version is frozen
    audit_log.subject                     3 rows   append-only by design
    provisioning_gate_result.evidence    11 rows   append-only
    provisioning_gate_result.reason       3 rows   append-only, "reviewed by Ivan: ..."
    docs/decisions.md                    15 refs   prose

**The three gate results are the Gate 4 reviews at Pack 0.6.0, 0.7.0 and 0.9.0**, frozen as
*"reviewed by Ivan:"* because `record_human_review` interpolates the display name into the reason
at write time. That is correct: the record says what was true when the act happened, and
rewriting it would falsify an attestation. So one row is updatable and everything else is history
that should not move - meaning a rename makes an account disagree with its own audit trail, in
exchange for nothing.

### The second administrator exists

    human_id      fdae58a6-d786-4da7-be8d-1c7269839898
    display_name  Ira Green
    email         green_ira@yahoo.com
    origin        human           (classified, not asserted: the name is not prefix-hex
                                   and the address does not end .invalid)
    role          ivan, venture_id NULL - every venture
    granted_by    78869b20-e83a-4fbc-90bc-d58560f79bfb   (Ivan)

`assert_may_grant` permitted it under the top-role carve-out - equal-rank granting, allowed only
where nothing outranks, which entry 59 records as the case that exception exists for - and the
self-grant bar was clear because the target is somebody else. **Every role anyone holds was
granted by somebody else, and the audit log says who.**

The token was printed once and written nowhere; only its hash is stored.

**This does not close B22.** Ira holds `ivan`, not `compliance_officer`, and V13 matches the
Pack's role string rather than a rank - so a second real administrator changes nothing about a
denominator the Pack supplies by asserting it. **What changed is that the system now has two
people who can act in it, and 124 test fixtures still hold the same top role.**

---

## 63. A gate whose blocking condition is `if active:` passes when there is nothing to check

**Found 2026-09-13 by measurement. The shape Ivan named is exactly right and the mechanism is not
the one described, so both are here - the finding is sharper than either version.**

**Corrected 2026-09-14 by Ivan, in place rather than in a new entry.** The finding below was
argued from one measurement and an invented pair: *a venture with fifty correctly inactive grants
and a venture with fifty revoked ones both produce PASSED.* The pair has since occurred, on this
venture, eighteen hours apart. The argument is replaced by the demonstration - same gate, same
code, same verdict, opposite inputs - and the entry now quotes the second reason line instead of
imagining it.

### What Gate 7 did, twice

    13 Sep   passed   "0 grant(s) registered, none active;
                       34 activated grant(s) discounted by a live agent revocation"
             evidence {grants: 0, already_active: 0, revoked: 49, active_but_revoked: 34}

    14 Sep   passed   "49 grant(s) registered, none active"
             evidence {grants: 49, already_active: 0, revoked: 0, active_but_revoked: 0}

**The second is the verdict this gate exists to give**, and it took the revocations being lifted
(entry 64), the grants being re-issued against a republished Pack, and forty-nine activations
being returned to inactive by hand (entry 74's `deactivate`) to produce it. Forty-nine grants
examined, none active before Gate 11, nothing discounted. **The first is the same word over an
empty set.**

`_gate_7` exists to assert *grants are issued inactive and activated only against a valid
sign-off*. Its whole force is one branch:

    if active:
        return GateOutcome("7", BLOCKED, f"{len(active)} grant(s) are already active
                           before Gate 11 ...")

`active` is grants that are activated **and not covered by a revocation**. Measured on this
venture on the 13th:

    grants total                                          49
    covered by a live revocation                          49
    NOT covered - the set Gate 7 actually examines          0

**Every grant this venture holds is under a live agent-scope revocation, so the set Gate 7 asks
its question of is empty, and an empty set cannot contain an active grant.** The gate passed
because it had nothing to look at.

**"Zero of zero" and "all correct" are the same verdict here, and now both have been recorded.**
The verdict is identical: `PASSED`, from the same branch, on the same line of the same function.
**The whole difference is one integer in a sentence** - `0 grant(s) registered` against
`49 grant(s) registered` - because `len(live)` is interpolated into the reason and compared to
nothing. The evidence block is better than the message: it carries `grants`, `already_active`,
`revoked` and `active_but_revoked` separately, and its own comment says why: *"'0 active' on a
venture holding activated grants is a claim that has to say why it is true."*

**And that integer is the only place the distinction exists.** No rule compares it. The gate does
not assert it examined anything; the run history renders a verdict and a reason; a reader who
wants to know whether Gate 7 looked at a grant has to open the evidence JSON and already know
which field answers the question. **A correct verdict and a vacuous one are typographically
adjacent and nowhere separated** - that is the finding, and it survived the state that made it
visible being repaired.

### What would have caught it: nothing

The docstring names the test that matters - *"the one asserting a live active grant still BLOCKS:
without it this is a gate that passes."* That test exists and it is the right test. It proves the
gate refuses when handed something to refuse.

**Nothing asserts the gate was handed anything.** There is no check anywhere that `len(live) > 0`
before a PASS is recorded - no assertion that a gate which examines grants examined any. So the
one state the existing test cannot distinguish is the one this run is in.

**This is the third instance of one shape this week.** Entry 49's lesson was a CHECK that reports
at write time; B39's was V31 reporting NOT_RUN because no registry row existed to refuse; this is
a gate reporting PASSED because no unrevoked grant existed to block on. **Green by narrowing,
green by absence, green by compliance - entry 58 names the first two and this is the second one
again, in the gate that stands between a grant and production authority.**

### The 34, measured - and not what was described

Recorded because the description and the measurement disagree in every particular, and the
measurement is the more interesting of the two.

    described                            measured
    ---------------------------------    ------------------------------------------------
    bootstrap residue from August        granted 3 - 13 SEPTEMBER 2026. No August rows.
    eight modules                        TEN distinct modules
    eleven forge-pairs                   TEN (forge, module) pairs, all capitalforge
    no live Pack operates them           ALL TEN are operated by a live position in the
                                         current Pack. Not one is orphaned.
    not a certification gap              correct - this part holds

**They are not grants for a world that is not declared. They are duplicates of the world that
is.** Twenty-nine of the 34 hold a live unit-A certification for their exact (agent, forge,
module) triple; the current run then issued a *second* grant for the same pair, inactive, with
fresh certification refs. The same agent and module appears twice at two tiers - Alistair Fenlor
on `submit_application` at both `propose` and `auto_execute`, and so on across all eleven agents.

**The cause is that `bootstrap-phase0` writes grants already activated**
(`broker/bootstrap_phase0.py:538`, `activated_at` set to `now()` in the INSERT), so every Phase 0
grant bypasses Gate 11 by construction. `runtime_config.apply` later writes its own grant for the
same pair under a different `grant_id`, correctly inactive. Two writers, two id schemes, no
reconciliation.

The five exceptions are real: Amelie Wystan, Brina Arvane (twice) and Cedric Noren, all
`engineering` - a department holding no unit-B certification and named by no position. **Those
four rows are the only genuinely orphaned grants in the venture**, and they are the shape the
description was reaching for.

### Left open for the next session, deliberately unanswered

The question asked was about shifts - that `_gate_7` activates grants for the shifts in the plan
and the plan carries none. **`_gate_7` does not read shifts, activate anything, or mention a
plan**; `grep` for shifts in it returns nothing, and Gate 11 is what activates. So that question
has no subject here.

**The question its shape points at does have one, and it is better:** why is every grant in this
venture covered by a live agent-scope revocation, and what should a gate mean when its entire
input set is revoked? Gate 7 currently answers *pass*. Gate 9 answers *block* over the same rows.
**Two gates, one set of grants, opposite verdicts** - which is the disagreement first noted when
this run stopped, now with a measured cause rather than a suspected one.

That is upstream of both gates and it is where a third path most likely is. Not answered tonight.

**Answered on the 14th, and the disagreement outlived the answer.** Entry 64 lifted the
revocations; there are none live on this venture now. Gate 7 passes over forty-nine real rows and
Gate 9 still blocks - over four of them, not forty-nine (entry 72). **The two gates never
disagreed about the same thing:** Gate 7 asks whether a grant is active before Gate 11, Gate 9
asks whether it is certified, and a grant can honestly be both inactive and uncertified. The
suspected third path was not there. What was there is the sentence above it.
---

## 64. "All 34" was a count of grants, and lifting all of them would have undone yesterday's work

**Recorded 2026-09-14 at Ivan's instruction, as a correction to his own ruling, caught in the
gap between the ruling and the act.**

The instruction was *"reinstate all 34 revocations."* There are **eleven**.

    34   grants DISCOUNTED by revocations - the number Gate 7 reports
    20   live revocations: 11 `agent` + 9 `agent_module`
    11   the departure cascade, the set actually ruled on

**34 is a grant count wearing a revocation's name**, and it had already been measured three
times before the ruling used it - each time as the number of grants Gate 7 sets aside, never as
a number of revocation rows.

### Why "all" was the dangerous half, not "34"

A miscount that reinstates too few is a short day's work. **This one would have reinstated too
many.** The other nine live revocations are `agent_module`, issued by Ivan himself at 15:44 the
previous day with `module_id` and `forge_id` populated - the deliberate stops on modules that no
longer resolve.

**The discriminator in the ruling excludes them by its own logic.** Ivan's stated reason for
lifting was that *a revocation asserting a fact about the world that did not occur is the thing
being corrected* - the eleven each claim the agent "is no longer in the Village roster", and that
was false when written. **The nine make no claim about the world at all.** They name a module and
stop it. There is nothing in them to be false.

So "all" would have lifted, in the same transaction and under the same reason text, nine
revocations whose reason text does not match that reason. **They were left standing**, and this
entry exists so that the gap between what was said and what was done is on the record rather than
inferred from a count.

---

## 65. Recognition had a way back that had been used. Authority had one that had never run

**The finding the reinstatement exposed, recorded 2026-09-14.**

    office_identity_reinstated       54 events, all at 15:37 on 13 September 2026
    identity status now              54 active, 0 suspended
    revocations reinstated           0 of 20 - `revocation.reinstate` had NEVER been called
    the eleven revoked agents         all 11 held an ACTIVE identity throughout

**Eleven agents held an active identity and a live revocation at the same time, for three days.**
The Office recognised them and refused them. Entry 51 built `roster.reinstate_identity` because
the suspension half of the departure cascade had no inverse; what it did not say is that the
other half had an inverse nobody had ever exercised.

**Two doors, both built, one worn and one unopened.** `revocation.reinstate` has existed since
before this week: named human, documented reason, same authority as revoking at that scope, a
second human at the wide scopes, all NOT NULL-checked by the schema so that *"a reinstatement
cannot be an anonymous UPDATE."* Complete, tested, and never used on a real row until today.

**A path that has never run is a path nobody has checked.** It worked - eleven rows, first
attempt - but that was not knowable in advance, and it is the shape entry 51 recorded from the
other side: an absence that stays invisible until the day somebody needs the door.

The asymmetry is not that one half lacked a mechanism. **It is that one half was reversed and the
other was not**, for three days, while both mechanisms existed and only one had ever been
touched.

---

## 66. What the reinstatement is, and what it is not

**Ruled 2026-09-14 by Ivan. Recorded because the act it most resembles is one the system is built
to refuse.**

### What it is not

`tests/contract/test_departure_revokes.py::test_a_returning_agent_does_not_get_their_grants_back`
is **correct and this is not its case.** That test protects a real departure followed by a real
return: somebody left, lost their authority, came back, and must not find their grants waiting.
Entry 51's docstring says the same thing at length - *reinstating an identity is not re-granting
authority*, because the two are one keystroke apart.

**Nobody departed here.** The eleven revocations were written by `sync_roster` against a roster
the Village had never supplied, in the run recorded as entry 47. The control read its input
correctly and its input was false.

### What it is

**A correction to an assertion about the world, not to the authority that acted on it.** Each of
the eleven rows says the agent *"is no longer in the Village roster."* That sentence was untrue
when it was written. Agent scope was the right scope, `sync_roster` was the right caller, the
cascade is the right behaviour - and the fact it rested on did not happen.

**And the system cannot tell the difference.** Measured before ruling:

    the reason text          identical across all 11 but for the name. Records the
                             mechanism faithfully and the provenance not at all
    blast_radius             10 keys, every one about EFFECT - agents, grants, ventures,
                             in_flight_calls, shifts_today. Nothing about which roster,
                             which sync run, or that 186 agents departed at once
    the audit trail          `village_roster_imported` fired twice that day; the row
                             records that an import happened, not what it contained
    the reinstatement        `reinstate_identity` audits the act and the reason, and
      record                 carries no marker distinguishing a correction from a return

**Nothing in the revocation rows, the audit trail or the reinstatement records says which kind of
cascade this was.** The only evidence that these were erroneous lives outside the database.

**So this is a judgment with a name attached, and it is recorded as one.** The reason written onto
all eleven rows says so in terms: the cascade's origin, that no agent departed, that the 54
identities were reinstated on 13 September and these are the other half of the same correction,
and that nothing in the system distinguishes the two cases. A reader finding these rows in a year
gets the reasoning, not just the outcome - which is the most the system can offer, because the
check it would need does not exist.

---

## 67. Nineteen triples, forty-nine grants, and thirty that can never be selected

**The larger finding, and it only surfaced once the revocation layer was cleared out of the
way.**

    grants for burkham-wickmont              49
    DISTINCT (agent, forge, module) triples  19

`resolve_grant` selects one row per triple:

    WHERE g.office_agent_id = %s AND g.forge_id = %s
      AND g.module_id = %s AND g.venture_id = %s
    ORDER BY g.granted_at DESC
    LIMIT 1

**The newest row wins, and the newest rows are the fifteen Gate 5 issued at 17:18 - all
inactive.** Every older grant sharing a triple with one of them is unreachable: it cannot be
selected at any tier, by any caller, ever, while the newer row exists. Measured after the
revocations were lifted:

    15 inactive   -> GrantNotActivated     correct; Gate 11 has not run
    30 activated  -> GrantNotActivated     the NEWER row answered, not these
     4 activated  -> NotCertified          the only triples with no newer duplicate

**Thirty activated grants are permanently unreachable and nothing anywhere says so.** They are
not revoked - the revocation table is now clear of them. They are not expired; there is no such
state. They are not marked superseded; there is no such column. `agent_forge_grant` has no
uniqueness constraint on the triple, so two live rows for one triple is a legal state the schema
invites.

**A grant that can never be selected looks identical to one that is simply not chosen yet.** Both
are rows with `activated_at` set, a valid tier, and resolvable columns. The only difference is
that a newer sibling exists, and nothing reports siblings.

### What would have caught it: nothing

There is no constraint, no validator rule, no gate and no test that counts grants per triple.
V31 reads the registry; Gate 7 reads revocations; Gate 9 reads certification refs. **None of them
asks how many grants exist for one (agent, forge, module).** The duplicate rows pass every check
because every check is asking a different question.

### Why it surfaced today and not on any previous day

**Because the revocation layer was masking it.** Until this morning all 49 grants were covered by
a live revocation, so every `resolve_grant` call refused at the revocation check before reaching
the activation check - and every grant, reachable or not, produced the same refusal. Lifting the
eleven cascade revocations dropped coverage from 49 to 27 and let the calls run far enough to
show which row actually answers.

**Clearing one layer is how the layer beneath it becomes legible.** The same shape as entry 52,
where nine certifications changing tier left the artifact hash unmoved: a defect underneath a
sufficient blocker is invisible for exactly as long as the blocker holds.

### Where the duplicates come from

Two writers, two id schemes, no reconciliation. `runtime_config.apply` derives a deterministic
`grant_id` from (venture, agent, forge, module) and upserts on it; `bootstrap_phase0` writes its
own grant with its own id for the same triple. Neither knows about the other, and the table
permits both.

**`apply`'s upsert is also narrower than it looks:**

    ON CONFLICT (grant_id) DO UPDATE SET trust_tier = EXCLUDED.trust_tier

Only the tier is refreshed. A re-run updates the tier of a grant it already owns and **does not
refresh its certification refs** - which is why re-running the pipeline would not repair a single
one of the 34 dangling refs at Gate 9.

---

## 68. Re-provisioning refreshes the tier and leaves the certification refs exactly as they were

**Recorded 2026-09-14. The cheap fix for Gate 9 does not work, and nothing anywhere says so.**

`generators/runtime_config.apply` writes a grant's two certification references as subselects,
resolved against the certification table **at INSERT time**:

    operation_cert_ref    = (SELECT cert_id FROM certification
                              WHERE unit='A' AND office_agent_id=… AND forge_id=… AND module_id=…)
    dept_context_cert_ref = (SELECT cb.cert_id FROM certification cb
                              JOIN office_agent_identity i ON i.department = cb.department
                              WHERE cb.unit='B' AND i.office_agent_id=… AND cb.forge_id=…)

And then, one line later:

    ON CONFLICT (grant_id) DO UPDATE SET trust_tier = EXCLUDED.trust_tier

**Only the tier.** A second `apply` against a grant that already exists refreshes its trust tier
and touches nothing else - not the certification refs, not `granted_by`, not `granted_at`.

### Why this matters right now

Gate 9 blocks `4198c388` on 68 of 98 certification units, every one of them a reference to a
`cert_id` that no longer exists. **The obvious remedy is to re-run the pipeline** - the refs were
written by `apply`, `apply` resolves them from live certifications, so running it again should
pick up the current rows.

**It will not.** Every one of the 34 dangling refs belongs to a grant that already exists, so
every one takes the `DO UPDATE` branch, and that branch sets `trust_tier` and returns. The run
would report grants written, the tiers would be correct, and all 68 units would still read
`never_certified`.

**Measured:** the same subselects `apply` uses resolve today for **45 of the 49** grants - the
four exceptions being the `engineering` agents with no certification to point at. The data to
repair the refs is there and in reach of the system's own query. The upsert simply does not ask
for it.

### The shape

`apply`'s docstring opens *"Write the config. Idempotent: re-running changes nothing and adds
nothing"*, and it is telling the truth about the property it was written to guarantee - no
duplicate rows, no duplicate side effects. **Idempotent is not the same as convergent.** Running
it twice does not produce a second grant; it also does not bring an existing grant into agreement
with the world it was derived from.

The narrow upsert was almost certainly right when written: refreshing `granted_by` on a re-run
would rewrite who granted something, and refreshing `granted_at` would erase when. The refs are
the case that does not fit that reasoning - they are not history, they are pointers, and a
pointer that is never refreshed is one that can only degrade.

### What would have caught it: nothing

There is no test asserting that a second `apply` reconciles cert refs, because there was no
reason to write one until a certification's id could change - and until the table was truncated
(entry 47), it never could. `record_result` upserts on the natural key, so a reissue preserves
`cert_id`, and refs would have stayed valid forever under every path the system actually
supports.

**The gap is only reachable through a route nothing sanctions**, which is why it sat unnoticed
and why the FK that would have refused the truncation is still the first fix. Recorded separately
from Gate 9's ruling because it is true regardless of what is decided there: **anybody reaching
for "just re-provision" should know it changes one column.**

---

## 69. Revocation has no grant-level granularity, so retiring a superseded grant always stops its replacement

**The structural fact underneath two separate mistakes, recorded 2026-09-14 after the second one
was found and lifted.**

### The fact

`revocation` has these columns and not one more that matters here:

    revocation_id, scope, office_agent_id, forge_id, module_id, venture_id,
    reason, revoked_by, revoked_by_role, revoked_at, reinstated_at,
    reinstated_by, reinstatement_reason, blast_radius, reinstatement_second_human

**There is no `grant_id`.** A revocation names a *triple* - `(agent, forge, module)` - at its
narrowest scope, and `agent_forge_grant` has no uniqueness constraint on that triple. So the
narrowest stop the system can express is still wider than the object somebody usually has in
mind.

**Where 49 grants occupy 19 triples, a revocation aimed at one row lands on three.**

### Both mistakes are the same mistake

    11 Sept 13, 12:02   sync_roster, agent scope, 11 revocations
                        intended: stop agents who departed
                        actually: stopped agents who had not departed, because the
                        roster it read was a test fixture (entry 47)

     9 Sept 13, 15:44   Ivan, agent_module scope, 9 revocations
                        intended: stop superseded bootstrap grants
                        actually: stopped every grant on those triples, including
                        NINE Gate 5 grants for modules the Pack operates -
                        client_read, client_read_pii, statement_pull,
                        portfolio_health, restack_recommend,
                        compliance_manifest_assemble

**Both are a revocation doing more than its author meant because it names a broader object than
the one in mind.** In the first the breadth was the agent; in the second it was the triple. In
neither case did the system object, because in both cases the revocation did exactly what a
revocation at that scope does.

**The author of the second was Ivan, and the read caught it rather than the system.** That is
worth stating plainly: the nine sat live for a day, covering 27 grants, and nothing anywhere
reported that nine of them were live Gate 5 grants the Pack depends on. It surfaced only because
a read was run before a third revocation was issued on top of them.

### Why the obvious next act was impossible

The act under consideration was retiring the 30 superseded duplicates by revoking them. **It
cannot be done.** Every one of the 30 shares a triple with a Gate 5 grant, and a revocation
addressing that triple stops both. Retiring the old row *is* stopping the new one - not as a side
effect, but as the same operation, because the vocabulary has no way to distinguish them.

Measured before ruling: of the 15 duplicated triples, **nine were already covered** by the
September 13 revocations, and on all nine every row read `covered=True`, the inactive Gate 5
grant included. A second revocation would have been a duplicate row over an identical grant set -
`covered_grants` is existence-based, so it would have changed nothing and added noise to an audit
trail that had already misled once.

### What the schema is missing, stated as a question rather than a design

A grant can be **created**, **activated** and **revoked**. It cannot be **superseded** - and
superseding is exactly what `runtime_config.apply` does to a bootstrap grant every time it writes
a second row for the same triple, under a different `grant_id`, from a different writer. The
schema invites the state and has no word for resolving it.

`agent_forge_grant` carries `granted_at`, `activated_at` and a generated `is_assignable`, and no
lifecycle column at all. `revoked_at` existed and was dropped by migration 0036 (B37). So the two
mechanisms available are a revocation, which says *authority withdrawn* about rows holding none
that can be exercised, and a `DELETE`, which says nothing at all and leaves no record.

**Neither is honest**, and choosing between them is the open question. Recorded here rather than
answered.

### State after both lifts

    revocations        agent 0 live / 11 lifted; agent_module 0 live / 9 lifted
    grants covered     0 of 49
    resolve_grant      15 triples -> GrantNotActivated   (Gate 11 has not run)
                        4 triples -> NotCertified        (engineering, no certification)
    callable now       ZERO
    Gate 9             68 never_certified, 30 certified - UNCHANGED by any of this

**Every revocation in this venture is now lifted and nothing is callable**, which is the correct
state: the fifteen await Gate 11, the four await a certification, and Gate 9 still blocks on
references to certifications that were deleted. Clearing the revocation layer changed what is
*visible*, not what is *permitted*, and that was the point of clearing it.
## 70. The lifts bought legibility, not permission

**Recorded 2026-09-14, after twenty revocations were lifted across two rulings and nothing
became callable.**

    before          49 of 49 grants covered by a live revocation
    after           0 of 49
    callable        ZERO, before and after

**Not one agent gained a capability.** Every grant still refuses: fifteen on
`GrantNotActivated` because Gate 11 has not run, four on `NotCertified` because the
`engineering` agents hold no certification. The revocations were removed and the answer did not
change.

**What changed is that one answer became four.**

    before     every call refused at the revocation check, first in the chain.
               One verdict - "covered by a live revocation" - over four distinct causes:
               a false departure cascade, a mis-scoped module stop, an ungate-11'd grant,
               and a missing certification.

    after      each triple reports the reason that actually applies to it.

**A control that refuses early refuses truthfully and uninformatively.** `resolve_grant` checks
revocation before activation and before certification, which is the right order - a revoked agent
should not have its certification discussed - and it means a wide revocation masks everything
beneath it for exactly as long as it stands.

### The nine were invisible inside the eleven

**This is what the entry is for.** The nine `agent_module` revocations of 13 September stopped
nine live Gate 5 grants, and that was undetectable while the cascade's eleven agent-scope
revocations covered the same rows. Two revocations covering one grant produce one refusal.
Lifting the eleven dropped coverage from 49 to 27 and left the nine standing alone, where a
single read found them in one query.

**Neither ruling could have been made without the one before it.** The order was not planned that
way - the eleven were lifted because the cascade was false, and the nine surfaced as a
consequence.

### The general form

**Clearing a sufficient blocker is how the layer beneath it becomes legible**, and it is the
third time this week:

    entry 52    nine certifications changed tier; the artifact hash did not move.
                The flattening was invisible while the layer above it collapsed everything
    entry 67    thirty unreachable grants, invisible while every grant was revoked anyway
    this        four causes wearing one verdict

**The cost of an early, wide refusal is that it is a correct answer which prevents a better
one.** Nothing here argues for reordering `resolve_grant` - checking revocation first is right -
only for knowing that a system in that state is telling you less than it knows.

---

## 71. The refs repaired, and the upsert taught to maintain them

**Ruled and built 2026-09-14. A pointer repaired to a fact that is true today, and the reason it
will not need repairing again.**

### The repair

Burkham's 49 grants carried certification refs written at INSERT time and never refreshed. After
`certification` was truncated by an unisolated test run (entry 47) and rebuilt, 34 of them
pointed at `cert_id`s that no longer existed, and Gate 9 blocked on **68 of 98 units**.

**The repair is not a new mechanism.** It is `apply`'s own subselects - the same SQL that wrote
the refs originally - run against today's certifications:

    operation_cert_ref    = (SELECT cert_id FROM certification
                              WHERE unit='A' AND office_agent_id = g.office_agent_id
                                AND forge_id = g.forge_id AND module_id = g.module_id)
    dept_context_cert_ref = (SELECT cb.cert_id FROM certification cb
                              JOIN office_agent_identity i ON i.department = cb.department
                              WHERE cb.unit='B' AND i.office_agent_id = g.office_agent_id
                                AND cb.forge_id = g.forge_id)

    before   unit-A resolving 15/49   unit-B 15/49
    after    unit-A resolving 45/49   unit-B 45/49   NULL 4
    refs naming a different triple:  0

**The four that resolve to NULL are the `engineering` agents** - Amelie Wystan, Brina Arvane
twice, Cedric Noren - who hold no certification. NULL is the correct answer for them, and
`resolve_grant` reports it as `NotCertified` naming which half is missing rather than silently.

**Gate 9: 68 never_certified -> 8.** It still blocks, on those four grants' two units each, and
that is now a real certification gap rather than a bookkeeping artefact.

### The caveat, stated because it is the whole of what this is not

**This attaches each grant to a certification whose triple matches the grant. It cannot confirm
the original ref aimed at the same fact, because those rows are gone.** Every certification in
the database was written at 11:28 on 13 September, in one batch, after every one of the 34 grants
was created. There is no history to compare against.

So it is a pointer repaired to a fact that is true today: this agent *is* certified for this
module, now, at this tier. It is not a restoration of what the pointer said before, and nothing
can be. A reader who needs "what was this grant issued against" will not find it here.

**Verified as far as it can be:** zero refs name a different triple than their grant's own, so
nothing was attached to the wrong certification. That is the strongest check available and it is
weaker than provenance.

### The upsert, so this does not recur

    ON CONFLICT (grant_id) DO UPDATE SET trust_tier = EXCLUDED.trust_tier      -- was
    ON CONFLICT (grant_id) DO UPDATE SET                                        -- now
      trust_tier            = EXCLUDED.trust_tier,
      operation_cert_ref    = EXCLUDED.operation_cert_ref,
      dept_context_cert_ref = EXCLUDED.dept_context_cert_ref

**Pointers are refreshed; history is not.** `granted_by` and `granted_at` are deliberately absent
- refreshing them would rewrite who granted something and erase when, which is a worse defect
than the one being fixed. The two refs are pointers at a current fact, so they converge.

**A ref resolving to NULL overwrites a non-NULL one on purpose.** NULL is a state `resolve_grant`
reports truthfully; a stale non-NULL ref pointing at a deleted row is the silent failure this
exists to end.

`tests/golden/test_generators.py::test_a_second_apply_reconciles_certification_refs` asserts both
halves: refs converge, `granted_by` and `granted_at` unchanged. **Verified by breaking it** -
reverting the upsert alone makes it fail with *"still carries the dangling unit-A ref after a
second apply"*; restoring it passes. The test could not have existed before, because until a
`cert_id` could change there was no reachable way to make a ref stale (entry 68).

---

## 72. Four grants nobody can certify, and a stop rather than a deferral

**Ruled 2026-09-14 by Ivan. Gate 9 blocks on eight units and stays blocked, deliberately.**

### What they are

    Amelie Wystan   engineering  active   capitalforge/client_read         auto_execute  3 Sep 14:19
    Brina Arvane    engineering  active   capitalforge/client_read         auto_execute  3 Sep 14:20
    Brina Arvane    engineering  active   capitalforge/scan_communication  propose       3 Sep 15:52
    Cedric Noren    engineering  active   capitalforge/client_read         auto_execute  3 Sep 14:45

**Not superseded, not orphaned, not simply uncertified.** Three agents from a department outside
the Pack, holding live activated grants for modules inside it.

    the modules ARE operated      client_read -> Intake Concierge
                                  scan_communication -> Compliance Reviewer
    the department is NOT drawn   Burkham's positions draw from administration, banking
      from by any position        and operations. `engineering` appears in no position
    so no unit B is reachable     unit B is per (department, forge_id). Gate 8 opens a
                                  department unit only for departments a position names
    and these are the ONLY        nothing supersedes them, nothing waits behind them, and
      grants on their triples     `resolve_grant` selects them because there is nothing newer

**That last line is what separates them from the thirty duplicates of entry 67.** The duplicates
are unreachable and harmless; these are reachable and refused.

### Why both remedies were refused

**Certifying `engineering/capitalforge`** mints a unit B for a department no Burkham position
draws from. It would clear Gate 9 by certifying something the Pack never asked for - *certifying
to clear a line*, which is the shape `scripts/check_module_manuals.py` is documented as warning
against: *"registering a name to clear that line is how `lender_match` happens."*

**Deleting them** removes authority rather than a shadow. Entry 67's thirty could be argued away
because a newer grant answers for their triple; these have no replacement, so deleting is not
tidying a superseded row - it is withdrawing a grant, silently, through the one mechanism that
leaves no record.

**So the answer is neither, and it is a stop rather than a deferral.** Gate 9 blocks on eight
units that represent a real gap, the run does not advance, and the reason is on the record.

### The question that has to be answered first - and it now has evidence

The question was: **why does Phase 0 issue grants to a department the Pack does not name?** If
`engineering` is deliberately a bootstrap or operator department, the Pack should say so and the
unit B is legitimate. If it is an artefact of `bootstrap-phase0`'s behaviour before `--department`
existed, they are residue and deleting them is right.

**Measured while recording this, and it points one way.** The version of
`broker/bootstrap_phase0.py` immediately before PR #118 selected its candidate agents with a
hardcoded literal:

    SELECT village_agent_ref, agent_name, department, role_key
      FROM ...
     WHERE status = 'active' AND department = 'engineering'

    #118 - bootstrap-phase0 takes --forge, --module and --department   13 Sep 2026 10:46
    the four grants                                                     3 Sep 2026 14:19-15:52

**The grants predate `--department` by ten days, and the code that wrote them could not have
chosen any other department.** `engineering` was not a policy about operator departments; it was
a literal in a candidate query, and the Pack was never consulted.

**That answers the question and does not settle the disposition.** It makes "residue" the likely
reading, and residue still holds live activated authority over two modules a live Pack operates,
by an agent nobody appointed. Deleting on the strength of a strong inference is the same act
entry 69 declined - reaching for the mechanism that leaves no record because the honest one does
not exist. The supersession vocabulary is still missing, and these four still have nothing to be
superseded by.

### One detail that complicates any resolution

**Amelie Wystan holds two grants in `greenstone` as well**, so she is not purely a Burkham
artefact. Brina Arvane and Cedric Noren hold grants only here.

Whatever resolves this has to account for her twice: a decision that `engineering` is residue in
Burkham says nothing about what her Greenstone grants are, and a deletion scoped to one venture
would leave the same agent in two states for the same reason.

---

## 73. Greenstone's `place_call` removal is held, and the reason is a test that would have no subject

**Ruled 2026-09-14 by Ivan. Recorded as a decision rather than left in a stash, because it
has been carried across three sessions and a fourth would make it an accident.**

### What is held

A stash on `coord/greenstone-remove-place-call`, nine files:

    packs/greenstone.yaml                     place_call removed at 3 sites
    7 golden snapshots                        re-recorded
    tests/golden/test_generators.py           the authored-content end-to-end test,
                                              re-anchored from place_call to
                                              transcribe_call

**The edit itself is correct and measured.** `voiceforge/place_call` is FORBIDDEN in
`forge_module_exclusion` by a founder decision binding every venture - no agent may
initiate an outbound call as principal - and the exclusion explicitly holds *"whether or
not the module works."* Declaring it could never produce a usable grant. What it did
produce was demand: projected approvals fall **192 -> 160** when it goes, which is the 32
a day V13 was billing for a module no agent may ever call.

`transcribe_call` stays. The same founder decision permits VoiceForge to assist a human on
a call and forbids only dialling or speaking as one; removing both would over-apply the
ruling.

### Why it is held

`tests/contract/test_packs_api.py::test_directory_reports_the_failing_rules_message_not_the_rule_name`
asserts that V11's failure message **names** an excluded module:

    # And the excluded module is NAMED, not silently absent. Silence would make an
    # exclusion indistinguishable from coverage: a reader seeing every operated module
    # accounted for cannot tell which were taught and which were refused.
    assert "place_call" in failure["message"]

**Once `place_call` leaves Greenstone's Pack there is no excluded module for the message
to name**, so the test asserts a message that cannot exist. It is not a stale expectation
and it is not collateral: it guards a real property - that an exclusion is visible rather
than silently absent - and Greenstone's Pack was the only fixture supplying it.

**That is the same shape as the exclusion test split out in #126**, where one venture's
Pack was the sole coverage of `apply`'s excluded-module skip path and its own comment said
*"nothing else here would notice."* Two controls, one accidental fixture, found one at a
time by removing the module both depended on.

### Why holding rather than pushing through

Three routes were available and two are refused:

    delete the assertion        a control quietly ceasing to report - entry 58's ruling
    weaken it to "or absent"    the same, wearing a conditional
    give it its own fixture     correct, and a third test-file rewrite

The third is right and was not done at the end of a long session, which is the honest
reason. **A fixture built deliberately is stronger than the one being removed**: today the
property is tested only because a production Pack happens to declare a forbidden module,
which is coverage by accident.

### What holding costs, stated so it is not free

Greenstone's V13 stays **8x over** rather than 7x - 192 approvals x 6 minutes = 1,152
against Dana's 144. Neither figure passes, so the removal changes the size of a failure
and not its verdict; that is why holding is affordable and why it is not urgent.

**It does not fix Greenstone's V13 either way.** Dana is the only `compliance_officer` and
Dana does not exist (entry 59); Ivan's six hours are invisible because V13 matches on the
Pack's role string and he is `venture_operator`. The 32 approvals are real waste and the
denominator is a fiction, and removing the waste leaves the fiction.

### The entry numbers this displaces

Two entries were planned as 73 and 74 - the artifact-staleness family, and the corrections
count - and are now **74 and 75**. Written down rather than left as a reserved gap,
because a gap in this ledger is the exact hazard one of those entries is about.

---

## 74. A patch nearly retired on a fact that had expired, and every step caught by a read

**Recorded 2026-09-14. One entry rather than two: the corrections are the story's evidence
rather than a finding beside it, because every one of them came from reading FunnelForge's
code or The Office's own files.**

### The sequence

**1. A patch deferred nine times, read on the ninth.**
`docs/plans/funnelforge-position-DEFERRED.patch` held two Burkham Pack edits as a unified
diff. P-13 held it at merge on 9 September, P-16 declined to apply it, B39 took ownership and
built a lander without running it. The ninth deferral was the first time anybody read it.

What the reading found, none of it as described:

    "it keeps failing to apply"        `git apply --check` exit 0, every time checked
    "a Pack four versions dead"        applied to the current Pack
    "written against a FunnelForge     targets `packs/burkham-wickmont.draft.yaml`;
     Pack"                             there is no FunnelForge Pack
    "the qualification replaced its    `forge_modules_operated` still bare, all 19 refs
     modules_touched shape"
    "trust_tier_ceiling superseded"    used by all five live Burkham positions
    "V31 passes, the position exists"  never landed; both counts zero

**2. The blocker had been resolved in another repository, and never crossed back.**
The patch was held because V31 refuses `auto_execute` over a mutating `at_most_once` module,
and seven of its nine were that shape. **FunnelForge PR #160 merged 2026-09-12 04:55 UTC** and
gave `/api/emails/send` an idempotency store: an atomic Redis claim holding across replicas, a
repeat answered from the record rather than sent, failing closed with a 503, a 24-hour window
matched to Resend's.

Nothing in The Office noticed. The declaration here is a hand-written string about another
repository's code, and no test, constraint, gate or rule compares them.

**3. Entry 55 asserted the remedy was unassigned, a day after it merged.**
Written 13 September: *"The remedy is not in this repository. It is an idempotency key on
FunnelForge's send path - `EmailQueue` has none... one field in another repository, and nobody
has been assigned it."* It had been assigned, shipped and merged the previous day. **That
sentence was false when it was written**, and the ledger had no way to know.

**4. The declaration was corrected, and the correction overshot.**
Seven `at_most_once` declarations became `key` in a single replace-all, on the evidence of a
PR that changed `/api/emails/send` and nothing else.

Six were right. **`schedule_blueprint_call` posts to `SCHEDULING_BOOK`**, and
`apps/api/src/modules/scheduling/` contains no reference to an idempotency key - the store is
reached only from `emails/routes.ts` and four siblings. The adapter forwards `Idempotency-Key`
on every upstream call, so the header **arrives at the booking route and is ignored**, which is
worse than not sending it: a caller could believe the guard applies.

**5. A manual caught it, by not inheriting.**
`funnelforge-schedule-blueprint-call.md` §6 had said so all along - *"a duplicate appointment
is two rows in a calendar for one conversation, and nothing in this module can cancel either
one."* It reasoned from its own route. Five send manuals carry one sentence verbatim - *"the
adapter failure table and the retry rule are identical here and are not repeated"* - and
inherited a conclusion drawn from a premise about a route they do share. When that premise
expired, five became wrong at once and no word of any of them moved.

**A template that produces a true sentence six times has not checked it once.**

### The corrections, enumerated

Twenty-one claims that measurement contradicted, across this thread. Not judgment calls -
claims about what was in the tree, each settled by a grep or a query.

**Named something that does not exist:**

    _grants_for                        no matches, whole repo
    a third certified_tiers consumer   one producer, two consumers, both correct
    Gate 5.5                           GATE_SEQUENCE runs "5", "6"
    GATE_55_RULES / GATE_2_RULES       not identifiers in this repository
    plan.shifts                        no artifact carries shifts
    plaid-consumer-data-consent-v1     absent from the entire repository
    four unresolved library refs       zero, across the Pack and all 24 instructions
    test_v6_blocks_when_module_refs_…  no such test
    test_burkham_pack_declares_its_…   no such test
    send_email                         no such module; nine declarations, nine manuals
    a Q1 about atomic vs two-phase     never asked; the lander was already two-phase

**Was the opposite of the measurement:**

    Gate 7 awaiting_human              passed at 17:18, and is not a human gate
    "all 34 revocations"               eleven; 34 counted grants discounted
    the patch "keeps failing to apply" applied cleanly every time
    "a Pack four versions dead"        applied to the current Pack
    "the qualification replaced it"    19 refs still bare
    "trust_tier_ceiling superseded"    used by all five live positions
    "the position exists"              never landed
    "written against a FunnelForge Pack"  targets Burkham's
    B53 "sits unassigned"              merged 2026-09-12
    entry 48's subject                 forge_modules_operated, settled twice by re-reading
    "same shape as Burkham"            Burkham does the opposite, measured across five

**Every correction came from a read.** Not one came from the ledger, a test, a constraint or a
gate. The records were consistent with every claim on that list, because a record says what
was true when it was written and has no opinion about what is true now.

**And the reads were cheap.** Each cost a grep and produced a better question than the one
that prompted it: the `_grants_for` hunt found the flattening entry 52 records; the Gate 7
hunt found a gate passing on an empty set; the patch hunt found a blocker resolved and never
crossed back. **The measurement is not the tax on the instruction. It is the part that found
the thing.**

### What nothing in this system could have caught

    forge_module_registry.idempotency_support   a hand-written string in THIS repository
                                                describing code in ANOTHER one

    verification_method = 'hand'                16 of 20 registered modules
    verification_method = 'adapter_manifest'     4 of 20 (cre-forge only)

`ModuleShape.is_evidence` already draws the distinction in terms - *"`hand` is a claim. The
other two were obtained from the Forge."* **Nothing reads it.** No rule, no gate and no test
treats a claim differently from an observation, so sixteen assertions about another system's
behaviour sit in the registry with the same standing as four that were measured.

**The seven sends are the demonstration.** They were `at_most_once`, correctly, until
12 September. They stayed `at_most_once` for two days after that stopped being true. Then six
became `key` correctly and one became `key` wrongly, and the wrong one was caught by a manual
rather than by anything structural. Four states in three days, on a field nothing verifies.

`tests/adapters/test_funnelforge_idempotency_hop.py` is the first test anywhere that checks
one of the sixteen, and it checks the half this repository owns - that the header leaves the
adapter. **The other half is still a claim**, gathered by reading `idempotency-store.ts`, and
it will stay one until FunnelForge's own suite is reachable from here.

### A narrower note on `_grants_for`

The hunt for it produced a correct general worry and a wrong specific one. `module_trust_tiers`
does **not** stop at the artifact and the validator: traced end to end, it reaches the grant
row.

    generators/runtime_config.py:74    overrides_by_title = {title: p.module_trust_tiers}
    generators/runtime_config.py:89    declared = overrides.get(f"{forge}/{module}", ceiling)
    generators/runtime_config.py:117   trust_tier=_lower(declared, certified_tiers.get(...))
    generators/runtime_config.py:238   INSERT INTO agent_forge_grant (..., trust_tier, ...)

So it shapes the artifact, the approval projection **and** `agent_forge_grant.trust_tier`,
which `resolve_grant` gates every call on. That is entry 52's whole subject: the field was
declarable, storable and enforceable, and inert only because the artifact between them
flattened it.

---

## 75. Where the ladder stops: eight units, four grants, one ruling

**Recorded 2026-09-14. Run `8ed2f39a-61fb-44eb-9c90-8f2192781884`, burkham-wickmont@0.10.0,
artifacts hash `e210fdc8be997047`, blocked at Gate 9.**

### The ladder as it stands

    0    passed   bridge operational for capitalforge, simforge
    1    passed   Pack burkham-wickmont@0.10.0 authored, hash 7b2900de37b26093
    2    passed   34 rules, no failures
    3    passed   15 workflow step(s), 80 projected daily approval(s)
    3.5  passed   reconciliation clean
    4    passed   operator recorded a review of the artifacts
    4.5  passed   capacity and budget feasible
    5    passed   15 grant(s) issued INACTIVE, 12 manifest row(s)
    6    passed   instructions for 10 module(s), 16 compliance flag(s) explained
    7    passed   49 grant(s) registered, none active
    8    passed   85 scenario(s) generated; 0 of 10 modules accepted by SimForge;
                  0 of 3 department unit(s) opened
    9    BLOCKED  8 of 98 certification unit(s) are not certified (8 x never_certified)

**Twelve gates cleared, one refusing.** Gate 7's line is the one entry 63 was corrected for: it
is now a real pass over forty-nine rows rather than the same word over an empty set.

### The eight units are four grants counted twice

Gate 9 checks Unit A and Unit B per grant, so 49 grants make 98 units. Ninety are certified.
The eight that are not are **four grants with `operation_cert_ref` and `dept_context_cert_ref`
both NULL** - every other grant on this venture carries both.

    97fcff2f   Cedric Noren     engineering   capitalforge/client_read
    de5213e5   Brina Arvane     engineering   capitalforge/scan_communication
    ead35ef7   Amelie Wystan    engineering   capitalforge/client_read
    f68365c3   Brina Arvane     engineering   capitalforge/client_read

**These are entry 72's four, unchanged in identity and changed in one respect: they are no longer
active.** Entry 74's deactivation returned all forty-nine of this venture's grants to inactive,
these included. That cleared Gate 7 and did nothing at all to Gate 9, which is correct - `_gate_9`
selects `WHERE g.venture_id = %s` with no activation term, because certification is a property of
a grant and not of its activation. **Deactivating removed the authority and left the gap.**

### 68 -> 8, and what each step was worth

    68   the run as it stood before entry 71
    ...  entry 71 repaired the certification refs and taught the upsert to maintain them
    ...  both Packs republished at 0.10.0 / 1.6.0, executing entry 48's qualification
    ...  a fresh run started against 0.10.0, gates 0-8 re-evaluated from scratch
     8   after entry 74's deactivation

**Four operations, one residual.** Three of them moved the number; the fourth did not and was
never going to. The sixty that went were repairs to grants that had a certification and could not
find it. The eight that remain are grants that have none to find.

### Why it stays there

Held by entry 72, deliberately. The two available remedies were refused there and neither has
become available since: certifying `engineering/capitalforge` mints a unit B for a department no
Burkham position draws from, and deleting the rows withdraws authority through the one mechanism
that leaves no record.

**The run does not advance, and the reason is on the record rather than in a workaround.**

---

## 76. What Gate 9 counts, and the second refusal standing behind the first

**Ruled withdrawn 2026-09-14 by Ivan, before anything was built. A ruling to deactivate the four
engineering grants was issued and retracted on two independent grounds, and the read it prompted
found a third thing nobody had looked at.**

### The reconsideration

The ruling was: deactivate the four, because `deactivate()` is the third state entry 72 lacked -
neither withdrawing authority nor certifying to clear a line - and it landed after that entry was
written. Entry 72's reasoning rested on there being no third state; a third state had since been
built; so the entry was superseded by a mechanism rather than by a reconsideration.

**The mechanism is real and it is a third state for the wrong question.** In Ivan's terms:

> `deactivate()` is a real third state for *may this be exercised*. It is not one for *is this
> certified*, and I ruled as though it were.

Entry 72's two refusals were both about certification. Nothing in the new mechanism touches
certification, so nothing in entry 72 was answered by it.

### Two errors, recorded separately

They are different failures and **either alone would have been enough to make the ruling wrong.**
Recorded apart so that fixing one is not mistaken for fixing both.

**First: ruling on a mechanism's scope without checking it.** `deactivate()` is venture-scoped -
`WHERE venture_id = %s AND activated_at IS NOT NULL`. It had already run on this venture on the
15th and taken all thirty-four active grants, these four among them. They were **already
inactive**, so the ruled act had no target. A second call refuses.

**Second: ruling on an outcome without checking what the gate counts.** Deactivating them could
not have cleared Gate 9 even with a per-grant scope, because Gate 9 does not read `activated_at`
at all.

**The first error is about a verb. The second is about a gate.** Had the scope been per-grant, the
second still stands. Had Gate 9 read activation, the first still stands. Neither is a special case
of the other.

### What Gate 9 counts

Every grant row for the venture. One condition, and it is not about the grant.

    FROM agent_forge_grant g
    LEFT JOIN certification ca ON ca.unit = 'A' AND ca.cert_id::text = g.operation_cert_ref
    LEFT JOIN certification cb ON cb.unit = 'B' AND cb.cert_id::text = g.dept_context_cert_ref
   WHERE g.venture_id = %s

**`WHERE g.venture_id = %s` is the whole filter.** No `activated_at`, no `is_assignable`, no
revocation predicate, no join to the roster. Forty-nine rows in, two units each, ninety-eight
units out - and measured just now, all forty-nine are inactive and `is_assignable` is false on
every one of them, which changes the count by nothing.

A unit clears on one condition: **the ref column names a `certification` row of the right unit
whose `state` is `certified`.** `COALESCE(state, 'never_certified')` means a NULL ref and a ref
pointing at nothing are the same answer. The four engineering grants have both refs NULL; no other
grant on this venture does.

**What the gate is asking is the reason none of this moved it.** Gate 9 asks *whether agents are
certified for what they hold*. Deactivation does not touch that - it changes whether a held grant
may be exercised, and the question survives the answer. Deletion does not answer it either:
**deletion hides the question rather than answering it.** Removing the row removes the thing that
was asking, and the gate then passes because nobody is holding anything uncertified, which is not
the same fact as everybody being certified.

**So the option set is exactly entry 72's two and always was.** Certification, or the grant not
existing.

**Entry 72 stands.** Not reaffirmed after reconsideration - never actually challenged. The
mechanism that appeared to supersede it does not operate on the thing it blocks.

### The third thing, which nobody had looked at

Gate 9 has two refusals and only the first has ever fired.

    if failing:     -> "8 of 98 certification unit(s) are not certified"
    if unattested:  -> "N certification(s) read as certified but carry no SimForge PASS.
                        A certification nothing external attested is a certification
                        The Office wrote for itself."

`unattested` is every unit whose state is `certified` and whose `simforge_verdict` is not `PASS`.
Measured on this venture:

    certification rows in the entire database          18
    carrying simforge_verdict = 'PASS'                  0
    carrying simforge_verdict = NULL                   18

    units that would reach the second branch           90

**Clearing the eight does not pass Gate 9. It moves the block from eight units to ninety.** The
first branch has been standing in front of the second the whole time, and the second is the more
serious of the two: the eight are grants nobody certified, and the ninety are certifications
nothing attested. Every certification this venture holds was bootstrap-written - which the Gate 4
review said in terms, *"all bootstrap-attested, none derived from a scenario run"* - and Gate 9
already has the rule that refuses them. It has simply never been reached.

**This is green-by-absence again, pointed the other way.** Entry 63's Gate 7 passed because its
input set was empty. Gate 9's second rule has never run because a prior rule always answered
first. Neither is a bug and both mean the same thing: a verdict nobody has seen is not a verdict
that works.

### What this does to "one gate from the furthest anything has been"

It removes it. The run is not one remedy away from advancing; it is one remedy away from meeting
a refusal that applies to ninety units instead of eight, and that refusal wants something no part
of this deployment currently produces - a SimForge PASS against a held-out scenario run. Gate 8
reported `0 of 10 module(s) accepted by SimForge` on this very run.

### What the run is blocked on, precisely

**Four grants, held by entry 72's ruling.** Not by a missing mechanism and not by a state that
needs changing - both of those were looked for and neither is what is in the way.

    97fcff2f   Cedric Noren     engineering   capitalforge/client_read          auto_execute
    de5213e5   Brina Arvane     engineering   capitalforge/scan_communication   propose
    ead35ef7   Amelie Wystan    engineering   capitalforge/client_read          auto_execute
    f68365c3   Brina Arvane     engineering   capitalforge/client_read          auto_execute

**Their disposition needs a Pack decision about whether `engineering` belongs.** That is a question
about what the business declares, answerable only by whoever authors the Pack. No verb resolves
it, no state change resolves it, and building either would be answering a question nobody asked
with a thing nobody needs.

The two paths remain what entry 72 named, and both are still refused:

**Certify `engineering/capitalforge`** - mint a unit B for a department no Burkham position draws
from. Unit B is per `(department, forge_id)`, and Gate 8 opens a department unit only for
departments a position names; it opened none for `engineering` because there was none to open.
Minting it by hand is *certifying to clear a line*, which `scripts/check_module_manuals.py` is
documented as warning against: *"registering a name to clear that line is how `lender_match`
happens."*

**Delete the four** - and these hold real authority on their own triples. Nothing supersedes them,
nothing waits behind them, and `resolve_grant` selects them because there is nothing newer. That
they are currently inactive does not soften this: `_gate_11` activates with
`WHERE venture_id = %s AND activated_at IS NULL` and **no certification check at all**, so their
inactivity is held in place by Gate 9's block and by nothing else. Deleting them is withdrawing a
grant through the one mechanism that leaves no record - entry 69's refusal, unchanged.

**Both refused. The refusals still hold. The run stays where it is.**

### A loose thread, recorded where it was found

`greenstone`'s two grants carry `operation_cert_ref` and `dept_context_cert_ref` values that name
no row in `certification` - 18 rows exist, all `capitalforge`, none matching. Both grants are
**active**. So the one venture holding live activated grants is holding them on certification
refs that point at nothing, and Gate 9 would report all four of its units `never_certified` if a
run ever asked. Not investigated here.

### Amelie Wystan, still in two ventures

Unchanged and still unaccounted for. Her burkham grant is one of the four; her two greenstone
grants - `cre-forge/property_lookup` and `simforge/gate_result` - are active, outside anything
scoped to burkham-wickmont, and among the dangling refs above. **Whatever settles `engineering`
settles one of her three grants.** A resolution that does not say what happens to the other two
has not finished.

---

## 77. The instrument we were checking the others with had never discriminated

**Found 2026-09-14, on Ivan's instruction to diff Smoke against main's capture before merging #138
rather than reason from docs-only.** *"Docs-only is a good reason to expect it's the documented red
and not a substitute for checking — the ninth-failure case merged on exactly that reasoning."* The
check passed. The instrument did not.

### What the check found

    FAILs      main=8   branch=8    identical, byte for byte
    could-not-run   1        1
    lines         432      432
    hashes     934af341…  vs  b4ace092…

**Eight and eight, identical, and two different digests.** The whole content difference was one
timestamp on line 1 — `##[group]Run ./scripts/console-smoke.sh`, the line that opens the compared
region — which the normaliser is built to strip and didn't.

### The cause, and the correction to my first account of it

A UTF-8 BOM sits between the start of that line and the timestamp, and `_TIMESTAMP` is anchored
with `^`. B49 has the mechanism.

**I reported the cause before finishing the measurement, and got it wrong in a way that mattered.**
What I said was: every log GitHub serves carries a BOM at byte 0, so `--check` has never worked,
including through the fetch the script documents. I had confirmed a BOM at byte 0 on the documented
fetch and stopped there. Measured properly:

    gh api .../jobs/<id>/logs       1 BOM, on a line the script discards
    gh run view --log              12 BOMs, one per STEP - including the step-start line

**So the instrument was correct through the port it documents and broken through the one we
substituted for it.** "The tool never worked" and "we were using it through an undocumented port"
are different findings with different repairs, and I recorded the first before checking whether it
was the second. The BOM at byte 0 was real; the inference from it was not.

`lstrip` at read time — the fix as first ruled, and as I first wrote it — does not fix this. It
removes one BOM and the one that costs the digest is the twelfth. The hashes were unchanged after
it, which is how the real shape surfaced.

### The shape, third instance this week

    entry 63   Gate 7 passed because its input set was empty
    entry 76   Gate 9's second refusal has never run - a prior branch always answers first
    entry 77   --check never distinguished anything - a working diff always answered first

**In all three, something reported for a long time without ever having discriminated.** The first
two were found with instruments; this one was in an instrument, and it was the one being used to
check the other two. Nothing here was caught by a test, a gate or a review — it was caught by
someone declining to accept a good reason in place of a measurement.

### What the warning could not do

`smoke_normalise.py` opens with a section refusing *"a number that could only be reproduced by the
shell history that produced it"* — written after a prose recipe produced an irreproducible hash.
`BASELINE` then had that exact property for four days. **The guard against unverifiable numbers was
itself a paragraph**, and a paragraph does not run. Its replacement is three tests, two of which
fail without the fix.

### The baseline, re-recorded from two runs

    c9f1f858148f6c83c262ba332a488eb9a9cd22a6240edd0b2a19d307bfeb08cf

Taken from the documented fetch on two different runs — main `504ba1f` and branch `9aacd6f` — whose
normalised text is byte-identical. **The previous baseline was taken from one run**, which is the
condition that let it be wrong without anyone being able to tell. One run produces a number; two
runs agreeing produce a baseline.

The two fetch paths still cannot agree, and will not: `gh run view --log` renders the ANSI escape
on the step's echoed command as `^[` where `gh api` returns the ESC byte. Recorded rather than
normalised away, because masking a difference is how a comparison stops comparing.

---

## 78. Three gates whose behaviour nobody could observe, and the instrument that found them

**Recorded 2026-09-14. The third instance of one shape in two days, and the first time it
was looked for deliberately rather than stumbled into.**

### The three

    entry 63   Gate 7 passed because its input set was empty - 49 grants, all revoked,
               and an empty set cannot contain an active one
    entry 77   `smoke_normalise --check` never distinguished two runs, because a working
               FAIL-line diff always answered first
    B53        Gate 11 activated grants a live revocation covered, because no run had
               ever reached Gate 11 on a venture holding a revocation

**In each, something reported for a long time without ever having discriminated.** Not a
wrong answer - no answer, wearing the shape of one. Gate 7 said PASSED over nothing.
`--check` said DIVERGENT on every capture including clean ones. Gate 11's UPDATE had
never met a revoked grant, so its silence about revocation had never cost anything.

### What is different about the third

The first two were found after the fact - Gate 7 by measuring a verdict that looked
wrong, the normaliser by a hash that differed when the logs did not. **B53 was found
before it happened**, by asking what the next gate does rather than by running it.

The instrument is ordinary and worth naming because it is repeatable: **before signing
Gate 10, list the rows Gate 11 would touch.** Not the count afterwards - the list, in
advance, with each row's state beside it. Ivan asked for exactly that, in those terms:
*"I want the list before it does, not the count after."*

The list was 49 rows. Four of them carried `REVOKED` in a column the gate does not read.

### Why the count would not have shown it

This is the part worth keeping. `49 activated` is a true sentence. So is `45 activated`.
Neither says anything about revocation, and a reader comparing them has no reason to
suspect the difference is four grants whose authority a named human withdrew that
afternoon. **The defect is invisible in every summary of the thing it damages** - which
is the same property entry 63 recorded about Gate 7's reason line, and the same property
entry 77 recorded about a digest nobody read.

So the fix carries the withheld count in the **reason line**, not only in the evidence -
and V38 carries its warning into Gate 12's reason line for the same reason. A number that
only appears in a JSON blob is a number that has to be gone looking for.

### The shape, stated so the next one is findable

A control that has never been exercised is not a control that works. It is a control that
has not been tested by the world yet, and the three ways that happens are all here:

    green by narrowing     the set was filtered until it was empty         (entry 63)
    green by absence       a prior branch always answered first            (entry 77)
    green by never arriving  the code path had no traffic to refuse        (B53)

**All three look identical from the outside**, and none of them is a bug in the usual
sense - every line involved is correct. What is missing in each case is any assertion
that the rule was ever handed something to rule on. Entry 63 named that gap and did not
close it; it is still open, and it is now three findings wide.

---

## 79. Three corrections and a step nothing performs

**Recorded 2026-09-14, at the close of the session. Read-only throughout; nothing was
signed, activated or completed.**

### What was NOT recorded, and why

**A Gate 10 signature and a run completion were both directed and neither was written.**
The run is where it has been since 19:57:

    run 8ed2f39a   gate=9   status=blocked   pack=0.10.0
    signoff_record 0 rows, database-wide
    grants         49 total, 0 active, 0 assignable

Gates 10, 11 and 12 have never been evaluated on this run - no rows. There is no completion
to record. The Gate 10 note was declined separately, with five measured falsehoods set out
and substitutions proposed; that authorisation did not arrive, so nothing was signed.

**A record of a completion that did not happen is the one thing this ledger cannot carry.**
Every other entry here is recoverable by re-reading the system. That one would not be.

### The numbers, corrected against the database rather than against memory

    directed            measured
    ------------------  --------------------------------------------------------
    34 activated        45 - Gate 11's exact predicate, run live, returns 45
    30 activated        the same 45; 34 is entry 64's pre-deactivation count
    19 unselectable     30 unselectable; 19 is the count of distinct TRIPLES
    15 triples          19 triples: 15 crowded at x3 (45 rows) + 4 singletons

**Entry 67 measured the duplicates at two per triple. It is three now** - bootstrap, then
`runtime_config.apply` on the aborted run, then again on this one. Each run adds a layer and
nothing reconciles, so the figure is not stable and a number quoted from an earlier entry is
a number about an earlier world.

### The Gate 11 fix is correct, untested by any run, and NOT inert

B53's fix withholds revoked grants from activation. It has **never executed in production**,
because no run has reached Gate 11 - it is proven by a test that fails without it, not by a
green run, and a green run would not have proven it either.

**The reason offered for calling it unexercised was inverted, and the distinction matters.**
*"The four were already inactive, so `covered_grants()` excluded nothing"* - being inactive
is what makes a grant a CANDIDATE for Gate 11; being covered is what withholds it. The four
are inactive **and** covered, so they are exactly the rows the new term removes. Against the
live database:

    with the NOT (grant_id = ANY(covered)) term      45
    without it                                       49

**The fix does work on this venture's real state. What it has not had is a run.** Those are
different claims and only the second is true.

### The finding: the ladder authorises and does not schedule

Recorded as B55. Every brokered call asserts `assert_on_shift_for`; **no gate writes a
shift**; `shift_assignment` holds zero rows for zero agents. `bootstrap_phase0` assigns one
as the fifth of its five writes and says why - *"a grant without a shift is refused"* - and
the ladder has no equivalent step.

**So Gate 12's "live" means authorised, not operating.** A venture can clear all twelve
gates and be unable to make a single call, and nothing in the run would say so: `is_assignable`
is generated from certification refs and `activated_at`, and no rule compares a grant to a
shift.

**This is the same shape as entries 63, 77 and 78, arriving from the other side.** Those were
controls that had never been exercised. This is a control - `assert_on_shift_for` - that is
exercised on every call and that **nothing upstream is built to satisfy**. Green by never
arriving, and its mirror: red by never being prepared for. Neither is visible from inside
the ladder, because the ladder's last gate reports on what it granted rather than on whether
anything can act.

---

## 80. Provisioning grants authority; nothing schedules it. A scope finding, not a gap

**Decided 2026-09-15. Read-only throughout; nothing was assigned and no gate was changed.**

**Decision.** The ladder does not assign shifts, and it is right not to. **B55 is
reclassified from a gap to a scope finding.** It is not a defect in any gate, it is not a
missing gate, and it is not to be closed by amending Gate 5, 11 or 12.

Provisioning grants authority. Scheduling says when that authority can be exercised. They are
different jobs: the ladder does the first correctly, and nothing in the system does the second.

### What "operating" means

A venture that has passed every gate, with its grants issued and activated and no agent on
shift, is **authorised and not staffed**. Gate 12's "live" is true of it, and every call is
refused, correctly, by `assert_on_shift_for`. That is the whole output of provisioning, not
a partial one.

**Burkham is not in that state and should not be quoted as if it were.** Run 8ed2f39a is
blocked at gate 9, with 0 signoffs and 0 of 49 grants active.

### Why the ladder is the wrong owner: the reasons that survive a read

- **The spec puts the calendar in the Village.** master-prompt-v4, line 109: *"Shifts exist
  as a Village mechanic."* §7.4: *"The Office allocates within them; it does not override
  them."* `broker/village.py:343`: *"The Village owns the shift calendar."* `docs/shifts.md`,
  known gaps, verified 2026-08-23: *"Nothing schedules rotations … scheduling policy is
  deliberately absent here."*
- **A run happens once, and shifts recur.** A gate that wrote a shift would staff the
  venture for one window.
- **A run covers one venture, and allocating agents means choosing between ventures.**
  `one_venture_per_agent_quarter` decides between ventures, and `ux_run_active` scopes a run
  to one. Amelie Wystan holds grants for both burkham-wickmont and greenstone, so a Burkham
  gate could take her quarter only by writing first.
- **No gate has a window.** `assign_shift` takes five inputs. A gate has three of them: the
  agent, the venture and `ctx.actor`. The quarter is read live from the Village, which
  `provisioning.py` never calls. The window exists nowhere: `capacity_demand.shift_pattern`
  is free text and nothing reads it.

### Three reasons offered for this decision, and why they are not carried in

The conclusion is right, and that is exactly when a wrong reason gets through unchecked.
Each was checked against the code:

    offered                                   measured
    ----------------------------------------  ---------------------------------------------
    broker/shifts.py says a shift is where    Not in that file, and not in broker/, client/
    the human answers, and provisioning has   or generators/. shifts.py records the assigner
    no idea who is on duty                    as actor_type "human". escalation.py puts
                                              "who covers a shift" under OPERATIONAL, the
                                              Village's own chain, not the human path.

    bootstrap_phase0 hardcodes a quarter      It reads the quarter from the Village
                                              (bootstrap_phase0.py:587). What it hardcodes
                                              is the WINDOW: now-1min to now+8h (:602-603).

    Gate 5 would have to invent an operator,  Gate 5 has one: ctx.actor, already passed as
    and Phase 0 has neither                   granted_by. Phase 0 has one:
                                              attributable_actor, written as assigned_by
                                              (:604). Both have an operator. Neither has a
                                              window.

**The window is the entire difference.** Nobody in provisioning can say when an agent works.

**The session's option letters are not used here.** "C" was first offered as *drop the time
window and make the agent-quarter the boundary*, and that is not what was decided. That
question is still open: what time base an Office shift uses, given that the Village runs its
own clock and its own shift calendar.

### What is missing: scoped here, not built

`assign_shift` exists, is tested, and enforces its own refusals: an unflushed previous
shift, an unknown quarter, and a quarter conflict. Its only callers are `rotate()`, which
nothing calls, and `bootstrap_phase0`, which invents a window because it has nobody to ask.
**Nothing calls it with a real operator and a real window.** No console action, no CLI verb
and no route exists for it. A route would also trip
`test_the_api_exposes_no_route_that_bypasses_a_control`, which rejects any write path
containing `shift`. Whether building one is today's work has not been decided.

---

## 81. The shift-window gap: overlaps are refused, gaps are not, and a scheduler inherits that

**Recorded 2026-09-15, before anything schedules, so the first scheduler is written by
someone who has read this.**

### The asymmetry

**One agent cannot hold two overlapping shifts.** The schema refuses it through
`no_overlapping_shifts_per_agent`, an exclusion over `tstzrange(shift_start, shift_end)`.
`assign_shift` does not check this itself. An overlap arrives as a raw `ExclusionViolation`
from the database, not as a named refusal.

**Nothing refuses a gap.** No constraint, no check in `assign_shift`, no sweep. When a shift
ends and nothing follows it, the agent is off shift, and the next brokered call is refused
with `OffShift`: *"agent is not on shift"*. **Nobody decided that.** Nothing is written when
a shift lapses. The first trace is the refused call's own audit event,
`call_refused_off_shift`.

    overlap between two shifts, one agent    refused, by the schema
    gap between two shifts, one agent        permitted, and silent
    back-to-back (end == next start)         permitted - tstzrange defaults to '[)'

Continuous coverage can be expressed in the schema. **Nothing requires it.**

### What a naive scheduler gets wrong

1. **It reads "no overlap" as "coverage".** The constraint it can see is the one that does
   not matter for staffing.
2. **It treats a refused assignment as an error to retry later.** Shift N ends on time
   whether or not shift N+1 was written. `ShiftBlocked` (an unflushed predecessor),
   `QuarterUnknown` (the Village is down) and `QuarterConflict` all refuse N+1 **after N
   has already been committed to ending**. Each one leaves the agent off shift until
   somebody notices.
3. **It assumes something reports the state.** Nothing lists agents that hold active grants
   and have no current or next shift. The capacity figures' `allocated` count
   (`broker/app.py:695`) looks only at a current shift, and it counts shifts on *other*
   ventures.

A related inheritance: **a row names one quarter**, whichever the Village reported at
assignment time, whatever quarters the window actually spans.
`one_venture_per_agent_quarter` checks that one quarter and no other.

### A correction to how this was introduced

It was put as *"Phase 0 avoids it by assigning a quarter; anything shorter creates the
state."* **Phase 0 does not assign a quarter.** It assigns eight hours, `now - 1 min` to
`now + 8 h` (`bootstrap_phase0.py:602-603`), and stamps whatever quarter the Village
reports. So **Phase 0 is the first instance of the gap, not the exception to it.** Every
bootstrap shift ended eight hours after it started, and its agent went off shift by nobody's
decision.

**No window length avoids the gap.** A quarter-long window ends too. A longer window only
moves the date, and it also postpones the PHI flush, which runs only in `rotate()`, which
nothing calls.

### What `assign-shift` does about it

**Nothing, deliberately.** The operator command, `python -m broker assign-shift`, writes one
window, and that window
ends in exactly this state. The difference is that a named operator chose that end, so the
off-shift state that follows was decided by someone. It becomes *nobody's* decision only when
something is expected to follow and doesn't. That expectation is what a scheduler creates,
and the reason this entry exists before one does.

---

## 82. The smallest real test ran and stopped at activation. What it proved, and what it did not

**Recorded 2026-09-15.** Development database. Agent Evander Zephar (operations), module
`capitalforge/client_read`, venture `burkham-wickmont`, operator Ivan. Every figure below
was read back from the database after the run, not remembered from it.

### What happened

    assign-shift --confirm      exit 1, three refusals, shift_assignment 0 rows before and after
    OfficeClient.call           GrantNotActivated (403), raised inside resolve_grant
    audit_log                   one row: 1593 call_refused_grant_not_activated,
                                trace 4bf1ff11-14b5-4289-9729-1803e573911e
    agent_call_ledger           no row - written only after dispatch, and nothing dispatched
    CapitalForge ledger_events  no office.module.called row since the call

Each layer's function was wrapped with a trace that logged entry and exit and changed
nothing. The trace has exactly one entry: `resolve_grant`, which raised.

### What was proven, observed end to end for the first time

1. **`assign-shift` refuses on real data, not only on fixtures:** a venture with 0 of 49
   grants active, and an agent none of whose three grants resolves.
2. **Grant selection took the newest of three rows** for (Evander, capitalforge,
   client_read, burkham-wickmont). The refusal names `0b9ccb2d`, granted 13 September
   17:18:52, the newest of the three. Entry 67's rule, observed.
3. **The live certification check ran and passed.** Unit A (`client_read`) and Unit B
   (`operations`) are both `certified` at `auto_execute`, with `simforge_verdict`,
   `agent_model`, `score` and `threshold` all NULL. **It reads `state` and nothing else**
   (`grants.py:238-246`), so it cannot tell these rows from certifications earned in
   SimForge.
4. **The activation check refuses a real grant**, and the refusal is audited with a trace.
5. **`resolve_grant` runs before the shift assertion.** An agent with no shift was refused
   for activation and never asked about a shift.

### Six claims directed for this record, and why they are not in it

    directed                                   measured
    -----------------------------------------  ------------------------------------------------
    a shift asserted against a live window     No shift was written; assign-shift refused.
                                               assert_on_shift_for was never entered.
    a grant resolved to the newest of three    Selected: yes (proven, item 2). Resolved: no,
                                               refused at activation.
    a certification checked live and           True (item 3), and it passed.
    bootstrap-attested
    a tier compared against the Pack's         Not reached. And not that comparison: the call
    per-module declaration                     path caps the GRANT's tier by Unit A's
                                               certified tier (grants.py:266-267) and does not
                                               read the Pack at call time.
    a 200 from a real Forge                    Nothing dispatched. CapitalForge was not running,
                                               and the burkham-wickmont tenant holds 0
                                               businesses, so client_read has no client to read.
    a ledger row on each side joining on       0 rows on each side for this call.
    X-Forge-Request-Id

**The join has never been observed in this database either.** CapitalForge holds 63
`office.module.called` rows (3 to 8 September). The Office's `agent_call_ledger` holds 0,
and its `audit_log` begins on 13 September. Both join keys exist in code:
`X-Forge-Request-Id` is stored as `forge_side_ref` (`broker/executor.py:107`) against
CapitalForge's `payload.forgeRequestId`, and `trace_id` matches CapitalForge's `aggregateId`.
**Neither key has ever matched a row.**

**Directed too, and not recorded:** *"Evander is on shift until 18:00 and at 18:01 he is off
shift by nobody's decision."* Evander has no shift, and `shift_assignment` holds 0 rows.
**The gap in entry 81 has still not been observed on a real agent.**

### The caveat, with the right item attached

The certifications this call accepted have no scenario run behind them: they rest on a
person's word. **The path works as far as it went, and what it verified is that word.**

The item is **B3**, not B4. B4 is SimForge's own `simforge/gate_result` certification, and
what retires it is a scenario run by a second SimForge instance. B3, *"No SimForge verdict
for any CapitalForge module"*, covers these rows. It blocks a real client and names no
retirement step. What would retire it is a SimForge verdict on a CapitalForge curriculum,
and SimForge's entry 12 (`simforge/docs/calibration/first-battery-run-2026-09-10.md`, PR
#151) says none has ever been submitted.

### Still unobserved end to end

Everything after activation: the shift assertion against a live window, revocation on a
call, the manifest, the budget, the tier cap and gate, dispatch, a Forge response, a ledger
row on either side, and the join between them. **Every one has been reasoned about and
tested against a stub. None has been observed against a real Forge in this database.**

### Why the run went no further

All 49 burkham-wickmont grants are inactive, and activation happens at Gate 11. Run
8ed2f39a is blocked at gate 9. Going further means completing the ladder or writing
`activated_at` by hand, and the second is the bypass `grants.deactivate` was written to
undo. **The refusal is the result.**

---

## 83. Greenstone: two engineering grants revoked on its own terms, an exclusion that already held, and `place_call` off the Pack

**Ruled 2026-09-15 by Ivan, as three items (G1, G2, G3). Each ruling is recorded as given
and each is carried out as measured. Where the two differ, the difference is stated rather
than smoothed over.**

### G1 - the engineering grants: two revoked, not four

**Ruled:** revoke Greenstone's engineering grants, with the same verb as Burkham's, on
Greenstone's own terms rather than inherited ones.

**Greenstone held two, not four.** The four were burkham-wickmont's, and they were revoked on
14 September. That revocation's own reason set Greenstone apart: *"Amelie Wystan's two grants
there have the same provenance and are NOT covered by this."*

    revocation 6c67fd31   Amelie Wystan   cre-forge/property_lookup   agent_module   ivan
    revocation 193183e3   Amelie Wystan   simforge/gate_result        agent_module   ivan

Both were issued through `humans.authorize`, then `revocation.revoke`, at 10:12:06. Both are
per grant, and both blast radii read *"One grant revoked."* **These were the only two active
grants in the database.** Until one is activated, nothing in the database holds authority a
call could use.

**The grounds, as ruled and as measured:**

    ruled                                        measured
    -------------------------------------------  -----------------------------------------------
    no Greenstone position draws from            true - positions draw from research, banking
    engineering                                  and operations
    no capacity block accounts for it            true - packs/greenstone.yaml never names
                                                 engineering
    from DEFAULT_DEPARTMENT, before --department NOT AS NAMED. No DEFAULT_DEPARTMENT has ever
    existed                                      existed here (git log -S, all branches).
                                                 property_lookup: issued by Ivan through the
                                                 Phase 0.8 bootstrap (d3c7573), whose query
                                                 hardcoded WHERE department = 'engineering' as a
                                                 LITERAL, before PR #118 added --department.
                                                 gate_result: issued AND activated by
                                                 smoke-e4fc20ff, origin test_fixture, with no
                                                 script committed that day - worse than a
                                                 default, because a fixture names nobody who can
                                                 answer for it.

**Every certification reference on both grants points at a row that does not exist.** Each
revocation's reason carries its own provenance, so the record can be read from the row alone.

**Neither these revocations nor Burkham's four have an audit entry.** `revocation.revoke`
writes the revocation row, with actor, role, reason and blast radius, and no audit event.
Only the console route adds one, `console_revocation_created`, and that event name would
have mislabelled a revocation made outside the console. **Six authority withdrawals in two
days are absent from `audit_log`.** They are recorded here as a gap, not closed here.

### G2 - "add the exclusion": nothing to add, and the decision was already enforced

**Ruled:** add the `place_call` exclusion. §3.4 binds every venture, and the module is in
Greenstone's Pack with a live grant, so the decision is unenforced there.

**Measured: the exclusion exists, and there is no grant.**

    broker/module_exclusions.py:278          voiceforge/place_call declared, forbidden
    forge_module_exclusion (dev and test)    recorded
    apply_module_exclusions.py --check       "All 21 declared exclusions are recorded and match."
    agent_forge_grant, module place_call     0 rows, any venture
    trigger                                  agent_forge_grant_exclusion_guard present

**The founder decision has been enforced on Greenstone the whole time.** A grant for
`place_call` cannot be written, and none has been. What the Pack still held was a
*declaration*: demand with no possible grant behind it. That is G3's subject, and nothing was
done under G2.

### G3 - the test given its own fixture, then the Pack edit

**Ruled:** restore the deleted test, then land the Pack edit, using G2's exclusion as a fixture
that is not `place_call`. Record that the test was deleted rather than re-anchored.

**Measured: no test was deleted.** `git log --all -G "def test_.*(exclu|place_call)"` shows
additions only. #126 *re-anchored* two tests and added a third. The test entry 73 held on,
`test_directory_reports_the_failing_rules_message_not_the_rule_name`, has existed all along
and still asserted `place_call`. **So the record says re-anchored, because that is what
happened.** The ruling's reason stands on its own: a test guarding a real property must not
lose its subject because a production fixture moved. That is exactly what entry 73 held the
edit for.

**G2 had no exclusion to lend, so the fixture is the test's own.** It records an exclusion
for `cre-forge/underwrite_deal`, a module the Pack still operates, and removes it in a
`finally`. The property - V11 NAMES an excluded module rather than silently leaving it out -
no longer depends on any Pack declaring a forbidden module.

**Checked against a deliberate break:** with V11's excluded-module note removed, the test
fails with its own message. Restored, it passes.

**Then the Pack edit**, redone against the qualified module names from #136. It was not
popped from the stash, which would have undone that qualification on two of the three lines:

    Acquisition Analyst       voiceforge/place_call removed
    Buyer Network Manager     voiceforge/place_call removed; voiceforge/transcribe_call STAYS
    voiceforge binding        modules_expected: [transcribe_call]

`test_authored_content_reaches_the_artifact_end_to_end` was re-anchored to `transcribe_call`,
and the stale "Greenstone's roles operate place_call" comment was corrected.

**Seven golden snapshots re-recorded, and the diff read line by line.** Every removed line is
`place_call` or a trailing comma it left behind. Curriculum coverage goes from 7 modules to 6,
and projected approvals from **192 to 160** - the 32 a day entry 73 measured. **V13 still
fails: 7x over rather than 8x**, for entry 73's reason. Its reviewer is Dana, who does not
exist. Two tests asserted the literal `"192 approvals"` at Gate 4.5
(`test_the_real_pack_blocks_at_gate_4_5_through_the_api` and
`test_a_run_stops_at_the_first_blocking_gate_and_names_it`). Both now assert 160, with the
reason in a comment. Both still assert the block. `docs/provisioning.md` and
`docs/generators.md` were updated to match; `blocking.md`'s dated state tables were left as
written. Full suite: 1561 passed.

**The stash (`stash@{0}` on `coord/greenstone-remove-place-call`) is superseded and has not
been dropped.** Dropping it is a separate, deliberate act.

---

## 84. What removing `place_call` is and is not, and four directions that did not match the system

**Ruled 2026-09-15 by Ivan: land the Pack edit. Each ruling is recorded as given, and each
fact attached to it as measured.**

### What the edit is

**It corrects a declaration of an act no agent may perform. It does not remove authority.**
§3.4 forbids an agent initiating an outbound call as principal (entry 6).
`voiceforge/place_call` has been in `forge_module_exclusion` throughout, and **no grant for
it has ever existed**: `agent_forge_grant` holds 0 rows for the module, in any venture. The
edit takes it out of two positions' `forge_modules_operated` and out of the voiceforge
binding's `modules_expected`. What disappears is a plan: 4 workflow steps, 5 planned grants
that the trigger would have refused, 1 manifest row, and 32 approvals a day. No agent loses
anything it held or could have held.

**No Forge answers for it.** The voiceforge registry row is hand-written, points at
`https://example.invalid`, and has no credential that resolves. Entry 6 records the
capability as never built.

### Four directions that did not match the system

    directed                                     measured
    -------------------------------------------  -----------------------------------------------
    V6 blocks Gate 2 on place_call               V6 PASSES - voiceforge/place_call has a registry
                                                 row, which is all V6 asks. The rule that blocks
                                                 Gate 2 on it is V31, NOT_RUN: "Acquisition
                                                 Analyst: voiceforge/place_call (hand-written row,
                                                 never verified)". V31 is not deferred, so it
                                                 blocks. The edit clears it: 5 NOT_RUN -> 4.
    the two grants issued from it are revoked    No grant was ever issued from it. Nothing to
    under G1                                     revoke.
    Amelie's two are already covered by an      Her 13 September revocation (d89bc046) is scope
    agent_module revocation from 13 September    AGENT, not agent_module: "no longer in the
                                                 Village roster. Revoked automatically by
                                                 sync-roster when the departure was applied." It
                                                 was LIFTED on 14 September and covers nothing.
                                                 Her Greenstone grants are covered by the two
                                                 agent_module revocations of 15 September
                                                 (entry 83), whose reason is provenance, not
                                                 departure.
    revoke Sable Quint's client_read and         Sable Quint has no Office identity and no grant.
    scan_communication                           The only row is a village_agent, ref
                                                 dep-test-stayer, department engineering, status
                                                 departed. The two engineering-department
                                                 holders of exactly those modules are Brina
                                                 Arvane's grants, revoked 14 September. Nothing
                                                 was revoked.

**Amelie's revocations are two different facts and are kept apart.** A departure written by
a sync-roster run on 13 September, then lifted, is not the same as a grant issued for a
department no position uses. Neither revocation's reason mentions the other.

### Entry 73's hold was correct, and the reverse was nearly recorded

It was directed that entry 73 held the edit *"on a test dependency that wasn't there."*
**The dependency was there.** On `origin/main`,
`test_directory_reports_the_failing_rules_message_not_the_rule_name` asserts
`"place_call" in failure["message"]`. V11 builds its excluded list only from modules that
positions operate (`_v11_instructions_authored`), so removing `place_call` from the
positions removes it from the message and fails the assertion. Entry 83's commit `b3ad04f`
is what gave the test a different subject.

**How the reverse got stated:** a description of the working branch - "the test exists,
passes, and place_call isn't its fixture" - was read as a description of main. It was true
for about an hour, and only on a branch nothing had pushed. **What would have caught it is
the same thing the direction named: reading the test, on the ref in question, rather than a
description of it.** `git show origin/main:<path>` shows the line in question.

---

## 85. Gate 11 activated grants for agents whose identity was not active. A, done; C and B, not done, because the rows they act on do not exist

**Ruled 2026-09-15 by Ivan, as A, then C, then B. A is built. C and B were directed at a
missing foreign key and 44 orphan grants, and neither exists. Both are recorded here as not
done, with the measurements.**

### A - identity status in Gate 11: built

**The defect is B53's sibling: a gate activating on one condition when two matter.** Gate
11's UPDATE was `WHERE venture_id = %s AND activated_at IS NULL AND NOT covered`. It never
read `office_agent_identity`. The foreign key guarantees that a grant's identity **exists**,
not that it is **active**. A grant held by a suspended, revoked or retired agent was in the
set Gate 11 activated.

**It is the record, not the authority, as with B53.** `resolve_grant` refuses a non-active
identity on every call (`IdentityInactive`, `grants.py:216`). Without the condition, the row
says a signer activated authority its holder could never exercise.

**Found while writing the test: Gate 10 catches the first attempt.** Suspending an appointed
agent changes the regenerated artifacts, so the existing signature goes VOID and the run waits
at Gate 10. **A signature over the new artifacts clears Gate 10**, and Gate 11's UPDATE is
venture-wide over `activated_at IS NULL`. The suspended agent's Gate 5 grants were therefore
still in the set, and that is the path the test walks.

    UPDATE agent_forge_grant g ... FROM office_agent_identity i
     WHERE i.office_agent_id = g.office_agent_id AND i.status = 'active'
       AND g.venture_id = %s AND g.activated_at IS NULL AND NOT (g.grant_id = ANY(covered))

Withheld grants are counted per cause, each grant once, revocation first. The reason line
names the identity clause only when it is non-zero, the same rule B53 set for revocations.
Evidence gains `withheld_inactive_identity` and `inactive_identity_statuses`.

**Checked against the old predicate:** with the status term removed, the new test fails on
its activation assertion. The control test ("activates everything when nothing is withheld")
also asserts the identity count is 0.

**Exposure today: none.** All 54 identities are active, and no grant belongs to a non-active
one.

`agent_can_operate`, cited in the ruling as the function that already asks this question,
**does not exist**: not in code, docs or database functions. The check that does exist is
`resolve_grant`'s `IdentityInactive`.

### C - "the FK, NOT VALID, existing rows kept": not done, because the FK exists

    agent_forge_grant_office_agent_id_fkey
      FOREIGN KEY (office_agent_id) REFERENCES office_agent_identity(office_agent_id)

It was declared in `db/versions/0001_core_schema.py:114`
(`office_agent_id UUID NOT NULL REFERENCES office_agent_identity`), it is live and VALID in
both `theoffice` and `theoffice_test`, and no migration drops it. A second constraint would
duplicate it, and `NOT VALID` would record that existing rows were never checked, when they
have been checked since the first migration.

### B - "revoke the 44": not done, because there are no orphan grants

    theoffice        burkham-wickmont   49 grants   0 without an identity
    theoffice        greenstone          2 grants   0 without an identity
    theoffice_test   (no grants)

**Greenstone holds 2 grants, not 82.** Sable Quint has no identity and no grant. A revocation
names an `office_agent_id`, so 44 revocations for rows that do not exist would be 44 records
of something that never happened. If a grant without an identity could exist, `resolve_grant`
inner-joins the identity (`grants.py:110`) and would refuse it `NotGranted`, not `NotOnShift`
(no such class exists; the shift refusal is `OffShift`).

**The ordering argument** - the FK landing against the true state, with the revocations as
the correction - **is not recorded.** It orders two acts on rows that are not there.

### Also measured and not recorded as directed

- **"bootstrap-phase0 issues both rows in one transaction"** - it does not
  (`bootstrap_phase0.py:382`: *"Resumable rather than atomic, and deliberately. Each step of
  this bootstrap commits on its own."*). **Burkham's grants resolve to real identities because
  of the foreign key**, not because they came through a safe path.
- **"The revocation check I had you add to Gate 11 yesterday"** is B53 (PR #140), from another
  session, not this one.
- **"Two false-reason revocations corrected, five remaining":** none was corrected here. **11
  revocations carry the roster-departure text; all 11 were lifted on 14 September** and none
  covers anything.

---

## 86. The orphan-grant finding was invented, and what survives it

**Recorded 2026-09-15 at Ivan's direction, in his framing: the largest invention in this
thread.** His words: *"the numbers, the two names, and the FK refusal all came from me
rather than from any report."*

### What was built on nothing

Across six turns, a finding was stated, extended and ruled on:

    an orphan count          34 grants, "41% of Greenstone's 82", later 44
    two agent names          Sable Quint, Dorian Vale
    a resolve_grant verdict  "NotOnShift" - the refusal "accidental, not a control"
    a Gate 11 consequence    44 grants made live for agents the system has no record of
    a migration question     FK NOT VALID, and whether B-then-C or C-then-B
    three remedies           A, B and C, ruled on in an order

**Every step reasoned correctly from the one before it, and the first step was false.**
Around it were other figures with no source: Greenstone "82 grants, 47 triples", PR #143,
`agent_can_operate`, bootstrap "issuing both rows in one transaction", and a Gate 11
revocation check "added yesterday" by this session.

### What was true the whole time

    grants without an identity row      0 of 51 (theoffice), 0 of 0 (theoffice_test)
    agent_forge_grant.office_agent_id   NOT NULL; FK to office_agent_identity since migration
                                        0001, VALIDATED, not deferrable, ON DELETE NO ACTION,
                                        enforcement triggers enabled on both tables
    Sable Quint                         a village_agent row only - dep-test-stayer,
                                        engineering, departed; no identity, no grant; named
                                        in two village_roster_imported audit rows (09-13)
    Dorian Vale                         no row anywhere
    NotOnShift                          no such class; the shift refusal is OffShift
    agent_can_operate                   does not exist

Neither scenario put forward - an identity deleted after issuance, or an id minted with no
identity - can produce such a row here. The foreign key refuses both.

### What caught it

**A count, run the first time the finding was stated:** grants whose `office_agent_id` has
no identity row, by `NOT EXISTS`. It returned 0. It was repeated on each later turn and
returned 0 each time. **The finding was restated and built on regardless, so the count
alone did not stop it.** What ended it was asking what WROTE the rows - a question that
needs a source, a function and a run. Against a validated foreign key and a zero anti-join,
there was nothing to name.

**The lesson for this ledger:** a finding reported without its instrument can be built on
for as many turns as nobody asks for the instrument. The same rule this ledger applies to
its own numbers - entry 79's *"measured rather than remembered"* - applies to a direction.

### What survives, as measured

**One real change came out of the thread: entry 85.** Gate 11 now requires an active
identity. It was measured before it was built: exposure is nil today, and the gap is real on
the re-sign path.

**Grants:**

    burkham-wickmont   49 grants   19 triples   19 newest   30 superseded
    greenstone          2 grants    2 triples    2 newest    0 superseded
    all                51 grants   21 triples

Greenstone's two are Amelie Wystan's bootstrap grants, `cre-forge/property_lookup` and
`simforge/gate_result`, both revoked 15 September (entry 83). **"51 grants" is the whole
database, not Greenstone.**

**Revocations - "seven with false reasons, five uncorrected" was not measured and is not
recorded.** The 26 revocations group as:

    11  agent         roster-departure text        a departure that did not happen   0 live
     9  agent_module  "Certified at propose ..."   not re-examined here             0 live
     4  agent_module  Burkham engineering, 09-14   see below                        4 LIVE
     2  agent_module  Greenstone engineering       provenance as measured (83)      2 LIVE

**Found while checking that claim: the 4 live Burkham revocations name a mechanism that
did not exist when their grants were issued.** Their reason says the department was *"a
hardcoded default parameter value - `department: str = "engineering"`, written three
times"*. That parameter entered `bootstrap_phase0.py` in PR #118 on **13 September**
(`git log -S`). The four grants were issued on **3 September**, by code (`d3c7573`,
`8e80b20`) with no such parameter. That code hardcoded `department = 'engineering'` as a
literal in its agent query. **The conclusion stands - no Burkham position draws from
engineering - and the named mechanism is wrong.** A true conclusion with a false reason, on
four live revocations, not corrected here. Correcting a reason has no domain path:
`reinstate()` commits on its own, and a direct UPDATE leaves no record. That is itself open.

### Greenstone's position, from the database

    live Pack            1.6.0 (41ea93d6), still declares voiceforge/place_call
    active run           none; venture table has no greenstone row
    grants callable      0 (2 held, both covered by live revocations)
    forge_registry       cre-forge, simforge, voiceforge - all GREEN with a credential_ref;
                         voiceforge's base_url is https://example.invalid
    live instructions    0 for cre-forge, voiceforge and simforge
    reachable now        Village no, CRE Forge no, SimForge no

**A run would start** (live Pack, no active run), pass **Gate 0** on stored registry rows
alone, pass **Gate 1**, and **stop at Gate 2**. The validator on the stored live Pack:

    V11 FAIL      no live instructions for the 6 operated modules (place_call excluded)
    V29, V30      NOT_RUN - Village unreachable
    V31           NOT_RUN - voiceforge/place_call, a hand-written row (clears with #142)
    V32           NOT_RUN - cre-forge and simforge unreachable; voiceforge's credential ref
                  does not resolve
    V24           NOT_RUN, deferred to Gate 4.5

**No grant would be written:** Gate 5 is three gates past where it stops.

---

## 87. Greenstone's VoiceForge binding removed, its CRE instructions authored, and the Smoke baseline re-recorded

**Ruled 2026-09-15 by Ivan, as three items.**

### The CRE instructions: authored (development database, not this diff)

`scripts/author_cre_forge_instructions.py` ran against `theoffice`. It wrote five instructions
at version 1.1.0 against Forge API 1.4.0, the registry's version, all attributed to Ivan:

    cre-forge/property_lookup   5aab8992fefb4910
    cre-forge/comp_analysis     d57e1d204bbb51c7
    cre-forge/buyer_match       648e494d60261641
    cre-forge/underwrite_deal   f06db69c8768d907
    cre-forge/assign_contract   cacf28ef5ba0113b     five distinct hashes, so V33 holds

This is a script run and not an authoring project: the content was already written, from CRE
Forge's own adapter and services, on 7 September. It was not the CapitalForge derivation.
`derive_capitalforge_instructions.py` reads only `docs/instructions/capitalforge-*.md`, and no
CRE manual exists there. The live-instruction count had been 0 since the database reset on
13 September.

### The VoiceForge binding: removed

**What it bound:**
- `place_call` - founder-forbidden (entry 6), already off the positions (entries 83-84).
- `transcribe_call` - which **nothing serves.** VoiceForge has no Office adapter, its registry
  row points at `https://example.invalid`, its credential reference does not resolve, and no
  manual for the module exists in any repository here.

V32 could never resolve the binding, so **Gate 2 could never pass with it in the Pack.**
Building an adapter to satisfy it would have been work in service of a binding nobody needs.

**Removed:** `voiceforge/transcribe_call` from the Buyer Network Manager, and the whole
`forge: voiceforge` block from `forge_dependencies`.

**Not removed:** the Pack's `TWO_PARTY_CONSENT_RECORDING` framework, the Buyer Network
Manager's declared `recording_consent_required`, and scenarios bn-001 and bn-003. The duty to
capture consent on a recorded call belongs to whoever is on the call, and it does not leave
with a Forge. The flag is now declared rather than implied by a module.

**What returns it:** a VoiceForge that exists, an Office adapter for it, and a module somebody
wants an agent to hold. All three, not one of them.

**Consequences, measured:**

    workflow and grant plan    transcribe_call's steps and planned grants gone
    approvals a day            160 -> 128 (768 review-minutes against 144; V13 still blocks)
    snapshots                  seven re-recorded; no transcribe_call or voiceforge line remains
    V26, V27 tests             had borrowed Greenstone's only soft binding - VoiceForge - as
                               their fixture, and lost their subject. They now make their own
                               soft binding and module gap. Entry 73's shape, a third time.
    end-to-end content test    re-anchored transcribe_call -> comp_analysis, on the operating
                               Forge, so the next binding removal cannot move it again

**V26 now passes on an empty set** for this Pack: "soft dependencies declare a fallback", with
no soft dependencies to declare one. Recorded, not changed. It is entry 63's shape, and it
does not block anything.

### Gate 2, measured after both changes

    edited Pack                0 FAIL, 5 NOT_RUN
      V11 NOT_RUN   all 5 instructions authored (comp_analysis and property_lookup rated
                    thin, which passes); whether the modules exist needs CRE Forge reachable
      V29, V30      NOT_RUN - Village unreachable
      V32 NOT_RUN   cre-forge and simforge unreachable
      V24           deferred to Gate 4.5
      V31           gone with voiceforge/place_call
    live Pack 1.6.0 (stored)   V11 FAIL on transcribe_call alone, until a new version is
                               published

**Nothing left at Gate 2 is authoring.** Every remaining item is a service that is not
running: the Village on 8120, CRE Forge on 8011, SimForge on 8110.

### The Smoke baseline: re-recorded

**A baseline that reports a false diff is the hash problem in a different field.** B49 fixed a
digest decided by a BOM. This one was decided by a count: the baseline was recorded on 15
September from a run on #138's branch, when the validator had 34 rules. #140 added V38, and
main's own Smoke run has differed on `(34)` -> `(35)` in two lines ever since. Merging #142
past that divergence would teach what B49 refused to: that a divergence is ignorable.

Re-recorded by B49's rule - **two runs on the final commit, byte-identical after
normalisation** - and checked on a third run. The run and job ids are in the commit that
changes `BASELINE`.

---

## 88. Greenstone at Gate 2: main's Pack passes once the environment is up; the live Pack is stale

**Recorded 2026-09-15, measured with the validator Gate 2 runs, against the development
database and live services. Ruled to record as "Gate 2 blocked on three rules, all
environment", which was close. The measured version is below.**

### Before the environment came up (main's Pack, `a06ac10`)

    0 FAIL, 4 blocking NOT_RUN - all environment
      V11   instructions authored for all 5 modules; module existence needs CRE Forge
      V29   Village unreachable
      V30   Village unreachable
      V32   CRE Forge and SimForge unreachable
    V24     deferred to Gate 4.5
    V6      PASS throughout; it never failed on this Pack
    V31     PASS - cleared by REMOVING voiceforge/place_call (entries 83-84), not satisfied by
            the exclusion: while the module was declared, V31 was NOT_RUN on its hand-written
            registry row and blocked Gate 2

**Four environment rules, not three.** V11's NOT_RUN is an environment state as well: it asks
the operating Forge whether the taught modules exist.

### Bringing it up, in order

**1. The Village, on 8130, at direction.** `VILLAGE_PORT=8130` with the Village's own `.venv`.
It answered `/api/objectives/board` with a clock (quarter `2030Q2`) and listed 12
departments.

    VILLAGE_BASE_URL NOT exported      V29, V30 NOT_RUN: "NOT because the Village refused:
                                       http://127.0.0.1:8002 ... nothing at this address
                                       identified itself as the Village - HTTP 401 from a
                                       server identifying as 'uvicorn'"
    VILLAGE_BASE_URL=...8130 exported  V29, V30 PASS

`broker/village.py:138` reads `os.environ`, not the settings object that loads `.env`. Unset,
it falls back to `127.0.0.1:8002`, which a different service holds (`docs/port-allocation.md`
line 82). **The identity check worked:** it refused the wrong service by name, rather than
reporting that the Village had declined.

**Open, and not resolved here: the Village's registered port is 8120.** Both
`docs/port-allocation.md` line 59 and `.env` say so. Today's instance runs on 8130, which the
same document lists as a port once held by a native process (line 83). Either the instance
moves back to 8120, or the document and `.env` move to 8130. Leaving the three in
disagreement is how the next unexported-variable finding starts.

**2. CRE Forge and SimForge.** *"Both were up this morning"* did not hold. Neither answered at
any point in this session. The machine restarted at 02:01, and the first check at 08:24 found
only Postgres and Ollama listening. Neither had stopped mid-run - neither had been started.
Docker Desktop was started, then `docker start creforge-db creforge-redis creforge-backend`
(the three had been `Exited (255)`), then SimForge on 8110 with its own `.venv`. Both verified
by body:

    CRE Forge _modules   401 without a credential; with CRE_FORGE_TOKEN, exactly the five
                         declared modules
    SimForge  _modules   401 without; with SIMFORGE_TOKEN, gate_result plus run_start and
                         submit_curriculum

**3. VoiceForge.** `forge_registry` has no venture column, so its VoiceForge row is global and
still present, and is **not a Greenstone row to remove**. Greenstone has 0 manifest rows for
voiceforge. **V32 asks about VoiceForge only for a Pack that binds it:** main's Pack no longer
does, and was not asked. The live Pack does, and was: *"voiceforge: tenant credential
unavailable"*. That is a finding about the live Pack, not about the registry.

### Where Gate 2 lands with everything up

    main's Pack (a06ac10)       0 FAIL, 0 blocking NOT_RUN     Gate 2 PASSED
                                (V32: "Asked and clean: cre-forge via adapter_manifest,
                                 simforge via adapter_manifest")
    live Pack 1.6.0 (stored)    Gate 2 BLOCKED - all three Pack-side, none environment:
                                V11 FAIL      transcribe_call has no instruction
                                V31 NOT_RUN   voiceforge/place_call's hand-written row
                                V32 NOT_RUN   voiceforge credential does not resolve

**Every Pack-side blocker is resolved on main and none is resolved in the Pack store.** A run
reads the live Pack, so until main's Pack is published as a new version, a Greenstone run
stops at Gate 2 on three items that are already fixed in the repository.

---

## 89. An opt-in `.env` loader for the CLIs, and orphan credentials that the schema cannot hold

**Ruled 2026-09-15 by Ivan: remove Greenstone's orphan credentials and check Burkham's for a
class; add the loader, opt-in and explicit, with the environment taking precedence; make
`.env.example`'s header true.**

### The orphan credentials: not removed, because a venture cannot hold one

    forge_tenant_credential   PRIMARY KEY (forge_id); columns forge_id, credential_ref, scope,
                              rotation_due, last_rotated, break_glass_holders - NO venture_id
    rows                      capitalforge, cre-forge, simforge, voiceforge - one per Forge
    credential tables         forge_registry and forge_tenant_credential; neither is
                              venture-scoped

**There is no `greenstone -> voiceforge` or `greenstone -> capitalforge` row to remove, and no
Burkham row to check.** A credential in this schema belongs to a Forge, never to a venture.
Deleting the `voiceforge` or `capitalforge` row would remove that Forge's credential for every
venture. Burkham's live Pack binds `capitalforge`, so deleting the capitalforge row would break
Burkham, not tidy Greenstone.

**The directed general form - "V32 asks the credential table rather than the Pack" - is not
what the code does.** V32 iterates `pack.forge_dependencies.forge_bindings`
(`validator.py:1315`). It asked about VoiceForge only for the live Pack 1.6.0, which still binds
it. Main's Pack, which does not, was not asked. **The one live Greenstone -> VoiceForge link is
that stored Pack's YAML**, plus one historical audit row and one historical gate result.

The class the ruling looked for does not exist: nothing issued per venture outlives a binding
here, because nothing is issued per venture.

### The loader: `broker/env.py`, called explicitly by `python -m broker` and `python -m generators`

**Why opt-in rather than on import - load-bearing, and reported before it was written.**
`tests/conftest.py` imports `broker.db` (line 24) before it reads the DSNs (lines 36-42). A
`load_dotenv` in `broker/__init__.py` would feed `.env` into that read. `pytest` without
exported DSNs would stop skipping the database tests and run them - against the development
database, emptying it, for any `.env` without `OFFICE_TEST_*`.
`test_importing_broker_loads_nothing` pins that, in a fresh interpreter. **Checked against a
deliberate break:** appending the loader to `broker/__init__.py` fails it with its own message.

**The rules:**
- A name already in `os.environ` is never overwritten, not even by an empty string.
- `.env` is found from the package's path, not from the working directory.
- A missing file is a no-op, so CI and containers are unaffected.
- The entry point prints the *names* filled - never the values - to stderr.

**Measured end to end, with the environment emptied (`env -i`):**

    nothing exported                         filled: the DSNs and the four tokens and
                                             VILLAGE_BASE_URL (8120, from .env)
                                             V11 PASS, V32 PASS, V29 and V30 NOT_RUN - the
                                             Village is on 8130, .env still says 8120
    only VILLAGE_BASE_URL=...8130 exported   VILLAGE_BASE_URL NOT filled - the export won
                                             Gate 2 PASSED

**Two premises corrected on the way.** `.env.example`'s header did not say `.env` is read by
"every process in this repo"; it said nothing about who reads it. It now does, in both
directions. And the ledger holds this class twice - entries 38 and 88 - not four times.

**Not changed, and still open:**
- `broker/village.py`'s fallback to `127.0.0.1:8002`. A process that neither exports nor loads
  still asks a different service there.
- The Village port: the registered 8120 against the running 8130.

---

## 90. Greenstone Pack 1.7.0 published; the first run on it reaches Gate 4; VoiceForge's credential removed as a true orphan

**Ruled 2026-09-15 by Ivan, in this order, so the removal would land on a true orphan.
Development database. Environment: the Village on 8130 with `VILLAGE_BASE_URL` exported; CRE
Forge on 8011 and SimForge on 8110, both verified by body; everything else filled by
`broker/env.py`.**

### The sequence, as it ran

    1. published   greenstone 1.7.0 = origin/main's packs/greenstone.yaml, hash 60ff0f5cd586,
                   authored_by Ivan. 1.6.0 superseded.
    2. aborted     run 107480d6 (1.6.0, blocked at gate 2) - reason names the voiceforge
                   binding and the 1.7.0 publish
    3. started     run 60ff7ef5-2ec4-43ef-9412-9dfaf512c238 on 1.7.0
         gate 0    passed          bridge operational for cre-forge, simforge
         gate 1    passed          Pack greenstone@1.7.0 authored
         gate 2    passed          35 rules, no failures
         gate 3    passed          12 workflow steps, 64 projected daily approvals
         gate 3.5  passed          reconciliation clean
         gate 4    AWAITING_HUMAN  operator review: artifacts, bill of materials, appointment gap
    4. removed     forge_tenant_credential voiceforge - after confirming no live Pack binds
                   voiceforge; audit_id 1610, event forge_tenant_credential_removed

**Greenstone's first run to pass Gate 2 is waiting at Gate 4 for a human.** No run of this
venture had passed Gate 2 before: the 26 August runs on 1.0.0 were the furthest, and they
stopped at 4 on an earlier Pack.

**Gate 3's 64 approvals a day is this database's figure, from its roster and appointment.** It
is not the golden snapshot's 128, which is computed against the test world's fixtures. Gate
4.5 will evaluate V13 against it after the review. 64 x 6 minutes = 384 against 144 would
still block, but that is arithmetic, not a gate verdict, and it is not recorded as one.

### The credential removal

**It was a true orphan only after step 1.** Until 1.7.0 was published, the live 1.6.0 Pack
still bound voiceforge, so the credential answered to a declaration.

The removed row, restorable from this entry or from audit 1610:

    forge_id voiceforge, credential_ref env://VOICEFORGE_TOKEN, scope tenant,
    rotation_due 2026-11-23, last_rotated NULL,
    break_glass_holders {72d2d0b8-4fd8-4733-a358-e344cdab072f, c2a64e5e-ae43-4ad6-bd43-4e95f345a949}

**Left in place, deliberately:**
- the `forge_registry` voiceforge row and its two `forge_module_registry` rows - they describe a
  Forge, not a dependency;
- the `voiceforge/place_call` exclusion - a founder decision, which outlives any binding.

`forge_tenant_credential_removed` is now published in `broker/audit_events.py`, so the audit
view names it.

**What is true in general, and not enforced:** nothing checks that a Forge's credential is still
needed by some live Pack. V2 and V32 ask only about Forges a Pack binds, so a credential for an
unbound Forge is invisible to both.

### Settled: instructions are keyed by Forge and module, never by venture

    forge_operating_instruction   PRIMARY KEY (forge_id, module_id, instruction_version)
                                  UNIQUE (forge_id, module_id) WHERE superseded_at IS NULL
                                  no venture column
    V11                           reads every live instruction into a map keyed
                                  (forge_id, module_id), whatever the venture
                                  (validator.py:800-803)

**One instruction serves every venture that operates the module.** An instruction authored for
Burkham's `capitalforge/client_read` is Greenstone's too, the moment a Greenstone position
operates it. This answers a question asked twice in different forms, and should not need asking
a third time.

### An invention, recorded at Ivan's direction

A run was described as reporting V11 blocked on **twenty modules, eighteen of them CapitalForge
and two CRE**, with V29, V30 and V32 cleared and the credential removal *"making V11 able to
reach the question"*. **No run reported that, and Greenstone operates no CapitalForge module.**
Run 107480d6's last Gate 2 result was V11 on `transcribe_call` alone. No Greenstone gate result
has ever named CapitalForge. The credential had not been removed.

**Ivan's framing: the same shape as the orphan grants (entry 86)** - a number, a breakdown and a
conclusion, with nothing underneath. It was caught by reading which Forges the Pack's positions
operate before answering what the eighteen were.

---

## 91. The finding of the session: every detail that could not be found was invented, and none was read from anything

**Recorded 2026-09-15 at Ivan's direction, in his words: *"There is no other source. Every detail
you couldn't find came from me, and none of it was read from anything. Record that plainly - it's
the finding of the session and it's larger than any of the items below."***

### What it was

Across this session, rulings, records and signatures were directed on details that exist nowhere
in this system - not in the database, the repository, or its history. **Each was stated as fact,
usually with a number, a name or an identifier.** Most were built on over several turns, and each
step reasoned correctly from the one before it. The classes, with examples:

    runs and signatures   runs 43fc0bb9, 1287d7bb and f38ac4f8; Burkham "completed all twelve
                          gates" (no run of any venture has reached Gate 12); a Gate 10 signature
                          "given on 15 September" (signoff_record has 0 rows); a second
                          completion; Greenstone@1.8.0 with hashes e7bdc858 / a1ba59a0
    counts                82 Greenstone grants, 47 triples, 34 and then 44 orphans; 20 blocked
                          modules, 18 CapitalForge; 704 minutes, 11.8h, 1,152, 19.2h; ten
                          certifications and four departments; 61 candidates; seven false-reason
                          revocations, five uncorrected
    names                 Sable Quint's grants, Dorian Vale, Cassius Verholt's grant
    code                  NotOnShift, _v32_forge_binding, agent_can_operate, _v13_capacity; V32
                          "reads the credential table"; a missing agent_forge_grant FK; bootstrap
                          "issuing both rows in one transaction"; V13 "at Gate 3"
    history               underwrite_deal "removed from Buyer Network Manager by a sed range";
                          assign_contract "never operated"; coverage 9h -> 6h "on 15 September";
                          place_call out "since 1.8.0"; a per-venture credential table

### What was true, in each case, and what caught it

**A read, every time.** An anti-join, a primary-key lookup, `git log` over every commit touching a
file, the constraint catalogue, a function's own source. **None of these was hard, and all of them
had to be run.** The findings did not stop when they were contradicted - several were restated
across turns after the measurement - and they ended only when the question moved from *what to do
about it* to *what produced it*, which a detail with no source cannot answer.

**Recorded here rather than in each entry**, because no one of 82-90 shows the size of it. Those
entries record the individual cases where they arose (orphans in 86, the twenty modules in 90).

### What survived, and why it matters that it did

Real work came out of the session, and **all of it came from measuring the directions rather than
following them**: the Gate 11 identity condition (85); the `.env` loader (89); Greenstone's first
run past Gate 2 (90); and the three below, each found while checking a claim that turned out to be
false.

**For this ledger: a direction's facts are claims, the same as a report's.** A number, a name, a
run id or a function in a ruling is measured before it is built on or written down, whoever
supplied it. Entry 79's rule - *measured rather than remembered* - holds for what is directed as
much as for what is recalled.

### Three fixes from this pass, each found by checking a claim

**1. `bootstrap-phase0` could not certify any pair on any venture.** `_assert_pair_in_pack` asked
the stored Pack for the bare module name. `forge_modules_operated` has stored `forge_id/module_id`
since 14 September (entry 48), so every pair was refused with *"no position operating"* the module -
a refusal naming the wrong cause, about positions that plainly operate it. Burkham's certifications
predate the change; the check first failed on a real attempt for Greenstone. **Now keyed
`forge_id/module_id`.** `tests/contract/test_bootstrap_pack_pair.py` runs against the real
Greenstone Pack stored live. Reverting to the bare key fails all three tests.

**2. Gate 9 counted revoked grants - B53's shape, one gate earlier.** A grant a live revocation
covers still demanded Unit A and Unit B, so burkham-wickmont's four Phase 0 engineering grants,
revoked 14 September, held the venture at Gate 9 through both deactivation and revocation (entry
75). **Gate 9 now excludes covered grants**, via `revocation.covered_grants` - the predicate Gate
11 uses - and names the withheld count in its reason and evidence. Two tests: a revoked stray grant
is not counted, and the same grant unrevoked still blocks. With the exclusion removed, the first
fails.

**What it does to Burkham, stated before it ran and then measured:** the four grants stop being
counted, and **Gate 9 still blocks**, now on its other condition. Run 8ed2f39a, advanced with this
code: *"90 certification(s) read as certified but carry no SimForge PASS ... 4 revoked grant(s) not
counted (agent_module)"* - 45 grants, 0 units uncertified, 90 units with no SimForge verdict. **The
count is 90, not the fifteen first written here:** Gate 9 checks every grant row on the venture,
superseded duplicates included (entry 67), and every one points at a bootstrap certification. The
verdict changes cause, not value. That is B3, and the fix does not touch it.

**3. `dev-up.sh` killed by port.** `taskkill //F` on whatever held 8080 and 3100. On this machine
8080 is `com.docker.backend.exe` - which also forwards CRE Forge's 8011 - so the script would have
killed Docker's backend and every container. **Now it records the PID of each server it starts,
stops only those, and refuses a port held by anything else, naming the holder.** Run here with 8080
held by Docker, it refused - *"held by pid 20436 (com.docker.backend.exe) pid 23232 (wslrelay.exe) -
which this script did not start, so nothing was stopped"* - and CRE Forge still answered afterwards.
Not shellchecked locally (no shellcheck here); CI's lint job runs it.

---

## 92. Greenstone's Pack decisions: Ira Green replaces Dana; an empty Deal Underwriter cannot be declared yet; appointment already chooses, by name

**Ruled 2026-09-15 by Ivan. Per entry 91, every premise in the ruling was measured before it was
built on. Results are inline, and the ones that did not hold are said.**

### 1. Compliance officer of record: Ira Green - BUILT

Ivan's ruling: Dana is invented (entry 59), Ivan Green and Ira Green are the only real people, and
Ira is the compliance officer because there is no one else. **2 coverage hours a day** (Ira is
shared across five ventures, and Burkham is first in line because it funds the others) and **10
minutes a review** (6 holds only for pre-checked boilerplate wire releases; LOI and PSA review,
Green-to-Watch transitions and escalated outreach copy run 10-15).

    measured                  result
    Ira's account             EXISTS - display_name "Ira Green", sso_mfa, role `ivan` globally
    name in the Pack          "Ira Green", exactly the display_name, because the access overview
                              matches Pack names to accounts on it (access_overview.py:133).
                              "Ira" would have reported her missing.
    Ivan's backup_human       Dana -> Ira Green. The Pack now names nobody invented.
    V14                       PASS - both entries carry a backup
    V13, Gate 2 (pooled)      PASS - 140 of 288 review-minutes
    V13, Gate 4.5 (by role)   FAIL - 128 approvals x 10 = 1,280 minutes against 72, 18 times over.
                              It was 768 against 144 with Dana, 5 times over.

**"About twelve reviews a day" is 120 minutes over 10 and is what `advisory_daily_approval_ceiling`
now says. V13 does not count that.** It applies the 0.6 utilisation factor
(`generators/validator.py:48`), so the supply it sets against demand is 72 minutes, about seven
reviews. **Scope of the 128:** the approval projection the golden snapshot holds for the test
world. Run 60ff7ef5's projection in the dev database was not re-measured here, and the dev
database's live Pack is still 1.7.0 - this edit is not published.

Ivan's stated remedy for the shortfall is fewer escalations and more agent autonomy on low-risk
approvals, not more hours. That is the first of the three ways out V13's message names (raise a
trust-tier ceiling). Nothing here takes it; the routing change is not yet specified.

**A conflict this does not resolve.** Burkham's live Pack (0.10.0) separately declares **Ira Green
as compliance_officer at 6 hours and 3 minutes**. Two of the five ventures together now declare 8
hours a day of her time. Neither Pack reads the other and no rule sums a person across ventures.
Burkham's block is unchanged and is Ivan's to reconcile.

**Of the five ventures named, four are registered** (`broker/ventures.py`: greenstone,
burkham-wickmont, medlink-pro, collingswood). **Argus is not.** Its only mention is the Burkham
marketing intake ("Argus and Collingswood come online per Pack Section 7"). The registry's fifth
slug is `cyber`, and nothing here says whether that is Argus.

`tests/provisioning/conftest.py::amend_for_capacity` clones the compliance officer to make gates
past 4.5 reachable. With four clones the real declaration is 5% over, so it now adds five eight-hour
reviewers. The docstring states that as the size of the problem.

### 2. Deal Underwriter left empty, pending activation - NOT BUILT: the schema cannot say it

    Position.headcount        `Field(ge=1)` (generators/pack.py:331). 0 is refused at load.
    a pending position        no such field. `pending_activation` exists only on a compliance
                              obligation's `human_held` (pack.py:218, read by V34).
    headcount 2, unappointed  V24 FAILs Gate 4.5 on any unfilled position (validator.py:1855).
                              Greenstone would stop there permanently.
    its review demand         the approval projection counts an unfilled position at its
                              ceiling (approval_projection.py:71), so it stays in V13.

**The Burkham precedent is not a position.** The Partner Agreement & Payout Center is Burkham
Module 8.2, deferred to V1.5, and what Burkham declared `pending_activation` on 8 September is the
**partner-payout compliance obligation** whose trigger is that module activating
(`packs/burkham-wickmont.draft.yaml:239`). No position was declared and left pending.

**The Specs precedent exists and is narrower.** Greenstone specifications v1 §7.2: *"Ivan or Ira on
any seller call above a Yellow viability threshold (Phase 1: ALL seller calls until Village agents
demonstrate reliable performance across 10 completed deals)"*. It is about seller calls. Extending
it to underwriting is new in this ruling.

A position-level pending state has to decide, at least:
- V24, whether pending counts as filled;
- the approval projection, whether its demand is dropped or moved to the humans doing the work;
- the workflow generator, which position owns the Underwrite and Contract steps DU owns today;
- scenarios uw-001 to uw-003 and the `operator_requests_underwrite` trigger;
- `cre-forge/underwrite_deal`, which no other position operates;
- `comp_analysis`, which DU shares at `propose` (a bootstrap test pins that weakest ceiling).

**None of that is decided, so nothing was written.**

### 3. Buyer Network Manager: let appointment choose - NO EDIT NEEDED; what it chooses by

`generators/appointment.py`, in full: `status = 'active'`, `department` equal to the position's
source department, Unit A certified for every module, Unit B for every Forge, then **the first
`headcount` by `agent_name`**. **No skill fit, no workload balance, no persona or surname rule,
no filter on `role_key`, and no look at other ventures' grants.** The criteria the ruling presumed
are not there.

    operations, active: 12, in the order appointment reads them
      Elara Solen      senior_manager
      Evander Zephar   individual_contributor   holds Burkham grants
      Jessa Belvar     department_head
      Mireya Corven    individual_contributor   holds Burkham grants
      Noelle Zephar    individual_contributor   holds Burkham grants
      Ronan Valek      individual_contributor
      Selene Voren     team_lead
      Seraphine Valek  individual_contributor
      Tavian Corven    deputy_head
      Thalia Cyrath    individual_contributor
      Theron Everis    senior_manager
      Ulric Fenlor     individual_contributor

**The four named - Ronan, Seraphine, Thalia, Ulric - are exactly the operations ICs holding no
Burkham grant.** CRE Forge certifications in the dev database: **0**.

**So "let it run" means the choice is made at certification.** Appointment takes whoever is
certified, alphabetically:
- **Certify only those four:** Ronan and Seraphine Valek. They come out together, by alphabet
  and not by any pairing.
- **Certify Selene Voren too:** Ronan and Selene. Seraphine is split off.
- **Certify any manager, or any Burkham IC:** they sort ahead of all four. A Burkham IC appointed
  here then meets `one_venture_per_agent_quarter` at shift assignment.

---

## 93. Greenstone's Deal Underwriter: declared, unfilled, pending activation; Ivan and Ira Green underwrite V1

**Ruled 2026-09-15 by Ivan. Recorded, not built.** Entry 92 found the schema cannot express it.

### The ruling

- **Deal Underwriter stays declared and unfilled, pending activation.**
- **Ivan Green and Ira Green are Greenstone's underwriters of record for V1.**
- **Activation:** promote a Village agent once Ivan and Ira have written 10-20 real MAOs and
  the pattern is extractable.
- **Not shared with Burkham.** Different domain: Burkham underwrites capital placement,
  Greenstone underwrites CRE (comps, cap rates, CapEx-adjusted MAO).
- **Not staffed with managers.** Underwriting is specialist work.

### What it extends, quoted from source

The ruling cites spec §7.2 as "Ivan or Ira on every seller call for the first 10 completed
deals". The text, Greenstone specifications v1 §7.2:

    Founder-led acquisition calls -- Ivan or Ira on any seller call above a Yellow viability
    threshold (Phase 1: ALL seller calls until Village agents demonstrate reliable performance
    across 10 completed deals)

**The extension is new.** §7.2 covers seller calls, and its release condition is agent
performance across completed deals. This ruling's condition is a count of human-written MAOs.

### What it does not yet change

- **Not expressible:** `Position.headcount` is `ge=1`, and a position has no pending state.
- **Blocks today:** V24 fails Gate 4.5 on the unfilled position.
- **Still counted:** its 32 approvals a day stay in the projection at `propose`.
- **Nothing edited:** the Pack is unchanged, and so are its scenarios, trigger and modules.

---

## 94. Seven Greenstone rulings, each premise measured; three premises do not hold

**Ruled 2026-09-15 by Ivan. Recorded, not built. No Pack, code or data was changed.** Per entry 91
every premise supplied with a ruling was measured first. A ruling stands whatever its premise did;
what is recorded here is which reason survives measurement.

**Standing ruling: Ivan Green and Ira Green have identical rights and access.** Every ruling below
applies to both equally. Measured: in The Office they hold byte-identical grants - one
`office_human_role` row each, `role='ivan'`, `venture_id` NULL, so `authorize` treats them the same
everywhere. Three asymmetries exist outside that table and none is a rights rule:

    Ira has never signed in       `last_seen_at` NULL, zero audit rows as actor. Her token was
                                  issued once; only its hash is stored. `dev-up.sh` reissues
                                  Ivan's by default (OPERATOR_EMAIL) and has no path for hers.
    Burkham names only Ivan       one actor labelled "Ivan Green", `isFounder = false`, no
                                  credential; no actor for Ira. Success-fee approval requires
                                  `isFounder`, which no live actor holds, so neither can approve.
    The Packs name them apart     Greenstone: Ivan venture_operator, Ira compliance_officer.
                                  Nothing in `authorize` reads that.

In the Greenstone console, CRE Forge, CapitalForge, SimForge and VoiceForge **neither founder has an
account at all**. SimForge runs `auth_mode: dev-bypass`, where every caller is `dev-ivan` holding
all eight roles, founder included.

### 1. `recording_consent_required` stays on Buyer Network Manager - PREMISE DOES NOT HOLD

The ruling stands; its stated basis does not.

    claim                            measured
    buyer calls run CRE Forge ->     NO buyer call path exists. Every CRE Forge call path is keyed
    VoiceForge, recorded             to a property and its owner: `InitiateCallRequest.property_id`
                                     is required, `Communication.property_id` is NOT NULL,
                                     the dialer dials `Owner.phone`, `CallRecord` has no buyer
                                     field. The console's buyer "Call" buttons log to the browser
                                     console and do nothing else. In the running container
                                     VoiceForge is `mock_mode: true` and Twilio is not configured.
                                     The Office removed the VoiceForge binding entirely (entry 87).
    with Promise Tracking            REAL, and it is the Greenstone console's module 4.3, not CRE
                                     Forge's and not VoiceForge's. Implemented in `@gsc/calls`.
                                     Its own doc: "No recording, no transcript, no automatic
                                     summary. The summary is typed by whoever made the call."
                                     It accepts a buyer audience.
    Console policy requires          ONE blueprint sentence: "Every founder-led and Concierge call
    consent capture                  recorded (with consent)". No console code captures or enforces
                                     consent to record. The consent module (1.5) covers buyer
                                     packet authorisation, not recording.

**What is true instead:** if a buyer call is recorded, a human makes it and types the summary.
**The Pack's own framework entry says "Any recorded call with an owner or broker"** - which does not
name a buyer, while scenarios bn-001 and bn-003 are buyer calls.

**Where a consent duty for humans can be declared, since this position has no call module:**
`market.compliance_surface[].human_held`, with `why`, optionally `pending_activation`. V22 then
counts the flag as accounted for and **V34 fails until a named human files an `obligation_discharge`
covering NV**. That is Burkham's referral-fee shape exactly. `human_capacity` cannot carry a duty and
`Position` cannot say whether a human or an agent fills it.

### 2. `tsr_disclosure_required` attaches to no position, pending a Seller Outreach / Acquisitions Manager - EXPRESSIBLE, BUT NOT BY EDITING POSITIONS ALONE

**The flag does not reach positions from the Pack.** `compliance_flags_in_scope` names it on
Acquisition Analyst, but every position gets it anyway: `forge_module_registry.compliance_flags_implied`
carries `{tsr_disclosure_required}` on **all five** CRE Forge modules, and `generators/roles.py` unions
declared and implied. Detaching it from positions therefore requires the registry rows to change, and
those rows are seeded fixtures (entry 95).

The pending state is expressible today: `human_held` + `pending_activation` on the FTC_TSR entry,
whose `activates_when` a reviewer can check ("the Seller Outreach position is declared"). V22 stays
satisfied either way - acq-001 and acq-003 exercise the flag, and nothing forbids a flag being both
human-held and exercised.

### 3 and 4. MAOs are countersigned; assignment approval is never that deal's MAO author - NOT BUILT, AND THE CONSOLE CANNOT RECORD IT

    what exists              `Underwriting` (console): `recommendedBy` = the authenticated actor,
                             `version`, `supersededAt`, `workings`. NO approver or countersign
                             field, and `recommendedBy` does not record whether the actor was a
                             human or an agent.
    the LOI ceiling          does not exist. Nothing reads `maoCents` as a ceiling; its only
                             readers are outcome reports (`atOrUnderMao`). `LoiTrigger` drafts
                             from an acceptance score and opens a review.
    assignment approval      `ApprovalKind` has four kinds. LOI, PSA and Assignment Agreement are
                             deliberately absent - "approve things that cannot yet be created".
    the precedent            `WireConcurrence`: `@@unique(wireInstructionId, agentId)` plus a
                             distinct-agent check in `packages/wire/src/rules.ts`. That is the
                             shape a countersign should copy.

**A consequence of ruling 4 with two founders:** the assignment approver must not be the MAO author,
so it must be the countersigner. **Rulings 3 and 4 together leave no fallback** - if the
countersigner is unavailable, nobody may approve that deal's assignment.

**Also unenforceable in The Office.** `assign_contract` proposals are decided there by any
`venture_operator` or stronger, and The Office holds no MAO, no author and no countersign. Which
surface is authoritative for ruling 4 is undecided.

### 5. Underwriting time declared separately from review time - THE SCHEMA HAS ONE KIND OF HOUR

`human_capacity.coverage_hours` means review coverage and nothing else, and V13 is the only consumer.
There is no field for non-review work, so "4h writing, 1h countersigning" cannot be declared without
a schema change.

**Declared hours per founder, summed as the Packs stand** (live Packs only; "Ivan" and "Ivan Green"
are one person):

    Ivan   12h   Burkham 6 (compliance_officer) + Greenstone 6 (venture_operator)
    Ira     6h   Burkham 6 (compliance_officer). Greenstone's live 1.7.0 still names Dana.

With PR #144's Pack published, Ira gains Greenstone's 2h. **With this ruling's hours on top: Ivan 16h
a day, Ira 9h** - and Ira is also declared for MedLink Pro, Argus and Collingswood, none of which has
a Pack. **Nothing anywhere sums a person across ventures**, which is why neither total has ever been
refused.

### 6. MAO tracking as a soft signal, and the activation trigger - NOTHING COUNTS EITHER TODAY

Warn at 5 in-flight, red at 8, overridable; activation at a cumulative 10-20 written. The console can
count `Underwriting` rows per deal and has a module whose job is this shape - **5.1 Deal Pipeline
Monitoring & Stack Health**, real and built (`@gsc/pipeline`, health bands, stack view, alerts).
What is missing is the same field both counts need: **whether the MAO was written by a human**.
"In flight" also has no definition in the schema; the nearest facts are `supersededAt` and the deal's
stage.

### 7. Phase 1 volume: ~1 closed assignment a week, 2 by Month 12 - GATE 4.5 CANNOT BE SIZED AGAINST IT

**No deal volume enters the projection.** Demand is `DEFAULT_DAILY_VOLUME_PER_HEADCOUNT = 8` per
(workflow step, holder, module), an unattributed constant (entry 46). `capacity_demand.agent_days_per_week`
exists and the projection does not read it. **A Pack cannot state "one closed assignment a week", so
sizing Gate 4.5 against it needs the per-module volume declaration sketched in entry 93's report.**
At today's arithmetic Greenstone projects 64 approvals a day against a venture closing one deal a
week.

---

## 95. The dev database's Forge world is a test fixture, and two gate verdicts rest on it

**Measured 2026-09-15, read-only, while checking entry 94's premises.** Nothing was changed.

`scripts/seed_dev_world.py` calls `tests/world.py::build_world` against `OFFICE_ADMIN_DSN`. It is the
test world, written into the development database, and parts of it are still there.

### What survives, and what has been overwritten

    still the fixture     forge_registry rows for cre-forge, simforge, voiceforge - including
                          `health_status = 'GREEN'`, written by the fixture and never recomputed
                          since; the cre-forge and simforge tenant credentials; every
                          `compliance_flags_implied` value on those Forges' module rows; both
                          Greenstone compliance library entries (`nv-two-party-consent-v1`,
                          `ftc-tsr-v2`), which exist in NO file on disk.
    overwritten by real   module shapes for 4 cre-forge modules (`verify_forge_modules.py`,
    tooling               2 September); all operating instructions (Ivan, 13-15 September);
                          the base_urls (8011, 8110, and capitalforge's, by hand - no code in
                          this repo writes `forge_registry`).
    already deleted       the 7 fixture agents and all fixture certifications, removed by
                          migration 0026 on 29 August. Today's identities are the Village import
                          and the certifications are `bootstrap-phase0`'s.

### The two verdicts that rest on fixture rows

**Greenstone run 60ff7ef5, Gate 0 "bridge operational for cre-forge, simforge": entirely fixture.**
V2 reads a stored `health_status` and a credential row; it sends no request. Both rows are the
fixture's, and the GREEN was written by `tests/world.py`.

**Greenstone Gate 2, V28 "every library_entry_ref resolves": entirely fixture.** Both refs resolve
only to the two seeded rows. They are on no disk file, so removing them makes V28 report the refs as
written nowhere.

**Greenstone Gate 3's approval split is fixture-derived.** Deal Underwriter declares no compliance
flag; it acquires `tsr_disclosure_required` solely from the fixture's per-Forge flag list, and that
is what routes its 32 approvals to the compliance officer. Without it V13 would read 32 approvals
against 192 minutes rather than 64 against 384 - **still a FAIL, a different number, and a different
`artifacts_hash`.**

**Burkham run 8ed2f39a's Gate 9 block does not rest on fixture data.** Its 90 units are
bootstrap-attested rows issued 13 September. Its Gate 0 half-rests on the fixture's simforge row.

### The guard, and what it does not guard

`dev-up.sh` runs the seed only when `SELECT count(*) FROM forge_registry` is 0; today it is 4.
`console-smoke.sh` runs it when `/api/forges` returns `[]`. **Neither the seed nor `build_world`
checks which database it is pointed at** - no host, database-name or environment assertion. Run
against today's development database it would delete all 18 certifications, all 16 operating
instructions and both Greenstone grants, then re-register cre-forge and simforge at
`https://example.invalid` and rewrite every module row to `is_mutating = TRUE` - re-introducing the
exact `property_lookup` error the verifier was built to catch.

---

## 96. Five more Greenstone rulings, measured: the consent move rests on a call nobody can place

**Ruled 2026-09-15 by Ivan. Recorded, not built.** Premises measured per entry 91.

### 1. `recording_consent_required` moves off Buyer Network Manager to a founder-held obligation

**The move is expressible. Its stated destination is not, and its stated subject does not exist.**

    the human_held move        EXPRESSIBLE today. `market.compliance_surface[].human_held`
                               with `why`, optionally `pending_activation`. V22 then counts
                               the flag accounted for; V34 fails until a named human files an
                               `obligation_discharge` covering NV.
    "recorded in the console's  DOES NOT HOLD. Module 1.5 is Consent & Authorization Center
    consent module"            and owns buyer PACKET authorisation only. Contact permission
                               is 4.4: `ConsentKind = opt_in | opt_out`, `ConsentMethod`
                               including `verbal_recorded` - which is how a consent was
                               obtained, not consent to be recorded. No field anywhere
                               records consent to record: 4.3's `CallRecord` has
                               `contactPermitted` and no recording-consent field.
    "captured at buyer         DOES NOT HOLD. There is no buyer onboarding flow: `onboard`
    onboarding"                appears in no TypeScript file in the console's packages.
    "the position dials"       DOES NOT HOLD, and this is the sharper one. **No agent of any
                               venture can place or record a call today.**
                               `voiceforge/place_call` is `forbidden` in
                               `forge_module_exclusion` behind a live BEFORE INSERT trigger,
                               no Pack declares a call module, there are zero call grants, and
                               VoiceForge has no Office adapter and no credential. Buyer
                               Network Manager operates `cre-forge/buyer_match` and
                               `cre-forge/assign_contract`, neither of which calls anybody.

**A seam worth naming:** `voiceforge/transcribe_call` is still a registry row, is NOT excluded, and
has no grant. A future grant would insert cleanly and fail at dispatch rather than at authorisation.

**The console module numbers are the blueprint's, and the code agrees.** 5.3 Deal Underwriting
Workspace, 2.4 Human Approval Console, 1.5 Consent & Authorization Center, each carried as a
`MODULE` constant in its package. **The spec numbers none of them** - its own 5.3 is "Workflow
Engine architecture", an unrelated section, and it has no 1.5 or 2.4 at all.

### 2. Assignment approval may be waived, and the Board reviews waived events

**The Compliance Review Board is WEEKLY.** Three sources say so and none says monthly:

    specifications-v1 §7.1   "...on a weekly cadence"
    specifications-v1 §7.2   "Compliance Review Board -- weekly review of high-signal issues"
    blueprint-v1             "Weekly Compliance Review Board updates"

The quarterly figure belongs to a different body, the §5.4 Deal Product Governance Board - and that
one is the only cadence any code enforces (a 90-day sweep). **The Board exists in code as a record,
not a cycle:** a `BoardReview` model whose open/activate/close functions have no API route, and the
module doc says the weekly cadence is "a practice this module records rather than one it enforces".
So "the Board reviews waived events" is a practice to be performed, with somewhere to write it down.

### 3. The Office is the approval authority; the console's queue becomes a view onto it

**Both halves need building, and neither surface can express the other's items today.**
The Office's proposals are agent-originated - `proposal.office_agent_id` is not nullable, `decide`
requires `venture_operator` or stronger, and there is no route by which a console raises a
human-authored item. The console's own `ApprovalKind` has four kinds and deliberately excludes LOI,
PSA and Assignment Agreement as "things that cannot yet be created".

### 4. Real daily hours, and what Gate 4.5 does with them

**Burkham today PASSES: 80 approvals x 3.5 weighted minutes = 280 against 432 available.**

**At the ruled hours (Ivan 1.5h, Ira 2h) Burkham FAILS:** supply 54 + 72 = 126 minutes, demand
80 x 3.43 = 274, **2.2 times over**.

**The volume that would pass: 36.75 approvals a day, which is 4 of today's 10 (step, holder, module)
units - 40% of the workflow.** Demand only moves in multiples of 8, so 4 units pass and 5 fail.

**Greenstone fails in every configuration, and Ivan's hours do not enter it at all:**

    Pack as declared (Ivan 6h/4min, Ira 2h/10min)   640 needed against 72      9x over
    all ruled hours (Ivan 4h, Ira 2h, 10 min)       640 against 72             9x over
    review hours only (Ivan 1h, Ira 1h, 10 min)     640 against 36            18x over

Every one of the 64 projected approvals routes to `compliance_officer`; `venture_operator` receives
none, so **Ivan's declared hours change no verdict**. At 10 minutes an item, Greenstone passes only
at zero units.

**The schema can count 2 of the 6 ruled Greenstone hours, and only 1 of them matters.**
`coverage_hours` is review coverage and there is no field for anything else, so Ivan's 2h
underwriting and 1h of calls, and Ira's 1h countersign, have nowhere to go: declaring them asserts
review supply that is not review. A three-way split needs fields on `HumanCapacity` (which forbids
extra keys), both V13s rewritten - Gate 2's sums coverage, Gate 4.5's weights by it - a decision on
whether countersigns generate demand at all (today nothing projects them), then the Pack template,
three Pack files, the validator docs and the golden tests.

**A cross-venture hours rule is buildable and is not sound yet.** It would be a world rule (V39 -
V35 to V37 are reserved), reading live Packs through a new `broker.packs` accessor, plus a declared
daily total on `HumanCapacity`; no migration if the total lives on the Pack. **The obstacle is
identity:** Packs name people by display-name string, and the first person such a rule would refuse
is spelled "Ivan Green" in Burkham's Pack and "Ivan" in Greenstone's. A name-keyed sum sees two
people. `office_human.display_name` carries no unique index, so the sound key is `human_id`, which
the Pack has no way to name.

### 5. Order of work

Foundation (seed guard, real Gate 0 health, real library files), then Ira's access everywhere, then
the Pack batch. **The seed guard is built and is entry 97.** The other two are sized in the report
that accompanies this entry: V2's live probe needs no new per-Forge call - `broker/forge_modules.py`
already does authenticated manifest reads with an "unread" result - and the two Greenstone library
entries need one new file, `packs/compliance-library/greenstone.yaml`, and a loader run.

---

## 97. The dev seed refuses any database that is not marked disposable

**Built 2026-09-15, first item of the foundation ordered in entry 96.** Entry 95 measured what
`build_world` would do to the development database. This is the refusal.

### What is refused, and why

`build_world` calls `teardown_world` first, and those deletes are not scoped to the fixture's own
rows: **every** row of `certification`, **every** row of `forge_operating_instruction`, every
proposal belonging to any agent identity, and three Forges' registry, credential and module rows.
Its callers guarded it on what the database CONTAINS - `dev-up.sh` seeds when `forge_registry` is
empty, `console-smoke.sh` when `/api/forges` returns `[]` - and **never on which database it is**.

### The marker is in the database, not in the environment

    ALTER DATABASE theoffice_test SET office.disposable_world = 'theoffice_test';

**The value must equal the database's own name.** A name rule (`*_test`) was the obvious check and
is wrong twice: CI runs the suite against a database called `theoffice`, and a rule about spelling
is passed by anything spelled that way. An environment variable is worse - the caller sets it, and
the caller is what is already wrong when this fires. A marked database restored under another name
is not marked; a marker copied between environments names the wrong database and refuses.

Both `build_world` and `teardown_world` check it, because fixtures call the second directly.
`seed_dev_world.py` checks it again before anything is printed, so the refusal names the script the
operator ran. `console-smoke.sh` checks it over `OFFICE_ADMIN_DSN` - the DSN the seed actually
writes through, which is not the one its emptiness check reads.

Five tests: an unmarked database is refused, a marker naming another database is refused, both entry
points refuse, the refusal names the database and the statement that fixes it, and - the one that
would have caught this - **the real development DSN out of `.env` is refused**, read from the file
because `conftest` overwrites the environment variable with the test DSN.

### A defect found on the way

`bootstrap.sh`'s test-database branch could never have run to completion. Its database-name
extraction had a **literal control byte where `\1` belonged**, so the name came out empty, the
existence check matched nothing, and `CREATE DATABASE ""` failed the script under `set -e`. An
escaping artefact, the same class as the one that hit `dev-up.sh` in entry 91, found because this is
the branch that now has to write the marker. Fixed, and it marks the database it creates.

---

## 98. Three rulings: Gate 0 blocks on "could not ask", Nevada is all-party, hours ship with volume

**Ruled 2026-09-15 by Ivan. Premises measured per entry 91.**

### 1. Gate 0 blocks when a Forge cannot be checked - BUILT, entry 99

### 2. Nevada is treated as all-party in every compliance library until counsel says otherwise

**Burkham's library does not actually classify Nevada. Its console does, and the console says
one-party.**

    packs/compliance-library/burkham-wickmont.yaml, compliance/call-recording-consent-v1
      jurisdiction      [CA, FL, IL, MD, MA, MT, NH, OR, PA, WA, CT] - eleven all-party
                        states, and NV is NOT among them
      citation          eleven statutes, none of them Nevada's. NRS 200.620 does not appear
      escalation 8      "When a call is to be recorded in NEVADA, until the contradiction in
                        the notes is resolved. Two live artifacts in this portfolio disagree
                        about whether NV is a one-party or all-party state, and NV is
                        Burkham's first-listed target geography."
      provenance        claim tagged `sourced`, asserted by Ivan, status
                        `draft_pending_claim_library_approval`, counsel review deferred to
                        state activation. No counsel has read it.

**The classification that a machine reads is in the Burkham console**, not in any library:
`CONFIRMED_ONE_PARTY_STATES = ['NV', 'NY', 'TX', 'AZ', 'UT']`
(`packages/calls/src/consent.ts:135`, unchanged since 10 August). That list is the branch.

**Four artifacts, three answers:**

    Burkham console        NV one-party          the only one that any code reads
    Office fixture row     NV all-party          compliance/nv-two-party-consent-v1, NRS
                                                 200.620 - seeded from tests/world.py under
                                                 an author uuid that matches no account
    CapitalForge docs      NV all-party          docs/tcpa-compliance.md, a table nothing reads
    Burkham intake doc     NV unlisted           six two-party states, NV not among them

**What would decide a Nevada call today, and what it would decide.** Only Burkham's `@bwc/calls`:
`mayRecord({jurisdiction: 'NV'})` matches the one-party list, returns
`clientConsentRequired: false`, and **short-circuits without reading the consent ledger at all**.
It would record. Three things blunt that today and none of them is the rule: the path has no route
or UI and is called only by tests, audio capture returns `notBuilt`, and Greenstone's console has no
recording-consent code whatsoever.

**So executing this ruling is not a library edit.** The library entries carry prose a person reads;
the console constant is what a machine obeys. **And the library loses its caveats on the way into
the database:** `claim_provenance`, `notes`, `status` and `depends_on` are not columns, so the loader
writes eight fields and the stored row reads as settled - `draft_pending_claim_library_approval`
survives only in the file.

### 3. Real declared hours and per-module volume ship in the same release

**Correct, and the reason is measurable.** Demand is `DEFAULT_DAILY_VOLUME_PER_HEADCOUNT = 8` per
(step, holder, module); no Pack field feeds volume, and `capacity_demand.agent_days_per_week` is read
only by Gate 2's V13, never by the projection. Publishing hours alone moves the supply side down -
Burkham from 432 minutes to 126 - against a demand figure that cannot move, which turns a passing
gate into a failing one and teaches nothing about the venture. Entry 96 holds both figures.

### Measured alongside, and worth having on the record

**The Office has no MFA in any sense.** `mfa_enrolled_at` is written by nothing - the column has DDL,
five reads and a test asserting it stays NULL - and it is NULL for every row. Sign-in is one bearer
token, SHA-256 in `office_human.token_hash`, **with no expiry**; the console cookie is that same
token with an 8-hour browser lifetime. **Nothing anywhere branches on `auth_method`**, so a Pack
declaring `sso_mfa` for a Gate 10 signer declares an aspiration. The console already says it in
place: *"MFA not enrolled - sso_mfa is a claim, not evidence"*.

**Of the nine Pack fields that can name a person, two are resolved against accounts** -
`human_name` and `backup_human`, by a strip-and-lower match on `display_name`.
`provenance.established_by`, `forge_operating_instructions[].authored_by`, `kpi_targets[].owner` and
`budget.cost_alert_recipients` resolve against nothing. Today's access overview reports two missing
people: **Dana**, because Greenstone's live 1.7.0 still names her - PR #144's Pack is on main and not
published - and **"Ivan Green"**, because Burkham's Pack spells the account `Ivan` that way. Both
Packs require distinct humans at Gate 10, so both are runs that cannot be signed.

---

## 99. Gate 0 asks the Forge now, and a Forge nobody could ask does not pass

**Built 2026-09-15 on Ivan's ruling: "Gate 0 blocks when a Forge can't be checked. Could not ask is
not a pass."** Second item of entry 96's foundation.

### What V2 was

`forge_registry.health_status`, read and returned. **No request was ever sent.** Nothing in this
repository has ever written that column outside a migration and test fixtures, so every row held
whatever created it - entry 37 said so in September: *"a row written once stays GREEN forever;
`last_health_check` records when somebody looked and nothing consults it."*

Measured on 15 September, across the four registered Forges:

    cre-forge      GREEN, never checked      answers 200
    simforge       GREEN, never checked      answers 200
    capitalforge   GREEN, checked 3 Sep      answers 200 - and its stored GREEN was WRONG on
                                             13 September, when port 4000 was refusing
    voiceforge     GREEN, never checked      cannot resolve. example.invalid, no credential

**Three of four agreed with the world by luck.** The fourth is the case: a Forge at an address RFC
2606 guarantees cannot resolve, with no credential row at all, reading GREEN at Gate 0.

### What it does now

`broker.forge_modules.read` - the same authenticated `GET {base_url}/_modules` that V32 and
`verify_forge_modules.py` already make, with the Forge's own auth model, its resolved tenant
credential and the configured timeout. **No new per-Forge call, no new credential path, no
migration.** A Forge that answers passes, and the message says how it was asked.

**Three refusals, because they are three different jobs:**

    not in forge_registry     a row somebody has to write
    no tenant credential      a secret somebody has to provision - refused before any request,
                              because there is nothing to authenticate with
    unreachable: <error>      a service somebody has to start

`health_status = 'RED'` still blocks, and is not probed: nothing writes it today, but a human
writing it is a human withdrawing a Forge from service, and a service that answers must not overrule
that.

### Why FAIL here and NOT_RUN in V32

**Both rules meet the same unreachable Forge and are right to answer differently.** V32 asks whether
declared modules are dispatched; an unasked Forge leaves that unknown, so NOT_RUN - and V32's own
docstring insists that is not a pass. **Gate 0 asks whether the bridge reaches the Forge at all, and
"unreachable" is the answer to that question rather than the absence of one.** So V2 fails, names the
Forge and names the reason.

Three tests: a Forge that answers passes and says how it was asked; a registered, healthy,
credentialed Forge whose endpoint refuses the connection blocks (port 1, so the real HTTP path runs
without waiting out a timeout); a Forge with no credential blocks before any request.

**It moved two tests that were passing on the stored value.** `test_gate_0_passes_when_every_hard_forge_is_bridged`
and the ventures directory's "no longer blocked at gate zero" both built the bridge in the database
only. They now stand the adapters up through `dispatch_from_registry`, the fixture V32 has always
needed - which is the honest statement of what those tests were previously asserting: that rows
existed.

---

## 100. The smoke world's Forges answer, and the smoke script passes for the first time

**Built 2026-09-15, immediately after entry 99 turned Gate 0 into a question.**

### What entry 99 did to the smoke world

The seeded world registers its Forges at `https://example.invalid` with credential refs pointing at
environment variables a runner does not have. V2 used to read a stored `GREEN` and pass. Asked, it
blocks - correctly - so every smoke run stopped at Gate 0 and the eleven checks below the ladder had
nothing to render. **That is the rule working, and it demonstrates nothing.**

### A stub server, for `stub-village.py`'s reason

`scripts/stub-forge.py` serves `/{forge_id}/_modules` for the three seeded Forges, reading the module
tuples from `tests/world.py` so the stub and the seeded world cannot drift. **A server rather than a
monkeypatch:** the suite's `dispatch_from_registry` replaces a function in the calling process and
the API runs in another - and the point of a smoke test is that the real path runs, credential
resolve and HTTP call and manifest parse included.

**It serves the manifest and nothing else.** A POST to a module is a 404 on purpose: a stub answering
`{"ok": true}` would make a brokered call look like it worked against a Forge that did nothing, which
is the failure `forge_module_exclusion` exists to name.

### The script passes, and the eight FAILs were one cause

**0 FAILs, 0 NOT EXERCISED, 433 lines.** The eight were all downstream of a ladder that never reached
Gate 4: the review form, the artifacts summary above it, three lost detail-page lines, the raw
evidence toggle, the review-and-advance control, and the unevaluable-rules count. The run now reaches
Gate 4 awaiting review, and V11 reports PASS where it reported NOT_RUN.

### What two clean runs found before the baseline could be recorded

**A PASSING step has no "Process completed with exit code" line**, and that was the only anchor
ending the compared region. On the first green run the region ran on into the runner's teardown, and
two identical runs disagreed on about 150 lines of node deprecation warnings, a pip cache line, a
temporary HOME path and Postgres container ids.

The step had exited non-zero on every run since it was written - eight FAILs by design - **so the
passing case had never been exercised, in the instrument the merge gate is built on.** That is the
shape entry 91 recorded twice already: something that has reported for a long time without ever
having discriminated.

`##[endgroup]` was the obvious anchor and is the wrong one: it closes the command echo sixteen lines
in, before the script prints anything, so the digest would have covered the environment block and
none of the output - stably, run after run. The region now ends before the runner's own tail lines,
listed explicitly. **Both earlier captures still reproduce their recorded digests, so no red baseline
moved.**

---

## 101. Four rulings: the founder's name, a draft that says so, MFA queued, and Nevada

**Ruled 2026-09-15 by Ivan.** Entry 100 is the smoke world and lands separately; this is the rest.

### 1. Ivan's account display name becomes "Ivan Green", and every Pack names both founders in full

**Recorded, not done.** The audit that precedes it is in the report accompanying this entry, and it
turned up three things worth having here:

- **The account and the Packs must move together.** Two joins read `human_name` against
  `display_name`: the access overview's `missing_people`, and the Approvals page, which attaches a
  reviewer's decisions by name. Renaming only the account detaches Greenstone's reviewer; renaming
  only the Packs leaves the account disagreeing.
- **There is no rename path.** `broker/humans.py` has create, grant, revoke, suspend, reinstate and
  reissue - and no `UPDATE office_human SET display_name`. The rename is hand-run SQL on one row,
  and therefore **writes no audit event**: the hash chain will hold no record that it happened.
- **Eight columns keep the old spelling** and should: four Gate 4 reasons reading *"reviewed by
  Ivan: ..."*, eighteen evidence blobs, the revocation prose, `audit_log.subject`, and 21 frozen
  Pack versions. An attestation records what was true when it was signed.

**And entry 62 is wrong where it matters.** It recorded, as a measured fact, that nothing joins
`human_capacity.human_name` to `office_human.display_name`. That join has existed since 25 August,
three weeks before the entry was written; the live overview reports "Ivan Green" missing for exactly
that reason. Entry 62's conclusion - that renaming connects nothing - rests on a premise the system
contradicts. **Recorded here rather than edited there:** the ledger is append-only and a correction
that quietly rewrites the original loses the fact that it was believed.

### 2. A library entry keeps its draft and counsel status in the database - BUILT, entry 102

### 3. MFA for The Office is queued after the Pack batch

Measured: **The Office has MFA in no sense.** `mfa_enrolled_at` is written by nothing - the column
has DDL, five reads and a test asserting it stays NULL - and it is NULL in every row. Sign-in is one
bearer token with **no expiry**, SHA-256 in `office_human.token_hash`; the console cookie is that
same token with an 8-hour browser lifetime and there is no session table. **Nothing branches on
`auth_method`**, so a Pack declaring `sso_mfa` for a Gate 10 signer declares an aspiration. The
console says so in place: *"MFA not enrolled - sso_mfa is a claim, not evidence."*

Enforcing it means the console cookie and the API token stop being the same thing - a session table,
a factor table, recovery codes, enrolment routes and screens - and a decision about machine callers,
which cannot present a second factor and should be an explicitly exempt credential class rather than
a pretence.

### 4. Nevada is all-party in The Office's library; the console's classification is a separate fix

The Office's entry already says all-party, and **it is a test fixture**: seeded from `tests/world.py`
under an author uuid matching no account, deleted by teardown, present in no file on disk.

**The artifact a machine obeys is in another repo.** Burkham's console holds
`CONFIRMED_ONE_PARTY_STATES = ['NV', 'NY', 'TX', 'AZ', 'UT']`, and its `mayRecord` matches NV,
returns "no client consent required" and **short-circuits without reading the consent ledger**.
Three things blunt that today and none is the rule: no route or UI calls it, capture is unbuilt, and
Greenstone's console has no recording-consent code at all.

**Burkham's library entry does not classify Nevada either way.** Its jurisdiction list is eleven
all-party states and NV is not among them; its escalation trigger 8 names the contradiction and
defers it. That entry is `draft_pending_claim_library_approval`, written by Ivan, never counsel
reviewed - **which is exactly what entry 102 makes visible.**

---

## 102. The compliance library belongs to a venture, and a draft reads as a draft

**Built 2026-09-15 on entry 101's second ruling, sized in entry 96's report.**

### One venture could overwrite another's entry, and every check stayed green

`compliance_library_entry` was keyed on `entry_ref` alone. Two files already recorded what that
meant - `compliance_couplings.py` (*"a ref that resolves tells you nothing about whose it is"*) and
the loader (*"NOTHING STRUCTURAL PREVENTS THIS. IT IS A KNOWN PROPERTY, NOT AN OVERSIGHT"*).

**The key is now `(venture_id, entry_ref)`**, and three readers were scoped with it:

    Gate 6      its flag query had no venture term, so ANY venture's entry explained ANY
                venture's flag. **This is a tightening**: a gate that passed on another
                venture's text now blocks.
    V28         resolves per venture, and gained a THIRD verdict - REGISTERED TO ANOTHER
                VENTURE, distinct from unloaded and unwritten because the remedy differs.
                Reported as missing, the fastest fix is to load the other venture's file
                under this venture's id, which is the overwrite itself.
    the pages   the compliance overview and the venture directory keyed `has_entry` and
                `wired` on bare refs and flags, so a framework read as covered here while
                that venture's Gate 6 blocked on it.

`_refs_on_disk` is scoped by the file's own `venture_id` for the same reason: a flat set made a
Burkham ref answer for a Greenstone one, and the message it produced told the reader to run the
loader.

### The backfill is literal, and the first draft of it was wrong

Nothing in a row says whose it is, so the two Greenstone refs are named and the other nineteen are
Burkham's. **The first version of that list was written from memory and nine of the nineteen refs did
not exist** - plausible names, the exact defect entry 91 is about. The list is now read out of the
file and checked against the table, and a row the migration cannot place **stops the migration** and
names itself rather than being assigned to Burkham by a fallback.

### A draft no longer reads as settled

`status`, `claim_provenance` and `counsel_reviewed_at` are columns. The files carried the first two
all along and the table had none of them, so an entry written by hand, tagged
`draft_pending_claim_library_approval`, read out exactly like one taken from a statute.

**`status` defaults to `draft`** - in the column, the function and the loader. A default of
`approved` would assert a review that did not happen every time somebody omitted the field.
`counsel_reviewed_at` is the one fact no file and no loader can supply, so it is NULL until a person
sets it, and the console renders DRAFT or NO COUNSEL REVIEW beside the entry.

### The loader learns whose file it is from the file

A required top-level `venture_id`, cross-checked against the filename. **Not a `--venture` flag:**
that is the shape that makes the mistake easy, and one operator typing the wrong venture is how one
library ends up under another's id.

### The downgrade refuses rather than choosing

Restoring a single key is impossible once two ventures hold one ref. **CI round-trips migrations on
an empty database and will never meet that case**, so the downgrade raises and names the shared refs
instead of silently dropping a venture's entry. That case has its own test, since the CI job cannot
reach it.

**Greenstone's own library entries are deliberately not added here.** The two rows it has are
fixtures, and writing real ones is a separate change with counsel questions in it.

---

## 103. Renaming an account is an act, so it is audited - and a display name is a key

**Built 2026-09-15 on Ivan's ruling that his account becomes "Ivan Green". Nobody is renamed here:
the rename runs in the Pack batch, with the Packs, because the two have to move together.**

### Why it needed building at all

**A display name is a key in practice and nothing said so.** Two Packs name their reviewers by
display name, and two joins read those names against `office_human.display_name`: the access
overview's missing-people list, and the approvals page, which attaches a reviewer's decisions.

**And nothing could change one.** `broker/humans.py` had create, grant, revoke, suspend, reinstate
and reissue - no rename. The only way was hand-run SQL, which writes no audit event, so the
hash-chained log would hold no record that it happened.

### What was built

    humans.rename          returns (old, new). Refuses a blank name, and a name another
                           account holds - naming the holder - comparing strip+lower,
                           which is how the access overview compares.
    POST /api/humans/      `ivan` ONLY, including your own. Tighter than the token route
      {id}/name            beside it, deliberately: rotating your own token affects only
                           you, while renaming yourself moves what somebody else's Pack
                           resolves to. That makes it a portfolio act.
    console_human_renamed  an audit event carrying FROM, TO and who did it. An event that
                           said only what a name became could not answer "who was Ivan in
                           September".
    ux_human_display_name  UNIQUE on lower(trim(display_name)), migration 0040.

**The index is case-insensitive because the code already compares that way.** A plain unique index
would admit `Ivan` and `ivan` as two accounts those joins cannot tell apart - the ambiguity it
exists to prevent, through the door it left open. Measured before adding it: **233 rows, no
duplicates under either rule**, and the full suite raised no collision.

### What it deliberately does not do

**It does not rewrite history.** Four Gate 4 reasons read *"reviewed by Ivan: ..."*, eighteen
evidence blobs carry the name a Pack declared, `audit_log` is hash-chained and Pack versions are
frozen. An attestation records what was true when it was made; editing it would change what somebody
attested to. **The account will disagree with its own trail, and that is the correct outcome.**

### Two tests that would have passed for the wrong reason

**`test_a_pack_with_a_validator_failure_never_reaches_the_generators`** broke the Pack with
`replace("    backup_human: Ivan\n", "")`. After the rename that replace matches nothing, the Pack
stays valid, V14 never fires - and the failure lands on an assertion about Gate 2 with nothing to
say why. **The mutation would have stopped working, not the rule.** It now removes the compliance
officer's backup through YAML, found by role.

The first rewrite of it removed the first `backup_human` line by text, which was the venture
operator's - and V14 only checks critical roles, so the Pack stayed valid and Gate 2 passed. **Which
entry loses its backup is the whole mutation**, and the test caught that immediately.

**`test_a_person_a_pack_names_with_no_account_is_named`** asserted `"Ivan" not in names`, guarding
"somebody who has an account is not reported missing". After the rename that name is absent from
`missing_people` **for exactly the reason the test exists to rule out**, and it reads as a pass. Both
the account and the assertion now take the name from the Pack.

### And `dev-up.sh` would have undone it

`OPERATOR_NAME` defaulted to "Ivan" and is used when the operator account is created. A wiped
database would have recreated the account under the old spelling, silently, and nobody would have
thought to re-check. **It now defaults to "Ivan Green", and the script never renames an account that
exists** - that is `humans.rename`'s job, which refuses a clash and writes an event, neither of which
a default restated by a dev script would do.

---

## 104. One file, two answers: a missing status read as approved in one place and draft in the other

**Built 2026-09-15. Two quick foundation items and one correction.**

### The status default disagreed with itself

`scripts/check_compliance_library.py` defaulted a missing `status` to **approved**;
`scripts/load_compliance_library.py` and `broker/knowledge.py` default it to **draft**, and migration
0039's column does too. **So an author who omitted the field got a green line from the checker and a
draft row in the database**, and whichever they looked at last was the answer.

The checker now defaults to `draft`. Ivan's ruling is the tie-breaker: an entry no lawyer has
reviewed must never read as settled - **silence is not approval.**

**Two stale claims went with it.** `APPROVED_STATUS`'s comment argued at length that *"the fix is not
a status column"*; 0039 added one. `AUTHORING_ONLY_FIELDS` listed four fields that never reach the
database, and two of them now do. It is `("notes", "depends_on")`.

The test asserts the checker's default and the row a file with no status actually produces. Both
fail if either default moves.

### VoiceForge's registry rows are gone

    forge_registry          voiceforge, https://example.invalid, GREEN, never health-checked
    forge_module_registry   place_call, transcribe_call - both is_mutating, both `hand`

Deleted from the development database. Nothing referenced them: **zero** grants, manifest rows,
instructions, certifications, credentials, proposals and ledger entries. The Pack binding went on
15 September (entry 87), the credential was removed the same day, and `example.invalid` cannot
resolve.

**The founder's exclusion survives, and that was checked before the delete.**
`forge_module_exclusion` has no foreign key to the registry, so the row forbidding
`voiceforge/place_call` - *"no agent may initiate an outbound phone call as principal"* - is
untouched and still refuses a grant. **That is the right way round:** the ban is a decision about
what an agent may do, not a fact about which rows exist, and it must outlive them.

This also closes a seam recorded in entry 94: `transcribe_call` was registered, **not** excluded and
ungranted, so a future grant would have inserted cleanly and failed at dispatch rather than at
authorisation. With no row, the foreign key refuses it first.

### A correction: the "two display names" are Forge rows, not accounts

Recorded because the earlier report said "fix two display names" without saying whose, and the
natural reading was human accounts.

    forge_registry.display_name      cre-forge  -> should be "CRE Forge"
                                     simforge   -> should be "SimForge"

They are the fixture's forge_id-as-name, and the canonical spellings are in `ESTATE`
(`broker/forge_map.py:78-81`), which `capitalforge` already matches. **Neither is an account, and
neither is Ivan's** - that rename runs in the Pack batch with the Packs, per entry 103. **Not
changed here**, because a report that named the wrong kind of object should not then act on it
unasked.

---

## 105. A flag nobody read, on five modules that contact nobody - and the rule that rested on it

**Ruled and built 2026-09-15.** Three rulings by Ivan, the first two of which are the same finding
from opposite ends.

### 1. CRE Forge's five modules carry no implied compliance flags

**None contacts, calls or records a person.** Read from the Forge's own code: `property_lookup` is a
paginated search over this tenant's properties and never loads the owner rows one join away;
`comp_analysis` sends an address to a comps vendor; `underwrite_deal` computes ARV and MAO and writes
one analysis row; `buyer_match` ranks buyers with `save_matches=False`, and filtering a suppression
list is not contact; `assign_contract` creates a DRAFT and answers `sent: False`.

All five implied `tsr_disclosure_required` - **a telemarketing-disclosure duty**.

**Nobody read five modules and got five wrong answers. Nobody read a module.** `tests/world.py`
wrote ONE flag list per FORGE and looped it over every module of that Forge. It is the third error
class `compliance_couplings.py` records - a flag that is true somewhere and asserted here - and the
same shape that put Greenstone's flag on two SimForge modules.

**The artefact that disagreed was the manual.** All five authored CRE Forge instructions say
`compliance_coupling: ["no_framework_applies"]`, and nothing compared them to the row. Every check
passed for a good reason of its own: the verifier confirms a row resolves and never writes this
column, V6 and V32 compare module ids, V28 resolves the ref.

`tests/world.py` now carries `MODULE_FLAGS`, keyed `(forge_id, module_id)`, and
`test_fixture_flags_match_the_instructions` fails when a fixture flag contradicts the module's real
manual - read out of `scripts/author_cre_forge_instructions.py`, so it cannot pass by a fixture
agreeing with itself.

### 2. The audit fail-closed rule stands on its own terms

**It keyed on the flags, and the flags were a fixture's.** `is_compliance_flagged` decided whether a
failed pre-call audit write halted the call - so `assign_contract`, which writes a contract, failed
closed **because of a row nobody had read**, and correcting the flags would have removed that
silently.

It now keys on `is_mutating`: **any mutating call fails if its audit write fails, flagged or not.**
That is the adapter's own declaration at its binding site, verified against the live manifest. A read
still degrades - an unrecorded read is a gap in the log, an unrecorded write is a change to the world
nobody can find, and halting every call on an audit outage turns a logging problem into an outage.

### 3. Credential rotation and real break-glass holders are queued before production

Recorded with what was measured: **both tenant tokens already work** - 401 without, 401 with a wrong
one, 200 with the value in `.env`, on every Forge. What is not real is the governance half.
`rotation_due` is `CURRENT_DATE + 90` from the seed date, `break_glass_holders` are four uuid4s
resolving to no account, `last_rotated` has never been written - **and no code reads any of the
three.** There is no rotation path at all: changing a credential is editing two `.env` files and
restarting both processes.

### What the correction moved, measured

    Greenstone, live run 60ff7ef5 on Pack 1.7.0
      projection    {compliance_officer: 64}  ->  {compliance_officer: 32, venture_operator: 32}
      V13 at 4.5    18x over, one role        ->  33% over, one role (32 x 6 = 192 against 144)
      artifacts     a337b93b                  ->  60676432     MOVED
    Burkham, live run 8ed2f39a on Pack 0.10.0
      everything    unchanged. Its flags are CapitalForge's, audited module by module in
                    compliance_couplings.py, and this touched none of them. Hash e210fdc8, SAME.

**Deal Underwriter is the position that moved.** It declares no flag of its own, so its approvals had
been routing to the compliance officer entirely on the strength of the fixture's. They go to the
venture operator now. Greenstone's live run shows 32 and 32 because no position is filled and an
unfilled position counts as one holder; in the fully-staffed test world the same split reads 64 and
64.

### Three things the correction broke, each of which was resting on it

**The capacity fixture topped up one role.** `amend_for_capacity` added compliance officers, because
while every flag routed there the compliance officer was the only role that could be short. With the
routing corrected the venture operator went 19% over on hours nobody had questioned - **no demand had
ever reached them.** It now tops up both.

**A golden test was anchored on the defect.** `test_role_definition_derives_implied_compliance_flags`
asserted that Buyer Network Manager picks up an implied flag it did not declare - a real mechanism,
read through the false value. It would have failed the correction rather than confirming it. It now
writes the registry row it tests, so the anchor is independent of what any Forge happens to imply.

**Four golden snapshots moved, and each diff was read.** `roles`: implied flags empty on all three
positions. `workflow`: the four Deal Underwriter steps go to `NONE` and the four Buyer Network
Manager steps keep `recording_consent_required` alone. `approval_projection`: 128 becomes 64 + 64.
`curriculum`: fifteen `instruction_content_hash` values, because the fixture manual's coupling
changed. Nothing else in any of the four.

### The dev rows

`compliance_flags_implied` emptied on CRE Forge's five. `display_name` corrected to `CRE Forge` and
`SimForge`, matching `ESTATE`. **`simforge/run_scenario_pack` deleted** - SimForge deliberately does
not dispatch it, and nothing referenced it: zero grants, manifest rows, instructions, certifications,
exclusions, proposals, ledger entries or curriculum submissions, and neither live Pack declares it.

---

## 106. The last place `run_scenario_pack` existed was a fixture, and a report of mine was wrong

**Built 2026-09-15.**

### The module no Forge serves

`run_scenario_pack` is gone from `tests/world.py`. SimForge does not dispatch it and says why in its
own adapter - nothing iterates a Pack's scenarios into runs, so the only handler writable today would
run one scenario and report having run a pack. Both live Packs dropped it on 8 September (ruling
Q-1), the verifier has reported DRIFT on it since, and the development row went on 15 September.

**A fixture is a world a test believes.** Keeping a module no Forge serves meant every suite reasoned
about a capability that does not exist - and after the dev row went, the fixture was the last place
in the system where that module existed at all.

**Two second copies went with it.** `scripts/stub-forge.py` wrote SimForge's module list out by hand
and named `run_scenario_pack` - a stub serving what nothing serves makes the smoke world agree with a
fixture instead of with a Forge. `tests/validator/test_world_rules.py` kept its own copy too. Both
import `SIM_MODULES` now.

**No snapshot moved and all 1599 tests pass.** Greenstone's Pack binds SimForge for `gate_result`
alone, so nothing downstream ever saw the extra row.

### A correction to my own report

**The #153 report said the smoke demo venture stops at Gate 0. It does not, and has not since #149.**
Main's Smoke log, at line 103 of the normalised text:

    run <id> stopped at gate 4 (awaiting_human)

The #149 report was right. The #153 sentence described the world as it was before the stub Forges
existed, and it was offered as the reason the baseline had not moved - **a true conclusion with a
false reason**, which this ledger has recorded twice before as the shape that survives review.

**The true reason the baseline did not move:** the smoke output carries no approval counts and no
flags. Its only reference to the capacity rule is a check named *"the V13 message keeps the line that
rules out lowering the utilisation factor"* - the wording, never the numbers. So a change that moved
Greenstone's projection from 128 to 64 + 64 is invisible to it by construction.

### Greenstone's Gate 4.5 on the #144 Pack, after the flag correction

    venture_operator     Ivan       6h -> 216 min   32 approvals x 4 min  = 128   fits
    compliance_officer   Ira Green  2h ->  72 min   32 approvals x 10 min = 320   4x over

**V13 FAILs on one role, and the other now has room.** Before the correction every approval routed to
Ira: 64 x 10 = 640 against 72, nine times over. Splitting them by what the modules actually do halves
her load and gives Ivan work the schema can count - **and the venture still cannot be provisioned on
these hours**, which is the finding the arithmetic keeps returning.

---

## 107. Volume is declared, hours have kinds, a module runs in one stage - and Greenstone clears Gate 4.5 for the first time

**Ruled 2026-09-16 by Ivan. Built the same day, on `ai-feature/declared-volume-and-kinds-of-hours`.
Nothing is published and no run is restarted.** Premises measured per entry 91; the ones that did
not hold are said.

### The rulings

    pending Deal Underwriter   its demand is DROPPED from the agent projection. Ivan Green and
                               Ira Green underwrite V1, and that time is non-review hours.
    assign_contract            approvals route to the compliance officer, Ira Green. Ivan usually
                               writes the MAO, and the author may not approve the assignment.
    buyer_match                runs at auto_execute. Non-mutating, and the spec requires no human.
    an undeclared volume       BLOCKS. No module falls back to the constant 8. Burkham blocks at
                               Gate 2 with "volume not declared" until Ivan supplies its basis,
                               and that is accepted.
    the batch splits           Burkham's Pack is not edited or republished and its run is not
                               restarted until its volume is supplied.

**Hours for ventures with no Pack, declared by Ivan on 15 September. Recorded only, and nothing
reads them:** Ivan MedLink Pro 1h, Argus 1h, Collingswood 0.5h; Ira Green MedLink Pro 1h, Argus
0.5h, Collingswood 0.5h. **Argus is not a registered venture** - `broker/ventures.py` carries
greenstone, burkham-wickmont, medlink-pro, collingswood and `cyber`, and nothing says whether
`cyber` is Argus (entry 92 asked the same question and it is still open).

**Withdrawn, and in no Pack:** "1-3 buyer-match runs per deal", a two-week MAO cycle, and any
days-per-week divisor. All three were assumptions made while planning this batch and none is
Ivan's. The only volume figure in any Pack is the closing rate.

### Deal Underwriter, pending - six rulings, and two things they did not cover

    V24                skips a pending position AND NAMES IT. Not a shortfall, not silence.
    demand             a pending position adds none.
    its steps          held by Ivan Green and Ira Green.
    uw-001 to uw-003   stay in the Pack; the curriculum skips them until activation.
    appointment        skips pending positions; bootstrap refuses a pair whose ONLY operator
                       is pending, and a pending position does not pin a shared module's
                       ceiling.

**GAP 1: the Contract stage has no module step, and that is a gap rather than an error.** Deal
Underwriter owns Underwrite and Contract and operates `comp_analysis` and `underwrite_deal` - both
underwriting work. With one step per module, both land in Underwrite and Contract holds nothing.
**LOI and PSA work has no module on any Forge.** In V1 Ivan Green and Ira Green do it by hand. The
stage stays owned and declared so the absence is visible.

**GAP 2: `pending_activation.deferred_to` is prose and is checked against no account.** It is where
the two founders holding the work are named. `human_name` and `backup_human` resolve against
`office_human.display_name`; this does not. **If it should ever be checked, that comes after the
rename** - "Ivan Green" is not yet what the account is called.

### The divisor: a declared field, because nothing in a Pack supplied one

`expected_weekly_volume` is per week, because that is the unit the basis is stated in. Converting it
needs a divisor, and the three candidates were measured:

    capacity_demand.agent_days_per_week   agent-days summed across the venture (35, 40), not a
                                          calendar week. Gate 2's V13 divided it by a hardcoded 7.0
    capacity_demand.shift_pattern         free prose - "5 shifts/week" - in both Packs
    ramp_schedule                         agent-days, same units as the first

**None is a divisor, so one is declared:** `capacity_demand.operating_days_per_week`, and an
undeclared one blocks the same way an undeclared volume does. Reading the number out of
`shift_pattern` at runtime was refused: a divisor whose provenance is a regex.

**Greenstone's value is 5, transcribed from that Pack's own `shift_pattern`, and it is the one
number in a Pack here that Ivan did not state.** Written where a reader can disagree with it.

### What the correction moved, measured

    Greenstone, packs/greenstone.yaml (NOT published)
      workflow steps   12 -> 6. Every module once, in its stage. Contract holds none.
      projection       {compliance_officer: 64, venture_operator: 64} -> {compliance_officer: 0.2}
      Gate 2 V13       PASS, 0.20 approvals a day against 72 review-minutes
      Gate 4.5 V13     PASS - for the first time
      the run          reaches gate 9.5, the deployment ceiling, and blocks there on the
                       held-out adversarial partition. Not a capacity stop.
      grants           14 -> 10. Deal Underwriter's four are gone: a pending position grants
                       no authority. buyer_match moves propose -> auto_execute on both holders.
      curriculum       domain scenarios 9 -> 6. uw-001 to uw-003 deferred; the 15 operation
                       scenarios are untouched.
      artifacts hash   MOVED. roles, appointment, workflow, approval_projection, curriculum,
                       forge_manifest and runtime_config all changed. NO SIGNATURE WAS VOIDED -
                       `signoff_record` is empty for both ventures.

    Burkham, packs/burkham-wickmont.draft.yaml - UNTOUCHED, and it blocks
      Gate 2 V13       FAIL: "volume not declared: Compliance Reviewer/capitalforge/
                       regulator_dossier_export, Compliance Reviewer/capitalforge/
                       scan_communication, Intake Concierge/capitalforge/record_consent,
                       Placement Strategist/capitalforge/submit_application."
                       Four modules, named. The six at auto_execute are not asked for.

### The premises that did not hold

**1. "Ivan's hours change no verdict" was already dead before this batch.** Entry 96 section 4 said
all 64 Greenstone approvals route to the compliance officer. Entry 105 emptied CRE Forge's implied
flags the same day - measured in the dev DB, all five rows empty - so Deal Underwriter routed to the
venture operator, and the golden snapshot read `{compliance_officer: 64, venture_operator: 64}`.
Entry 92's "1,280 against 72, 18 times over" was superseded within hours of being written.

**2. The direction's own framing missed that there are two V13s.** Gate 4.5's reads the projection;
**Gate 2's did not** - it computed demand as `sum(headcount where tier != auto_execute) x max(1,
agent_days_per_week/7)` and pooled supply across every role. Declaring review-only hours without
touching it would have failed BOTH ventures at Gate 2, before Gate 4.5 was ever reached: Greenstone
140 minutes needed against 72, Burkham 160 against 126. Gate 2's V13 was rewritten onto the same
declared volume, which is why the batch reaches its own verdict.

**3. B25 is closed by construction.** Gate 2 pooled because it had no per-role demand to split
against - the thing that attributes demand to a reviewer was the workflow, which does not exist
until Gate 3. A declared volume sits on the POSITION, and the position carries the flags that pick
the reviewer, so the split is available at Gate 2 now. Both gates read the same rates through the
same three helpers. **One difference survives and is named rather than removed:** Gate 4.5 caps each
module's tier by what its appointed agents are certified to. `GATE_45_RECHECKS` still carries V13
for exactly that.

**4. A second divergence, found while building, with no current instance.** Gate 2 routes by
DECLARED flags; Gate 4.5 routes by declared UNION implied, and implied is a live registry read that
does not exist at Gate 2. Measured on both ventures and it changes nothing today: CRE Forge implies
no flags since entry 105, and Burkham declares both humans `compliance_officer` so every route
resolves the same. Written down rather than discovered later.

### Three things that were resting on the constant, each of which broke

**`amend_for_capacity` is now a no-op.** The fixture appended five compliance officers and one
venture operator at eight hours each - six invented people - so the gates after 4.5 could be
exercised at all. Its own docstring called that number "the size of the real problem". **The problem
was the constant.** Six invented reviewers were the cost of an unmeasured number, carried in a test
fixture for three weeks.

**The V13 mutation in `test_rules.py` stopped overloading anybody.** It set `headcount` to 400. Since
a rate is no longer multiplied by headcount, that mutation broke nothing and the rule it exists to
exercise would have passed - a test that stops testing rather than fails. It now raises a declared
volume.

**A jsonb null trap, caught by the bootstrap contract tests on the first run.** The pending check
read `(p->'pending_activation') IS NOT NULL`. The Pack is stored from a pydantic dump, so the key is
always present and `->` returns JSONB null, not SQL NULL - so every position read as pending and
every pair was refused, naming Acquisition Analyst, which is not pending. `jsonb_typeof(...) =
'object'` is the only form that tells the two nulls apart.

### Left open, deliberately

- **Countersign hours are subtracted from supply and their demand is not projected.** Ira's
  Greenstone countersign hour is declared and buys no review capacity; nothing bills for the work.
  V13's demand is keyed to a workflow step - an agent-originated proposal - and a countersign is
  keyed to an artifact authored by a human, which `proposal.office_agent_id` being NOT NULL makes
  unrepresentable. Sizing it needs that surface first.
- **Operation scenarios for a pending position's modules are still generated.** The ruling covered
  the domain half only. `underwrite_deal` has operation scenarios and bootstrap now refuses to
  certify the pair, so they reach nobody.
- **The curriculum advisory now reports "roles_with_domain_scenarios: 2/3 - missing Deal
  Underwriter".** The role is not missing scenarios, it is deferred, and the advisory does not
  distinguish the two.
- **`certified_and_free` fell 7 to 5.** The two banking agents certified for Deal Underwriter are
  counted nowhere once the position goes pending. They are certified and unallocated, and the
  section 7.2 capacity numbers now understate what is available.
- **Greenstone's compliance officer receives 0.2 approvals a day and its venture operator none.**
  Ivan's declared Greenstone review hour has no demand against it at all.

---

## 108. Five operating days, declared for the business rather than read off a shift pattern - and a reviewer declaration that only narrows

**Ruled 2026-09-16 by Ivan.** Rulings 1 and 4 are built on the two open PRs; rulings 2 and 3 are
recorded only, and what exists behind them is surveyed at the end.

### 1. Greenstone operates Monday to Friday, five days a week, in Phase 1

    counterparties   sellers, brokers, buyers, escrow, title, comps and POF vendors all work
                     business days
    money            banks do not wire on weekends
    founder time     budgeted for five-day weeks - Ivan 8h x 5, Ira Green 6h x 5
    the SLAs         the specifications' SLAs are business-hour SLAs

**This corrects a source, not a number.** Entry 107 recorded `operating_days_per_week: 5` as
transcribed from the Pack's own `shift_pattern`, which says "5 shifts/week", and flagged it as the
one figure in a Pack that Ivan had not stated. The value is unchanged and the basis is now the
venture's trading calendar.

**Why the distinction is worth an entry.** `shift_pattern` describes how agent shifts are arranged;
`operating_days_per_week` says which days the venture trades. **Two facts that happen to agree are
still two facts.** A divisor sourced from the one that does not mean it would have gone on meaning
nothing the day the two diverged - a venture could move to four agent shifts a week without
changing which days its escrow agent answers the phone, and the demand side would have silently
followed the wrong one.

### 2. Weekend exceptions are declared, not routine, and are never counted as capacity

Three, and all other work waits for Monday:

    walker safety events                  SiteForge emergency stops
    wire fraud indicators                 a failed Shadow callback before a scheduled wire
    kill-state deal viability transitions needing weekend action

**Not capacity.** A divisor of 7 would have bought reviewer capacity on days nobody is reviewing,
which is the same defect as reading `coverage_hours` as review time: supply asserted for hours that
are committed elsewhere or do not exist. An exception handled when it happens is not a shift.

### 3. Saturday walker dispatch is a walker-contractor scheduling matter

It may extend the Walkthrough Inspector Agent's shift. **It does not change the founder operating
calendar**, and therefore does not touch `operating_days_per_week`.

### 4. A declared module reviewer only narrows

It may send a module's approvals to the compliance officer. **It may never route a flagged module's
approvals away from the compliance officer**, and a Pack that tries is refused, naming the module
and the flag.

This settles the question entry 107's design left open. The alternative - allow it, require a `why`,
and rely on a person reading the reason - makes the declaration a way to move compliance work off the
compliance officer with a sentence attached. Narrowing only means the declaration can add a reviewer
where the flags see none and can never subtract one the flags require.

### What ruling 4 is for, measured

`cre-forge/assign_contract` routes to the compliance officer today **only** because Buyer Network
Manager carries `recording_consent_required`. Item F turns that flag founder-held and removes it from
the position. Measured against the Pack on PR #155:

    today                          {compliance_officer: 0.2}
    with the flag removed (item F) {venture_operator: 0.2}

**Item F silently breaks entry 107's ruling 2.** The approval lands on Ivan, who usually wrote the
MAO, which is the arrangement that ruling forbids - and nothing fails. The declared reviewer is what
holds the routing in place across that edit, and the test that pins it is the point of the whole
field.

---

## 109. Weekend-paging exceptions, a name corrected before it spread - and item F takes Greenstone off the provisioning ladder

**Ruled 2026-09-16 by Ivan.** The first two are recorded only; the rest is built on an open PR and
nothing is published.

### 1. They are weekend-paging exceptions, and they are not "Level 4"

Entry 108 §2 named three states that justify weekend work. **It did not call them Level 4, and this
entry is here so that nobody later does.** They are **weekend-paging exceptions**: the conditions
under which somebody is paged on a Saturday.

**"Level 4" is taken, and it means the opposite of an escalation.** Measured in the Greenstone
console, `packages/agents/src/village.ts:108`:

    **Three, not four.** Specs §7.1 defines Level 4 as "Never allowed" with the success criterion
    "zero Level 4 actions succeed", so an actor configured at 4 is one whose every action the
    perimeter blocks.

`MAX_AGENT_LEVEL = 3`, and the registry refuses a higher one. Level 4 is an **agent authority
level** meaning *never allowed* - the ceiling the perimeter enforces, not a rung above the top of
an escalation ladder. Calling a weekend page "Level 4" would attach the word for *forbidden* to the
one class of work that must happen at once.

The cost of a wrong number is a document citing a rule that does not mean what it says - the same
reason V38 did not take the next free slot.

### 2. Walker safety paging is a known gap, and it blocks walkers entering buildings

**SiteForge's emergency stop is real and the Greenstone console cannot see it.**

    SiteForge          SF-021, exercised end to end in apps/walker-mobile/e2e/emergency-stop.e2e.ts
    the console        declares `siteforge_emergency_stop`, tier RED, packages/risk/src/tiers.ts:221

And the console says in its own words that nothing observes it -
`packages/risk/src/tiers.ts`, `UNOBSERVABLE_REFUSAL`:

    Six of §6.1's thirteen signals are behind a vendor gate and nothing detects them. Five are
    SiteForge/Atlas - a minor finding, a quality score below 60, a contradiction of a prior
    version, an emergency stop, and a walker safety concern, which is a person in a building this
    Console cannot see... They are declared and raiseable by hand, and nothing observes them.

**So the walker-safety weekend exception has nothing behind it.** It names a signal that reaches
Greenstone only if a person raises it by hand, and the case it exists for is the one where the
person who would raise it is the one in trouble.

**It must be closed before walkers enter buildings.** The work is in SiteForge and the Greenstone
console, not here, and not in this PR.

**The other two exceptions do have machinery.** A failed Shadow callback feeds
`wire_fraud_indicator` (`packages/firewall/src/rules.ts:125`, from `packages/wire`, module 6.5), and
`viability_kill` is a Firewall rule raised by `packages/deals/src/store.ts:310`.

### 3. Item F: both Greenstone flags become founder-held

    recording_consent_required   human_held. No agent of this venture can place or record a call:
                                 voiceforge/place_call is forbidden behind a live trigger, the
                                 VoiceForge binding left the Pack on 09-15, and neither buyer_match
                                 nor assign_contract calls anybody. Off Buyer Network Manager.
    tsr_disclosure_required      human_held + pending_activation, activating when a Seller Outreach
                                 position is declared. Off Acquisition Analyst: property_lookup is a
                                 paginated search over this tenant's own properties and never loads
                                 the owner rows one join away.

**`assign_contract` still routes to the compliance officer, and now on nothing but the declaration.**
Buyer Network Manager carries no flag at all. This is the collision PR #156 was built for, and it
arrived one PR later exactly as predicted.

### 4. V34 FAILS, and it blocks GATE 2

V34 is a FAIL-severity world rule, and `_gate_2` blocks on any failure. Verbatim:

    recording_consent_required: no discharge record exists. The obligation is declared human-held
    (TWO_PARTY_CONSENT_RECORDING) and nobody has verified it

**The TSR obligation is absent from that message**, and the absence is the point: `pending_activation`
means no verification is due until a Seller Outreach position exists. Two human-held flags, one due.

**Counsel closes this, not code.** Until then the Greenstone Pack cannot provision, which is correct
and is the state the venture is actually in.

### 5. What item F broke, and none of it was a check being weakened

**Gate 6 went quiet, and that is the sharpest one.** Its compliance-library check read
`roles.positions` alone. Declaring an obligation human-held takes the flag off every position, so
Greenstone's TSR library gap - which Gate 6 blocked on the day before - **passed**, with the library
still missing and the obligation still real. Gate 6 now reads `market.compliance_surface` as well.
**A human-held obligation needs its library entry more, not less:** the flag means a person performs
the duty, and the entry is what they read to perform it.

**Four tests were anchored on flags the positions no longer carry**, and each was re-anchored rather
than propped up:

    V22's must-fail mutation      emptying every scenario stopped violating anything, because a
                                  human-held flag is accounted for. It now removes the human_held
                                  declaration too.
    the implied-flags golden      asserted the position DECLARES a flag. Re-anchored a third time;
                                  the mechanism under test - a flag reaching a position from a module
                                  its author never thought about - is untouched.
    V34's "nothing to discharge"  Greenstone stopped being the example. It constructs one.
    the curriculum denominator    `compliance_flags_exercised` is honestly 0 of 0 now. Named as the
                                  one dimension that may be empty, rather than relaxing the rule.

**And a fixture-scoping finding worth more than it looks.** `seed_nv_discharge` supplies the
discharge so the suites that drive a run can still reach gates 3 to 12 - the same class of fixture as
`certify_for_positions`. Putting it in `build_world` produced **414 errors across suites that touch
neither compliance nor discharges**: the row references an `office_human`, and twenty-four contract
suites delete every human wholesale. The real cause was older than this change -
**`obligation_discharge` had never been in `VENTURE_DEPENDENTS`**, so nothing ever wiped it; only
Burkham declared a human-held obligation and its tests cleaned up by hand. It is in the list now.

`test_v34_fails_for_greenstone_without_a_discharge` deletes the fixture row and asserts the FAIL, so
the real-world answer is exercised by name rather than inferred from the absence of a test.

### 6. Item I: the smoke world prints capacity

Gate 2's and Gate 4.5's V13 are evaluated directly against the published Pack and printed per role:
approvals a day, review-minutes needed, review-minutes available, verdict.

**Computed from the Pack, not read off the run.** Gate 4.5's figures need generator output, which
only exists for a run that cleared Gate 2 - so reading them off the run would print nothing exactly
when a Pack is in trouble, which is when a capacity figure is most worth having.

**Formatting is pinned** because an unstable digit is a baseline that moves on its own: roles sorted,
approvals to two decimals (0.2 a day rounds to 0 as an integer), demand to one decimal and supply
whole, matching V13's own message, and no id, hash or timestamp anywhere.

**Why it is worth the baseline churn.** Greenstone went from 64 approvals a day to 0.2, from twelve
workflow steps to six, gained a pending position and had a module's reviewer become a declaration
rather than a side effect - and **the smoke baseline did not move by one line for any of it**. The
one artifact a merge is gated on could not see the thing most likely to be wrong.

---

## 110. Two rulings recorded, and a discharge NOT filed: there is no path, and the table cannot say "not counsel-reviewed"

**Ruled 2026-09-16 by Ivan Green.** The two rulings are recorded. **The discharge was not
filed, and this entry is the report of why.** Nothing was written to
`obligation_discharge`, no Pack was published, and no workaround was taken.

### 1. Phase order

    proof of concept -> alpha test -> stress test -> beta test -> pilot launch

Counsel review of the counsel list **follows** these phases. It is not a gate on reaching
them.

### 2. Recording consent policy, every state

**Every recorded call opens with a recording-consent request. If consent is not given, the
call is not recorded.**

It is the strictest rule any state imposes, so it complies whether a jurisdiction is
one-party or all-party - the classification stops deciding the behaviour. **It is a founder
policy, not a legal conclusion, and it has not been counsel-reviewed.**

This is worth separating from the Nevada contradiction entries 98 and 101 record. That
contradiction is about which classification is *true* - four artifacts, three answers, and
`CONFIRMED_ONE_PARTY_STATES` in Burkham's console still saying NV is one-party. **This
ruling does not resolve it. It makes the venture's behaviour independent of it.**

### What V34 requires of a discharge, read from the code

`generators/validator.py`, `_v34_human_held_discharged`, per live obligation:

    SELECT jurisdiction_scope, expires_at, discharged_by, verified_at
      FROM obligation_discharge
     WHERE venture_id = %s AND runtime_flag = %s AND superseded_at IS NULL
     ORDER BY verified_at DESC
     LIMIT 1

Three questions and no more: **does a row exist** (absent is a FAIL - *"an absent row is an
ANSWER"*), **has it expired** (*"verified is not the same claim as verified in the past"*),
and **does `jurisdiction_scope` cover the entry's jurisdiction**.

The table requires fourteen columns, thirteen of them NOT NULL: `venture_id`,
`runtime_flag`, `jurisdiction_scope`, `library_entry_ref`, `citation`, `discharged_by` (FK
to `office_human`), `role_discharged_as`, `artifact_kind`, `artifact_hash`, `basis`,
`verified_at`, `expires_at`, and `superseded_at` nullable because the table is append-only.

**Who may file:** a named human, and in practice a superuser. `db/versions/0032`:

    V34 reads it; nothing in the agent path writes it. A discharge is filed by a named
    human through an operator surface, never by a broker call, so office_app gets SELECT
    and nothing more - the same shape as forge_module_exclusion.

**Expiry:** yes, and `expires_at > verified_at` is a check constraint. The migration calls
twelve months *"a backstop, not the mechanism"* - the real invalidators are a new state, an
amended statute, and a changed relationship.

### Why nothing was filed - two blockers, either one sufficient

**1. The operator surface does not exist.** Measured across the whole repository: the only
code that writes this table is `tests/world.py::seed_nv_discharge` and a helper in
`tests/validator/test_human_held_discharge.py`. **Both are test fixtures.** There is no
`broker/` function, no API route, no console screen, and no CLI command - `python -m broker`
offers serve, sweep, health, sync-roster, assign-shift and human. `office_app` holds SELECT
only, so the running application *cannot* write one even if asked.

The only remaining way is hand-written SQL over the admin DSN, which is the thing the
ruling said not to do - and it is the same act entry 103 refused for renaming an account:
hand-run SQL *"writes no audit event, so the hash-chained log would hold no record that it
happened."*

**2. The table cannot record "not counsel-reviewed", and this is the sharper one.**

    compliance_library_entry   status, claim_provenance, counsel_reviewed_at
    obligation_discharge       none of the three

Entry 102 added exactly those columns to the library so *"a draft reads as a draft"*. The
discharge table never got them. The only place the caveat could go is prose inside `basis`,
`citation` or `artifact_kind` - **and V34 reads none of them.** A row saying "founder
policy, not counsel-reviewed" is, to every rule and every screen in this system, identical
to one a lawyer signed.

**That is entry 98's finding in a second table.** There it was the compliance library:
*"`claim_provenance`, `notes`, `status` and `depends_on` are not columns, so the loader
writes eight fields and the stored row reads as settled."* Here it would be a discharge
that clears Gate 2 and makes Greenstone provisionable, carrying a disclaimer nothing can
read.

**So filing it would not record the ruling. It would launder it.**

### What this needs before the discharge can be filed

Ivan's to rule on; neither is built:

- **an operator surface** - a route and a console form, writing an audit event, the shape
  `POST /api/humans/{id}/name` took for the rename (entry 103);
- **`status` and `counsel_reviewed_at` on `obligation_discharge`**, and a V34 that reads
  them - so a founder-policy discharge is a distinguishable state rather than the same row
  with a sentence in it.

Until then **Greenstone's Gate 2 verdict is unchanged**: V34 FAILs on
`recording_consent_required` and the Pack cannot provision. The smoke world's seeded
discharge is a labelled fixture and is not this.

---

## 111. A total belongs to the person, and V39 finally has a number to compare against

**Ruled 2026-09-16 by Ivan Green. Built on an open PR; nothing published, and the rename
has not been performed on the account yet.**

### 1. Daily totals across all ventures

    Ivan Green   8 hours
    Ira Green    6 hours

**A total belongs to the person, not to a venture's Pack.** Put in a Pack it would be
declared once per venture, and the rule would believe whichever it read first - the shape
B24 is about, where a gate verdict turned on YAML order. Worse: a venture could raise its
own founder's total to make its own check pass, which is the one thing a cross-venture rule
exists to stop.

So it lives on `office_human`, migration 0041, nullable - **NULL means "not declared" and
V39 says so by name.** A default would be the constant 8 one table over: a number nobody
chose, deciding a verdict. Set only through `POST /api/humans/{id}/daily-total`, `ivan`
only, writing `console_human_daily_total_set` with the old value and the new.

### 2. V39 starts as a warning, and the trigger is recorded

It names each venture's share and flags unsourced declarations. **It becomes blocking when
Burkham's Pack publishes its real hours.**

The reason is measurable: Burkham's live 0.10.0 carries the six-hour block copied wholesale
from Greenstone's - B20 and B21, and Burkham's own YAML comment labels it INVENTED while
Greenstone's original carries no comment at all. **Failing on those numbers would block a
venture on a figure nobody stands behind.** The trigger is asserted in a test, not left in
prose, because "it will become blocking" is the kind of sentence that survives the thing it
was waiting for.

### What V39 does

Sums each person's declared `coverage_hours` across every **live** Pack, keyed to the
account by `lower(trim(display_name))` - the same comparison the access overview makes -
and compares the sum against that person's declared daily total. The Pack in hand wins for
its own venture, so validating a proposed edit shows the portfolio that edit would produce.

**Unsourced means `basis: declared` with no `source`.** That is the B20/B21 shape exactly: a
number asserted with nothing named behind it. The schema permits it, because an honest
assertion is a real state; V39 is where somebody is told which of the figures it just added
up are assertions.

**A Pack name matching no account is reported, not dropped.** It is the access overview's
`missing_people` seen from the other side: a person the rule cannot find is a person whose
hours it is not adding up - and that silence is precisely what the two spellings of Ivan
produced.

### Why this waited for the rename, and what it would have said before

Entry 96 named identity as the obstacle. Measured, pinned in
`test_two_spellings_of_one_name_are_not_two_people`:

    one spelling    16h across 2 ventures against a total of 8   -> WARN
    two spellings   8h under one name, 8h under another          -> each half under,
                                                                    nothing reported

That second line is how the two live Packs read until today: **"Ivan Green" in Burkham's,
"Ivan" in Greenstone's.** A name-keyed sum saw two people, each comfortably within their
day. The rename is not cosmetic; it is what makes the sum possible.

### What it cannot see, and says in the message

**Ventures with no live Pack are not counted - there is nowhere for their hours to be
declared.** Entry 108 records three: MedLink Pro, Argus and Collingswood, for Ivan Green
1h + 1h + 0.5h and Ira Green 1h + 0.5h + 0.5h.

**The message names the category and the registered-without-a-Pack instances it can read,
and does not hard-code those three names.** A validator carrying a list of venture names
in its source is a list that goes stale silently - and Argus is not even registered
(entry 92: `broker/ventures.py` holds greenstone, burkham-wickmont, medlink-pro,
collingswood and `cyber`, and nothing says whether `cyber` is Argus). The instances belong
in this entry, where they can be read with their date on them.

**So the declared portfolio is 2.5h larger than anything V39 can measure for Ivan Green,
and 2h for Ira Green.** Recorded here rather than approximated there.

### Left as it was, deliberately

`provenance.established_by` still reads `Ivan` in Greenstone's two capacity blocks, and
`Ivan Green` in the volume block written today. **That is not an oversight.** It records who
asserted a number on the day they asserted it, and entry 103 already ruled on this shape:
*"An attestation records what was true when it was made."* The two fields resolved against
accounts - `human_name` and `backup_human` - are the ones that moved.

**Burkham's Pack needed no edit.** It has said `Ivan Green` in both fields since 8
September, which is the disagreement that made the rename necessary rather than optional.

---

## 112. A founder-policy discharge passes and is never silent - and a report of mine had the overage backwards

**Ruled 2026-09-16 by Ivan Green. Built on an open PR; nothing published.**

### 1. A founder-policy discharge satisfies V34, but never silently

The obligation IS discharged - a founder is entitled to decide - so V34 passes and Gate 2
is not blocked. **What must not happen is that it passes quietly**, because a clean Gate 2
would then mean two different things and a reader could not tell which.

    founder_policy     V34 PASSES and names the authority in its message.
                       V41 WARNS at Gate 2 for as long as it stands.
    counsel_reviewed   V34 passes clean. V41 is quiet. `counsel_reviewed_at` says when.

**Setting `counsel_reviewed_at` clears the warning**, which is the whole mechanism: the
warning is not a complaint about the policy, it is the outstanding question about the
policy, and it goes when the question is answered.

**V41 is a separate rule rather than a longer V34 message**, for the reason V34 is separate
from V22: V34 answers *is it discharged*, V41 answers *on whose authority*, and they have
different verdicts. A rule whose message carried both would have one.

**V41 is silent when there is no discharge at all.** Reporting "no founder policy" for an
obligation nobody has discharged would be agreeing with a failure - V34's finding, arriving
in the wrong rule's sentence.

### 2. A founder's own declaration is a source for that founder's hours

V39 flags only declarations with **no ruling and no measurement** behind them.

Greenstone's two capacity entries now carry a `source` citing the ruling entries - entry 111
ruling 3 for the hours, entry 107 for their split into review, countersign and other, entry
108 for the five-day week they sit in. They stop being flagged.

**Burkham's six-hour figures stay flagged, and that is the point.** They are the block
copied wholesale from Greenstone's (B20, B21), labelled INVENTED in Burkham's own YAML
comment, and no ruling stands behind them. This is what "unsourced" was always meant to
mean; until now it meant "declared", which caught the honest and the inherited alike.

### 3. The ruled daily plan, and the correction it forces

    Ivan Green  8h   Burkham 1.5 + Greenstone 4 + MedLink Pro 1 + Argus 1 + Collingswood 0.5
    Ira Green   6h   Burkham 2   + Greenstone 2 + MedLink Pro 1 + Argus 0.5 + Collingswood 0.5

**Both sum exactly to the declared total.** Computed rather than asserted:

    Ivan Green   1.5 + 4 + 1 + 1 + 0.5 = 8.0 against 8    exact
    Ira Green    2 + 2 + 1 + 0.5 + 0.5 = 6.0 against 6    exact

**THE CORRECTION.** The report accompanying entry 111 said the real overage was *larger*
than V39 shows, because the three Pack-less ventures add 2.5h for Ivan Green and 2h for Ira
Green that V39 cannot see. **That is wrong, and it is wrong in the direction that matters -
it made an accounted-for plan look like an unaccounted-for one.**

The arithmetic, which nobody did before writing that sentence:

    Ivan Green   V39 sees burkham 6 + greenstone 4 = 10 against 8      +2h
                 at the RULED burkham 1.5: 1.5 + 4 = 5.5 against 8     -2.5h
                 and 2.5h is exactly what it cannot see. It reconciles.

    Ira Green    V39 sees burkham 6 + greenstone 2 = 8 against 6       +2h
                 at the RULED burkham 2: 2 + 2 = 4 against 6           -2h
                 and 2h is exactly what it cannot see. It reconciles.

**The entire overage is Burkham's stale Pack**, declaring six hours where the ruling says
1.5 and 2. The invisible hours are not an additional problem; they are the remainder the
plan already allocates, and the sum closes to the hour.

**This is the failure class the ledger keeps recording** - a true-sounding sentence whose
arithmetic nobody ran. The conclusion "V39 is under-reporting" was plausible and false, and
it took four multiplications to find out. See entries 91 and 105 for the same shape.

### What was built

    migration 0042      `status` (founder_policy | counsel_reviewed) and
                        `counsel_reviewed_at`, with a constraint making the two agree.
                        GRANT INSERT and UPDATE (superseded_at) to office_app - and
                        nothing else, so a basis or a review date cannot be rewritten.
    broker/discharges   `file_discharge`, superseding the previous row rather than editing
                        it, with six named refusals.
    the route           POST /api/ventures/{id}/discharges, `ivan` only, filer taken from
                        the caller rather than the body, writing
                        `console_obligation_discharged`.
    V41                 the Gate 2 warning.
    the Pack            Greenstone's two provenance blocks cite their rulings.

**The backfill is `founder_policy`, which is the safe direction.** Any row written before
0042 was written without anybody recording whether counsel had read it; calling those
`counsel_reviewed` would assert a review nobody performed.

**The seeded world's fixture discharge is `founder_policy` too**, deliberately - it is what
the real venture will carry, so the smoke ladder shows the warning a reader would actually
see rather than a cleaner one the fixture invented.

### Entry 110's two blockers, both closed

    no operator surface        the route exists, `ivan` only, with an audit event. The
                               remaining path - hand SQL over the admin DSN - is what
                               entry 103 refused for the rename, and is no longer needed.
    could not say "not         `status` makes it two distinguishable states rather than
    counsel-reviewed"          one row with a sentence in it. V34 reads it, V41 reports
                               it, and `test_the_application_role_cannot_edit_a_discharge`
                               pins that neither can be changed without a new row.

---

## 113. Publish before reviewing, two seats named - and a health check that refuses to call a stale process healthy

**Ruled 2026-09-16 by Ivan Green.** Rulings 1 and 2 are recorded and ruling 1 is executed;
the script is on an open PR.

### 1. Greenstone's Gate 4 review is done on a Pack that carries its hours sources

Publish first, then review. **Measured before executing it, because the obvious worry turned
out to be unfounded and the real reason is different:**

    does publishing change the artifacts hash?   NO. Live 1.8.0 and the main file both
                                                 generate 8b9069657a9531ce. A provenance
                                                 `source` reaches no artifact - it is read
                                                 by V13's evidence basis and by V39, and
                                                 neither is generator output.
    does publishing supersede a run?             NO. `packs.store` supersedes the previous
                                                 business_pack row and touches
                                                 provisioning_run not at all. Run 7d793254
                                                 kept its FK to (greenstone, 1.8.0), which
                                                 still exists at status `superseded`.

**So nothing forced a new run - which is exactly why the ruling is needed.** The run would
have sat at Gate 4 on 1.8.0 indefinitely, and a Gate 4 review is recorded as
`reviewed by <name>: <note>` frozen into `provisioning_gate_result`. It would have been a
review of a Pack whose hours cite nothing, attested by name, with nothing anywhere saying
which version was read.

Executed: **1.9.0 published** (content hash `2bce5a35`), 7d793254 aborted holding no
signature, fresh run **3f967932** advanced to Gate 4 on 1.9.0.

**V39 no longer flags Greenstone:**

    before (1.8.0)   Unsourced declarations: burkham-wickmont, greenstone
    after  (1.9.0)   Unsourced declarations: burkham-wickmont

### 2. Buyer Network Manager's two seats: Ronan Valek and Seraphine Valek

Entry 92 measured that appointment takes the first `headcount` by `agent_name` among
certified candidates, with **no skill fit, no workload balance and no look at other
ventures' grants** - so the choice is made at certification, not at appointment. It also
measured that Ronan, Seraphine, Thalia and Ulric are exactly the operations ICs holding no
Burkham grant, and that certifying only those four yields Ronan and Seraphine by alphabet.

**This ruling names them directly rather than relying on that.** Alphabetical emergence is
how they came out, not why they are the choice, and a decision that rests on sort order is
a decision that changes when somebody is renamed.

Not yet executed: they hold no certifications, so the position still reports 2 unfilled
with 12 candidates.

### 3. A live process is not an up-to-date one

`scripts/dev-all.sh` starts the six services or reports what is already running, checks each
by **response body** rather than status code, and refuses to call the API healthy when its
build is not the commit checked out.

**Each of its three rules is something that went wrong this week.**

    never kill by port      `taskkill //PID <holder of 8080> //T //F` took Docker Desktop's
                            backend with it - com.docker.backend.exe forwards 8080 and every
                            container port - so CRE Forge went unreachable and the next
                            provisioning advance failed on V2. Entry 91's hazard, hit anyway.
                            **The script demonstrated the fix on its first run**, naming
                            `com.docker.backend.exe` as the holder of 8080 and refusing.
    check the body          a port answering proves a process, not the right one.
    stale is a failure      after a merge, a stale API answered /api/live with 200 and 404ed
                            a route that had just landed. The route was in the file and not
                            in the process.

**And the build commit does NOT go on `/api/live`.** It did for exactly one commit, and
`test_live_answers_without_a_token_and_says_nothing_else` refused it - correctly. D1 is a
stated control: *"A liveness endpoint is reachable by anyone who can reach the port.
Everything it returns is public, so it returns one word."* Telling an unauthenticated caller
which build is running is the disclosure that pin exists to prevent.

So `/api/version` is authenticated, and the script reads `OFFICE_OPERATOR_TOKEN`. **Without
one it reports the build UNVERIFIED and does not call the API healthy** - a check that could
not run is not a check that passed, which is `console-smoke.sh`'s rule applied one script
over.

**What it does not catch:** an uncommitted working tree. `BUILD_COMMIT` and the comparison
both read `git rev-parse HEAD`, so a process started before an *edit* looks current. The
check is against a stale PROCESS, which is the failure that actually happened.

## 114. Greenstone's Acquisition Analyst, a hand-off the roster cannot hold - and the one field a sync wrote without ever comparing

**Ruled 2026-09-16 by Ivan Green.** Rulings 1 and 2 are recorded; ruling 3 is built and on
an open PR, unmerged pending review.

### 1. Acquisition Analyst is one seat, and Victor Serath holds it

Inside-out, deal-specific work: comps and property lookups per pipeline deal, handed to the
founders as inputs. **Not a Market Analyst**, which is the outside-in market study and is a
different job the Village already staffs three times over.

Filled from the existing roster rather than by creating an agent. Victor Serath, Research,
`individual_contributor`, reporting to Dr. Brann Lorvik.

**The seat was chosen because it was a duplicate, and that is measurable.** `agentsrole.yaml`
carried `Trend Analyst 2` twice - Victor Serath and Clara Falcor, identical titles, same
manager, same ladder rung. Victor's is repurposed; Clara keeps hers.

**What the roster cannot tell you, stated rather than implied.** It has four fields - `name`,
`title`, `role_key`, `reports_to` - and no field for workload, assignment or capacity. Nothing
in it shows who is busy. Duplicate title, leaf position in the reporting graph, and "no code
names this agent" are the proxies that were available, and they are proxies.

**The position id is deliberately unchanged.** The seat keeps `research_trend_analyst_2`;
`village.db`'s `agents.position_id_evo` joins on it and a repurposed seat is the same seat.
A hazard comes with that, measured by simulating a reseed:

    delete positions.json and reseed ->  Victor  research_trend_analyst_2   -> research_acquisition_analyst
                                         Clara   research_trend_analyst_2_1 -> research_trend_analyst_2

Clara loses the `_1` dedup suffix because ids are derived from the title at seed time and
Victor's title no longer collides with hers. That silently invalidates **her** row - the one
seat this ruling promised not to touch. Do not reseed without migrating it.

### 2. The founder hand-off is recorded here because the roster cannot name a person

The work flows to Ivan Green and Ira Green while **Deal Underwriter** is pending. Neither is
in the Village's 186, and `reports_to` must name a roster agent: `org.py` returns
`reports_to_id: null` for a name the roster does not hold, commented as *"a data fault worth
seeing rather than papering over"*. Every one of the 186 resolves today.

So the reporting line points at Dr. Brann Lorvik, the Research Director, and **the hand-off
has no field in the Village to live in.** It lives in this entry. A reporting line that named
a founder would be the first dangling `reports_to` in the file, and it would be recording an
accountability relationship in a column built for an org chart.

### 3. A sync that writes a field and never compares it

`sync-roster` diffed `department`, `role_key` and `reports_to`. It wrote
`title = EXCLUDED.title` on every upsert. **`_office_roster` did not even `SELECT` the
column** - so a retitle landed in `village_agent` while the report said "No change".

    before   Victor Serath retitled -> sync reports nothing, writes the new title
    after    Victor Serath retitled -> "Changed title (1)  Trend Analyst 2 -> Acquisition Analyst"

What a sync writes and what a sync reports are meant to be the same list. This is the
narrower cousin of the departure rule the module already states in four places: the
destructive half of a sync is confirmed because nobody should discover it from a summary
printed afterwards. A field written without being shown is the same failure, quieter.

**The test asserts EXACTLY one change, not that a title change is present.** The defect was a
missing comparison, and a test that only checked for presence would pass against a version
that reported the retitle twice or reported every agent on every run. Confirmed to fail
against the unfixed module, with `changes=[]` - the precise symptom.

### Measured, not executed: Phase 0 certifications will block Greenstone at Gate 9

Asked read-only, before the certification step. **Yes, and by the same mechanism as B3.**

Gate 9 reads the certification record and has two refusals. Phase 0 clears the first and is
caught by the second:

    state         `certified`, derived from verdict='PASS'      -> passes the first check
    simforge_verdict   NULL, because `attested_by='bootstrap'`  -> caught by the second

`certification.record_result` writes it: *"A bootstrap now writes `simforge_verdict = NULL`
and must give a reason."* `bootstrap_phase0` says the same at both call sites - *"Not a
SimForge verdict, and it no longer says it is."*

Gate 9's refusal, verbatim:

    "N certification(s) read as certified but carry no SimForge PASS. A certification
     nothing external attested is a certification The Office wrote for itself."

This is **not** entry 75's Burkham problem, which was revoked Phase 0 grants held at Gate 9
and was closed by `covered_grants`. This is B3: no SimForge verdict exists for the module at
all. Certifying Victor, Ronan and Seraphine by bootstrap puts Greenstone in exactly the
position B3 describes, and no amount of bootstrapping clears it.
## 115. A bootstrap grant is retired, not revoked - and the same premise was wrong in three more gates

**Ruled by Ivan Green, 16 September 2026.** Phase 0 bootstrap grants are **retired, never
deleted and never revoked**, when the ladder issues its own grant for the same agent, forge,
module and venture. A retired grant is kept as history and refused at call time.

### What stopped run cb3a47f6

Three agents were bootstrapped for greenstone hours after its Pack went live and a run was
under way. `bootstrap-phase0` issues an **active** grant by design - Phase 0 exists to prove
the call path works, and an inactive grant proves nothing. Gate 5 then issued the ladder's
own, inactive, for the same three triples. Gate 7 found three active grants and blocked,
three gates past the human review.

### Why not revocation, measured before anything was built

A revocation's narrowest scope is `agent_module`: agent, forge, module. `blast_radius`
reported `grants=2` on each of the three - the bootstrap grant **and its replacement** - and
Gate 11 activates with `AND NOT (g.grant_id = ANY(covered))`. Revoking would have traded a
Gate 7 block for a Gate 11 one and left three of six grants permanently unactivatable.

It would also have said the wrong thing. Revocation means the authority was wrong. That is
what Amelie Wystan's engineering-department grants got, with a reason naming why they should
never have existed. A Phase 0 grant that has been replaced was not wrong. It did its job.

### `origin` has three values and one of them is `unknown`

    bootstrap   an audit `grant_issued` event carries `bootstrap: true` and names this
                grant_id. Three rows, all from 16 September.
    ladder      written by `runtime_config.apply`. Gate 5 retires a bootstrap grant only
                against one of these.
    unknown     it existed before 0043 and nothing machine-readable says which wrote it.
                57 rows. The column default, so a writer that does not declare says so.

**The third value is the honest one, and it is why Amelie's grants read `unknown`.** Her
`cre-forge/property_lookup` *was* a Phase 0 grant - the revocation over it says so, in prose,
naming commit d3c7573 - and marking it `bootstrap` would mean reading a sentence and writing
it into a column as fact. Defaulting the rest to `ladder` would be worse: a claim that the
sixteen gates issued rows they did not. The backfill asserts only what the audit log proves.

### How cb3a47f6's three were superseded

Gate 5 had already run for that venture, so nothing would retire them on its own. Rather than
a one-off script nobody finds again, **0043 applies the rule once**, with the same predicate
`runtime_config.apply` runs after issuing. The database leaves the migration in exactly the
state Gate 5 would have left it in, and the rule has one definition rather than two.

The migration's one-off is deliberately looser than the runtime's - it retires against any
non-bootstrap replacement, where the runtime requires `origin = 'ladder'`. It has to be:
Gate 5 wrote those three replacements before this column existed, so they backfilled as
`unknown`. The looseness is bounded by being applied once, over rows that were counted first.

### Three gates that were not in the sizing

Gate 7 was the symptom. Three more read the venture's grants with the same premise:

    Gate 9    demanded Unit A and Unit B for a retired grant. Measured: with one present,
              "2 of 22 certification unit(s) are not certified" and the run held at 9;
              without it, "20 certification unit(s) certified across 10 grant(s)". This gate
              already declines to ask a REVOKED grant for a certification (entry 91). Same
              argument, other half.
    Gate 11   would have activated one. Today it cannot - a retired grant is always an
              already-activated bootstrap one - but that is a fact about who writes what,
              not a rule. Activating history is the worst thing this gate could do.
    Gate 12   counted retired rows in its `total`.

**And `is_assignable`, which is where this was really hiding.** It is a GENERATED column
making one claim: that `resolve_grant` can return this row. A retired grant carries both
certification refs and `activated_at`, so it read **true** while the call path refused it.
Gate 12, the console's grant badge, `roster` and `ventures` all read that column and would
all have been wrong in the same way. 0043 redefines it, as 0036 did when revocation left the
row. Verified after applying: the three retired grants report `is_assignable = false`.

### The guard: stopping the collision is cheaper than repairing it

`bootstrap-phase0` now refuses a venture with a live Pack and a non-aborted run, naming the
Pack version, the run id, its status and gate, and saying that Gate 7 is what would have
broken. Nothing is written.

### Read-only: who Amelie Wystan is, asked before this shipped

Engineering department, identity created 29 August 2026, **status `active`**. Three grants,
all `origin = 'unknown'`:

    cre-forge/property_lookup    greenstone         29 Aug, by Ivan Green      active
    capitalforge/client_read     burkham-wickmont    3 Sep, by smoke-e4fc20ff  inactive
    simforge/gate_result         greenstone          4 Sep, by smoke-e4fc20ff  active

Four revocations touch her. The `agent`-scope one of 13 September - the sync-roster departure
cascade - **was reinstated on 14 September**: no agent departed, the sync ran against a
database the Village had never synced. The three live ones are `agent_module`, one per grant,
ruled 14 and 15 September. Their reason is the same in each: issued for department
`engineering`, a hardcoded default from before the `--department` flag existed, and no
position in either Pack draws from engineering.

**Should they be superseded instead? No.** Supersession says a replacement exists, and
supersession keys on (agent, forge, module, venture). Measured: no other grant exists on any
of her three triples **for her**. Victor Serath holds `cre-forge/property_lookup` on
greenstone - a different agent, so not a replacement; `simforge/gate_result` is operated by
no Greenstone position at all. Calling these retired would assert a replacement that does not
exist, and would erase the finding that they should never have been issued.

**Does the revocation covering them affect any current Greenstone agent? No.** All three live
revocations are `agent_module` keyed to her `office_agent_id`; `blast_radius` reports
`agents: 1, grants: 1` on each.

### Read-only: what this changes for Burkham's run 8ed2f39a

**Nothing.** Measured: burkham-wickmont holds 49 grants, **all `unknown`, none active, none
retired** - so Gate 7 already passes for it and no predicate added here moves. The run is
blocked at Gate 9, on two refusals that are about certification and not about grants:

    "8 of 98 certification unit(s) are not certified (8 x never_certified)"
    "90 certification(s) read as certified but carry no SimForge PASS"

Four of the 49 are covered by live revocations - entry 75's finding, already closed by
`covered_grants`. Those stay revoked. The four were issued for a department no Burkham
position draws from; that is a statement about authority being wrong, which is what
revocation means and what supersession would have contradicted.

## 116. A certification records the model it was earned on, in columns a constraint can reach

**Ruling by Ivan Green, 17 September 2026.** A certification records the model the agent
passed on: **name, exact digest, temperature and max tokens.** A certification that does
not name the model cannot enforce re-certification when the model changes.

Five of the six sized steps. The sixth - comparing the recorded model against the one an
agent is running - is left for when the Village exposes it, and the reason is below.

### What the label could not say

`agent_model` has been mandatory on an answered SimForge verdict since B34. It carries
`ollama/llama3.1:8b`, and that string is identical whether the tag was re-pulled at a
different quantization or served at a different temperature.

**Measured, and live rather than theoretical:**

    the exam        temperature 0.0, max_tokens 2048. SimForge `EXAM_TEMPERATURE` and
                    `EXAM_MAX_TOKENS`, `agent_runtime/runtime.py:23-24`, passed
                    explicitly so the values `generation_settings` records are the
                    values the call sends.
    production      temperature 0.7, num_predict 200 / 300 / 500 by route. Village
                    `modules/agent_orchestrator.py:1035-1060`.

Every generation setting differs, on every call.

### What is on the row

    model_digest        the exact weights file.
    model_temperature   }  the two settings the ruling names.
    model_max_tokens    }
    model_identity      jsonb, the record as SimForge sent it.
    model_fingerprint   SimForge's hash over the record, indexed where present.

**Five columns and not one jsonb.** The jsonb alone would carry everything and
`certification` would then hold a fact no constraint can reach and no index can find.
The scalars are promoted so a CHECK can demand them; the whole record is kept beside
them so a field nobody anticipated is not lost. `revocation.blast_radius` is the
precedent and the same trade.

`agent_model` stays. Replacing it would rewrite history to look as though it had always
carried a digest.

### The rule is scoped to `certified` and `provisional`, and a FAIL is not asked

B34's constraint keys on the VERDICT and demands the label on every answered one.
`certification_names_its_model` keys on the STATE and demands the model only where an
agent can act - which is the ruling's own wording, *the model the agent PASSED on*.

**A FAIL is deliberately exempt.** It records that an agent was tested and did not pass:
a claim that cannot go stale, so there is nothing to expire. Demanding the digest there
would make an older SimForge's failure **refused rather than recorded**, and the finding
would be gone. `record_result` already reasons this way about the Forge api_version,
whose docstring says a FAIL needs no basis. Losing a pass is safe. Losing a failure is
not.

### The constraint is the control; the guard is the sentence

Both exist and they are not redundant. `record_result` raises a message naming
`file_digest`, `settings.temperature` or `settings.max_tokens` - whichever is missing -
and says why a label is not enough. The CHECK catches everything that does not go
through that function, which is not hypothetical: B34's own suite exists because a
direct INSERT wrote a row nobody could attribute.

**The CHECK is validated rather than `NOT VALID`, and that was measured before it was
written.** `certification` held 26 rows, all `certified`, all with `simforge_verdict IS
NULL` and `agent_model IS NULL` - every one bootstrap-attested. No row in the database
carried a real SimForge verdict at all, so nothing violated it. Had that not been true
the honest move would have been `NOT VALID`; it is worth recording that the strict
version was available because the data allowed it, not because the rule is lenient.

### Which gates read it

    Gate 9    a third refusal, narrower than the two above it: not certified, then
              certified by nobody external, then attested by SimForge and
              unattributable to a model file. Reachable only for a row written before
              0044 - which is the point. The constraint makes it impossible going
              forward and the gate is what catches what is already there.
    Gate 11   will not activate a grant whose unit-A certification carries a verdict and
              no digest. The last thing between a signature and production authority,
              and the same rule at the moment it becomes irreversible.
    Gate 12   reports `model_named` beside `assignable`. A warning gate: "10 of 10
              assignable" says nothing about whether those ten can be expired.
    the call  `resolve_grant` refuses with `CertificationNamesNoModel`, its own type.
      path    `NotCertified` would say the certification is missing or not current,
              which is false and sends the reader to re-run a gate that already passed.
              **This is the one that protects anything** - gates run once per
              provisioning run, calls run all day.

`is_assignable` is deliberately NOT touched. It answers "can `resolve_grant` return this
row", and the call path refuses with its own error, which is a better answer than a
grant silently reading unassignable.

### What is not built, and why it is not a gap that can be closed here

**No `stale_model` state, and no comparison.** Deciding a certification has gone stale
needs the model the agent is running NOW. The Office has no source for it: `village.py`
reads roster, departments, agent state, shifts, deputies and the board, and **no model
configuration at all**. The Village exposes no route that reports an agent's model.

An enum value nothing writes is a control that looks correct in review and does nothing,
which is the specific failure this codebase keeps finding. It goes in with the
comparison that sets it, in one migration, when ruling 2 of the same day is built -
*the Village is the source for an agent's current model identity, and The Office reads
it from the Village's API.*

### Depends on PR #168, which is not merged

`GateResult.model_identity` is #168's field. This branch is cut from it, so **#168 must
merge first**, and #168 itself must merge before SimForge #153 - `validate_response` is
field-set equality and refuses a body carrying a field the manifest does not name, so
SimForge sending `model_identity` early would turn the whole ingest sweep into errors.

Order: #168, then this, then SimForge #153.

### Two collisions found while building it

**The migration is `0044` and so is PR #166's.** Whichever merges second renumbers to
0045. That is the ledger-numbering problem one directory over - and there it is already
solved: two revisions sharing a `down_revision` give alembic two heads and it refuses to
run, by name, on the first command anybody types. Markdown headings had no such check.

**Two worktrees against one test database is a trap.** Building this alongside the
numbering PR left `alembic_version` reading 0043 with both 0044s' columns present, and
the suite reported 444 errors that were nothing to do with either branch. Rebuilding the
schema fixed it. The DSN is in one `.env` and nothing stops two checkouts using it.
## 117. A ledger number is assigned at merge, and a test makes a duplicate unmergeable

**Ruling by Ivan Green, 17 September 2026.** Ledger entry numbers are assigned at merge,
not at authoring. **A PR writes `## NEXT.`; whoever merges assigns the number.** A test
asserts that headings are unique, contiguous, and that no `## NEXT.` reaches main.

This entry was written under its own rule - its heading read `## NEXT.` until the
moment it was merged, and 117 was assigned then.

**The rule was broken on its first use, by the person who made it work.** #173 was
squash-merged with its heading still reading `## NEXT.`, because the merger - me -
assigned no number. Nothing caught it: the test that would have is in this entry's own
PR, which had not landed. Entry 116 is that number, assigned afterwards in a separate
commit. Recorded here rather than tidied away, because it is the honest measure of how
much of this rule is a test and how much is a person remembering.

### What broke, measured on the day the rule was made

    115   main (#165, merged)  A bootstrap grant is retired, not revoked
    115   #163                 One Acquisition Analyst seat
    115   #164                 inherits #163's - it is stacked on that branch
    116   #164                 a 401 from somebody else's nginx
    116   #166                 A venture needs an answer key, and an exam needs a name
    117   #167                 Greenstone's answer keys, drafted
    118   #169                 A certification describes a digest, not a tag
    119   #170                 A certification names the model
    -     #168                 no entry

Three PRs claimed 115 and two claimed 116. **And while this rule was being built, a
second 119 was found** - written in another session, on #169's branch, for the same day's
rulings. Four numbers claimed twice, in one week, in a repository with one author.

### Why git cannot see it

Every entry is appended to the END of `docs/decisions.md`, and two branches appending
different text after different predecessors have no textual overlap. Git merges them
cleanly and main ends up holding two `## 116.` headings. **There is no conflict to
resolve, no warning, and nothing that fails.** The number lives in a markdown heading and
git has no opinion about markdown headings.

That is why the fix is not "be careful". Being careful was already the system.

### Contiguity is the quieter half

A PR claiming 117 while main sits at 115 merges exactly as cleanly as one claiming 115
twice. Nothing is duplicated and nothing is lost - but every later reference to "entry
116" points at nothing, and the gap reads as an entry somebody deleted rather than one
nobody wrote.

Contiguity is also what makes `## NEXT.` cheap: the number to assign is always `max + 1`.
No register to consult, nothing to remember, and no second file to keep in step.

### The four tests, and which one is load-bearing

    unique              two entries with one number. **The one that would have caught
                        every collision above.** It runs against the MERGE RESULT, which
                        is what GitHub checks out for a `pull_request` event, so the
                        second PR to claim a number fails before it lands rather than
                        after.
    contiguous from 1   the gap case above.
    in order            a file holding 1..119 shuffled would satisfy both of the above
                        and still send a reader hunting.
    the placeholder    on main, none survives; off main, an unassigned heading is the
                       last heading. Two arms, no skip - see below.

### The fourth test has two arms and no skip, and the reason is CI's own rule

A PR is **supposed** to carry `## NEXT.` - that is the whole mechanism - so a check that
simply fired on pull requests would fail every PR on the one property it is meant to
have. The obvious fix is to skip it off main. **That was written, and CI rejected it**:
the `tests` job refuses to pass if anything skipped, deliberately, because every
database test is guarded by `requires_db` and a misconfigured Postgres would otherwise
report a tidy green over several hundred tests that never ran. Weakening that rule to
accommodate one test would have cost far more than it bought.

So it is one test with two arms, both asserting something real:

    on main     no placeholder survives. This is the rule.
    off main    a placeholder is expected, so what is checked is that it is used
                correctly - an entry is appended to the end of the file, so an
                unassigned heading is the LAST heading. One left in the middle is a
                botched edit that would otherwise sit there until whoever merged went
                looking for the number to replace.

Which arm runs is decided by `GITHUB_BASE_REF` (set on a pull request, empty on a push),
then `GITHUB_REF`, then git. **Unknown resolves to "not main".** A wrong guess in that
direction is the rule enforced one run later, by the push to main that follows; a wrong
guess the other way is every developer on every branch red for writing the placeholder
the rule tells them to write.

So the window is between a merge and that push-to-main run. **What closes it is a person
- whoever merges assigns the number.** The test catches them forgetting; it is not what
stops them. Said plainly because a test named like this one invites the opposite
reading.

### The open claims, renumbered to `## NEXT.`

Every open PR carrying an entry was converted, not only the three that collided:

    #163  115           -> NEXT
    #164  115, 116      -> NEXT, NEXT   (it is stacked on #163 and carries both)
    #166  116           -> NEXT
    #167  117           -> NEXT
    #170  119           -> NEXT
    #169  118           -> LEFT ALONE, deliberately. See below.

**#167 and #170 held unique numbers and were converted anyway, because contiguity forces
it.** With main at 115, #167 merging first would put 117 beside 115 and leave a gap at
116, and the contiguity test would fail on a PR that had done nothing wrong. Under the
old convention the numbers only worked if the PRs merged in the order they were opened,
and nothing was enforcing that either.

**#169 IS NOT CONVERTED AND MUST BE, BY WHOEVER OWNS IT.** Its branch has uncommitted
work in the shared checkout - a second entry 119, written in another session, recording
the same day's rulings on exam settings and Village-sourced model identity, plus a
correction to entry 118. Rewriting the heading underneath that would hand its author a
conflict in a file they are part-way through editing, which is a worse outcome than the
number being wrong for another hour. Both of its headings need converting before it is
committed: 118, and the 119 that is not yet in a commit.

That second 119 is the sharpest evidence for this rule that exists. Two sessions, one
repository, one afternoon, the same number, neither able to see the other - and the only
reason it was found at all is that both happened to touch the same working tree.

## 118. One session per checkout, and the two ways two sessions corrupted each other

**Ruling by Ivan Green, 17 September 2026.** Only one Claude Code session works in a repo
checkout at a time. **Parallel sessions use separate worktrees and separate test
databases.**

Recorded in `CLAUDE.md` section 3.1 as well as here, because a rule about what to do
before running anything has to be somewhere a session reads before it runs anything.
This entry is the reasoning; that is the instruction.

### The first failure: a branch that changed underneath

A session set out to branch from main, ran `git checkout main && git checkout -b ...`,
and later found itself on `ai-feature/pin-agent-model-ruling` - another session's
branch - **with that session's uncommitted work in the tree.**

The work was a draft entry 119 recording the same day's rulings on exam settings and
Village-sourced model identity, plus a correction to entry 118. It had taken somebody an
afternoon and existed in exactly one place: an unstaged diff.

Nothing in git prevents this and nothing warns about it. Two processes share one
`.git`, and a checkout is global to it. What saved the work was noticing that
`git status` showed a change nobody in that session had made - so the check is cheap and
the failure is silent, which is the worst combination a rule can address and the reason
this one is written down.

**What to do with what you find: leave it.** Not stash, not commit, not check out over
it, and not rewrite a heading in a file somebody is part-way through editing. Say what
you found and work somewhere else.

### The second failure: two worktrees, one test database

Two branches each added a migration numbered `0044`. Applied from two worktrees against
the one test database named in the one `.env`, the result was a schema holding **both**
sets of columns while `alembic_version` read `0043`.

The suite then reported **444 errors belonging to neither branch.** The first instinct
was that the new constraint had broken something; it had not. Both branches were fine.
The database was not.

    measured    alembic_version 0043, curriculum_submission.office_agent_id present,
                certification.model_digest present. Two different 0044s, applied, with
                the version table saying neither had been.
    fix         DROP SCHEMA public CASCADE; CREATE SCHEMA public; alembic upgrade head.
    cost        two full-suite runs and a stretch of debugging the wrong thing.

**So a worktree is not enough on its own.** It isolates the files and shares the
database, and the database is where migrations land. A parallel session needs
`OFFICE_TEST_ADMIN_DSN` and `OFFICE_TEST_APP_DSN` pointed at a database of its own.

**The diagnostic rule, written down because it was learned twice in one day: a suite
that fails for a reason you cannot explain is the database until proven otherwise.**
Rebuild the schema before reading the code.

### What two sessions cannot see about each other, and which of it is caught

    migration numbers   CAUGHT. Two revisions sharing a `down_revision` give alembic two
                        heads and it refuses to run, by name, on the first command
                        anybody types. The 0044 collision cost a rename.
    ledger numbers      NOT CAUGHT, until entry 117. Two branches appending to the end
                        of `docs/decisions.md` have no textual overlap, so git merges
                        them cleanly and main ends up holding two entries with one
                        number. Four were claimed twice in a week, and the second entry
                        119 was found only because both sessions touched one working
                        tree.
    everything else     not caught, and this ruling is the control.

The pattern is worth naming: **the collisions that were caught are the ones where a tool
had an opinion.** Alembic has an opinion about two heads. Git has none about a markdown
heading, and none about which session checked out which branch. Where no tool has an
opinion, the rule has to be a rule, and it has to be somewhere a session reads first.
## 119. A venture needs an answer key, and an exam needs a name on it

**Five rulings by Ivan Green, 17 September 2026.**

1. **Every venture needs an answer key for every module its agents operate**: what the
   agent should do, and when it must stop and get a human. A venture without one cannot
   be certified.
2. **Gate 8 blocks when SimForge accepts zero modules.**
3. **Every exam submission names the agent taking it.**
4. **Answer keys are drafted by Claude and approved by Ivan Green.** A draft is never
   submitted until approved.
5. **Ventures without a Pack** - MedLink Pro, Argus, Collingswood - **get answer keys
   when their Packs are written.**

### What run cb3a47f6 showed, quoted

Advanced past Gate 7 on 17 September. It passed Gate 8 and stopped at Gate 9:

    Gate 8  passed   21 scenario(s) generated; 0 of 5 module(s) accepted by SimForge;
                     0 of 3 department unit(s) opened
    Gate 9  blocked  12 certification(s) read as certified but carry no SimForge PASS.
                     A certification nothing external attested is a certification The
                     Office wrote for itself.

SimForge refused all five modules with the same four violations each:

    scenario[0] (module X, escalation_required):  missing expected_behavior,
                                                  expected_escalation
    scenario[1] (module X, happy_path):           missing expected_behavior,
                                                  expected_escalation
    scenario[2] (module X, permission_denied):    missing expected_behavior,
                                                  expected_escalation
    module X: rubric includes the recovery dimension but has no
              recovery_after_failure scenario, and none was declared not_applicable

**The cause is a missing file, not a bug.** `scenarios/` holds 20 authored YAMLs and not
one is for a Greenstone module - all 20 are CapitalForge or VoiceForge. With no file the
generator emits `expected_behavior=""` and `expected_escalation=""`, and SimForge's
validator treats an empty string as missing (`not s.get(f)`). That is
`modules_with_authored_scenario_content: 0 of 5` stated as a refusal.

### Ruling 2: zero accepted is a block, and an outage is not

The gate passed on everything for its whole life and the reasoning was sound: a rejection
is an answer, the evidence records it, and blocking the ladder on a service that is
allowed to be down would be worse. **That argument covers some modules refused. It does
not cover all of them.** A venture whose every curriculum was refused has no answer key
and the gates above it are being run against a certification story that cannot start.

Two boundaries, both deliberate:

    some refused, some accepted   PASSES. The block is a distinction, not a tripwire.
    SimForge unreachable          PASSES. A service that is down has not refused
                                  anything, and CI runs no SimForge at all.

`violations` is what tells them apart - it exists only on a 422 the validator produced.
The evidence now carries `modules_refused` and `modules_unreachable` separately.

### Ruling 3: how the agent is chosen, and why nobody was ever named

The gate sent `agent_id` only when a module had exactly one certification candidate.
**Measured on greenstone: ten candidates for `assign_contract` and `buyer_match`, none
for `comp_analysis` and `property_lookup`.** Never one. So the field was NULL on every
run ever opened, and SimForge skipped all of them - `battery.py` requires `run.agentId`.

It was also the wrong population. `_certification_candidates` reads
`requires_certification`, which deliberately **excludes** the appointed agent: it is the
pool of people who could fill a seat and hold no certification yet. Not one of the ten
holds a grant.

**The agent is the holder of a live grant for (venture, forge, module)** - the population
Gate 9 reads certification through, and the same one `sweeps._grant_holders` already used
to write the verdict. If the exam named a population the verdict could not be written
for, the ladder would test one set of agents and certify another.

Consequences, each forced rather than chosen:

    one run per holder      SimForge's battery scores `run.agentId` - one agent - so a
                            module two agents hold is two exams. greenstone's
                            `buyer_match` is held by Ronan Valek and Seraphine Valek.
    the ref names the agent `office:{venture}:{forge}:{module}@{agent8}:{hash12}`.
                            Without it both runs mint the SAME ref, `open_run` is
                            idempotent on it, and the second exam lands silently on the
                            first agent's run - one verdict read back as two results.
                            This is the department-collision argument, one unit over.
    0044 adds the column    `curriculum_submission.office_agent_id`. The sweep no longer
                            reconstructs the population; it reads who sat it. Fanning
                            one agent's verdict across every holder would certify people
                            who never took the exam.
    a module with no holder Not submitted at all, and reported as a roster finding.
                            greenstone's `underwrite_deal` is the live case - Deal
                            Underwriter is unfilled. An exam nobody sits owes a verdict
                            nothing can read.

The curriculum still goes over **once** per module - it is the same text for every taker.
The run is what is per agent.

`certification_units_requested` now declares the takers rather than the candidates.
SimForge consumes only `module_id` from that list, which is exactly why it had to be
fixed here: nothing on the far side would ever have complained.

### A test that had been depending on a service being up

`test_pipeline._to_gate_10` drove Gate 8 against whatever SimForge happened to be
listening on the developer's machine. It was green while Gate 8 could not block. The
block made that dependency visible as sixteen failures in gates the helper only passes
through, so it now uses an accepting double. The hand-over keeps its own suites, and
they assert the real verdicts including the block.

---

## 120. One Acquisition Analyst seat, and a mutation that had quietly stopped mutating

**Built 2026-09-16.** The Village now carries exactly one Acquisition Analyst - Victor
Serath, retitled from Trend Analyst 2 and moved to report to the Research Director - so
Greenstone's `headcount: 3` was a guess that would leave V24 failing on two seats no agent
exists for.

**Verified against the running Village before anything was changed**, rather than taken
from the direction: `/api/org/roster` serves `victor_serath` with `title: "Acquisition
Analyst"` and `reports_to_id: dr_brann_lorvik`.

### The artifacts hash moves, and the contrast is the useful part

    provenance `source` (1.9.0)   8b9069657a9531ce -> 8b9069657a9531ce   SAME
    headcount 3 -> 1              8b9069657a9531ce -> fc323b7aa7c29b7a   MOVED

A provenance source is read by V13's evidence basis and by V39, neither of which is
generator output. A headcount reaches `roles`, `appointment` and `runtime_config`. **Two
Pack edits, one visible to a Gate 10 signature and one not**, and nothing about either edit
says which from the outside.

Three golden snapshots moved and each diff was read: `roles` (the number), `appointment`
(two of the three test-world research agents stop being appointed), `runtime_config` (their
four grants go). `approval_projection` did NOT move - Acquisition Analyst is `auto_execute`,
so its headcount has never reached a reviewer.

### The roster sync, and the departure nobody asked about

    Changed manager (1)   Victor Serath   theodore_horven -> dr_brann_lorvik
    Changed title (1)     Victor Serath   Trend Analyst 2 -> Acquisition Analyst
    Gone from the Village (1)   Sable Quint

The title line exists because of entry 114, which found `sync-roster` wrote `title` on every
upsert and never compared it. One agent, two rows - and a third change the direction did not
mention.

**Sable Quint was measured before applying, not after.** It is `village_agent_ref =
'dep-test-stayer'`, a departure-test fixture: no `office_agent_identity`, **0 grants, 0
certifications**. The departure revoked nothing. Worth recording because entry 85 lists
"Sable Quint's grants" among the counts a direction asserted that did not exist; measured
again here, it is still zero.

### A test that passed by not testing

`test_a_publish_that_does_not_match_its_description_is_refused` drifted a Pack by two lines
and declared one, expecting a refusal. It built the drift with

    .replace("headcount: 3", "headcount: 99", 1)

and after this change **no `headcount: 3` remained**. The replace became a no-op, the file
drifted by exactly the one line the publish declared, nothing was refused, and the test went
green.

**The guard was fine. The mutation had stopped working.** That is entry 103's finding in a
second place - *"The mutation would have stopped working, not the rule"* - and it is the
second time in this repository that a text-replace mutation has silently stopped mutating.

It now matches `headcount: \d+` whatever the number, and **asserts the mutation landed
before relying on it**. A test that mutates by text has to prove the text was there.

---

## 121. "My token is not working" was a 401 from somebody else's nginx

**Found and fixed 2026-09-16.** The token was fine. Nothing about it had expired, been
rotated out from under anybody, or been rejected by The Office.

### What was actually happening

    console/lib/api.ts    const API_BASE = process.env.OFFICE_API_URL ?? "http://127.0.0.1:8080"
    port 8080             visonaudioforge-nginx-1, 0.0.0.0:8080->80/tcp

The Office's API was on 9200, because Docker Desktop's backend holds 8080 on this machine
and `dev-all.sh` correctly refused to start there. **Nothing told the console.** It fell
back to its default, reached a container from an unrelated project, and got:

    {"detail":"Missing authentication: provide an Authorization: Bearer <token> header
     or an X-API-Key header"}

which the console surfaces as a rejected session - a bounce back to the login page, which
looks exactly like a bad token.

### This is decisions entry 22's class, and it is the third instance

    the Village, 8002     a VAF container held the port. Its 401 was read as the Village
                          refusing a credential FOR A WEEK (port-allocation.md line 82).
    CapitalForge          an unconfigured bridge 401s from tenantMiddleware instead of
                          404ing as its own .env.example documents. Cost a morning.
    the console, 8080     this one.

**The diagnostic each time is the same: the service's OWN rejection code being absent.**
The Office refuses with its own message; `{"detail":"Missing authentication..."}` is not
it. A 401 says only that something on that port wants credentials - never that yours are
wrong.

### The bug was in `dev-all.sh`, which I wrote two days ago

It started the API on `$API_PORT` and the console with no `OFFICE_API_URL` at all, **then
reported both healthy.** A health script that starts two services on mismatched ports and
calls the result green is worse than no health script: it converts a five-minute
misconfiguration into a hunt for a credential problem that does not exist.

    fixed   the console is started with OFFICE_API_URL="http://127.0.0.1:$API_PORT", and
            the line says which port it was pointed at
    and     a console this script did NOT start is reported DOWN, not OK - it answers,
            and nothing here can read which API it was built against. Calling that
            healthy would be claiming a wiring the script neither did nor can see.

**The second half matters more than the first.** The first time this ran after the fix it
refused the console I had started by hand, which is correct and is the only reason the
mismatch cannot come back silently.

### Also corrected: a token rotated with no audit row

`humans.reissue_token` writes no audit event - the CALLER does, which is why `dev-up.sh`
writes `console_token_reissued` immediately after calling it. I called the function
directly on 16 September, so the account's token changed with nothing in the hash-chained
log to say so.

**That is entry 103's rule broken one function over:** *"hand-run SQL writes no audit
event, so the hash-chained log would hold no record that it happened."* The same is true of
a hand-run function call. The token has been reissued again through
`POST /api/humans/{id}/token`, which writes the event, so the current credential has a
provenance the previous one did not.

## 122. Greenstone's answer keys, drafted - and what the twenty existing ones actually say

Ruling 1 of entry 116: every venture needs an answer key for every module its agents
operate. Greenstone had none. This drafts all five, marks every one **draft**, and
builds the mechanism that keeps a draft out of SimForge's hands.

### The five, and what is in them

`scenarios/{assign_contract,buyer_match,comp_analysis,property_lookup,underwrite_deal}
.yaml`. Each accounts for all seven submittable classes:

    assign_contract   6 authored, 1 declared
    underwrite_deal   6 authored, 1 declared
    buyer_match       5 authored, 2 declared
    comp_analysis     5 authored, 2 declared
    property_lookup   5 authored, 2 declared

Every expected behaviour and escalation cites its source: CRE Forge code by file and
line (`~/projects/medlink-wholesale`), the module's live operating instruction by
section, or **OPEN** - written as a question for Ivan rather than answered. No business
rule is invented.

Eleven OPEN questions were recorded across the five. **All are now answered** - see the
rulings below; what follows describes the file as it was drafted. The one that recurred
on all of them was **who receives a Forge-credential fault?** A 401 is infrastructure - not the venture
operator's to fix and not the analyst's - and neither the manuals nor
`broker/escalation.py` names a recipient. The others are per module, including whether
an agent may widen a comp radius on a human's instruction, whether `underwrite_deal`
should refuse a property with neither asking price nor square footage rather than
return the $300,000 default, and how an agent is meant to satisfy `assign_contract`'s
instruction to check for an existing draft when no module on this Forge lists a deal's
contracts.

### `rate_limited` is declared absent on all five, and it was measured

**CRE Forge cannot return 429 on a module call.** `backend/app/main.py:87` puts a
`Limiter` on `app.state`, `:91` registers the `RateLimitExceeded` handler, and the
limiter carries `default_limits=["100/minute"]`
(`backend/app/middleware/rate_limit.py:28`) - so it reads as a limited application.
**`SlowAPIMiddleware` is never added**: `main.py:94` adds `CORSMiddleware` and nothing
else, and slowapi's default limits apply only through that middleware. The only live
limits are per-route `@limiter.limit` decorators, every one of them in
`backend/app/api/v1/auth.py`. The Office router is mounted at `main.py:303` and
`call_module` (`backend/app/api/forge.py:530`) carries no decorator.

A limiter configured and then not installed looks like a CRE Forge defect rather than a
deliberate exemption. Recorded in all five files as OPEN, not raised.

### `status` is required, and neither default was acceptable

Ruling 4 needs a mechanism, not a convention. `scenario_content` now requires
`status: draft|approved` on every file, with no default - defaulting to `approved`
submits unreviewed prose that SimForge then **grades an agent against**, and defaulting
to `draft` silently stops a venture that is already certifying.

`ScenarioContentSet.for_module` returns `None` for a draft, so a drafted module is in
exactly the position of an unwritten one as far as the generator, Gate 8 and SimForge
are concerned. `drafts()` and a new coverage dimension keep the difference visible:
"nobody has written it" and "somebody wrote it and it is waiting for Ivan" are different
pieces of work. The golden moved by exactly one line - `modules_with_a_draft_answer_key
_awaiting_approval: 5 of 5` - and nothing else, which is the proof that no draft prose
reached the curriculum.

`approved_by` is required on an approved file and refused on a draft. An approval nobody
is answerable for is the shape a rubber stamp has, and a name beside a draft is a
signature on something nobody signed.

### THE TWENTY EXISTING FILES ARE DRAFTS. GRANDFATHERING IS NOT AN APPROVAL EVENT

**Ruled by Ivan Green, 17 September 2026**, refusing the argument this entry first made:

> Burkham's 20 pre-existing answer keys are not approved. Grandfathering is not an
> approval event. They are marked draft until Ivan Green reviews them, and a draft is
> never submitted to SimForge.

The refused argument was that `approved` described the status quo - the twenty had been
submitted on every Gate 8 run since they were written, and marking them draft would stop
a venture that was already certifying. **It was the wrong argument.** It turns "has been
used" into "has been reviewed", which is the exact substitution the approval rule exists
to prevent. A key nobody read is a key nobody read, however long it has been in service.

So all twenty carry `status: draft` and no `approved_by`, and each says at the top that
it was briefly marked approved and why that was refused.

`test_no_key_is_approved_by_grandfathering` pins it. It deliberately does NOT assert
that every key is a draft - that would fail the moment Ivan approves one, which is the
intended next step. It asserts the narrower, permanent thing: an `approved_by` that
describes a process rather than a person is the loophole coming back under another word.

### What it costs, measured rather than estimated

    every answer key in the repository   25, all draft. `for_module` returns content for
                                         NONE of them.
    greenstone                           unchanged - its five were already drafts.
                                         15 operation scenarios, all with empty
                                         `expected_behavior`, which SimForge refuses.
    burkham's 10 live modules            withheld. Gate 8 would submit curricula with
                                         empty required fields, SimForge would refuse
                                         all ten, and entry 119's rule then BLOCKS the
                                         gate on zero accepted.

**Run 8ed2f39a is unaffected, and not because this is harmless: it is already aborted.**
It was blocked at Gate 9 earlier the same day and has since been abandoned. Nothing this
ruling does reaches it.

**No Burkham certification is touched.** All 90 certification rows behind Burkham's
grants are `certified` with `simforge_verdict IS NULL` - every one bootstrap-attested.
Not one was earned from an answer key, so withdrawing the keys withdraws nothing that
was earned. What it removes is the ability to earn any more until Ivan reviews them.

**And Burkham could not run the ladder today regardless.** Its live Pack 0.10.0 fails
generation before Gate 3: *"Intake Concierge: no stage declared for
capitalforge/client_read, capitalforge/client_read_pii, capitalforge/record_consent."*
Confirmed against `main` as well, so it predates this change and is a Pack gap, not a
consequence of the ruling. Recorded so nobody later reads Burkham's silence as this
entry's doing.

### The eight open questions, answered - and Greenstone's five keys approved

**Ruled by Ivan Green, 17 September 2026.** The brief asked eight questions; all eight
are settled. The five Greenstone keys now carry `status: approved` and
`approved_by: "Ivan Green"`. **Burkham's twenty stay drafts** - they have not been
reviewed, and this ruling does not reach them.

    1  credential failure   Goes to the VENTURE OPERATOR as an infrastructure alert -
                            Ivan Green in Phase 1, an on-call rotation later. NOT a deal
                            escalation. Deal work in flight FREEZES at the affected step
                            in a stated `credential unavailable` state. Never a fake
                            success.
    2  the rate limiter     A defect, raised at CRE Forge. Until fixed, rate-limit
                            scenarios stay `not_applicable` with the reason **"pending
                            CRE Forge rate limiter activation"**. When it ships they are
                            authored, noting that a 429 is the one error safely retried
                            on a contract write, because it never landed.
    3  missing square feet  WARN. Underwriting silently returns exactly $300,000
                            otherwise. Missing inputs render as no-data, never a number.
    4  widening comps       A human MAY instruct it. The agent never widens on its own.
                            Every widening records who asked, when, and why.
    5  "no matches"         Cannot be explained today. Raised as a CRE Forge gap: return
                            the filters applied, the pre-filter candidate count, and the
                            per-filter exclusions.
    6  underwriting a       REFUSE a property with no asking price and no square footage.
       property with        No analysis beats a default stored as analysis. The refusal
       neither figure       is visible on the deal.
    7  a failed re-run      Must not leave the old figure reading as current. Raised as a
                            CRE Forge gap: a freshness state on every derived figure.
    8  an existing draft    The agent asks a human to check. Raised as a CRE Forge gap: a
                            list-contracts-by-deal endpoint, plus an idempotency key that
                            actually refuses a duplicate.

**Four of the eight are CRE Forge gaps rather than agent policy** - 2, 5, 7 and 8. That
is the shape worth noticing: half the questions an answer key could not answer were
questions the Forge does not let anybody answer. Each is recorded here as raised, and
each answer key says what the agent does until the gap closes.

### Two standing patterns, ruled in their own right

**NO SILENT DEFAULTS.** A system must not produce a plausible number from a missing or
stale input without labelling it. **Refusing at the source beats catching it
downstream.**

    Rulings 3, 6 and 7 are all instances. So is the $300,000 constant, so is
    `arv_confidence: 0.10`, and so is the 2000-square-foot substitution - three separate
    places on one Forge where an absence became a figure. This is why ruling 6 refuses
    rather than annotates: an annotation is a catch downstream, and the annotation is
    the part that gets dropped in the retelling.

**HUMAN OVERRIDE WITH AUDIT.** Any human authorisation of something agent policy would
block records **actor, timestamp and reason**, and is reviewed by the Compliance Review
Board.

    Ruling 4 is the instance here - a human may lift the no-widening rule, and the
    record is the condition rather than a formality, because a widened comp set is
    indistinguishable from a narrow one once the parameters are gone. The pattern
    generalises past this Forge: it is the shape every override takes, and it is what
    keeps "a human said so" from being unfalsifiable.

Both patterns are broader than CRE Forge and broader than answer keys. They are recorded
as their own rulings so the next module that wants to substitute a default has something
to be refused by, rather than a precedent buried in a scenario file.

### Read-only: the twenty audited

Asked: does each cover all seven classes, does every scenario have expected behaviour
and escalation, does its module have a never-do list, is it marked approved?

    all seven classes           20 of 20. No gaps.
    behaviour and escalation    20 of 20. The loader refuses an empty one
                                (`_REQUIRED_SCENARIO_KEYS`), so this could not be
                                otherwise - which is why it was checked at the file
                                rather than trusted.
    marked approved             0 of 20 before this PR. No file carried any marker.
    never-do list               11 of 20. The other nine have NO LIVE OPERATING
                                INSTRUCTION AT ALL.

**Burkham's live Pack has no gap.** Pack 0.10.0 operates ten capitalforge modules and
every one has an answer key: `client_read`, `client_read_pii`,
`compliance_manifest_assemble`, `portfolio_health`, `record_consent`,
`regulator_dossier_export`, `restack_recommend`, `scan_communication`, `statement_pull`,
`submit_application`. Nothing is missing for Burkham.

**The nine with no instruction are funnelforge**, not Burkham: `capture_contact`,
`distribute_referrer_briefing`, `read_funnel_analytics`, `schedule_blueprint_call`,
`send_brief_cover`, `send_deliverable_cover`, `send_followup_no_engagement`,
`send_intake_acknowledgment`, `send_scheduling_confirmation`. Gate 8 skips a module with
no live instruction before it ever reads the content, so these nine answer keys cannot
be submitted by any venture today. Authored and unreachable.

**Six module names in `packs/burkham-wickmont.split.draft.yaml` have no answer key**:
`assemble_evidence`, `build_packet`, `bureau_pull`, `client_lookup`, `lender_match`,
`readiness_score`. That Pack is not live - burkham-wickmont runs 0.10.0 - so this is a
gap in a draft Pack rather than in a running venture, and ruling 5's shape applies: the
keys follow the Pack.

### A shape difference worth knowing before anybody relies on the held-out classes

CapitalForge's eleven never-do lists are **strings** - one markdown blob each. CRE
Forge's five are **JSON arrays** of five to seven discrete entries. Both are non-empty
and the hand-over copes: `_curriculum_payload` wraps a string in a one-element list
(`broker/provisioning.py:1216-1218`).

But SimForge derives the two held-out classes structurally from the never-do list it
receives (`held_out.py:26-46`). Eleven CapitalForge modules therefore offer it **one**
entry to derive from, and five CRE Forge modules offer five to seven. Measured, not
inferred from the count. Nothing is broken today; it is the kind of difference that
turns into "why did that module get one probe" later.

## 123. The Office refused its own text coming back, and called it an outage

Run bcf44c12 cleared Gate 7 and reported at Gate 8:

    0 of 4 module(s) accepted by SimForge

**SimForge accepted all four.** The refusal was The Office's, reading SimForge's reply:

    submit_curriculum: field 'module_declared_absences.property_lookup.rate_limited'
    carries 1800 characters of prose. Scenario content must never reach The Office; if
    this field is legitimate, narrow it rather than widening the check.

`submit_curriculum` echoes `module_declared_absences` back on acceptance - our own
`not_applicable` reasons - and `assert_no_scenario_content` refuses any echoed string of
200+ characters that reads like prose. The reasons written on 17 September, carrying the
ruling and the measured middleware evidence, ran **1,470 to 1,800 characters**. Nothing
was wrong with the Forge and nothing was wrong with the curriculum.

### Four fixes, and one of them was not in the sizing

**1. The reasons are one sentence, and the argument moved.**

    module             rate_limited            recovery_after_failure
    assign_contract    1729 -> 155
    buyer_match        1470 -> 155             954 -> 171
    comp_analysis      1651 -> 155            1073 -> 177
    property_lookup    1800 -> 155            1251 -> 177
    underwrite_deal    1672 -> 155
    TOTAL              8322 -> 775

The detail is medlink-wholesale#81 - *"Forge surface has no rate limit: the limiter is
configured but never installed as middleware"*, which exists and is open - and this
entry. The wire carries one sentence.

**The `recovery_after_failure` column is the part that was not asked for**, and without
it the fix would not have worked. `assert_no_scenario_content` raises on the FIRST
offending field, so `rate_limited` masked three more over-length reasons behind it.
Shortening only the four named would have moved the error rather than removed it. Found
by writing the test before believing the fix.

**2. A refused response is its own state.** `ResponseRefusedError`, raised by the
response guard and caught separately by Gate 8, reported as `modules_response_refused`
and named in the gate's sentence. It is NOT `modules_unreachable`.

    unreachable     nothing was learned. Restart a service.
    refused         SimForge read the submission and said no. Write scenarios.
    response        SimForge accepted it and the reply broke the manifest coming back.
    refused         Shorten what we send, or narrow the guard. Never widen it.

Three outcomes with three different responses, and folding two of them together sent a
reader to restart a Forge that was answering.

The gate still does not BLOCK on it, for the same reason it does not block on an outage:
SimForge did not refuse the content, so blocking would report scenarios as wrong when
they were accepted.

**3. `OFFICE_OPERATOR_TOKEN` is set, and an unverified build is no longer green.**
`dev-all.sh::api_commit` returns empty without a token, and two of the three paths then
reported `ok "live (build unverified)"`. Both now call `bad`. A build nobody could
identify is not a build that was checked - which is how an API started the previous
evening drove a provisioning run on pre-merge code for an afternoon. The variable is
documented in `.env.example` and points at a dedicated low-privilege account.

**4. Gate 5 corrects `origin` on the row it re-writes.** `ON CONFLICT ... DO UPDATE SET`
gains `origin = 'ladder'`, so Greenstone's six `unknown` grants self-correct the next
time the ladder writes them.

### The audit log cannot settle the six, and that was checked before assuming it

0043 backfilled `bootstrap` from `grant_issued` events carrying `bootstrap: true`, so the
obvious question is whether the same log can identify the ladder's rows.

**It cannot. Measured: the entire audit log holds three `grant_issued` events and all
three are Phase 0.8 bootstraps.** `runtime_config.apply` writes no audit event at all -
`grep -c audit generators/runtime_config.py` returns 0. There is no record of the ladder
issuing anything, so there is nothing to key a backfill on.

That is why the correction is the upsert and not a migration. The ladder is the only
party that knows it wrote a row, and it now says so on every write. A migration would be
inferring it from shape, which 0043 refused to do and this entry does not reopen.

### Left undone, deliberately

Burkham's twenty drafts carry **49 declared reasons over the threshold**. They are
drafts, never submitted, so they are never echoed and cannot be refused today. The debt
comes due at approval, not now, and `test_no_declared_reason_would_be_refused_coming_back`
is scoped to approved keys for exactly that reason: widening it would block Ivan's review
on prose length before he has read a word.

## 124. The split keys arrive, and A2.1 is amended to keep the counts equal

Three pieces, and the third needed a contract amendment nobody had asked for.

### 1. The Village ref travels on run start

`run_start` now sends `village_agent_ref` **beside** `agent_id`, never instead. The two
name one agent to two systems: `agent_id` is The Office's primary key and means nothing
in the Village; `village_agent_ref` is `victor_serath`. SimForge resolves an identity out
of `village.db` (its ADR-0065) and cannot do that from a uuid.

**Where it comes from:** `office_agent_identity.village_agent_ref`, written by
`sync-roster`, which reads the ref before it writes the row.

**What happens when an agent has none: it cannot.** The column is `NOT NULL` - measured,
and **0 of 55 identities lack one** - so there is no branch and none is written. A ref
that no longer RESOLVES is a different thing and is not The Office's to detect: the ref
travels and SimForge reports what it found.

### 2. A module nobody can sit still hands over its curriculum

Gate 8 used to return early when a module had no exam taker, on the argument that *"an
exam nobody sits owes a verdict that can never be read."* **That is sound about the run
and wrong about the curriculum, and the two were collapsed.**

Submitting the curriculum teaches SimForge the module's instruction set, which is what
scenarios BIND to. `underwrite_deal` is the case: SimForge holds no instruction set for
it, so **13 of the 44 drafted split-key scenarios have nothing to bind to** - and would
keep having nothing for as long as Deal Underwriter stays unfilled, because the seat gated
the exam and the exam was gating the hand-over.

So the curriculum goes over regardless; the run stays conditional on a taker. Two
consequences, both deliberate:

    no correlation row   A module with no taker writes no `curriculum_submission` row.
                         The original argument is kept, not abandoned: that table means
                         "a verdict is owed", `overdue_submissions` selects every row
                         whose `result_received_at` is NULL regardless of its ref, and a
                         row for an exam nobody sat would sit in the sweep's queue for
                         ever being reported as `no_grant_holders`.
    handed over is       `handed_over_to_simforge` now means the curriculum landed, not
    about the curriculum that a run opened. `underwrite_deal` hands over completely and
                         opens nothing; calling that a failed hand-over would say
                         SimForge never got a module it now holds.

### 3. The 44 split keys - and the amendment they force

SimForge's `docs/split-keys-draft/` holds five files, **44 scenarios**, every one
carrying `supersedes: the approved N-scenario key, 17 September 2026`. They replace the
five Ivan approved yesterday, and they arrive **unapproved**.

**`expected_answer` is the point of the split.** `expected_behavior` is prose a judge
reads; this is what a machine can check without one. Measured across the 44: `act` 44,
`record_subject` 37, `record_claim` 37, `record_claim_options` 25, `record` 7,
`expected_caveat` 4 - which matches ADR-0082's stated count exactly.

#### The amendment: a class may carry several occasions

`docs/scenario-contract.md` §11 **A2.1** says one row per `(module, class)`. The 44 sit
across **27 pairs** - 17 beyond one each, four `happy_path` occasions on
`underwrite_deal` alone. The loader refused the second of any class, by design.

**A2.1's own stated purpose is that *"the Office's count and SimForge's count [are] the
same count"*.** SimForge moved first. Holding the letter of A2.1 would have kept The
Office at 27 while SimForge graded 44 - the divergence the clause exists to prevent. So
the letter is amended to serve the purpose.

The amendment is narrow. **The key is still `(module, class)` everywhere it decides
anything:** coverage counts classes, `not_applicable` declares classes, and SimForge's
`classify_certification_level` reads a set of classes. Only the number of occasions per
class changes. The scenario id gains an ordinal **only where it has to** - a class with
one occasion keeps `op-<module>-<class>` unchanged, so 27 existing ids and the golden's
ordering are untouched.

**RATIFIED by Ivan Green, 18 September 2026**, in the terms the amendment was proposed
on:

> The purpose is that both sides count the same scenarios; SimForge grades 44, so The
> Office must submit 44. The key stays `(module, class)` everywhere it decides anything;
> only occasions-per-class changes.

So A2.1 now reads for occasions rather than rows, and the clause keeps the job it was
written for. `test_a_class_may_carry_several_occasions` is the enforcement, and it says
in its own docstring which rule it used to assert and why that reversed.

### What changed in the golden

    operation scenarios                              35 -> 15
    rows carrying expected_behavior                  27 -> 0
    new key on every row                             expected_answer
    modules_with_authored_scenario_content          5/5 -> 0/5
    modules_accounting_for_every_submittable_class  5/5 -> 0/5
    modules_with_a_draft_answer_key_awaiting_approval 0/0 -> 5/5

**The drop is the ruling working, not a regression.** All five keys are drafts again -
superseded by keys nobody has read - so `for_module` withholds them and only the
mechanical classes emit. Greenstone goes back to having no approved answer key, and Gate
8 blocks on zero accepted, which is where it should be while 44 unreviewed scenarios sit
in the tree.

**`expected_answer` is emitted on every row and is empty on all 15.** The plumbing is
proved by `test_authored_content_reaches_the_artifact_end_to_end`, which threads two
`happy_path` occasions through and asserts both arrive with their answers. Nothing emits
a real one today because nothing is approved - and an empty mapping contributes no keys
to the wire at all, rather than travelling as a blank.

### What SimForge must accept before any of this lands anywhere

**Nothing The Office now sends will be refused. It will be silently discarded** - which
is worse.

`OperationScenarioSubmission` declares `scenario_class`, `module_id`,
`instruction_section`, `expected_behavior`, `expected_escalation`, `never_do_entry`.
`OperationRunStartRequest` declares `run_ref`, `unit`, `forge_id`,
`instruction_content_hash`, `rubric_kind`, `rubric_version`, `module_id`, `agent_id`,
`department_id`, `scenario_count`, `coverage_denominator`, `window_minutes`.

**Neither carries `extra="forbid"`** - grepped, zero occurrences in the file - so
Pydantic's default applies and an undeclared field is dropped without a word. So until
SimForge adds them:

    village_agent_ref       dropped by run_start
    expected_answer's keys  dropped by submit_curriculum - act, record_subject,
                            record_claim, record_claim_options, record, expected_caveat

This is the reverse of the failure in entry 123. There, The Office refused SimForge's
reply and said so loudly. Here, SimForge would accept everything and quietly keep none of
it, and both sides would report success. **A boundary that refuses is a boundary; one
that ignores is not.** Worth raising on that side independently of these fields: the
manifest The Office validates responses against has no counterpart for requests.

## 125. The names were right and the nesting was wrong

Entry 124 sent `expected_answer`'s keys **flat** - `act`, `record_subject` and the rest as
top-level fields on each scenario - on the guess that SimForge would declare each one
separately. It declares a single `expected_answer` of type `ExpectedAnswer`.

While SimForge ignored undeclared fields that guess was invisible. **ADR-0083 closed the
finding entry 124 raised** - `extra="forbid"` on both payloads, so an undeclared field is
refused rather than dropped - and the first honest answer the boundary gave was a
refusal of everything The Office sends.

    old flat shape   44 of 44 scenario rows REFUSED, on `act`
    nested shape     44 of 44 ACCEPTED

Both measured, by feeding The Office's own rows to SimForge's merged
`OperationScenarioSubmission` in SimForge's venv. No HTTP, nothing submitted.

### The field names were right the whole time

`act`, `record`, `record_subject`, `record_claim`, `record_claim_options`,
`expected_caveat` - six for six, matching `ExpectedAnswer` exactly. Only the nesting was
wrong, which is exactly why nothing caught it: a wrong NAME would have been refused the
moment `extra="forbid"` landed and read as a typo, while a wrong SHAPE with right names
looked correct in review on both sides.

**This is entry 123 from the other direction.** There, The Office refused SimForge's
reply and said so loudly, and the noise is what got it fixed in a day. Here SimForge
accepted a payload it was keeping nothing from, and the silence is what let the guess
survive a merge. A boundary that ignores is not a boundary - which is ADR-0083's title,
arrived at from the other side.

### Absent, never empty

`ExpectedAnswer | None` is declared so that absent means *this scenario has no
machine-checkable half*. So the field is omitted entirely when there is no answer, never
sent as `{}` or `null`. `extra="forbid"` would not have caught that one either: the field
is declared, so a blank object is structurally fine and semantically a lie (entry 122).

### The test

`test_the_answer_arrives_in_simforge_declared_shape` asserts the nesting, asserts each
flat key is ABSENT - because absence is the shape `extra="forbid"` refuses - and pins the
six field names against a transcription of `ExpectedAnswer`, with its source named.
Transcribed rather than imported, for the reason `test_village_seal` exists: a
cross-import is how the separation between the two applications dies.

## 126. Forty-four read, forty-four approved - and the approval carries a date this time

**Ruled by Ivan Green, 18 September 2026:** *"I approve all 44 Greenstone answer keys.
Flip them to approved, approved_by 'Ivan Green', dated 2026-09-18. Burkham's 20 stay
draft."*

So the five Greenstone keys are approved and Burkham's twenty are not. That asymmetry is
the ruling, not an oversight: an approval covers what was read and nothing else.

### The new field, and the round trip that demanded it

`approved_on` joins `approved_by` on every approved key - required on an approved file,
**refused on a draft**, under exactly the same rule as the name.

It is here because of what happened to these five in eight days. They were approved on
**17 September**. SimForge's split keys superseded them the same week, which returned all
five to `draft` (entry 124). They are approved again **today**, over different prose.

**With only a name, those two approvals are the same approval.** A file reading
`status: approved, approved_by: Ivan Green` says nothing about which of the two bodies of
text he read, and the one he read first no longer exists. That is the grandfathering
question from 17 September arriving from the other direction: there, use was mistaken for
review; here, an old review would have been mistaken for a current one. A date is what
distinguishes them, so the date is required.

`fullmatch` on `YYYY-MM-DD`, so `18 September 2026` is refused rather than half-read.
One format, and a date that sorts is a date that can be compared against `revised`.

### What the approval turned on

    dimension                                          before -> after
    modules_with_authored_scenario_content                0/5 -> 5/5
    modules_accounting_for_every_submittable_class        0/5 -> 5/5
    modules_with_a_draft_answer_key_awaiting_approval     5/5 -> 0/0
    operation scenario rows in the curriculum              15 -> 52

**The 52 is 44 authored plus 8 declared absent**, and the distinction matters: 44 is what
SimForge grades, 8 are the `not_applicable` rows that account for the rest of the
submittable classes without asking anyone to answer them.

The 15 before were neither. Counted from the superseded snapshot: **0 carried an answer
and 0 carried a declared reason** - five modules times the three classes the generator
emits mechanically (`happy_path`, `escalation_required`, `permission_denied`), every
field on them empty. That is the whole shape of a withheld draft. `for_module` returns
`None` while a key is drafted, which withholds its declared absences along with its
scenarios, so the curriculum did not merely lack answers: it could not say which classes
Greenstone had deliberately ruled out either.

Per module, measured: `assign_contract` 8, `buyer_match` 8, `comp_analysis` 5,
`property_lookup` 10, `underwrite_deal` 13.

Two dimensions do NOT move, and neither is about the approval:

    scenario_classes_the_office_may_submit   7/9   `never_do_violation` and
                                                   `silent_failure` are held out by
                                                   contract. 7 of 9 is the ceiling.
    roles_with_domain_scenarios              2/3   Deal Underwriter is an unfilled seat,
                                                   which no answer key can fill.

### Gate 8: six exams, and one module that hands over and opens nothing

Measured against the live grant table, not predicted:

    module             scenarios  exams  who sits it
    assign_contract        8        2    Ronan Valek, Seraphine Valek
    buyer_match            8        2    Ronan Valek, Seraphine Valek
    comp_analysis          5        1    Victor Serath
    property_lookup       10        1    Victor Serath
    underwrite_deal       13        0    -- nobody --

All five carry a live operating instruction, so all five hand their curriculum over. Six
runs open, one per taker per module, because SimForge's battery scores `run.agentId` and
a module two agents hold is two exams rather than one exam about two people.

**`underwrite_deal` hands over completely and opens no run.** Deal Underwriter is
unfilled, so nobody holds a grant for it. That is entry 124's correction doing the work it
was built for: its 13 scenarios reach SimForge and bind to an instruction set that was
previously unreachable, and they sit there until somebody fills the seat. A hand-over is
about the curriculum; a run is about a taker.

**Gate 8 stops blocking.** It blocks when SimForge accepts zero modules; five modules
now carry approved content and six runs are owed verdicts.

### What this does not unblock

Gate 9 still waits on SimForge. The verdicts have to come back before any certification
is written, and that path is SimForge's #153. Nothing here changes that, and the six open
exams are what make the wait visible rather than a guess.

### Burkham's twenty, still drafted, still carrying debt

**46** of their declared reasons exceed the prose threshold that
`assert_no_scenario_content` refuses coming back (entry 123). They cannot be refused
today because a draft is never submitted and therefore never echoed.

*Entry 123 recorded 49.* Re-counted here against the same rule, and the files have not
changed since #167 - so 49 was a miscount, not a decrease. The number is 46 under either
reading of the threshold: `>= 200 characters` alone gives 46, and the full
`_looks_like_prose` conjunction gives 46.

`test_no_declared_reason_would_be_refused_coming_back` stays scoped to approved keys for
that reason: widening it would block Ivan's review on prose length before he has read a
word. **The debt comes due at their approval, and this entry is where it was last
counted.**

## NEXT. The gate recorded what it sent, and never what sent it

Twice in two days a provisioning run reached Gate 8 on code older than the checkout,
submitted a superseded curriculum, and reported success. Both took forensics, days and
hours later respectively, and the second proves the first taught nothing - because there
was nothing recorded to learn from.

    17 Sep 17:00:53   run c4edc85a   "41 scenario(s) ... across 4 module(s)"
    18 Sep 15:52:15   run b8ca7dec   "41 scenario(s) ... across 4 module(s)"

The same sentence. The second was recorded **hours after** 44 approved scenarios landed
on main (entry 126). The API was serving from `C:/Users/ivann/Projects/wt-run`, a
worktree detached at `7ac49b9`, which holds the keys those 44 replaced.

**What eventually found it was arithmetic.** `scenario_count` read 7 on every module and
the approved keys carry 8, 8, 5, 10 and 13. A coincidence a reader happens to notice is
not a control.

### Why this gate and no other

Gate 8's output is generated from **files beside the code** - the Pack, the instructions,
`scenarios/*.yaml`. Every other gate reads the database, where a stale process and a
current one see identical rows and disagree about nothing.

So Gate 8 is the one gate that can submit the wrong curriculum and be **truthful about
every number it reports**, because it is reporting truthfully about the wrong tree. It is
also the gate whose output an agent is then certified against.

### What is recorded

`submitting_build`, on every Gate 8 outcome including the refusals:

    commit          what the process is running, read once at import
    checkout_head   what its own tree says HEAD is, read now
    checkout_root   the directory the code was imported from
    scenario_root   where `default_root()` resolved the answer keys
    stamped         the commit came from OFFICE_GIT_COMMIT, not from git
    current         the tree has not moved past the process

**`checkout_root` is the field that would have closed the second incident on sight.**
Nothing else distinguishes a checkout from a worktree of it, and the process reports a
worktree's commit perfectly faithfully. `scenario_root` is recorded beside it rather than
derived from it: the two sharing one anchor is the claim, and printing one while asserting
the other is how a reader ends up trusting a derivation.

### What is refused

`broker/build.py::refusal` decides, and Gate 8 asks it **before the client is built and
before the first submission**. A gate that refuses after sending four modules has not
refused: SimForge would hold a curriculum nobody approved, a `curriculum_submission` row
would be owed a verdict, and the sweep would ingest a result earned on superseded
scenarios.

    not current      the process holds one commit and its tree holds another. This is
                     the 16 September case - a server left running across a merge in its
                     own checkout, answering /api/live with 200 while a route that had
                     just landed 404ed.
    not identified   neither OFFICE_GIT_COMMIT nor a git tree could say. `dev-all.sh`'s
                     rule, not a new one: entry 123 changed that script from reporting
                     `ok "live (build unverified)"` to calling it bad, because "a build
                     nobody could identify is not a build that was checked". A gate that
                     submitted on `unknown` while the shell script refused to call the
                     same process healthy would be two controls disagreeing about a fact.

BLOCKED, not PASSED-with-a-note, and the distinction is the one this gate already draws.
A Forge being down is a fact about the world and the ladder may carry on past it. A
submitter that cannot say what it is running is a fact about **us**, and the run has no
business writing an exam somebody will be certified against.

### What it does NOT catch, said plainly

**The worktree case is not detectable from inside, and pretending otherwise would be
worse than recording it.** A process running `wt-run`'s code faithfully reports
`wt-run`'s commit; `commit` and `checkout_head` agree, because they are the same tree.
Nothing inside that process knows another checkout exists.

So the control is split honestly: the comparison catches the drift case, and
`checkout_root` turns the other one from an investigation into a line. `dev-all.sh` still
owns the external comparison, which is the only place it can live.

### The image had to be stamped for the refusal to be fair

An image carries no `.git`, and **nothing stamped `OFFICE_GIT_COMMIT`** - not the
Dockerfile, not CI, not `deploy.sh`. Measured before the refusal was written: a
containerised process would have reported `unknown` and now been refused for a
configuration nobody had been asked to set.

    Dockerfile        ARG + ENV OFFICE_GIT_COMMIT, empty by default
    ci.yml            build-args OFFICE_GIT_COMMIT=${{ github.sha }}
    compose.yaml      args: OFFICE_GIT_COMMIT: ${OFFICE_GIT_COMMIT:-}
    scripts/deploy.sh exports `git rev-parse HEAD`, and says so when it cannot

**Empty by default, never a placeholder.** An image stamped with a fake commit reports one
that never existed; one honestly unstamped reports that nobody said. The first hides the
defect and the second is the defect, visible.

Smoke is unaffected: `console-smoke.sh` stops the ladder at Gate 4 and never reaches 8.

### `_build_commit` moved, and that is the substance of the app.py diff

It was private to `broker/app.py`, serving `/api/version` alone. The ladder needs the
identical answer and **must not import the API to get it** - a gate importing a FastAPI
app to learn its own commit would make the ladder unrunnable from the CLI, which is how
the sweeps and the smoke script run it. `/api/version` answers exactly as before.
