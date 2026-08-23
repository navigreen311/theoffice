# The Office

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
| 4.3 | Next.js console (14 screens) | Next |

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
./scripts/bootstrap.sh                                  # everything
.venv/Scripts/python -m pytest -q                       # tests
.venv/Scripts/python -m ruff check .                    # lint
.venv/Scripts/python -m alembic upgrade head            # migrate
.venv/Scripts/python -m alembic downgrade base          # roll back fully

psql "$OFFICE_ADMIN_DSN" -c "SELECT * FROM audit_log_verify_chain()"

.venv/Scripts/python -m broker sweep                    # the verification sweeps
.venv/Scripts/python -m broker health                   # freshness of every control
.venv/Scripts/python -m broker serve --port 8080        # the Operations API
```

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
- `docs/certification.md` — instructions, the two units, staleness, and the no-read-path check
- `docs/pack-validator.md` — the Business Pack, the 27 rules, and why three of them read the world
- `docs/generators.md` — the seven generators, determinism, and two findings they surfaced
- `docs/shifts.md` — the temporal PHI wall, the verified flush, and why a failed flush blocks
- `docs/sweeps.md` — continuous verification, and why a stale pass is not a pass
- `docs/console-api.md` - the Operations API, and why it is not a bypass
- `docs/reference/` — what The Office is, and what gets built in what order

## Security

Two database roles. `office_app` is the runtime role and holds `INSERT` + `SELECT`
on ledger tables and nothing else — `UPDATE` and `DELETE` are never granted. Secrets
are stored as vault refs, never as values. Never commit `.env`.
