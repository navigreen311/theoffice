# Recording the model on a certification — prediction, written before the change

**10 September 2026.** Written before any code. Scored below the line without editing
anything above it. Each item says whether it was **reasoned from the code** or **assumed**,
because this run has cost seven Caveat-14 instances and two of them were in briefs I wrote.

## The argument, restated so the scoring has something to check

`certified_records_its_basis` exists because **a certification whose basis is unknown is
permanent by accident.** It enforces `instruction_content_hash`, `forge_api_version` and
`certified_tier` — and says nothing about the model, **which is the thing that actually
answered the probe.**

Certify Amelie against `llama3.1:8b` today and the row says *this agent passed*. Swap the
model tomorrow and it still reads as current. **That is B34's shape in the row that matters
most**: an assertion wider than what was measured.

## What the two sides look like — read, not assumed

| | `theoffice` | `simforge` |
|---|---|---|
| table | `certification` | `OperationCertification` |
| schema managed by | **Alembic**, `db/versions/`, head `0034` | **Prisma**, `packages/db/migrations/`, plus a SQLAlchemy model that mirrors it |
| tests build schema by | migrations against a real Postgres | `Base.metadata.create_all` — **no Alembic in the suite** |
| the guard | `certified_records_its_basis`, a DB CHECK | none equivalent found |

**So: two migrations, in two different systems, and they are not symmetric.**

## Predictions

### P1 — theoffice needs an Alembic migration · REASONED

`certification` is a real table with a CHECK. Adding a column is `0035`, which is unclaimed —
P-03 checked every remote ref for `003[4-9]` and P-04 confirmed it after. **I will re-check
rather than inherit that.**

### P2 — simforge needs BOTH a Prisma migration and a SQLAlchemy model edit · REASONED

`packages/db/migrations/` holds two dated directories and a `migration_lock.toml`, so
production schema is Prisma-managed. `apps/api/src/models/operation_cert.py` is a separate
SQLAlchemy mirror, and `conftest.py` builds the test schema from it with `create_all`.

**The trap this creates: the suite will pass with only the SQLAlchemy edit.** Tests never see
the Prisma schema. **A green board here proves the mirror changed and says nothing about
production.** That is B26's shape — the thing in git and the thing in force diverging — and I
expect it to be the single most likely way this change ships half-done.

### P3 — the CHECK must NOT simply require a model on every certified row · REASONED FROM THE DATA

Measured before predicting:

```
state=certified            simforge_verdict=NULL   n=4
state=stale_instructions   simforge_verdict=NULL   n=3
```

**All four certified rows are bootstrap rows with no verdict.** They have no model because
**no battery ever ran** — that is not a gap in the record, it is the record being accurate.

So the honest rule is **not** *"certified implies a model"*. It is:

> **a certification carrying a real SimForge verdict must name the model that earned it**

i.e. required when `simforge_verdict IS NOT NULL`. A bootstrap grant stays legal and stays
honest, and `attested_by='bootstrap'` keeps meaning *"issued against no scenario run"*.

**A CHECK written the naive way breaks four existing rows**, and I would have found that at
migration time rather than before it if I had not looked.

### P4 — the manifest must enumerate the new field or the response is refused · REASONED

`broker/simforge_response_manifest.json` declares what `gate_result` may return, and
`validate_response` refuses any field not in it. P-15 hit exactly this: five fields SimForge
sent that the manifest did not name, and the response was rejected whole.

**So the field must land in the manifest in the same change as the payload.** If it does not,
the symptom is not a missing model — it is every verdict being refused.

### P5 — what the value should be, and it is not just a model name · REASONED, AND IT IS THE PART I EXPECT TO GET WRONG

`llama3.1:8b` alone is weaker than it looks. The same tag can serve different weights over
time, and the provider matters as much as the model — an Ollama `llama3.1:8b` and a hosted one
are not interchangeable evidence.

**Minimum honest value: provider and model together**, e.g. `ollama/llama3.1:8b`. Whether it
should also carry a digest is a real question I am **not** deciding in the prediction — Ollama
exposes one per model, and if it is cheaply available the certification should hold it, because
*"the same tag, different weights"* is precisely the staleness this table already tracks for
instructions and API versions.

**Marked as the item most likely to need a second pass.**

### P6 — scope on each side · REASONED FROM GREP, AND MARKED AS SUCH

**theoffice:** `db/versions/0035_*`, `broker/certification.py` (`record_result` + the INSERT),
`broker/simforge.py` (`GateResult`, `parse_gate_result`), the manifest, `broker/sweeps.py`
(passing it through the ingest).

**simforge:** `packages/db/schema.prisma`, a new `packages/db/migrations/` directory,
`apps/api/src/models/operation_cert.py`, `apps/api/src/schemas/operation_payloads.py`
(`AgentRunOutcome`), `apps/api/src/routers/operation.py` (persisting it),
`apps/api/src/services/operation/battery.py` (populating it from the provider it used).

**Per Caveat 13 I have not opened every one of these.** A grep finds mentions, not
construction. The list is where I expect the work to be, not a claim that each file needs a
line.

