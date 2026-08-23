# Pack Editor and Provisioning Console — PLAN

Master prompt Part 17, screens 12 and 13. The last increment built their backend; this
one builds the routes and the screens.

Thirteen of fourteen screens after this. The Knowledge Base Manager stays unbuilt,
because Part 6 names five knowledge bases and one exists.

---

## What makes these two screens different from the eleven before them

The console's existing risk is that a UI **misrepresents state** — a never-run sweep
rendered a reassuring grey. Increment 3 added a second: a UI can make a control **easy to
defeat without bypassing it**, which is why the approval queue expands the payload and
names the five-second threshold on screen.

These two add a third, and it is the sharpest yet. **They are the first screens that
author the input to everything else.** A Business Pack is the document every artifact
derives from: positions, appointments, workflow, task ledger, curriculum, grants. A
provisioning run is the thing that turns that document into production authority.

A text box that publishes a Pack looks like a file editor. It is not. Publishing
supersedes the live Pack, and the next run provisions the new one.

So three rules.

### 1. Validate before publish, and show the whole report

`POST /api/packs/validate` runs all 27 rules and **stores nothing**. The editor shows
FAIL, WARN and NOT_RUN separately, because `NOT_RUN` is not a pass and an editor that
renders it as "no problem" teaches the operator to read it that way.

Publishing does not require a clean report. Gate 2 refuses a Pack with a FAIL, and it
refuses it in the run where refusing means something. An editor that would not let you
save a draft with a known failing rule would just push people to edit YAML elsewhere.

### 2. Publishing does not start a run

Two acts, two buttons, two audit events. A save button that quietly begins provisioning
is a save button that issues grants.

### 3. The console cannot choose the hash it signs

`POST /api/signoffs` accepts an arbitrary `artifact_hash` in the body. That was fine when
nothing consumed it and is not fine now that Gate 11 activates grants against it: a
client that supplies the hash can sign artifacts it never displayed.

So provisioning sign-off gets its own route. The client sends the hash **it displayed**,
the server recomputes the artifacts and **refuses if they differ**. Signing is a
confirmation of what was on screen, not an assertion about what is in the database.

---

## Routes

Reads:

| Route | For |
|---|---|
| `GET /api/packs` | live Pack per venture |
| `GET /api/packs/{venture_id}` | version history + live source |
| `GET /api/packs/{venture_id}/versions/{pack_version}` | one version's source |
| `GET /api/provisioning/runs` | runs, optionally by venture |
| `GET /api/provisioning/runs/{run_id}` | run state + every gate result with evidence |

Writes — seven new, taking the pinned surface from 7 to 14:

| Route | Guarded function it delegates to |
|---|---|
| `POST /api/packs/validate` | `validator.validate` — **stores nothing** |
| `POST /api/packs` | `packs.store` |
| `POST /api/provisioning/runs` | `provisioning.start_run` |
| `POST /api/provisioning/runs/{run_id}/advance` | `provisioning.advance` |
| `POST /api/provisioning/runs/{run_id}/review` | `provisioning.record_human_review` |
| `POST /api/provisioning/runs/{run_id}/abort` | `provisioning.abort_run` |
| `POST /api/provisioning/runs/{run_id}/signoff` | `humans.sign_off`, hash recomputed |

None reaches past a guarded function to a table. `advance` activates grants at Gate 11 —
through the gate machine, which requires a valid unvoided signature. There is no route
that activates a grant directly, and there must never be.

The API always uses the default `PartitionAbsent`, so **no run started from the console
can pass Gate 9.5**. That is the truth about this deployment and the screen says so.

---

## Screens

**Pack Editor** — `/packs` and `/packs/[venture]`.
Version history with live/superseded state and content hash. A YAML editor. Validate
(report, no write) and Publish (write) as separate acts. Before publishing, the screen
says what publishing will disturb: any active run, and any existing Gate 10 signature
that will be void against the new artifacts.

**Provisioning Console** — `/provisioning` and `/provisioning/[venture]`.
The gate ladder: sixteen rows, each with verdict, reason and evidence. Three verdicts
rendered three ways — `awaiting_human` is not `blocked` and not `passed`. Evidence is
expanded on the current gate, because the current gate is the one being acted on.

Actions appear only where they apply: Review at Gate 4, Sign at Gate 10, Advance
otherwise, Abort always. The Gate 4 review is the approval queue's hazard again — a
one-click "reviewed" beside a collapsed artifact summary is a rubber stamp — so the
unfilled positions, the capacity triple and the generator warnings render expanded, and
the note is required.

---

## Acceptance tests

| # | Test |
|---|---|
| C1 | validate stores nothing, and reports FAIL/WARN/NOT_RUN separately |
| C2 | publishing supersedes and returns the computed hash |
| C3 | publishing does not start a run |
| C4 | the write surface is 14 routes, enumerated |
| C5 | a run started through the API stops at Gate 4 `awaiting_human`, not `blocked` |
| C6 | review requires a note and a venture-scoped operator |
| C7 | **sign-off refuses a hash that does not match the recomputed artifacts** |
| C8 | sign-off with the matching hash lets Gate 11 activate |
| C9 | there is no route that activates a grant |
| C10 | abort frees the venture; grants are untouched |
| C11 | severity mapping: `awaiting_human` renders distinctly from `blocked` and `passed` |
| C12 | smoke: both screens render against real seeded data |
