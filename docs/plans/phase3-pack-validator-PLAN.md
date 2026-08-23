# Phase 3, increment 1 — Business Pack and the Validator — PLAN

**Blueprint Phase 3**, first increment: hand-author the Greenstone Pack, and build the
Pack Validator. Gates 1 and 2 of the provisioning pipeline.

The seven generators (increment 2) and shift assignment with PHI flush (increment 3)
follow. Each ends in a testable, committable state.

**`ASSUMPTION` — first venture is Greenstone**, per blueprint Phase 3. Not asked, so
taken as specified. Consequence worth stating plainly: Greenstone's operating Forge is
**CRE Forge**, and the bridge is going to CapitalForge first (your decision, superseding
J4). **Validator rule V2 enforces Gate 0 — no engagement provisions against a Forge the
bridge does not reach — so the Greenstone Pack will FAIL V2 in production until CRE
Forge is bridged.** That is the validator working, not a defect. To change: say
"Burkham first" and the same machinery runs against CapitalForge.

---

## Mini-PRD

**Problem.** The Office has a call path, governance gates and certification, but no way
to describe a venture. Every manifest row, grant and instruction so far has been
hand-inserted by a test fixture. There is no artifact a human authors and no gate that
refuses a bad one.

**Users.** Whoever authors a Pack (Ivan, venture operators); the generators, which
consume it; Gate 4 human review.

**Success metrics.**
1. The Greenstone Pack loads, and every schema-v3 field round-trips.
2. All 27 validator rules are implemented, and **each FAIL rule has both a must-fail
   and a must-pass fixture** (blueprint §5 test strategy — a rule with only a must-pass
   fixture is a rule nobody has seen fire).
3. A Pack with any FAIL does not pass. WARN does not block.
4. V2 (Gate 0) actually reads the bridge state rather than trusting a declaration.

---

## Design decisions

### Pydantic for shape, the Validator for meaning

The Pack is a YAML document. Pydantic models handle *shape* — required fields, types,
enums — and fail at load. The 27 rules handle *meaning*: cross-references, capacity
arithmetic, whether a declared framework resolves to a runtime flag.

Keeping them separate matters because the two failure modes read differently to an
author. A missing `venture_name` is a typo; `projected daily approvals exceed capacity`
is a design problem with the venture.

### The validator returns a report, not a boolean

Every rule produces a result with its id, severity, verdict and a message naming the
offending value. A validator that returns False tells an author to go looking; one that
says `V13 FAIL: 340 projected approvals vs 216 capacity (0.6 x 6h x 60)` tells them what
to change.

WARN rules are reported and do not block. V24 blocks at Gate 4.5 rather than Gate 2,
because appointment output does not exist yet at Gate 2 — recorded in the rule's own
metadata rather than as a comment.

### V2 reads the world, not the Pack

Gate 0 is the one rule that cannot be checked from the document. "Bridge operational"
means: the Forge is in `forge_registry`, its health is not RED, and it has a
`forge_tenant_credential`. A Pack that *declares* a Forge is bridged proves nothing —
that is precisely the state Gate 0 exists to catch.

So the validator takes an optional database connection. Rules that need the world are
skipped-with-a-reason when it is absent, and **reported as `NOT_RUN`, never as pass**.
Part 10.1's rule about `NOT_RUN` never being reported as a failure has a converse that
matters just as much here: it must never be reported as a success either.

---

## The 27 rules

| # | Rule | Result |
|---|---|---|
| V1 | All required fields present | FAIL |
| V2 | Bridge operational for every `hard` Forge binding (Gate 0) | FAIL · needs DB |
| V3 | Every compliance framework has a resolving `runtime_flag` | FAIL |
| V4 | Every framework has `library_entry_ref` or an explicit gap flag | FAIL |
| V5 | Every KPI has `measurement_source` + `frequency` + `owner` | FAIL |
| V6 | Every Workflow module ref resolves in `forge_module_registry` | FAIL · needs DB |
| V7 | `api_version` pinned; not `latest` | FAIL |
| V8 | No `criticality: hard` with `module_gap: true` | FAIL |
| V9 | Every `external_software` transmitting PHI has a signed BAA/DPA | FAIL |
| V10 | Every `positions_required` entry names ≥1 Forge module and a source department | FAIL |
| V11 | Every position's modules have Forge Operating Instructions authored | FAIL · needs DB |
| V12 | Every instruction set has `version_sensitivity` + `content_hash` | FAIL |
| V13 | Projected daily approvals ≤ capacity × 0.6 | FAIL |
| V14 | Compliance + T&S roles have `backup_human` | FAIL |
| V15 | `gate_signoff_policy` declared; justification if single-human | FAIL |
| V16 | `agent_initiated` triggers have rate + depth limits | FAIL |
| V17 | `data_retention` covers every sensitive data type | FAIL |
| V18 | Budget caps present | FAIL |
| V19 | `availability` complete incl. RTO/RPO | FAIL |
| V20 | Every binding has `rate_limit_policy` and `credential_mode` | FAIL |
| V21 | SimForge binding present, `criticality: hard` | FAIL |
| V22 | Every compliance flag appears in ≥1 scenario | FAIL |
| V23 | ≥3 scenarios per role × domain; ≥1 `expected_escalation` per role | FAIL |
| V24 | Unfilled positions in appointment output | FAIL at Gate 4.5 |
| V25 | Declared Forge with zero `required_by` references | WARN |
| V26 | `fallback_behavior` on every `soft` Forge | WARN |
| V27 | Any `[MODULE GAP]` in Pack | WARN + surfaced at Gate 4 |

