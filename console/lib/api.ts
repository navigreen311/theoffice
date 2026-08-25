import "server-only";

import { cookies } from "next/headers";

/**
 * The Operations API client. **Server-side only.**
 *
 * The `server-only` import at the top is load-bearing: importing this module from a
 * client component is a build error, not a runtime surprise. That is what keeps the
 * token out of the browser rather than a convention someone has to remember.
 *
 * Why every call happens on the server:
 *
 *   - **No CORS.** The browser never makes a cross-origin request, so there is no CORS
 *     configuration to get wrong and no preflight to reason about.
 *   - **The token is never in JavaScript.** It lives in an httpOnly, sameSite=strict
 *     cookie, is read here, and is never serialised into a prop or a hydration payload.
 *     An XSS in this console cannot exfiltrate it.
 *
 * The alternative — token in localStorage, browser calls the API directly — needs CORS,
 * puts a credential where any script can read it, and buys nothing.
 */

const API_BASE = process.env.OFFICE_API_URL ?? "http://127.0.0.1:8080";
export const SESSION_COOKIE = "office_session";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly body: unknown,
  ) {
    super(`${status}: ${detail}`);
  }
}

/**
 * Raised when there is no usable session, so a page can redirect rather than throw.
 *
 * Two cases, and both must land here. No cookie at all is the obvious one. The other is
 * a cookie the API **rejects** — an expired token, a token from a database that has
 * since been rebuilt, a suspended human — which used to throw `ApiError(401)` instead.
 * No page caught that, so every screen answered with a 500 and a digest, and the only
 * way out was to know to clear a cookie you cannot read.
 *
 * A rejected credential is not an application error. It is the same situation as having
 * no credential, and it gets the same answer: go and sign in.
 */
export class NotAuthenticated extends Error {}

async function token(): Promise<string> {
  const value = cookies().get(SESSION_COOKIE)?.value;
  if (!value) throw new NotAuthenticated("no session cookie");
  return value;
}

async function request<T>(
  path: string,
  init: RequestInit & { token?: string } = {},
): Promise<T> {
  const bearer = init.token ?? (await token());
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...init.headers,
      Authorization: `Bearer ${bearer}`,
      "Content-Type": "application/json",
    },
    // Governance state is never served stale. A cached revocation list is a list that
    // can show a revoked agent as active.
    cache: "no-store",
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      (body as { detail?: string; message?: string } | null)?.detail ??
      (body as { message?: string } | null)?.message ??
      response.statusText;

    // 401 only. A 403 is a *authenticated* human without the authority for this action,
    // which several screens explain in place rather than bouncing to a login they are
    // already past — the access screen says whose screen it is not.
    if (response.status === 401) {
      throw new NotAuthenticated(detail);
    }
    throw new ApiError(response.status, detail, body);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string, opts?: { token?: string }) =>
    request<T>(path, { method: "GET", ...opts }),
  post: <T>(path: string, payload: unknown, opts?: { token?: string }) =>
    request<T>(path, { method: "POST", body: JSON.stringify(payload), ...opts }),
};

/** Verify a token by calling an authenticated route. Used by the sign-in handler. */
export async function verifyToken(candidate: string): Promise<boolean> {
  try {
    await api.get("/api/health", { token: candidate });
    return true;
  } catch {
    return false;
  }
}

// ------------------------------------------------------------------ response shapes

export type ControlHealth = {
  state: "fresh" | "stale" | "never_run" | "failing";
  healthy: boolean;
  status?: string;
  age_hours?: number;
  max_age_days: number;
  denominator?: number | null;
  last_run?: string;
  detail?: string;
};

export type HealthResponse = {
  controls: Record<string, ControlHealth>;
  healthy: boolean;
  unhealthy: string[];
};

export type ChainStatus = {
  ok: boolean;
  checked_count: number;
  first_break_audit_id: number | null;
  tail_gap: number;
  reason: string;
};

export type Incident = {
  incident_id: string;
  severity: string;
  kind: string;
  venture_id: string | null;
  office_agent_id: string | null;
  forge_id: string | null;
  module_id: string | null;
  detail: Record<string, unknown>;
  raised_at: string;
};

export type AgentRow = {
  office_agent_id: string;
  agent_name: string;
  department: string;
  status: string;
  live_grants: number;
  certifications: number;
  cert_states: string[];
  declared_tier_floor: string | null;
  certified_tier_floor: string | null;
};

