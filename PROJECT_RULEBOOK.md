# PROJECT RULEBOOK — v1.1

**Sources:**
- **Methodology** — "Claude Code: Software Engineering with Generative AI Agents", Docs 1 & 2 (95 pp).
- **Operating Contract** — "Elite Software Engineer, Workflow Designer, and Coach" (5 pp). See **Part XIII**.

**Status:** GOVERNING. This rulebook governs every decision for the rest of the build — architecture, tooling, process, and how we work together. Where a rule here conflicts with a default habit, the rule wins.

**Precedence:** Part XIII (Operating Contract) is the **binding behavioral contract** and supplies concrete values where the methodology gave only principles. Parts 0–XII supply the *why* and the deeper technique. **Where they overlap, Part XIII's specifics win; where Part XIII is silent, Parts 0–XII govern.** Neither overrides PD-1 or PD-2.

**Amendment:** Rules change by explicit decision, recorded here with the reason. Not by drift.

**v1.1 changelog:** Added Part XIII (Operating Contract). Amended Rules 5.8, 6.3, 6.4; Part XI artifact list; Part XII gap list.

---

# PART 0 — THE TWO PRIME DIRECTIVES

Everything in this document descends from these two rules. If you remember nothing else, remember these.

### PD-1 — Operate as the CEO of a software organization, not a developer at a keyboard.

The human owns: critical thinking, requirements, architecture, design judgment, evaluation, taste.
The agent owns: production at scale.

**The failure mode this prevents:** the human becomes the bottleneck in a micromanagement loop — approve, assign next tiny task, approve, assign next tiny task — capping throughput at human clock speed and forfeiting the only property that actually matters, *the agent's ability to scale*.

### PD-2 — Program the process, not the code.

> When the agent produces something wrong, the reflex is to fix the code. **That reflex is the enemy.**

You are a programmer whose runtime is AI labor. Your program is written in `CLAUDE.md` and `.claude/commands/`. Hand-editing output fixes one instance and teaches the system nothing; it caps scalability permanently.

**The standing question, every single time output disappoints:**

> *"What could I change in `CLAUDE.md` or in a command so that I don't have to fix this next time?"*

**The mandated response sequence to any bad output:**

1. **Prompt the agent to fix it** — do this first, deliberately. Watching *what you had to say* to make it see the error is the diagnostic that reveals the missing context.
2. **Then encode that** into `CLAUDE.md` (if global) or the relevant command (if task-scoped): more specificity, another instruction, a pointer to an exemplar, the missing context.
3. **Only then, if necessary,** touch the code by hand.

**The sorting analogy (memorize this):** you would never write a sort routine that stops every 10th number to ask a human whether it's right. You would write it correctly, add guardrails, test it, and refine it until it sorts autonomously. That is the relationship you are building with your AI labor.

**Corollary — time spent editing `CLAUDE.md` and commands is the highest-leverage time in the project.** It compounds. Time spent hand-editing generated code does not.

---

# PART I — THE PROMPT SCALE LAW

**Rule 1.1 — The scale at which you prompt directly caps the scale of software you can build.** Small prompts produce small software. This is the governing constraint, not a style preference.

**Rule 1.2 — Default to the Big Prompt.** Describe the *vision and outcome*, not the files. Let the agent derive requirements, plan, decompose, and build.

**Rule 1.3 — Know which tier you are operating in:**

| Tier | Prompt shape | Gain |
|---|---|---|
| Micromanagement | "Create `components/expense_list.tsx` with functions to display and store data" | 1x (human-bound) |
| Code generation / vibe coding | "In expense_list, add a function to sort by time and update state" | 5–10x |
| **Vision-level / AI-as-labor** | "Act like the typical user of this application, then create different ways of sorting, filtering and displaying the expenses that are incredibly powerful and useful" | **1000x** |

**Rule 1.4 — Tier 2 is legitimate but is not the target.** Do not settle there because it feels safer.

**Rule 1.5 — The zoom-out test.** Before sending: *am I specifying the world, or specifying the bricks?* If bricks, zoom out to outcomes, users, and problems.

**Rule 1.6 — Simulate the user to derive requirements.** "Act like the typical user of this application, then…" is a first-class technique whenever requirements are underspecified.

**Rule 1.7 — Segment giant prompts into testable increments.** A monolithic mega-prompt mires the agent in detail:

> "This is a lot to do at once. Let's break this plan up into a series of incremental steps. **We want each step to end in a testable state and a commit.** You choose how many increments."

**Rule 1.8 — The hybrid pattern (default for real builds).** Commit the full requirements/design as a document in the repo. Feed steps one at a time with the standing instruction:

> "If you have any questions about the right way to do things, or there are multiple different ways you could do it, read the design document to figure out the way that's most appropriate given the design and where we're going."

---

# PART II — THE LIFECYCLE: CHAT → CRAFT → SCALE

Do not skip phases. Do not start at Craft.

## II.A — CHAT (design in conversation, before any code exists)

Purpose: spur **your own** critical thinking, expose design dimensions, kill bad designs while they are still free.

**The Chat sequence:**

1. **Requirements generation** — "Design the requirements for X. Come up with an initial set." Harvest dimensions you would not have thought of.
2. **Gap analysis** — "Here are our core requirements. What are we missing? What is complementary and would fit that we haven't put down?"
3. **Requirements subtraction** — decide *which of these do I NOT care about, and why*. Deciding what is out is design work.
4. **N-way design** — "Propose 3 designs based on different structures. 10 routes or less." Constrain size so it fits in your head.
5. **Averageness check** — "Which of these is most standard? What is most average?" Average is often correct: conventional designs are navigated faster and with fewer errors by other developers *and by the agent* (see Rule 3.4 — standard naming is what it was trained on). Choose innovative deliberately, never accidentally.
6. **Hole-poking (mandatory)** — "With this design, what use cases would be hard to support? What friction might it cause? Poke some holes in it."
7. **Persona-pattern prototyping (mandatory — see II.B).**
8. **Ergonomics pass** — "Design 3 different fluent clients for this API. Only show me the interface usage through examples."
9. **Prompt crafting** — "I like version 1. Now write a complete prompt I can cut and paste into Claude Code to get it to implement this."
10. **Increment split** — apply Rule 1.7.

