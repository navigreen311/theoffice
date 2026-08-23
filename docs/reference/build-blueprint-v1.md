# THE OFFICE — BUILD BLUEPRINT v1

**What this is:** the implementation plan. Master prompt v4 says *what The Office is*; this says *what gets built, in what order, and how you know each piece works.*

**One-sentence definition of the product:** The Office is the layer that gives each Village agent its own revocable identity, lets that agent operate Forges on its own initiative on behalf of a named venture, and records and governs every such action.

---

## 0. STARTING STATE

| Component | Status |
|---|---|
| Village — 106 agents, 12 departments, work system, Deputy scheduling | Built, running |
| Forges — PAF, CapitalForge, CRE Forge, medlink-pro, FunnelForge, VoiceForge, VisionAudioForge, SimForge | Built |
| **Village ↔ Forge connection** | **Does not exist** |
| Per-agent credentials at any Forge | Does not exist — each Forge holds one tenant key |
| Held-out scenario partition | Does not exist |
| Structural PHI flush at shift boundary | Does not exist |
| CyberForge, StyleForge | [MODULE GAP] |

**Locked decisions carried in:** one venture per agent per shift · brokered identity with a native-credential migration path · SimForge owns the held-out partition · certification gates assignment · agents act on their own initiative, guardrails in the call path.

---

## 1. TECH STACK

Proposed for consistency with SimForge. [ASSUMPTION — confirm before Phase 0 starts; changing later is expensive.]

| Layer | Choice | Rationale |
|---|---|---|
| Broker + API | FastAPI, Python 3.11 | Matches SimForge; async-native, which the broker needs |
| Database | PostgreSQL 16 | Append-only ledger with partitioning; RLS available if needed later |
| Migrations | Alembic | Ledger schema will move; needs real migration discipline |
| Secrets | HashiCorp Vault (or cloud KMS equivalent) | Per-Forge credential storage, rotation, break-glass audit |
| Console | Next.js 14 + TypeScript + Tailwind + shadcn/ui | Matches portfolio standard |
| Client library | Python package, agent-side | Must be the only path to a Forge |
| Queue | Postgres-backed (`LISTEN/NOTIFY`) at v1 | Avoid a broker dependency until volume justifies it |
| Tests | pytest + snapshot fixtures | Golden Packs need snapshot assertion |

**Repo:** `navigreen311/the-office` — monorepo.

```
the-office/
  broker/          # FastAPI identity broker
  client/          # agent-side library — the mandatory call path
  generators/      # the seven Pack → artifact transformers
  console/         # Next.js admin UI
  db/              # Alembic migrations
  tests/
    golden/        # snapshot-asserted generator fixtures
    contract/      # per-Forge connector contract tests
    isolation/     # no-read-path check, PHI flush verification
  docs/
```

---

## 2. CORE DATA MODEL

Written first because everything else depends on it. Ledger tables are append-only — no `UPDATE`, no `DELETE`, enforced at the role level.

