"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api } from "@/lib/api";

/**
 * The routed human's two acts.
 *
 * **Neither carries an actor.** Ruled 21 September 2026 (decisions entry 150): the actor
 * comes from the token on the route, never from an argument. The first build of
 * `record_receipt` took a uuid and checked nothing, so any caller could record any
 * person - including the one that raised the escalation - as having received it.
 *
 * So these post nothing but the escalation id and, for an answer, the words. Who acted
 * is whoever the session belongs to, and the API refuses anybody but the routed human.
 */
export type EscalationState = { error?: string; ok?: string };

export async function receiveAction(
  _prev: EscalationState | null,
  form: FormData,
): Promise<EscalationState> {
  const escalationId = String(form.get("escalation_id") ?? "");
  try {
    await api.post<{ received_at: string }>(
      `/api/escalations/${escalationId}/receive`,
      {},
    );
    revalidatePath("/escalations");
    return { ok: "Receipt recorded. It is yours to answer." };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}

export async function answerAction(
  _prev: EscalationState | null,
  form: FormData,
): Promise<EscalationState> {
  const escalationId = String(form.get("escalation_id") ?? "");
  const answer = String(form.get("answer") ?? "").trim();

  // An answer is a sentence, not a flag - the same rule the API and a CHECK both apply.
  // Refused here as well so somebody typing gets told before the round trip, and not
  // INSTEAD of there: a client-side check is a courtesy and never a control.
  if (!answer) {
    return { error: "An escalation is answered with a sentence, not a button." };
  }

  try {
    await api.post<{ answered_at: string }>(
      `/api/escalations/${escalationId}/answer`,
      { answer },
    );
    revalidatePath("/escalations");
    return { ok: "Answered. The path has now been travelled end to end." };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}