export type AuditEntry = {
  audit_id: number;
  event_type: string;
  actor_type: string;
  actor_id: string;
  venture_id: string | null;
  subject: Record<string, unknown>;
  trace_id: string | null;
  ts: string;
  entry_hash: string;
};

export type VentureRow = {
  venture_id: string;
  agents: number;
  live_grants: number;
  monthly_usd_cap: string | null;
  hard_cap_reversed_at: string | null;
};

export type ForgeMapRow = {
  forge_id: string;
  module_id: string;
  is_required: boolean;
  criticality: string;
  module_gap: boolean;
  calls_30d: number;
};

export type DispositionRow = {
  venture_id: string;
  forge_id: string;
  module_id: string;
  disposition: string;
  call_count: number;
  reason: string | null;
};

export type ForgeMap = {
  venture_id: string;
  declared: ForgeMapRow[];
  declared_not_used: ForgeMapRow[];
  dispositions: DispositionRow[];
  pending_dispositions: DispositionRow[];
};

export type ModuleRow = {
  module_id: string;
  is_mutating: boolean;
  idempotency_support: string;
  compliance_flags_implied: string[];
  has_instructions: boolean;
  instruction_version: string | null;
  version_sensitivity: string | null;
};

export type ForgeRow = {
  forge_id: string;
  display_name: string;
  api_version: string;
  credential_mode: string;
  health_status: string;
  modules: ModuleRow[];
};

export type Capacity = {
  venture_id: string;
  certified_and_free: number;
  certified_but_allocated: number;
  produced_not_yet_certified: number;
  total_considered: number;
  note: string;
};

export type Gates = {
  venture_id: string;
  gate_15_pending_dispositions: number;
  signoffs: { gate: string; signatures: number }[];
  unassignable_grants: number;
};

export type GrantRow = {
  grant_id: string;
  forge_id: string;
  module_id: string;
  venture_id: string;
  trust_tier: string;
  is_assignable: boolean;
  revoked_at: string | null;
  unit_a_state: string | null;
  certified_tier: string | null;
};

export type AgentDetail = {
  identity: {
    office_agent_id: string;
    agent_name: string;
    department: string;
    status: string;
    village_agent_ref: string;
    revocation_reason: string | null;
  };
  grants: GrantRow[];
  forge_migration_status: {
    forge_id: string;
    credential_mode: string;
    health_status: string;
  }[];
  recent_shifts: {
    shift_id: string;
    venture_id: string;
    shift_start: string;
    shift_end: string;
    flush_verified: boolean;
  }[];
};

export type InstructionDetail = {
  forge_id: string;
  module_id: string;
  live: {
    instruction_version: string;
    forge_api_version: string;
    version_sensitivity: string;
    content_hash: string;
    content: Record<string, unknown>;
  } | null;
  versions: {
    instruction_version: string;
    forge_api_version: string;
    version_sensitivity: string;
    content_hash: string;
    authored_at: string;
    superseded_at: string | null;
  }[];
  certification_states: Record<string, number>;
};

export type InstructionDiff = {
  changed: string[];
  added: string[];
  removed: string[];
};

export type Proposal = {
  proposal_id: string;
  office_agent_id: string;
  venture_id: string;
  forge_id: string;
  module_id: string;
  task_id: string;
  trust_tier: string;
  payload: Record<string, unknown>;
  status: string;
  created_at: string;
  review_seconds: string | null;
};

export type PackTemplateCategory = {
  category: string;
  frameworks: string[];
  example: string;
};

export type RuleHit = { rule_id: string; message: string };

/**
 * A Pack's validation state. Four values, and the reason there are four rather than two
 * is `not_validated`: a rule that could not run has not passed. Rendering "no failures
 * found" the same way as "every rule passed" is the single thing this page must not do.
 */
export type PackValidation = {
  state: "failing" | "not_validated" | "warnings" | "valid";
  failures: RuleHit[];
  warnings: RuleHit[];
  not_run: RuleHit[];
  /** Rules evaluated at a later gate. Deferred is not the same as unrun. */
  deferred: RuleHit[];
  rules_checked: number;
};

export type PackVersionRef = {
  version: string;
  content_hash: string;
  authored_at: string;
  author: string | null;
};

export type PackArtifact = {
  name: string;
  count: number | null;
  persisted: boolean;
  note: string | null;
};

