# PARALLEL_BUILD_ESCALATION_P08.md

**P-08's escalations.** Same three kinds as `PARALLEL_BUILD_ESCALATION.md` — **BLOCKING**
(the package cannot complete the task as written), **RATIFY** (the package took a decision
it was not clearly authorised to take and is declaring it rather than hiding it), or
**RECORDED** (a finding for whoever holds the contract next; nothing is waiting on it).

**Why this is a separate file rather than an append.** Same ruling P-06 and P-12 are
under: several packages branched off the same commit, and three agents appending to one
file is a merge conflict created by the filename rather than by the work.

**Numbering.** The highest entry visible when this was written was **E-008** (P-12), so
this file starts at **E-009**. P-07 and P-09 are running concurrently against the same
range and may have claimed the same numbers; if so, this file is the one to renumber —
nothing outside it references these ids.

**Two of P-08's four names are BLOCKING.** They are the two the card's own compliance flag
predicted: a rename that changes a serialized artifact is a different change from one that
does not, and both of these change one.

---

# P-08 — B23, four names asserting more than the code does

Two names renamed and shipped:

| was | is | why the old one asserted more |
|---|---|---|
| `max_daily_approvals` | `advisory_daily_approval_ceiling` | read as an enforced per-reviewer cap; nothing reads it, and V13 computes from `coverage_hours` and `median_review_minutes` alone |
| `proposal.review_seconds` | `proposal.queue_to_decision_seconds` | measures wall-clock from `created_at` to the decision — queue latency including review effort, not review effort |

Two escalated below.

---

## E-009 — `live` on a Pack cannot be renamed by this package · **BLOCKING**

