---
name: test-suite
description: Create or extend an automated test suite (unit, integration, e2e) and optionally wire it into CI.
---

# test-suite

Build or extend the automated test suite so the agent can close its own feedback loop.

## Arguments

| Argument | Meaning | Default |
|---|---|---|
| `target` | path, module, or feature to cover | whole repo |
| `coverage_goal` | e.g. `80%` lines, or `all acceptance criteria` | `all acceptance criteria covered` |
| `test_kinds` | `unit` \| `integration` \| `e2e` (comma-separated) | `unit,integration` |
| `ci_provider` | `github-actions` \| `gitlab-ci` \| `none` | `none` |
| `seed_data` | fixture/seed strategy | in-test factories |

## Process

### 1. Inventory
List what tests exist today: framework, location, naming convention, how they run, current pass/fail state, current coverage if measurable. **Report the real state, including failures.**

### 2. Identify gaps
Map `target` against the inventory. Name explicitly what is untested:
- untested branches and error paths
- untested integration seams (DB, HTTP, queue, filesystem, third-party)
- acceptance criteria with no corresponding test
- known-fragile areas

Rank by risk. Say what you are **not** covering and why.

### 3. Add tests
- Follow the existing test conventions exactly — they are the specification. If none exist, choose the idiomatic framework for the stack and say so as an `ASSUMPTION`.
- **Unit:** pure logic, isolated, fast.
- **Integration:** real seams — actual DB, actual HTTP layer. Prefer real dependencies over mocks where feasible; mock only what is slow, external, or non-deterministic.
- **E2E:** critical user journeys only. E2E is expensive; keep it thin and high-value.
- Every test must be able to fail for the right reason. No assertion-free tests. No `expect(true).toBe(true)`.

### 4. Fixtures & teardown
- Deterministic setup, guaranteed teardown, isolated state.
- No inter-test order dependencies. No shared mutable global state.
- Seed data per `seed_data`.

### 5. Scripts
Wire idiomatic scripts into the project manifest: `test`, `test:unit`, `test:integration`, `test:e2e`, `test:watch`, `test:coverage`. **This is the Output Automater obligation — one command must run everything.**

### 6. CI (if `ci_provider` is not `none`)
Generate the workflow: install → lint → type check → build → test → publish coverage. Cache dependencies. Fail the build on test failure or coverage regression. Never put a secret in the workflow file — reference the provider's secret store and document which secrets are needed.

### 7. Run & summarize
Actually run the suite and report real numbers.

## Outputs

- New/updated test files
- Updated scripts in the project manifest
- CI config (if requested)
- Coverage report path

Closing block:

```
TESTS     | <N added> across <unit/integration/e2e>
RESULT    | <command> → <N passed / N failed / N skipped>
COVERAGE  | <before> → <after>   (report path: <path>)
GAPS      | <what remains untested and why>
```

Plus a **Fact Check List** for anything version- or environment-sensitive.

## Error Handling

- Failing tests are the finding, not an obstacle. Report them with logs.
- **Never** make a test pass by weakening its assertion, deleting it, or adding a blanket skip. If a test must be skipped, say so explicitly with the reason and a follow-up.
- Distinguish clearly: pre-existing failure vs. failure this change introduced.

## Example

```
/test-suite target=src/services/billing coverage_goal=85% \
  test_kinds=unit,integration ci_provider=github-actions
```