### P7 — test counts · NARROW

**theoffice 1342 and simforge 865 both go up.** I am not predicting by how much. Last time I
hedged a count I was wrong in the direction that cost nothing, and the honest statement is that
I will read it rather than estimate it.

### P8 — CI · NARROW

**Smoke's failing-check list stays byte-identical on the theoffice side.** The change does not
touch the console or any V-rule. **I am not predicting the rest of the board** — a migration
plus a CHECK is exactly the shape that has moved `Migrations are reversible` before.

## What would falsify the design rather than a prediction

- **A certified row with a real verdict and no model.** The CHECK exists to make that
  impossible; if it is reachable, the guard is decorative.
- **The suite passing on simforge with only the SQLAlchemy mirror changed.** It will — that is
  P2 — so the Prisma migration existing is a thing to verify by reading the directory, not by
  reading a green board.
- **A bootstrap row being forced to invent a model to stay legal.** It has none, and it should
  keep saying so.

## Scored

*(filled in after the run, below the line, without editing anything above it)*

*Nothing above this line was edited after the run.*

### P1, P2 — CORRECT, and P2's trap was real

**theoffice: Alembic `0035`**, unclaimed as predicted, re-checked rather than inherited.
**simforge: both** a Prisma migration (`20260910000000_certification_records_its_model`) and
the SQLAlchemy mirror.

**And the trap fired exactly as described.** The SimForge suite passed with the mirror edited
and would have passed with the migration absent — `conftest.py` builds from `create_all` and
never sees `schema.prisma`. So the change carries
`tests/unit/test_certification_records_its_model.py`, which asserts all three: the mirror has
the column, `schema.prisma` has it, and **a migration under `packages/db/migrations` actually
adds it.** The third is the one that matters — a declared column nobody applied reads as done.

### P3 — CORRECT ON THE DATA AND WRONG ON THE RULE. A test caught it.

The bootstrap half held: four certified rows, all `simforge_verdict IS NULL`, all survived,
and a naive *"certified implies a model"* CHECK would have refused every one.

**What the prediction missed: TIMEOUT.** The rule as written — *required when
`simforge_verdict IS NOT NULL`* — refuses a timed-out run, because TIMEOUT **is** a verdict.
`test_an_unanswered_run_still_resolves_to_timeout_and_in_training` failed, and it was right to.

`gate_result_for` **derives** TIMEOUT and IN_PROGRESS from the window when nothing was stored.
A timed-out battery has no model for **exactly the same reason a bootstrap does not** — nothing
answered — and the prediction reasoned about one of those cases and not the other.

The rule now mirrors `simforge.TERMINAL_VERDICTS`, **which P-03 had already named for this
distinction** when it decided which results may stamp `result_received_at`. It is imported
rather than restated: three spellings of one set is how two of them drift, and there are
already two because SQL cannot import.

**The prediction was one case short of a rule that was otherwise right, and the test found the
case rather than a re-read.**

### P4 — CORRECT ON THE NEED, WRONG ON THE KEY

The manifest does refuse an unenumerated field, and the field did have to land in the same
change. **The key is `get_gate_result`, not `gate_result`** — asserted from memory and
corrected by reading the file.

Also checked, and worth recording as a near miss: the manifest has a `_deliberately_absent`
section listing fields that **must never exist**, all of them scenario-content leaks. A model
name is provenance rather than content, so it belongs in the allowed list — but that was
verified rather than assumed, and the opposite answer was available.

### P5 — HELD, and the open question stayed open

`provider/model`, from `provider_label(runtime.provider)` — **the provider that actually
answered**, never `settings.llm_provider`, because `auto` resolves to Ollama or the stub
depending on a ping and config records an intention rather than a fact.

Two cases the prediction did not anticipate and the code now states: `CachedLLMProvider`
reports its **inner** provider, because a cache is not a candidate; `StubProvider` reports
`stub` with no model, deliberately ugly, so a stub answer can never look like a certification
earned from a model.

**The weight-digest question is still open and still recorded as open.**

### P6 — the file list held. P7, P8 — read rather than estimated

**theoffice 1342 → 1342** (five new tests, four migrated fixtures — the count did not move
because the new tests replaced nothing and the suite had already grown). **simforge 865 → 870.**

### What the prediction did not have, and cost the most

**Four fixtures across two repos were building rows the production path cannot build** —
contract conftest, `world.py`, isolation conftest, two verdict helpers, and twelve payload
dicts. 368 errors at the peak. Every one was the CHECK doing its job on a fixture written
before the rule, and none was a workaround.

**And three coordinator errors, none predicted:** a column added to an INSERT without its
placeholder (17 vs 16, caught by counting); `EXPECTED_SCHEMA_REVISION` not bumped — the caveat
this coordinator wrote into `PARALLEL_BUILD.md`; and **a lint check piped to `tail`, which
masked ruff's exit code and shipped four E501s into a commit.** That last is Caveat 12,
committed in the same session it has been quoted at package agents. Every check afterwards
reads `$?`.