**The rename is right and the file is on P-08's MUST NOT TOUCH list.** `live` is a
`business_pack.status` value and an accessor of the same name, and both live in
`broker/packs.py` — 22 of the 23 non-doc mentions are in that one file (`store`, `live`,
`get_version`, `publish_draft`, `list_versions`, `list_ventures`, `validation_state`,
`directory`, and the partial unique index's own comment). There is no subset of the rename
that can be done outside it, and a half-applied status value would be worse than the name:
the reads and the writes would disagree about what the column holds.

**It is also not only a rename.** `live` is a stored value in a column with a `CHECK`
constraint and a partial unique index (*one live Pack per venture*). Changing it is a
migration that rewrites existing rows in both real ventures — the same class as
`review_seconds` below, but against data rather than an all-null column, and the `status`
column is what B26/B27/B28 are already about.

**What it should say.** B27 has the finding: `live` is a **publication state** and reads as
a **validation state**. Twelve rows read `live` while `parse_only` refused them, and
`greenstone@1.3.0` is `live` today with a run that cannot start. `published` is the honest
word; the schema already has `draft` and `superseded` beside it, and all three are then
publication states with no verdict smuggled in.

**Blocked on:** whoever owns `broker/packs.py` this run. Nothing in P-08's diff depends on
it, and nothing is half-done — the rename was not started.

---

## E-010 — `produced_not_yet_certified` moves a golden snapshot, so it was not renamed · **BLOCKING**

**This is the case the card's compliance flag names, and it is met the way the flag says to
meet it.** The field is serialized into
`tests/golden/snapshots/greenstone_appointment.json` and into `artifacts_hash`, which
**Gate 4.5 signatures are taken against** — a signature over an artifact whose shape
changed is not a signature over the artifact that was reviewed. `UPDATE_GOLDEN=1` is the
coordinator's call, and `broker/provisioning.py` — which reads the field into the Gate 4
evidence block — is on P-08's MUST NOT TOUCH list independently.

`docs/decisions.md` reached the same conclusion on 7 September and said so: *"Not renamed
here… a rename is a change to an artifact shape that Gate 4.5 signatures are taken
against. Recorded first; the rename is its own change with its own diff to declare."*

**What was delivered instead — T-010, which is what T-010 always was.** The plan lists
T-010 as a *semantics note*, and P-08 carries it:

- `generators/artifacts.py` — the field now carries the docstring saying it counts
  **candidates examined for positions being appointed**, how the two readings were
  separated, and that the rename is escalated rather than forgotten.
- `tests/golden/test_generators.py` — the discriminating experiment is now a test rather
  than a paragraph in a prediction document. An uncertified identity in `marketing`, which
  no Greenstone position draws on, must not move the counter.

### And a second thing, found while reading the call sites

**There are two `produced_not_yet_certified`, and they count different populations.**

- `generators.artifacts.CapacityNumbers` — candidates one appointment run examined and
  refused, per position, for `never_certified` / `in_training` / `missing_unit_b`.
- `GET /api/ventures/{id}/capacity` — every active row in `office_agent_identity` with no
  certified unit-A row, across every department, examined or not.

The endpoint's number is what the name says. The artifact's is not. **They are not required
to agree and routinely will not**, and a reader comparing a console capacity strip against
a Gate 4.5 artifact is comparing two answers to two questions with one name between them.
Both are now documented at their definitions; neither was changed.

**A rename that fixes one and not the other would make this worse, not better** — it would
leave two numbers that no longer look related and are still both consulted for the same
question. Whoever takes E-010 takes both.

---

## E-011 — renaming a Pack schema field invalidates Packs already stored · **RATIFY**

`advisory_daily_approval_ceiling` is a field of `HumanCapacity`, and
`generators.pack.Strict` sets `extra="forbid"`. Every Pack row already in `business_pack`
carries `max_daily_approvals`, so after this merges those rows do not parse — the
B26/B27/B28 failure, arriving from a different direction.

**CI does not see it and neither do the tests.** `scripts/console-smoke.sh` and
`scripts/dev-up.sh` both publish `packs/greenstone.yaml` **from disk** into a fresh
database, and every test world builds its Pack the same way. Nothing in the suite reads a
row written before the rename, which is exactly why this is declared here rather than left
for the deployment that meets it.

**Deliberate, and the remedy is the one this project already used.** Burkham is out of the
B26 state because it was republished as 0.6.0. The same act clears this: republish each
venture's Pack from the file on disk. `packs/greenstone.yaml`,
`packs/burkham-wickmont.draft.yaml` and `packs/burkham-wickmont.split.draft.yaml` are all
updated in this diff, so the sources are correct and only the stored copies are stale.

**The alternative was considered and refused.** Pydantic's `AliasChoices` would let the old
name keep parsing, and it would also let a *new* Pack keep declaring `max_daily_approvals`
— which reintroduces the name the package exists to remove and takes it out from under
`extra="forbid"`, where a typo would then be silently accepted. A compatibility alias for a
name that is wrong is a way of keeping it.

**Ratify or reverse:** if the coordinator would rather the wire field stayed
`max_daily_approvals` and only the Python attribute moved, that is one `Field(alias=...)`
and P-08 will make the change.

---

## E-012 — every package in this run is measuring against the same test database · **RECORDED**

**Not a request. A warning about the measurements, including P-08's first two.**

`OFFICE_TEST_ADMIN_DSN` in `.env` names one database, `theoffice_test`, and seven package
worktrees are pointed at it. P-08's first full run reported **97 failed, 906 passed, 98
errors**; every one of the errors passed when the same test was run alone. Re-running the
suite against a database created for this package alone gave **1051 passed, 0 failed**,
with no code change in between.

**A run of that shape is not evidence of anything**, in either direction — and the
dangerous half is not the false red. Two agents interleaving fixture teardown can also
produce a false *green*, and nothing in the output says which kind of run you got.

There is a second edge with teeth. `tests/deployment/test_probes.py` writes
`EXPECTED_SCHEMA_REVISION` into `alembic_version` as its restore step. Run the suite from a
branch that adds a migration, against a database that has not had it applied, and the
version table is left **stamped at the new revision with the old schema underneath** —
`alembic upgrade head` then reports nothing to do while the column is not there. P-08 hit
this and had to stamp back to `0032` by hand. Any package adding a migration will hit it
the same way.

**What would retire it:** a per-package test database (`theoffice_test_p08`, and so on), or
a `conftest` that refuses to run while another session holds the database. Neither is
P-08's to build.
