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

**A Forge address CI can reach.** That is the open item, and this entry is what it
closes.

Concretely: a deployed CapitalForge instance or a container the Smoke job starts, a
reachable `base_url` in the smoke environment's `forge_registry`, a credential CI
can resolve, and enough seeded tenant data for the modules to answer. Entry 1 records
that this is **unscoped work with no owner**, not waiting.

When it exists, V11 and V32 run in CI for the first time and this entry becomes
history. Until then it is the standing explanation for why two rules on `main` have
never been exercised there.

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

**Recorded because a removal with no record comes back next quarter as a mystery.**
Somebody reading the Pack in December will find a Placement Strategist who operates
one module and duties describing three, and this entry is the answer to why.