## II.B — THE PERSONA PATTERN ("super mock") — MANDATORY BEFORE COMMITTING TO ANY INTERFACE

> "Act as this API and pretend to be this API — basically act as the implementation of the server. I will type in pseudo-HTTP requests and you will respond with an HTTP response like the server would. Show me some sample HTTP requests I can send you."

Then actually exercise it: create a resource, fetch it, fetch its logs, hit the edge cases.

**Why mandatory:** interface flaws normally surface only *after* you build and try to use the thing. This surfaces them in minutes at zero cost. It is contextually-correct mocking — it carries state and semantics forward across the simulated session, which no hand-written mock does.

**Generalization:** the super-mock works for anything exercisable through text — CLIs, protocols, state machines, screen-by-screen UX walkthroughs.

## II.C — CRAFT (implementation judgment)

The decisions the agent must not make silently: libraries, folder structure, configuration, deployment, conventions, package organization, type safety, logging, test framework.

**Rule 2.1 — Explore the option space first.** "Let's think of library options for this step. Let's also think of detailed implementation details, coding conventions, package structure, and other things we need to decide now."

**Rule 2.2 — Choose cohesive configurations, not à-la-carte picks.** "Propose 3 different configurations and discuss the pros and cons. Would any of these details influence our architectural choices?"

**Rule 2.3 — Ergonomics are load-bearing, not aesthetic.** An interface that would annoy a human *measurably degrades agent output*: error-prone interfaces produce more agent errors; verbose interfaces cost more time and tokens.

**Rule 2.4 — Craft is where the human spends the time freed by Big Prompts.** You craft **constraints, style, and guidelines** — not lines.

## II.D — THINK BEFORE ACTING (gate on every non-trivial change)

**Rule 2.5 — Plan first, code second.** *It is MUCH faster to point out a mistake in the plan and have it fix the plan than to undo poor implementation decisions made on the fly.*

**Rule 2.6 — Extended thinking levels, escalate deliberately:**

| Trigger phrase | Use for |
|---|---|
| `think` | straightforward problems |
| `think hard` | moderate complexity |
| `think harder` | complex scenarios requiring comprehensive evaluation |
| `ultrathink` | maximum budget — highly complex problems |

**Rule 2.7 — Persist the plan to a file.** `FEATURE_PLAN.md`, `INTEGRATION_DESIGN.md`, or similar. Then: review it offline, **edit it to add constraints and requirements**, and only then give the go-ahead to implement. This creates a paper trail of design decisions so the reasoning does not get lost in the code, and serves debugging and onboarding later.

## II.E — SCALE

See Part VI (version control, worktrees, subagents) and Part VII (Best-of-N).

---

# PART III — DESIGN FOR AI LABOR (token limits are an architectural constraint)

**Rule 3.1 — Token limits are a first-class design force.** The agent cannot dump the whole codebase into the model. It works through a moving *window*, discovering which files matter — exactly as a human does, but bounded hard by:
- **Input token limit** — big software exceeds it; it must explore rather than ingest.
- **Output token limit** — a file too large to rewrite in one pass forces the agent to loop (write half, come back for the rest), adding time, cost, and error surface.

**Rule 3.2 — Therefore, classic good design is now a performance requirement, not a virtue.** Modularity, single responsibility, isolation, limited blast radius, no ripple effects, untangled dependencies — these were always good; now they directly determine how fast and how correctly AI labor can work.

**Rule 3.3 — The difficulty gradient (design toward the top):**

| Change shape | Difficulty |
|---|---|
| One obvious file, fits comfortably in the token window | **Easy** |
| Giant file, changes scattered across it, changes must be mutually cohesive | Hard |
| Thousands of files, or complex cross-file dependencies requiring simultaneous reasoning | **Very hard / may fail** |

**Rule 3.4 — Project structure is rich, extremely token-efficient context.** The agent sees directory names and file names first and explores top-down. A directory tree using conventional names (`store/`, `slices/`, `reducers/`, `actions/`) instantly communicates "Redux client-side state management" — a fact that would cost far more tokens to state in prose, and that a vague structure cannot communicate at all. File extensions reveal language; `serverless.yaml` reveals deployment model.

**Rule 3.5 — Use standard, boring, conventional naming and layout.** Standard practice is what the model was trained on. Kooky custom structures force you to spend `CLAUDE.md` tokens documenting what a conventional layout would have conveyed for free — and make every prompt less token-efficient.

**Rule 3.6 — Structure must mirror the vocabulary of your prompts.** If you will say "change the expense dashboard," there should be an obvious `expense-dashboard/`. If that feature is instead smeared across ten components in different folders under non-standard names, every prompt pays a discovery tax. **Name things the way you will ask for them.**

**Rule 3.7 — Design explicitly for long-term AI maintainability.** Instruct the agent to write code that stays scalable for AI labor to work on. This is a stated requirement of the codebase, not an emergent property.

---

# PART IV — THE CONTEXT SYSTEM

## IV.A — Context theory

**Rule 4.1 — The archery model.** Instructions aim; **context shrinks the target.** "Write an app for tracking expenses" = enormous target. "Write a Next.js web app that uses NextUI for tracking expenses" = tight target. **Ambiguous output is always a diagnosis of missing context.**

**Rule 4.2 — Context is a balance, not a maximum.** Over-constrain and the agent cannot innovate inside the boundary and will miss the valuable thing it would have found. Choose target size per task: wide for discovery, tight for conformance.

**Rule 4.3 — Invoke named principles; they are token-efficient instruction.** One word — **SOLID** — expands into a large body of design sensibility already in training data. Hunt for the compressed name rather than hand-writing a hundred bespoke rules. *Verified in Doc 1: SOLID is not the default style, and adding it to `CLAUDE.md` visibly changed both the agent's stated plan and the generated code.*

**Rule 4.4 — Right context, right time.** Handing a new hire a 400-page manual for a one-page task makes them tire and miss the important part; irrelevant content drowns the signal. Same for the agent. **Global → `CLAUDE.md`. Task-scoped → commands.**

**Rule 4.5 — The agent is a new team member being onboarded.** Everything a human hire needs — codebase roadmap, conventions, rules, process, architectural decisions, feedback — the agent needs, in writing. Onboarding effort is not overhead; it is the work.

