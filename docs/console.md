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
| **Packs** (`/packs`, `/packs/[venture]`) | whether each Pack can provision and why not; draft/live/provisioned versions and the drift between them; validate and publish as separate acts |
| **Provisioning** (`/provisioning`, `/provisioning/[venture]`) | the sixteen-gate ladder, with three verdicts rendered three ways |
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
every rule in the registry and stores nothing. FAIL, WARN and NOT_RUN render separately, because
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

## The Packs page, rebuilt

The old page listed which ventures had a Pack and gave the first sixteen characters of a
hash. It could not answer the question a reader opens it with: **can this Pack
provision, and if not, why.** A Pack failing any FAIL rule cannot provision, cannot
generate and cannot appoint — so validation state is the most consequential thing about
a Pack, and it was the one thing the page did not carry.

**Four validation states, not two.** `can provision`, `provisions with warnings`, `not
validated`, `cannot provision`. The third exists because a rule that could not run has
passed nothing, and rendering "no problems were found" the same as "every rule passed"
is the specific failure this page exists to prevent. `not validated` renders in the
warning palette rather than a neutral one: an unknown about whether a Pack can provision
is not a resting state.

**Deferred is not unrun.** V24 is evaluated at Gate 4.5 against appointment output,
which does not exist at Gate 2 — Gate 2 excludes it from its own NOT_RUN check. Counting
it here would make `not validated` permanent and `can provision` unreachable, which
turns the distinction above into noise. It is reported separately, by rule id.

