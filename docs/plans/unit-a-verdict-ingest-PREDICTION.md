# The unit-A verdict return path — prediction, written before the build

**9 September 2026, P-03.** Written before `broker/sweeps.py` is touched, so the result
can be scored against it instead of described after the fact. Nothing above the scoring
line is edited after the build starts.

Measured on `theoffice_test_p03`, a database created for this package alone (Caveat 15),
migrated to head and then **checked by column rather than by stamp** (Caveat 16):
`alembic_version` says `0033`, and `proposal.queue_to_decision_seconds`,
`curriculum_submission.simforge_run_ref`, `curriculum_submission.result_received_at`,
`certification.forge_api_version` and `forge_operating_instruction.content_hash` are all
present in `information_schema.columns`.

---

## What was read before predicting anything

Every claim below was read out of the file named, not inferred from a name (Caveat 14).

**`curriculum_submission` has no `forge_api_version`.** `db/versions/0007_…py:196-210`
creates fourteen columns and none of them is that; no later migration alters the table.
So the value a `certified` row is refused without has to come from
`forge_operating_instruction`, keyed on the hash the submission already stores.

**`content_hash` is not unique per `(forge_id, module_id)`.** The primary key is
`(forge_id, module_id, instruction_version)` and the only other unique index is
`ux_instruction_live … WHERE superseded_at IS NULL`. Two rows with the same content and
different `forge_api_version` are legal, and are exactly what a republish against a
bumped Forge API produces.

**Nothing writes `result_received_at`.** Two hits in the whole repository: the migration
that creates it and `overdue_submissions`' own `WHERE result_received_at IS NULL`.

**`get_gate_result` cannot be called by a sweep.** It is the brokered path —
`OfficeClient.call` resolves a grant for `(agent, simforge, gate_result)`, enforces a
shift, checks a budget and writes a ledger row naming the agent. A sweep has no agent,
and `broker/simforge.py:203-214` refuses in advance the obvious workaround: "Minting one
to satisfy the signature is `origin='human'` again … a name in a ledger row for a call it
did not make."

**But SimForge dispatches `gate_result` from the same map, behind the same check, as the
two calls The Office already makes unbrokered.** `simforge/apps/api/src/routers/office.py`
`MODULES` binds `gate_result`, `submit_curriculum` and `run_start` alike; `call_module`
gates all three on `_require_tenant_credential` and takes `x_office_agent_id` as an
optional header. Read-only inspection of the other repo, which is how the receiving side
is supposed to be checked.

**SimForge answers TIMEOUT itself, and a late verdict beats it.**
`run_registry.gate_result_for` returns `run.verdict` when one exists, and otherwise
computes `TIMEOUT` or `IN_PROGRESS` from the window — "the answer must not depend on how
recently a background job ran". So a run that timed out and then finished answers with
the real verdict on the next read, forever.

**The call path finds a certification by its natural key, not by the grant's pointer.**
`broker/grants.py:120-123` — `LEFT JOIN certification ca ON ca.unit='A' AND
ca.office_agent_id = g.office_agent_id AND ca.forge_id = g.forge_id AND ca.module_id =
g.module_id`. `operation_cert_ref` is only tested for NULL, as an "is this grant issued
at all" check. `_gate_9` in `broker/provisioning.py:1024-1027` joins the *other* way,
on `cert_id::text = g.operation_cert_ref`. **Those two are different questions and this
package answers the first one.**

**Gate 7 requires grants to exist, inactive, before Gate 8 submits anything**
(`broker/provisioning.py:475-498`). So `agent_forge_grant` is a populated table by the
time a verdict comes back, and it is the same population `_gate_9` and `resolve_grant`
will interrogate.

---

## The design, stated so it can be wrong

A fifth sweep kind, `VERDICT_INGEST`, in the unconditional tuple of `run_all`, under
`_sweep_lock`, with its own `MAX_AGE` entry of **one day** and a denominator that counts
submissions **examined**.

Per unresolved submission: poll SimForge for the verdict with the Office's own tenant
credential; fall back to `timeout_gate_result` only when the run cannot be read and the
Office-side deadline has passed; resolve the verdict to a state through
`VERDICT_TO_STATE`; write one `certification` row per agent holding a live grant on that
`(forge_id, module_id)`; stamp `result_received_at` **only on a terminal verdict**.