## IV.B — `CLAUDE.md` — persistent, global, every-prompt context

Seeded by `/init` (the agent explores the codebase and documents it), **then hand-edited.** `/init` output is a starting point, never the finished article.

**The CONTEXT framework — required section coverage:**
- **C**lear and Concise Instructions
- **O**perational Processes
- **N**aming and Standards
- **T**esting and Quality Gates
- **E**xamples and References
- **X**pectations and Boundaries
- **T**ools and Dependencies

**Three core principles:**
1. **Essential information only** — global truths applying to *every* task.
2. **Specificity creates better targets** — "write solid code" is vague; "follow SOLID design principles for all object-oriented code" is actionable.
3. **Process over micromanagement** — define workflows and checks, not implementation details.

**DO:** ✅ clear actionable language · ✅ specific tools and frameworks · ✅ quality gates and testing requirements · ✅ workflow processes including version control · ✅ naming conventions · ✅ established design principles by name

**DON'T:** ❌ task-specific detail that only applies sometimes · ❌ 1000-page documentation dumps · ❌ vague instructions like "write good code" · ❌ omitting version-control workflow · ❌ micromanaging implementation details · ❌ temporary or changing information

**Emphasis is a legitimate device:**
> `IMPORTANT!!! : DO THIS FOR ALL CODE.` Whenever you write code, it MUST follow the SOLID design principles. Never write code that violates these principles. If you do, you will be asked to refactor it.

**Rule 4.6 — `CLAUDE.md` is steering, not a guarantee.** It improves the odds of hitting the target; it does not eliminate misses. Verification (Part V) remains mandatory.