export type PackCard = {
  venture_id: string;
  display_name: string;
  validation: PackValidation;
  versions: {
    draft: PackVersionRef | null;
    live: PackVersionRef | null;
    provisioned: string | null;
  };
  drift: boolean;
  never_provisioned: boolean;
  signatures: number;
  signatures_voided_by_publish: boolean;
  schema: {
    present: number;
    total: number;
    missing: string[];
    required_missing: string[];
  };
  artifacts: PackArtifact[];
  nothing_generated: boolean;
};

export type PackDirectory = {
  as_of: string;
  packs: PackCard[];
  packless: string[];
  registered_ventures: number;
  unregistered_portfolio: PortfolioGap[];
  portfolio_size: number;
  rules_total: number;
  schema_blocks: number;
};

export type PackSummary = {
  venture_id: string;
  pack_version: string;
  content_hash: string;
  authored_at: string;
};

export type PackVersion = {
  pack_version: string;
  content_hash: string;
  authored_by: string;
  authored_at: string;
  superseded_at: string | null;
  /**
   * `draft` | `live` | `superseded`. Read this, never `superseded_at`: a draft has no
   * `superseded_at` either, so the old check rendered an unpublished draft with a green
   * "live" badge beside the version that was actually in force.
   */
  status: "draft" | "live" | "superseded" | "abandoned";
  /**
   * What became of it, in words: `live`, `draft`, `superseded by 1.1.0`, `abandoned
   * draft`. One word for both a released version replaced by a later release and a
   * draft nobody published is what made the history read as an unsorted list.
   */
  disposition: string;
  superseded_by: string | null;
  author: string | null;
  /** Provisioning runs that started from this version. The section promises this. */
  runs: number;
  last_run_at: string | null;
};

export type PackSource = {
  pack_version: string;
  content_hash: string;
  yaml_source: string;
};

export type PackDetail = {
  as_of: string;
  venture_id: string;
  live: PackSource | null;
  /** The unpublished draft. The editor opens this in preference to `live`. */
  draft: PackSource | null;
  validation: PackValidationReport | null;
  /**
   * The schema's block list, in document order. Presence is deliberately not here: the
   * editor's sidebar describes the buffer being typed into, and a parsed model reads an
   * optional field with a default as present even when the document never mentions it.
   */
  schema: {
    blocks: { name: string; required: boolean }[];
    total: number;
  };
  bindings: {
    /** Bound to the *artifacts* hash, which is generated from this Pack. */
    gate_10_signatures: number;
    open_runs: {
      run_id: string;
      pack_version: string;
      status: string;
      current_gate: string;
    }[];
  };
  versions: PackVersion[];
};

/** A rule, and how far this stage could actually get with it. */
export type StagedRule = RuleRow & {
  /** False when the rule could not be evaluated here at all. */
  evaluable: boolean;
  /** The gate that settles it, when this one cannot. */
  settled_at_gate: string | null;
  why_not_here: string | null;
  /** Passed here, and evaluated again later against real generator output. */
  rechecked_later: boolean;
  rechecked_reason: string | null;
  /**
   * The Pack blocks this rule reads, derived from the rule's own source. Lets the
   * editor mark the block a failure lives in rather than only listing the failure.
   */
  blocks: string[];
};

/**
 * Three states, never two.
 *
 * `passed + failed + not_evaluable` is the whole rule set. A rule that could not be
 * evaluated has established nothing, and folding it into a "checked" count produces a
 * badge claiming the document was examined more thoroughly than it was.
 */
export type PackValidationReport = {
  state: "failing" | "not_validated" | "warnings" | "valid";
  rules: StagedRule[];
  passed: number;
  failed: number;
  not_evaluable: number;
  /** Passed here but re-checked later. Not a failure, and not a clean bill either. */
  rechecked_later: number;
  rules_total: number;
};

export type RuleRow = {
  rule_id: string;
  severity: "FAIL" | "WARN";
  verdict: "PASS" | "FAIL" | "WARN" | "NOT_RUN";
  message: string;
};

export type ValidationResponse = {
  parsed: boolean;
  error?: string;
  venture_id?: string;
  passed: boolean;
  results: RuleRow[];
  failures: string[];
  warnings: string[];
  not_run: string[];
  rules_checked?: number;
};

