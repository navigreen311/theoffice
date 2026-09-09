# Parallel build — Gate 4.5 to a certified agent

**Opened 9 September 2026 by P-00.** Governed by `docs/coordination-plan-gate45.md`
Revision 3; the fifteen package prompts are in
`docs/coordination-plan-gate45-packages.md`.

**One coordinator merges, never in parallel. No force-push to main, ever.**

---

## Baselines — the gate is *no new failures against these*, never a green board

Recorded before any package started, because a board that was already red cannot be
judged against green and a package that tries will "fix" something deliberate.

### Starting SHAs

| repo | SHA | branch |
|---|---|---|
| `theoffice` | `5e39956` | main |
| `simforge` | `2ce2f5d` | main |

### Test counts at those SHAs

| repo | collected |
|---|---|
| `theoffice` | **1049** |
| `simforge` | **769** |

**A package that changes the count must say why in its PR.** The missing-V34-tests gap was
caught only because a pass count did not move when it should have — nothing checks that a
new rule has a test, and the count is the only signal.

### `theoffice` CI — six green, Smoke alone red, deliberately

| job | state |
|---|---|
| Console | pass |
| Images build | pass |
| Lint and types | pass |
| Migrations are reversible | pass |
| No committed secrets | pass |
| Tests | pass |
| **Smoke — the console actually renders** | **FAIL — the baseline below** |

**Do not fix Smoke. Do not weaken V11, V22, V32 or V33 to make it green.** It fails because
V11 and V32 report NOT_RUN in CI, where no runner can reach a live Forge. That is the
correct answer to a question CI cannot ask.

### The Smoke baseline capture — ten lines, verbatim

Reference run `34263050339`. **Diff byte-for-byte against this before merging anything.**

```
  FAIL the Gate 4 review form did not render
  FAIL the review form rendered without the artifacts summary above it - that is a rubber-stamp machine
  FAIL detail page lost: This gate waits. It does not pass on its own, and nothing ad
  FAIL detail page lost: Runs from gate 4 until a gate stops it. Gates are not skippa
  FAIL detail page lost: Required. Recorded against your name in the append-only log.
  FAIL the raw evidence is gone entirely - engineers need it
  FAIL recording a review and advancing are still two unrelated controls
  FAIL unevaluable rules with no gate named: ['V11', 'V32']
  1 check(s) could not run
  8 check(s) failed
```

**A zero-line diff of two empty captures is not a comparison.** Verify the capture is
non-empty and ten lines long before you conclude anything from it. This has already been
caught once in this project: two empty greps compared equal and read as a pass.

---

## Caveats carried forward

Each was paid for once. They are here so it is not paid for twice.

**Caveat 12 — a `tail -3` on a three-command chain is a prediction dressed as a
measurement.** "Ruff clean" was reported twice from an unread `tail`, while ruff was failing
on three `UP017` violations the whole time. **Read the output you report.**

**Caveat 13 — a grep finds mentions, not construction.** Four construction sites were
predicted from a grep hit list; one broke, and the failure surfaced in a fifth file never
named. Three of the four hits were a copy, a mutation and a docstring. **Read each hit
before claiming what it does.**

**Caveat 14 — read a claim out of the schema or the receiving side, not out of the names.**
New this run. The coordination plan's own premise was wrong twice, and both times a name was
doing the reasoning: *"unit B"* looked like it needed domain scenarios and does not, and
*"no new code expected"* described a path with no writer at all.

**Every agent gets its own git worktree.** `git checkout -b` in a shared checkout collides
with whatever another agent has uncommitted. This cost a recovery on the previous run.

**A migration or a rule moves `EXPECTED_SCHEMA_REVISION` and every rule-count assertion, in
the same commit.** CI catches it, and the assertion's own message tells you to.

**A moved golden snapshot is a finding, not a chore.** `UPDATE_GOLDEN=1` is the
coordinator's call, never a package's.

---

## Ruling — T-014 is dropped from P-00's blockers and stays owed

**9 September 2026, by Ivan. Recorded as a ruling rather than an edit, so the next reader
meets a decision instead of a blocker that quietly vanished.**

P-00's card required **both** T-013 (rotate `OFFICE_SHARED_SECRET`) and T-014 (create Ira
Green's `office_human` row) before merge. **T-013 is verified. T-014 is not met** — no row
matching "Ira" exists under any origin, and the newest `console_human_created` audit event
is from 26 August. The call never reached the endpoint.

**T-014 is removed as a blocker because nothing on the critical path reads Ira's row:**

- **Unit-B certification is what blocks C**, not the Pack's reviewer list. Every Burkham
  candidate is refused `missing_unit_b` for `administration`, `banking` and `operations`
  regardless of who is named in `human_capacity`.
