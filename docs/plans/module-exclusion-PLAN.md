# Module exclusion — a module that must never be granted

## Problem

Onboarding CapitalForge surfaced three classes of endpoint that return a plausible
success for work that does not happen:

  1. `POST /api/platform/workflows` persists a rule. Nothing runs it — the platform's
     own `GET /workflows` says so in the response body (`execution.runs: false`).
  2. The VoiceForge call endpoints record a call and dial nobody. `voiceforge.service.ts`
     uses a `TwilioStubClient` declared inside itself which logs and returns
     `https://api.twilio.com/stub/...` SIDs. The production client exists and is
     imported only by the SMS path.
  3. Ten endpoints return 501 by design.

An agent granted any of these gets a 200, a ledger row, and no work. That is the
false-green the Phase 0.8 write-up is about, with an agent behind it.

## Why a new table rather than a column on `forge_module_registry`

`forge_module_registry.forge_id` references `forge_registry`, so a module row cannot
exist before the Forge is onboarded. CapitalForge is not onboarded — that is precisely
when the exclusion needs to exist, because an exclusion recorded after the registry
rows are written is a reaction, and one recorded before is a prevention.

`forge_module_exclusion` therefore carries **no foreign key to `forge_registry`**. It is
a finding about a codebase, not operational state about a registered Forge, and it has
to outlive and precede registration.

Alternatives considered:

| option | why not |
|---|---|
| Column `is_callable` on `forge_module_registry` | Cannot exist before the Forge is registered. Also invites the reading that absence of a row means callable. |
| Rely on absence — never write the registry row | Absence is not a record. The next person onboarding CapitalForge generates module rows from the route table and sweeps these back in, with nothing to stop them. |
| Denylist constant in code only | Matches `forge_map.ESTATE` idiom, but the grant path is not the only writer — `generators/runtime_config.py` and `bootstrap_phase0.py` both INSERT grants. A constant guards the paths that remember to consult it. |

Chosen: the table, plus a **BEFORE INSERT trigger on `agent_forge_grant`**, so no writer
can bypass it, plus the declared constant as the reviewable source the seeder applies.

## Enforcement points

  1. `agent_forge_grant` BEFORE INSERT trigger — refuses the grant at the database.
     INSERT only, deliberately: revoking an existing grant is an UPDATE, and revocation
     of an excluded module must stay possible. Guarding UPDATE would make an excluded
     grant unrevokable, which is the opposite of the goal.
  2. `grants.resolve_grant` raises `ModuleExcluded` — defense in depth for a grant that
     predates the trigger or was written by a superuser, and the place the refusal
     becomes an auditable reason rather than a constraint error.

## Not excluded

`POST /api/workflow/rules` and `POST /api/workflow/evaluate` are real:
`workflow-engine.service.ts:268` reads active `WorkflowRule` rows and returns matched
actions, blockers and an approval chain. Evaluate computes; it never claimed to execute.

Related and worse: the two surfaces write the **same** `workflowRule` table in
incompatible shapes. `platform` writes `conditions: {expression: string}`; the engine
reads `conditions as RuleCondition[]` and calls `.every()` on it. One platform-created
rule makes `evaluateRules` throw for every rule in that tenant. The exclusion of
`platform_workflow_*` therefore protects `workflow_evaluate` as well as the caller.

## Acceptance

  - A grant INSERT for an excluded module raises, from the database, for every writer.
  - Revoking an existing grant for an excluded module still succeeds.
  - `resolve_grant` raises `ModuleExcluded` with the recorded reason.
  - The seeder is idempotent and re-runnable.
  - The exclusions are readable next to the evidence that justifies them.