export type LadderRow = {
  gate: string;
  /** Plain language, for scanning. `title` is what the gate actually checks. */
  name: string;
  title: string;
  /** One line on what the gate does, so a pending row is not just a name. */
  description: string;
  state: "passed" | "blocked" | "awaiting" | "running" | "pending";
  reason: string | null;
  evidence: Record<string, unknown>;
  recorded_at: string | null;
  /** Elapsed from the previous gate, so a slow gate is visible. */
  seconds: number | null;
  is_current: boolean;
  is_ceiling: boolean;
  /** Never ran, because the run stopped before reaching it. Not the same as "not yet". */
  downstream_of_stop: boolean;
};

/** Who ended a run, when, and the reason they gave. Read from the audit log. */
export type Disposition = {
  actor: string | null;
  at: string;
  reason: string | null;
  gate: string | null;
};

/**
 * Something a human should see at gate 4, and how much it matters.
 *
 * `severity` is the whole point: a rule that FAILs at gate 4.5 was being rendered in a
 * block labelled "Generator warnings" beside a genuine advisory, sharing a count. One
 * of those halts the run one gate later and the other does not.
 */
export type Advisory = {
  severity: "fail" | "warn";
  message: string;
  source: string;
  rule_id: string | null;
  /** The gate this will stop the run at, when it is a failure. */
  blocks_at: string | null;
  /** Pack blocks the rule reads, so "Fix in Pack editor" can land on one. */
  blocks?: string[];
};

export type RunStop = {
  gate: string;
  name: string;
  reason: string;
  evidence: Record<string, unknown>;
  at: string | null;
  /** Who acted at the gate — not who started the run. Different people, often. */
  actor: string | null;
};

export type RunCard = {
  run_id: string;
  status: string;
  /** The reader's vocabulary: `stopped at gate 4`, `at ceiling`, `cancelled`. */
  display_status: string;
  current_gate: string;
  current_gate_name: string;
  pack_version: string;
  started_at: string;
  completed_at: string | null;
  started_by: string | null;
  gates_passed: number;
  stop: RunStop | null;
};

export type ProvisioningCard = {
  venture_id: string;
  display_name: string;
  has_live_pack: boolean;
  live_pack_version: string | null;
  run: RunCard | null;
  ladder: LadderRow[];
  runs_total: number;
  resumable: boolean;
  resume_blocked_because: string | null;
  pack_changed: boolean;
};

export type ProvisioningDirectory = {
  as_of: string;
  ventures: ProvisioningCard[];
  startable: { venture_id: string; display_name: string }[];
  gates_total: number;
  ceiling_gate: string;
  portfolio_size: number;
  empty_ladder: LadderRow[];
};

export type Me = {
  human_id: string;
  display_name: string;
  roles: string[];
};

export type HistoryRun = {
  run_id: string;
  status: string;
  display_status: string;
  current_gate: string;
  current_gate_name: string;
  pack_version: string;
  started_at: string;
  completed_at: string | null;
  actor: string | null;
  gates_passed: number;
  reason: string | null;
};

/* ------------------------------------------------------- the Village roster */

/**
 * One agent, and how far into The Office it has got.
 *
 * `in_roster` and `has_identity` are different facts and the gap between them is the
 * page: the Village creates agents, The Office appoints them, and an agent in the first
 * set and not the second is visible but unappointable.
 */
export type RosterAgent = {
  village_agent_ref: string | null;
  agent_name: string;
  department: string;
  in_roster: boolean;
  roster_status: string;
  source: string | null;
  office_agent_id: string | null;
  has_identity: boolean;
  identity_status: string | null;
  live_grants: number;
  assignable_grants: number;
  certifications: number;
  /** The Pack's ceiling. `null` means no Pack appoints this agent — not a low tier. */
  declared_tier: string | null;
  /** What SimForge certified was earned. */
  certified_tier: string | null;
  /** The lower of the two, or null when neither exists. */
  effective_tier: string | null;
  /** Certified above the declared ceiling. The Pack is the ceiling, so this is wrong. */
  tier_inconsistent: boolean;
  /** Certification makes an agent eligible; a grant is what lets it reach a Forge. */
  certified_without_grants: boolean;
  last_shift: string | null;
};

export type RosterDepartment = {
  department: string;
  in_roster: number;
  with_identity: number;
  without_identity: number;
  agents: RosterAgent[];
};

