# THE OFFICE — CHIEF PLATFORM ARCHITECT MASTER PROMPT v4

**This is a rewrite, not a revision.** v1–v3 were built on four wrong assumptions. All four are corrected here. If you have v3, discard it — do not merge.

---

## WHAT CHANGED FROM v3, AND WHY

| v3 assumed | Actually true | Consequence |
|---|---|---|
| Five Villages, one per venture, each provisioned from a Pack | **One Village.** 106 agents, 12 departments, built by hand, running today. It carries multiple ventures at once | Tenant boundary moves from Village to **venture engagement**. Generators stop creating org charts and start appointing from an existing roster |
| Gardner is a governance platform layer above the ventures | **Gardner is an agent** — role COO, `can_self_initiate: true`, runs system health checks 08:00 UTC daily and performance reviews on 6h interval | No second platform layer. The Office sits above the Village; Gardner is the top agent inside it |
| Agents already operate Forges; The Office governs that | **The Village and the Forges are not connected.** No agent has ever called a Forge | **The Office is the bridge.** This is not a governance layer over a working capability — it is the capability |
| PHI walls run between Villages | One Village, agents rotating across ventures by shift | The wall is **temporal, not spatial** — it runs at the shift boundary, inside a single agent |

**The load-bearing correction is the third one.** Everything v3 specified — audit logs, kill switches, trust tiers, cost metering, the SimForge certification chain — presumes an agent can reach a Forge. None of it was wrong. All of it was downstream of something that does not exist.

v4 puts the bridge first.

---

## HOW TO READ THIS DOCUMENT

This is a prompt. It tells an architect what to produce.

| Section | Contents |
|---|---|
| Fixed Context | The Village as it actually is. Do not re-derive |
| Part 1 | **The Identity & Execution Layer** — the bridge. Everything else depends on it |
| Parts 2–16 | The rest of the platform, in build order |
| Business Pack schema v3 | The input artifact |
| Validator, decisions, build order, self-audit | Enforcement and sequencing |

**Five ideas everything hangs on:**

1. **The bridge does not exist.** Village agents have never touched a Forge. Building that path is The Office's primary job, not an assumption underneath it.
2. **Agents act on their own initiative.** No queue, no runner, no human in the loop. An agent decides and goes. Guardrails live in the call path, not in the agent's judgment.
3. **Identity is issued by The Office, presented to the Forge.** Every agent gets its own revocable identity today, without waiting for eight Forge rebuilds.
4. **Certification gates assignment.** An agent is not capacity until SimForge certifies it for the Forge modules the venture needs.
5. **Report the denominator.** No green check without a coverage count.

---

## WHAT THE OFFICE DOES, DAY TO DAY

Once the bridge exists, this is the loop The Office runs — and it is the reason the platform exists at all. Everything in Parts 1 and 9–17 is scaffolding around it.

```
  A venture Pack arrives
  (new, or one already written — Burkham, Greenstone, MedLink…)
            │
            ▼
  ① Role Definition      → The Office names the positions this venture needs
                           "Capital Underwriting Analyst", "Buyer Network Manager",
                           "Clinician Credentialing Specialist" — titles the Village
                           roster does not natively contain. The Office writes them.
            │
            ▼
  ② Appointment          → Picks named agents from the existing 106, by department
                           fit and certification state. Reports the gap where it
                           cannot fill. NEVER creates an agent. NEVER appoints an
                           uncertified one.
            │
            ▼
  ③ Workflow             → Every operational step, in order, each naming a Forge module
  ④ Task Ledger          → Every task owned, tiered, SLA'd, volume-estimated
  ⑤ Curriculum           → Scenarios handed to SimForge for certification
  ⑥ Forge Manifest       → The venture's bill of materials, reconciled three ways
  ⑦ Runtime Config       → Grants issued, integrations wired, flags applied
            │
            ▼
  A working agent team for a venture that did not have one an hour earlier.
  The Village carries several ventures at once — one venture per agent per shift.
```

**The Office assigns agents. It does not create them.** The Village produces agents; The Office appoints them to venture positions and revokes them. A capacity shortfall flags to Ivan with three numbers (§7.2) — it never fills a gap by lowering the bar.

The generators are specified in Part 5. They appear after Part 1 in this document because ② cannot run until certification exists, and certification cannot run until an agent can call a Forge. **Sequence, not priority.**

---

## 🏛 FIXED CONTEXT — DO NOT RE-DERIVE

### The Village

One Village. 106 agents. 12 departments. Built by hand, running today, adversarially tested.

| Department | Agents |
|---|---|
| Media Production | 15 |
| Music Production | 15 |
| Product Development & Engineering | 12 |
| AI & Data Science | 11 |
| Publishing | 9 |
| Infrastructure & Cybersecurity | 8 |
| Client Success & Operations | 8 |
| Research & Market Intelligence | 7 |
| Marketing & Communications | 7 |
| Finance & Administration | 6 |
| Autonomous Operations | 5 |
| Executive & Strategy | 3 |

