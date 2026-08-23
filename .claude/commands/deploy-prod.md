---
name: deploy-prod
description: Prepare production deployment assets and a repeatable, observable pipeline.
---

# deploy-prod

Produce the assets and pipeline to deploy this application to production repeatably and safely.

> **This command prepares and validates deployment. It does not deploy to production on its own.**
> Staging deploys are in scope. A production release requires explicit human approval.

## Arguments

| Argument | Meaning | Default |
|---|---|---|
| `platform` | e.g. `vercel`, `fly`, `render`, `aws-ecs`, `gcp-run`, `k8s` | recommend via Alternatives & Tradeoffs |
| `region` | deployment region | nearest to primary users — `ASSUMPTION`, state it |
| `runtime` | language/runtime version | pinned to the project's current version |
| `database` | managed DB choice | recommend via Alternatives & Tradeoffs |
| `secrets_source` | `platform-env` \| `vault` \| `aws-sm` \| `gcp-sm` \| `doppler` | `platform-env` |
| `zero_downtime` | `true` \| `false` | `true` |

## Process

### 1. Architecture
Diagram the deployed system (Mermaid): services, data stores, network boundaries, ingress, secrets flow. Make the trust boundary explicit.

### 2. Platform & database choice
If `platform` or `database` was not supplied, present **2–3 options with pros/cons and a recommendation, then proceed** with the recommendation. Compare on: operational burden, cost at expected scale, scaling model, vendor lock-in, and regional/compliance fit.

### 3. IaC or platform config
Generate infrastructure-as-code or platform config. Everything version-controlled and reproducible — **no click-ops steps in the critical path.** Pin every version explicitly.

### 4. Build & release scripts
One idempotent command per stage: `build`, `migrate`, `release`, `rollback`. **This is the Output Automater obligation.** Re-running any of them must be safe.

### 5. Rollout strategy
Per `zero_downtime`: rolling, blue/green, or canary. Specify:
- health check endpoint and its success criteria
- readiness vs. liveness distinction
- **the rollback trigger and the exact rollback command**
- **database migration strategy — forward-compatible, reversible, and decoupled from the code release** (expand/contract). Never a migration that only works if code and schema deploy atomically.

### 6. Observability
Structured logging, error tracking, health checks, key metrics (latency, error rate, saturation), and at minimum an alert on error rate and on failed health checks. **A deploy you cannot observe is a deploy you cannot roll back with confidence.**

### 7. Secrets
Document every required variable in `.env.example` with placeholder values (`YOUR_DATABASE_URL_HERE`). Document loading from `secrets_source`. **No real secret appears in any file, log, or output — ever.**

### 8. Staging deploy + smoke tests
Deploy to staging. Run smoke tests against the deployed URL. Report real results.

## Outputs

- Infra / workflow files
- `docs/deploy.md` — architecture, prerequisites, env vars, deploy steps, rollback steps, observability, runbook for common failures
- `.env.example` updated
- A **"how to deploy" command block**:

```
BUILD    | <command>
MIGRATE  | <command>
DEPLOY   | <command>
VERIFY   | <command + URL>
ROLLBACK | <command>
```

Plus a **Fact Check List** — mandatory here, focused on: pinned versions, platform limits (payload size, timeout, cold start, concurrency), **cost at expected scale**, egress charges, and every security assumption.

## Error Handling

- Staging failure blocks the production path. Report logs, diagnose, fix, retry.
- Never work around a failing health check by disabling it.
- If a rollback path cannot be demonstrated, say so explicitly — that is a blocking finding.

## Example

```
/deploy-prod platform=fly region=iad runtime=node-22 database=postgres \
  secrets_source=platform-env zero_downtime=true
```
