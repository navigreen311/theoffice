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

Nine remain (Pack Editor, Provisioning Console, Venture Directory, Venture Dashboard,
Shift & Capacity, KB Manager, Instruction authoring, Readiness Gate, Compliance detail).

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

## Known gaps

- **Nine screens remain** (increment 3).
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
