"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api } from "@/lib/api";

export type RunActionState = { error?: string; ok?: string };

function fail(error: unknown): RunActionState {
  if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
  throw error;
}

/** Start a run against the venture's live Pack. */
export async function startRunAction(
  _prev: RunActionState | null,
  form: FormData,
): Promise<RunActionState> {
  const venture = String(form.get("venture_id") ?? "");
  try {
    const result = await api.post<{ run_id: string }>("/api/provisioning/runs", {
      venture_id: venture,
    });
    revalidatePath(`/provisioning/${venture}`);
    revalidatePath("/provisioning");
    return { ok: `Run ${result.run_id.slice(0, 8)} started at gate 0.` };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Advance a run.
 *
 * This is the only console action that can end with a grant becoming active, and it
 * cannot skip a gate to get there — the machine runs from the current gate and stops at
 * the first blocking one. Gate 11 refuses without a Gate 10 signature bound to the
 * current artifacts, and re-checks rather than trusting Gate 10's recorded verdict.
 */
export async function advanceRunAction(
  _prev: RunActionState | null,
  form: FormData,
): Promise<RunActionState> {
  const runId = String(form.get("run_id") ?? "");
  const venture = String(form.get("venture_id") ?? "");
  try {
    const result = await api.post<{
      status: string;
      current_gate: string;
      outcomes: { gate: string; verdict: string; reason: string }[];
    }>(`/api/provisioning/runs/${runId}/advance`, {});
    revalidatePath(`/provisioning/${venture}`);

    const last = result.outcomes[result.outcomes.length - 1];
    if (!last) return { ok: `No gate ran. The run is ${result.status}.` };
    return {
      ok: `${result.outcomes.length} gate(s) ran. Stopped at gate ${last.gate}: ${last.verdict} — ${last.reason}`,
    };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Gate 4 — record that a named human reviewed the artifacts.
 *
 * The note is required by the domain function. It is checked here too, because a round
 * trip that comes back "a Gate 4 review requires a note" after the operator has already
 * clicked is a worse way to learn the same thing.
 */
export async function reviewRunAction(
  _prev: RunActionState | null,
  form: FormData,
): Promise<RunActionState> {
  const runId = String(form.get("run_id") ?? "");
  const venture = String(form.get("venture_id") ?? "");
  const note = String(form.get("note") ?? "").trim();

  if (!note) {
    return {
      error:
        "A review needs a note saying what you looked at. Gate 4 exists so somebody read the bill of materials and the appointment gap report.",
    };
  }

  try {
    await api.post(`/api/provisioning/runs/${runId}/review`, { note });
    revalidatePath(`/provisioning/${venture}`);
    return { ok: "Review recorded. Advance the run to continue past Gate 4." };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Gate 10 — sign off, bound to the artifacts hash that was on screen.
 *
 * The hash is submitted from the rendered page rather than fetched at submit time, and
 * the API refuses if it no longer matches. A signature is a confirmation of what the
 * signer saw; signing whatever the server computes at click time would sign something
 * they never read.
 */
export async function signOffRunAction(
  _prev: RunActionState | null,
  form: FormData,
): Promise<RunActionState> {
  const runId = String(form.get("run_id") ?? "");
  const venture = String(form.get("venture_id") ?? "");
  const hash = String(form.get("artifacts_hash") ?? "");
  const note = String(form.get("note") ?? "").trim();

  if (!hash) {
    return {
      error:
        "No artifacts hash on this page. Advance the run so the artifacts are generated before signing.",
    };
  }

  try {
    const result = await api.post<{ artifacts_hash: string }>(
      `/api/provisioning/runs/${runId}/signoff`,
      { artifacts_hash: hash, note: note || null },
    );
    revalidatePath(`/provisioning/${venture}`);
    return {
      ok: `Signed against ${result.artifacts_hash.slice(0, 16)}…. Advance the run to activate grants.`,
    };
  } catch (error) {
    return fail(error);
  }
}

/** Abandon a run. Not a revocation — grants are deliberately untouched. */
export async function abortRunAction(
  _prev: RunActionState | null,
  form: FormData,
): Promise<RunActionState> {
  const runId = String(form.get("run_id") ?? "");
  const venture = String(form.get("venture_id") ?? "");
  const note = String(form.get("note") ?? "").trim();

  if (!note) return { error: "Abandoning a run needs a reason." };

  try {
    await api.post(`/api/provisioning/runs/${runId}/abort`, { note });
    revalidatePath(`/provisioning/${venture}`);
    revalidatePath("/provisioning");
    return { ok: "Run abandoned. Grants are unchanged — abandoning is not revoking." };
  } catch (error) {
    return fail(error);
  }
}
