# A module that must never be granted

## What this is for

Some endpoints return a plausible success for work that never happens. An agent granted
one gets a 200, and The Office writes a ledger row saying a call was made — which is
true, and which reads afterwards as evidence that the work was done. It was not.

That is a false green with an agent behind it, and the ledger is the thing that makes it
durable. A refusal is recoverable; a record of work that did not happen is not.

Three shapes, all found while onboarding CapitalForge:

| shape | what it looks like | example |
|---|---|---|
| `inert` | persists or records something no runner ever consumes | `POST /api/platform/workflows` — the platform's own GET answers `execution: {runs: false}` |
| `stubbed` | calls a stub client that fabricates a third-party response | `voiceforge.service.ts` uses a `TwilioStubClient` declared inside itself and returns invented Twilio SIDs |
| `refuses` | answers 501 by design | eleven endpoints, each stating why in its body |
| `attributed` | answers about a subject it never read, from values the caller supplied | `GET /api/readiness/:businessId` scores from query parameters and stamps the businessId on the result |
| `fabricated` | answers 200 with invented figures presented as a record | `POST /api/rewards/:clientId/export` reported per-programme points balances, identical for every client, in a domain whose own balance endpoint is a 501 |

## How it is enforced

Two layers, the same way append-only is two layers.

1. **A BEFORE INSERT trigger on `agent_forge_grant`.** Two production paths write grants
   — `generators/runtime_config.py` at the end of the provisioning ladder and
   `broker/bootstrap_phase0.py` — and a future third will not consult a Python constant.
   The database refuses, and the refusal carries the recorded reason rather than a bare
   constraint name.

2. **`grants.resolve_grant` raises `ModuleExcluded`.** For a grant that predates the
   exclusion, or one written by a superuser, and to turn a constraint violation into an
   audited reason (`call_refused_module_excluded`). It is checked *before* identity
   status and everything else about the agent: an exclusion is true of every agent, so
   reporting a suspended identity first would bury the reason that matters.

**INSERT only.** Revoking a grant is an UPDATE of `revoked_at`, and a grant for an
excluded module must stay revokable. A trigger that fired on UPDATE would make the
dangerous case permanent, which is the opposite of the intent.

## Why the table has no foreign key

`forge_module_registry.forge_id` references `forge_registry`, so a module row cannot
exist before its Forge is onboarded — and that is exactly the wrong moment. An exclusion
recorded after the registry rows are written is a reaction. One recorded before is a
prevention, and the prevention is the whole value.

`forge_module_exclusion` therefore references nothing. It records a finding about a
codebase, and a finding does not become true when somebody gets around to registering
the Forge.

## The one way this can be defeated by accident

The exclusion is keyed `(forge_id, module_id)`. CapitalForge is not onboarded, so
recording the exclusion first is also what **fixes the vocabulary**: whoever writes
`forge_module_registry` rows for CapitalForge has to use these `module_id` values for
these endpoints. Register `POST /api/platform/workflows` under a different name and the
exclusion silently misses, and the module becomes grantable.

`broker/module_exclusions.py` is the declared list, with the file and symbol that justify
each one, so the names are reviewable in a diff before they are needed.

## Working with it

```
.venv/Scripts/python scripts/apply_module_exclusions.py           # apply (idempotent)
.venv/Scripts/python scripts/apply_module_exclusions.py --check   # verify, exit 1 on drift
```

`--check` is the CI form: a declaration that was never applied is the same failure as no
declaration at all, and it is invisible from the code alone.

The seeder **never deletes**. Removing an exclusion re-opens a module for granting, and
that is not something a seeder should do as a side effect of an edit. Remove the row
deliberately, with the evidence that it no longer applies.

Requires `OFFICE_ADMIN_DSN` — `office_app` holds SELECT and nothing else, because
recording an exclusion is a deliberate act, not something the broker does to itself
mid-call.

## What is recorded today

Nineteen modules on `capitalforge`: three `platform_workflow_*`, four VoiceForge call
and outreach modules, the eleven 501s, `rewards_export`, and `readiness_score`.

`readiness_score` is the one to read if you only read one. It is the quietest module
on the Burkham Pack's list - a score, arithmetic, nothing that touches a person - and
it never opens the record it reports on. Everything it scores is asserted by the
caller in the query string, and the response carries the businessId as though the
business had been consulted. Ordering an audit by blast radius would have reached it
last. Reasons and evidence per module are in
`broker/module_exclusions.py`.

**Not excluded**, and worth stating because the two look alike:
`POST /api/workflow/rules` and `POST /api/workflow/evaluate` are real —
`workflow-engine.service.ts` reads active `WorkflowRule` rows and returns matched
actions, blockers and an approval chain. Evaluate computes; it never claimed to execute.

The two surfaces do write the same `workflowRule` table in incompatible shapes, though:
`platform` writes `conditions: {expression: string}` while the engine reads them as
`RuleCondition[]` and calls `.every()`. One platform-created rule makes `evaluateRules`
throw for every rule in that tenant. Excluding `platform_workflow_*` protects
`workflow_evaluate` as much as it protects the caller.

The exclusion only stops an **agent**. A human calling that endpoint still poisons the
table, so it is filed against the Forge as
[navigreen311/Capitalforge#81](https://github.com/navigreen311/Capitalforge/issues/81)
and has to be fixed there regardless of what The Office does.
