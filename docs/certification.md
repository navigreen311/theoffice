# Instructions and Certification — Phase 2

Before this, the certification gate was a non-null check on a free-text column. **Any
string satisfied it.** Nothing bound a certification to what the agent was actually
taught, so rewriting a module's instructions left every certification against the old
text silently valid.

Phase 2 makes certification mean something.

---

# ⚠ CAPITALFORGE IS CERTIFIED BY BOOTSTRAP, NOT BY SIMFORGE

**Every CapitalForge certification in the database today was written by a script,
not earned against a scenario run.** They exist for one reason: the bridge could
not be proved to work without a grant, and a grant cannot be issued without a
certification.

They are marked structurally, not by convention: `simforge_verdict IS NULL`, and
`scenario_pack_ref` begins `NO SCENARIO RUN -` followed by why.

**That was not true until 3 September 2026, and the correction matters more than
the constraint.** `record_result` wrote its `verdict` argument straight into
`simforge_verdict`, so a bootstrap had no way to record itself except by claiming
SimForge passed it. Both Phase 0.8 cre-forge rows carried `simforge_verdict =
'PASS'` against no scenario run at all — a false statement in the single column
that exists to say whether SimForge ran, which is the column a reader trusts
most. `attested_by="bootstrap"` now writes NULL there and requires a reason, and
a real verdict is the only thing that can put a value in that column.

**This is at the top of this document rather than in "Known gaps" because a
certification that was asserted looks exactly like one that was earned.** Both
are rows with `verdict = 'PASS'`. Nothing downstream can tell them apart, and the
gate ladder will not stop a call made under one.

## The constraint

**No agent serves a Burkham Wickmont client through CapitalForge until a real
SimForge verdict exists for the module it is calling.**

Not a preference and not a footnote. The whole point of Unit A is that an agent
was tested against the instruction it is about to follow — that is what binds a
certification to a `content_hash`, and it is the reason the gate is not a
non-null check on a free-text column any more. A bootstrap certification restores
exactly the property Phase 2 was built to remove.

## Why it was done anyway

Holding the bridge for SimForge means proving nothing while SimForge is built.
The alternative to a bootstrapped grant was no call at all, and therefore no
evidence that the adapter, the manifest, the credential, the tenant mapping or
the ledger join work — five things that were all untested and are now all proved.

Finding out that the trace header was read under the wrong name is worth more
than a certification record that is honest about being absent.

## What has to happen, and when

**This is the next item after the bridge works, not something to schedule later.**

1. SimForge runs a scenario pack against each bound CapitalForge module.
2. `certification.record_result` writes Unit A and Unit B from those verdicts,
   against the live instruction's real `content_hash`.
3. The bootstrap certifications are superseded — not deleted, so the record shows
   what was relied on and for how long.
4. Only then does a Burkham agent touch a real client.

## How to find them

```sql
SELECT forge_id, unit, module_id, state, scenario_pack_ref
FROM certification
WHERE simforge_verdict IS NULL;
```

Every certification nobody earned, across every Forge. Structural rather than a
naming convention, so it cannot be defeated by choosing a different
`rubric_version`.

**If that query returns a row for a module a Burkham agent is calling against a
real client, the constraint above has been broken.** It returns rows for
cre-forge too — Phase 0.8's own bootstrap, now marked honestly.

---

## Forge Operating Instructions (Part 6.1)

Not documentation. This is the curriculum agents are educated on and the thing SimForge
tests against, and `content_hash` is what binds a certification to a specific text.

**Eight required sections, enforced by a CHECK constraint:**

`what_it_does` · `what_it_does_not_do` · `inputs` · `correct_sequence` ·
`failure_signatures` · `retry_vs_escalate` · `never_do` · `compliance_coupling`

A constraint rather than a convention, because Part 6.1 elevates instructions "from
filing cabinet to curriculum" — and a curriculum missing its failure signatures is a
document that reads fine and teaches nothing about the case that matters. The
application layer rejects the same thing earlier so it can name *which* section is
missing; "violates constraint instruction_has_all_sections" tells an author nothing.

### Two of the eight are routinely written as something else

**Every CapitalForge manual authored so far — seven of seven — needed one or both of
these fixed before it could be authored.** That is not seven authors making seven
mistakes; it is a section title that reads as an invitation to write something
adjacent. Both definitions are here so the next author has them before writing
rather than during mapping.

**`correct_sequence` — the ordered steps an agent takes.** Not context. Not what
comes back. Not what the section is about.

