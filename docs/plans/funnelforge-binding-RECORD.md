# FunnelForge — the binding, what it cost, and what it cannot yet do

**Record, 9 September 2026. Written by P-13 against a running FunnelForge.**

`docs/plans/funnelforge-animaforge-surface-PROPOSAL.md` proposed nine modules and the
condition they turn on. This is what happened when they were built: what held, what did
not, and the price the next person pays.

---

## The six-step price of a seventh template

**Recorded because §4.5 expects the inventory to grow** — *"the number of approved
templates should grow as patterns solidify"* — so somebody will pay this, and it is
better chosen than discovered.

Adding one autonomous template under module-gating costs six steps:

| # | step | where | who can do it | automatable |
|---|---|---|---|---|
| 1 | bind the module in the adapter, template closed over | `adapters/funnelforge/` | engineer | yes |
| 2 | `forge_module_registry` row — `is_mutating`, `idempotency_support` | The Office | `scripts/register_funnelforge_modules.py` | **yes, now** |
| 3 | `venture_forge_manifest` row for the venture | The Office, via the ladder | provisioning run | yes |
| 4 | **operating instruction** — the manual, authored against the code | The Office | author | **NO** |
| 5 | **curriculum** — scenarios exercising the module | Pack, then generator | author, then generator | **NO** |
| 6 | certification — Unit A per agent, Unit B per department | SimForge verdict | certification run | yes |

**Steps 4 and 5 are the expensive ones and they are not automatable.** A manual is
written against what the code does — `docs/forge-adapter.md`'s §2 audit found manuals
asserting middleware that does not exist, and an assurance makes a reader confident and
wrong where an omission only leaves them uncertain. `PENDING_AUTHORING` is a Pack
placeholder rather than a row. Until both exist the position operating the new template
is unfillable, and Gate 4.5 reports that as a **capacity shortfall rather than a missing
certification** (`docs/decisions.md` entry 11).

**Step 2 moved off the not-automatable list on this branch.** It was a row a human typed
— which is the reason V6 compares two claims, the reason `property_lookup` sat recorded
`is_mutating: TRUE` for months while being a search, and the reason V31 will not PASS on a
`verification_method = 'hand'` row. `generators/forge_module_rows.py` now derives the row
from the adapter's dispatch map intersected with the Pack's declaration. That is a change
to the price of every future Forge, not only to FunnelForge's.

**This is a consequence of module-gating, not a defect in it.** The gate has to live
somewhere; putting it in the module list means the module list is what changes when the
gate changes. §4.5 itself says the review gate on new templates is strict and that it is
*"better to route to human than to add a marginal template"* — a process that makes
adding a template deliberate is aligned with that rather than fighting it.

**What would change the price:** a per-template approval scope and a readable compliance
state, both upstream in FunnelForge. With those, a seventh template costs one row in
FunnelForge and nothing in The Office, because the module stops being the gate. Today's
friction buys a gate that exists; the fields buy the friction back.

---

## Ports: running and reachable are different states, and both were measured

**Every probe below read a response body.** Not a status code, not a container being up.

`docker ps` is the authority, not the compose file — and here they disagree.

`C:/Users/ivann/Projects/funnelforge/docker-compose.yml` publishes ports: `5432:5432`,
`3001:3001`, `3000:3000`, `3012:3012`. **The running containers were not created from it.**

```
docker inspect funnelforge-api --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'
  C:\Users\ivann\Projects\ff-docker\docker-compose.prod.yml
```

That file **does not exist on disk.** The project directory `C:/Users/ivann/Projects/ff-docker`
is there; the compose file the fifteen containers were created from is gone. Whatever is
running cannot be reproduced from anything in either repository.

