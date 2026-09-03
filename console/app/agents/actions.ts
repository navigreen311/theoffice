"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, type RosterDiff } from "@/lib/api";

export type RosterState = {
  error?: string;
  ok?: string;
  diff?: RosterDiff;
  /** Echoed back so the paste box keeps its contents after a round trip. */
  source?: string;
};

/**
 * Read a pasted roster into rows.
 *
 * Two formats, because a Village roster arrives as whatever somebody can export: CSV
 * (`ref,name,department`) or JSON. Neither is validated here beyond shape - the server
 * checks departments against the same list a Pack position is validated against, and
 * doing it twice would mean two answers to one question.
 */
function parseRoster(text: string): { village_agent_ref: string; agent_name: string; department: string }[] {
  const trimmed = text.trim();
  if (!trimmed) return [];

  if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
    const parsed = JSON.parse(trimmed);
    const rows = Array.isArray(parsed) ? parsed : parsed.agents;
    return rows.map((row: Record<string, string>) => ({
      village_agent_ref: String(row.village_agent_ref ?? row.ref ?? ""),
      agent_name: String(row.agent_name ?? row.name ?? ""),
      department: String(row.department ?? ""),
    }));
  }

  return trimmed
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => {
      const cells = line.split(",").map((cell) => cell.trim());
      return {
        village_agent_ref: cells[0] ?? "",
        agent_name: cells[1] ?? "",
        department: cells.slice(2).join(",").trim(),
      };
    })
    // A header row is the most common first line of a pasted CSV.
    .filter((row) => row.village_agent_ref.toLowerCase() !== "village_agent_ref");
}

/**
 * What importing this roster would change. **Writes nothing.**
 *
 * Separate from applying it because an import can remove agents, and an agent that
 * leaves the Village holding grants is a revocation somebody has to perform rather than
 * a row that quietly disappears.
 */
export async function previewRosterAction(
  _prev: RosterState | null,
  form: FormData,
): Promise<RosterState> {
  const source = String(form.get("roster") ?? "");
  if (!source.trim()) return { error: "Nothing to import." };

  let agents;
  try {
    agents = parseRoster(source);
  } catch (error) {
    return {
      error: `Could not read that as CSV or JSON: ${(error as Error).message}`,
      source,
    };
  }
  if (agents.length === 0) return { error: "No rows found in that roster.", source };

  try {
    const diff = await api.post<RosterDiff>("/api/agents/roster/preview", { agents });
    return { diff, source };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}`, source };
    throw error;
  }
}

/** Apply a roster the operator has already seen a diff for. */
export async function importRosterAction(
  _prev: RosterState | null,
  form: FormData,
): Promise<RosterState> {
  const source = String(form.get("roster") ?? "");
  if (!source.trim()) return { error: "Nothing to import." };

  try {
    const diff = await api.post<RosterDiff>("/api/agents/roster", {
      agents: parseRoster(source),
    });
    revalidatePath("/agents");
    return {
      ok:
        `Roster imported: ${diff.incoming_total} agents, ${diff.added.length} new, ` +
        `${diff.departed.length} departed, ${diff.moved.length} moved department.`,
      diff,
    };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}`, source };
    throw error;
  }
}

/**
 * Make Village agents appointable.
 *
 * Not a create — the agents already exist. This records that The Office recognises them,
 * which is what lets them be granted and certified.
 */
export async function issueIdentitiesAction(
  _prev: RosterState | null,
  form: FormData,
): Promise<RosterState> {
  const refs = form.getAll("village_agent_ref").map(String).filter(Boolean);
  if (refs.length === 0) return { error: "No agent selected." };

  try {
    const result = await api.post<{
      issued: { village_agent_ref: string }[];
      refused: { village_agent_ref: string; reason: string }[];
    }>("/api/agents/identities", { village_agent_refs: refs });

    revalidatePath("/agents");
    const issued = result.issued.length;
    // Refusals are reported, not summed away: a bulk issue where four of twelve were
    // refused is a different outcome from one where all twelve worked.
    return {
      ok:
        `${issued} identit${issued === 1 ? "y" : "ies"} issued.` +
        (result.refused.length
          ? ` ${result.refused.length} refused — ${result.refused
              .map((row) => `${row.village_agent_ref}: ${row.reason}`)
              .join("; ")}`
          : ""),
    };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}

/**
 * Record a Village agent an import cannot see.
 *
 * Named for what it does. "Add agent" would imply The Office creates agents, which it
 * does not, and the control would become a second source of truth for who exists.
 */
export async function registerAgentAction(
  _prev: RosterState | null,
  form: FormData,
): Promise<RosterState> {
  const ref = String(form.get("village_agent_ref") ?? "").trim();
  const name = String(form.get("agent_name") ?? "").trim();
  const department = String(form.get("department") ?? "").trim();

  if (!ref) {
    return {
      error:
        "The Village's own reference is required. Without it there is nothing for a " +
        "later roster import to reconcile against.",
    };
  }

  try {
    await api.post("/api/agents/village", {
      village_agent_ref: ref,
      agent_name: name,
      department,
    });
    revalidatePath("/agents");
    return { ok: `${name} recorded as a Village agent. Issue an identity to appoint.` };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}

/** Revoke a grant, or every grant this agent holds. */
export async function revokeAction(
  _prev: RosterState | null,
  form: FormData,
): Promise<RosterState> {
  const scope = String(form.get("scope") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  const agentId = String(form.get("office_agent_id") ?? "");
  const grantId = String(form.get("grant_id") ?? "");

  if (!reason) return { error: "A revocation needs a reason. It is recorded against your name." };

  try {
    await api.post("/api/revocations", {
      scope,
      reason,
      office_agent_id: agentId || null,
      grant_id: grantId || null,
    });
    revalidatePath(`/agents/${agentId}`);
    revalidatePath("/agents");
    return { ok: `Revoked (${scope}). Recorded in the append-only log.` };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}
