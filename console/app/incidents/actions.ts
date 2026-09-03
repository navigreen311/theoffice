"use server";

import { revalidatePath } from "next/cache";

import { api, ApiError } from "@/lib/api";

export type IncidentActionState = { ok?: string; error?: string } | null;

function fail(error: unknown): IncidentActionState {
  if (error instanceof ApiError) return { error: error.message };
  throw error;
}

/** File an incident a person noticed. */
export async function raiseIncidentAction(
  _prev: IncidentActionState,
  form: FormData,
): Promise<IncidentActionState> {
  const summary = String(form.get("summary") ?? "").trim();
  if (!summary) {
    return {
      error: "A kind and a severity with nothing attached is a label, not a detection.",
    };
  }

  const venture = String(form.get("venture_id") ?? "").trim();

  try {
    const created = await api.post<{ incident_id: string }>("/api/incidents", {
      severity: String(form.get("severity") ?? "MEDIUM"),
      kind: String(form.get("kind") ?? "external_report"),
      detection_source: String(form.get("detection_source") ?? "external_report"),
      summary,
      venture_id: venture || null,
    });
    revalidatePath("/incidents");
    return {
      ok: `Raised ${created.incident_id.slice(0, 8)}. It cannot be edited — the response is appended.`,
    };
  } catch (error) {
    return fail(error);
  }
}

/** Append one stage account to an incident's response timeline. */
export async function appendAccountAction(
  _prev: IncidentActionState,
  form: FormData,
): Promise<IncidentActionState> {
  const incidentId = String(form.get("incident_id") ?? "");
  const account = String(form.get("account") ?? "").trim();
  if (!account) {
    return {
      error:
        "Marking a stage done with nothing attached is the status change this table exists to prevent.",
    };
  }

  try {
    await api.post(`/api/incidents/${incidentId}/accounts`, {
      stage: String(form.get("stage") ?? "triage"),
      account,
    });
    revalidatePath(`/incidents/${incidentId}`);
    revalidatePath("/incidents");
    return { ok: "Appended. This cannot be edited or removed." };
  } catch (error) {
    return fail(error);
  }
}
