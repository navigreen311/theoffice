# Plan — `python -m broker assign-shift`

Decisions entries 80 and 81. **Provisioning grants authority; nothing schedules it.** This is
the smallest thing that does the other job honestly: one named operator, one agent, one
venture, one real window, written through `shifts.assign_shift` and nothing else.

## Problem

`assign_shift` exists, is tested, and enforces its own refusals. Its only callers are
`rotate()`, which nothing calls, and `bootstrap_phase0`, which invents an eight-hour window
because Phase 0 has nobody to ask. A venture that clears the ladder is authorised and not
staffed, and no operator has a way to staff it.

## Users

A human operator of a venture, holding `venture_operator` or stronger for that venture
(`ivan` applies to every venture). Today that means the two real `ivan` accounts; no real
account holds `venture_operator`.

## Shape — the same as `bootstrap-phase0`

    python -m broker assign-shift --venture V --agent REF_OR_ID --operator EMAIL \
        --start now|ISO-8601 --end ISO-8601 [--confirm]

- Reports without `--confirm`, writes with it. Every refusal exits non-zero.
- `apply` re-plans rather than trusting the report it printed.
- The only write is `shifts.assign_shift`. No SQL writes in this module.

## Refusals, all checked before anything is written

| # | Refusal | Why |
|---|---|---|
| 1 | operator unknown, not `origin = 'human'`, inactive, or without `venture_operator`+ for the venture | a shift names who put the agent on duty; a fixture names nobody |
| 2 | agent identity unknown or not `active` | |
| 3 | window naive, `end <= start`, already ended, or starting more than 5 min in the past | a real window; no backdating an on-duty record |
| 4 | **venture has no active grants** (activated and not covered by a live revocation) | a shift there staffs nothing |
| 5 | **agent holds no grant that resolves** for the venture (`grants.resolve_grant`, then `revocation.covered_grants`) | the call path's own answer, not a restatement of it |
| 6 | window overlaps an existing shift for the agent | the schema refuses it anyway; this names it instead of a traceback |
| 7 | previous shift has no verified flush | `assign_shift` refuses it; reported up front |
| 8 | Village quarter unknown, or agent already works another venture that quarter | same |

"Now" is the **database's** `now()`, the clock `assert_on_shift_for` reads, so a shift that
starts now is current at the first call whatever the Python host's clock says.

## Deliberately out of scope

- **The gap (entry 81).** The window ends and nothing follows it. The command says so on
  success rather than pretending otherwise.
- A console action or route. `test_the_api_exposes_no_route_that_bypasses_a_control`
  rejects a write path containing `shift`, and the console is a later decision (C1).
- Manifest declaration, budget, rate limits. Those are call-time checks with their own
  refusals; a shift does not promise a call passes them.
- A window-length cap and any scheduling.

## Alternatives considered for "a named human"

| Option | For | Against |
|---|---|---|
| **`--operator EMAIL` + `humans.authorize` (chosen)** | names the person; checks role *and* venture scope; refuses fixtures | attribution, not authentication: the CLI's trust boundary is the database DSN, the same as every other CLI command |
| `humans.attributable_actor` (bootstrap's) | proven | never names anyone: it picks the oldest `ivan`, and cannot express `venture_operator` |
| bearer token from the environment | real authentication | tokens are shown once and not recoverable; the operator likely has none |

## Tests — `tests/contract/test_assign_shift.py`

Report writes nothing · confirm writes one row + one audit event · **before the command a
call is refused `OffShift`; after it, one brokered call succeeds** · each refusal 1-8 exits
non-zero and writes nothing.