**Gardner** — COO, Autonomous Operations, the original autonomous agent. `can_self_initiate: true`. Task types: `system_health_check`, `performance_review`, `escalation_management`. Priority P1. Gardner is an agent, not infrastructure.

**Work system as built:** every agent has a daily job authored mechanically by the department Deputy from template + backlog + on-shift headcount. Deputy authoring is gated on the Deputy being on-shift; a 1.5× cushion carries the desk through rest days. Strategic objectives (17/quarter) sit above, pulled first per department. Pull rule guarantees no idle agents.

**Clock:** 1 agent-day = 1 real hour. All capacity math is denominated in **agent-days**.

**Shifts exist** as a Village mechanic — on-shift headcount, rest days, Deputy cushion. **An agent works exactly one venture per shift. Decided, not assumed.** Venture switching mid-shift is not permitted, which means the PHI flush occurs at a single predictable boundary rather than on a runtime condition. Conditional flushes were rejected: the condition is where the bug lives, and idle time is recoverable by tuning shift length while a PHI leak is not.

### What exists, what does not

| | Status |
|---|---|
| The Village + 106 agents + work system | **Built, running** |
| PAF, CapitalForge, CRE Forge, medlink-pro, FunnelForge, VoiceForge, VisionAudioForge, SimForge | **Built** |
| Village ↔ Forge connection | **Does not exist.** No agent has called a Forge |
| Per-agent credentials at any Forge | **Does not exist.** Forges hold one tenant key each |
| Held-out scenario partition (Gate 9.5, SimForge Q3) | **Does not exist.** Specified only |
| Structural PHI flush at shift boundary | **Does not exist** |
| CyberForge | [MODULE GAP] |
| StyleForge | [MODULE GAP] |

**The Village's work output today is mechanically-authored and scored inside the Village.** Two-sided quality — work fails as well as succeeds — which is a real achievement and a different thing from an authenticated call to a Forge with a live customer record and a compliance obligation attached. v4 exists to close that difference.

### Ventures The Office serves

Green Companies LLC (Las Vegas, NV). MedLink Pro Staffing (operating; HIPAA, HCQC) · Greenstone (launching; CRE wholesale; no PHI) · Collingswood & Co. (two-party consent, voice-cloning consent) · Burkham Wickmont (TILA, FCRA, ECOA, UDAAP, CROA, state lender licensure) · Cybersecurity venture (NRS 648 NV; blocked — see [MODULE GAP: CyberForge]).

The Village carries several ventures simultaneously. Ventures are **engagements on the Village**, not separate Villages.

---

## PART 1 — THE IDENTITY & EXECUTION LAYER (THE BRIDGE)

**This is the product.** Nothing else in this document is buildable or meaningful until this exists.

### 1.1 The problem stated precisely

An agent needs CapitalForge to parse a bank statement. Today there is no path. Two ways to create one:

**Per-agent native credentials** — each agent holds its own login at each Forge. Correct end state. Not buildable today: every Forge holds a single tenant-scoped key, and adding per-principal identity is a change inside each of eight Forges.

**Office-brokered identity** — The Office issues each agent its own identity, holds the Forge's existing tenant key, and presents it on the agent's behalf while stamping which agent made the call. Buildable today against every Forge as it stands.

**v1 builds the second, structured so the first is a swap and not a rewrite.**

What the agent experiences is identical either way: it decides, it calls, it acts immediately, it is accountable, and it can be revoked in one second. Nothing queues. No human intervenes. The difference is only where the credential physically lives.

**Explicitly rejected: removing authentication so agents can access Forges freely.** Unique per-principal identification is what makes audit, revocation, trust tiers, spend attribution, and certification meaningful — remove it and all six collapse simultaneously. It is also a HIPAA violation on its face (45 CFR 164.312(a)(2)(i) requires unique user identification), and an unauthenticated path is not selectively open to your agents.

### 1.2 Architecture

```
  Agent (Village)
      │  acts on own initiative — no queue, no approval wait
      ▼
  Office Client Library            ← mandatory call path
      │  · stamps trace_id
      │  · writes audit entry BEFORE the call
      │  · checks trust tier for this agent × module × venture
      │  · verifies module is in venture's Forge Manifest
      │  · applies per-agent + per-Forge rate limit
      │  · attaches idempotency key
      │  · attaches venture context + compliance flags
      ▼
  Identity Broker
      │  · resolves office_agent_id → Forge tenant credential
      │  · injects X-Office-Agent-Id, X-Office-Venture, X-Office-Trace
      │  · enforces revocation (checked per call, not cached)
      ▼
  Forge (CapitalForge, VoiceForge, …)
```

**The client library is not optional and not advisory.** An agent that constructs its own HTTP call to a Forge is bypassing every control in this document. Network policy must make the Forge endpoints unreachable from agent runtime except through the broker. This is the single point where Way-1 autonomy and Way-2 governance are reconciled — the agent is fully autonomous, and the path it acts through is instrumented.

### 1.3 Data model