**Fifteen containers up, none publishing a host port.** `docker ps` shows `3001/tcp`,
`3000/tcp`, `5432/tcp` — exposed, not published. `HostConfig.PortBindings` on
`funnelforge-api` is `{}`. A sixteenth container, `funnelforge-nginx` — the one that would
have published — is **`Exited (127) 2 weeks ago`**. Exit 127 is "command not found". The
ingress has been dead for a fortnight and every other container has been healthy
throughout, which is exactly the state where "the stack is up" and "anything can reach it"
come apart.

So the probes went in over the docker network:

```
docker run --rm --network ff-docker_funnelforge-network curlimages/curl -s http://api:3001/health
  {"status":"ok","timestamp":"2026-09-09T17:34:23.318Z"}
```

**Reachable from inside, unreachable from the host.** A `base_url` for
`forge_registry` therefore cannot be written yet: The Office would have to sit on that
network, or the ingress has to come back. This is recorded, not fixed.

### Every operation, called, with the answer read

`docs/forge-adapter.md` trap #4: *"Call every operation of every module against a running
Forge before you register a single row. Not one per module — every operation, because the
two that were wrong sat beside fifteen that were right."*

| operation | answer |
|---|---|
| `POST /api/leads/capture` | `500 {"code":"P2003","message":"...Foreign key constraint violated: 'Lead_businessId_fkey (index)'"}` — reached the database |
| `POST /api/analytics/track` | `500 {"code":"P2003",...'AnalyticsEvent_funnelId_fkey (index)'}` — reached the database |
| `POST /api/scheduling/public/{id}/{slug}/book` | `404 {"success":false,"error":{"message":"Booking type not found or inactive"}}` — a **domain** 404; the handler ran |
| `POST /api/emails/send` | `401 FST_JWT_NO_AUTHORIZATION_IN_HEADER` |
| `GET /api/analytics/dashboard` | `401 FST_JWT_NO_AUTHORIZATION_IN_HEADER` |
| `POST /api/emails/templates` | `404 {"message":"Route POST:/api/emails/templates not found"}` — a **routing** 404 |
| `GET /docs/json` | **200, zero bytes** |

The last two are the ones worth keeping. The pair of 404s have different shapes and mean
different things, and only reading both bodies separates them. And `GET /docs/json`
answering 200 with an empty body is the shape of a false green: "the API publishes
OpenAPI" is true and buys nothing. The route list in `adapters/funnelforge/upstream.py`
was read out of `apps/api/src/modules/*/routes.ts` and then called.

**A caveat on the two 500s.** A foreign-key violation is strong evidence the binding
reaches the handler and weak evidence about anything past it. Neither has been called with
a real `businessId` or `funnelId`, because creating Burkham data inside FunnelForge is not
P-13's to do. The binding is *verified as far as the database and no further*, and that
distinction is the whole of trap #4.

---

## What the proposal assumed and what is actually there

The proposal established that FunnelForge holds neither fact the send gate needs — no
per-template approval scope, no compliance state. That still holds; `model EmailTemplate`
is unchanged.

**A second fact was found on 9 September and it is stronger: there is no send-from-template
path in FunnelForge at all.**

- `POST /api/emails/send` takes `to`, `subject`, `html`. No `templateId`.
- `POST /api/emails/broadcast` takes `businessId`, `subject`, `body`. No `templateId`.
- `POST /api/emails/templates` is 404. `packages/sdk-js/src/resources/emails.ts` declares
  template CRUD against `/api/emails/templates`; `apps/api/src/modules/emails/routes.ts`
  implements none of it. **The SDK describes an API that is not there.**
- `EmailQueue.templateId` is written by four call sites and read by none. The sender is the
  BullMQ `email-send` queue and it carries rendered content.

So *"the handler hardcodes its template id"* could not mean an id FunnelForge resolves.
The design survives; the mechanism moved. The approved copy is in
`adapters/funnelforge/templates.py`, in git, behind the same review gate §4.5 asks for,
and the handler sends the body it was bound to. **The approved-copy library for autonomous
send is a Python module, not a FunnelForge table** — stated plainly because that is a
consequence a reader should meet rather than infer.

