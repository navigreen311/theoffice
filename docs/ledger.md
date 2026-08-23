# The Ledger — append-only storage and the audit hash chain

## Why this is load-bearing

Until Forges support per-principal identity, every Forge holds a single tenant key,
so **Forge-side logs attribute every call to the tenant, not to the agent.** The
Office ledger is therefore the *only* per-agent record that exists anywhere.

Reconciliation between the two sides can verify call counts and payload hashes. It
cannot independently corroborate attribution. That is a real gap, stated rather than
papered over — and it is why ledger integrity gets treated as a control rather than
a nice-to-have. If the ledger can be edited, the system has no audit at all.

This closes when Forges gain native per-agent credentials (`credential_mode: native`).

---

## Append-only

Two tables are append-only: `agent_call_ledger` and `audit_log`.

### Layer 1 — role grants (the control)

`office_app` — the role the broker connects as — holds `SELECT` and `INSERT` on both
tables. `UPDATE` and `DELETE` are not revoked after being granted; they are **never
granted**. `TRUNCATE` likewise. `PUBLIC` holds nothing.

Monthly partitions are separate tables and do not inherit privileges, so
`ensure_ledger_partition()` issues the same grants on each partition it creates. A
partition created by hand without those grants would be a silent hole; creating them
through the function is what prevents that.

### Layer 2 — guard triggers (defense in depth)

A `BEFORE UPDATE OR DELETE` trigger on each table raises `insufficient_privilege`.

This does **not** stop a superuser, and is not pretending to. It catches the
realistic failure: someone grants `office_app` too much later, or a migration
connects as the owner and runs an `UPDATE` by mistake.

Layer 1 without layer 2 fails silently on misconfiguration. Layer 2 without layer 1
is a convention, not a control. Both.

### Correcting a bad entry

Append a compensating entry. Never edit history. The guard's `HINT` says so.

---

## The hash chain

Every `audit_log` row carries `prev_hash` and `entry_hash`. Each entry hashes its own
contents *plus* its predecessor's hash, so altering any entry invalidates every entry
after it.

```
entry_hash = sha256( jsonb_build_object(
    audit_id, event_type, actor_type, actor_id,
    venture_id, subject, trace_id, ts_utc, prev_hash )::text )
```

Genesis `prev_hash` is 64 zeros. `prev_hash` and `entry_hash` are both `UNIQUE`, so a
fork or a replay is a constraint violation rather than a corruption.

### Three decisions that each prevent a specific silent failure

**1. `audit_id` is assigned inside the trigger, under the advisory lock — not by a
column `DEFAULT`.**
If the sequence were consumed before the lock, two writers could take ids in one
order and the lock in the other. The chain would then verify link-by-link and still
have entries in the wrong order. Assigning the id under the lock makes chain order
and `audit_id` order the same thing.

**2. The hashed payload is built with `jsonb_build_object`, not string concatenation.**
Delimiter-joined concatenation is forgeable: a field containing the delimiter lets two
different entries produce an identical payload. `test_delimiter_injection_cannot_collide`
exercises exactly that pair.

**3. The timestamp is rendered with an explicit UTC format string.**
`timestamptz::text` renders in the session `TimeZone`. A verifier running in a
different session would recompute different hashes and report false tampering.
`test_hash_is_timezone_independent` checks three zones agree.

### The writer cannot choose its position

The trigger overwrites any caller-supplied `audit_id`, `prev_hash`, or `entry_hash`.

### Concurrency and isolation

Writers serialise on `pg_advisory_xact_lock`. **Audit writes must run at READ
COMMITTED.** Under `REPEATABLE READ` the trigger's snapshot predates a concurrently
committed row, so it would chain onto a stale tip — the lock serialises entry, it does
not refresh the snapshot.

That case is **rejected** by `UNIQUE(prev_hash)`, never silently accepted.
`test_repeatable_read_is_rejected_not_silently_forked` proves the rejection and then
proves the chain survived intact.

---

## Verification

```sql
SELECT * FROM audit_log_verify_chain();
```

| Column | Meaning |
|---|---|
| `ok` | `false` only on a **provable** break |
| `checked_count` | how many entries verified — the denominator |
| `first_break_audit_id` | where it broke |
| `tail_gap` | how far the sequence has advanced beyond `max(audit_id)` |
| `reason` | what happened, in words |

### What it detects

| Attack | Detected by |
|---|---|
| Alter an entry's contents | `entry_hash` recomputation mismatch |
| Alter or remove a predecessor | `prev_hash` link mismatch |
| Delete a mid-chain entry | `audit_id` gap |
| **Delete the newest N entries** | **`tail_gap`** |

### Why `tail_gap` is reported separately from `ok`

Truncating the tail leaves a chain that is internally perfect — every surviving link
joins, every hash recomputes. It is the most dangerous false negative available and
the shape an attacker would choose. The sequence is the only witness.

But a **rolled-back insert also consumes a sequence value.** A nonzero `tail_gap` has
an innocent explanation and a guilty one. Folding it into `ok` would report tampering
on every rolled-back transaction, and a verifier that cries wolf is one people learn
to ignore.

So it is reported as its own number for a human to explain, and `ok` stays reserved
for a provable break. Both cases are tested:
`test_tail_deletion_is_reported_as_tail_gap` and `test_tail_gap_is_advisory_not_a_verdict`.

### `checked_count` is not decoration

A bare `ok = true` cannot distinguish a verified chain from an empty table. Reporting
the denominator is CLAUDE.md invariant 13, and this is the smallest place it applies.

---

## Partitioning

`agent_call_ledger` is `PARTITION BY RANGE (ts_start)`.

**Divergence from blueprint §2, deliberate.** The blueprint declares
`call_id UUID PRIMARY KEY` on a partitioned table. PostgreSQL requires every
partitioning column to appear in a unique constraint, so that DDL will not run. The
primary key here is `(call_id, ts_start)`. `call_id` remains globally unique in
practice; the composite key is a storage-engine requirement, not a semantic change.
**The blueprint should be amended.**

A `DEFAULT` partition exists so a row outside every provisioned range is never
rejected. Losing a ledger row is worse than an untidy partition.

```sql
SELECT ensure_ledger_partition(date_trunc('month', now())::date);
```

Idempotent; safe on every deploy and from a scheduled job. It is `SECURITY DEFINER`
with a pinned `search_path`, so `office_app` gets exactly one privileged capability —
creating an append-only ledger partition — without holding `CREATE` on the schema.
Granting `CREATE` instead would let the runtime role create any object in the schema,
including a table shadowing one the broker reads.

---

## Invariants enforced structurally

These live in the schema because a rule enforced only in application code is a rule
that holds until someone writes a second code path.

| Invariant | Mechanism |
|---|---|
| 1 — ledger is append-only | role grants + guard triggers |
| 2 — audit is tamper-evident | hash chain + `UNIQUE(prev_hash, entry_hash)` |
| 6 — certification gates grants | `is_assignable` generated column |
| 7 — one venture per agent per shift | `no_overlapping_shifts_per_agent` GiST exclusion constraint |
| 8 — flush verified before next assignment | `flush_verified_implies_completed` |
| 14 — two-human break-glass | `break_glass_min_two` |
| V7 — `api_version` pinned | `api_version_pinned` (rejects `'latest'`) |
| Revocation names when/who/why | `revocation_is_complete` |

`is_assignable` is a generated column rather than a predicate each caller writes,
because "assignable" needs one definition in one place. A predicate re-derived at
every call site is a predicate that eventually disagrees with itself.