```sql
office_agent_identity
  office_agent_id, village_agent_ref, agent_name, department,
  status: [active | suspended | revoked | retired],
  created_at, revoked_at, revoked_by, revocation_reason

agent_forge_grant                 -- what this agent may do, where
  office_agent_id, forge_id, module_id, venture_id,
  trust_tier: [auto_execute | propose | suggest],
  operation_cert_ref,             -- SimForge Unit A; NULL = not assignable
  dept_context_cert_ref,          -- SimForge Unit B; NULL = not assignable
  granted_by, granted_at, revoked_at

forge_tenant_credential           -- one per Forge, vault-backed
  forge_id, credential_ref, scope: tenant,
  rotation_due, last_rotated, break_glass_holders[]

agent_call_ledger                 -- append-only; audit + cost + manifest check
  call_id, trace_id, office_agent_id, venture_id, shift_id,
  forge_id, module_id, api_version,
  ts_start, ts_end, latency_ms, status_code,
  tokens_in, tokens_out, usd_cost,
  trust_tier_at_call, compliance_flags_active[], data_types_touched[],
  idempotency_key,
  manifest_match: [required | declared_only | UNDECLARED],
  forge_side_ref                  -- for reconciliation; see 1.5
```

`agent_forge_grant` with either cert reference NULL is **not assignable**. Certification is not advisory metadata; it is the grant condition.

### 1.4 Revocation — the kill switch under Way 1

With no front desk to stop, revocation is the kill switch. Four scopes:

| Scope | Effect | Authority |
|---|---|---|
| Agent × module | One grant revoked | Venture operator |
| Agent (all) | Agent cannot reach any Forge | Venture operator |
| Venture | All grants for that engagement | Compliance officer |
| Forge-wide | Broker refuses all calls to that Forge | Ivan |

Revocation is checked **per call at the broker, never cached**. A revoked agent's next call fails, not its next session. Every revocation and re-enable writes an audit entry; re-enable requires a documented ritual and a named human.

### 1.5 Dual-sided audit and its current limit

The Office logs what was sent. The Forge logs what it received. Reconciliation between them is how a compromised or malfunctioning agent is caught.

[ASSUMPTION / KNOWN WEAKNESS: until Forges support per-principal identity, **Forge-side logs will attribute every call to the tenant, not the agent.** The Office ledger is therefore the only per-agent record, and reconciliation can verify call counts and payload hashes but not independently corroborate attribution. This is a real gap, stated rather than papered over. It closes when Forges gain native per-agent credentials. Until then, integrity of `agent_call_ledger` is load-bearing and must be protected accordingly — append-only, signed, replicated.]

### 1.6 Migration to native credentials

Structure the broker so the swap is configuration, not rearchitecture:

- `forge_tenant_credential.scope` gains `agent` as a value
- When a Forge supports per-principal identity, grants resolve to the agent's own credential instead of the tenant key
- The client library, trust-tier checks, manifest checks, rate limits, and ledger are unchanged
- Forge-side logs begin carrying agent attribution, and reconciliation becomes genuinely dual-sided

Per-Forge migration status is tracked and displayed, because it changes the strength of the audit guarantee for that Forge.

### 1.7 Build order within Part 1

1. `office_agent_identity` — issue identities for all 106 agents
2. Vault + `forge_tenant_credential` for one Forge
3. Client library — trace, audit-before-call, idempotency
4. Identity broker — resolve, stamp, enforce revocation
5. Network policy — Forge endpoints unreachable except via broker
6. `agent_call_ledger` + revocation controls
7. **One agent, one module, one real call, end to end** ← the first thing that has never happened
8. Trust tier + manifest enforcement in the path
9. Rate limiting, per-agent and per-Forge global ceiling
10. Repeat 2 for the remaining seven Forges

Step 7 is the milestone that matters. Everything before it is scaffolding; everything after it is scale.

---

## 📐 BUSINESS PACK — SCHEMA v3

Changes from v2: `estimated_agent_count` removed (the roster exists; The Office appoints from it). `capacity_demand` added. `positions_required` added — The Office names venture-specific roles rather than reading them from a fixed list.

