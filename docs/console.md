# The Console — increment 2

Master prompt Part 17. Next.js 14 + TypeScript + Tailwind, per the blueprint stack.

## One decision solves both problems increment 1 left open

At the end of the API increment I named two things the UI would have to deal with:
**CORS, and how the browser holds a token.** Both disappear if the browser never talks
to the API.

Every API call happens **server-side inside Next.js** — Server Components and Server
Actions. The bearer token lives in an `httpOnly`, `sameSite=strict` cookie, is read on
the server, and is never sent to the browser.

- **No CORS configuration exists**, because no cross-origin request is ever made.
- **The token is never in JavaScript.** Not in `localStorage`, not in a prop, not in a
  hydration payload. An XSS in this console cannot exfiltrate it.
- The API is unchanged — no new routes, no relaxed auth.

`lib/api.ts` starts with `import "server-only"`, so importing it from a client component
is a **build error**, not a runtime surprise. That is what keeps this true rather than a
convention someone has to remember.

The smoke script greps every rendered page for the token and fails if it appears.

## The risk specific to a UI

Increment 1's risk was an API that bypasses a control. A UI cannot bypass one — it can
only call the API, whose write surface is pinned by a test.

**A UI's risk is that it misrepresents state.** A dashboard rendering a sweep that has
never run in a reassuring grey, or showing "0 incidents" without saying the check that
produces them is stale, is worse than no dashboard. It manufactures confidence.

So the rule this increment adds:

> **Anything not verifiably healthy renders as not-healthy.** `never_run` and `stale`
> are red, not grey, not absent.

That mapping lives in `lib/severity.ts` as a pure function with its own tests, rather
than as a Tailwind class chosen inline in a component nobody will read again. An
unrecognised incident severity maps to `bad`, not neutral — guessing "probably fine" for
a value nobody anticipated is the same mistake as a silent default in a verdict map.

The Compliance Dashboard puts **control freshness above the incident list**, because a
quiet incident list means nothing if the check producing it is stale.

## Screens

| Screen | Notes |
|---|---|
| **Compliance Dashboard** (`/`) | control freshness, chain integrity, recent incidents |
| **Agent Registry** (`/agents`) | certified tier **beside** declared tier — Part 17 asks for both because they disagree |
| **Revocation Controls** (`/revocations`) | four scopes with their blast radius stated next to the control |
| **Forge Map** (`/forge-map`) | Declared × Required × In-Use, pending Gate 15 dispositions first |
| **Audit Log Explorer** (`/audit`) | filters; chain status shown above the entries |
| **Venture Directory** (`/ventures`) | engagements on the Village, not Villages |
| **Venture Dashboard** (`/ventures/[id]`) | the three capacity numbers, readiness gates, Forge usage |
| **Agent Identity & Grants** (`/agents/[id]`) | grants, per-Forge migration status, recent shifts |
| **Approval queue** (`/proposals`) | the screen that can erode a control without bypassing it |
| **Instruction authoring** (`/instructions`) | index + version, diff, staleness, certification impact |
| **Pack Editor** (`/packs`, `/packs/[venture]`) | validate and publish as separate acts; version history with hashes |
| **Provisioning Console** (`/provisioning`, `/provisioning/[venture]`) | the sixteen-gate ladder, with three verdicts rendered three ways |

One remains, and it is **still not buildable**:

| Screen | Blocked by |
|---|---|
| **Knowledge Base Manager** | Part 6 names five knowledge bases. **One exists.** The other four would be empty promises with a UI on top. |

A screen over nothing is worse than an absent screen, because it implies the thing
exists.

## The risk increment 3 adds

Increment 2's risk was a UI that *misrepresents* state. This one is sharper:

> **A UI can make a control easy to defeat without bypassing it.**

The approval queue is the example. Part 14 requires rubber-stamp detection precisely
because approving is the easy path, and a queue with a one-click **Approve** next to a
collapsed payload is a rubber-stamp machine — every approval authorised, audited,
counted, and producing exactly the outcome the control exists to prevent.

So `/proposals`:

- shows the **full payload expanded by default**, never behind a disclosure;
- names the five-second threshold **on screen**, with a live counter next to the button;
- requires a reason to reject, because "no" without one returns nothing the agent can
  learn from;
- does **not** disable the button for five seconds — that trains people to wait five
  seconds. Showing the number they are about to be measured against gives them a reason
  to read.

None of this is enforcement. The API decides, and it computes `review_seconds` from
`created_at` in the database so a client cannot report a review time it did not take.
This is the difference between a screen that cooperates with a control and one that
quietly erodes it.

## Two findings from the smoke run

**A venture that does not exist rendered a dashboard.** Ventures are engagements derived
from grants, manifest rows and budgets rather than a table, so any string produced a page
full of zeroes — and zeroes for a mistyped venture look exactly like zeroes for a real
one that has not started. `/ventures/[venture]` now `notFound()`s unless the venture
appears in the directory, and the smoke script asserts a 404.

**A smoke check passed for the wrong reason.** The parameterised-route check scraped the
HTML for `/ventures/<slug>` and matched a Next.js chunk filename, then reported a pass
against a venture that did not exist. It now asks the API for real ids. A check that can
pass for the wrong reason is worse than no check.

**The console does not pre-check your authority.** The API checks it twice — role
strength for the scope, and whether you operate that venture — and the console reports
the refusal. A second opinion in the UI would eventually disagree with the first, and
the UI's copy is the one nobody updates.

## A green build is not proof the app runs

`/revocations` compiled cleanly, passed `tsc --noEmit`, passed `next build`, and threw at
render:

```
TypeError: (0 , a.useActionState) is not a function
```

`useActionState` is React 19. This project pins React 18.3.1 per the blueprint stack,
where the equivalent is `useFormState` from `react-dom`. The types resolved and the
bundle compiled; only a real request found it.

That is why `scripts/console-smoke.sh` exists and why it runs the real server rather
than trusting the build.

## Verification

```bash
cd console && npm run typecheck && npm test   # types + the logic that can mislead
./scripts/console-smoke.sh                     # the real server, end to end
```

The smoke script starts the API and the console, issues a throwaway operator token, and
asserts: unauthenticated routes redirect, authenticated routes render, the session
cookie is `httpOnly`, **no route leaks the token into HTML**, and unhealthy controls
carry a failing severity class. It kills whatever it started however it exits.

Playwright is deliberately absent: `next start` is documented in my notes as crashing
mid-E2E on Windows, so a browser suite here would be flaky for reasons unrelated to this
code. The risky logic is pure and unit-tested; the rest is checked over HTTP.

## shadcn/ui

`shadcn init` is an interactive CLI, and an interactive prompt in this environment hangs
rather than fails. The five primitives these screens need are hand-written in
`components/ui/` following shadcn conventions, so running the real CLI later drops in on
top. Recorded rather than silently substituted.

## The risk increment 4 adds

These are the first two screens that **author the input to everything else**. A Business
Pack is the document every artifact derives from — positions, appointments, workflow,
task ledger, curriculum, grants. A provisioning run is the thing that turns it into
production authority.

A text box that publishes a Pack looks like a file editor. It is not: publishing
supersedes the live Pack, and the next run provisions the new one.

Three rules follow.

**Validate before publish, and show the whole report.** `POST /api/packs/validate` runs
all 27 rules and stores nothing. FAIL, WARN and NOT_RUN render separately, because
`NOT_RUN` is not a pass and an editor that shows it as a green tick teaches the operator
to read it that way.

Publishing does *not* require a clean report. Gate 2 refuses a Pack with a FAIL, and it
refuses it in the run — where refusing means something. An editor that would not let you
save a draft with a known failing rule pushes people to edit YAML somewhere this console
cannot see.

**Publishing does not start a run.** Two acts, two routes, two audit events. A save
button that quietly begins provisioning is a save button that issues grants. The editor
does say what publishing will disturb — an active run, and any Gate 10 signature that
will be void against the new artifacts — because neither is visible from a text box.

**The console cannot choose the hash it signs.** `POST /api/signoffs` accepts an
arbitrary `artifact_hash`, which was harmless while nothing consumed it. Gate 11
activates production grants against it now, so provisioning sign-off has its own route:
the client sends the hash **it displayed**, the server regenerates the artifacts, and a
mismatch is refused rather than re-pointed. A signature is a confirmation of what was on
screen.

### Three verdicts, rendered three ways

`gateSeverity` in `lib/severity.ts` is the piece of presentation logic that can defeat
the gate it describes. `awaiting_human` rendered as a pass and the operator stops
looking; rendered as blocked and they go hunting for a defect instead of reading the
artifacts they are being asked to review. A gate that has not run is a fourth case, and
is not a pass either.

The ladder renders **all sixteen rows**, including gates still ahead. A ladder listing
only what happened shows a run stopped at 9.5 as a tidy column of nine passes.

Gate 4 is the approval queue's hazard in a new place: a one-click "reviewed" beside a
collapsed artifact summary is a rubber stamp — authorised, audited, and producing exactly
the outcome the gate exists to prevent. So the unfilled positions, the capacity triple
and the generator warnings render expanded above the form, and the note is required.

### The ceiling is stated on the index, not discovered at the gate

No run started from this console can pass gate 9.5, because SimForge's held-out partition
does not exist. The index says so in a card rather than letting an operator find out by
clicking Advance nine times. There is no override.

## Running the console against real data

A fresh database has no Forge registry, so Gate 0 refuses every run — correctly — and
these two screens have nothing to render.

    .venv/Scripts/python scripts/seed_dev_world.py

Registers three Forges at `example.invalid`, authors instructions, and certifies the
seven-agent stand-in roster. **Development only**, and idempotent by deletion: it clears
the world it owns before rebuilding, which includes every certification and instruction
in the database.

`scripts/console-smoke.sh` calls it when the Forge registry is empty, publishes the
Greenstone Pack if no venture has one, then drives a real run and renders the ladder —
because the first version of these checks passed against a page showing one blocked gate
and no forms at all.

## Known gaps

- **One screen remains** — the Knowledge Base Manager, blocked on four knowledge bases
  that do not exist.
- **Gate 10's sign-off form is not exercised by the smoke script.** The real Greenstone
  Pack blocks at gate 4.5 on the capacity finding, so a run from the dev seed never
  reaches gate 10. The form shares its hook usage with the three that are exercised;
  that is an argument, not evidence.
- **No `secure` cookie flag outside production** — correct for local HTTP, but the
  deployment must be HTTPS or the cookie travels in the clear.
- **No CSRF token on the Server Actions.** Next.js Server Actions carry origin checks and
  the cookie is `sameSite=strict`, which covers the common case; a deployment behind a
  proxy that rewrites `Origin` would need more.
- **Session is 8 hours with no refresh and no idle timeout.**
- **No pagination** — the audit explorer caps at 100 rows and says nothing about what it
  did not show.
- **Revocation is write-only in the UI.** Reinstatement exists in the API; there is no
  screen for it yet, so lifting a revocation currently needs a direct API call.