> Six manuals opened this section with "There is none" or "None. One call, one X"
> and then spent a paragraph describing a sequence anyway. The steps were always
> there; they were in the prose underneath. Writing "no required ordering" as a
> one-item list satisfies `validate_sections` by turning a stated absence into a
> step, which is the move these manuals warn about everywhere else.
>
> If the calls genuinely have no ordering between them, say so in the first line and
> then write the ordered steps of what surrounds a call — check the basis before
> reporting, apply shared rule 1 where the read feeds a decision, carry it no
> further than the answer requires. That is a sequence.

**`inputs` — the parameters a caller supplies and what each means.** Not what comes
back.

> Three manuals had a §3 that was WHAT COMES BACK, a channel enum, or a gate ladder.
> Each is worth writing and none is an input. Where a manual has no inputs section,
> the curriculum's `inputs` gets written from route code instead — and then one
> field of that module's curriculum is not derived from its manual, which is the
> exception the whole arrangement cannot afford.
>
> Include what the caller does **not** supply and where it comes from instead. A
> tenant read from the token is an input in the sense that matters: it decides what
> the call can reach, and an agent that thinks it can set one is wrong about the
> module.

Present-but-empty is rejected too. It is the failure a `?` key check misses.

**`content_hash` is computed in the database**, by a BEFORE trigger, from canonical
JSONB. A caller cannot supply a hash that disagrees with its content — a supplied hash
is a claim, a computed one is a fact.

**Exactly one instruction set is live per module**, enforced by a partial unique index.
Two would make "the current content_hash" ambiguous, and staleness is defined by
comparison against it.

Supersede-then-insert happens in one transaction. Between the two statements there is
no live instruction set, and a concurrent staleness recompute would see zero and mark
everything stale.

**Diff is section-level**, not line-level. The question an author and a reviewer
actually ask is "did the never-do list change", and a line diff buries that answer in
reformatting.

---

## Two certification units (Part 10.1)

| Unit | Subject | Measures | Rubric |
|---|---|---|---|
| **A** | agent × forge × module | operation competence | operation |
| **B** | department × forge | judgment in context | domain |

**Both are required for assignment. Department certification is necessary, never
sufficient** — and the reverse holds too: operation competence alone is not enough.

**Two rubrics, never merged.** A CHECK constraint pairs unit to rubric kind, so a
composite score cannot be written at all rather than being discouraged in review.

---

## Seven states, never collapsed

`certified` · `stale_instructions` · `stale_forge` · `in_training` ·
`never_certified` · `failed` · `revoked`

Only `certified` passes the gate. The refusal names **which unit** and **which state**,
because `stale_instructions` (was good, text changed), `failed` (was never good) and
`never_certified` (never attempted) call for three different responses.

**Two verdict mappings matter more than the rest**, and both are the kind of thing a
`verdict == "PASS"` check gets wrong by omission:

| Verdict | State | Why |
|---|---|---|
| `TIMEOUT` | `in_training` | **Never `certified`.** A run that did not finish proved nothing. Treating "we ran out of time" as a pass is how an uncertified agent reaches a Forge. |
| `NOT_RUN` | `never_certified` | **Never `failed`.** Nothing was attempted. Reporting that as failure defames an agent and pollutes the metric meant to show real failures. |

An unknown verdict **raises rather than defaulting**. A default would silently turn an
unrecognised SimForge response into whichever state the default was — and the
safe-looking default (`failed`) is itself wrong for `NOT_RUN`.

---

## Staleness is a comparison, not a flag

A cert stores the instruction `content_hash` and Forge `api_version` it was earned
against. Freshness is computed against what is live now, so **nobody has to remember to
invalidate anything** — the only way this stays true after the sixth Forge is bridged.

A `certified` result must record all three of hash, api_version and certified tier.
Enforced by CHECK: without them staleness is uncomputable and the certification is
permanent by accident.

### Instruction staleness

Live `content_hash` ≠ stored hash → `stale_instructions`, and **the next call fails**.
That is what "removes assignability" means; a flag that changes in a table while calls
keep succeeding is not a control.

### Forge version staleness — `version_sensitivity`

| Sensitivity | 2.1.0 → 2.1.5 | 2.1.0 → 2.2.0 | 2.1.0 → 3.0.0 |
|---|---|---|---|
| `major` | fresh | fresh | **stale** |
| `major.minor` (default) | fresh | **stale** | **stale** |
| `major.minor.patch` | **stale** | **stale** | **stale** |