```yaml
# BUSINESS PACK — [venture_name] · schema_version: 3

identity:
  venture_name: [string, required]
  legal_entity: [string, required]
  parent: [string, default: "Green Companies LLC"]
  operating_status: [enum: launching | operating | scaling | winding_down]
  category: [string, required]
  positioning_one_liner: [string, ≤200 chars, required]

environment: [enum: sandbox | staging | production, required]

market:
  target_personas: [list, required, min 1]
  target_geographies: [list, required]
  compliance_surface:
    - framework: [enum: HIPAA | HCQC | TILA | FCRA | ECOA | UDAAP | CROA |
                  FTC_TSR | NRS_648_NV | STATE_LENDER_LICENSURE |
                  MCA_DISCLOSURE_CA_SB1235 | TWO_PARTY_CONSENT_RECORDING |
                  VOICE_CLONING_CONSENT | GDPR | CCPA | PCI_DSS, required]
      jurisdiction: [list | "FEDERAL" | "ALL", required]
      applies_when: [string, required]
      runtime_flag: [string, required]
      library_entry_ref: [string, required]

engagement_model:
  service_lines: [list, required, min 1]
    - service_line_name:
      lifecycle_stages: [list, min 3]
      pricing_structure: [enum: subscription | retainer | success_fee | hybrid | project]
      revenue_model: [MRR | project | hybrid]
  conversion_events: [list, required]
  disqualification_criteria: [list, required]
  out_of_scope_at_launch: [list, required]

positions_required:                       # NEW v3 — The Office names these
  - position_title: [string, required]    # "Capital Underwriting Analyst"
    reports_to: [position_title or "venture_operator", required]
    duties: [list, required]
    forge_modules_operated: [list, required]
    source_department: [enum: 12 Village departments, required]
    compliance_flags_in_scope: [list, required]
    headcount: [int, required]
    trust_tier_ceiling: [auto_execute | propose | suggest, required]

capacity_demand:                          # NEW v3 — replaces estimated_agent_count
  agent_days_per_week: [number, required]
  peak_concurrent_positions: [int, required]
  shift_pattern: [string, required]
  ramp_schedule: [list]                   # week → agent-days

forge_dependencies:
  operating_forge: [enum, required]
  training_forge: [SimForge, always]
  forge_bindings:
    - forge: [enum, required]
      api_version: [semver, required]     # pinned; "latest" FAILS
      criticality: [enum: hard | soft, required]
      modules_expected: [list]
      compliance_flags_propagated: [list, required]
      fallback_behavior: [enum: halt | queue | skip_step | manual_handoff, required]
      rate_limit_policy: {max_rps, burst, backoff, on_429}
      credential_mode: [enum: brokered | native, required, default: brokered]
      cost_center: [string, required]
      module_gap: [bool, default: false]
  external_software:
    - name, purpose, criticality
      data_types_transmitted: [list, required]
      dpa_or_baa_status: [enum: signed | pending | not_required, required]

forge_operating_instructions:             # NEW v3 — the education layer
  - forge_id, module_id
    instruction_version: [semver, required]
    forge_api_version: [semver, required]
    version_sensitivity: [enum: major | major.minor | major.minor.patch,
                          required, default: major.minor]
    sensitivity_rationale: [string, required if major.minor.patch]
    content_hash: [string, required]
    authored_by: [human_id, required]

triggers:
  - trigger_id, type: [scheduled | forge_webhook | human_initiated | agent_initiated]
    max_invocations_per_hour: [int, required if agent_initiated]
    max_chain_depth: [int, default: 3, required if agent_initiated]

budget:
  monthly_usd_cap, soft_cap_pct (default 80), hard_cap_action: [pause | throttle]
  per_agent_usd_daily_cap, per_task_usd_ceiling: [required]
  cost_alert_recipients: [list, required, min 1]

human_capacity:
  - human_name, role, coverage_hours, timezone
    backup_human: [required if compliance_officer or trust_safety_escalation]
    max_daily_approvals: [int, required]
    auth_method: [sso_mfa | mfa_only, required]

separation_of_duties:
  gate_signoff_policy: [distinct_humans | single_human_permitted, required]
  single_human_justification: [required if single_human_permitted]

availability:
  office_unreachable_behavior: [halt | degrade_to_propose, required]
  audit_write_failure_behavior: [fail_closed | queue_durable, required]
  rto_minutes, rpo_minutes: [required]

data_retention:
  - data_type, retention, legal_basis
    deletion_mechanism: [crypto_shred | hard_delete | tombstone, required]

kpi_targets:
  day_30 / day_60 / day_90 / day_180:
    - kpi_name, target_value, unit
      measurement_source: [string, required]      # table.column or endpoint
      measurement_frequency: [required]
      owner: [required]

lifecycle:
  teardown_policy: {forge_tenant_disposition, audit_log_disposition,
                    phi_disposition, teardown_signoff_required}
```

---

## 🧭 OUTPUT RECIPE — PARTS 2–16

### PART 2 — Executive Summary
What The Office is: **the layer that lets Village agents operate Forges on behalf of ventures, and governs that operation.**

State the day-to-day loop first, because it is what The Office does once running: a venture Pack arrives → The Office names the positions the venture needs → appoints named agents from the existing 106-agent roster by department fit and certification state → generates workflow, task ledger, curriculum, Forge manifest, and runtime config → a working agent team exists for a venture that had none an hour earlier. The Village carries several ventures simultaneously; one venture per agent per shift. **The Office appoints agents; the Village creates them.**

Then state what has to exist first: the Village and the Forges are not connected, and nothing above is possible until they are.

Who uses it. What ships at v1. The seven artifacts produced from a Pack. Success definition, stated honestly: *"A Village agent, holding an Office-issued identity, completes a real authenticated Forge operation for a named venture, with a per-agent audit entry, under a SimForge operation certification."* That has never happened. It is the bar.

Out of scope at v1: stated explicitly.

