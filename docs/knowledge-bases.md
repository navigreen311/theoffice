# The five knowledge bases

Master prompt Part 6 and Part 17, screen 14.
Code: `broker/knowledge.py`, migration `0012_knowledge_bases.py`, `console/app/knowledge/`.
Tests: `tests/knowledge/`, `tests/contract/test_knowledge_api.py`.

---

## Why this was refused three times

The Knowledge Base Manager was named as unbuildable in three commit messages with the
same sentence: *a screen over nothing is worse than an absent screen, because it implies
the thing exists.* Part 6 names five stores and one was built. So the screen was never
the increment — **the four stores were**, and the Manager is what you get once they
exist.

## Each store gets one control, and the control is why it is a store

A table with a CRUD screen over it is a filing cabinet. Forge Operating Instructions
were *"elevated from filing cabinet to curriculum"* by exactly one property:
`content_hash` binds certification, so republishing decertifies. Each of the four gets
its equivalent.

| KB | The property |
|---|---|
| 6.1 Forge Operating Instructions | `content_hash` binds certification |
| 6.2 Business Playbooks | cross-venture visibility requires a written opt-in |
| 6.3 Compliance Library | six fields, all NOT NULL — and Pack refs resolve against it |
| 6.4 Persona Library | the runtime role cannot read a persona body |
| 6.5 Historical Records | append-only, with a writer on day one |

### 6.2 — sharing is opt-in, structurally

Part 6.2: "cross-venture patterns shareable **by opt-in only**." A playbook belongs to
one venture and becomes visible to another only through a `playbook_share` row naming
both ventures, who consented, and why.

`playbooks_for(conn, venture_id)` resolves the share join inside the query. There is
deliberately **no unscoped read**: a function returning all playbooks and leaving scoping
to the caller would work correctly at every call site except the one that forgot, and
that call site would look exactly like the others.

Revoking keeps the row. Who saw what has to survive the withdrawal, or the record of the
decision does not exist.

Authority is checked against the **owner**, not the recipient. The owner consents to
disclosure; the recipient has nothing to consent to, and checking the recipient's
operator would let a venture help itself.

### 6.3 — structured, and it makes V4 checkable

Six fields, all NOT NULL and non-blank at the table, and checked again in the domain
function so the error names the missing one instead of surfacing a constraint violation
somebody has to decode. An entry with a citation and no **agent-behaviour implication**
is a legal reference nobody can act on; one with no **escalation trigger** says what to
notice and not what to do about it.

The real change is upstream. `library_entry_ref` in a Pack was **self-attestation**: V4
passes whether or not the ref resolves, exactly as a Pack *declaring* a Forge is bridged
proves nothing. **V28** resolves every ref against the library, and one pointing at
nothing is a `[COMPLIANCE LIBRARY GAP]`. That is the same upgrade V2 represents for
Gate 0, and it was unavailable until there was a library to check against.

An explicit `library_gap: true` passes V28. The Pack has said the entry does not exist,
which is the thing V28 would otherwise have to discover — failing it would punish the
Pack that told the truth.

Writing an entry is `compliance_officer`-only, because the library is portfolio-wide: an
entry changes what every Pack resolves and what Gate 6 considers explained, which is not
a per-venture decision.

### 6.4 — a column privilege, not a convention

Part 6.4 is one line: "SimForge only, never production." The production call path runs as
`office_app`, so:

```sql
GRANT INSERT, UPDATE ON persona TO office_app;
GRANT SELECT (persona_id, venture_id, persona_name, target_persona,
              persona_version, body_hash, authored_by, authored_at, superseded_at)
  ON persona TO office_app;   -- persona_body is not in that list
```

`office_app` can author a persona and **cannot read one back**. `SELECT *` fails too. A
read written later by someone who never read this file is a privilege error rather than
a leak — which is the difference between a boundary and a habit.

Four layers, because each catches what the others cannot:

1. the column privilege refuses a read at runtime;
2. a source scan forbids any string literal pairing `SELECT` with the column — proved
   able to fail against a deliberately leaky sample, because a check that has only seen
   compliant source proves the source is compliant;
