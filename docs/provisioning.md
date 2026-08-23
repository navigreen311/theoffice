# The Pack store and the provisioning pipeline

Master prompt Part 11 (the gates) and Part 14 (named-human accountability).
Code: `broker/packs.py`, `broker/provisioning.py`, migration `0011_provisioning.py`.
Tests: `tests/provisioning/`.

---

## The Pack store

A Business Pack used to be a YAML file on disk. That is fine for a document a human
edits in an editor and useless for everything else: a Pack Editor cannot edit a file the
server has never seen, a provisioning run cannot record which Pack it provisioned, and a
Gate 10 signature cannot bind to something with no identity.

Two rules, both mirroring the instruction store because they exist for the same reasons.

**One live Pack per venture**, enforced by a partial unique index rather than by
convention. A run has to name exactly one Pack, and "the current Pack" cannot be a
question with two answers.

**`content_hash` is computed in the database**, never accepted from a caller. A supplied
hash is a claim; a computed one is a fact. This is what a Gate 10 signature binds to, so
a caller able to choose it could sign one Pack and provision another.

The YAML source is stored alongside the parsed form. The parsed form is what the
generators read; the source is what a human edits and what the hash is taken over,
because two YAML documents that parse identically but read differently are, to a
reviewer signing one of them, not the same document.

`store()` takes no `venture_id`. It is derived from the Pack, so a caller cannot publish
one venture's Pack under another venture's name.

Superseded versions stay readable. A run records the version it started from, and that
record is worthless if the version disappears the moment somebody edits.

---

## A run is a state machine, not a script

Each gate has a blocking condition. The run stops at the first one that blocks and says
which and why. Gates are neither skippable nor reorderable: Gate 5 issues grants and Gate
2 is the validator, so a run that could jump would issue grants for a Pack nobody
validated.

| Gate | What it checks | Blocks on |
|---|---|---|
| 0 | Bridge operational | any `hard` Forge the bridge does not reach |
| 1 | Pack authored | no live Pack for this venture |
| 2 | Pack Validator | any FAIL, or any NOT_RUN other than V24 |
| 3 | Generators 1–6 | generator error |
| 3.5 | Manifest reconciliation | `REQUIRED_NOT_DECLARED`, hard dependency on a module gap |
| **4** | **Human review** | **waits — `awaiting_human`** |
| 4.5 | Capacity and budget | approvals over capacity, unfilled positions |
| 5 | Sandbox grants issued **inactive** | provisioning failure |
| 6 | KBs seeded, instructions indexed | a module with no instructions |
| 7 | Engagement registered, grants inactive | a grant already active |
| 8 | Curriculum submitted | submission failure |
| 9 | Readiness Gate per role per domain | any grant whose Unit A or Unit B is not certified |
| 9.5 | Held-out adversarial set | the partition does not exist, or a verdict that is not PASS |
| **10** | **Named-human sign-off** | **waits — missing, or voided by artifact change** |
| 11 | Production grants activated | Gate 10 signature absent or void |
| 12 | Live | — |

`advance()` runs from the run's current gate until something stops it. Gate 3 re-runs on
every pass rather than trusting a stored copy of the artifacts — that is what keeps the
signature, the artifacts and the grants describing the same thing.

`abort_run()` abandons a run. A venture may only have one active run, so a run parked at
a signature that is never coming would block the venture permanently. Aborting is **not**
revoking: it deliberately leaves grants alone, because abandoning a run and pulling a
venture's authority are different acts with different authority, and collapsing them
would make the first a silent way to do the second with no revocation record.

---

## Four decisions that carry the design

### A human gate waits. It does not pass.

Gates 4 and 10 return `awaiting_human`, which is neither a pass nor a failure. A pipeline
that auto-advances through a human review gate is a pipeline without human review, and
the tell is that it still *reports* having one.

This is the same distinction as `NOT_RUN` everywhere else in this system, and it reaches
the run status too: `awaiting_human` is a different status from `blocked`, because an
operator told "blocked" goes looking for a defect instead of reading the artifacts.

A Gate 4 review requires a named human scoped to *this* venture and a note. "Reviewed"
with nothing attached is a checkbox; Gate 4 exists so that somebody looked at the bill of
materials and the appointment gap report.

### Grants are issued inactive and activated only against a valid signature

Part 11 Gate 7 says "agents appointed but **grants inactive**"; Gate 11 says "production
grants activated". Before this increment there was no such distinction — a grant written
at Gate 5 was live immediately, so "sandbox provisioning" would have handed agents
production authority six gates early.

So `agent_forge_grant.activated_at` exists and **`is_assignable` requires it**:

```sql
GENERATED ALWAYS AS (
  operation_cert_ref IS NOT NULL
  AND dept_context_cert_ref IS NOT NULL
  AND revoked_at IS NULL
  AND activated_at IS NOT NULL
) STORED
```

The column is not the control. `resolve_grant` checks activation and raises
`GrantNotActivated` — a distinct refusal from `NoGrant`, because an issued-but-unactivated
grant is a venture mid-provisioning, not a missing appointment, and the two need different
responses.

That distinction is worth stating plainly, because the first version of this change was
inert: `is_assignable` was a generated column that nothing read, so adding a term to it
changed exactly nothing at runtime while looking completely correct in review. The tests
assert the consequence — a real call refused — rather than the flag.

### Void is not missing

Gate 10 compares the signature's `artifact_hash` to the artifacts as they are now.
Missing means nobody signed. **Void means somebody signed something else**, and reporting
the second as the first sends the operator to find a signer when what they need to know
is that the document changed after signing.

Nothing has to remember to revoke a signature when a Pack is edited. It voids by
comparison — the same property that makes certification staleness reliable rather than
aspirational.

Gate 11 re-checks this rather than trusting Gate 10's recorded verdict. In an ordinary run
Gate 10 catches a void signature first and Gate 11's check never fires, which is exactly
why it has its own test: a gate that trusts its predecessor can be reached by any path
that sets the predecessor's state, and activation is the moment agents gain production
authority.

### Gate 9 reads the record; Gate 9.5 reads a port

**Gate 9** does not call SimForge. A Readiness Gate verdict reaches The Office by being
recorded as a certification, and the certification is what the call path enforces on
every request — so checking the record asserts the thing that actually gates work, and it
keeps asserting it when a verdict later goes stale, which a point-in-time call could not.
An empty deployment blocks here naturally: no recorded verdicts means every grant reports
`never_certified`, and the gate names the count. Seven states, never collapsed — an agent
nobody trained and an agent whose training no longer describes the module get different
responses.

**Gate 9.5** is the one fact that is not in this database. SimForge owns the held-out
partition outright and The Office has no read path to it by construction (J8). What The
Office is entitled to learn is a verdict — whether, not why — and even that has nowhere
to come from until the partition exists.

So it is a port, `HeldOutSource`, with one method returning one string. The only
implementation shipped is `PartitionAbsent`, which reports that the partition does not
exist. **That is the true state of this deployment, and it blocks every run at 9.5.** When
SimForge Phase 2 stands the partition up, a real implementation replaces it and nothing
else changes.

A verdict that is not `PASS` blocks and is named verbatim. `NOT_RUN` is not a pass and
`TIMEOUT` is not a failure.

---

## Two things this deployment cannot do

Stated here rather than discovered later.

**No venture can reach Gate 12 today.** Gate 9.5 blocks on a partition that does not
exist. That is Gate 0's philosophy applied to certification — no engagement provisions
against a capability that does not exist — and skipping it would produce a venture that
reads as fully provisioned and has been certified for nothing.

**Greenstone's own Pack blocks at Gate 4.5.** The generated workflow routes 192 compliance
approvals a day at six minutes each against one officer's four coverage hours: 1152
review-minutes needed against 144 available. Gate 2's estimate passes and Gate 4.5's does
not, which is not a bug in either — Gate 2 cannot see a workflow that does not exist yet,
which is precisely why the blueprint puts a second capacity check after the generators run.

The validator names three ways out and deliberately does not offer a fourth: raise a
trust-tier ceiling, add reviewer coverage, or reduce scope. **This is a decision for the
venture, not for the pipeline.** The test suite amends the Pack with four more compliance
officers purely so the gates after 4.5 can be exercised; the number it lands on — five
officers — is worth reading as the size of the real problem.

---

## Evidence and audit

Every gate records a reason and non-empty evidence. A verdict with no evidence is an
opinion, and evidence carries denominators: Gate 9 reports units checked, Gate 2 reports
rules checked, Gate 6 reports which knowledge bases exist and which four do not.

Every gate result is written twice, and both are load-bearing. `provisioning_gate_result`
is the run's own record and is what a Provisioning Console reads; it is append-only to
`office_app`, because deleting one would make a gate that blocked indistinguishable from
a gate that never ran. `audit_log` is hash-chained and is what survives someone with
write access to the first table — Gate 11 hands agents production authority, which is
exactly the class of event that must be recorded somewhere the recording process cannot
quietly revise.

---

## Not built

The **Pack Editor** and **Provisioning Console** screens. This increment is their
backend; there are no HTTP routes for either yet, and the console write surface is
unchanged at seven routes.

The **four missing knowledge bases**. Part 6 names five; one is built. Gate 6 reports the
gap in its evidence rather than passing over it.

A real **SimForge**. `HeldOutSource` is where it plugs in.