### PART 3 — Naming, Category & Positioning
Rank ≥5 names (The Office, Concourse, Steward, The Commons, Overseer, +). Pronounceability, domain, [TM SEARCH REQUIRED], tonality, collision with Forge naming. Recommend three, pick one. Define the category — not "AI orchestration platform." Positioning in "For X who Y, we are Z unlike A because B." Explicit rejection: not LangChain, not CrewAI, not AutoGen, not workflow automation.

### PART 4 — Platform Architecture (seven layers)
Diagram + table. For each: responsibilities, data owned, dependencies, v1 scope.
1. **Identity & Execution** (Part 1) — the bridge
2. **Pack Ingest & Validation**
3. **Generator Layer** — seven generators
4. **Knowledge Base Layer** — five stores
5. **Shift & Assignment Layer** — allocator, capacity, rotation
6. **Governance & Observability** — audit, compliance, cost, dashboards
7. **Administration** — the console

### PART 5 — The Seven Generators
Deterministic transformers. Same Pack in, same artifacts out. LLM temperature >0 only inside sub-tasks where determinism is impossible, never at structural level.

**5.1 Role Definition Generator.** In: Pack. Out: `positions_required` fully specified — venture-specific position titles the Village roster does not natively contain (Capital Underwriting Analyst, Clinician Credentialing Specialist, Buyer Network Manager, Capital Architect), each with duties, reporting line, Forge modules operated, source department, compliance flags in scope, trust-tier ceiling. **The Office names the positions; it does not look them up.**

**5.2 Appointment Generator.** In: positions + Village roster + certification state. Out: named agent appointed to each position, with the gap report. Rules: appointment requires Unit A operation certification for every module the position operates, **and** Unit B department context certification. Uncertified candidates appear as `requires_certification`, never as filled. Shortfall does not auto-reject and does not auto-appoint uncertified agents — it flags to Ivan with the three capacity numbers (§7.2).

**5.3 Workflow Generator.** In: `lifecycle_stages`. Out: `# | Step | Stage | Position | Supporting | Forge Module(s) | Trigger | Inputs | Outputs | Success Metric | Failure & Escalation | Compliance Flag`. Every step names a module resolving in `forge_module_registry`; every step carries a flag or explicit NONE; every step has an escalation path.

**5.4 Task Ledger Generator.** In: Workflow + Appointments. Out: every task → (position, agent, module, trust tier, flags, SLA, expected volume, idempotency class). Required additional output: projected daily approval volume per human role.

**5.5 Curriculum Generator.** In: Pack + Workflow + Appointments + Forge Operating Instructions. Out: Scenario Pack for SimForge — domain scenarios and operation scenarios, with coverage denominators stated. The Office authors; SimForge runs.

**5.6 Forge Manifest Generator.** In: bindings + Workflow + Task Ledger. Out: the venture's Bill of Materials plus three-way reconciliation (Declared / Required / In-Use). `REQUIRED_NOT_DECLARED` fails the Pack. `IN_USE_NOT_REQUIRED` is a HIGH incident and auto-throttle. `criticality: hard` + `module_gap: true` cannot provision.

**5.7 Runtime Config Generator.** In: all above. Out: idempotent deployment config — issues grants, wires integrations, applies flags, seeds knowledge bases, registers the engagement. Consumes the Manifest, not the Pack. Re-running produces identical state with zero duplicate side-effects.

### PART 6 — The Five Knowledge Bases
**6.1 Forge Operating Instructions** — *elevated from filing cabinet to curriculum.* Per Forge, per module: what it does and does not do; function-level inputs and meanings; correct sequence; failure signatures (failure vs. slow success vs. silent partial); retry-vs-escalate rules; never-do list; compliance coupling. Versioned; `content_hash` binds certification. This is what agents are educated on and what SimForge tests against.
**6.2 Business Playbooks** — venture SOPs. Cross-venture patterns shareable by opt-in only.
**6.3 Compliance Library** — structured: framework, jurisdiction, applicability rule, agent-behavior implication, escalation trigger, citation.
**6.4 Persona Library** — SimForge only, never production.
**6.5 Historical Records** — append-only institutional memory.

### PART 7 — Shifts, Capacity & Assignment
**7.1 Unit of account.** Agent-days. 1 agent-day = 1 real hour. Capacity demand and supply both denominated this way.

**7.2 The three numbers.** Every shortfall flag reports all three; one number hides the state:
- Certified and free this window
- Certified but allocated to another venture
- Produced but not yet certified (`never_certified` | `in_training`)

**7.3 Shortfall handling.** Flag to Ivan for decision. Never auto-reject the Pack. Never auto-appoint uncertified agents. Never silently reduce scope.

**7.4 Rotation and the Deputy cushion.** Respect the Village's existing mechanics — Deputy on-shift gating, 1.5× cushion through rest days. The Office allocates within them; it does not override them.

**7.5 Boundary discipline.** **One venture per agent per shift — locked.** No mid-shift venture switching under any condition, including non-PHI ventures; a single uniform rule is enforceable where a conditional one is not. At every shift boundary, in order: PHI-tagged working memory flushed and flush verified → grants re-resolved for the incoming venture → venture context switched → audit entry written. A failed flush blocks the next assignment. Capacity is therefore denominated in whole agent-days, matching the Village clock and the Deputy cushion math.