export type RosterDirectory = {
  as_of: string;
  agents: RosterAgent[];
  departments: RosterDepartment[];
  departments_total: number;
  departments_represented: number;
  /** Rows in the Village roster. Zero means no roster has been imported. */
  roster_total: number;
  roster_imported: boolean;
  with_identity: number;
  without_identity: number;
  /** Identities whose Village agent the roster cannot account for. */
  unmatched_identities: number;
  capacity: {
    certified_and_free: number;
    holding_grants: number;
    not_yet_certified: number;
    no_identity: number;
  };
  all_departments: string[];
};

export type RosterDiff = {
  added: { village_agent_ref: string; agent_name: string; department: string }[];
  departed: {
    village_agent_ref: string;
    agent_name: string;
    department: string;
    live_grants: number;
    has_identity: boolean;
  }[];
  moved: {
    village_agent_ref: string;
    agent_name: string;
    from_department: string;
    to_department: string;
  }[];
  renamed: { village_agent_ref: string; from_name: string; to_name: string }[];
  unchanged: number;
  incoming_total: number;
  current_total: number;
};

/** A certification is always *for* a Forge and a module. Never a bare tier. */
export type Certification = {
  unit: "A" | "B";
  forge_id: string;
  module_id: string | null;
  department: string | null;
  state: string;
  certified_tier: string | null;
  instruction_content_hash: string | null;
  forge_api_version: string | null;
  rubric_kind: string | null;
  rubric_version: string | null;
  score: number | null;
  threshold: number | null;
  simforge_verdict: string | null;
  issued_at: string | null;
  updated_at: string | null;
};

export type ForgeAccess = {
  forge_id: string;
  credential_mode: string;
  /** The Forge itself is up. Says nothing about whether this agent can reach it. */
  health_status: string;
  grants_here: number;
  reachable: boolean;
};

/* ---------------------------------------------------------- the approval queue */

export type PendingApproval = {
  proposal_id: string;
  office_agent_id: string;
  agent_name: string | null;
  department: string | null;
  venture_id: string;
  forge_id: string;
  module_id: string;
  module_name: string | null;
  task_id: string;
  trust_tier: string;
  payload: Record<string, unknown>;
  payload_hash: string;
  created_at: string;
  /** When this stops being decidable. Expiry fails the task; it never approves it. */
  expires_at: string;
  trace_id: string;
  /** From the module registry — what the call would touch, not what the agent claims. */
  compliance_flags_implied: string[] | null;
  is_mutating: boolean | null;
};

export type DecidedApproval = {
  proposal_id: string;
  office_agent_id: string;
  agent_name: string | null;
  venture_id: string;
  forge_id: string;
  module_id: string;
  status: string;
  decision_reason: string | null;
  review_seconds: string | number | null;
  decided_at: string | null;
  reviewer: string | null;
  /** The payload as it stood at decision time — the row is never rewritten. */
  payload: Record<string, unknown>;
  payload_hash: string;
};

export type Reviewer = {
  venture_id: string;
  name: string;
  role: string;
  coverage_hours: number;
  timezone: string;
  backup_human: string | null;
  max_daily_approvals: number;
  median_review_minutes: number | null;
  decisions_today: number;
  remaining_today: number;
  median_seconds_today: number | null;
  matched_to_a_human: boolean;
};

export type ApprovalQueue = {
  as_of: string;
  pending: PendingApproval[];
  history: DecidedApproval[];
  reviewers: Reviewer[];
  metrics: {
    decisions_today: number;
    approvals_today: number;
    approval_rate: number | null;
    median_seconds: number | null;
    under_threshold: number;
    threshold_seconds: number;
    by_reviewer: {
      reviewer: string | null;
      decisions: number;
      approvals: number;
      fast_approvals: number;
      median_seconds: string | number | null;
    }[];
  };
  capacity: {
    reviewers: number;
    remaining_today: number;
    pending: number;
    over_capacity: boolean;
  };
  state: {
    live_grants: number;
    grants_below_auto: number;
    calls_ever: number;
    proposals_today: number;
  };
  /** Why the queue is empty, in this system's terms. Null when it is not empty. */
  empty_reason: string | null;
};

/* --------------------------------------------------- curriculum completeness */

/**
 * One of the eight required sections, and whether it teaches anything.
 *
 * `authored` used to mean a row exists. The live cre-forge curriculum satisfies that
 * with `"what_it_does": "Documented."` — every section present, none empty, a valid
 * content_hash over the lot, and certifications bound to it.
 */
