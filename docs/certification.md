# Instructions and Certification — Phase 2

Before this, the certification gate was a non-null check on a free-text column. **Any
string satisfied it.** Nothing bound a certification to what the agent was actually
taught, so rewriting a module's instructions left every certification against the old
text silently valid.

Phase 2 makes certification mean something.

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

- **No real SimForge integration.** `SimForgeClient` is a Protocol; the stub exercises
  the contract. Wiring a live instance is a config change, not a rewrite.
- **Staleness recompute is called explicitly**, not on a schedule or a trigger. Nothing
  yet runs it when a Forge's `api_version` changes in the registry — a scheduled sweep
  is needed before this is trustworthy in production.
- **The authoring UI does not exist** (Part 17, console). Authoring is via
  `broker.instructions.author`.
- **Gate 9.5 held-out execution is SimForge's.** The Office's obligation here is only to
  have no read path, and that is what is tested.
- **`scenario_pack_ref` is opaque.** Scenario Pack *generation* is Phase 3 (Generator 5.5).