Accepted cost: an agent whose venture queue empties mid-shift idles until the boundary. Recoverable later by tuning shift length. Not traded against isolation.

### PART 8 — Multi-Venture Isolation
Tenant boundary is the **venture engagement**, not the Village. Specify: per-engagement data isolation; cross-venture referral protocol with consent capture and audit (Burkham → Collingswood, MedLink → cyber, Greenstone → Burkham); shared vs. isolated services.

**The PHI wall is temporal.** MedLink's PHI must never reach Collingswood's FunnelForge CDP — and the same agent may serve both across consecutive shifts. Required:
- PHI tagged at write time, not inferred at flush time
- Mandatory clear at every boundary, agent-uninterruptible
- Flush verified and audited; a failed flush **blocks the next assignment** rather than logging and continuing
- Enforced regardless of certification state — this is a control, not a competence claim

[LEGAL REVIEW REQUIRED — intercompany BAAs and referral-fee instruments between Green Companies entities.]

### PART 9 — Governance, Audit & Compliance
Append-only signed audit log: every Forge call, grant, revocation, tier change, KB update, kill-switch event, shift boundary. Retention per `data_retention`. Trust-tier enforcement in the call path with named-human approval on change. Compliance-flag enforcement (HIPAA → PHI wall; two-party consent → recording disclosure on every VoiceForge call). Incident response: detection → triage → containment → disclosure → post-mortem, cross-venture aggregation. Regulator response: structured export on demand (CFPB, FTC, HHS OCR, state DFI). Revocation as kill switch (§1.4). Named-human accountability — humans sign, not agents.

### PART 10 — Forge Integration Map
Table per Forge: `Integration Surface | Auth Model | credential_mode | Data Contract | Rate Limit | Migration Status | v1 or Later`. One row per Forge plus SimForge. Cover per-venture provisioning, grant wiring, flag propagation, and migration status from brokered to native credentials.

### PART 10.1 — SimForge Contract (settled — see companion doc, Rev 3)
Ownership: The Office authors scenario content; SimForge owns scenario schema, rubric, threshold, and the held-out set. **The Office may not read the held-out set — structural, not procedural. Ship condition.**

Two certification units, both required for assignment: **Unit A** `agent × forge × module` (operation competence). **Unit B** `department × forge × context` (judgment). Department certification is necessary, never sufficient.

Two rubrics, never merged: the 8-dimension domain rubric, and a purpose-built operation rubric (sequence correctness, failure recognition, escalation discipline, never-do adherence, recovery; final set pending). Separate version stamps, separate re-cert triggers, no composite score.

States distinguished always: `certified | stale_instructions | stale_forge | in_training | never_certified | failed | revoked`. `TIMEOUT` never resolves to PASS. `NOT_RUN` never reported as failure. Certification binds to `content_hash`; mismatch voids. Version sensitivity per module, default `major.minor`.

**Certified tier caps declared tier.** The Pack declares a ceiling; SimForge sets the actual.

**Held-out partition ownership — resolved (J8).** SimForge owns the partition outright. Held-out scenario content lives in SimForge storage; The Office holds none of it and exposes no endpoint, field, log, query, backup, or export that returns it. The Office's obligation is negative — there is no read path to build, only one never to build.

**Automated no-read-path check — required.** Because Green Companies operates both sides of this boundary, self-attestation is the weakest possible enforcement for the one control whose entire purpose is preventing one side from seeing the other's content. Therefore:

- Every field in every SimForge → Office response payload is enumerated in a manifest.
- A test asserts that no enumerated field can carry scenario content, and that no endpoint returns scenario bodies under any parameter combination.
- The test runs in the golden-test suite on every build. Adding a field without updating the manifest fails the build.
- Test failure blocks release of both operation certification and Gate 9.5.

This converts SimForge's ship condition — structural, not procedural — into something a machine verifies continuously rather than something two parties assert about themselves.

### PART 11 — Provisioning Pipeline (17 gates)

| # | Gate | Blocks on |
|---|---|---|
| 0 | **Bridge operational for required Forges** | Part 1 incomplete for any `hard` binding |
| 1 | Pack authored | — |
| 2 | Pack Validator | Any FAIL rule |
| 3 | Generators 1–6 run | Generator error |
| 3.5 | Forge Manifest reconciliation | `REQUIRED_NOT_DECLARED`; `hard` + `module_gap` |
| 4 | Human review of artifacts + BOM + appointment gap report | Operator rejection |
| 4.5 | Capacity & budget feasibility | Approvals > capacity; spend > cap; unfilled positions |
| 5 | Sandbox Forge grants issued | Provisioning failure |
| 6 | Knowledge bases seeded, instructions indexed | `[COMPLIANCE LIBRARY GAP]` on declared framework |
| 7 | Engagement registered; agents appointed but **grants inactive** | — |
| 8 | Curriculum → SimForge (domain + operation) | — |
| 9 | Readiness Gate per role per domain | Any role-domain fail |
| 9.5 | Held-out adversarial set | Requires the one-way partition to exist |
| 10 | Named-human sign-off bound to artifact hashes | Missing signature; SoD violation |
| 11 | Production grants activated | — |
| 12 | Live; tiers active; revocation armed | — |
| 13 | Backup + restore drill verified | Failed restore |
| 14 | Continuous certification | — |
| 15 | Monthly manifest reconciliation sweep | Undispositioned `UNDECLARED` |
| 16 | Teardown (terminal) | Sign-off per policy |

