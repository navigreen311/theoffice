"use server";

import { revalidatePath } from "next/cache";

import { api, ApiError } from "@/lib/api";

import type { Radius } from "./form";

export type RevokeState = { ok?: string; error?: string } | null;

function fail(error: unknown): RevokeState {
  if (error instanceof ApiError) return { error: error.message };
  throw error;
}

/**
 * What a revocation would stop, for the current selection.
 *
 * A read against existing state. It answers "how much is this", never "may you" — the
 * API decides authority, once, and reports the refusal. A second implementation of the
 * authorization rule here would drift from the first, and the drift would show up as the
 * console cheerfully offering an action the API then refuses, or worse, greying out one
 * it would have allowed.
 */
export async function blastRadiusAction(selection: {
  scope: string;
  office_agent_id: string | null;
  forge_id: string | null;
  module_id: string | null;
  venture_id: string | null;
}): Promise<Radius | null> {
  const query = new URLSearchParams({ scope: selection.scope });
  for (const [key, value] of Object.entries(selection)) {
    if (key !== "scope" && value) query.set(key, value);
  }
  try {
    return await api.get<Radius>(`/api/revocations/blast-radius?${query}`);
  } catch {
    // A radius that cannot be computed is shown as no radius rather than as zero.
    // Zero would read as "this stops nothing", which is the most dangerous wrong answer
    // this screen could give.
    return null;
  }
}

export async function revokeAction(
  _prev: RevokeState,
  form: FormData,
): Promise<RevokeState> {
  const scope = String(form.get("scope") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  if (!reason) {
    return { error: "A reason is required. It is surfaced in regulator exports." };
  }

  const field = (name: string) => {
    const value = String(form.get(name) ?? "").trim();
    return value === "" ? null : value;
  };

  try {
    await api.post("/api/revocations", {
      scope,
      reason,
      office_agent_id: field("office_agent_id"),
      forge_id: field("forge_id"),
      module_id: field("module_id"),
      venture_id: field("venture_id"),
    });
    revalidatePath("/revocations");
    return {
      ok: "Revoked. It takes effect on the target's next call, not its next session.",
    };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Lift a revocation.
 *
 * §1.4 requires a documented ritual and a named human. At venture and Forge scope it
 * also requires a second: one person's judgement created a stop that reaches an
 * engagement or the whole portfolio, and one person's judgement should not be enough to
 * end it. The domain function refuses without it and so does a CHECK constraint.
 *
 * Neither the revocation nor this account is ever removed. Re-enabling appends.
 */
export async function reinstateAction(
  _prev: RevokeState,
  form: FormData,
): Promise<RevokeState> {
  const id = String(form.get("revocation_id") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  if (!reason) {
    return {
      error: "Re-enabling requires a written account of what was resolved.",
    };
  }
  const second = String(form.get("second_human") ?? "").trim();

  try {
    await api.post(`/api/revocations/${id}/reinstate`, {
      reason,
      second_human: second || null,
    });
    revalidatePath("/revocations");
    return {
      ok: "Re-enabled. The revocation stays in the record with both accounts attached.",
    };
  } catch (error) {
    return fail(error);
  }
}