A **downgrade is stale too**: the certification was earned against behaviour that is no
longer current, and which direction the version moved is not the point.

`major.minor.patch` requires a written `sensitivity_rationale`, enforced by CHECK.
Declaring it decertifies every agent on that module at every patch release — sometimes
right, always expensive, never accidental.

### The three version fields, and which one decides what

A module carries three version-ish values and they answer different questions. Two
of them decertify; the third computes nothing at all.

| field | what it is | decertifies? |
|---|---|---|
| `content_hash` | sha256 of the instruction JSON, computed by a trigger | **Yes.** Any change to any of the eight sections. No dial, no threshold |
| `forge_api_version` + `version_sensitivity` | which Forge release the cert was earned against | **Yes**, at the sensitivity declared — see the table above |
| `instruction_version` | the label on this generation of the text | **No.** Nothing computes on it |

**`version_sensitivity` is about the FORGE's releases, not about edits to the
instruction.** It reads `forge_registry.api_version` — CapitalForge shipping 1.0.1 —
and has nothing to do with a typo fix in the manual. That distinction is easy to
lose, and losing it makes `major.minor` look like a decision about how carelessly
one may edit a curriculum. It is not: **every edit to an instruction decertifies,
whatever the sensitivity**, because the hash moves.

So the argument for `major.minor` is narrow and worth stating in its own terms: a
Forge patch release is not evidence that a module's behaviour changed, and
decertifying every agent on it would be expensive and uninformative. A Forge minor
release might be. That is the whole of it.

### `instruction_version` tracks the manual's version

`instruction_version` is free text — nothing parses it, nothing compares it,
nothing decertifies on it. Because it is mechanically inert, it is free to carry a
convention, and the useful one is this:

**A CapitalForge curriculum's `instruction_version` is the version in its manual's
header.** `record_consent` manual 1.3 is authored as `1.3`. Not a coincidence and
not its own counter.

The alternative — an independent counter, which is what cre-forge, simforge and
voiceforge use, all at `1.0.0` — means one module has two version numbers with no
stated relationship, and no way to tell by looking which generation of the manual a
curriculum was derived from. That is the ambiguity worth avoiding, and it costs
nothing to avoid.

**What this buys is a drift check nobody has to remember.** Manual header vs
`instruction_version` answers *was this curriculum derived from the manual as it now
reads?* If the manual is 1.7 and the curriculum says 1.6, someone edited the manual
and did not re-author. The `content_hash` cannot answer that question — it hashes
the JSON, not the markdown, so it can only tell you the curriculum changed, never
that the manual did.

Two artifacts, one number, and the mismatch is visible in a directory listing.

**Not enforced.** `check_module_manuals.py` already parses each manual's header for
its module id and could compare the version too. It does not yet, so this is a
convention, and a convention is the weaker thing — recorded here so the next author
follows it rather than infers it.

**The older Forges do not follow it.** cre-forge, simforge and voiceforge curricula
are all `1.0.0`, authored before the manuals carried version headers. They are not
retro-fitted: renumbering a live instruction changes nothing mechanically and would
make the audit trail say a text was revised when it was not.

### Settle the manual, then author

The convention above only holds if the authoring happens **after** the manual is
final. Author first and the row claims to derive from a version of the text that
never existed.

That is not hypothetical. `client_read` was authored at v1.6 carrying a corrected
§5, then the manual was corrected and it was re-authored at v1.7. The table now
holds:

```
client_read  v1.6  51e070a3...  superseded
client_read  v1.7  51e070a3...  live
```

**Identical hashes, different versions.** The v1.6 row says it derives from manual
1.6 and its content is manual 1.7's. Nothing reads it — it is superseded — but the
audit trail carries a row whose source claim is wrong.

**It is left in place.** A superseded row with a wrong source claim is a smaller
problem than an audit trail somebody deletes from: the moment a row can be removed
because it is inconvenient, no row in the table means anything. It stays, and this
paragraph is what it is worth.

**The rule: settle the manual, then author.** If a correction is found while
mapping sections onto the eight fields — which is when several have been found —
fix the manual, bump its version, and author once from the settled text.

**A `failed` cert does not become stale.** A cert that was never fresh cannot go out of
date, and collapsing the two erases the difference between "was good, text changed" and
"was never good".

---

## Certified tier caps declared tier — live

Part 10.1: "The Pack declares a ceiling; SimForge sets the actual."

