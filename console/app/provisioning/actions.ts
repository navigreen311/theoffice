"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, type HistoryRun } from "@/lib/api";

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

    // Two submits, one form. Recording and advancing is what almost everybody wants;
    // recording alone is the real second case, for a reviewer who is not the person who
    // will advance. Splitting them across two cards left the relationship between them
    // to be discovered by trying.
    if (String(form.get("then") ?? "") !== "advance") {
      revalidatePath(`/provisioning/${venture}`);
      return { ok: "Review recorded. The run stays at gate 4." };
    }

    const result = await api.post<{
      status: string;
      current_gate: string;
      outcomes: { gate: string; verdict: string; reason: string }[];
    }>(`/api/provisioning/runs/${runId}/advance`, {});
    revalidatePath(`/provisioning/${venture}`);
    revalidatePath("/provisioning");

    const last = result.outcomes[result.outcomes.length - 1];
    if (!last) {
      return { ok: `Review recorded. No gate ran; the run is ${result.status}.` };
    }
    if (last.verdict === "passed") {
      return {
        ok: `Review recorded. ${result.outcomes.length} gate(s) ran, now at gate ${result.current_gate}.`,
      };
    }
    return {
      ok: `Review recorded. Stopped at gate ${last.gate} — ${last.reason}`,
    };
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


/* ------------------------------------------------- actions for the index page */

/**
 * Resume a run from the gate it stopped at.
 *
 * The same call as advancing — `advance_run` starts from `current_gate`, so resuming is
 * not a separate mechanism and cannot drift from one. What differs is the wording: an
 * operator looking at a run that stopped three days ago is asking to continue it, not
 * to step it forward.
 *
 * Not offered when the Pack changed underneath the run. That check lives on the server
 * and the button is hidden here; both, because a hidden button is a courtesy and the
 * server check is the control.
 */
export async function resumeRunAction(
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
    revalidatePath("/provisioning");
    revalidatePath(`/provisioning/${venture}`);

    const last = result.outcomes[result.outcomes.length - 1];
    if (!last) {
      return { ok: `No gate ran. The run is still ${result.status} at gate ${result.current_gate}.` };
    }
    if (last.verdict === "passed") {
      return { ok: `${result.outcomes.length} gate(s) ran. Now at gate ${result.current_gate}.` };
    }
    return {
      ok: `${result.outcomes.length} gate(s) ran. Stopped at gate ${last.gate} — ${last.reason}`,
    };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Start a fresh run from gate 0.
 *
 * A re-run is a new run, not a reset of the old one. The old run keeps its record —
 * which gate stopped it and why is the institutional memory the next attempt is built
 * on, and a page that only ever showed the latest attempt would throw it away.
 */
export async function rerunAction(
  _prev: RunActionState | null,
  form: FormData,
): Promise<RunActionState> {
  const venture = String(form.get("venture_id") ?? "");
  try {
    const result = await api.post<{ run_id: string; current_gate: string }>(
      "/api/provisioning/runs",
      { venture_id: venture },
    );
    revalidatePath("/provisioning");
    revalidatePath(`/provisioning/${venture}`);
    return {
      ok: `Run ${result.run_id.slice(0, 8)} started at gate 0. The previous run keeps its record.`,
    };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Decline at a gate awaiting a human decision.
 *
 * Distinct from abandoning the run, and the console has to keep them distinct because
 * the statuses mean different things to whoever provisions this venture next: a
 * cancelled run says nothing about the artifacts, a rejected one is a judgement of them.
 *
 * This is the only human decision here that stops a run. There is deliberately no
 * counterpart that passes a gate the system blocked.
 */
export async function rejectRunAction(
  _prev: RunActionState | null,
  form: FormData,
): Promise<RunActionState> {
  const runId = String(form.get("run_id") ?? "");
  const venture = String(form.get("venture_id") ?? "");
  const note = String(form.get("note") ?? "").trim();

  if (!note) {
    return {
      error:
        "Rejecting needs a reason. It is a judgement about the artifacts, and the next person to provision this venture reads it.",
    };
  }

  try {
    await api.post(`/api/provisioning/runs/${runId}/reject`, { note });
    revalidatePath("/provisioning");
    revalidatePath(`/provisioning/${venture}`);
    return {
      ok: "Rejected. Grants are unchanged — rejecting is not revoking.",
    };
  } catch (error) {
    return fail(error);
  }
}

/** Every run for a venture. Read on the server; the page holds no history until asked. */
export async function ventureHistory(ventureId: string): Promise<HistoryRun[]> {
  const result = await api.get<{ runs: HistoryRun[] }>(
    `/api/provisioning/history/${encodeURIComponent(ventureId)}`,
  );
  return result.runs;
}
