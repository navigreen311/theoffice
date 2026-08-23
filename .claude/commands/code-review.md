---
name: code-review
description: Structured, example-driven review for architecture, correctness, security, performance, and maintainability.
---

# code-review

Review code against the standards **this codebase actually demonstrates**, not generic best practice.

## Arguments

| Argument | Meaning | Default |
|---|---|---|
| `paths` | files/dirs to review | the current diff vs. the base branch |
| `style_examples` | exemplar files defining "good here" | the exemplars in CLAUDE.md §8 |
| `severity_threshold` | `blocker` \| `major` \| `minor` \| `nit` | `minor` (report at and above) |

## Process

### 1. Learn the style from examples — do this FIRST, before reviewing anything

Read `style_examples`. If none are supplied, read the file **closest in kind** to what you are reviewing (same layer, same concern).

Then **write down the principles you derived** — naming, module boundaries, error-handling strategy, state management, dependency direction, test style, comment density.

> This step is not optional and its output is not optional. A review that judges against generic best practice instead of this codebase's demonstrated conventions produces noise. **State the derived standard before applying it.**

Note where the exemplar itself looks weak — a bad exemplar propagates into every future change and is a finding in its own right.

### 2. Review against the checklist

**Architecture** — boundaries respected? dependency direction correct? single responsibility? is this the right layer? does it fit the existing design or fight it?

**Correctness** — logic errors; off-by-one; null/undefined; unhandled error paths; race conditions; incorrect async handling; unawaited promises; **edge cases: empty, one, many, huge, malformed**; timezone and encoding assumptions.

**Security** — input validation; injection (SQL, command, template, path traversal); authn/authz on every entry point; **secrets in code, logs, or error messages**; unsafe deserialization; dependency risk; data exposure in responses and logs.

**Performance** — N+1 queries; unbounded queries or memory growth; missing indexes; sync work on a hot path; needless re-renders/re-computation; missing pagination. **Measure or reason concretely — do not speculate.**

**Maintainability** — naming; dead code; duplication that matters; **files too large to read and rewrite in one pass**; tangled dependencies; missing or misleading tests; comments explaining *what* instead of *why*.

**Consistency with the derived standard** — the step-1 output, applied.

### 3. Produce issues

Each issue:
- `file:line`
- **severity**: `blocker` (must fix before merge) / `major` / `minor` / `nit`
- **what** is wrong
- **why** it matters — a concrete failure scenario, not a principle
- **suggested patch** — actual code, not a description

Drop anything below `severity_threshold`. **Do not pad the review.** A short review of real problems beats a long one of stylistic opinions. If the code is good, say so.

### 4. Summarize by severity

### 5. Output a ready-to-paste PR comment

## Outputs

- Per-file critique at `<filename>.review.md` for each reviewed file
- Severity summary:

```
REVIEWED | <N files>
BLOCKER  | <n>
MAJOR    | <n>
MINOR    | <n>
NIT      | <n>
VERDICT  | approve | approve-with-comments | request-changes
```

- The PR comment block
- **Fact Check List** for any assumption made about runtime behaviour, versions, or external services

## Error Handling

- Cannot determine intent from the code? Say so and ask — do not guess and review against an invented intent.
- Flag anything you could not review (unreadable, out of scope, generated) rather than silently skipping it.
- Distinguish **pre-existing** issues from **introduced-by-this-change** issues. Report both; label which is which.

## Example

```
/code-review paths=src/api/expenses severity_threshold=major \
  style_examples=src/api/categories/route.ts,src/api/users/route.ts
```