Gate 0 is new and non-negotiable: no engagement provisions against a Forge the bridge does not yet reach.

### PART 12 — Cost, Metering & Budget
Shares `agent_call_ledger`. Metering points: LLM completion, Forge call, external software, SimForge run, KB indexing. Ladder: per-task ceiling → task halts; per-agent daily cap → agent paused; soft cap → **all auto_execute downgrades to propose across the engagement**; hard cap → pause or throttle, Ivan-only reversal. Reporting: cost per completed operational task per venture — the number that proves or disproves the thesis.

### PART 13 — Availability & Failure Semantics
Audit-write failure: fail-closed on compliance-flagged actions, durable-queue otherwise. Office unreachable: degrade to propose after grace, halt at 4× grace, **never fail open**. Broker unreachable: agents cannot reach Forges — that is correct behavior, not an outage to route around. Backup/restore with RTO/RPO and quarterly tested drill. Health ladder GREEN → AMBER → RED → BLACK.

### PART 14 — Human Capacity, Identity & Separation of Duties
`office_human`, `office_human_role`, `signoff_record` with artifact-hash binding — artifact change voids signature. SoD declared per Pack; single-human justification surfaced verbatim in regulator exports. Backup human required on all compliance and T&S roles. **Approval-capacity rule (FAIL):** projected daily approvals × median review minutes ≤ coverage hours × 60 × 0.6. Rubber-stamp detection: sub-5-second approval clusters raise a governance flag.

### PART 15 — Forge Manifest & Utilization
Three states reconciled (Declared / Required / In-Use) with four mismatch handlers. `forge_registry`, `forge_module_registry` (including `idempotency_support`), `agent_forge_grant`, `agent_call_ledger`. Forge Map console screen: Required graph, In-Use live, Reconciliation diff, cross-venture blast-radius matrix.

### PART 16 — Runtime Operations
Trigger taxonomy — `agent_initiated` rate- and depth-limited. Concurrency: optimistic lock with lease + heartbeat; idempotency keys on all mutating calls; `at_most_once` endpoints never auto-retried. `trace_id` propagates Village → Office → Forge. Secrets: vault-backed, per-Forge rotation, two-human break-glass. **Testing The Office itself:** golden Packs with snapshot-asserted generator output, contract tests per Forge connector, validator fixtures, provisioning idempotency test. Operator onboarding and permissions ramp. Teardown lifecycle — retention survives decommission.

### PART 17 — Administration Console
Pack Editor · Provisioning Console · **Agent Identity & Grants** (issue, scope, revoke, migration status per Forge) · Venture Directory · Venture Dashboard · Agent Registry (certified tier vs. declared tier side by side) · Shift & Capacity view (three numbers) · Knowledge Base Manager · **Forge Operating Instructions authoring** (author, version, diff, staleness) · Readiness Gate view · Forge Map · Compliance Dashboard · Revocation Controls · Audit Log Explorer.

---

## ✅ PACK VALIDATOR

| # | Rule | Result |
|---|---|---|
| V1 | All required fields present | FAIL |
| V2 | Bridge operational for every `hard` Forge binding (Gate 0) | FAIL |
| V3 | Every compliance framework has a resolving `runtime_flag` | FAIL |
| V4 | Every framework has `library_entry_ref` or explicit gap flag | FAIL |
| V5 | Every KPI has `measurement_source` + `frequency` + `owner` | FAIL |
| V6 | Every Workflow module ref resolves in `forge_module_registry` | FAIL |
| V7 | `api_version` pinned; not `latest` | FAIL |
| V8 | No `criticality: hard` with `module_gap: true` | FAIL |
| V9 | Every `external_software` transmitting PHI has signed BAA/DPA | FAIL |
| V10 | Every `positions_required` entry names ≥1 Forge module and a source department | FAIL |
| V11 | Every position's modules have Forge Operating Instructions authored | FAIL |
| V12 | Every instruction set has `version_sensitivity` + `content_hash` | FAIL |
| V13 | Projected daily approvals ≤ capacity × 0.6 | FAIL |
| V14 | Compliance + T&S roles have `backup_human` | FAIL |
| V15 | `gate_signoff_policy` declared; justification if single-human | FAIL |
| V16 | `agent_initiated` triggers have rate + depth limits | FAIL |
| V17 | `data_retention` covers every sensitive data type | FAIL |
| V18 | Budget caps present | FAIL |
| V19 | `availability` complete incl. RTO/RPO | FAIL |
| V20 | Every binding has `rate_limit_policy` and `credential_mode` | FAIL |
| V21 | SimForge binding present, `criticality: hard` | FAIL |
| V22 | Every compliance flag appears in ≥1 scenario | FAIL |
| V23 | ≥3 scenarios per role × domain; ≥1 `expected_escalation` per role | FAIL |
| V24 | Unfilled positions in appointment output | FAIL at Gate 4.5 |
| V25 | Declared Forge with zero `required_by` references | WARN |
| V26 | `fallback_behavior` on every `soft` Forge | WARN |
| V27 | Any `[MODULE GAP]` in Pack | WARN + surfaced at Gate 4 |

