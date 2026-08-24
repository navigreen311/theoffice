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
| **Knowledge Base Manager** (`/knowledge`) | coverage for all five stores; blocking gaps render differently from advisory ones |
| **Access** (`/access`) | people, roles, tokens and active revocations — the screen that removed the shell dependency |
| **Incidents** (`/incidents`) | open and resolved; resolving appends an account and never edits the detection |

**All fourteen exist.** The Manager was the last, and it was refused three times with
the same sentence — *a screen over nothing is worse than an absent screen, because it
implies the thing exists.* Part 6 names five knowledge bases and one was built, so the
screen was never the increment: the four stores were. See `docs/knowledge-bases.md`.

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

## The Compliance page, rebuilt

The page told a reader who already knew the system what state it was in: a banner
reading "4 control(s) not verified" and four snake_case identifiers in a table. **A
count is not a conclusion**, and `audit_chain` is an identifier, not an explanation.

What changed, and why each thing:

**The banner states a conclusion.** "Compliance posture is unverified, not clean", then
what that means for everything below it, then the sentence about absence of findings.
And it **does not disappear when everything is fine** — it turns green and says so.
Health communicated by the absence of a warning is indistinguishable from a warning that
failed to render.

**Every control explains itself.** A human name with the identifier beside it for the
engineers who search by it, a sentence saying what the check actually does, its cadence,
and the consequence of it not running — the consequence in the danger colour when it
blocks. The copy lives in `broker/app.py` next to the code that runs the sweeps, because
a description that drifts from the check it describes is worse than none, and the console
is the wrong place to notice the drift.

**Every control can be run from the page — except one, which says why.** The restore
drill needs superuser credentials to create a scratch database, and the API deliberately
does not hold them. A Run button that always fails is worse than no button, so that row
carries the host command instead. This is a deliberate deviation from the brief, and the
alternative was giving the API superuser credentials to make a button work.

**Frameworks are on the compliance page.** This was the largest gap: a Compliance page
with no compliance frameworks on it. One row per venture, each declared framework
resolved against both a runtime flag and a Compliance Library entry — because missing
either means the obligation is named but not enforced. It is the same check V28 makes at
Gate 2, rendered.

**Every number carries its denominator, and none of them is invented.** The brief asked
for "0 of 5 ventures" and "0 of 106 agents". The Village roster has not been imported, so
the honest denominator is the seven agents The Office actually knows — reporting 106
would fabricate a number on the one page whose own copy insists on real ones. The gap is
reported as its own fact instead.

**An as-of timestamp**, because a compliance view with no time anchor cannot be used as
evidence and a screenshot of it cannot be dated.

**A regulator export** (Part 9). It states its own control freshness *on its face* — an
export produced while four controls have never run says so at the top — and it lists what
it did not include. It is hash-stamped rather than signed: there is no key material in
this deployment, and a fabricated signature would prove nothing while appearing to prove
provenance.

**Scheduling is a statement, not a button.** There is no in-app scheduler. In a
deployment the `sweeps` container runs them hourly; locally nothing does. A control that
claimed to configure a schedule would be a lie on the page whose entire purpose is not
lying about what has been checked.

### Design tokens and dark mode

Every colour resolves through a CSS variable in `app/globals.css`, with a full dark
palette. No component contains a hex literal, and the smoke script fails if one appears —
a hardcoded colour is a colour that cannot invert, and one of them eventually renders a
failure state in a reassuring grey.

Severity is a triple per state (tinted background, border, text) rather than
`bg-ok/10`. Tailwind's opacity modifier needs a colour it can decompose into channels
and a `var(--x)` is opaque to it, so the old classes silently produced nothing once the
palette moved to variables.

Type scale is six named sizes and two weights. Navigation is the same fourteen links in
four groups — Operate, Teach, Govern, Inspect.

## The Ventures page, rebuilt

Five columns, none of which answered the question a reader opens the page to ask:
**where is this venture, and can it go live.** Pipeline state is a venture's most
important attribute and appeared nowhere — and a table row has nowhere to put the
blocked reason, which is the most important content on the page.

**Cards, with the gate in the status.** `blocked at gate 0`, never bare "blocked" —
which tells a reader nothing they can act on. A six-segment bar maps the sixteen gates
onto bridge → pack → generate → certify → sign off → live, and a test asserts the
mapping covers `GATE_SEQUENCE` exactly so a gate cannot drift into the wrong phase.