**Terminal means SimForge stored it**: PASS, PROVISIONAL, FAIL, REVOKED. TIMEOUT,
IN_PROGRESS and NOT_RUN are computed or provisional answers and leave the row eligible.

---

## Predictions

Each is falsifiable, and each is scored below without editing anything above this line.

### P1 — the fifth sweep kind cannot be inserted without a migration

**`sweep_run.sweep_kind` is a CHECK constraint over four literals**, so `_start` will
raise a check violation on the first insert of `verdict_ingest`. `db/versions/*` and
`broker/app.py::EXPECTED_SCHEMA_REVISION` are both outside this package's MAY MODIFY
list. **Predicted: this blocks, and is escalated rather than worked around.** I predict
the constraint is real and not merely documented, and that no other branch has claimed
revision `0034`.

### P2 — the guard refuses, and refuses for the reason claimed

A PASS verdict whose submission's `instruction_content_hash` matches no
`forge_operating_instruction` row will raise `CertificationError` from `record_result`,
**not** write a row with a placeholder api version. Predicted message mentions the
instruction hash, the Forge api_version and the certified tier, and the
`certified_records_its_basis` CHECK is never reached because the Python guard fires
first. I predict **zero** `certification` rows exist for that agent afterwards.

### P3 — the ambiguity is real in the database, not just in the DDL

Two `forge_operating_instruction` rows for one `(forge_id, module_id)` with the same
`content_hash`, different `instruction_version` and different `forge_api_version` will
**insert without error**. A lookup by hash alone returns two rows. Predicted resolution:
pick the row in force at `submitted_at`, and I predict that rule is **not** a tie-break
invented for this sweep — it reconstructs the value Gate 8 actually put on the wire,
because `_curriculum_payload` sends `instruction.forge_api_version` off the live
instruction at submit time.

### P4 — a withheld verdict never reaches `certified`

`PROVISIONAL` resolves to state `provisional` and `certified_tier` stays NULL even when
SimForge sends one. I predict the row is accepted with hash and api_version and **no**
tier, because `record_result`'s provisional branch deliberately does not require one.

### P5 — the timeout path survives, and a late verdict beats it

A submission past the deadline whose run cannot be read resolves TIMEOUT → `in_training`
and **`result_received_at` stays NULL**. When the same run later answers PASS, the next
sweep re-examines it, upserts the same row to `certified`, and only then stamps.
I predict the certification row count is **1**, not 2 — the ON CONFLICT key is
`(office_agent_id, forge_id, module_id)`.

### P6 — idempotence is visible in the denominator, not only in the row count

Two consecutive sweeps over one terminal submission: the first reports
`examined=1, ingested=1`; the second reports **`examined=0`**, because the stamp removed
the row from the candidate set. A design that re-wrote an identical row would report
`examined=1` twice and would be idempotent in effect while lying about coverage.

### P7 — the advisory lock serialises, and the loser does nothing

Two concurrent `run_all`-shaped invocations on two connections: exactly one acquires
`pg_try_advisory_lock(hashtext('sweep:verdict_ingest'))`, exactly one `sweep_run` row is
written, and the loser writes nothing at all — not a `sweep_run` row with zero findings.

### P8 — test count and CI

The suite gains **8 to 12** tests. `Tests` is green on the PR; Smoke is red with the
ten-line failing-check list **byte-identical** to the baseline in `PARALLEL_BUILD.md`;
the other five jobs are green. I predict **no** change to the Smoke list, because nothing
here touches a validator rule, a Pack or a console template.

### P9 — the thing I expect to be wrong

I predict at least one of P1–P8 is wrong, and my guess at which is **P8's count** — the
guard and ambiguity cases each want more than one test and I have under-counted before.

---
<!-- ============ SCORING LINE — nothing above is edited after this point ============ -->

## Scored after the build

**Nothing above the line was edited.** Measured on `theoffice_test_p03`, migrated to
`0034` and verified by column. **1227 passed, 0 failed**, run serially with no other
agent working; ruff clean, `mypy --strict` clean over `broker client generators`;
migrations round-tripped up/down/up/down/up to `0034 (head)`.