```sql
-- ============ IDENTITY ============
CREATE TABLE office_agent_identity (
  office_agent_id      UUID PRIMARY KEY,
  village_agent_ref    TEXT NOT NULL UNIQUE,   -- maps to workingagents.txt name
  agent_name           TEXT NOT NULL,
  department           TEXT NOT NULL,          -- one of the 12
  status               TEXT NOT NULL CHECK (status IN
                         ('active','suspended','revoked','retired')),
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at           TIMESTAMPTZ,
  revoked_by           UUID,
  revocation_reason    TEXT
);

CREATE TABLE forge_registry (
  forge_id             TEXT PRIMARY KEY,
  display_name         TEXT NOT NULL,
  base_url             TEXT NOT NULL,
  api_version          TEXT NOT NULL,
  auth_model           TEXT NOT NULL,
  credential_mode      TEXT NOT NULL CHECK (credential_mode IN ('brokered','native')),
  health_status        TEXT NOT NULL,
  last_health_check    TIMESTAMPTZ,
  deprecation_date     DATE
);

CREATE TABLE forge_module_registry (
  forge_id             TEXT REFERENCES forge_registry,
  module_id            TEXT NOT NULL,
  module_name          TEXT NOT NULL,
  api_version_introduced TEXT,
  api_version_deprecated TEXT,
  compliance_flags_implied TEXT[] NOT NULL DEFAULT '{}',
  idempotency_support  TEXT NOT NULL CHECK (idempotency_support IN
                         ('key','natural','at_most_once')),
  is_mutating          BOOLEAN NOT NULL,
  PRIMARY KEY (forge_id, module_id)
);

CREATE TABLE forge_tenant_credential (
  forge_id             TEXT PRIMARY KEY REFERENCES forge_registry,
  credential_ref       TEXT NOT NULL,          -- vault path, never the secret
  scope                TEXT NOT NULL CHECK (scope IN ('tenant','agent')),
  rotation_due         DATE NOT NULL,
  last_rotated         TIMESTAMPTZ,
  break_glass_holders  UUID[] NOT NULL         -- min 2
);

-- ============ GRANTS ============
CREATE TABLE agent_forge_grant (
  grant_id             UUID PRIMARY KEY,
  office_agent_id      UUID REFERENCES office_agent_identity,
  forge_id             TEXT NOT NULL,
  module_id            TEXT NOT NULL,
  venture_id           TEXT NOT NULL,
  trust_tier           TEXT NOT NULL CHECK (trust_tier IN
                         ('auto_execute','propose','suggest')),
  operation_cert_ref   TEXT,                   -- SimForge Unit A; NULL = unassignable
  dept_context_cert_ref TEXT,                  -- SimForge Unit B; NULL = unassignable
  granted_by           UUID NOT NULL,
  granted_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at           TIMESTAMPTZ,
  FOREIGN KEY (forge_id, module_id) REFERENCES forge_module_registry
);

CREATE INDEX ON agent_forge_grant (office_agent_id, forge_id, module_id)
  WHERE revoked_at IS NULL;

-- ============ SHIFTS ============
CREATE TABLE shift_assignment (
  shift_id             UUID PRIMARY KEY,
  office_agent_id      UUID REFERENCES office_agent_identity,
  venture_id           TEXT NOT NULL,          -- exactly one; locked decision
  shift_start          TIMESTAMPTZ NOT NULL,
  shift_end            TIMESTAMPTZ NOT NULL,
  flush_completed_at   TIMESTAMPTZ,            -- NULL blocks the next assignment
  flush_verified       BOOLEAN NOT NULL DEFAULT FALSE,
  assigned_by          UUID NOT NULL
);

-- ============ LEDGER (append-only) ============
CREATE TABLE agent_call_ledger (
  call_id              UUID PRIMARY KEY,
  trace_id             UUID NOT NULL,
  office_agent_id      UUID NOT NULL,
  venture_id           TEXT NOT NULL,
  shift_id             UUID,
  forge_id             TEXT NOT NULL,
  module_id            TEXT NOT NULL,
  api_version          TEXT NOT NULL,
  ts_start             TIMESTAMPTZ NOT NULL,
  ts_end               TIMESTAMPTZ,
  latency_ms           INT,
  status_code          INT,
  tokens_in            INT,
  tokens_out           INT,
  usd_cost             NUMERIC(12,6),
  trust_tier_at_call   TEXT NOT NULL,
  compliance_flags_active TEXT[] NOT NULL DEFAULT '{}',
  data_types_touched   TEXT[] NOT NULL DEFAULT '{}',
  idempotency_key      TEXT,
  manifest_match       TEXT NOT NULL CHECK (manifest_match IN
                         ('required','declared_only','UNDECLARED')),
  forge_side_ref       TEXT,
  payload_hash         TEXT NOT NULL
) PARTITION BY RANGE (ts_start);

CREATE TABLE audit_log (
  audit_id             BIGSERIAL PRIMARY KEY,
  event_type           TEXT NOT NULL,
  actor_type           TEXT NOT NULL CHECK (actor_type IN ('agent','human','system')),
  actor_id             UUID NOT NULL,
  venture_id           TEXT,
  subject              JSONB NOT NULL,
  trace_id             UUID,
  ts                   TIMESTAMPTZ NOT NULL DEFAULT now(),
  prev_hash            TEXT NOT NULL,
  entry_hash           TEXT NOT NULL          -- hash chain; tamper-evident
);
```

