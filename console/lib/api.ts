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

/** Raised when there is no session at all, so a page can redirect rather than throw. */
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