Resolved on **every call** in `resolve_grant`, not once at grant issuance. A cert
downgraded after the grant was written takes effect on the next call, for the same
reason revocation is not cached. By the time the tier gate reads `grant.trust_tier` it
is already capped; the gate must not re-derive it.

---

## THE NO-READ-PATH CHECK

Part 10.1, resolved (J8): **SimForge owns the held-out partition outright.** The
Office's obligation is **negative** — there is no read path to build, only one never to
build.

> "Because Green Companies operates both sides of this boundary, self-attestation is the
> weakest possible enforcement for the one control whose entire purpose is preventing
> one side from seeing the other's content."

Both sides being the same company is exactly why a machine has to check this
continuously. `tests/golden/test_no_read_path.py` is that machine. It needs **no
database and no SimForge instance** — a boundary check that only runs when the far side
is reachable is a check that stops running the moment anything else breaks.

### Three parts, because each alone is defeatable

| Part | Catches | Defeated alone by |
|---|---|---|
| **1. Manifest completeness** — every response field enumerated in `simforge_response_manifest.json` | drift; **this is what fails the build when someone adds a field** | an innocuous name |
| **2. No field may carry scenario content** — names vs. forbidden fragments, values vs. prose shape | an innocuously named leak | a genuinely new, benign-looking field |
| **3. No parameter combination widens the response** — a matrix sweep | smuggling via `include_scenarios`, `expand=*`, `fields=*`, `verbose` | a default response change |

### The check is not vacuous

A boundary test that only ever sees compliant responses proves the *stub* compliant,
not the *check* effective. So the suite includes a deliberately leaky SimForge with
four plausible implementation mistakes, and asserts every one is caught:

1. an honestly named field (`scenario_bodies`)
2. an innocuous name carrying prose (`notes`)
3. burial inside a nested object (`meta.detail.text`)
4. an undeclared but harmless-looking field (`attempt_number`) — the build-failing case

Plus a SimForge that *honours* smuggling parameters, to prove the sweep would catch one
that widens on request rather than passing because the stub ignores everything.

### Guardrails on the guardrail

- **The manifest cannot legalise a leak.** A test asserts no manifested field name
  matches a forbidden fragment. Adding a field to the manifest does not make it
  legitimate.
- **Every deny-list fragment must reject something.** An entry that matches nothing is a
  comment pretending to be a control.
- **Every manifested field must declare a meaningful purpose.** A field documented as
  "string" is a field nobody reviewed. *(This test caught two thin entries on its first
  run.)*
- **Refs, hashes and version strings must not trip the prose heuristic.** A check that
  fires on every hash gets disabled, and a disabled check protects nothing.
- **Fields that must never exist are documented** in `_deliberately_absent`, so absence
  is a decision on the record rather than an oversight — and so "why not just add
  `failed_scenario_ids`" has an answer.

### What The Office is entitled to learn

Whether an agent passed, by how much, against what threshold. **Not why.** A rich enough
explanation of a failure reconstructs the scenario that produced it. `failed_scenario_ids`
narrows the held-out set by elimination; `per_scenario_scores` leaks the set's shape.

**Failure blocks release of both operation certification and Gate 9.5.**

---

## Curriculum submission

`curriculum_submission` records what was handed to SimForge and what came back: refs,
counts, and the instruction hash the curriculum was authored against.

It holds **no scenario bodies**. A table on the Office side recording what was sent is a
table holding scenario content.

`coverage_denominator` is `NOT NULL` — "report the denominator; no green check without a
coverage count."

---

## Run

```bash
.venv/Scripts/python -m pytest tests/golden -q          # the no-read-path check
.venv/Scripts/python -m pytest tests/contract/test_certification.py -q
```

---

## Known gaps

*Last verified: 2026-08-23.*

- **No real SimForge integration.** `SimForgeClient` is a Protocol; the stub exercises
  the contract. Wiring a live instance is a config change, not a rewrite.
- **Staleness recompute runs in the certification sweep**, not on a trigger. A Forge
  whose `api_version` changes mid-cycle is stale from the change and detected at the next
  sweep, which the deployment runs hourly. That window is real and is the reason the
  sweep's freshness is on the compliance dashboard.
- **Certification cannot be re-run from the console.** Instructions can be authored and
  the staleness consequence is shown, but starting a certification run needs SimForge,
  which has no instance.
- **Gate 9.5 held-out execution is SimForge's.** The Office's obligation here is only to
  have no read path, and that is what is tested.
- **`scenario_pack_ref` is opaque.** Scenario Pack *generation* is Phase 3 (Generator 5.5).
