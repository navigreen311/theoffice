# Package distribution — Gate 4.5 to a certified agent

**9 September 2026.** Fifteen paste-ready prompts, one per package, each self-contained.
Governed by `docs/coordination-plan-gate45.md` Revision 3.

**Before P-00 merges, Ivan does T-013** (rotate `OFFICE_SHARED_SECRET` in both `.env` files,
restart, re-run the three bridge checks) **and T-014** (create Ira Green's `office_human`).

**Merge order is the order below. Never parallel-merge into main. Never force-push to main.**

| # | Package | Repo | Depends on | Cx |
|---|---|---|---|---|
| 1 | **P-00** — Coordinator — foundations | theoffice | NONE | M |
| 2 | **P-01** — A1 — verify the Gate 8 handover is accepted | simforge | P-00 | M |
| 3 | **P-02** — A1b — Gate 8 from The Office's side | theoffice | P-01 | S |
| 4 | **P-03** — Unit-A verdict return path — the sweep as ingester  [CRITICAL PATH] | theoffice | P-02 | L |
| 5 | **P-04** — Unit-B department submitter  [CRITICAL PATH] | theoffice | P-03 — same file, same sweep | L |
| 6 | **P-05** — A2 — held-out authoring, BOTH classes  [CRITICAL PATH] | simforge | P-01 | L — unscoped |
| 7 | **P-06** — Declare portfolio_health's escalation_required not-applicable | theoffice | P-00 | S |
| 8 | **P-07** — B27 + B26 — the false message and the round-trip test | theoffice | P-00 | M |
| 9 | **P-08** — B23 — four names asserting more than the code does | theoffice | P-00 | M |
| 10 | **P-09** — B25 — the two gates aggregate supply differently | theoffice | P-00 | M |
| 11 | **P-10** — B22 — the reviewer-exists check | theoffice | P-09 AND P-03 — both own files you touch | M |
| 12 | **P-11** — C — the certification run | theoffice | P-03, P-04, P-05 AND P-06 — all four | M |
| 13 | **P-12** — D — Gate 5 and the manifest | theoffice | P-11 | M |
| 14 | **P-13** — G — FunnelForge binding | theoffice | NONE — fully independent, gates nothing | L |
| 15 | **P-14** — AnimaForge — the ruling, recorded | theoffice | P-00 | S |

**Critical path:** P-00 → P-01 → P-02 → P-03 → P-04 → P-11 → P-12, with P-05 joining before P-11.

**Can start the moment P-00 lands:** P-01, P-06, P-07, P-08, P-09, P-13 — and P-14.

---

## P-00 — Coordinator — foundations

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-00
Title:                 Coordinator — foundations
Repo:                  theoffice (+ one simforge ADR)
Tasks included:        T-001, T-008, T-010, T-012, T-015
Merge order:           1    Complexity: M

Description:
  Lay the ground every other package stands on: the baseline record, the A0 finding, and
  pre-allocated numbers so two agents never claim the same decisions entry.

  YOU BUILD NOTHING. Everything here is a record.

  PARALLEL_BUILD.md must capture, before anything runs:
    - THE BASELINE, NOT GREEN. theoffice main is red on Smoke ALONE, deliberately: V11 and
      V32 report NOT_RUN in CI where no runner can reach a live Forge. Capture that failing-
      check list BYTE-FOR-BYTE, and record that a comparison of two EMPTY captures is not a
      comparison.
    - Test counts per repo at the starting SHA.
    - Caveats carried forward: a `tail -3` on a three-command chain is a prediction dressed
      as a measurement; a grep finds mentions, not construction.
    - The empty merge ledger.

  The A0 finding, into blocking.md and an ADR:
    - Certification is OUT OF BAND by design — Gate 9 reads the record, not the wire.
    - TWO producers are missing, not one: `attested_by="simforge"` appears nowhere (unit A),
      and nothing submits a department curriculum at all (unit B).
    - UNIT B DOES NOT REQUIRE EXECUTABLE DOMAIN SCENARIOS, so decisions.md entry 5 STANDS and
      its reopening condition has NOT fired. Record this explicitly — the opposite finding
      would have reversed a ruling, and a reader needs to know it was checked.

FILES YOU MAY CREATE:
  - PARALLEL_BUILD.md
  - docs/adr/ADR-00XX-certification-is-out-of-band.md  (choose the number, then record it)
  - simforge: docs/adr/ADR-00YY (same finding, simforge side)

FILES YOU MAY MODIFY:
  - docs/blocking.md
  - docs/decisions.md   (pre-allocate an entry number per package; P-14 needs one)

FILES YOU MUST NOT TOUCH:
  - any file under broker/, generators/ or tests/
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            NONE
BLOCKED BY:            T-013 and T-014 — Ivan does both before you merge
BRANCH NAME:           feature/p-00-coordinator
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  tests/test_docs.py must pass. No new tests — you are not changing behaviour.

COMPLIANCE / SECURITY FLAGS:
  none

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-01 — A1 — verify the Gate 8 handover is accepted

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-01
Title:                 A1 — verify the Gate 8 handover is accepted
Repo:                  simforge
Tasks included:        T-004
Merge order:           2    Complexity: M

Description:
  Gate 8 submitted six curricula and got six 422s on missing scenario_class and
  instruction_section. P-05 put both fields on the wire. NOBODY HAS RUN GATE 8 SINCE, so the
  fix is unexercised and no curriculum_submission row has ever carried a run_ref.

  Observe one real submission being accepted. That is the whole package.

  EVERYTHING DOWNSTREAM WAITS ON THIS. P-03's sweep cannot be judged usable until a row
  carries a run_ref, and P-05 builds on a submission path nobody has seen work.

FILES YOU MAY CREATE:
  - an end-to-end curriculum submission test

FILES YOU MAY MODIFY:
  - nothing in production code. IF A PRODUCTION CHANGE IS NEEDED, THAT IS THE FINDING —
    write it in the PR, do not fix it here.

FILES YOU MUST NOT TOUCH:
  - src/services/operation/scenarios.py
  - src/services/operation/never_do.py
  - src/services/operation/run_registry.py
  - the scorer / rubric modules
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-00
BLOCKED BY:            NONE
BRANCH NAME:           feature/p-01-verify-handover
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  One real submission accepted, asserted ON THE RESPONSE BODY, not on a 200. A 200 whose
  body rejected the curriculum is the exact failure this package exists to catch.

COMPLIANCE / SECURITY FLAGS:
  THIS PACKAGE MAY REPORT THAT THE HANDOVER STILL FAILS. That is a valid outcome and a
  useful one. Do not work around it, do not adjust the submission until it passes, and do
  not report success you did not observe.

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-02 — A1b — Gate 8 from The Office's side

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-02
Title:                 A1b — Gate 8 from The Office's side
Repo:                  theoffice
Tasks included:        T-004 (mirror)
Merge order:           3    Complexity: S

Description:
  The other half of P-01: confirm Gate 8 submits and that simforge_run_ref is populated on
  the curriculum_submission row.

  That field being NULL on all 10 existing rows is why blocking.md B8 is still open. This
  package is what retires it — or proves it is not yet retirable.

FILES YOU MAY CREATE:
  - a Gate 8 harness test under tests/provisioning/

FILES YOU MAY MODIFY:
  - nothing in production code

FILES YOU MUST NOT TOUCH:
  - broker/provisioning.py   (P-03 owns it)
  - broker/simforge.py       (P-03 owns it)
  - broker/certification.py  (P-03 owns it)
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-01
BLOCKED BY:            NONE
BRANCH NAME:           feature/p-02-gate8-harness
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  Gate 8 submits, and `curriculum_submission.simforge_run_ref` IS POPULATED — the exact
  condition B8 waits on. Assert on the STORED ROW, not on the call returning.

COMPLIANCE / SECURITY FLAGS:
  none

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-03 — Unit-A verdict return path — the sweep as ingester  [CRITICAL PATH]

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-03
Title:                 Unit-A verdict return path — the sweep as ingester  [CRITICAL PATH]
Repo:                  theoffice
Tasks included:        T-002, T-021
Merge order:           4    Complexity: L

Description:
  There is no code that turns a SimForge verdict into a certification row.
  `attested_by="simforge"` appears NOWHERE in this codebase. `record_result` has one
  non-test caller: bootstrap_phase0.py. `SimForgeClient.gate_result(run_ref)` exists and
  nothing outside tests calls it.

  Build the caller. FOUR OF FIVE PIECES ALREADY EXIST:
    - overdue_submissions()  — the query, referenced by nothing but its own test
    - timeout_gate_result()  — builds a GateResult and derives the unit correctly
    - VERDICT_TO_STATE       — the mapping
    - SimForgeClient.gate_result(run_ref) — fetches a real verdict
  Only the caller is missing, and the sweep registry does not include it.

  SETTLED DESIGN — A SWEEP, NOT AN INBOUND ROUTE. The reasoning is overdue_submissions' own
  docstring: "a control that depends on the failing component to announce its own failure is
  not a control." An inbound route would have SimForge announcing a value that grants
  production authority — the same shape that docstring rejects, at higher stakes.

  Also carries T-021 (B29): authorize() returns the role acted as, sign_off keeps it into
  signoff_record.role_signed_as, and record_human_review discards it one line later. Carry it
  into provisioning_gate_result.evidence, which is jsonb — NO MIGRATION. It is in your
  package only because it lives in a file you own, not because the tasks relate.

FILES YOU MAY CREATE:
  - the ingest caller (a sweep entry, wired into the sweep registry)

FILES YOU MAY MODIFY:
  - broker/simforge.py
  - broker/certification.py
  - broker/provisioning.py
  - the sweep registry
  - docs/blocking.md   (YOUR SECTION ONLY — a B29 closure note)

FILES YOU MUST NOT TOUCH:
  - generators/*            (P-06, P-08, P-09, P-10 territory)
  - broker/packs.py         (P-07 owns it)
  - anything under packs/
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-02
BLOCKED BY:            NONE — the sweep-vs-route question was ruled 9 September
BRANCH NAME:           feature/p-03-verdict-ingest
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  - a SimForge verdict produces a certification row with attested_by='simforge'
  - a WITHHELD verdict produces `provisional`, NEVER `certified`
  - the existing `certified_records_its_basis` CHECK is EXERCISED, never bypassed: a
    certified row lacking instruction_content_hash, forge_api_version or certified_tier must
    still be refused
  - an unanswered run STILL resolves to TIMEOUT and in_training — you are adding a branch,
    not replacing the timeout path
  - B29: a Gate 4 review records the role acted as, in evidence

COMPLIANCE / SECURITY FLAGS:
  AUTH / TRUST BOUNDARY. This path grants production authority. A verdict that certifies
  must not be constructible by the submitter. If your design lets the party being certified
  influence its own verdict, STOP and escalate.

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-04 — Unit-B department submitter  [CRITICAL PATH]

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-04
Title:                 Unit-B department submitter  [CRITICAL PATH]
Repo:                  theoffice
Tasks included:        T-003
Merge order:           5    Complexity: L

Description:
  Certification has TWO units and Gate 8 produces only one of them.

    unit_targets_match:  A -> office_agent_id AND module_id NOT NULL
                         B -> department NOT NULL
    rubric_matches_unit: (A AND rubric_kind='operation') OR (B AND rubric_kind='domain')

  A submission is one or the other, keyed on module_id. Gate 8 submits per module, so it
  produces unit-A only: curriculum_submission holds 10 rows, 10 with module_id, 0 with
  department.

  AND UNIT B GATES APPOINTMENT. generators/appointment.py refuses any candidate whose forges
  lack a certified unit-B row for the position's department. The only unit-B rows that exist
  are three bootstrap rows, all department='engineering'. Burkham declares administration,
  banking and operations. EVERY BURKHAM CANDIDATE IS REFUSED missing_unit_b EVEN AFTER P-03
  LANDS.

  Build the submitter: start a run per (department, forge) with unit="B",
  rubric_kind="domain", department_id — OperationRunStart already accepts all three — and
  read the verdict back through P-03's sweep.

  YOUR FIRST TASK, BEFORE ANY CODE: does SimForge hold domain certifications for
  administration, banking and operations? Only engineering exists on our side. If SimForge
  holds none, YOU STILL SHIP — a submitter that correctly reports three uncertified
  departments is the honest outcome, and C stays blocked on something true.

FILES YOU MAY CREATE:
  - the unit-B submission path

FILES YOU MAY MODIFY:
  - broker/simforge.py
  - broker/certification.py
  - docs/blocking.md   (YOUR SECTION ONLY)

FILES YOU MUST NOT TOUCH:
  - broker/provisioning.py  (P-03 landed it; do not re-enter)
  - generators/*
  - broker/packs.py
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-03 — same file, same sweep
BLOCKED BY:            NONE
BRANCH NAME:           feature/p-04-unit-b-submitter
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  - a unit-B submission carries `department` and NO module_id, satisfying unit_targets_match
  - the row lands with rubric_kind='domain', satisfying rubric_matches_unit
  - a department with no SimForge domain cert REPORTS AS UNCERTIFIED, not as an error
  - the unit-A path is unaffected

COMPLIANCE / SECURITY FLAGS:
  DO NOT BUILD AN EXECUTABLE-DOMAIN-SCENARIO BRIDGE.

  A unit-B run closes on department certification STATES (run_registry.py:135 —
  `own_states = agent_states if run.unit == "A" else department_states`), not on scenario
  execution of Office-submitted content. The Office's domain scenarios are prose
  {role, domain, summary}; SimForge's are hashed YAML with a seed and a target agent. They
  share scenario_id and nothing else.

  decisions.md entry 5 ruled Office domain scenarios Pack-validation-only. THAT RULING STANDS
  and its reopening condition has NOT fired. Do not reverse it by accident.

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-05 — A2 — held-out authoring, BOTH classes  [CRITICAL PATH]

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-05
Title:                 A2 — held-out authoring, BOTH classes  [CRITICAL PATH]
Repo:                  simforge
Tasks included:        T-005
Merge order:           6    Complexity: L — unscoped

Description:
  HELD_OUT_CLASSES = frozenset({NEVER_DO_VIOLATION, SILENT_FAILURE}). SimForge authors
  these; the submitter is forbidden to, and validate_curriculum_submission refuses either on
  arrival.

  simforge's P-03 (2ce2f5d) moved the never-do refusal from submission time to SCORING time,
  so a submission declaring a never-do list with no authored scenario is accepted and held at
  provisional — a real coverage hole reported as one. The consequence: EVERY MODULE DECLARING
  A NEVER-DO LIST SITS AT PROVISIONAL, because the pipeline that would author those scenarios
  does not exist.

  Build that pipeline. Take a declared module_never_do entry, author a held-out
  never_do_violation scenario that tests whether the agent declines, grade it like any other
  class.

  BOTH CLASSES, ONE PIPELINE. silent_failure is in the same frozenset, refused by the same
  path, named in the same GATE_9_5_FLAG. classify_certification_level does
  `declared - HELD_OUT_CLASSES`, so NEITHER can be declared away via ADR-0049. Deferring
  silent_failure would leave modules stuck at provisional for the second reason after you
  fixed the first.

  Sizing input: the eleven CapitalForge manuals carry the richest material for exactly this
  class. record_consent alone has 13 never_do entries, each already a violation scenario in
  miniature. That material lives on The Office's side and is structurally unavailable to it.

FILES YOU MAY CREATE:
  - the held-out authoring pipeline

FILES YOU MAY MODIFY:
  - src/services/operation/scenarios.py
  - src/services/operation/never_do.py
  - the scorer / rubric modules

FILES YOU MUST NOT TOUCH:
  - the curriculum submission validator's acceptance path (P-01's territory)
  - src/services/operation/run_registry.py
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-01
BLOCKED BY:            NONE
BRANCH NAME:           feature/p-05-held-out-authoring
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  - a declared module_never_do entry produces a held-out never_do_violation scenario
  - AN EQUIVALENT PATH EXISTS FOR silent_failure
  - THE SUBMITTER CANNOT READ EITHER SET — asserted by a test, not claimed in a comment
  - a compliant agent passes and a violating agent fails
  - a module whose never-do obligation is now exercised stops being a coverage hole

COMPLIANCE / SECURITY FLAGS:
  HELD-OUT INTEGRITY. GATE_9_5_FLAG already records that "the engine cannot self-prove that
  isolation". You cannot close that gap here — but you must not widen it. The isolation test
  is mandatory.

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-06 — Declare portfolio_health's escalation_required not-applicable

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-06
Title:                 Declare portfolio_health's escalation_required not-applicable
Repo:                  theoffice
Tasks included:        T-007
Merge order:           7    Complexity: S

Description:
  escalation_required is mandatory per module. capitalforge/portfolio_health cannot supply it
  at any level of effort — it takes no identifier, writes nothing, and its retry_vs_escalate
  is "RETRY FREELY" in full. There is no failure to hand a human.

  Stack Manager operates portfolio_health, so without this that position cannot be certified
  regardless of how well anything is authored.

  THE MECHANISM IS ALREADY BUILT ON BOTH SIDES. Do not build it again:
    simforge  — NotApplicableDeclaration, declarations_from_map, required prose reason, and
                three levels: certified / certified_with_declared_absence / demonstrated
    theoffice — not_applicable_reason on the curriculum artifact, emitted by
                generators/curriculum.py

  Your package is THE DECLARATION, not the mechanism. Closes blocking.md B16.

FILES YOU MAY CREATE:
  - nothing

FILES YOU MAY MODIFY:
  - the capitalforge/portfolio_health scenario content / declaration
  - docs/blocking.md   (YOUR SECTION ONLY — a B16 closure note)

FILES YOU MUST NOT TOUCH:
  - generators/curriculum.py's mechanism (USE it, do not change it)
  - broker/simforge.py, broker/certification.py  (P-03/P-04)
  - anything in the simforge repo
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-00
BLOCKED BY:            NONE
BRANCH NAME:           feature/p-06-portfolio-health-na
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  - the declaration reaches SimForge as module_not_applicable
  - escalation_required reports declared-absent WITH ITS REASON, not untested
  - THE MODULE CLASSIFIES AS certified_with_declared_absence, NEVER certified. That level
    exists precisely so the cap stops being silent, and a test asserting `certified` would be
    asserting the bug ADR-0049 was written to prevent.

COMPLIANCE / SECURITY FLAGS:
  The reason is REQUIRED PROSE. A one-word reason is refused by machinery that already
  exists. Do not weaken it to pass — the refusal is the feature.

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-07 — B27 + B26 — the false message and the round-trip test

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-07
Title:                 B27 + B26 — the false message and the round-trip test
Repo:                  theoffice
Tasks included:        T-019, T-020
Merge order:           8    Complexity: M

Description:
  B27: live() and get_version() report a row stored under an earlier schema as
  "not a schema-v3 Business Pack". THE ROW IS SCHEMA-V3. Its schema_version column says 3 and
  it was valid v3 the day it was written. The true statement is narrower: stored before
  provenance was required. The message asserts something false about the data, and it sends
  the reader to inspect a Pack that is fine instead of to the migration.

  B26: nothing reads a published Pack back out of business_pack and parses it. Every test
  loads from packs/*.yaml on disk. That is why making provenance required left twelve
  published rows unreadable and no test noticed.

FILES YOU MAY CREATE:
  - a round-trip test under tests/contract/

FILES YOU MAY MODIFY:
  - broker/packs.py
  - docs/blocking.md   (YOUR SECTION ONLY — B26/B27 closure notes)

FILES YOU MUST NOT TOUCH:
  - broker/provisioning.py, broker/simforge.py, broker/certification.py
  - generators/*
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-00
BLOCKED BY:            NONE
BRANCH NAME:           feature/p-07-pack-read-honesty
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  - an old-schema row reports "stored before provenance was required", not "not schema-v3"
  - THE ROUND-TRIP TEST MUST BE SHOWN TO FAIL against a row written before the field existed.
    Construct one and demonstrate it. A version that publishes and re-reads in one process
    proves only that store and live agree, which is NOT the property.

COMPLIANCE / SECURITY FLAGS:
  none

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-08 — B23 — four names asserting more than the code does

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-08
Title:                 B23 — four names asserting more than the code does
Repo:                  theoffice
Tasks included:        T-017 (carries T-010)
Merge order:           9    Complexity: M

Description:
  Four names, each more specific than the thing behind it. None is a lie; each invites a
  conclusion the code never made:

    produced_not_yet_certified — counts candidates EXAMINED FOR POSITIONS BEING APPOINTED,
                                 not uncertified identities in the venture
    live (on a Pack)           — a status column that read `live` on twelve rows the parser
                                 could not read
    review_seconds             — populated and never used; MUST NOT be dropped into
                                 median_review_minutes
    max_daily_approvals        — decoration; no rule reads it, and V13 computes from
                                 coverage_hours and median_review_minutes alone

FILES YOU MAY CREATE:
  - nothing

FILES YOU MAY MODIFY:
  - the four names and their call sites
  - docs/blocking.md   (YOUR SECTION ONLY)

FILES YOU MUST NOT TOUCH:
  - tests/golden/snapshots/*  — IF A SNAPSHOT MOVES, STOP AND ESCALATE
  - broker/simforge.py, broker/certification.py, broker/provisioning.py, broker/packs.py
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-00
BLOCKED BY:            NONE
BRANCH NAME:           feature/p-08-honest-names
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  Every renamed symbol has its call sites updated and the existing tests still pass. Add a
  test only where a name change revealed a behaviour worth pinning.

COMPLIANCE / SECURITY FLAGS:
  A rename that changes a SERIALIZED ARTIFACT is a different change from one that does not.
  If a golden snapshot moves, that is the signal you crossed that line — escalate rather than
  regenerate.

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-09 — B25 — the two gates aggregate supply differently

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-09
Title:                 B25 — the two gates aggregate supply differently
Repo:                  theoffice
Tasks included:        T-018
Merge order:           10    Complexity: M

Description:
  V13 has two implementations and they do not compute the same quantity:

    Gate 2   — pools EVERY human regardless of role, unweighted mean of
               median_review_minutes, sum of all coverage
    Gate 4.5 — splits per role, coverage-weighted review minutes (B24, already fixed),
               sum per role

  The Gate 4.5 docstring explains at length why the two gates see different DEMAND figures
  and says nothing about them aggregating SUPPLY differently. A documented difference sitting
  next to an undocumented one is worse than two undocumented ones, because the first vouches
  for the second.

  Either share one aggregation helper, or state Gate 2's pooling as a deliberate
  simplification and say why. The second is probably right — Gate 2 is explicitly the cheap
  estimate — but it has to be a STATED CHOICE, not a difference somebody finds by reading
  both.

FILES YOU MAY CREATE:
  - docs/plans/<slug>-PREDICTION.md   (see the test scope — write it BEFORE you run)

FILES YOU MAY MODIFY:
  - generators/validator.py  — THE GATE 2 V13 PATH ONLY
  - docs/blocking.md   (YOUR SECTION ONLY — a B25 closure note)

FILES YOU MUST NOT TOUCH:
  - the Gate 4.5 recheck body in generators/validator.py (B24 fixed it; leave it)
  - broker/*
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-00
BLOCKED BY:            NONE
BRANCH NAME:           feature/p-09-v13-aggregation
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  WRITE A PREDICTION FILE BEFORE YOU RUN, predicting Burkham's and Greenstone's V13 verdicts
  at BOTH gates. Score it below a line afterwards without editing what is above.

  If either venture's verdict FLIPS, that is a verdict changing without anything getting
  better. It needs a written explanation in the PR, not a silent pass.

COMPLIANCE / SECURITY FLAGS:
  BURKHAM'S V13 MARGIN IS TWELVE MINUTES — 420 demanded against 432 available. A Gate 2
  change that moves the pooled mean can move it. REPORT THE NEW MARGIN EXPLICITLY. "PASS" is
  not a report; a PASS looks identical at twelve minutes of margin and at twelve hours.

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-10 — B22 — the reviewer-exists check

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-10
Title:                 B22 — the reviewer-exists check
Repo:                  theoffice
Tasks included:        T-016
Merge order:           11    Complexity: M

Description:
  The Pack-to-human join is a display-name string match. Nothing between Gate 0 and Gate 10
  checks that a named reviewer has an account. Both halves:

    - the Pack can name a reviewer the system has never heard of
    - the system will accept a review from someone the Pack never named

  RULED 9 SEPTEMBER: NAME MATCH, NOT AN ID. The finding is not that the join is a string; it
  is that NOTHING CHECKS THE STRING RESOLVES UNTIL GATE 10. Moving the check to Gate 1 or 2
  fixes both halves with no schema change.

  Record the id as the DEFERRED option, and what would justify it: two humans sharing a
  display name, or a rename orphaning a reference. NEITHER HAS HAPPENED. When one does the
  case makes itself — so record the trigger and do not pre-build for it.

FILES YOU MAY CREATE:
  - nothing

FILES YOU MAY MODIFY:
  - generators/validator.py  (a new rule)
  - broker/provisioning.py   (the Gate 4 side)
  - docs/blocking.md   (YOUR SECTION ONLY — a B22 closure note)

FILES YOU MUST NOT TOUCH:
  - the Gate 2 V13 path (P-09 just landed there)
  - broker/simforge.py, broker/certification.py, broker/packs.py
  - any migration — THE RULING IS EXPLICITLY NO SCHEMA CHANGE
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-09 AND P-03 — both own files you touch
BLOCKED BY:            NONE — ruled 9 September
BRANCH NAME:           feature/p-10-reviewer-exists
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  - a Pack naming a reviewer with no office_human row FAILS AT GATE 1 OR 2, NOT GATE 10
  - a review recorded by a human the Pack never named is recorded AS UNDECLARED
  - the message names the missing account, not the Pack generally

COMPLIANCE / SECURITY FLAGS:
  THE RULE COUNT CHANGES. Every rule-count assertion — there are at least two of the
  `34 -> 35` kind — moves IN THE SAME COMMIT. CI catches this and its own message tells you to.

  Whether Gate 4 should REFUSE an undeclared reviewer or merely RECORD that they were
  undeclared is a separate decision. An `ivan` doing an emergency review is a real case.
  RECORD; do not refuse, unless Ivan rules otherwise.

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-11 — C — the certification run

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-11
Title:                 C — the certification run
Repo:                  theoffice
Tasks included:        T-009
Merge order:           12    Complexity: M

Description:
  OPERATIONAL. No new code expected — and unlike the attachment's version of that claim, it is
  now true, because P-03 and P-04 built what was missing.

  Run certification for Burkham's agents against the eleven CapitalForge modules its positions
  operate. 54 identities exist; produced_not_yet_certified was 63 at Gate 4.

FILES YOU MAY CREATE:
  - nothing

FILES YOU MAY MODIFY:
  - nothing. If you find yourself editing production code, STOP and escalate — that means
    P-03, P-04, P-05 or P-06 left something unfinished, and it belongs to them.

FILES YOU MUST NOT TOUCH:
  - everything under broker/ and generators/
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-03, P-04, P-05 AND P-06 — all four
BLOCKED BY:            NONE
BRANCH NAME:           feature/p-11-certification-run
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  None new. THE DELIVERABLE IS A REPORT:
    - how many of the eight seats across five positions fill
    - how many candidates are refused missing_unit_b VERSUS uncertified on unit A — these are
      DIFFERENT failures with different owners
    - what produced_not_yet_certified reads, and what it means (B23: it counts candidates
      examined for positions being appointed, not uncertified identities in the venture — the
      number will behave in ways its name does not predict)

COMPLIANCE / SECURITY FLAGS:
  A certification issued here is attested by a SimForge whose OWN gate_result certification is
  a human-issued bootstrap, and the row says so (B4). What retires that is a scenario pack run
  by a DIFFERENT SimForge instance — running it on the same one certifies the thing against
  itself. STATE THIS IN YOUR REPORT. It is a real limitation with a recorded retirement
  condition, not a defect to fix before proceeding — but the first green verdict must not be
  read as more than it is.

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-12 — D — Gate 5 and the manifest

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-12
Title:                 D — Gate 5 and the manifest
Repo:                  theoffice
Tasks included:        T-011
Merge order:           13    Complexity: M

Description:
  OPERATIONAL. Advance the ladder past Gate 4.5 to Gate 5 and let runtime_config.apply
  generate the manifest. No run has ever reached Gate 5.

FILES YOU MAY CREATE:
  - nothing

FILES YOU MAY MODIFY:
  - nothing

FILES YOU MUST NOT TOUCH:
  - venture_forge_manifest rows — see the flag
  - everything under broker/ and generators/
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-11
BLOCKED BY:            NONE
BRANCH NAME:           feature/p-12-gate-5
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  None new. Report what runtime_config.apply produced and how it compares to the seven
  declared modules.

COMPLIANCE / SECURITY FLAGS:
  DO NOT HAND-WRITE MANIFEST ROWS. venture_forge_manifest holds two rows against seven
  declared modules, both hand-placed by Phase 0's bootstrap. Two hand-placed rows make it look
  like a working manifest with one module missing; FOUR MORE WOULD LEAVE THE SAME DEFECT ONE
  MODULE WIDER.

  If the generator produces fewer than seven, THAT IS THE FINDING. Report it.

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-13 — G — FunnelForge binding

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-13
Title:                 G — FunnelForge binding
Repo:                  theoffice
Tasks included:        T-022, T-023, T-025
Merge order:           14    Complexity: L

Description:
  Nine modules, scoped and approved, nothing bound: one per approved template plus
  scheduling, contact capture and analytics.

  THE DESIGN CONDITION HOLDS: the module must refuse a non-autonomous template and a non-Pass
  state INSIDE THE HANDLER, verified by tests. One grant covering all approved templates is
  only safe if the module itself is the gate.

  The price of a seventh template is six steps — adapter binding, registry row, manifest row,
  operating instruction, curriculum, certification. STEPS 4 AND 5 ARE NOT AUTOMATABLE. §4.5
  expects the inventory to grow, so someone will pay this; better chosen than discovered.
  Record the six steps as part of your deliverable.

FILES YOU MAY CREATE:
  - the FunnelForge adapter and its bindings
  - registry and manifest rows via the proper generators, NOT by hand

FILES YOU MAY MODIFY:
  - adapter registration points

FILES YOU MUST NOT TOUCH:
  - broker/provisioning.py, broker/simforge.py, broker/certification.py, broker/packs.py
  - generators/validator.py
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            NONE — fully independent, gates nothing
BLOCKED BY:            NONE
BRANCH NAME:           feature/p-13-funnelforge
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  - THE MODULE REFUSES A NON-AUTONOMOUS TEMPLATE, inside the handler
  - THE MODULE REFUSES A NON-PASS STATE, inside the handler
  Both asserted directly. A grant-level check is not the same control and does not satisfy
  this.

COMPLIANCE / SECURITY FLAGS:
  AUTHORIZATION BOUNDARY. The single grant is only safe because the module gates.

  FunnelForge's fifteen containers PUBLISH NO HOST PORTS. Running and reachable are different
  states there — every probe must read a RESPONSE BODY, not a status code, and not the
  container being up.

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```

## P-14 — AnimaForge — the ruling, recorded

```markdown
CLAUDE CODE — PARALLEL PACKAGE AGENT

You are one of several Claude Code agents working in parallel across two repositories
(`theoffice` and `simforge`). Your job is to complete ONE work package, on your own branch,
in your own git worktree, without stepping on any other agent's work.

You are not free to touch any file in the repo. You are constrained to the files listed in
your package card. Reaching outside that scope — even for a "small fix" — corrupts the
parallel build.

If you finish early and feel the urge to help with adjacent work, STOP. Adjacent work
belongs to another agent.

YOUR PACKAGE CARD
=================
PACKAGE ID:            P-14
Title:                 AnimaForge — the ruling, recorded
Repo:                  theoffice
Tasks included:        T-024
Merge order:           15    Complexity: S

Description:
  RECORD ONLY. No build, no behavioural change.

  RULED 9 SEPTEMBER: ZERO FOR V1. No agent-facing act in the marketing plan produces video;
  everything creative is human-authored and the worker's share is distribution.

  What the entry must say:
    - This is A RULING, not an inference from silence. The previous state — zero inferred from
      what the intake does not say — was weaker than §3.4's explicit ban. THE NUMBER DID NOT
      CHANGE; THE STANDING DID, and the entry must record that.
    - REOPENING CONDITION: the day a marketing act produces generated video or creative.
    - WHAT IT DOES NOT MEAN: AnimaForge is first-wave BY FOUNDER DECISION, and V1's plan
      giving it nothing to do is A FACT ABOUT V1, not about AnimaForge. Both sit side by side;
      keep them there rather than resolving one into the other.

  If AnimaForge is ever started: its compose wants 4000, 3001, 3002, 5432 and 8001, and 5432
  IS THE OFFICE'S OWN DATABASE — it needs an override before it runs at all. Record that in
  the entry; do not fix it.

FILES YOU MAY CREATE:
  - nothing

FILES YOU MAY MODIFY:
  - docs/decisions.md   (ENTRY 29 — allocated to you by P-00; do not choose your own)

FILES YOU MUST NOT TOUCH:
  - any code file at all
  - docs/blocking.md — this is a decision, not a blocker
  - PARALLEL_BUILD.md              (coordinator only)
  - .env, .env.example             (gitignored / coordinator only)
  - tests/golden/snapshots/*       (rule 4)
  - any section of docs/blocking.md that is not yours

DEPENDS ON:            P-00
BLOCKED BY:            NONE — ruled 9 September
BRANCH NAME:           feature/p-14-animaforge-ruling
WORKTREE:              required — see rule 1

TESTS YOU MUST WRITE AND PASS BEFORE OPENING A PR:
  tests/test_docs.py passes. NO BEHAVIOURAL TEST — a ruling that produced a test would be a
  ruling that changed the code, and this one does not.

COMPLIANCE / SECURITY FLAGS:
  none

RULES OF ENGAGEMENT
===================

1. Branch and worktree discipline
   - Create a SEPARATE GIT WORKTREE for your branch. Do not `git checkout -b` in a shared
     checkout — that collides with whatever another agent has uncommitted. This happened on
     the last run and cost a recovery.
   - Branch from current main at the moment you start. The branch name is fixed.
   - Commit early and often. The branch is yours.

2. File discipline
   - If you need a file not on your allowed list — STOP. Do not modify it silently. Write
     PARALLEL_BUILD_ESCALATION.md on your branch saying what you needed and why, complete
     what you can without it, and flag the gap in your PR.
   - Config files (tsconfig, package.json, pyproject, Tailwind) are shared-file changes and
     are OFF LIMITS unless explicitly listed.

3. Dependency respect
   - If your card names a dependency, do not start until it has MERGED to main.
   - Pull latest main before you begin. Never proceed on stale main.

4. Test discipline
   - Write tests for what you produce. All must pass locally before you open a PR.
   - THE GATE IS "NO NEW FAILURES AGAINST THE RECORDED BASELINE", NOT A GREEN BOARD.
     `theoffice` main is red on Smoke alone, deliberately — V11 and V32 report NOT_RUN in CI
     where no runner can reach a live Forge. Read PARALLEL_BUILD.md for the baseline before
     you judge any failure.
   - NEVER weaken a rule to make a check pass. V11, V22, V32 and V33 are named specifically;
     the principle covers all of them. It also covers SimForge's held-out refusal and
     ADR-0049's required reason — both exist to refuse something, and a package that loosens
     either has broken it, not fixed it.
   - If a golden snapshot moves, STOP and escalate. A moved snapshot is a finding, and
     UPDATE_GOLDEN=1 is not your call.
   - If you add a migration or a rule, bump EXPECTED_SCHEMA_REVISION and every rule-count
     assertion IN THE SAME COMMIT. CI catches this; its own message tells you to.
   - Do not modify tests owned by other packages, even if they are failing.

5. Measure, do not predict
   - Never report a result you did not read. A `tail -3` on a three-command chain is a
     prediction dressed as a measurement.
   - A grep finds mentions, not construction. Read each hit before claiming what breaks.
   - Read a claim out of the schema or the receiving side, not out of the names. This plan's
     own premise was wrong twice, and both times a name was doing the reasoning.
   - Where your card asks for a prediction, write it down BEFORE you run and score it
     afterwards without editing what you wrote.

6. PR protocol
   - Open a PR against main when your tests pass. Title: `[P-NN] <package title>`
   - The description must include: the package card summary; files created and modified,
     verified against your allowed list; test results with actual counts; any escalations;
     and the exact sentence "Ready for coordinator merge".
   - Then STOP. Do not merge your own PR.

7. If the coordinator hands your PR back
   - Fix on your existing branch, push, and say it is ready for retry.
   - If the failure is clearly another package's, escalate to Ivan. Do not fix their work.

8. What you never do
   - Never merge to main yourself. Never force-push to main. Ever.
   - Never edit a file on the MUST NOT TOUCH list, "just this once".
   - Never start before a dependency has merged.
   - Never refactor a shared utility "to keep things clean".
   - Never skip tests because the change was simple.
   - Never hand-write data a generator is supposed to produce.

ACKNOWLEDGMENT REQUIRED BEFORE YOU BEGIN
========================================
Reply with:
  1. Your package ID, repo, and branch name
  2. Confirmation you have read the FILES YOU MUST NOT TOUCH list
  3. Confirmation your dependencies have merged, or your plan to wait
  4. Any clarifying question about scope

Then begin.

```