**Hash chain on `audit_log` is not optional.** Until Forges support per-agent identity, the Office ledger is the *only* per-agent record — Forge-side logs attribute everything to the tenant. That makes ledger integrity load-bearing in a way it wouldn't otherwise be.

---

## 3. THE CALL PATH

The single most important code path in the system.

```python
# client/office_client.py — the ONLY way an agent reaches a Forge

async def call(forge_id, module_id, payload, *, agent_ctx):
    trace_id = new_trace()

    # 1. Resolve grant — revocation checked live, never cached
    grant = await broker.resolve_grant(
        agent_ctx.office_agent_id, forge_id, module_id, agent_ctx.venture_id)
    if grant is None:
        raise NotGranted(...)                      # audited
    if grant.operation_cert_ref is None or grant.dept_context_cert_ref is None:
        raise NotCertified(...)                    # audited

    # 2. Manifest check
    match = await manifest.check(agent_ctx.venture_id, forge_id, module_id)
    if match == "UNDECLARED":
        await incidents.raise_high("undeclared_forge_call", ...)
        raise ManifestViolation(...)

    # 3. Trust tier
    if grant.trust_tier != "auto_execute":
        return await proposals.submit(...)         # human queue, not a Forge call

    # 4. Rate limit — per agent AND per Forge global ceiling
    await limiter.acquire(agent_ctx.office_agent_id, forge_id)

    # 5. Idempotency
    idem = idempotency_key(agent_ctx.task_id, module_id, payload)
    if mod.idempotency_support == "at_most_once" and is_retry(idem):
        raise EscalateToHuman(...)                 # never auto-retry these

    # 6. Audit BEFORE the call — fail closed if compliance-flagged
    written = await audit.write_pre_call(...)
    if not written and grant.compliance_flags:
        raise AuditUnavailable(...)                # fail closed

    # 7. Broker executes with tenant credential, stamps agent identity
    resp = await broker.execute(forge_id, module_id, payload,
        headers={"X-Office-Agent-Id": ..., "X-Office-Venture": ...,
                 "X-Office-Trace": trace_id, "Idempotency-Key": idem})

    # 8. Ledger
    await ledger.write(...)
    return resp
```

**Network policy must make Forge endpoints unreachable from agent runtime except via the broker.** Without that, the client library is a convention rather than a control, and every guardrail above becomes optional.

---

## 4. BUILD PHASES

### Phase 0 — The Bridge (target: 1 week, CRE Forge)

The only thing here that has never been proven possible.

| # | Deliverable | Done when |
|---|---|---|
| 0.1 | Schema + Alembic migrations | Tables exist; append-only roles enforced; hash chain verified by test |
| 0.2 | Identity issuance | All 106 agents have `office_agent_id`, mapped to `village_agent_ref`, department populated |
| 0.3 | Vault + CRE Forge credential | Credential retrievable by ref; never in logs or env; rotation runbook written |
| 0.4 | Broker skeleton | Resolves grant, injects headers, executes, returns |
| 0.5 | Client library | Trace, pre-call audit, idempotency, ledger write |
| 0.6 | Network policy | Direct Forge call from agent runtime fails, proven by test |
| 0.7 | Revocation | Revoked agent's *next* call fails; verified live, not cached |
| **0.8** | **First real call** | **One agent, one CRE Forge module, one authenticated call, one ledger row naming that agent** |

**Phase 0 acceptance test:** a named agent completes a real CRE Forge operation; the ledger row names it; revoking the grant makes the immediate next call fail; a direct call bypassing the client library is refused at the network layer.

### Phase 1 — Governance in the path (target: 1 week)

Trust-tier enforcement · manifest check with the four mismatch handlers · rate limiting per agent and per Forge global ceiling · cost metering into the same ledger · four revocation scopes · fail-closed audit on compliance-flagged actions.

