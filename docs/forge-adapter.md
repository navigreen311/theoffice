# Onboarding a Forge — the adapter, and four things that fail silently

CRE Forge is the first Forge The Office can actually call. Seven more follow, and
`medlink-wholesale/backend/app/api/forge.py` is the template they will be copied from.

This document exists because of how Phase 0.8 actually went. The adapter was designed,
reviewed, and read carefully before anything ran. Three defects survived all of that and
were found only by making a real call. **Every one of them returned a plausible success**
— no exception, no error log, a 200 in the response — which is why reading did not catch
them and why they are worth writing down.

The fourth was added after CapitalForge, and it is the one this document did not warn
about. The first three were all caught here by a reader who had this page open. The
fourth was not, and it was found the same way the first three were.

If you are onboarding Forge number two, read this section before you write code.

---

## The four that fail silently

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

### 4. A manifest can be consistent with everything and still wrong about upstream

Two verifiers stand behind the module list, and **neither of them calls anything.**

    verify_forge_modules.py    forge_module_registry rows  vs  GET /_modules
    check_module_manuals.py    docs/instructions/*.md      vs  GET /_modules

Both read the manifest. The manifest is derived from the dispatch map, so it is honest
about *which names are bound* — that is the property the whole design rests on, and it
holds. What neither verifier can see is **what the bound handler does when it is
called**, because neither one calls it.

So a binding can be green on every axis and broken on every request:

| axis | says |
|---|---|
| `_modules` | the name is bound — **true** |
| `forge_module_registry` | a row exists and matches — **true** |
| the operating instruction | a manual describes it — **true** |
| the actual call | 400 on every attempt |

**Two of CapitalForge's seventeen operations were exactly this.**

    client_read_credit / history    `profileType` is a REQUIRED query parameter on the
                                    upstream route, not an optional filter. The binding
                                    omitted it. Every call answered
                                    PROFILE_TYPE_REQUIRED.

    record_consent / grant          The binding invented `method` and `notes` and omitted
                                    `consentType`, which GrantConsentBodySchema requires.
                                    Every call answered VALIDATION_ERROR.

Both had passed design review, `tsc`, `eslint`, a 4,000-test suite, and both verifiers.

**Why the unit tests did not catch it.** The adapter's tests inject a fake inner caller
and assert the request the adapter *built* — the path, the method, the body. That is the
adapter's own belief about what upstream wants, checked against itself. A test written
that way can only ever confirm the assumption it was written from. It will tell you the
binding is stable; it cannot tell you the binding is right.

**Why it does not look like a defect when it happens.** These do not fail silently
per-call — they fail loudly, with a clear code and a sensible message. They fail silently
at the *conformance* level: nothing that watches the Forge is watching answers, so the
signal never reaches anyone, and the first human to see one reads
`PROFILE_TYPE_REQUIRED` as bad test data rather than as a wrong binding.

**The rule.** Call every operation of every module against a running Forge before you
register a single row. Not one per module — every operation, because the two that were
wrong sat beside fifteen that were right. `_modules` tells you a handler is bound;
only a real call tells you the binding reaches the thing the manual describes.

Fifteen of seventeen were correct. That ratio is the argument: an adapter written
carefully from the route definitions is *mostly* right, which is precisely what makes
the remainder hard to find by reading.

**A related one that calling does NOT catch: a registry value that resolves and is
wrong.**

`forge_module_registry.compliance_flags_implied` on `record_consent` was written as
`per_connection_authorization_required`. That flag exists, resolves against the
Pack, and passes every check there is. It is also GLBA — `compliance/glba-plaid-connection-v1`,
a **bank account** connection. `record_consent` records consent to be contacted by
email, SMS or voice. The value was chosen by matching on the word "connection", and
it put a bank-data coupling on a communications-consent module.

Calling the module does not find this: the module works. The verifier does not find
it either — `verify_forge_modules.py` checks that a row resolves against the
adapter, not that its *values* are the right ones, and a flag that exists is a flag
that resolves.

**Nothing in this system checks that a compliance flag is the correct flag.** It was
found by reading the Pack's `compliance_surface` to see which framework each flag
belongs to. That is the check, and it is a human one: for every flag on a module,
name the framework it comes from and say why this module implies it. If the sentence
does not come out true, the flag is wrong.

---

## A fifth: a module that answers without doing the work

The four above are defects in the adapter or its bindings. This one is a property of
the Forge, and it is worse, because nothing about the call looks wrong at either end -
not even a real call, which is what separates it from #4.

CapitalForge has three shapes of endpoint that return a plausible success for work that
never happens:

    inert     `POST /api/platform/workflows` persists a rule. No scheduler, runner or
              cron consumes it. The platform's own GET says so in its response body:
              `execution: {runs: false}`.
    stubbed   The VoiceForge call endpoints record a call and dial nobody -
              `voiceforge.service.ts` uses a `TwilioStubClient` declared inside itself
              which returns fabricated SIDs. The production Twilio client exists, and
              is imported only by the SMS path, which is live. The endpoint named
              "initiate outbound call" is the inert one.
    refuses   Ten endpoints answer 501 by design.

Grant one of these and the agent gets a 200, and The Office writes a ledger row saying
a call was made. That is true, and it reads afterwards as evidence that the work was
done. **Check what is on the other end of a module before you certify an agent for it.**
An endpoint's name is not evidence that it does the thing.

These are recorded in `forge_module_exclusion` and enforced by a BEFORE INSERT trigger
on `agent_forge_grant`, so no writer can grant one - see `docs/module-exclusions.md`.
Record the exclusion **before** onboarding: the table deliberately has no foreign key to
`forge_registry`, because an exclusion written after the registry rows exist is a
reaction, and one written before is a prevention.

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

---

## The module manifest, and why the adapter is the naming authority

**Every adapter must serve `GET {base_url}/_modules`**, authenticated with the same
tenant credential as a module call, returning the dispatch map's keys:

```python
return {"forge": "cre-forge", "modules": sorted(MODULES)}
```

The entry for each module carries three fields:

```json
{"module_id": "underwrite_deal", "is_mutating": true, "idempotency_support": "natural"}
```

### Write `sorted(MODULES)`. Never a literal list.

This is the only answer in the whole path that is not a declaration.

The Office's `forge_module_registry` rows are rows a human typed. A Business Pack's
`modules_expected` is a list a human typed. V6 compares those two, which means it
compares two claims and can find a typo — the Burkham Pack declared twelve modules,
three of them did not exist, and V6 passed on all twelve because somebody had written
twelve rows. `lender_match` was granted `auto_execute` over a capability that was not
there.

`sorted(MODULES)` is different because it is derived. A name is in the answer if and
only if a handler is bound to it: you cannot add the name without adding the function,
and you cannot delete the function and keep the name. A list maintained beside the dict
throws that away and is *worse* than the two declarations that already exist, because it
drifts silently while carrying the authority of having come from the Forge.
`test_manifest_is_derived_from_the_dispatch_map` fails the build if one appears.

### One of the three fields is derived. Two are declared.

`module_id` is derived — a name appears if and only if a handler is bound.

`is_mutating` and `idempotency_support` are **declared at the binding site**. They
travel with the handler rather than living in another system's table, and you cannot
bind a module without stating them, but they are still somebody's word. Say which is
which when you report them; do not let a reader believe the whole answer is derived.

They are checked rather than trusted:

- **At runtime.** A module declared `is_mutating=False` whose handler dirties the
  session is refused by `call_module`, its write rolled back, and a
  `office.call.contract_violation` logged. That is the only moment the truth is
  observable, and it is why the declaration is worth more than a registry row.
- **By The Office.** `scripts/verify_forge_modules.py` **corrects** the registry from
  the manifest rather than trusting the row. Its first run against CRE Forge moved
  `property_lookup` from `is_mutating: TRUE` to `FALSE` — it is a search, and the row
  had said otherwise since the day it was written.

This matters because V31 refuses `auto_execute` over a module that is mutating and
`at_most_once`. A row that understates mutation hands an unattended agent a writer, so
**V31 will not PASS on a `verification_method = 'hand'` row** — it reports NOT_RUN and
names the verifier. A *refusal* still stands on a hand-written row: blocking on a claim
that might be wrong is safe, and passing on one is not.

### What a green conformance check proves

**A handler is bound to that name.** Not that the handler works, and not that it does
what the name says.

This automates the half of the question that was being done by hand — does the module
exist — and does not touch the other half. `readiness_score` is bound, answers 200,
mutates nothing, and scores a business from query parameters it never reads. Nothing in
the manifest will ever find that. Reading the handler will, and the finding goes in
`forge_module_exclusion`.

### The adapter's keys are the spelling of record

> **If you are about to write `forge_module_registry` rows, read this.**

A `module_id` must be spelled exactly as the key in the adapter's dispatch map, because
`broker/executor.py` builds the URL as `{base_url}/{module_id}` — the id *is* the
address. Three separate things resolve against that one set of keys:

| | |
|---|---|
| a Pack's `modules_expected` | V32 refuses a Pack declaring a module the Forge does not dispatch |
| `forge_module_registry` | `scripts/verify_forge_modules.py` stamps the rows that resolve, and reports the ones that do not |
| `broker/module_exclusions.py` | the exclusion is keyed `(forge_id, module_id)` |

`docs/module-exclusions.md` names the one way an exclusion can be defeated by accident:
register an excluded endpoint under a second name and the exclusion silently misses, and
the module becomes grantable. Resolving every side against the adapter's keys closes
that mechanically instead of by memory — a second spelling does not quietly work, it
fails to resolve and V32 says so.

### Reserved prefix

Module ids must not start with `_`. That prefix belongs to the adapter's own endpoints,
and a module named `_modules` would shadow the manifest. Assert it at import beside the
dict rather than writing it down here only.

### The probe, and when it cannot answer

Where an adapter exists without a manifest, The Office falls back to
`OPTIONS {base_url}/{module_id}`: a bound path answers 405 or 200, an unbound one 404,
and no handler runs either way. An authenticated POST would answer the same question by
executing the module, which is not a thing to do to a mutating one.

It is calibrated on every run against an id that cannot exist, and **if that id does not
404 the probe reports NOT_RUN rather than PASS.** An adapter built on the CRE template
routes everything through one `POST /{module_id}`, so every id matches the path template
and nothing 404s — on that shape the probe is structurally unable to tell a bound module
from an absent one. Serve the manifest; the probe is there for Forges that cannot yet.

### NOT_RUN is the expected state before an adapter exists

A Forge with no adapter leaves V32 NOT_RUN, which blocks Gate 2. That is correct and it
is not a defect in the Pack: nothing has been resolved, so the Pack is unverified rather
than verified. All twelve of the Burkham Pack's modules are in that state today.

---

## Checklist for Forge number two

- [ ] `forge_registry` row: `base_url` pointing at the adapter, correct `api_version`,
      `auth_model`, `credential_mode`
- [ ] `forge_tenant_credential` row with a `credential_ref`, and the value resolvable
      (`env://NAME` in development) — never the value in the table
- [ ] Adapter serves `GET {base_url}/_modules` from `sorted(MODULES)` — derived from
      the dispatch map, never a literal list — with `is_mutating` and
      `idempotency_support` stated at each binding
- [ ] Every `is_mutating=False` handler verified against the runtime guard: a read that
      writes is refused and rolled back, not returned as a 200
- [ ] `forge_module_registry` rows for each module, spelled **exactly** as the adapter's
      dispatch keys, with honest `is_mutating` and `idempotency_support`
- [ ] **Every operation of every module called against a running Forge, and the answer
      read** — before any registry row is written. Not one call per module: the two
      CapitalForge bindings that were wrong sat beside fifteen that were right. See
      trap #4; the verifiers below cannot see this, because neither of them calls
      anything
- [ ] `scripts/verify_forge_modules.py --check` exits 0 — every row resolves against the
      adapter, and the adapter dispatches nothing the registry has not heard of
- [ ] `scripts/check_module_manuals.py` exits 0 — every bound module has an operating
      instruction. A manual with no module is reported, not failed: registering a name
      to clear that line is how `lender_match` happens
- [ ] `venture_forge_manifest` row per venture × module — **or every call is UNDECLARED**
- [ ] Grant at `auto_execute`, with Unit A and Unit B certifications at the same tier —
      **or no call is made at all**
- [ ] No `auto_execute` grant over a module that is `is_mutating` and `at_most_once` —
      V31 refuses it, because an unattended retry writes a second record of the same act
- [ ] Every module checked for a stub, a missing runner, or a 501 - and any found
      recorded in `forge_module_exclusion` **before** the registry rows are written
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

---

## The §2 audit, 3 September 2026

After `submit-application.md` §2 was found asserting a middleware that does not
exist, every manual's §2 was read for the same shape: a sentence naming a
middleware, guard, permission or gate.

**§2 is where this lives, because §2 is written by naming what stops you.** And the
direction matters more than the count. An omission leaves an agent uncertain; **an
assurance makes it confident and wrong**, and a curriculum built from an assurance
certifies the confidence.

Three claims found in ten manuals. Two false, one true, and the true one is the one
that carries.

### Confirmed true — the mount guard, verified at line level

Three manuals say it, and it is the load-bearing claim in three curricula:

> *"The mount guard runs before any handler here, so by the time a handler executes
> the client is known to exist and to belong to the caller's tenant."*

- `api/routes/index.ts:162-163` installs `requireOwnedBusiness('clientId')` on both
  `/clients/:clientId` and `/v1/clients/:clientId`
- the router mounts at `170-171`, **after** the guard
- `businessBelongsToTenant` runs `findFirst({where: {id, tenantId}})` — existence and
  tenancy in one query

It is what makes `client_read`, `client_read_pii` and `client_read_credit` able to
say `clientId` is guaranteed to exist and be the caller's. **Accurate as written**,
and worth recording as confirmed rather than merely not-flagged: the audit that
found two false claims also checked the one everything rests on.

### False — `record_consent` §2 named six submission gates

It listed credit-union membership disclosure among gates that run.
`submit-application.md` had said since it was written that the gate cannot fire.

**Cross-manual, which is what makes it the worst instance.** An agent reading
`record_consent` has no path to the correction — the contradicting statement is in a
manual it may hold no grant for.

### False — `record_consent` §2 named four SMS gates

Five run: `no_phone`, `dnc`, `no_consent`, `unknown_timezone`, `quiet_hours`. The
four named were right and in the right order, with an unnamed fifth between consent
and quiet hours. Wrong in the safe direction and wrong the same way.

### What the audit does not do

It checks claims that are *made*. A manual that never mentions a protection is not
audited by this, and three manuals had nothing to check —
`compliance_manifest_assemble`, `regulator_dossier_export` and `scan_communication`
describe absent capability rather than asserted protection.

**Run it again whenever a §2 is written.** The two false claims were both written by
somebody who believed them, and neither was found by review.