**V13 arithmetic**, stated because it is easy to get subtly wrong:
`projected_daily_approvals × median_review_minutes ≤ coverage_hours × 60 × 0.6`.
The 0.6 is Part 14's utilisation factor — a human who reviews for 100% of their coverage
hours does nothing else, and a trust tier backed by a saturated reviewer is a
rubber stamp waiting to happen.

---

## Acceptance tests

- Every FAIL rule: one fixture that must fail it, one that must pass it. **54 assertions
  minimum**, and a meta-test asserting no rule lacks either.
- The Greenstone Pack passes every rule that does not need the bridge.
- A rule needing the world reports `NOT_RUN` without a connection — never `PASS`.
- WARN does not block; FAIL does.
- Validator output is deterministic: same Pack, same report, same order.

---

## Out of scope for this increment

The seven generators (increment 2). Shift assignment and PHI flush (increment 3). The
Pack Editor UI (Part 17).

---

# Phase 3, increment 2 — The Seven Generators — PLAN

Master prompt Part 5. **Deterministic transformers: same Pack in, same artifacts out.**
No LLM anywhere in this increment — structural generation must be reproducible, and
`tests/golden/` snapshot-asserts every artifact so any diff fails CI.

| # | Generator | In | Out |
|---|---|---|---|
| 5.1 | Role Definition | Pack | positions fully specified, implied compliance flags resolved |
| 5.2 | Appointment | positions + roster + certification | named agents + the three capacity numbers |
| 5.3 | Workflow | lifecycle_stages + positions | ordered steps, each naming a module, a flag and an escalation |
| 5.4 | Task Ledger | Workflow + Appointments | tasks with tier, SLA, volume, idempotency class + projected approvals per human |
| 5.5 | Curriculum | Pack + Workflow + Appointments + Instructions | Scenario Pack with coverage denominators |
| 5.6 | Forge Manifest | bindings + Workflow + Task Ledger | BOM + three-way reconciliation |
| 5.7 | Runtime Config | all above | idempotent deployment; re-run = identical state |

## Schema divergence #3 — `lifecycle_stages_owned` on Position

Generator 5.3 is specified as `In: lifecycle_stages. Out: [step table]`, and every step
must name a **position**, a **module**, a **compliance flag or explicit NONE**, and an
**escalation path**.

Schema v3 carries lifecycle stages on the service line and modules on the position, but
**nothing maps a position to a stage.** Without that mapping the generator can only
guess — distributing positions across stages by index, or string-matching duty text.
Both are deterministic and both produce a nonsense workflow, which is worse than
failing: a plausible-looking workflow nobody can trace is exactly the defect class the
blueprint's test strategy calls out.

So `Position` gains `lifecycle_stages_owned: list[str]`, defaulting to every stage.
Recorded here rather than silently added. **The blueprint should be amended** — this is
the third such gap, after the partitioned-table PK and the ledger's missing `task_id`.

## Determinism rules

- No `uuid4` in any artifact. `grant_id` and `task_id` are **UUIDv5** derived from their
  natural key, which also makes 5.7's idempotency structural rather than a code path.
- No wall-clock timestamps inside artifacts.
- Every collection sorted by an explicit key, never by dict or query order.
- Candidate agents ordered by `(agent_name, office_agent_id)` — a stable tiebreak, so
  two runs against the same roster appoint the same agents.

## Acceptance tests

| # | Test | Asserts |
|---|---|---|
| G1 | every generator is byte-identical across two runs | determinism |
| G2 | golden snapshots match | regression |
| G3 | 5.1 derives implied compliance flags the author omitted | it does real work |
| G4 | 5.2 never appoints an uncertified agent | Part 5.2, absolute |
| G5 | 5.2 reports all three capacity numbers on a shortfall | §7.2 |
| G6 | 5.2 flags a shortfall rather than auto-rejecting or lowering the bar | §7.3 |
| G7 | every workflow step names a module, a flag-or-NONE, and an escalation | 5.3 |
| G8 | 5.4 projects daily approvals per human role | 5.4 required output |
| G9 | 5.5 states a coverage denominator for every dimension | "report the denominator" |
| G10 | 5.6 `REQUIRED_NOT_DECLARED` fails the Pack | 5.6 |
| G11 | 5.6 `hard` + `module_gap` cannot provision | 5.6 |
| G12 | 5.7 run twice → identical state, zero duplicate rows | idempotency |
| G13 | 5.7 consumes the Manifest, not the Pack | 5.7, stated explicitly |