export type CurriculumSection = {
  section: string;
  title: string;
  state: "complete" | "thin" | "stub" | "missing";
  /** Names the specific defect, for whoever has to fix it. Null when complete. */
  reason: string | null;
};

export type CurriculumQuality = {
  state: "complete" | "thin" | "stub" | "missing";
  sections: CurriculumSection[];
  complete: number;
  total: number;
  placeholder_sections: string[];
  missing_sections: string[];
  thin_sections: string[];
  /** `stub` or `missing`. A Pack may not pass V11 against one of these. */
  teaches_nothing: boolean;
};

export type InstructionModule = {
  forge_id: string;
  module_id: string;
  module_name: string | null;
  instruction_version: string;
  forge_api_version: string;
  forge_current_version: string | null;
  version_sensitivity: string;
  sensitivity_rationale: string | null;
  content_hash: string;
  authored_at: string | null;
  author: string | null;
  is_mutating: boolean | null;
  idempotency_support: string | null;
  compliance_flags_implied: string[] | null;
  certifications: number;
  quality: CurriculumQuality;
  /** Why the Forge has moved past what this curriculum tolerates. Null when it has not. */
  stale_forge: string | null;
  certifications_on_hollow: number;
};

export type InstructionForge = {
  forge_id: string;
  api_version: string;
  health_status: string;
  modules: InstructionModule[];
  unwritten: { forge_id: string; module_id: string; module_name: string | null }[];
  written: number;
  total: number;
  stub: number;
  thin: number;
};

export type InstructionDirectory = {
  as_of: string;
  forges: InstructionForge[];
  modules: InstructionModule[];
  unwritten: { forge_id: string; module_id: string; module_name: string | null }[];
  totals: {
    modules_with_instructions: number;
    forges_with_instructions: number;
    forges_registered: number;
    complete: number;
    thin: number;
    hollow: number;
    modules_without_instructions: number;
    certifications_on_hollow: number;
  };
};

export type BoundCertification = {
  office_agent_id: string;
  agent_name: string | null;
  department: string | null;
  state: string;
  certified_tier: string | null;
  updated_at: string | null;
};

export type RunSummary = {
  run_id: string;
  venture_id: string;
  pack_version: string;
  pack_hash: string;
  status: string;
  current_gate: string;
  artifacts_hash: string | null;
  started_at: string;
  completed_at: string | null;
  gates_passed: number;
};

export type RunDetail = {
  as_of: string;
  run_id: string;
  venture_id: string;
  pack_version: string;
  status: string;
  /** The reader's vocabulary. `awaiting_human` is a column value, not a sentence. */
  display_status: string;
  disposition: Disposition | null;
  current_gate: string;
  current_gate_name: string;
  artifacts_hash: string | null;
  ladder: LadderRow[];
  history: {
    gate: string;
    verdict: string;
    reason: string;
    evidence: Record<string, unknown>;
    recorded_at: string;
  }[];
};

// ------------------------------------------------------------- knowledge bases

export type StoreCoverage = {
  covered?: number;
  denominator?: number;
  uncovered?: string[];
  count?: number;
  entries?: number;
  shares?: number;
  blocking: boolean;
  note: string;
};

export type KnowledgeCoverage = {
  forge_operating_instructions: StoreCoverage;
  compliance_library: StoreCoverage;
  business_playbooks: StoreCoverage;
  persona_library: StoreCoverage;
  historical_records: StoreCoverage;
};

export type PlaybookRow = {
  playbook_id: string;
  venture_id: string;
  title: string;
  lifecycle_stage: string | null;
  playbook_version: string;
  content_hash: string;
  content: Record<string, unknown>;
  shared_from: string | null;
};

export type ShareRow = {
  playbook_id: string;
  title: string;
  from_venture: string;
  to_venture_id: string;
  reason: string;
  shared_at: string;
  revoked_at: string | null;
};

export type PlaybookResponse = {
  venture_id: string | null;
  playbooks: PlaybookRow[];
  shares: ShareRow[];
};

export type ComplianceEntry = {
  entry_ref: string;
  framework: string;
  jurisdiction: string[];
  applicability_rule: string;
  agent_behavior_implication: string;
  escalation_trigger: string;
  citation: string;
  runtime_flag: string | null;
  authored_at: string;
  updated_at: string;
};

