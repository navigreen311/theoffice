---
name: impl-feature
description: Plan and implement a complete feature end-to-end (design → code → tests → docs → demo) in its own branch.
---

# impl-feature

Plan and implement a complete feature end-to-end, in its own branch, to Done Criteria.

## Arguments

Parse from `$ARGUMENTS`. Any not supplied: infer where safe, otherwise label an `ASSUMPTION` and proceed.

| Argument | Meaning | Default |
|---|---|---|
| `feature_name` | kebab-case short name | **required** |
| `scope` | `ui` \| `api` \| `fullstack` \| `agent` \| `infra` | `fullstack` |
| `acceptance_criteria` | bullets or Gherkin | `ASSUMPTION` — derive from feature_name, state them, ask for confirmation only if materially ambiguous |
| `tech_constraints` | stack limits / integrations | existing stack (see CLAUDE.md §13) |
| `priority` | `p0` \| `p1` \| `p2` | `p1` |
| `perf_targets` | performance goals | none |
| `security_notes` | security / compliance notes | none |

## Process

### 1. Understand & Plan
- Restate the inputs, including anything you inferred.
- Write a **mini-PRD**: problem, users, success metrics, constraints, risks.
- Outline the **architecture**: components, data model, APIs, sequence diagram (Mermaid allowed).
- Define the **acceptance tests** — one per acceptance criterion.
- For any major choice (framework, DB, auth, caching, queue), give **2–3 options with pros/cons and a recommendation, then proceed** with the recommendation.
- Save the plan to `docs/plans/${feature_name}-PLAN.md`.
- For `p0` or architecturally significant work, `think hard` (or `ultrathink`) before writing the plan.
- **Pause here only if a genuinely blocking ambiguity remains.** Batch 3–5 questions. Otherwise continue.

### 2. Branch
- `git checkout -b ai-feature/${feature_name}`
- If several independent features are in flight, create a git worktree instead and say which commands you ran and why.

### 3. Implement
- Modify all layers required by `scope`.
- Cohesive, well-named modules; clear boundaries; files small enough to read and rewrite in one pass.
- Match the style of the exemplar files named in CLAUDE.md §8.
- Atomic Conventional Commits as you go — not one commit at the end.

### 4. Tests
- Create or extend **unit + integration** tests, one-to-one with the acceptance criteria.
- Run them. They must pass.
- Record the **exact command**.

### 5. Verify
- Build and run the app. Perform local smoke tests.
- Write a short **demo script**: exact commands + URLs a human can follow.

### 6. Docs
- Update `README.md`.
- Add `docs/${feature_name}.md` — overview, architecture, endpoints, env vars.
- Add a CHANGELOG entry under added / changed / removed.

### 7. Automation artifact
If setup, migration, or verification takes more than one command, ship a **single idempotent script** (or npm script / Make target) that runs it all. Re-running it must be safe.

## Output Requirements

Branch `ai-feature/${feature_name}` containing code, tests, and docs, plus a closing block:

```
IMPLEMENTED | <what was built, by layer>
TESTED      | <command> → <N passed / N failed> | coverage: <if known>
HOW TO RUN  | <exact commands + URLs>
```

Then:
- **PR-style summary** — what, why, how, tests, risks
- **Fact Check List** — assumptions that would break this if wrong (security, versions, limits, cost-sensitive services)
- **Every `ASSUMPTION`** listed, with how to change it later
- **Open follow-ups**

## Error Handling

- On failure: show the actual logs, diagnose, propose a fix, retry. Do not report success over a failing gate.
- If a gate cannot be satisfied, say which one and why — never silently skip it.
- Missing info → smallest reasonable `ASSUMPTION`, labelled, proceed.

## Example

```
/impl-feature feature_name=expense-export scope=fullstack priority=p1 \
  acceptance_criteria="- User can export filtered expenses to CSV and JSON
                       - Export respects active filters
                       - Files download with a dated filename" \
  perf_targets="export of 10k rows in under 2s"
```
