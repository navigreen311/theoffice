"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api } from "@/lib/api";

/**
 * Decide a proposal.
 *
 * A rejection requires a reason. "No" without one returns nothing actionable to the
 * agent, which turns a trust tier into a coin flip the agent cannot learn from - and the
 * whole point of `propose` is that a human's judgment reaches the work.
 *
 * The review timer is not enforced here. The API computes `review_seconds` from
 * `created_at` in the database precisely so a client cannot report a review time it did
 * not take, and re-implementing the check in the console would just be a second opinion
 * that eventually disagrees.
 */
export type DecisionState = { error?: string; ok?: string };

export async function decideAction(
  _prev: DecisionState | null,
  form: FormData,
): Promise<DecisionState> {
  const proposalId = String(form.get("proposal_id") ?? "");
  // Approve and deny are separate forms with separate buttons, so the decision arrives
  // as its own field rather than as the identity of whichever button was pressed.
  const approve = String(form.get("approve") ?? "") === "true";
  const reason = String(form.get("reason") ?? "").trim();

  if (!approve && !reason) {
    return { error: "A rejection needs a reason - the agent has to learn something." };
  }

  try {
    const result = await api.post<{ status: string }>(
      `/api/proposals/${proposalId}/decide`,
      { approve, reason: reason || null },
    );
    revalidatePath("/proposals");
    return { ok: `Recorded: ${result.status}.` };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}
