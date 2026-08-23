# Console, increment 3 — the remaining screens — PLAN

Master prompt Part 17 lists fourteen screens. Five shipped in increment 2.

## Nine remain, and three of them are not buildable yet

Stated up front rather than discovered halfway through:

| Screen | Buildable now | Why not |
|---|---|---|
| Agent Identity & Grants (detail) | **yes** | `/api/agents/{id}` exists |
| Venture Directory | **yes** | `/api/ventures` exists |
| Venture Dashboard | **yes** | composes capacity + gates + budget |
| Shift & Capacity (three numbers) | **yes** | `/api/ventures/{id}/capacity` exists |
| Readiness Gate view | **yes** | `/api/ventures/{id}/gates` exists |
| Instruction authoring | **yes**, +2 read routes | needs a module list and a version diff |
| **Pack Editor** | **no** | Packs are YAML files on disk. There is no Pack store, no persistence, no versioning. A "Pack Editor" that edits a file the server cannot see is a text box. |
| **Provisioning Console** | **no** | Gates 3–11 are functions nobody has wired to a request. Running seven generators, holding the artifacts for Gate 4 human review, then applying — that is a backend increment, not a screen. |
| **Knowledge Base Manager** | **no** | Part 6 names five knowledge bases. **One exists.** Business Playbooks, Compliance Library, Persona Library and Historical Records are not built at all, so the "manager" would manage one thing and four empty promises. |

This increment builds the six. The three that need backend get their backend named, not a
placeholder screen — a screen over nothing is worse than an absent screen, because it
implies the thing exists.

## The risk specific to this increment

Increment 2's risk was a UI that *misrepresents* state. This one is different and
sharper:

> **A UI can make a control easy to defeat without bypassing it.**

The proposal queue is the example. Part 14 requires rubber-stamp detection precisely
because approving is the easy path, and a screen with a one-click **Approve** button
next to a collapsed payload is a rubber-stamp machine. It bypasses nothing — every
approval is authorised, audited, and counted — and it produces exactly the outcome the
control exists to prevent.

So the proposal screen:

- shows the **full payload expanded by default**, not behind a disclosure;
- states the five-second threshold **on the screen**, next to the button;
- requires a decision reason for a rejection, because "no" without a reason returns
  nothing actionable to the agent;
- shows the venture's compliance flags on the proposal, so the reviewer sees what applies
  before deciding rather than after.

None of this is enforcement — the API decides. It is the difference between a screen that
cooperates with a control and one that quietly erodes it.

## Two new API routes, both reads

- `GET /api/forges` — registry with modules and whether instructions are authored.
  The instruction-authoring screen has no way to list what it can author for.
- `GET /api/instructions/{forge}/{module}/diff` — section-level diff between two
  versions, from `instructions.diff`.

Reads only. The write surface stays pinned at seven routes and the bypass test is
unchanged.

## Acceptance tests

| # | Test | Asserts |
|---|---|---|
| V1 | the write surface is still exactly seven routes | the new routes added nothing writable |
| V2 | `/api/forges` reports instruction presence per module | authoring screen has its input |
| V3 | the diff route names changed sections | |
| V4 | a proposal older than the rubber-stamp threshold is flagged in the UI helper | |
| V5 | the capacity view refuses to show fewer than three numbers | §7.2 |
| V6 | every new route renders 200 authenticated, redirects when not | |

## Out of scope

Pack store, provisioning pipeline over HTTP, the four missing knowledge bases. Each is a
backend increment with its own plan.