- **B22's second half: Gate 4 never reads `human_capacity` at all.** `record_human_review`
  authorizes on role strength and venture scope and never asks whether the reviewer is one
  the venture declared. A named reviewer with no account changes nothing there.

**T-014 stays owed. It is not cancelled and it is not done.** It gates nothing, which is
exactly why it is at risk of being forgotten — so it is written here rather than left in a
card nobody reopens.

### T-013 — verified after the rotation, all three states distinct

| control | result |
|---|---|
| valid token | **`HTTP 200`, 11 modules** |
| no token | `HTTP 401` · **`OFFICE_CREDENTIAL_REJECTED`** |
| wrong token | `HTTP 401` · **`OFFICE_CREDENTIAL_REJECTED`** |

The eleven: `client_read`, `client_read_credit`, `client_read_pii`,
`compliance_manifest_assemble`, `portfolio_health`, `record_consent`,
`regulator_dossier_export`, `restack_recommend`, `scan_communication`, `statement_pull`,
`submit_application`.

**Counted from the parsed body, not from the status.** The code is present on both 401s,
which is the distinguishing evidence: an unmounted bridge and a rejected credential share a
status, and only the absence of `OFFICE_CREDENTIAL_REJECTED` tells them apart.

---

## Number pre-allocation

So two agents never claim the same entry. **Write into your allocated number; do not choose
your own.**

**`theoffice` has no `docs/adr/` directory — `docs/decisions.md` is the mechanism here.**
`simforge` has `docs/adr/`. P-00's own card said "an ADR"; on this side that is an entry, and
the correction is noted rather than silently applied.

| package | `docs/decisions.md` | `simforge/docs/adr/` |
|---|---|---|
| **P-00** | **entry 27** — A0: certification is out of band, both producers missing · **WRITTEN** | ADR number to be claimed by P-01 or P-05, whichever lands first |
| **P-00** | **entry 28** — unit B does not require executable domain scenarios; entry 23 stands · **WRITTEN** | — |
| **P-14** | **entry 29** — AnimaForge: zero for V1 | — |
| **P-10** | **entry 30**, if the reviewer-exists rule warrants one | — |
| any other package | **ask the coordinator before writing to `decisions.md`** | — |

`docs/blocking.md` is **append-only, one section per package.** A closure is an appended
paragraph; it never rewrites the item above it.

**No interface file is needed this run.** No package imports another's new code — P-05 is in
a different repo from everything it serves. Stated so nobody invents one to be safe.

---

## Merge ledger

Every merge gets a row: package, PR, merge SHA, test result, timestamp.

| package | PR | merge SHA | tests | Smoke vs baseline | timestamp |
|---|---|---|---|---|---|
| — | [#69](https://github.com/navigreen311/theoffice/pull/69) | `c4671fa` | 1049 pass | 10 lines, identical | 2026-09-09 |
| — | [#70](https://github.com/navigreen311/theoffice/pull/70) | `5e39956` | 1049 pass | 10 lines, identical | 2026-09-09 |
| P-00 | | | | | |
| P-01 | | | | | |
| P-02 | | | | | |
| P-03 | | | | | |
| P-04 | | | | | |
| P-05 | | | | | |
| P-06 | | | | | |
| P-07 | | | | | |
| P-08 | | | | | |
| P-09 | | | | | |
| P-10 | | | | | |
| P-11 | | | | | |
| P-12 | | | | | |
| P-13 | | | | | |
| P-14 | | | | | |

*(#69 and #70 predate P-00 and are listed because they changed `docs/blocking.md`, which
every package appends to. #69 is T-015.)*

---

## Two results wanted the day they happen, not in a summary

**Ivan's standing instruction, 9 September.**

**P-01's result — within the hour if Gate 8 still fails.** Four packages are aimed at a
handover nobody has seen work: P-02, P-03, P-04 and P-05 all assume a submission is
accepted. If it is not, they are aimed at nothing and the wave stops rather than continuing
on an assumption.

**GAP-5 — does SimForge hold domain certifications for `administration`, `banking` and
`operations`?** **P-04's first task, before any code — not P-11's discovery.** Only
`engineering` exists on The Office's side. If SimForge holds none for Burkham's three, P-04
still ships a submitter that correctly reports them uncertified, and C stays blocked on
something true. **Finding this at P-11 would mean four merged packages before anyone learned
the run could not finish.**

---

## Escalation

- A package needing a file outside its list writes `PARALLEL_BUILD_ESCALATION.md` on its
  branch and flags it in the PR. **It does not modify the file.**
- **A critical-path package failing twice halts the entire run** and escalates to Ivan.
- Any package requiring more than one revert-and-retry gets a post-mortem entry here.
