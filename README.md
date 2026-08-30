# The Office

[![CI](https://github.com/navigreen311/theoffice/actions/workflows/ci.yml/badge.svg)](https://github.com/navigreen311/theoffice/actions/workflows/ci.yml)

The layer that gives each Village agent its own revocable identity, lets that agent
operate Forges on its own initiative on behalf of a named venture, and records and
governs every such action.

**The bar:** *a Village agent, holding an Office-issued identity, completes a real
authenticated Forge operation for a named venture, with a per-agent audit entry,
under a SimForge operation certification.* Every clause is currently false. Phase 0
exists to make the first ones true.

## Status

| Phase | Deliverable | State |
|---|---|---|
| 0.1 | Schema, append-only ledger, hash chain | **Done** — 42 tests |
| 0.2 | Identity issuance for all 106 agents | Blocked — needs the Village roster |
| 0.3 | Vault + CRE Forge credential | Blocked — needs Vault and CRE Forge access |
| 0.4 | Broker — grant resolution, credentials, execution | **Done** |
| 0.5 | Client library — the mandatory call path | **Done** |
| 0.6 | Network policy | Blocked — needs the deployment target |
| 0.7 | Revocation — four scopes | **Done** |
| 0.8 | **First real authenticated call** | The milestone — needs Forge access |
| **1** | **Governance in the path** | **Done** |
| **2** | **Instructions, certification, no-read-path check** | **Done** |
| **3.1** | **Business Pack v3 + Pack Validator (27 rules)** | **Done** — 247 tests |
| **3.2** | **The seven generators + golden snapshots** | **Done** — 274 tests |
| **3.3** | **Shift assignment + verified PHI flush** | **Done** |
| **4.1** | **Continuous verification: 4 sweeps + control health** | **Done** |
| **4.2** | **Human identity + Operations API** | **Done** - 337 tests |
| **4.3** | **Next.js console - 5 of 14 screens** | **Done** - 337 py + 12 ts tests |
| **4.4** | **Console screens 6-11 of 14** | **Done** - 337 py + 18 ts tests |
| 4.5 | Pack store, provisioning pipeline, 4 missing knowledge bases | Blocked on backend |

## Quick start

Requires PostgreSQL 16+ running locally and Python 3.11.

```bash
cp .env.example .env      # then fill it in
./scripts/bootstrap.sh    # venv, deps, database, migrations, tests
```

`bootstrap.sh` is idempotent. `--reset` drops and recreates the database;
`--no-test` sets up without running the suite.

## Commands

```bash
./scripts/dev-up.sh                                     # a usable local instance + a token
./scripts/dev-up.sh --stop                              # stop it again
./scripts/bootstrap.sh                                  # everything
.venv/Scripts/python -m pytest -q                       # tests
.venv/Scripts/python -m ruff check .                    # lint
.venv/Scripts/python -m alembic upgrade head            # migrate
.venv/Scripts/python -m alembic downgrade base          # roll back fully

psql "$OFFICE_ADMIN_DSN" -c "SELECT * FROM audit_log_verify_chain()"

.venv/Scripts/python -m broker sweep                    # the verification sweeps
.venv/Scripts/python -m broker health                   # freshness of every control
.venv/Scripts/python -m broker serve --port 8080        # the Operations API
cd console && npm run dev                               # the console on :3000
./scripts/console-smoke.sh                              # both, verified end to end
.venv/Scripts/python scripts/seed_dev_world.py          # bridged Forges + a certified roster
```

## Running it locally

```bash
./scripts/dev-up.sh
```

Migrates, seeds the dev world and the Greenstone Pack if they are missing, issues a
token for the operator (**reissuing** rather than failing when they already exist), and
starts the API and the console. Prints the URL and the token.

The test suite runs against **its own database** (`OFFICE_TEST_ADMIN_DSN` /
`OFFICE_TEST_APP_DSN`, created by `bootstrap.sh`), so running the tests no longer ends
your console session. Without those set the suite falls back to the development database
and says so at startup rather than quietly emptying it — it empties every table it
touches, which is correct for a suite and fatal for a session.

Sign in at **http://localhost:3100**, not `127.0.0.1`: the session cookie is scoped to
the host you sign in on, and Next redirects to `localhost` regardless.

## CI

`.github/workflows/ci.yml`. Seven jobs: **lint and types** (ruff, strict mypy,
shellcheck), **tests** (Postgres 16 service, migrations, the full suite), **migrations
are reversible** (up/down/up/down/up, then one head), **console** (vitest, tsc, build,
eslint), **smoke** (a real server, real requests, real pages), **images** (both containers build,
start and run non-root), and **no committed secrets**.

Three of those need explaining, because each closes a way this repository can go green
while proving nothing.

**`tests` refuses to pass if anything skipped.** Every database test is guarded by
`requires_db`, which *skips* when the DSNs are unset. With the service container
misconfigured, `pytest` reports `103 passed, 324 skipped` and **exits 0** — a green tick
over 324 assertions that never ran. The job parses the JUnit report and fails on any
skip, because the suite has no legitimately skipped test.

**`console` lints with `--max-warnings=0`.** `next lint` exits 0 on warnings, so a lint
step without that flag reports success over every warning it just printed.

**`smoke` starts the real thing and asks it for pages.** `next build` passing is not
evidence the app runs: the revocation page compiled, type-checked and threw at render
because a React 19 hook does not exist in React 18. The job runs
`scripts/console-smoke.sh`, which boots the Operations API and the console, checks that
every route redirects unauthenticated and renders authenticated, that the bearer token
never appears in the HTML, that a persona body reaches no page, and that the gate ladder
renders against a live provisioning run.

The script runs on Linux and on Windows under Git Bash — everything platform-specific is
behind two functions. It reads `.env` when there is one and the environment when there
is not, so CI needs no dotfile:

```bash
./scripts/console-smoke.sh              # build, then verify
./scripts/console-smoke.sh --no-build   # reuse an existing .next
```

## Deploy

One Linux VM, Docker Compose, Vault, staging and production. See
`docs/deployment.md`.

```bash
cp deploy/example.env deploy/production.env    # gitignored; fill it in
./scripts/deploy.sh production
./scripts/backup.sh production --verify        # dump, restore, verify the chain
```

`deploy.sh` refuses a dirty tree, migrates before starting the new API, **waits for
`/api/ready` and fails without switching traffic if it never comes**, then verifies the
audit chain — a migration is the most plausible thing to have broken it.

## Layout

```
broker/       FastAPI identity broker
client/       agent-side library - the mandatory call path
generators/   the seven Pack -> artifact transformers
console/      Next.js admin UI
db/           Alembic migrations
tests/
  ledger/     append-only enforcement, hash chain
  golden/     snapshot-asserted generator fixtures
  contract/   per-Forge connector contract tests
  isolation/  no-read-path check, PHI flush verification
docs/
  reference/  master prompt v4, build blueprint v1
  plans/      per-feature design, written before implementation
```

## Read first

- `CLAUDE.md` — conventions and the 14 non-negotiable invariants
- `PROJECT_RULEBOOK.md` — the governing methodology
- `docs/ledger.md` — how append-only and the hash chain actually work
- `docs/call-path.md` — the broker, the client library, and why the order matters
- `docs/governance.md` — revocation scopes, manifest, trust tiers, limits, budget
- `docs/forge-adapter.md` — onboarding a Forge, and three defects that returned 200 while being wrong
- `docs/certification.md` — instructions, the two units, staleness, and the no-read-path check
- `docs/pack-validator.md` — the Business Pack, the 27 rules, and why three of them read the world
- `docs/generators.md` — the seven generators, determinism, and two findings they surfaced
- `docs/shifts.md` — the temporal PHI wall, the verified flush, and why a failed flush blocks
- `docs/sweeps.md` — continuous verification, and why a stale pass is not a pass
- `docs/console-api.md` - the Operations API, and why it is not a bypass
- `docs/console.md` - the console, and why the browser never sees the token
- `docs/reference/` — what The Office is, and what gets built in what order

## Security

Two database roles. `office_app` is the runtime role and holds `INSERT` + `SELECT`
on ledger tables and nothing else — `UPDATE` and `DELETE` are never granted. Secrets
are stored as vault refs, never as values. Never commit `.env`.