---

## 🔓 OPEN DECISIONS

| # | Decision | Blocks | Recommendation |
|---|---|---|---|
| J1 | Final name | Domain, repo, UI | **Concourse.** [TM SEARCH REQUIRED] |
| J2 | ~~Mid-shift venture switching~~ | — | **RESOLVED: one venture per shift.** No switching under any condition. Flush at boundary only |
| J3 | One human signing all Gate 10 roles? | SoD | Permit with written justification; backups required regardless |
| J4 | Which Forge gets the bridge first | Part 1 step 2 | **CRE Forge** — Greenstone has no PHI, smallest compliance surface |
| J5 | Monthly budget cap per venture | Cost ladder | Set low; caps are easier to raise than to discover |
| J6 | Compliance Library sharing: opt-in or default | KB isolation | Opt-in |
| J7 | CyberForge / StyleForge timing | Cyber venture entirely | Cyber cannot pass Gate 3.5. Spec CyberForge or drop cyber from v1 |
| J8 | ~~Owner of the held-out partition~~ | — | **RESOLVED: SimForge owns it outright.** Automated no-read-path check required in golden-test suite |
| J9 | Which dimension grades `phi_boundary_flush` | Scenario ships ungraded | Recommend a dedicated `data_boundary_discipline` dimension. **SimForge's call — still open** |

---

## 🔨 BUILD ORDER

**Phase 0 — the bridge.** Part 1, steps 1–7, against one Forge. Ends when one agent makes one real authenticated call. Nothing else starts first.

**Phase 1 — governance in the path.** Trust tiers, manifest check, rate limits, revocation, ledger. Part 1 steps 8–9.

**Phase 2 — instructions and certification.** Author Forge Operating Instructions for the first Forge's modules. Stand up SimForge's held-out partition **and the automated no-read-path check in the golden-test suite** — the check ships with the partition, not after it. Run operation certification for a handful of agents. This is where SimForge's work becomes usable.

**Phase 3 — one venture.** Greenstone. Hand-author its Pack, run the generators, appoint agents, certify, provision sandbox, then live.

**Phase 4 — generalize.** Remaining Forges, remaining ventures, console breadth.

**Do not build Parts 12–17 before Phase 0 completes.** They govern a capability that does not yet exist.

---

## ✅ SELF-AUDIT

- [ ] One Village, 106 agents, 12 departments — not five Villages
- [ ] Gardner treated as an agent (COO), not a platform layer
- [ ] Bridge treated as non-existent and as Part 1
- [ ] Identity brokered, per-agent, revocable; native migration path specified
- [ ] Removing authentication explicitly rejected with stated reasons
- [ ] Client library mandatory; network policy makes bypass impossible
- [ ] Forge-side attribution gap stated as a known weakness, not hidden
- [ ] Revocation specified as the kill switch, checked per call, never cached
- [ ] The Office names positions; appoints from the existing roster
- [ ] Capacity in agent-days; three numbers on every shortfall; flags to Ivan
- [ ] Village Deputy mechanics respected, not overridden
- [ ] One venture per shift enforced uniformly; no conditional mid-shift switching
- [ ] PHI wall temporal; flush verified, audited, blocks next assignment on failure
- [ ] Forge Operating Instructions as curriculum, versioned, hash-bound
- [ ] Both certification units required for assignment
- [ ] Held-out partition SimForge-owned; Office has no read path by construction
- [ ] Automated no-read-path check in golden-test suite; failure blocks release
- [ ] Two rubrics never merged; states never collapsed; TIMEOUT never PASS
- [ ] Certified tier caps declared tier
- [ ] Gate 0 blocks provisioning against an unreached Forge
- [ ] Held-out partition named as non-existent and on the critical path
- [ ] Approval capacity validator-enforced; rubber-stamp detection specified
- [ ] Coverage denominators reported everywhere
- [ ] Every assumption marked; every gap flagged
- [ ] No re-derivation of ventures or Forges

---

## ⚠️ BEFORE BUILDING

The success bar is one sentence: **a Village agent, holding an Office-issued identity, completes a real authenticated Forge operation for a named venture, with a per-agent audit entry, under a SimForge operation certification.**

Every part of that sentence is currently false. The agent has no identity, no path, no certification, and no venture context.

Build toward that one sentence before building anything that governs it. Phase 0 against CRE Forge is roughly a week of work and it is the only thing in this document that has never been proven possible.
