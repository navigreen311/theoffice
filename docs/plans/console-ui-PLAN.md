# Console, increment 2 — the Next.js application — PLAN

Master prompt Part 17. Next.js 14 + TypeScript + Tailwind, per the blueprint stack.

## The two problems I named at the end of increment 1, solved by one decision

**CORS, and how the browser holds a token.** Both disappear if the browser never talks
to the API.

Every API call happens **server-side inside Next.js** — Server Components and Route
Handlers. The bearer token lives in an `httpOnly`, `sameSite=strict` cookie, read on the
server and never sent to the browser.

Consequences worth stating, because this is the load-bearing decision of the increment:

- **No CORS configuration is needed**, because no cross-origin request is ever made. The
  browser talks only to Next.js.
- **The token is never in JavaScript.** Not in `localStorage`, not in a client component
  prop, not in a hydration payload. An XSS in this console cannot exfiltrate it.
- The API stays exactly as increment 1 left it — no new surface, no relaxed auth.

The alternative (token in `localStorage`, browser calls the API directly) needs CORS,
puts a credential where any script can read it, and buys nothing.

## The risk specific to a UI

Increment 1's risk was an API that bypasses a control. A UI cannot bypass a control — it
can only call the API, and the API's write surface is pinned by a test.

**A UI's risk is different: it can misrepresent state.** A dashboard that renders a
sweep that has never run as a reassuring grey, or shows "0 incidents" without saying the
check producing them is stale, is worse than no dashboard. It manufactures confidence.

So the one rule this increment adds:

> **Anything not verifiably healthy renders as not-healthy.** `never_run` and `stale`
> are red, not grey, not absent.

That mapping is a pure function with its own tests, not a Tailwind class chosen inline in
a component where nobody will look at it again.

## Screens in this increment

Five, chosen by weight rather than by order in Part 17:

| Screen | Why first |
|---|---|
| **Compliance Dashboard** (home) | control health + incidents; where `never_run` must be red |
| **Revocation Controls** | the kill switch, four scopes, authority enforced server-side |
| **Audit Log Explorer** | until Forges carry per-agent identity this is the only per-agent record |
| **Forge Map** | reconciliation diff and pending Gate 15 dispositions |
| **Agent Registry** | certified tier beside declared tier — Part 17 asks for both because they disagree |

The remaining nine (Pack Editor, Provisioning Console, Venture Directory, Venture
Dashboard, Shift & Capacity, KB Manager, Instruction authoring, Readiness Gate, Venture
Dashboard) are increment 3.

## shadcn/ui

`shadcn` init is an interactive CLI, and an interactive prompt in this environment hangs
rather than fails. The handful of primitives these five screens need — card, badge,
table, button, field — are hand-written with the same Tailwind conventions shadcn
generates, in `components/ui/`. Running the real CLI later drops in on top of them.
Recorded rather than silently substituted.

## Testing, given a known Windows trap

`next start` is documented in my notes as crashing mid-E2E on Windows (exit 3221226505),
so a Playwright suite here would be flaky for reasons that have nothing to do with this
code.

Instead:
- **Pure functions carry the risky logic** (health → severity, tier comparison, relative
  age) and are unit-tested with vitest. These are the parts that can be wrong in a way
  that misleads.
- **`next build` must succeed** — type errors and bad imports fail there.
- **The dev server is exercised over HTTP** for the routes, which catches a broken page
  without Playwright's process-lifecycle problems.

## Acceptance tests

| # | Test | Asserts |
|---|---|---|
| U1 | `never_run` maps to a failing severity, not neutral | the rule of this increment |
| U2 | `stale` maps to failing | a stale pass is not a pass |
| U3 | `failing` maps to failing | |
| U4 | only `fresh` maps to healthy | |
| U5 | a certified tier below the declared tier is flagged as capped | Part 10.1 |
| U6 | the API client never returns the token to a caller | |
| U7 | `next build` succeeds | types and imports |
| U8 | every screen route responds 200 when authenticated, redirects when not | |

## Out of scope

The nine remaining screens. Real SSO. Anything that would need a new API route — if a
screen wants one, that route goes through increment 1's bypass test first.