**Acceptance:** an agent at `propose` tier cannot execute — the call produces a proposal, not a Forge action. An `UNDECLARED` call raises a HIGH incident and throttles. Exceeding the per-task ceiling halts that task.

### Phase 2 — Instructions and certification (target: 2 weeks)

Forge Operating Instructions authoring UI (author, version, `content_hash`, `version_sensitivity`, diff, staleness) · SimForge held-out partition, SimForge-owned · **the automated no-read-path check, shipped with the partition** · curriculum submission + Gate result callback · grants gated on both certification units.

**Acceptance:** an agent is certified for one CRE Forge module and becomes assignable; an uncertified agent cannot be granted; rewriting the instructions flips affected certs to `stale_instructions` and removes assignability; the no-read-path test fails the build if a new response field is added without manifest update.

### Phase 3 — First venture (target: 3 weeks) — Greenstone

Hand-author the Greenstone Pack · Pack Validator · seven generators with golden-test snapshots · appointment with the three-number capacity report · shift assignment with verified PHI flush at boundary · sandbox provisioning, then live.

**Acceptance:** Greenstone Pack passes validation, generators produce artifacts a human approves unchanged, agents are appointed and certified, and a real Greenstone operational task completes end to end.

### Phase 4 — Generalize

Remaining seven Forges through Phase 0–2 each · remaining ventures · console breadth · backup/restore drill · monthly reconciliation sweep.

**Sequencing note:** medlink-pro last among the Forges. PHI raises the cost of every mistake, and by then the flush, isolation, and audit paths will have been exercised on ventures where an error is recoverable.

---

## 5. TEST STRATEGY

| Suite | What it protects |
|---|---|
| `golden/` | Generator regressions — fixed Packs, snapshot-asserted outputs. Any diff fails CI and requires explicit approval |
| `contract/` | Per-Forge connector correctness against sandbox tenants; failure pins affected ventures to the prior API version |
| `isolation/` | The no-read-path check; PHI flush verification; network-policy bypass attempt |
| `validator/` | Every FAIL rule has a must-fail fixture and a must-pass fixture |
| `idempotency/` | Runtime Config run twice → identical state, zero duplicate side-effects |
| `ledger/` | Hash chain continuity; append-only enforcement; restore drill |

**The Office must test itself.** Everything else in the portfolio tests Villages. A generator regression that silently alters an appointment roster is exactly the plausible-looking-false-output defect class already catalogued portfolio-wide.

---

## 6. RISK REGISTER

| Risk | Impact | Mitigation |
|---|---|---|
| Forge-side logs can't attribute per agent until native credentials exist | Reconciliation is one-sided; Office ledger is the sole record | Hash chain, replication, quarterly restore drill. Prioritize native migration per Forge |
| Client library bypassed | Every guardrail becomes optional | Network policy, not convention. Tested as a bypass attempt |
| No-read-path check not built with the partition | Held-out integrity reverts to a handshake | Ships in Phase 2 as a gate, not a follow-up |
| Certification backlog throttles capacity | Ventures wait on SimForge rather than on build | Certify narrowly — one Forge, few modules — before broadening |
| CyberForge absent | Cyber venture cannot pass Gate 3.5 | Decide: spec it, or drop cyber from v1 |
| Approval queue exceeds human capacity | Trust tiers become decorative | Validator rule V13 blocks the Pack; rubber-stamp detection at runtime |
| Stack assumption wrong | Rework across broker and console | Confirm §1 before Phase 0 line one |

---

## 7. DEFINITION OF DONE — v1

1. All 106 agents hold Office-issued identities.
2. At least one Forge fully bridged, with certification gating grants.
3. Greenstone live: real operational tasks completing, per-agent ledger entries, revocation proven.
4. Console supports Pack authoring, appointment, grants, revocation, Forge Map, audit query.
5. All six test suites green; restore drill passed.
6. Cost per completed operational task reportable for Greenstone.

**Item 6 is the one that matters commercially.** It's the first number that tells you whether The Office is worth what it costs to run — and nothing before Phase 3 can produce it.