| # | claim | verdict |
|---|---|---|
| P1 | a fifth sweep kind needs a migration | **right, and incomplete** |
| P2 | the guard refuses an unrecoverable basis | **right** |
| P3 | the hash ambiguity is real in the database | **right** |
| P4 | a withheld verdict never reaches `certified` | **right in the half that matters, wrong in the detail** |
| P5 | the timeout path survives and a late verdict beats it | **right** |
| P6 | idempotence is visible in the denominator | **right** |
| P7 | the lock serialises and the loser does nothing | **right, and the first version of the test could not have shown it** |
| P8 | 8–12 new tests, CI unchanged apart from `Tests` | **wrong on the count** |
| P9 | at least one of P1–P8 is wrong, probably P8's count | **right** |

### P1 — right about the constraint, wrong about how much was outside the list

`sweep_run_sweep_kind_check` is a real CHECK over four literals, confirmed by reading
`pg_constraint` on the live database and not only the migration. No branch anywhere
claimed `0034` — every remote ref was enumerated and `git ls-tree db/versions/` grepped
for `003[4-9]`, which returned nothing. So `0034` and the `EXPECTED_SCHEMA_REVISION`
bump were written, and both are declared in the PR as outside MAY MODIFY.

**What the prediction missed: `broker/app.py` needed two more edits, and four existing
tests found them, not I.** `CONTROL_COPY` and `RUNNABLE_FROM_THE_API` enumerate the
controls for the compliance page, and `test_every_metric_carries_a_real_denominator`
compares that map's size against `len(MAX_AGE)`. Adding a control without its copy fails
four tests in `test_compliance_api.py` — which is the assertion doing exactly its job,
and is why the P-00 rule about rule-count assertions exists. I predicted one file outside
the list and there were three.

### P4 — the half that matters held; the detail did not

PROVISIONAL resolves to `provisional` and never to `certified`: right, and it is the
claim worth having. **The prediction that `certified_tier` stays NULL "even when SimForge
sends one" is wrong.** The sweep passes through what SimForge sent, and the row carries
`certified_tier = 'suggest'`.

On reflection the behaviour is right and the prediction was the mistake. `record_result`
declines to *require* a tier on a hold — "demanding one here would invite a placeholder
that a later reader takes for a real cap" — which is not the same as discarding one that
was measured. The value is inert: `cap_tier` is reachable only through `resolve_grant`,
which refuses any state but `certified` several checks earlier. The test now asserts the
tier explicitly, so the behaviour is pinned rather than incidental.

### P7 — right, and the first test could not have shown it

The first version used two checkouts from the shared pool. It passed, and on a later run
reported `[True, True]`. **A PostgreSQL advisory lock is held by a session and is
re-entrant within it**, so two contenders that happen to share a connection both acquire
it and the assertion proves nothing — a green that means the opposite of what it reads.

Rewritten onto two dedicated connections, with an `asyncio.Barrier` so both contend at
once and an assertion that the backend PIDs differ, so the setup cannot silently degrade
to one session again. Stable over five consecutive runs.

**This is the run's own lesson arriving in miniature:** the first result was a
measurement of the harness, not of the lock.

### P8 — wrong on the count, and predictably so

**17 new tests, not 8–12.** The guard wanted two (a refusal, and a FAIL that legitimately
needs no basis), the ambiguity wanted both directions in one test, and the wire wanted
three of its own — the signing, the leak check that shows the control was not widened,
and the 404 that must not become a NOT_RUN. Collected count moves 1210 → 1227, and the
PR says so.

CI is unjudged here on purpose. Predicting it is Caveat 12; the PR run is the
measurement, and the Smoke ten-line list is diffed against the `PARALLEL_BUILD.md`
baseline after it runs rather than before.

### What I would tell the next package

**Read the receiving side before designing the caller, not after.** Three of this
package's four corrections — the brokered read, the missing api_version column, the two
different certification joins — were each one file away, and all three would have been
built wrong and passed their own tests. The fourth, `attested_by` being a parameter and
not a column, would have produced a query that silently returned nothing forever.