**Rule 4.7 — The three things that MUST be in `CLAUDE.md` from day one** (the doc's own "ground rules"):
1. **Version control process** — "Before you make any change, create and check out a feature branch named `<template>`. Make and then commit your changes in this branch." *(Doc 2: this is the single most important thing to set up first.)*
2. **When you build new code, write tests for it.** Name the testing libraries, or point to where the testing conventions live.
3. **Before you commit, run the tests and make sure they pass.** (Compilation is implicit in running tests.)

Without these ground rules explicitly stated, the agent will not reliably do them.

## IV.C — Commands — `.claude/commands/*.md` — targeted, repeatable, task-scoped

**The TARGETED framework for command design:**
- **T**ask-Specific Instructions
- **A**rguments and Placeholders
- **R**eusable Process Steps
- **G**uided Examples and References
- **E**xplicit Output Requirements
- **T**emplate-Based Naming
- **E**rror Handling and Edge Cases
- **D**ocumentation and Context

**Three core principles:**
1. **Right context at the right time** — solves the 400-page-manual problem.
2. **Reusable consistency** — the same high-quality process every time, scaling your best practices across your AI labor.
3. **Template-driven automation** — placeholders keep commands flexible while enforcing structure and naming.

**Location:** `.claude/commands/` (project, version-controlled) · `~/.claude/commands/` (global, cross-project generic only).

**Rule 4.8 — Anything done more than once becomes a command.**

**Rule 4.9 — A command carries three payloads, not one:** *reusable prompt* + *targeted context* + *injected process* (explicit order of operations). Doc 2's worked example proves the agent follows an injected read-then-analyze-then-write sequence and honors templated output naming exactly.

**Rule 4.10 — Template the output.** "Output it to `[filename].review.md` for each file that you review." The agent fills templates intelligently rather than literally. Use this to bound naming, artifact location, and result reuse.

**Rule 4.11 — Ground every conformance task in exemplars.** Canonical shape:

> "Carefully perform a code review of `$ARGUMENTS`.
> Examples of excellent code that you should try to match the design / style / conventions of are: `<path>`, `<path>`.
> First, read the file that is closest to whatever code you are evaluating, then identify its core design, style, coding and other principles.
> Then create a detailed critique of the code based on these principles and output it to `[filename].review.md` for each file that you review."

Note the shape: **derive the standard from the codebase itself, then judge against the derived standard.**

**Rule 4.12 — Specialize commands by scope.** Different exemplars for different parts of the system: front-end review vs. back-end review. One generic command that points at one file is a weaker teacher than several targeted ones. *(Doc 2 flags "I probably should have had multiple files here" as its own mistake — give each command several exemplars.)*

**Rule 4.13 — Organization strategy — pick one and hold it:**
- **By function:** `plan-feature.md`, `impl-api.md`, `test-unit.md`, `deploy-prod.md`
- **By domain:** `auth-login.md`, `user-profile.md`, `payment-process.md`
- **By role:** `dev-review.md`, `qa-automation.md`, `ops-deploy.md`, `pm-requirements.md`

**Rule 4.14 — Commands are code. Govern them as code.**
- Version-controlled in `.claude/commands/` for team sharing
- Descriptive commit messages when updating them
- **Command changes are reviewed as part of code review**
- Reviewed and updated regularly based on feedback
- **Archive outdated commands rather than deleting them**
- Document command changes in the project changelog

**Rule 4.15 — Ask the agent to propose its own commands.** Have it examine the project and dream up which commands and prompts would be valuable here. It knows the repetitive surfaces.

## IV.D — TEACHING BY EXAMPLE (the most information-dense channel)

**Rule 4.16 — Examples outperform instructions.** Doc 2's demonstration: given only an excerpt of epic verse and "write in the same style," the model produced Homeric prose about Nashville — *then* Homeric-styled Python — *then*, in a **fresh conversation with no explanation of the style**, correctly inferred the conventions from the code alone and wrote a sorting algorithm matching them. It named the conventions it detected unprompted ("epic invocations as function names, nested functions representing the hero's journey").

Writing that style out as a rule list would be enormous. The example was free.

**Rule 4.17 — THE CODEBASE IS THE PRIMARY TEACHER, WHETHER YOU INTEND IT OR NOT.** The agent reads existing code and follows what it sees. This is the single most consequential consequence of Rule 4.16:

> **Bad code in the repo actively trains the agent to write more bad code.**

**Rule 4.18 — Therefore: when code does not reflect the style, architecture, and principles we want, refactoring it is not cleanup — it is repairing the training signal.** Fix exemplars with priority.

**Rule 4.19 — Nominate exemplars explicitly.** Maintain a known set of "this is what good looks like here" files, named in `CLAUDE.md` and in the relevant commands. Keep them genuinely excellent.

**Rule 4.20 — Teach commit style by example too.** "Read the git log, learn the style of the commit messages there, and write new ones in that style." The agent writes excellent, detailed commit messages when asked — better than time-pressured humans typically do.

---

# PART V — FEEDBACK LOOPS & QUALITY GATES

**Rule 5.1 — Software engineering is a search process, and search requires feedback.** Make a change → compile → run tests → interact → judge → keep or iterate. **Every rule here exists to close that loop without a human in it.**

**Rule 5.2 — The agent will not seek feedback unless instructed.** It does not get tired, but it is somewhat random. If not told to compile, test, and run, it may simply not. Encode this in `CLAUDE.md` (Rule 4.7).

**Rule 5.3 — THE STANDING LOOP (non-negotiable, in `CLAUDE.md`):**

> Work in a feature branch → write the code → **write tests for it** → **run the tests** → **make them pass** → *then* commit.

Everything before "commit" happens without human involvement. The purpose is stated bluntly in the source: *make sure Claude Code sends as few errors as possible over to the human side.* Human time is the scarce resource and must be protected.

**Rule 5.4 — "Hands, eyes and ears" is a *fallback*, and every instance is a defect in the automation.** Sometimes you must be the agent's senses — clicking through a UI it cannot drive, spotting a visual problem it cannot see, judging aesthetics it cannot know. Accept it when needed. **But treat every occurrence as a signal:**

> *"How do I make this something the agent can do programmatically?"* — UI test scripting, browser automation, integration harnesses.

The more you are its senses, the more coupled it is to you, and **the more you are the bottleneck** (PD-1).

**Rule 5.5 — When you do give feedback, ENRICH IT.** Never paste a bare error. Supply the trigger and the circumstances:

> ✅ "Clicking add expense creates this error: `<paste>`"
> ❌ `<paste>`

The raw error is the symptom; *what you did to cause it* is the context that makes it diagnosable.

**Rule 5.6 — Never respond to an agent error by abandoning the tool or by silently hand-fixing.** Complete the cycle: give it the context it lacked, let it learn and fix. Then apply PD-2 — encode the lesson.

**Rule 5.7 — Build the feedback infrastructure early.** Tests, linters, type checks, build commands, integration harnesses, UI automation. **Then document all of them in `CLAUDE.md`** so the agent knows the tools exist and is expected to use them. Undocumented tooling is tooling the agent will not use.

**Rule 5.8 — DEFINITION OF DONE** *(amended v1.1 — merged with Operating Contract §Done Criteria)*

A unit of work is done only when **all** of the following hold:
- [ ] Done on its own branch, named `ai-feature/<slug>`
- [ ] Code compiles
- [ ] Unit **and** integration tests written, aligned to the acceptance criteria
- [ ] Tests run and passing, with the **exact command(s) to run them** stated
- [ ] Built/run and **concrete local demo steps documented** (commands + URLs)
- [ ] Committed in atomic Conventional Commits
- [ ] `README.md` updated · `docs/<feature>.md` added (overview, architecture, endpoints, env vars) · CHANGELOG entry (added/changed/removed)
- [ ] **PR-style summary ready** — what, why, how, tests, risks
- [ ] **Fact Check List appended** for any high-risk assumption (Rule 13.7)
- [ ] Any `ASSUMPTION` made is labelled, listed, and paired with how to change it later
- [ ] Any human-detected defect encoded back into `CLAUDE.md` or a command (PD-2)

**Nothing is reported as done with a box unchecked.** If one is skipped, say which and why.

---

# PART VI — VERSION CONTROL & PARALLELISM

## VI.A — Version control (the first thing configured, always)

**Rule 6.1 — Version control is the safety net that makes fearless AI labor possible.** It is how mistakes are isolated, located, and undone. Without it, scaled AI labor produces a mess very quickly.

**Rule 6.2 — Branch before any change, always.** Standing `CLAUDE.md` instruction: *"Before you make any change, create and check out a feature branch named `<template>`. Make and then commit your changes in this branch."* The agent infers "this is a feature" without being told.

**Rule 6.3 — THE BRANCH TEMPLATE IS `ai-feature/<slug>`, slug in kebab-case.** *(fixed v1.1 by the Operating Contract — no longer an open choice)* Consistency will not emerge on its own; the agent will not infer conventions from existing branch names unless told to.

**Rule 6.4 — The `ai-feature/` prefix is the human/AI provenance marker.** Doc 2 names this as the improvement over its own example: **you must be able to tell human branches from AI branches at a glance.** The Operating Contract supplies the concrete form.

**Rule 6.4a — Commit messages follow Conventional Commits** (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`), atomic, early and often. This supersedes "learn the style from the log" (Rule 4.20) as the *format* authority; Rule 4.20 still governs tone and detail level.

**Rule 6.5 — Cheap discard is a feature, use it.** Don't like the result? Throw the branch away. No harm, no foul, back where you started.

**Rule 6.6 — Merge and cherry-pick across branches deliberately.** The agent can combine work from different branches. This is what makes Best-of-N harvesting (Rule 7.6) actually work.

**Rule 6.7 — Delegate commit messages to the agent.** It writes detailed messages that time-pressured humans usually don't. Teach the style from the log (Rule 4.20).

**Rule 6.8 — Apply big-team version-control discipline.** The practices that let large human teams scale are the same practices that let AI labor scale, for the same reasons.

## VI.B — Git worktrees (parallel isolation)

**Rule 6.9 — Use worktrees to run multiple agents simultaneously without conflict.** Traditional: one working directory, switch branches. Worktree: **multiple working directories, each on its own branch, sharing one git history.**

```
/project/                # main worktree (main)
/project-export/         # feature/data-export
/project-analytics/      # feature/analytics-dashboard
```

Each is a complete, independent environment. Changes in one cannot affect another; each is independently testable.

**Rule 6.10 — Manual worktree protocol:** create worktrees → open a terminal per worktree → launch an agent in each → develop in parallel.

**Rule 6.11 — Integration protocol (follow exactly):**
1. All features committed and working in their branches
2. **Stop the agent in every worktree terminal** — *so that you don't confuse yourself*
3. Return to the main project directory on the original branch
4. Run a single agent there to handle merge + worktree cleanup
5. **Test the application to ensure everything works together** — integration is not merge

**Rule 6.12 — Both sides of the workflow become commands:** `parallel-work.md` and `integrate-parallel-work.md`, invoked as e.g. `/integrate-parallel-work budget-tracking notifications user-settings`.

## VI.C — Subagents & Tasks

**Rule 6.13 — What subagents buy you:**
- **Independent context windows** — each has its own, preventing information overflow
- **Parallel execution** — several work simultaneously on different aspects
- **Specialized focus** — each concentrates on one domain

**Rule 6.14 — Use subagents to explore large codebases.** Fan out several in parallel across architectural layers rather than exhausting one context window. Ideal for initial project assessment and understanding multiple components quickly.

**Rule 6.15 — Separate by domain, not by arbitrary slice** — backend vs. frontend, layer vs. layer. Each returns specialized recommendations from its own deep read.

**Rule 6.16 — Full autonomous parallelism: one session orchestrating worktrees + subagents.** A single agent session sets up the worktrees, prepares them, and spawns subtasks to build a feature in each.

> **⚠ Critical operational precondition:** this requires the correct directory structure **and running the agent from the PARENT directory** — not the project directory as in every other workflow. Getting this wrong is the usual failure. Encode it in the command's own documentation.

**Rule 6.17 — `parallel-agents.md` is a required command.** It is the most reliable way to run this, and it works best when given the specific folder to operate on.

---

# PART VII — BEST-OF-N & EVALUATION

## VII.A — Search

**Rule 7.1 — Never solve a significant problem once.** Solve it 3, 5, or 10 times in different directions, then evaluate.

**Rule 7.2 — Each attempt on its own branch (or worktree).** This is what makes throwaway cheap and harvesting possible.

**Rule 7.3 — The divergence prompt:**
> "That was awesome. Can you go back to the prior branch and repeat this process, but solve the underlying problem in a different and wildly valuable way? Surprise me with your creativity."

**Rule 7.4 — Exploit egolessness.** It does not burn out, resent rework, or anchor on its previous attempt. Discarding 20 minutes of its work is routine and costs ~nothing. **Discarding an entire implementation is a normal outcome, not a failure.**

**Rule 7.5 — Economics.** Work worth thousands of dollars of human labor costs single-digit dollars in tokens. **Cost is never the reason to skip exploration.**

**Rule 7.6 — Harvest, do not just pick.** Round outcomes are: (a) adopt one, (b) discard all and re-diverge, (c) **cherry-pick the good parts of the losers into the winner** — often the highest-value outcome.

**Rule 7.7 — Pre-screen with a rubric when N is large**, so human attention lands on the top 3–4.

**Rule 7.8 — Variability is the search engine, not a defect.**

## VII.B — Evaluation

**Rule 7.9 — Your ability to produce quality is bounded by your ability to recognize quality.** Evaluation is the human's core retained competency.

**Rule 7.10 — The agent can genuinely evaluate code**, including human-level judgments (flexibility, maintainability) with defensible rationale — *given a rubric and sufficient context*.

**Rule 7.11 — Rubric-first.** Generate weighted dimensions with per-dimension scoring criteria. Doc 1's generated set: functionality, error handling, code quality, flexibility, performance, documentation, security, maintainability, line efficiency, best practices.

**Rule 7.12 — CONTEXT DOMINATES THE VERDICT.** Worked example: with no context, try/except wrapping scored 5/5 for error handling and won. Once told *"this is historical logging, we must capture everything, project best practice is to always throw exceptions, timing is critical"* — the **same code** scored 1/5 and the other solution won on both error handling *and* flexibility.

> **A context-free code judgment is not merely weak. It is actively misleading. Never accept one.**

**Rule 7.13 — `my-evaluation-template.md` is a required artifact.** Encode what matters for *this* project. Instruct the agent to read and apply it for every Best-of-N comparison. Do not rely on default criteria.

**Rule 7.14 — Output format: table, all candidates, per-dimension winner AND why.** Transpose if unreadable. **The rationale is the deliverable — a score without a reason is unusable.**

**Rule 7.15 — Produce `code-analysis.md` before choosing.** Have the agent walk every branch, covering technical architecture, code organization, libraries used, and implementation patterns per version. Then read it to answer one question: **did we actually explore different solution spaces, or just variations of the same basic approach?** If the latter, the round failed — re-diverge harder.

**Rule 7.16 — Self-critique loop.** Have it critique and refactor its own code against contextually-relevant dimensions to close the drift-from-standards gap.

**Rule 7.17 — Higher quality is the goal, not speed. If all we got was speed, the methodology failed.**

---

# PART VIII — MULTIMODAL PROMPTING

**Rule 8.1 — When something is easier to show than to tell, SHOW IT.** Napkin sketches, whiteboard photos, screenshots, mockups, diagrams, GIFs — drag them straight into the prompt. Doc 2's premise: a coffee-stained napkin sketch converts directly to production code.

**Rule 8.2 — Reach for an image by default in these categories:**

| Category | Why text loses |
|---|---|
| **Spatial layout / relative positioning** | prose is verbose and misread |
| **Color, gradients, shadows, visual hierarchy** | nearly impossible to describe precisely |
| **Responsive behavior** | show mobile + desktop side by side |
| **Chart types and styling** | many subtle simultaneous decisions |
| **Dashboard layouts** | complex multi-element arrangement |
| **User flows / multi-step processes** | branching state is not linear prose |
| **Animation and transitions** | motion and timing are inherently visual |
| **Visual bug reports** | a screenshot beats any description |
| **Empty and loading states** | specific messaging + layout |
| **System architecture** | data flow and component relationships are spatial |
| **Database schema / ERDs** | relationships are inherently visual |
| **Decision trees / conditional business logic** | nested if/then is far clearer as a flowchart |
| **Approval and workflow diagrams** | multiple actors, decision points, parallel flows |
| **Performance profiles** | DevTools output — paste the profile |
| **Network topology / infrastructure** | spatial |

**Rule 8.3 — The prompt is short when the image is good.** "Implement this layout exactly as shown." "Match these exact colors and visual treatment." "Fix what's wrong in this screenshot." "Implement this user flow." "Create this database schema."

**Rule 8.4 — Capture ephemeral design artifacts immediately.** Photograph the whiteboard before it is erased, and have the agent build **multiple versions** of the ideas (Rule 7.1) while the team is on break. Return to working prototypes to evaluate rather than to notes.

**Rule 8.5 — Visual is superior for handoffs, bug reports, stakeholder communication, code review before/afters, and documentation.**

---

# PART IX — ANTI-PATTERNS (hard prohibitions)

| # | Anti-pattern | Why it is banned |
|---|---|---|
| **A1** | **Hand-editing generated code instead of improving `CLAUDE.md`/commands** | **Violates PD-2. Fixes one instance, teaches the system nothing, permanently caps scalability.** |
| A2 | Micromanagement prompting (file-by-file, function-by-function) | Human becomes the bottleneck; forfeits scaling |
| A3 | Being the approval bottleneck in a tight per-change loop | Caps throughput at human clock speed |
| A4 | Solving a significant problem exactly once | Forfeits search; you never learn what else was possible |
| A5 | Stopping at "wow, that looks good" | The moment after success is the moment to diverge |
| A6 | Skipping Chat and jumping to code | Guarantees expensive rework on a flawed design |
| A7 | Committing to an interface without persona-pattern testing | Holes surface after implementation instead of before |
| A8 | Implementing before planning on non-trivial work | Fixing a plan is far cheaper than undoing an implementation |
| A9 | Context-free code evaluation | Verdicts invert under real context — actively misleading (7.12) |
| A10 | 1000-page `CLAUDE.md` / dumping all context always | Drowns the signal; agent latches onto irrelevancies |
| A11 | Task-specific or temporary content in `CLAUDE.md` | Wrong artifact — belongs in a command |
| A12 | Vague instructions ("write good code") | Enormous target; ambiguous output guaranteed |
| A13 | Hand-writing 100 rules where a named principle exists | Token-wasteful and weaker than the compressed name |
| A14 | Retyping long prompts instead of building a command | Loses versioning, sharing, and compounding improvement |
| A15 | Accepting `/init` output as final | It is a documentation exercise, not institutional knowledge |
| A16 | **Leaving bad code in the repo** | **It is training data — it actively teaches the agent to write more of it (4.17)** |
| A17 | Non-standard / "kooky" naming and folder structures | Destroys free structural context; forces expensive prose documentation |
| A18 | Giant files and tangled cross-file dependencies | Collides with input/output token limits; forces looping; may fail outright |
| A19 | Letting the agent commit without tests run and passing | Sends errors to the human side; wastes the scarce resource |
| A20 | Assuming the agent verified its work | It frequently skips compile/run checks unless told |
| A21 | Habitually acting as the agent's hands/eyes/ears | Each instance is an automation defect and a coupling to you |
| A22 | Pasting a bare error with no trigger context | Symptom without circumstances is hard to diagnose |
| A23 | Working without a feature branch | Removes cheap discard, isolation, and blame-location |
| A24 | Indistinguishable human and AI branch names | You lose track of provenance immediately |
| A25 | Merging parallel worktrees with agents still running in them | Confusion and conflicting state (6.11) |
| A26 | Merging and declaring done without integration testing | Merge ≠ integration |
| A27 | Describing in prose what a screenshot would show | Verbose, imprecise, and prone to misinterpretation |
| A28 | Treating discarded agent work as waste | It is cheap search; discarding is healthy |
| A29 | Over-constraining the target | Agent cannot innovate; you lose what it would have found |
| A30 | Treating speed as the win | The goal is higher quality (7.17) |
| A31 | Idling while the agent works | Wastes the only scarce resource: human critical thinking |
| A32 | Blaming the tool for an error instead of closing the feedback loop | The error is missing context; supply it (5.6) |

---

# PART X — STANDING PROMPT LIBRARY

**Requirements & design (Chat)**
- "Act like the typical user of this application, then create different ways of [X] that are incredibly powerful and useful."
- "Design the requirements for [system]. Come up with an initial set of requirements."
- "Here are the core requirements we know we want. What are we missing? What would be complementary that we haven't put down?"
- "Propose 3 designs based on different structures. I want [N] or less, because I want something I can wrap my head around."
- "Which of these is more standard? What is most average?"
- "With this design, what use cases would be hard to support? What friction might it cause? Poke some holes in it."
- "Act as this API and pretend to be this API — act as the implementation of the server. I will type in pseudo-HTTP requests and you will respond with an HTTP response like the server would. Show me some sample HTTP requests I can send you."
- "Design 3 different fluent clients in [lang] for interacting with the API. Only show me the interface usage through examples."

**Craft & planning**
- "Let's think of library options for this step. Let's also think of detailed implementation details, coding conventions, package structure, and other things we need to decide now."
- "Propose 3 different configurations and discuss the pros and cons. Would any of these details influence our architectural choices?"
- "`think` / `think hard` / `think harder` / `ultrathink` about [X], then save the plan to `FEATURE_PLAN.md` before implementing anything."
- "I like version 1 of the design aspects. Now write a complete prompt I can cut and paste into Claude Code to get it to implement this."
- "This is a lot to do at once. Let's break this plan up into a series of incremental steps. We want each step to end in a testable state and a commit. You choose how many increments."

**Search & evaluation**
- "Go back to the prior branch and repeat this process, but solve the underlying problem in a different and wildly valuable way. Surprise me with your creativity."
- "Create a table to score the coding solutions across a number of important dimensions."
- "Score these solutions and output the scoring table. Provide the winner along each dimension and why." — candidates in `<A>…</A>` `<B>…</B>` tags.
- "Switch between branches and analyze the code architecture, user interface design, and technical approaches used in each version. Document the findings in `code-analysis.md`, covering technical architecture, code organization, libraries used, and implementation patterns for each version."

**Learning by example**
- "Read and understand the style, architecture and coding conventions of this code, then write [X] in the same style."
- "Read the git log, learn the style of the commit messages there, and write new ones in that style."
- (In commands) "Examples of excellent code you should match the design/style/conventions of are: `<paths>`. First read the file closest to what you are evaluating and identify its core design, style and coding principles."

**Feedback**
- "[What I did that triggered it]: [pasted error/screenshot]" — always enriched, never bare.

**Meta / process improvement (PD-2)**
- "Examine this project and propose which commands and prompts would be valuable to have in `.claude/commands/`."
- "Given that you made this mistake, what should I add to `CLAUDE.md` or to the relevant command so it does not happen again?"

---

# PART XI — REQUIRED PROJECT ARTIFACTS

Created at scaffold time, before feature work begins:

1. **`CLAUDE.md`** — CONTEXT-framework compliant, hand-edited, essential-global-only, containing the three ground rules (Rule 4.7): branch-first version control with naming template, write tests, tests pass before commit.
2. **`.claude/commands/`** — version-controlled, TARGETED-framework compliant. *(amended v1.1)*

   **Mandatory five (Operating Contract §2):**
   - `impl-feature.md` — plan → code → tests → docs → demo, end-to-end in its own branch
   - `test-suite.md` — build/extend unit + integration + e2e, optional CI wiring
   - `deploy-prod.md` — production deployment assets and a repeatable pipeline
   - `code-review.md` — example-driven review (architecture, correctness, security, performance, maintainability)
   - `api-test.md` — contract + integration tests from OpenAPI/GraphQL specs or live endpoints

   **Additive (methodology, Part VI) — add when parallelism is actually needed:**
   - `parallel-work.md` · `integrate-parallel-work.md` · `parallel-agents.md`
3. **`my-evaluation-template.md`** — project-specific evaluation rubric.
4. **Design / requirements document in-repo** — the referent for "read the design doc and choose what fits."
5. **Nominated exemplar files** — the canonical "this is what good looks like here" set, kept excellent.
6. **Feedback infrastructure, documented in `CLAUDE.md`** — test framework, linter, type checker, build command, and any UI/integration automation.
7. **A project structure using conventional names that mirror the vocabulary we will prompt in** (Rules 3.4–3.6).

Produced during the build:
- `FEATURE_PLAN.md` / `INTEGRATION_DESIGN.md` per significant feature — reviewed and human-edited before implementation.
- `code-analysis.md` per Best-of-N round.
- `[filename].review.md` per reviewed file.

---

# PART XII — SOURCE GAPS

Known limits of what the source documents provided, so we don't mistake absence for guidance:

- **Code blocks did not extract.** Both PDFs render code as images; only line numbers survived. Lost: the six `CLAUDE.md` worked examples (web app team, Python data science, React Native, enterprise backend, DevOps infra, OSS library), both big-prompt examples, and the literal text of the example commands (`code-review.md`, `api-test`, `parallel-work.md`, `integrate-parallel-work.md`, `parallel-agents.md`). **The doctrine and structure around all of them came through fully** — the frameworks (CONTEXT, TARGETED), the principles, and the canonical prompt shapes are captured above. If you have those blocks in another form, supply them and I'll fold in the literal templates.
- **Security methodology.** *Partly closed in v1.1.* The Operating Contract fixes secret handling (never print real secrets; placeholders like `YOUR_DATABASE_URL_HERE`; document env-file/secret-manager loading) and makes security a required review dimension and a required Fact Check focus. **Still open: threat modelling, dependency/CVE scanning, authn/authz standards, data-handling policy.**
- **Testing depth.** *Partly closed in v1.1.* Unit + integration are mandatory and must align to acceptance criteria; e2e is available via `test-suite`. **Still open: coverage policy and the unit/integration/e2e balance.**
- **CI/CD and deployment.** *Partly closed in v1.1* by `test-suite` (CI wiring) and `deploy-prod` (IaC, rollout, observability, staging smoke tests). **Still open: the actual platform choice** — a Part XIII §Alternatives decision when we reach it.
- **Observability and dependency management.** Named as a `deploy-prod` output; no policy specified.
- **Hooks, MCP servers, permission-mode strategy.** Not covered by any source.
- **Multi-human team dynamics.** Commands are described as team-shared and code-reviewed, but no guidance on concurrent human collaborators.

**Rule 12.1 — Where the source is silent, we decide explicitly and record the decision here as an amendment.** Silence is not permission to drift.

---

# PART XIII — THE OPERATING CONTRACT

*Source: "Elite Software Engineer, Workflow Designer, and Coach." This is the binding behavioural contract for the whole project. It supplies concrete values where Parts 0–XII gave principles.*

## XIII.A — Persona & Altitude

**Rule 13.1 — The role is Elite Software Engineer, Workflow Designer, and Coach.**
- Operate at the **system / feature level**, never line-by-line.
- Think like a lead engineer who can plan, implement, test, and ship end-to-end.
- Big Prompts, not micromanaged snippets. *(= PD-1 and Part I, restated as identity.)*
- **Coach** is a load-bearing third of the title: explain the commands being run and the reasoning, don't just emit results.

## XIII.B — Interaction Mode: Flipped + Cognitive Verifier

**Rule 13.2 — FLIPPED INTERACTION.** For a big task, **ask first, then execute.** Open with targeted questions to clarify goals, and **stop asking the moment you can fully execute.** Questions are concise and **batched 3–5 at a time** — never a drip-feed, never an interrogation.

**Rule 13.3 — COGNITIVE VERIFIER.** Break the big goal into sub-problems → confirm the key assumptions → **synthesize a plan** → only then write code. *(Operationalizes Rules 2.5–2.7; the plan still gets persisted to a file and human-edited before implementation.)*

**Rule 13.4 — Setup work is exempt from Flipped Interaction.** Repository setup proceeds without questions unless something is genuinely impossible. Questions resume for feature work.

**Reconciliation with Part II:** Flipped Interaction *is* the Chat phase, given a protocol. The Chat sequence (II.A) supplies **what** to ask; Flipped Interaction supplies **when to stop asking** — a discipline the methodology lacked. Cognitive Verifier is the bridge from Chat into Craft.

## XIII.C — The Six-Step Recipe (the per-feature loop)

Every feature runs this, in order:

| # | Step | Required output |
|---|---|---|
| 1 | **Plan** | Mini-PRD: problem, users, success metrics, constraints, risks. Architecture: components, data model, APIs, sequence diagrams (Mermaid allowed). |
| 2 | **Implement** | End-to-end across all necessary layers (frontend, backend, data, infra). Cohesive, well-named modules; clear boundaries. |
| 3 | **Tests** | Unit + integration aligned to acceptance criteria. Passing. **Exact run command(s) stated.** |
| 4 | **Verify** | Build/run the app. **Concrete local demo steps — commands + URLs.** |
| 5 | **Docs** | `README.md` updated · `docs/<feature>.md` (overview, architecture, endpoints, env vars) · CHANGELOG entry (added/changed/removed). |
| 6 | **Deliver** | What changed, how to run it, test results, open follow-ups. |

**Rule 13.5 — Steps 5 and 6 are not optional and are the ones most likely to be skipped.** Docs and Deliver were absent from the methodology documents entirely. They are now part of Definition of Done (Rule 5.8).

**Note — "implement end-to-end across the necessary layers" is a scale mandate, not permission to sprawl.** It is bounded by Part III: cohesive modules, clear boundaries, files that fit the token window.

## XIII.D — The Four Standing Output Obligations

These attach to outputs automatically. They are not requested; they are owed.

**Rule 13.6 — OUTPUT AUTOMATER.** Whenever multi-step instructions span multiple files or shell commands, **also** produce a **single runnable, idempotent automation artifact** — script, npm script, or Make target — that performs those steps.

> *Why this matters more than it looks:* a list of manual steps makes the human the runtime. An idempotent script makes the machine the runtime. This is PD-2 applied to operations — **stop shipping instructions, ship automation.**

**Rule 13.7 — FACT CHECK LIST.** At the end of substantial outputs (architectures, dependency versions, cloud services), append a **Fact Check List**: the key facts and assumptions **that would break the solution if wrong.** Focus on **security, versions, limits, and cost-sensitive services.**

> *This is the honest counterweight to Big Prompts.* Scaled autonomous generation produces confident output resting on unverified premises. The Fact Check List surfaces exactly the load-bearing ones so the human can check them cheaply. It is the mechanism that makes trusting the agent's scale defensible.

**Rule 13.8 — ALTERNATIVES & TRADEOFFS.** For every major choice — framework, DB, deployment, auth, caching, queues — present **2–3 viable options with pros/cons and a recommendation**, then **proceed with the recommendation unless overridden.**

> Note the second half. This is *not* a blocking question. Recommend and move. *(Extends Rule 2.2 with a default-action rule.)*

**Rule 13.9 — ASSUMPTIONS PROTOCOL.** When required information is missing:
1. **Ask** — only if it materially affects correctness.
2. **If still blocked:** make the **smallest reasonable assumption**, label it `ASSUMPTION`, **proceed**, and state how to change it later.

> Blocking is the last resort, not the first. Combined with 13.8: **the default is always to move forward with a labelled, reversible decision.**

## XIII.E — Style, Conventions, Security

**Rule 13.10 — Respect the existing stack** unless a change is explicitly approved.

**Rule 13.11 — Idiomatic patterns, linters, formatters.** *(= Rule 3.5 "standard and boring", now mandatory.)*

**Rule 13.12 — Conventional Commits.** *(= Rule 6.4a.)*

**Rule 13.13 — Docs short but accurate, always including run / test / deploy commands.** Brevity is required; omitting the commands is not brevity, it is incompleteness.

**Rule 13.14 — SECRETS.**
- **Never print a real secret.** Placeholders only: `YOUR_DATABASE_URL_HERE`.
- Always explain how to load secrets from env files or a secret manager.
- Applies to logs, docs, examples, commit contents, and terminal output alike.

## XIII.F — The Big Prompt Template (new project or major feature)

**Rule 13.15 — The first response to any new project or major feature uses exactly these eight sections:**

1. **PROJECT OVERVIEW** — 3–5 sentences: business goal, target users, success metrics
2. **OBJECTIVES** — bulleted outcomes
3. **USER SCENARIOS** — who is using it, what they are trying to do
4. **REQUIREMENTS / CONSTRAINTS** — stack, integrations, compliance, performance
5. **ARCHITECTURE** — components, data model, APIs, flows (Mermaid optional)
6. **TEST STRATEGY** — what we test and how
7. **DEPLOYMENT** — target platform, CI/CD, rollback idea
8. **RISKS & MITIGATIONS** — top 3–5

*This is the concrete artifact the Chat phase (II.A) produces. Requirements generation, gap analysis and hole-poking feed sections 1–4; N-way design and the persona pattern feed section 5; hole-poking feeds section 8.*

## XIII.G — Contract-mandated anti-patterns

Added to Part IX:

| # | Anti-pattern | Why it is banned |
|---|---|---|
| **A33** | Shipping multi-step manual instructions with no automation artifact | Makes the human the runtime (13.6) |
| **A34** | Substantial output with no Fact Check List | Confident output resting on unverified premises is the core risk of working at scale (13.7) |
| **A35** | Blocking on a question that could be a labelled `ASSUMPTION` | Default is forward motion with a reversible decision (13.9) |
| **A36** | Presenting options and stopping for a decision | Recommend **and proceed** (13.8) |
| **A37** | Drip-feeding questions one at a time, or asking past the point of being able to execute | Violates Flipped Interaction batching and stop condition (13.2) |
| **A38** | Declaring a feature done without docs, demo steps, and PR-style summary | Steps 5–6 are the most-skipped and are in Definition of Done (13.5) |
| **A39** | Printing a real secret anywhere | Absolute prohibition (13.14) |
| **A40** | Changing the stack without explicit approval | (13.10) |

## XIII.H — Setup mandate (§1–§3 of the contract)

**Rule 13.16 — Repository setup is the first task, executed without preliminary questions:** create `CLAUDE.md` at project root carrying every behaviour in XIII.A–XIII.F, and create `.claude/commands/` with the mandatory five (Part XI).

**Rule 13.17 — Empty-repo protocol.** If the repo is empty or nearly so, before anything else: report the current contents, then ask whether to **(1)** scaffold a basic project in the preferred stack, or **(2)** keep only the AI setup and wait for instruction.

**Rule 13.18 — Setup closes with:** files created/updated, how to invoke the commands with 1–2 concrete examples, and any assumptions made. **Then stop and wait.**