This is the third instance of `docs/forge-adapter.md`'s *"does the Forge have anything to
gate on"* check, and the first two steps passed while step 2 failed again: name the fact,
**find the column**, and if there is no column the refusal cannot be written. There was no
column for the approval scope, and this time there was no *route* either.

---

## V31 refuses seven of the nine at the only tier that calls

**The largest finding on this branch, and it must not be fixed by softening a declaration.**

Seven modules are `is_mutating=True, idempotency_support="at_most_once"`: the six approved
sends and the booking. V31 refuses `auto_execute` over exactly that shape, and
`auto_execute` is the only tier that reaches a Forge at all — step 7 of the client library
turns anything below it into a proposal and makes no HTTP call.

**So seven of the nine cannot today be granted at a tier that makes a call.**

The declarations are right. An email leaves the system and reaches a person; a retry sends
a second one, and `EmailQueue` holds `templateId`, `recipient`, `status`, `scheduledAt` and
nothing that would recognise a repeat. The booking is `prisma.appointment.create` with no
de-duplication. V31 is right to refuse them.

The Pack declares the Marketing Operations Coordinator at `auto_execute` because §4.5 says
these sends are Village-autonomous. Declaring `propose` instead would make V31 pass
vacuously over a surface that never calls anything — a different thing wearing autonomous
send's name. The refusal is the honest output.

**What would change it: an idempotency key on FunnelForge's send path.** That is a
FunnelForge change and it is not The Office's to make. Until then the two grantable
modules are `capture_contact` (natural) and `read_funnel_analytics` (non-mutating).

The proposal said *"`at_most_once` throughout, and not defensively"* and was right about
the classification; it did not carry the consequence forward to V31. Carried forward here.

---

## Three more things found by reading handlers

None of these is visible to `_modules`, `verify_forge_modules.py` or `check_module_manuals.py`,
because none of those calls anything.

**1. `capture_contact` can send email through a path no module gates.** On a *new* lead,
`POST /api/leads/capture` auto-enrols it in the business's active `WELCOME` sequence
(`apps/api/src/modules/leads/routes.ts`). Module-gating stops an agent *naming* a send; it
does not stop a non-send module *triggering* one. The approved-template refusal never runs
on that mail. **This is a real hole in module-gating and it is not closable from The
Office** — it closes by there being no active `WELCOME` sequence on the Burkham business,
which is an operational fact nobody currently checks.

**2. That route's `isNew` flag is wrong.** It returns `isNew: !body.funnelId` — derived
from whether a funnel id was supplied, not from whether the lead was new. `capture_contact`
does not pass it on rather than forwarding a field that does not mean what it says.

**3. There is no tenant credential.** `server.decorate('authenticate', ...)` verifies a
**user JWT**, and `x-api-key` / `apiKey` appear nowhere in the API's middleware or plugins.
So `auth_model` is `bearer` and what The Office would broker is one user's token: every
agent's call is attributable to a single FunnelForge account, and FunnelForge's own audit
trail cannot tell agents apart. The Office ledger stays the per-agent record, which is what
`broker/executor.py` already says about `credential_mode: brokered` — but it is worth
knowing that here the Forge side is *structurally* unable to help, rather than merely not
yet configured.

**And one about exposure.** `POST /api/leads/capture` and `POST /api/analytics/track` are
unauthenticated writes that reach the database, available to anything on
`ff-docker_funnelforge-network`. Recorded, not fixed; FunnelForge's own.

---

## What this branch delivers, and what it does not

**Delivered — steps 1, 2 and 3 for all nine modules:**

- the adapter and its bindings (`adapters/funnelforge/`), with the two refusals in the
  handler and tests that call the handler directly;
- `generators/forge_module_rows.py` and `scripts/register_funnelforge_modules.py`, which
  derive the nine `forge_module_registry` rows rather than anyone typing them;