**The blocked sentence is computed, never looked up.** The brief that specified this
page supplied three example blockers, and one of them — "structural PHI flush is not
built" — had stopped being true when Phase 3.3 shipped. That is the argument against a
table of blocker strings: right the day it is written, wrong afterwards. The sentence
comes from the validator's own message for the rule that failed, so Greenstone reports
*the bridge does not reach cre-forge* because V2 says so.

**Status is derived, not stored.** The only stored states are the two nothing can
derive: `archived`, and the draft that exists before a Pack does.

**Creation, two ways.** Start from a Pack validates all 28 rules before anything is
created; start blank takes five fields and leaves the rest to the Pack editor. The
venture id always comes from the document rather than the form.

**The portfolio panel.** Four of the five named ventures have no Pack. They are listed
as absent, with what each one would bring — the same principle as the Compliance
banner, because absence must not be able to look like health. Which are missing is
computed against what exists, so it cannot go on claiming a venture is unauthored after
somebody authors it.

**Spend shows the cap and says it is not measured.** `usd_cost` is never populated, so a
burn-down bar pinned at zero would read as "nothing spent" when it means "nothing
measured". The bar renders only when there is real spend, with the soft cap marked —
that is the line where every agent in the venture downgrades to `propose`.

### A venture table, for two things an engagement cannot be

A venture has always been an engagement rather than a table, and mostly still is. It
cannot represent a **draft** — `BusinessPack` is `Strict`, so a stub Pack would mean
inventing a `monthly_usd_cap`, which is the field V18 exists to stop a venture reaching
production without — or **archived**, which is indistinguishable from empty. So
`venture` holds only that: slug, declared name and category, environment, lifecycle. The
Pack still wins on everything it declares.

### Navigation

The wordmark is a link, Dashboard is the first item under Operate, and pages carry a
breadcrumb. There was previously no route back to a dashboard from anywhere.

## Known gaps

*Last verified: 2026-08-23.*

- **Playbooks and personas are authored but not consumed.** There is no knowledge-
  retrieval path for agents in The Office at all, and SimForge has no instance. See
  `docs/knowledge-bases.md` for what that leaves open.
- **Gate 10's sign-off form is not exercised by the smoke script.** The real Greenstone
  Pack blocks at gate 4.5 on the capacity finding, so a run from the dev seed never
  reaches gate 10. The form shares its hook usage with the three that are exercised;
  that is an argument, not evidence.
- **The `secure` cookie flag follows the request protocol, not the build mode.** It used
  to follow `NODE_ENV`, and `next start` sets that to production — so a local build over
  http emitted a `Secure` cookie that the browser silently discarded, and the sign-in
  bounced straight back to the login screen looking like a rejected token. `curl` stores
  such a cookie anyway, which is why the smoke script passed while the console was
  unusable in a browser. It now reads `x-forwarded-proto` first (Caddy terminates TLS
  and the app sees http on the internal hop) and falls back to the request URL, and the
  smoke script asserts both directions.
- **No CSRF token on the Server Actions.** Next.js Server Actions carry origin checks and
  the cookie is `sameSite=strict`, which covers the common case; a deployment behind a
  proxy that rewrites `Origin` would need more.
- **Session is 8 hours with no refresh and no idle timeout.** An expired or otherwise
  rejected session redirects to the login page — it used to throw a 500, because only a
  *missing* cookie raised `NotAuthenticated` while a *rejected* one raised `ApiError`
  that no page caught.
- **Pagination covers audit and incidents only.** Proposals, history and the knowledge
  lists still return everything they have. They are bounded by the business today and
  will not stay that way.
- **No search across ventures.** Every list is filtered by exact match; there is no free
  text anywhere.
- **Dark mode is complete for the primitives and the Compliance page.** Other screens
  inherit dark surfaces through `Card`, `Badge` and `Table`, and a handful of page-level
  strings still carry their own spacing-era classes. Nothing is unreadable; a pass over
  the remaining screens is a follow-up.
- **The regulator export is hash-stamped, not signed.** Provenance needs key material
  this deployment does not have.
- **The export returns a document, not a downloadable archive.** The brief asked for a
  signed archive; what exists is the manifest that would go in one.