/** Never carries a body. `office_app` holds no SELECT on `persona_body`. */
export type PersonaRow = {
  persona_id: string;
  venture_id: string;
  persona_name: string;
  target_persona: string;
  persona_version: string;
  body_hash: string;
  authored_at: string;
};

export type HistoryRow = {
  record_id: number;
  venture_id: string | null;
  record_type: string;
  summary: string;
  detail: Record<string, unknown>;
  actor_type: string;
  recorded_by: string | null;
  occurred_at: string;
  recorded_at: string;
};

/** A page that says what it did not show. See `Page` in `broker/app.py`. */
export type Paged<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type HumanRole = {
  role: string;
  venture_id: string | null;
  granted_by: string;
  granted_at: string;
};

export type HumanRow = {
  human_id: string;
  display_name: string;
  email: string;
  status: string;
  auth_method: string;
  created_at: string;
  suspended_at: string | null;
  has_token: boolean;
  roles: HumanRole[];
};

export type RevocationRow = {
  revocation_id: string;
  scope: string;
  reason: string;
  office_agent_id: string | null;
  agent_name: string | null;
  forge_id: string | null;
  module_id: string | null;
  venture_id: string | null;
  revoked_by: string;
  revoked_by_role: string;
  revoked_at: string;
  reinstated_at: string | null;
  reinstated_by: string | null;
};

export type IncidentRow = Incident & {
  resolution: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  // How the detection arrived, and who filed it if a person did. An incident somebody
  // reported must never render as one a control caught.
  detection_source: string;
  reported_by: string | null;
};

export type ControlRow = {
  id: string;
  name: string;
  cadence: string;
  checks: string;
  consequence: string;
  blocking: boolean;
  runnable_from_here: boolean;
  host_command: string | null;
  state: "fresh" | "stale" | "never_run" | "failing";
  healthy: boolean;
  last_run?: string;
  denominator?: number | null;
  age_hours?: number;
  max_age_days: number;
  detail?: string;
};

export type FrameworkRow = {
  framework: string;
  runtime_flag: string | null;
  library_entry_ref: string | null;
  declared_gap: boolean;
  has_flag: boolean;
  has_entry: boolean;
};

export type VentureCoverage = {
  venture_id: string;
  frameworks: FrameworkRow[];
  resolved: number;
  declared: number;
  assignable_grants: number;
  status: "ready" | "gaps" | "blocked";
  blocked_because: string | null;
  has_pack: boolean;
};

/** Every metric carries its denominator. That is enforced by the type. */
export type Metric = { value: number; denominator: number; note?: string };

export type ComplianceOverview = {
  as_of: string;
  controls: ControlRow[];
  scorecard: {
    ventures_live: Metric;
    agents_with_grants: Metric;
    frameworks_in_scope: Metric;
    controls_verified: Metric;
  };
  ventures: VentureCoverage[];
  chain_stats: {
    audit_entries: number;
    oldest_entry: string | null;
    agent_calls: number;
    last_agent_call: string | null;
  };
  library_entries: number;
};

export type VenturePhase = { name: string; state: "done" | "current" | "todo" };

export type VentureFramework = { framework: string; wired: boolean };

export type VentureCard = {
  slug: string;
  display_name: string;
  category: string;
  carries_phi: boolean;
  operating_forge: string | null;
  registered: boolean;
  has_pack: boolean;
  pack_version: string | null;
  status: string;
  gate: string | null;
  blocked_because: string | null;
  phases: VenturePhase[];
  gate_index: number;
  gate_total: number;
  positions_filled: number;
  positions_defined: number;
  live_grants: number;
  monthly_usd_cap: number | null;
  hard_cap_action: string | null;
  soft_cap_pct: number | null;
  hard_cap_reversed_at: string | null;
  spend_this_month: number;
  frameworks: VentureFramework[];
  frameworks_wired: number;
  last_activity: string | null;
};

export type PortfolioGap = {
  slug: string;
  display_name: string;
  category: string;
  operating_status: string;
  frameworks: string[];
  note: string;
};

export type VentureDirectory = {
  as_of: string;
  ventures: VentureCard[];
  missing: PortfolioGap[];
  portfolio_size: number;
  scorecard: {
    live: Metric;
    agents_appointed: Metric;
    spend_this_month: Metric;
    blocked: Metric;
  };
};