- the Pack binding and the position, so generators 5.1 → 5.3 → 5.6 produce a
  `venture_forge_manifest` entry per module — asserted end to end in
  `tests/adapters/test_funnelforge_rows.py`.

**Not delivered — steps 4, 5 and 6, owed for all nine:**

No operating instruction, no curriculum, no certification. **This is the six-step price
being paid rather than a gap that was overlooked.** Steps 4 and 5 are the two the record
above says are not automatable: nine manuals authored against the code, at the standard
`docs/instructions/capitalforge-*.md` sets (130–315 lines each, with §2 claims that must be
true), plus scenario content. Producing nine of each mechanically to clear
`check_module_manuals.py` is precisely the pressure that check is documented as applying
and precisely the thing it warns against — *"registering a name to clear that line is how
`lender_match` happens."*

Until they exist the Marketing Operations Coordinator is unfillable and Gate 4.5 reports a
capacity shortfall, which is entry 11's behaviour working, not failing.

**Also not done, and each blocked on something outside this package:**

- no `forge_registry` row — there is no `base_url` to write while the ingress is dead and
  the containers publish nothing;
- no `forge_tenant_credential` row — there is no tenant credential to hold;
- the adapter is not deployed anywhere. It is authored and tested in this repository
  because P-13's scope is `theoffice`; the FunnelForge repository was read and not
  modified. V32 will report NOT_RUN for FunnelForge until it is deployed and reachable,
  and **NOT_RUN is the correct answer there, not a defect in the Pack.**

---

## The Pack edit was held back at merge — coordinator, 2026-09-09

**The adapter, the generator, the registration script and every test merged. The position
declaration did not.** It is preserved verbatim as
`docs/plans/funnelforge-position-DEFERRED.patch` — `git apply` it and the position returns
exactly as authored, comment and all.

### Why, measured rather than argued

Adding `Marketing Operations Coordinator` to the Pack moves **Burkham's Gate 2 from 0 FAIL to
3 FAIL**:

| | before | with the position |
|---|---|---|
| Burkham Gate 2 | **33 PASS / 0 FAIL / 1 NOT_RUN** | **28 PASS / 3 FAIL / 3 NOT_RUN** |

- **V6** — the nine modules are not in `forge_module_registry`
- **V11** — no Forge Operating Instructions authored for any of them
- **V23** — no scenarios for `Marketing Operations Coordinator`
- **V31 → NOT_RUN** — *"nothing verified is known about the shape of"* those modules. **The
  rule this package's design condition is about does not even run**, which is worth saying
  plainly: the expected V31 failure is not what happens. Something earlier stops first.
- **V32 → NOT_RUN** — `funnelforge: not in forge_registry`

### What this is, and what it is not

**This is not a rejection of the package's judgement — it is the split the package itself
argued for.** P-13 declined to generate nine manuals mechanically to clear
`check_module_manuals.py`, on the grounds that doing so is *"exactly the `lender_match`
pressure that check warns against"*. That was right. The consequence it did not have a way to
avoid is that the Pack edit lands the **declaration** while the artifacts that satisfy it stay
owed — so the venture stops passing a gate it was passing, for work that is correctly not
done yet.

**A declaration and its evidence have to land together.** That is the same rule the human-held
obligation work arrived at from the other direction, and the same one B26 broke by tightening a
schema in git without migrating what was in force.

**Run `def65e4f` is unaffected** — it is past Gate 2 and pinned to pack `0.6.0`. What was at
risk was the next run, which would not have reached Gate 4 at all.

### What re-applies it

**Steps 4, 5 and 6 for all nine modules** — operating instruction, curriculum, certification —
plus the registry rows, which `generators/forge_module_rows.py` now derives rather than asking
a human to type. Then `git apply docs/plans/funnelforge-position-DEFERRED.patch`, republish,
and Gate 2 should return to 0 FAIL with V31 finally **running** — and, per this package's own
finding, **failing on seven of the nine**, which is the honest declaration and must not be
softened at either end.
