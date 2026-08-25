# The Operations API — Console, increment 1

Master prompt Part 17 (Administration Console) and Part 14 (Human Capacity, Identity,
Separation of Duties).

The console's fourteen screens are views over these routes. This increment builds the
API and human identity; the Next.js app is increment 2.

## Why the API before the UI

`broker/` was a library. The client library called its functions in-process; there were
no HTTP routes and **no human identity at all**. Every governance action took a `UUID`
for the actor and a role *string*, and trusted the caller about both.

A Next.js app on top of that is a mockup — and worse, a mockup that looks like a control
surface.

## The design risk

This is the most dangerous code in the repository to write carelessly, and the danger is
not obvious.

Every control lives in a guarded function. Revocation checks authority. A disposition
demands a reason. `assign_shift` refuses an unflushed predecessor. Certification is a
live state, not a column somebody sets. **An API that reached past those functions to
the tables would undo all of it while looking like a feature.**

"Let the operator fix the certification state" is a reasonable-sounding request that
removes the entire certification gate.

Two rules, both tested rather than reviewed by eye:

**1. Every write calls the same guarded function the domain uses.**
`test_the_api_module_contains_no_raw_mutation` greps `broker/app.py` for `UPDATE`,
`DELETE FROM` and `INSERT INTO`. There is no second path to a table.

**2. Routes that must not exist, do not exist.**
`test_the_api_exposes_no_route_that_bypasses_a_control` pins the entire write surface to
nineteen routes and rejects any path containing `certification`, `flush`, `ledger`,
`shift`, `memory`, `grant` or `audit`. If a new route trips it, the question is not how to make it
pass — it is whether that route should exist.

| Write route | Delegates to |
|---|---|
| `GET /api/agents/roster` | `roster.directory` — the Village roster and the identity gap |
| `POST /api/agents/roster/preview` | `roster.diff` — **writes nothing** |
| `POST /api/agents/roster` | `roster.apply` |
| `POST /api/agents/identities` | `roster.issue_identity` — makes an existing agent appointable; never creates one |
| `POST /api/agents/village` | `roster.register_village_agent` — requires the Village's own ref |
| `POST /api/revocations` | `revocation.revoke` |
| `POST /api/revocations/{id}/reinstate` | `revocation.reinstate` |
| `POST /api/proposals/{id}/decide` | `proposals.decide` |
| `POST /api/dispositions/resolve` | `sweeps.disposition` |
| `GET /api/instructions/directory` | `instructions.directory` — completeness assessed from content, not from a row existing |
| `POST /api/instructions` | `instructions.author` |
| `POST /api/ventures/{id}/reverse-hard-cap` | `budget.reverse_hard_cap` |
| `POST /api/signoffs` | `humans.sign_off` |
| `POST /api/packs/validate` | `validator.validate` — **writes nothing** |
| `POST /api/packs` | `packs.store` |
| `POST /api/packs/draft` | `packs.store(publish=False)` — stored, and unreachable by Gate 1 |
| `POST /api/packs/{venture_id}/publish` | `packs.publish_draft` |
| `GET /api/me` | the signed-in human, so a screen can say "awaiting you" rather than `awaiting_human` |
| `POST /api/provisioning/runs` | `provisioning.start_run` |
| `POST /api/provisioning/runs/{id}/advance` | `provisioning.advance` |
| `POST /api/provisioning/runs/{id}/review` | `provisioning.record_human_review` |
| `POST /api/provisioning/runs/{id}/reject` | `provisioning.reject_run` — a human declines at a gate awaiting their decision. Distinct from abort |
| `POST /api/provisioning/runs/{id}/abort` | `provisioning.abort_run` |
| `POST /api/provisioning/runs/{id}/signoff` | `provisioning.sign_off_run` |
| `POST /api/knowledge/playbooks` | `knowledge.author_playbook` |
| `POST /api/knowledge/playbooks/share` | `knowledge.share_playbook` / `revoke_share` |
| `POST /api/knowledge/compliance` | `knowledge.author_compliance_entry` |
| `POST /api/knowledge/personas` | `knowledge.author_persona` — **write-only** |
| `POST /api/knowledge/history` | `knowledge.record` — append-only |

