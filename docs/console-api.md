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
seven routes and rejects any path containing `certification`, `flush`, `ledger`, `shift`,
`memory`, `grant` or `audit`. If a new route trips it, the question is not how to make it
pass — it is whether that route should exist.

| Write route | Delegates to |
|---|---|
| `POST /api/revocations` | `revocation.revoke` |
| `POST /api/revocations/{id}/reinstate` | `revocation.reinstate` |
| `POST /api/proposals/{id}/decide` | `proposals.decide` |
| `POST /api/dispositions/resolve` | `sweeps.disposition` |
| `POST /api/instructions` | `instructions.author` |
| `POST /api/ventures/{id}/reverse-hard-cap` | `budget.reverse_hard_cap` |
| `POST /api/signoffs` | `humans.sign_off` |

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

## Known gaps

- **`ASSUMPTION` — bearer tokens, not SSO.** Part 14 declares
  `auth_method: sso_mfa | mfa_only`. Real SSO is an external provider that does not
  exist yet (same class as Vault). The column records the intent; the API authenticates
  a hashed bearer token. To change: implement the OIDC exchange; everything downstream
  is unaffected.
- **No token rotation or expiry.** A token is valid until the human is suspended.
- **No rate limiting on the API itself.** Agents are rate-limited; humans are not.
- **No CORS configuration** — needed before a browser app on a different origin can
  call this.
- **The Next.js console does not exist yet** (increment 2).
- **Gate sign-off does not yet read the Pack's declared `gate_signoff_policy`** — the
  API takes `distinct_humans` as a request field rather than resolving it from the Pack.
