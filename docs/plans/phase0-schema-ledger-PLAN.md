# Phase 0.1 — Schema, Append-Only Ledger, Hash Chain — PLAN

**Blueprint deliverable 0.1.** Done when: tables exist · append-only roles enforced · hash chain verified by test.

---

## Mini-PRD

**Problem.** The Office ledger is the *only* per-agent record of Forge activity. Until Forges support per-principal identity, Forge-side logs attribute every call to the tenant. That makes ledger integrity load-bearing in a way it would not otherwise be: if the ledger can be edited, the system has no audit at all.

**Users.** The broker and client library (writers); compliance officers and regulator-export tooling (readers); Ivan (revocation and incident response).

**Success metrics.**
1. Every table in blueprint §2 exists with its constraints.
2. The application role **cannot** `UPDATE` or `DELETE` a ledger row — proven by a test that attempts it and asserts failure.
3. The `audit_log` hash chain verifies end-to-end, and any tampering is detected — proven by a test that mutates a row as superuser and asserts the verifier fails.
4. Concurrent audit writes cannot silently fork the chain.

**Constraints.** PostgreSQL 16 target; local dev is 17 — use no 17-only feature. Alembic migrations, reversible. No secret values in any table — refs only.

**Risks.**
| Risk | Mitigation |
|---|---|
| Hash chain forks under concurrency | Advisory lock serializes writers; `UNIQUE(prev_hash)` makes a fork impossible rather than merely unlikely |
| Sequence assigned out of lock order → chain order ≠ id order | `audit_id` assigned *inside* the trigger, under the lock — not by column default |
| Snapshot isolation hides the latest row from the trigger | Documented as READ COMMITTED-only; stricter isolation is rejected loudly by the unique constraint, never silently corrupted |
| Append-only enforced only by trigger | Enforced primarily by **role grants**; trigger is defense-in-depth for misconfiguration |

---

## Blueprint defect found — must fix, not copy

Blueprint §2 declares:

```sql
CREATE TABLE agent_call_ledger (
  call_id UUID PRIMARY KEY, ...
) PARTITION BY RANGE (ts_start);
```

**This is invalid PostgreSQL.** A unique constraint on a partitioned table must include every partitioning column. As written the migration cannot run.

**Fix:** `PRIMARY KEY (call_id, ts_start)`. `call_id` remains globally unique in practice (UUIDv4) and is the join key; the composite PK is a storage-engine requirement, not a semantic change.

Recorded here rather than silently corrected — the blueprint should be amended.

---

## Architecture

```
db/versions/
  0001_core_schema.py      identity · forge registry · grants · shifts · ledger · audit
  0002_append_only.py      roles, grants/revokes, guard triggers
  0003_hash_chain.py       chain trigger + verification function
```

**Two database roles.**
- `office_app` — `INSERT` + `SELECT` on ledger tables; full DML on operational tables. The role the broker connects as.
- `office_owner` — owns the schema, runs migrations. Not used at runtime.

Append-only is `REVOKE UPDATE, DELETE` from `office_app`, plus a `BEFORE UPDATE OR DELETE` trigger that raises. The grant is the control; the trigger catches misconfiguration.

**Hash chain.**

```
entry_hash = sha256( audit_id ‖ event_type ‖ actor_type ‖ actor_id ‖
                     venture_id ‖ subject::jsonb::text ‖ trace_id ‖ ts ‖ prev_hash )
```

`jsonb` text output is key-sorted and duplicate-free, so it is canonical. Genesis `prev_hash` is 64 zeros. `UNIQUE(prev_hash)` and `UNIQUE(entry_hash)` make a fork or a replay a constraint violation.

`audit_log_verify_chain()` walks the chain in `audit_id` order and returns the first break with its reason, or reports OK with the row count — **the denominator, per CLAUDE.md invariant 13.**

---

## Acceptance tests

| # | Test | Asserts |
|---|---|---|
| A1 | All blueprint tables and columns exist | schema completeness |
| A2 | CHECK constraints reject bad enum values | status, trust_tier, credential_mode, idempotency_support, manifest_match, actor_type |
| A3 | `office_app` INSERT into ledger succeeds | writers work |
| A4 | `office_app` UPDATE ledger row → error | append-only |
| A5 | `office_app` DELETE ledger row → error | append-only |
| A6 | Same for `audit_log` | append-only |
| A7 | Chain verifies over N inserts | continuity |
| A8 | Superuser tampers with a `subject` → verifier reports the exact break | tamper-evident |
| A9 | Superuser deletes a middle row → verifier reports the break | tamper-evident |
| A10 | Forced duplicate `prev_hash` → constraint violation | fork impossible |
| A11 | Grant with NULL cert ref is queryable as non-assignable | invariant 6 |
| A12 | `break_glass_holders` with < 2 entries → rejected | invariant 14 |
| A13 | Ledger partition routing works across a month boundary | partitioning |

---

## Out of scope for this increment

Broker, client library, network policy, Vault integration, identity issuance for the 106 agents. Those are 0.2–0.8 and depend on inputs not yet supplied.
