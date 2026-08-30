# Onboarding a Forge — the adapter, and three things that fail silently

CRE Forge is the first Forge The Office can actually call. Seven more follow, and
`medlink-wholesale/backend/app/api/forge.py` is the template they will be copied from.

This document exists because of how Phase 0.8 actually went. The adapter was designed,
reviewed, and read carefully before anything ran. Three defects survived all of that and
were found only by making a real call. **Every one of them returned a plausible success**
— no exception, no error log, a 200 in the response — which is why reading did not catch
them and why they are worth writing down.

If you are onboarding Forge number two, read this section before you write code.

---

## The three that fail silently

### 1. A grant below `auto_execute` never reaches the Forge

The first Phase 0 grant was issued at `suggest`, with a comment in the source calling it
"the weakest tier that still permits a call".

That is wrong. Step 7 of the client library turns anything below `auto_execute` into a
**proposal**, and makes no Forge call at all:

```
7. trust tier gate     below auto_execute -> proposal, and no Forge call
```

A `suggest` grant produces a proposal row, no ledger row, and no HTTP request. Nothing
fails. If you are testing an adapter and the Forge never sees traffic while The Office
reports no error, check the tier before you check the network.

Note that the *certified* tier caps the declared tier (Part 10.1), so both the grant and
the Unit A/Unit B certifications must be at `auto_execute`. Setting only the grant leaves
it capped back down.

**Choose the tier from what the module does, not from caution.** `auto_execute` on a
read-only lookup is the right call; the instinct to grant the lowest tier produces
something that cannot be tested at all.

### 2. A module with no manifest row is a violation on every call

`venture_forge_manifest` must contain a row for `(venture_id, forge_id, module_id)`
before any call. Step 4 of the call path raises `ManifestViolation` **and opens a HIGH
incident**, before the tier gate and regardless of what the caller holds:

| manifest state | verdict | consequence |
|---|---|---|
| in manifest, required | `required` | proceeds |
| in manifest, not required | `declared_only` | proceeds, records `IN_USE_NOT_REQUIRED` |
| not in manifest | `UNDECLARED` | HIGH incident, throttle, **BLOCK** |

A grant without a matching manifest row is a grant whose every call is a governance
violation. In normal operation `runtime_config.apply` writes both together at the end of
the provisioning ladder, so they cannot drift apart — anything issuing a grant outside
that path has to write the manifest row itself.

`criticality` is `hard` or `soft`. It is not `high`/`medium`/`low`, and the CHECK
constraint is the only thing that will tell you.

### 3. The trace header is `X-Office-Trace`, not `X-Office-Trace-Id`

The first adapter read `X-Office-Trace-Id`. FastAPI bound it to `None` on every request,
the call returned 200, the ledger row was written, and the correlation id — the single
value that joins The Office's ledger to the Forge's own logs — was silently absent from
the Forge side.

**A header read under the wrong name does not fail. It reads as absent.**

Copy these from `broker/executor.py` rather than inferring them:

| header | source |
|---|---|
| `X-Office-Agent-Id` | `office_agent_id` on the resolved grant |
| `X-Office-Venture` | `venture_id` |
| `X-Office-Trace` | the trace id generated per call |
| `X-Office-Forge-Api-Version` | `forge_registry.api_version` |
| `Idempotency-Key` | derived, present only for modules that support it |
| `Authorization` / `X-Api-Key` | per `forge_registry.auth_model` |

The Forge answers with `X-Forge-Request-Id`, which The Office stores as
`agent_call_ledger.forge_side_ref`. That pair is what makes a call traceable from either
end; assert on it in whatever check you write, because both sides return 200 without it.

---

## What an adapter is, and is not

The Office posts to `{forge_registry.base_url}/{module_id}` with a JSON body. The
adapter's whole job is to map that onto the Forge's own service layer and return the
result.

**It decides nothing.** By the time a request arrives, The Office has already checked
the grant, certification state, revocation, shift, manifest, budget, tier and rate limit,
and has written an audit entry *before* the call. An adapter that re-checks any of that
adds a second authorization system — and it is the one nobody audits, because the adapter
writes neither an audit entry nor a ledger row. The two will disagree the first time
either changes.

The only thing an adapter refuses is a caller who cannot present the tenant credential.
That is authentication, not authorization.

**It contains no business logic.** Call the same service the Forge's own HTTP endpoint
calls. Do not reimplement the query, and do not make an HTTP hop back into the same
process. A second implementation is a second thing to keep correct.

**It fails closed when unconfigured.** With no tenant credential configured, return 503
rather than serving the surface unauthenticated. An adapter that treats "no credential
set" as "allow everything" is how an open endpoint reaches production.

**Its logs must actually emit.** CRE Forge configures no logging — the root logger sits
at WARNING with no handlers — so the adapter's identity lines were formatted and dropped.
A log line that never appears is not a record. Check the effective level of whatever
logger you use before trusting that the correlation is being written down.

## Checklist for Forge number two

- [ ] `forge_registry` row: `base_url` pointing at the adapter, correct `api_version`,
      `auth_model`, `credential_mode`
- [ ] `forge_tenant_credential` row with a `credential_ref`, and the value resolvable
      (`env://NAME` in development) — never the value in the table
- [ ] `forge_module_registry` rows for each module, with honest `is_mutating` and
      `idempotency_support`
- [ ] `venture_forge_manifest` row per venture × module — **or every call is UNDECLARED**
- [ ] Grant at `auto_execute`, with Unit A and Unit B certifications at the same tier —
      **or no call is made at all**
- [ ] Adapter reads the header names above verbatim from `broker/executor.py`
- [ ] Adapter returns `X-Forge-Request-Id`
- [ ] Verified: 401 with no credential, 401 with a wrong one, 404 for an unimplemented
      module, 200 with the agent id and trace id visible in the Forge's own log
- [ ] Verified: the ledger row's `forge_side_ref` matches the id in the Forge's log

## Worked example

`medlink-wholesale/backend/app/api/forge.py`, and on The Office side
`broker/bootstrap_phase0.py`, which issues the identity, certifications, grant, shift and
manifest row that Phase 0.8 needed. The bootstrap exists because grants are otherwise
only written at the end of the sixteen-gate provisioning ladder; it is not a pattern to
copy for a production Forge, which should be onboarded through a Pack.
