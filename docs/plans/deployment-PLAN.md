# Deployment — PLAN

Phase 0.6. Decided with the user: **one Linux VM running Docker Compose**, **HashiCorp
Vault** for credentials, **staging and production**.

---

## What "deployment setup" has to include, and what it must not pretend

A compose file and a Dockerfile are the easy half. The half that matters is that this
system's guarantees are all runtime properties, and most of them are currently true only
because a developer's machine happened to be set up right:

- the audit chain is tamper-evident **and nothing backs it up**;
- `credential_ref` holds a vault path **and there is no Vault resolver** — the class
  exists and raises;
- the sweeps are the continuous-verification layer **and nothing runs them on a
  schedule**;
- `/api/health` is the freshness endpoint **and it requires a bearer token**, so no
  orchestrator, proxy or uptime check can use it.

Each of those is a control that exists in the repository and would not exist in the
deployment. That is the same failure Phase 4.1 shipped once already, and a deployment is
where it gets expensive.

## Five pieces

### 1. Liveness and readiness, unauthenticated — and pinned

Docker's healthcheck and Caddy's upstream check cannot hold a bearer token.

- `GET /api/live` — the process is up. No database, no auth, no information.
- `GET /api/ready` — the database answers **and the schema is at head**. A container
  serving traffic against a half-migrated database is worse than one that is down.

Adding an unauthenticated route to this API is a reviewable act, so
`test_the_unauthenticated_surface_is_exactly_these_two` pins it the same way the write
surface is pinned. Neither returns anything an unauthenticated caller could learn from:
no version, no counts, no error text.

`/api/health` stays authenticated. It reports control freshness, which is exactly the
kind of thing an attacker would like to know is stale.

### 2. A real Vault resolver

`VaultCredentialResolver` currently raises, and does so deliberately rather than falling
back to the environment. Now it reads KV v2, and the important properties are the ones
that keep the ref/value split honest:

- the ref is `vault://mount/path#key`, parsed strictly — a malformed ref is refused, not
  guessed at;
- the token never enters a log line, an exception, or the `Credential.__repr__`;
- a resolution failure raises `CredentialUnavailable` with the **ref**, never the value;
- **no fallback to `env://` ever**, in any error path. A silent fallback is how a
  production deployment reads secrets from its own process environment while its config
  says Vault.

Tested against a stub Vault, including the leaky cases, in the shape
`tests/golden/stub_simforge.py` established.

### 3. Images and compose

Two Dockerfiles, both multi-stage and both non-root:

- `Dockerfile` — the API. Also the image the sweep job runs, because a scheduled job
  that runs a *different* build from the API is a job verifying a system that is not
  deployed.
- `console/Dockerfile` — Next.js `output: "standalone"`.

`compose.yaml` plus `compose.staging.yaml` and `compose.prod.yaml` overlays. Services:
`db`, `api`, `console`, `caddy`, `sweeps`. Postgres is **not** published to the host;
only Caddy binds a port.

The sweeps service is a loop rather than a host cron, so the schedule ships with the
deployment instead of living in somebody's crontab.

### 4. Backups, because the audit chain is the point

`scripts/backup.sh` — `pg_dump` to a timestamped file, retention, and **a restore drill
that verifies the hash chain on the restored copy**. A backup nobody has restored is a
belief. Gate 13 already exists as a sweep for exactly this reason; this is the host-side
half.

### 5. One deploy command

`scripts/deploy.sh <staging|production>` — pull, build, migrate, start, wait for ready,
verify the chain, report. Idempotent, refuses to run with a dirty tree, and **fails
before switching traffic if readiness never comes up**.

## What this does not do

- **No TLS certificate automation is verified by me.** Caddy does it on a real domain;
  I have no domain to test against, so the config ships with a placeholder and the doc
  says what to change.
- **No HIPAA claim.** Greenstone carries no PHI. MedLink would need a BAA with the host
  provider, encryption at rest, and a review of this whole file.
- **No CI deploy.** CI builds the images so a broken Dockerfile fails a PR; it does not
  push or deploy anywhere.

## Acceptance tests

| # | Test |
|---|---|
| D1 | `/api/live` answers without a token and returns nothing else |
| D2 | `/api/ready` reports not-ready when the schema is behind head |
| D3 | the unauthenticated surface is exactly those two routes |
| D4 | the Vault resolver reads a KV v2 secret |
| D5 | **a malformed ref is refused, never guessed at** |
| D6 | **no error path falls back to the environment** |
| D7 | a Vault failure raises with the ref and never the value |
| D8 | the token never appears in a repr, a log or an exception |
| D9 | both images build (CI) |
