# Continuous Verification — Phase 4, increment 1

Blueprint Phase 4: "backup/restore drill · monthly reconciliation sweep". Gates 13, 14
and 15. Master prompt Part 13 and Part 15.

## The gap this closes

Three controls shipped fully tested and **completely inert**, because nothing ran them.
The same sentence appears at the end of three phase reports:

| Phase | What shipped | What was missing |
|---|---|---|
| 0.1 | `audit_log_verify_chain()` | "must be run on a schedule or it proves nothing" |
| 2 | `recompute_staleness()` | "nothing runs it when a Forge's `api_version` changes" |
| 1 | manifest reconciliation | runtime only; no periodic sweep |

**A control nobody runs exists in the repository, not in the system.**

Worse than inert — *indistinguishable from healthy*. An absence of incidents looks
identical whether the chain verified this morning or has not been looked at since March.

## Two rules

### A stale pass is not a pass

Every sweep declares a `max_age`. `broker health` reports, per control:
`never_run` · `fresh` · `stale` · `failing`.

**`never_run` and `stale` are not green.** Same rule as the validator's `NOT_RUN`, for
the same reason: an absence of findings from a check that did not run is not evidence,
and reporting it as healthy is how a broken sweep survives for a quarter.

| Control | max age | Source |
|---|---|---|
| `audit_chain` | 1 day | ours — a chain nobody looked at for 29 days is not tamper-evident in any useful sense |
| `certification_staleness` | 1 day | ours |
| `manifest_reconciliation` | 31 days | Part 15, "monthly sweep" |
| `restore_drill` | 92 days | Part 13, "quarterly tested drill" |

### Evidence, not verdicts

Every run records **what it found and how many things it looked at**. "Chain OK" is not
a result. `chain verified over 41,882 entries` is. Same rule as the flush evidence and
the curriculum coverage denominators — and `sweep_run` has a CHECK constraint requiring
a denominator on any finished run.

---

## The four sweeps

### `audit_chain`

Runs the verifier. A break raises **CRITICAL**, not HIGH: until Forges support
per-principal identity this ledger is the only per-agent record anywhere, so a broken
chain means the platform has *no* audit trail rather than a degraded one.

`tail_gap` stays **advisory** here exactly as it is in the verifier. A rolled-back insert
produces one innocently, and a sweep that fails on every rollback is a sweep people learn
to ignore — and an ignored sweep is worse than none, because it looks like coverage.

### `certification_staleness`

Recomputes staleness across every Forge. A newly-stale cert backing a **live grant** is a
HIGH incident: an agent just lost assignability and its next call will fail. A newly-stale
cert backing no grant is bookkeeping.

**Finding staleness is the sweep working, not the sweep failing.** It reports `passed`
with findings. Otherwise every ordinary instruction rewrite would look like an outage.

### `manifest_reconciliation` — Gate 15

Three-way: Declared × Required × In-Use, with In-Use read from `agent_call_ledger`.

Runtime already blocks an `UNDECLARED` call, so anything found here got in *before* the
manifest row was written, or the row was removed afterwards. Either way it needs a human.

**The sweep fails while any finding is undispositioned.** Part 15. An undeclared call
must not be absorbed by time passing.

A disposition requires a named human and a stated reason — enforced by CHECK, so it
cannot be a status flip. Four values:

| Disposition | Meaning |
|---|---|
| `pending` | found, unresolved — **blocks** |
| `declared` | the Pack was wrong; the module belongs |
| `revoked` | the call was wrong; access removed |
| `accepted_risk` | known, tolerated, revisit |

**`accepted_risk` exists deliberately.** Without it the only way to clear a finding
someone has decided to live with is to mislabel it `declared` — and a disposition
vocabulary that forces a lie produces a register nobody trusts.

### `restore_drill` — Gate 13

Part 13 requires a "quarterly tested drill". **A drill that mocks the restore tests the
mock.** This one runs `pg_dump`, creates a scratch database, restores into it, and
asserts `audit_log_verify_chain()` passes **in the restored copy** — the only property
that matters, since a backup that restores a broken chain has restored nothing worth
having. The scratch database is dropped in a `finally`.

If `pg_dump` is unavailable the run is recorded as `error`, **never silently passed**. A
drill that could not run is a drill that did not run.

---

## Run

```bash
python -m broker sweep                  # the three routine sweeps
python -m broker sweep --restore-drill  # plus Gate 13
python -m broker health                 # freshness of every control
```

`health` exits non-zero when any control is `never_run`, `stale` or `failing`, so a
monitor can watch the exit code rather than parse output. Both commands are safe to run
from cron: one advisory lock per sweep kind, and a second runner exits cleanly rather
than double-opening dispositions.

Sample of the state that matters — before anything has ever run:

```
!!  audit_chain: never_run
       {"healthy": false, "max_age_days": 1,
        "detail": "this control has never been verified"}
UNHEALTHY: audit_chain, certification_staleness, manifest_reconciliation, restore_drill.
```

## Verified against the real database

Running the sweeps against this repository's development database immediately found four
undeclared in-use modules — ledger residue from earlier test runs — and Gate 15 correctly
refused to pass while they sat undispositioned. The restore drill dumped 92 KB, restored
into a scratch database, and verified the chain in the copy.

## Known gaps

- **No scheduler ships with this.** The CLI is the entry point; a cron entry or systemd
  timer invokes it. Choosing which is a deployment decision, and Phase 0.6 is still
  blocked on a deployment target.
- **Nothing sweeps shift rotations.** `rotate()` still needs a caller at a real boundary
  (Phase 3.3 gap, still open).
- **Backups themselves are not scheduled** — the drill proves a dump *can* be restored;
  it does not prove one is being taken.
- **No alerting.** Incidents are raised into the table; nothing notifies anyone.