The persona route writes and **there is no route that reads a body back**, because
`office_app` holds no read privilege on that column (Part 6.4). A read route would be a
privilege error rather than a leak. `docs/knowledge-bases.md` has the four layers that
keep it that way.

`advance` is the only route in this API that can end with an agent holding production
authority, and it cannot skip a gate to get there: the machine runs from the current
gate, Gate 11 refuses without a Gate 10 signature bound to the current artifacts, and it
re-checks rather than trusting Gate 10's recorded verdict.

**There is no route that activates a grant**, and there must never be — the signature
check, the artifact binding and Gate 9 all live on the other side of one.
`test_there_is_no_route_that_activates_a_grant` fails the build if one appears.

`POST /api/provisioning/runs/{id}/signoff` exists because `POST /api/signoffs` takes
whatever `artifact_hash` its caller passes. That was harmless while nothing consumed it.
Gate 11 activates production grants against it now, so the provisioning route takes the
hash the client **displayed**, regenerates the artifacts, and refuses a mismatch rather
than re-pointing the signature at whatever is current. A signature is a confirmation of
what was on screen.

## Authorisation asks two questions

A role string alone can only answer the first.

1. **Is this role strong enough for this scope?** — `revocation.assert_authority`, the
   §1.4 matrix: `agent_module`/`agent` need venture_operator, `venture` needs
   compliance_officer, `forge` needs Ivan.
2. **Is this person an operator of *this venture*?** — `humans.authorize`, using
   `office_human_role.venture_id`.

The second could not exist before, because the domain only ever saw a role string. A
venture operator could revoke in a venture they had nothing to do with.

**Reinstatement requires the same authority as the revocation it lifts.** Otherwise a
venture operator could undo a compliance officer's venture-wide stop, and the matrix
would be decorative.

**Status is read live.** A suspended human is refused on their next *request*, not their
next session — the same rule agent revocation follows, for the same reason.

**`token_hash`, never a token.** Same rule as `credential_ref`: the column proves
possession without being the thing possessed. The plaintext is returned exactly once.

## Sign-offs void by comparison

Part 14: "artifact change voids signature."

`signoff_record` stores the hash of what was signed. `signoff_status()` compares it to
the artifact now, so a signature is void by *comparison* rather than by somebody
remembering to revoke it when a Pack is edited — the same property that makes
certification staleness reliable rather than aspirational.

**Separation of duties** is `distinct_humans`: a human who has already signed another
gate for this venture cannot sign this one. Checked in `sign_off`, not trusted to
process.

## Run

```bash
.venv/Scripts/python -m broker serve --port 8080
```

**Not `uvicorn broker.app:app`.** uvicorn explicitly installs
`WindowsProactorEventLoopPolicy` on Windows, overriding the selector policy
`broker/__init__.py` sets — and psycopg's async driver cannot run on Proactor.

The symptom is not an error. The server starts, accepts connections, and **every
database-backed request hangs until the client times out**, with the real cause in a
startup log line nobody is reading. `serve` passes `loop="none"` so uvicorn leaves the
policy alone, and a test asserts that argument is still there.

This is the third entry point where this gotcha has appeared — after the test suite and
the Pack-validator CLI. It is now the first thing to check whenever something that
touches the database hangs on Windows.

Interactive docs at `/docs` once running.

## Two SQL shapes that are banned

`tests/test_sql_shapes.py` fails the build on either of these inside a query containing
a `LEFT JOIN`. Both shipped, both produced a believable wrong number, and neither raised
or logged anything.

**`count(*) FILTER (WHERE <joined column> IS NULL)`.** A LEFT JOIN that matches nothing
still produces one row with every right-hand column NULL, and `NULL IS NULL` is true —
so the row is counted. A venture with no grants reported one live grant. Count a column
from the joined side instead: `count(g.grant_id) FILTER (...)`.

**`bool_or` / `bool_and` without `COALESCE`.** Over an empty group the result is NULL,
and `NOT NULL` is NULL rather than TRUE — so the group matches no negated filter and
disappears from the totals. An agent with no certification row fell into none of the
three capacity numbers, which then stopped summing to the roster they were counting,
under a docstring reading "all three, always — one hides the state".

