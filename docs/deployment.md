# Deployment

One Linux VM, Docker Compose, HashiCorp Vault, staging and production.

Code: `Dockerfile`, `console/Dockerfile`, `compose.yaml` + overlays, `deploy/Caddyfile`,
`scripts/deploy.sh`, `scripts/backup.sh`.

---

## The half that is not a compose file

A Dockerfile and a compose file are the easy part. What makes this deployment rather
than a container is that **this system's guarantees are runtime properties**, and four
of them existed only in the repository:

| Guarantee | State before |
|---|---|
| The audit chain is tamper-evident | **nothing backed it up** |
| `credential_ref` holds a vault path, never a value | **no Vault resolver — the class raised** |
| The sweeps are continuous verification | **nothing ran them on a schedule** |
| `/api/health` reports control freshness | **required a bearer token, so no probe could use it** |

Each is a control that existed in the repository and would not have existed in the
deployment. That is the failure Phase 4.1 shipped once already, and a deployment is
where it gets expensive.

---

## Services

```
                    :80 :443
                       │
                    ┌──▼───┐
                    │ caddy│  TLS, HSTS, CSP. The only container that binds a host port.
                    └──┬───┘
                       │
                  ┌────▼────┐        ┌────────┐
                  │ console │───────▶│  api   │   compose network, never the browser
                  └─────────┘        └───┬────┘
                                         │
                       ┌─────────┐   ┌───▼────┐
                       │ sweeps  │──▶│   db   │   no host port, ever
                       └─────────┘   └────────┘
```

**Postgres binds no host port.** A published Postgres is a Postgres exposed the first
time the VM's firewall is edited in a hurry, and this database holds the audit chain.

**The Operations API is not proxied by Caddy.** Its only client is the console, which
reaches it over the compose network. Publishing a bearer-token API to the internet to
serve one client already inside the network buys nothing.

**The sweeps run in a container, not a host crontab**, so the schedule ships with the
deployment and cannot be true on one VM and absent on the next. It reuses the API image
— a verification job running a *different* build from the API verifies a system that is
not deployed.

---

## First deploy

```bash
git clone … && cd theoffice
cp deploy/example.env deploy/production.env    # fill it in; it is gitignored
./scripts/deploy.sh production
```

`OFFICE_DOMAIN` must already resolve to the VM. If it does not, Caddy cannot obtain a
certificate and serves plain HTTP — at which point the session cookie is `secure` and
never sent, so **the console appears to accept a sign-in and then behaves as though
nobody signed in**. Check `docker compose logs caddy` on the first deploy.

Then seed the world it needs:

```bash
docker compose … exec api python -m broker health   # every control never_run, as expected
```

### What `deploy.sh` does, and why in that order

1. **Refuses a dirty tree.** A deployment whose commit exists nowhere cannot be
   reproduced, rolled back, or reasoned about after an incident.
2. **Validates the compose config** before building or stopping anything, so a missing
   variable is a five-second failure rather than a half-applied deploy.
3. **Migrates before starting the new API**, from the API image — so migrations run the
   same code as the build being deployed.
4. **Waits for `/api/ready`, and fails if it never comes.** Traffic is not switched. A
   deploy that reports success while a container restarts has told you nothing.
5. **Verifies the audit chain.** A migration is the most plausible thing to have broken
   it, and the chain is what makes every other record credible.
6. **Reports control freshness.** Non-fatal: on a first deploy every sweep is
   legitimately `never_run`.

---

## Liveness and readiness

Two unauthenticated routes, and **only** two — pinned by
`test_the_unauthenticated_surface_is_exactly_these_two`.

`GET /api/live` — the process is up. **Does not touch the database.** A liveness probe
that fails during a database outage makes the orchestrator restart a healthy process in
a loop, turning an outage in one system into an outage in two.

`GET /api/ready` — the database answers **and the schema is at the revision this build
expects**. A container serving traffic against a half-migrated database is worse than
one that is down: it answers, and it answers wrong.

`EXPECTED_SCHEMA_REVISION` in `broker/app.py` must be bumped in the same commit as a
migration. A test enforces it, because the two disagreeing is the condition the endpoint
exists to detect.

> Found while building this: `office_app` could not read `alembic_version` — alembic
> creates it as the migration user and grants nothing. `/api/ready` would have returned
> 503 forever and every deploy would have hung on a condition that could not become
> true. Migration `0013` grants SELECT. Found by calling the endpoint, not by reading it.

---

## Credentials

`CREDENTIAL_BACKEND=vault`. Refs are `vault://<mount>/<path>#<key>`, KV v2.

Three properties keep the ref/value split honest:

- **Strict parsing.** A ref with no `#key` is refused, not defaulted. A resolver that
  guessed would read the wrong secret the first time two keys share a path.
- **No fallback to the environment, on any path** — not a 404, not a 403, not a sealed
  Vault, not a network error. A silent fallback is how a deployment reads secrets from
  its own process environment while its config says Vault, and nothing in its logs
  disagrees. There is no `vault_with_env_fallback` backend and adding one would be a
  reviewable act.
- **The Vault token appears nowhere.** Not in `__repr__`, not in an exception, not in a
  log line. Failures name the *ref*, which is a path.

Storing a Forge's tenant key:

```bash
vault kv put secret/forges/capitalforge token=YOUR_TOKEN_HERE
# then in the database, the ref only:
#   credential_ref = 'vault://secret/forges/capitalforge#token'
```

---

## Backups

```bash
./scripts/backup.sh production --verify
```

**A backup nobody has restored is a belief.** `--verify` restores the dump into a
scratch database inside the same container and runs `audit_log_verify_chain()` against
the restored copy — a dump that restores into a database whose chain does not verify is
not a backup of this system, it is a backup of the rows.

It reports the denominator and **warns when the chain verified over zero entries**,
because "the chain verifies over 0 entries" is equally true of an empty database and of
a dump that restored nothing.

Schedule it from the host — this is the one thing deliberately left to cron, because a
backup container that dies with the stack it is backing up is not a backup:

```
17 3 * * *  cd /srv/theoffice && ./scripts/backup.sh production --verify >> /var/log/office-backup.log 2>&1
```

---

## Known gaps

*Last verified: 2026-08-23.*

- **No off-host copy.** `./backups` lives on the same VM as the database, so it survives
  a bad migration and not a lost disk. Add object-storage sync before this holds
  anything that matters.
- **TLS issuance is unverified by me.** I have no domain to test against. The Caddyfile
  is the standard configuration; the first deploy must check the logs.
- **No CI deploy.** CI builds both images so a broken Dockerfile fails a PR. It pushes
  nothing and deploys nowhere; `deploy.sh` builds on the VM.
- **No rollback command.** Rolling back is `git checkout <sha> && ./scripts/deploy.sh`,
  which does **not** roll the schema back — `alembic downgrade` is deliberately manual,
  because a downgrade that drops a column drops the data in it.
- **No HIPAA claim.** Greenstone carries no PHI. MedLink would need a BAA with the host
  provider, encryption at rest, and a review of this entire file.
- **Single VM, no redundancy.** Deliberate for one venture. The audit chain is the thing
  that must survive, and backups are how it does.
- **Vault is assumed to exist.** Standing one up is not automated here; `VAULT_ADDR` and
  `VAULT_TOKEN` are inputs. A token with no renewal will expire, and the API refuses to
  start rather than falling back.