**The failure names this Pack's problem.** `V11 · no Forge Operating Instructions
authored for: comp_analysis, place_call`, not the rule's description. The second is a
specification; only the first tells somebody what to go and do. It comes from the
validator's own message, so it cannot go stale the way a table of blocker strings does.

**Three version states, because they are three different documents.** The draft somebody
is writing, the live version that would be provisioned next, and the version the running
system was actually built from. Live ahead of provisioned is **drift** — the running
configuration is not the published one — and nothing in the old page could express it.
When a Pack has drifted and Gate 10 signatures exist, the page says those signatures no
longer cover what is published: nothing revoked them, they stopped matching.

**Drafts, and why they cannot provision.** Migration 0017 adds `business_pack.status`.
A draft is unreachable by construction rather than by a check: `packs.live` filters on
`status = 'live'`, so Gate 1 cannot find a draft and nothing downstream has an input.
That is what makes it safe to save a Pack that still fails ten rules — and the work of
authoring a Pack is mostly the work of making it stop failing, so it has to be storable
in the meantime or it gets written somewhere this console cannot see. Replacing a draft
supersedes it rather than deleting it: `office_app` has no DELETE on the Pack store, and
a draft somebody replaced is still a document somebody wrote.

**New Pack, three ways in and one way out.** Paste, template and duplicate differ only
in where the text comes from; all three end at the same textarea and the same save. A
separate "create from template" route that wrote its own row would be a second way to
author a Pack, and the second way is always the one that skips a check.

**A template fails validation on purpose.** Every field whose value depends on the
venture is `REPLACE_ME`, and every venture-specific number is zero — so V18 fails on the
budget caps, and that failure is the mechanism that makes somebody choose real ones. A
template that shipped a plausible budget would produce a Pack that passes V18 on a
figure this repository invented. What a template *does* carry is the compliance surface
for its category, because that does not depend on the venture, marked `library_gap:
true`. Every other choice defaults to its safe end: `sandbox`, `suggest`, `halt`,
`fail_closed`, `distinct_humans` — an unfinished Pack that reached a run anyway cannot
be more permissive than the operator intended.

**Every denominator is computed.** The brief that specified this page said 27 validator
rules and 17 schema blocks. The registry has 28 and the model has 18, and both numbers
were already wrong when the brief was written — so the page reads them from
`all_rule_ids()` and `BusinessPack.model_fields` rather than carrying them as copy.

**Two bugs this increment found.** `/api/packs/directory` was registered after
`/api/packs/{venture_id}`, and FastAPI matches in declaration order — so the literal
segment was handed to the parameterised route as a venture id and the endpoint answered
200 with the detail for a venture named "directory". Nothing failed; the wrong route
answered with a plausible body. And `PORTFOLIO` declared the cyber venture's only
framework as `NRS_648` where the Pack schema's literal is `NRS_648_NV` — so no Pack for
that venture could ever have declared it. Nothing had noticed, because nothing tried to
generate a Pack from the portfolio until templates existed. Both are pinned by tests.

## The Provisioning page, rebuilt

The page's own subtitle promised that a run "stops at the first gate that blocks and
says which". It named the gate number and stopped there. Sixteen gates were represented
by `5 of 16` - a number with no map - and the page could not say what happened at the
gate that stopped the run, what cleared before it, or what is still ahead. It also
carried no action at all, which made the provisioning page the one place you could not
provision from.

**The ladder replaces the fraction.** Every gate renders, in order, whether or not it
ran, and it is never collapsed or truncated: seeing the whole path is the point. The
gate a run stopped at is filled in danger; the ceiling gate is filled in warning
wherever the run stopped. Those are two unrelated walls - the one this run hit, and the
one every run in this deployment will hit - and the old page gave no way to tell them
apart.

**Plain-language names on the ladder, the spec's names underneath.** `GATE_TITLES` says
what a gate checks, in the vocabulary of the document that defined it - "Human review of
artifacts, BOM and appointment gap report". That is right on the gate's own row, where
there is room; a sixteen-row ladder needs "Human review". `GATE_NAMES` is the second
map, and the ladder carries the long form as the row's title attribute rather than
losing it.

**The numbering is explained rather than left contradictory.** A page showing "Gate 4"
and "5 of 16" at the same time reads as a bug. Gates 3.5, 4.5 and 9.5 were inserted
after the original twelve, so the gate number and the cleared count legitimately differ,
and the footnote says so - computed from the ladder, including which gates are the
fractional ones, so inserting a gate 6.5 later cannot make the sentence wrong.

**Why the run stopped, in this run's own words.** The old page said `aborted, gate 4`.
Gate 4 is human review, so that could have been a rejection, a timeout or an error. The
stop block now names the gate, the disposition, the human who acted and when, then what
happened and what it means downstream - including how many gates never ran as a result.
The reason is always the recorded outcome; rendering the gate's generic description here
would produce a sentence true of every run and about none of them.

**A run somebody ended does not have its reason in the gate results.** The gate recorded
why it was *waiting*; the human recorded why they stopped it, and that went to the audit
log. So a cancelled or rejected run reads its disposition from `audit_log` - actor,
timestamp and reason - and that overrides the gate's message. The first build of this
page credited a cancellation to whoever *started* the run, which for a run cancelled
days later is the wrong person.

**The status vocabulary is the reader's, not the machine's.** `aborted` reads as though
somebody cancelled it - which is what it means, and what it fails to distinguish from a
gate refusing. Stored status stays as it is; the display status is derived:

| Shown | When |
| --- | --- |
| `running at gate N` | in progress |
| `awaiting review at gate N` | a gate has put something to a human |
| `stopped at gate N` | a gate blocked on policy |
| `failed at gate N` | a gate threw. Marked at the gate with `evidence.error`, not guessed from the reason string |
| `rejected at gate N` | a human declined at a gate awaiting their decision |
| `cancelled` | a human abandoned the run. Says nothing about the artifacts |
| `at ceiling` | reached 9.5 and can go no further in this deployment |
| `complete` | reached gate 12 |

**`at ceiling` is not a failure.** A run that reaches 9.5 has done everything currently
possible, and conflating that with failing would misrepresent a successful run as a
broken one. It is drawn on the *evidence*, not the gate number: a held-out verdict of
`FAIL` at the same gate is a real failure, and reading the two the same way would report
a venture that failed adversarial testing as merely waiting for infrastructure.

**Gate 4 can now say no.** Until this increment `record_human_review` could only record
that a human had reviewed the artifacts - there was no way to decline. A review that can
only approve is not a review, and what a reviewer actually had was `abort_run`, which
means something different: abandoning a run rather than judging it. Migration 0018 adds
`rejected` as a terminal status, and it is only reachable while a gate is
`awaiting_human` - rejecting a run nothing has put to a human would be a way to stop it
mid-flight while dressing it as a judgement. Like an abort, it does not deactivate
grants: a rejection is not a revocation.

**Resume, and when it is refused.** Resuming is `advance` from the gate the run stopped
at - the same mechanism, so it cannot drift from one. It is unavailable when the Pack
changed underneath the run, including the case a version string cannot catch: the same
version re-stored with different content. The run holds the Pack hash it began with, and
resuming against different content would provision something nobody started.

**No override, anywhere.** The ceiling notice states there is none deliberately, and a
UI offering one would make that copy a lie. `test_no_route_can_pass_a_gate_that_blocked`
enumerates the provisioning write surface and fails on any route whose path contains
force, skip, override, bypass or unblock - so the guarantee is enforced rather than
remembered. Every write there either starts a run, runs gates in order, or stops one.

**Ceiling styling.** The notice was styled identically to body copy, which is how the
strongest sentence in the console came to read like an aside. It now carries the warning
palette and a lock icon.

### The run detail page

The structure here was already right — sixteen rows including the gates still ahead, the
review form beside the numbers it is about, advance and abandon as separate acts. What
was wrong was what the page knew and did not say.

**It knew the next gate would fail.** At gate 4 it held `GATE 4.5 V13 FAIL` and filed it
under *Generator warnings (2)*, then asked a human to write a review and press *Advance
from gate 4* — while already holding the reason the run halts one gate later. That
spends somebody's attention to manufacture another abandoned run. A danger banner now
states it above the form: which gate, which rule, and what advancing will do. It
deliberately does **not** disable Advance: an operator may legitimately want to confirm
the halt, and a page that decides for them has stopped informing and started enforcing,
which is the gates' job.

**A failure was being counted as a warning.** `_collect_warnings` returned a flat list of
strings, so a rule that FAILs at 4.5 and a genuine advisory shared a container and a
count. The fix is at the source rather than in the console: `Advisory` carries
`severity`, `rule_id` and `blocks_at`, so the two cannot be conflated by any reader, and
the console renders *Blocking failures (1)* and *Warnings (1)* as separate blocks with
separate counts. Deriving it in the page from a substring match on `"FAIL"` would have
worked until the day a warning mentioned the word.

**Raw JSON was the default view.** Three capacity numbers as an object literal and a
warnings array with escaped quotes, printed at the human about to take responsibility for
what they read. Capacity is three metric cards, unfilled positions render as a sentence
when empty, the artifacts hash truncates with a copy control and one line on what it
binds. The raw object stays behind a *View raw* toggle — engineers need it, and when a
rendered summary and the underlying object disagree the object is the one that is true.

**V13 reads as English.** It was a formula: `192 approvals x 6 min = 1152 minutes against
144 available`. It is now three sentences that keep every number, and the last one is
pinned verbatim by a test — the utilisation factor is the one number in that rule
somebody can lower to make it pass without changing anything real, so the message closes
that door explicitly.

**Run history states its finding.** Six runs, all Pack 1.0.0, all stopped at gate 4,
rendered as six identical rows: the pattern was the most useful fact on the page and the
reader had to derive it. The heading now carries it, the Pack version is on every row —
consecutive runs sharing a version is the signal that nothing changed — and older
identical outcomes collapse behind a count.

**`aborted` and `rejected` no longer share a colour.** Abandonment is neutral and says
nothing about the artifacts; rejection is a judgement about them. `aborted` also renders
as *abandoned*, because "aborted" reads as a crash when somebody chose it.

**Gate 9.5 reads the same on both screens.** It said *not run* here and *blocked —
ceiling* on the index, because each screen described the ladder in its own terms. Both
now call `provisioning.ladder_for`, so one gate cannot mean two things depending on which
page you opened.

**Two review actions instead of two cards.** *Record review and advance* and *Record
review only*, in one form. They sat in separate cards with no stated relationship, so
whether advancing needed the review first was something an operator found out by trying.

**Two smaller defects found on the way.** The shared `Button` hardcoded `text-white` on
`bg-surface-inverse`; that surface flips with the theme, so every filled button rendered
white-on-white for dark-mode readers. And starting a second run for a venture surfaced
the `ux_run_active` constraint as a bare **500** — a deliberate rule reported as an
internal error teaches an operator that the system is broken when it is working. It now
refuses with a message naming the run in the way. The constraint is still the control:
the pre-check loses a race between two simultaneous requests, and a test proves the
database refuses independently by inserting past the check.

### The Pack editor

The directory rebuild gave Packs drafts, templates, four validation states and a publish
step. None of it reached the editor — which is the screen where the work those things
describe actually happens.

**A draft saved from the directory was invisible here.** The detail route returned only
the live Pack, so the editor opened that over the top of the draft. The draft was still
stored; it just was not on the screen built to work on it, and the next save wrote over
it with text the operator had never seen as a draft. The route now returns both, and the
editor opens the draft in preference, saying which version stays live meanwhile.

**A draft was rendered as live.** The version history keyed "live" off
`superseded_at IS NULL` — which is true of a draft as well, so an unpublished draft
appeared with a green live badge beside the version actually in force. Two rows both
claiming to be what a run would provision. It reads `status` now, which exists precisely
so this cannot be inferred wrongly.

**Three acts, three forms.** Validate writes nothing; saving a draft stores a document
that cannot provision; publishing supersedes the live Pack. A stored draft gets its own
publish control, which says explicitly that it promotes the stored draft rather than the
text in the box — those differ the moment somebody types.

**One validation state machine.** `packs.validation_state` is shared by the directory and
the editor, so a Pack cannot read `valid` on one screen and `not validated` on the other,
and the rule count comes from the registry rather than the copy — the editor said "all 27
rules" against a registry of 28.

### The editor's validation badge, and what a stage can claim

The badge read `can provision - 28 of 28 rules checked`. Both halves overclaimed, and
the second has a principle behind it.

**Not evaluable, passed and failed are three states.** One rule - V24 - had not been
evaluated at all: it tests appointment output, which does not exist until the generators
run at Gate 3. Counting it in "28 of 28 checked" claims the document was examined more
thoroughly than it was, on the screen where somebody decides whether to publish it. The
result is now three numbers that partition the rule set, and a test asserts the
partition rather than the wording.

**"Can provision" is a claim about the pipeline, not about this stage.** V13 passes at
Gate 2, which estimates approvals from headcount, and fails at Gate 4.5, which computes
them from the real Task Ledger - the two disagree by an order of magnitude and the Gate
2 estimate is the optimistic one. So a Pack with no failures here has not been shown to
be provisionable. The badge says `No blocking failures at this stage`, which is the
finding the validator can actually support, and rules that a later gate re-checks say so.

`GATE_45_RECHECKS` names those rules, and a test reads the source of
`validate_gate_4_5` to assert the constant matches what the function evaluates - a list
that drifts from the thing it describes is worse than no list, because the editor would
go quietly back to implying Gate 2 is the last word.

**Every unevaluable rule names the gate that settles it and why this one cannot.** A bare
NOT_RUN says something did not happen without saying what would, which leaves a reader
to decide whether it is a defect, a gap in the Pack, or normal.

### The diff, the history, and the publish guard

**A diff, on the document that gets signed.** Its hash pins every provisioning run that
started from it and Gate 10 signatures bind to the artifacts it generates, and there was
no way to see what differed from the live version. `lib/diff.ts` is a plain LCS -
implemented rather than imported, because a dependency on this page is a dependency on
the one screen that must not surprise anybody. Identical text says so rather than
rendering an empty panel, which reads as a diff that failed to load.

**Migration 0019 separates `abandoned` from `superseded`.** A released version replaced
by a later release and a draft nobody published were both `superseded`, which is why an
abandoned draft above the live version read as a broken sort - the list was ordered
correctly and the label was not saying what happened. The first attempt distinguished
them by a `-draft` suffix on the version string; that is a naming convention rather than
a fact, wrong for a draft called `1.2.0` and for a release called `2.0.0-draft`. The
store records which one it was.

**The history keeps its own promise.** "A run names the version it provisioned" was copy
under a list that could not say it: versions were here and runs were on another screen.
Each row now carries its run count, its author, a diff against live or any other
version, and Restore as draft - which restores as a *draft* rather than publishing,
because restoring is usually recovery and that is exactly the moment not to put a
document into force in one click.

**Publish confirms.** Version transition, diff summary, the rules the text is known to
carry, and what publishing does not do. The warning names Gate 10 signatures rather than
certifications: `certification.instruction_content_hash` binds to a Forge Operating
Instruction, not to a Pack, so publishing a Pack does not void certifications. What it
voids is signatures, which bind to the artifacts the Pack generates.

### Block navigation, and where the actions live

342 lines in one scroll, with Validate, Save draft and Publish below all of them. Editing
`budget` at line 129 meant scrolling past 128 lines to reach it and the rest of the
document to act on it.

**A sidebar of every block the schema defines, present or not.** A list of the blocks a
document happens to contain cannot say "this Pack has no `kpi_targets`" - the absence has
no line to scroll to, so the sidebar is the only place it can appear.

**The mapping from rule to block is derived, not written down.** The sidebar marks blocks
a failing rule reads, which needs a rule-to-block map. Twenty-eight table entries
maintained beside twenty-eight functions, with nothing forcing them to agree, is the
shape of the blocker-string table the ventures page replaced. A rule already names the
fields it reads - `pack.budget`, `pack.positions_required` - so `rule_blocks()` reads it
back out of the source. All 28 rules map; the four world rules, which are appended by
`validate` rather than registered by the decorator, are named explicitly because they are
about the bridge rather than about a block.

**Icons only where they mean something.** A failing rule, or an absent block. Marking
every row would make the two that matter indistinguishable from the sixteen that do not.

**Line numbers and presence come from the buffer, not the stored Pack.** The sidebar has
to follow what is being typed, including a document that does not parse yet - which is
the state it is most useful in, and the state a YAML parser returns nothing for. So
`lib/blocks.ts` reads top-level keys out of the text, and the server sends only the
schema's block list.

**The actions are pinned to the bottom of the editor card**, and submit the same three
forms as the reference row below the document via `form=` rather than duplicating them.
Publish still opens its confirmation: a pinned button that skipped it would be a
one-click supersede, which is what the confirmation exists to prevent.

**`min-w-0` on the editor column is load-bearing.** Without it the monospace content sets
the flex item's minimum width and the document pushes the sidebar off the screen instead
of scrolling.

**A note on the fixture.** The smoke check for "every block has a row" was passing for
the wrong reason: Greenstone's Pack contains all eighteen blocks, so a sidebar listing
only what it found was indistinguishable from one listing the whole schema. The check now
runs against a draft with one block removed, and reinstating the present-only filter
fails the suite.

## Known gaps

*Last verified: 2026-08-24.*

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
- **Nothing in this project executes client JavaScript.** `tsc`, `next build`, the unit
  tests and the smoke script all pass against a page that is broken in a browser: the
  server render is correct and only a browser hydrates. Two failures have shipped through
  that hole - `useActionState`, and a function passed to a form `action`, both React 19
  APIs that type-check against the definitions Next ships while the pinned runtime is
  React 18.3.1. The smoke script now greps for the shapes that have bitten, which catches
  a repeat and not a new one. Closing it properly means a headless browser in CI loading
  each page and asserting no uncaught error - roughly a minute of CI time and a real
  dependency, so it is a decision to take deliberately rather than a side effect.
- **The editor is a textarea with line numbers, not a code editor.** No YAML syntax
  highlighting, and no parse-error marking distinct from rule failures. Block navigation
  and deep links now exist; highlighting still wants a real editor component (CodeMirror
  or Monaco), which is a bundle and a CSP decision rather than a side effect.
- **Scroll-spy measures line height from computed style.** It assumes every line is one
  line tall, which a textarea guarantees only while wrapping is off. It is, and the
  gutter depends on the same assumption; a wrapped line would put both out by the number
  of visual rows it occupies.
- **Download YAML and Replace from file are not implemented.** The text is selectable and
  the diff is readable, so nothing is blocked; it was cut for the items above it.
- **The publish confirmation lists rules the *stored* Pack carries, not the edited text.**
  Validating the buffer would need a round trip the confirmation does not make. Validate
  first and the panel above is authoritative; the confirmation says "as stored".
- **Schema completeness is on the Packs directory, not in the editor.** The directory
  computes it per Pack; the editor would need to compute it against the unsaved buffer,
  which is the same round-trip question as above.
- **A run started before this increment has the old gate-4 evidence.** Advisories are
  recorded when the gate runs, so runs already parked at gate 4 carry the flat `warnings`
  list and show no downstream banner. Re-running produces the structured form; nothing
  backfills.
- **"Awaiting you" means "awaiting somebody with your role".** Gate 4 names no individual
  — any venture operator can review — so the page says "awaiting you" to anyone who could
  act and "awaiting a venture operator" to anyone who could not. It is not a personal
  assignment and does not claim to be.
- **Per-gate timing is measured from the previous gate's record, not from when the gate
  started.** With gates that take milliseconds this is the same number; a gate that waits
  on a human shows the wait rather than the work, which is arguably the more useful
  figure and is definitely not the one the column name implies.
- **History is fetched per venture on demand and is not paginated.** A venture with
  hundreds of runs would return all of them. Nothing has more than a handful today.
- **`failed at gate N` depends on gates marking their own faults.** Gates 3 and 5 set
  `evidence.error` when they catch an exception; a gate added later that blocks on a
  caught error without setting it will read as `stopped`, which understates it.
- **The Pack directory validates every Pack on every page load.** Each card runs the
  full rule set against the live database, which is why a Pack that passed yesterday can
  fail today — a Forge went unreachable, an instruction was withdrawn. With one Pack
  that is correct and cheap; with fifty it is fifty validation passes per render, and it
  will need caching with an explicit staleness statement rather than a silent one.
- **Duplicating a Pack does not rewrite the identity for you.** The copy arrives with
  the source venture's `identity.venture_name`, and `venture_id` derives from it, so
  saving unchanged overwrites the source venture's own draft rather than creating a new
  one. The action says so; it does not prevent it.
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