3. an HTTP test writes a marker body and asserts it comes back from no route;
4. the console smoke script greps every rendered page for it.

**Accepted cost, stated:** the console cannot render a persona body either, because it
runs as the same role. Reviewing one is an out-of-band act on the admin connection. The
authoring form says so before you use it — a form that silently could not show its own
result would read like a defect. That is the price of the boundary being real, and it is
the same trade the held-out partition makes.

### 6.5 — append-only, with a writer on day one

Same two layers as the ledger: `office_app` was never granted UPDATE or DELETE, and a
guard trigger catches the realistic failure where somebody grants too much later.

And it has a writer immediately. Provisioning records `venture_provisioned` on
completion and `provisioning_abandoned` on abort — the second arguably more useful, since
the next person to provision a venture wants to know what stopped the last attempt and at
which gate. Phase 4.1 shipped three controls that were fully tested and completely inert
because nothing ran them; **a store nobody writes to is that mistake with a better name**,
and it would be invisible for exactly as long.

---

## Gate 6 stops lying

Gate 6 used to carry this:

```python
"knowledge_bases_missing": ["business_playbooks", "compliance_library",
                            "persona_library", "historical_records"],
```

Accurate the day it was written, and a lie the day the four were built — it would have
gone on reporting them missing while a venture provisioned against a library it was being
told was absent. A hardcoded list is right exactly once and then rots.

It now counts every store against a denominator drawn from what the venture actually
needs, and **two of the five block**:

| Store | Denominator | Blocks? |
|---|---|---|
| Forge Operating Instructions | modules the positions operate | **yes** — a module with none can never be certified |
| Compliance Library | compliance flags the positions carry | **yes** — the flag reaches the agent as a label, not a constraint |
| Business Playbooks | lifecycle stages the Pack declares | no — advisory |
| Persona Library | target personas the Pack names | no — advisory |
| Historical Records | count | no |

Which ones block is a decision, so it is in the gate's evidence rather than in a doc.
A venture can operate without its SOPs written down; it cannot operate under a compliance
flag nobody has defined. Saying which is which is most of what this gate is for.

---

## The Manager

`/knowledge`. **Coverage, not browsing.** For each of the five: what exists, out of how
many, and what is missing by name. A screen listing forty entries and no denominator
would be a filing cabinet with search — the question an operator has is which store is
thin and where.

`coverageSeverity` in `lib/severity.ts` carries the one refinement this increment adds to
the console's standing rule that anything not verifiably healthy renders as not-healthy:
**a blocking gap and an advisory gap render differently.** Rendering both as the same red
teaches an operator that red here means "eventually", which is how the one that means
"now" gets skipped. A denominator of zero is neutral — the absence of a question is not a
pass. A bare count is never `ok`: twelve entries is not evidence that the one that
matters is among them.

Playbooks are readable only with a venture selected, because that is the only correct way
to read them.

---

## Run it

```
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python scripts/seed_dev_world.py   # includes the two Greenstone entries
```

`seed_dev_world.py` now seeds the Compliance Library, because "a fully prepared world" is
exactly what V28 asks about — without it, Greenstone's Pack fails V28 and Gate 2 blocks.

---

## Known gaps

- **Nothing consumes personas yet.** They are authored and indexed, and the curriculum
  generator does not reference them — SimForge is the consumer and has no instance. The
  store is not inert (Gate 6 counts persona coverage against the Pack's target personas)
  but the hand-off is not built.
- **Playbooks are not read by any agent.** There is no knowledge-retrieval path for
  agents in The Office at all; playbooks are authored, shared and counted, and reach a
  human through this console. Building agent retrieval is where the SimForge-only rule
  for personas stops being cheap to enforce.
- **The Compliance Library is not versioned.** Entries update in place with an
  `updated_at`. Instructions are versioned because certification binds to their hash;
  nothing binds to a compliance entry yet, so versioning would be ceremony. It becomes
  necessary the moment an agent's behaviour is certified against a specific entry text.
- **`library_gap: true` is still self-attested.** V28 takes the Pack's word that the
  entry does not exist. Checking that claim means checking a negative against a library
  that is itself incomplete.