The checks are scoped to `LEFT JOIN` because with an inner join every group has at least
one row and both idioms are correct. They are proved able to fail against the two
queries as they were actually written.

## Knowledge listings are paged, and hide fixtures by default

`GET /api/knowledge/personas` and `GET /api/knowledge/history` returned a bare array.
They now return an envelope:

    {"rows": [...], "total": 0, "page": 1, "pages": 1,
     "total_before_filters": 60, "excluded_fixtures": 60}

`excluded_fixtures` is the count the caller is *not* seeing, so a client cannot render
"no personas" over a library that has sixty rows it was not shown. `include_fixtures=true`
returns them, each row carrying an `origin` of `authored`, `system` or `test_fixture`.

Origin is derived per request by `broker/knowledge_origin.py` rather than stored.
`historical_record` is append-only and `office_app` holds no UPDATE on it, so a column
could not have been backfilled onto existing rows or corrected afterwards.

`GET /api/knowledge/overview` returns the five bases with a count, a denominator, and the
gap in words, plus a `fixtures` block. Denominators come from the live Packs — target
personas, positions, lifecycle stages, runtime flags — so a base with nothing in it can
say what it is missing rather than reporting zero.

Three contract tests indexed those routes as arrays and broke when the envelope landed,
which is the envelope working: `test_a_persona_body_appears_in_no_response`,
`test_a_note_is_recorded_against_the_human_who_wrote_it`, and
`test_resolving_an_incident_appends_and_never_edits`.

## Incidents publish their taxonomy; revocation reports its blast radius

`GET /api/incidents/taxonomy` serves the severities, kinds, detection sources and response
stages from `broker/incident_taxonomy.py`. The console renders from it rather than keeping
its own copy: a screen holding a private enumeration disagrees with the database the first
time a value is added, and the disagreement shows up as a row rendering blank.

`kind` now has a CHECK constraint, written by migration 0023 from that same module. Two
test fixtures were seeding kinds the code never raises - `'test'` and `'rubber_stamp'`,
where the real one is `rubber_stamp_approval` - and both passed for as long as the column
was free text.

`POST /api/incidents` files one a person noticed; only the three human kinds are accepted,
because filing `audit_chain_broken` by hand would claim a check ran that did not.
`POST /api/incidents/{id}/accounts` appends one stage account. Neither edits anything:
`incident` refuses UPDATE by grant, `incident_account` by trigger.

`GET /api/incidents/overview` returns control freshness, open counts and the cross-venture
grouping by kind. The page states freshness instead of pointing at the compliance
dashboard for it.

`GET /api/revocations/blast-radius` counts what a revocation would stop, before it is
issued - agents, live grants, in-flight calls, shifts today, and the forward-looking
effect. It is a read against existing state and says nothing about authority; the console
still pre-checks nobody's permission. The same figures are stored on the revocation when
it is issued, because recomputing them later answers about today's grants rather than the
ones it stopped.

`POST /api/revocations/{id}/reinstate` takes `second_human`, required at `venture` and
`forge` scope and refused if it names the caller. `GET /api/revocations/targets` and
`/history` back the pickers and the regulator-export view.

## Known gaps

*Last verified: 2026-08-23.*

- **`ASSUMPTION` — bearer tokens, not SSO.** Part 14 declares
  `auth_method: sso_mfa | mfa_only`. Real SSO is an external provider that does not
  exist yet (same class as Vault). The column records the intent; the API authenticates
  a hashed bearer token. To change: implement the OIDC exchange; everything downstream
  is unaffected.
- **No token rotation or expiry.** A token is valid until the human is suspended.
- **No rate limiting on the API itself.** Agents are rate-limited; humans are not.
- **No CORS configuration** — needed before a browser app on a different origin can
  call this.
- **`POST /api/signoffs` still accepts a caller-supplied hash.** Provisioning has its
  own route that does not, but the general one is unchanged, so a Gate 10 signature can
  still be created against an arbitrary hash by calling it directly. Narrowing it needs
  a per-gate artifact resolver, which does not exist for the gates outside Part 11.
- **Gate sign-off does not yet read the Pack's declared `gate_signoff_policy`** — the
  API takes `distinct_humans` as a request field rather than resolving it from the Pack.
