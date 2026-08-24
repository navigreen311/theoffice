"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { Ago } from "@/components/local-time";
import { History, PlayerPlay, Refresh, X } from "@/components/icons";
import type { HistoryRun, ProvisioningCard } from "@/lib/api";
import { relativeAge } from "@/lib/severity";

import {
  rejectRunAction,
  rerunAction,
  resumeRunAction,
  startRunAction,
  ventureHistory,
  type RunActionState,
} from "./actions";

/**
 * The controls of the Provisioning index.
 *
 * There was no action on this page at all: you could read how far a venture got and
 * then had to go somewhere else to do anything about it.
 *
 * What is deliberately absent is any way past a gate. No force, no skip, no admin
 * bypass — the ceiling notice states there is no override, and a UI that offered one
 * would make that copy a lie. The only human decision here that changes a run's fate is
 * *rejecting* it, which stops a run rather than advancing one.
 */

function Submit({
  label,
  busy,
  icon,
  tone = "quiet",
}: {
  label: string;
  busy: string;
  icon?: React.ReactNode;
  tone?: "primary" | "quiet" | "danger";
}) {
  const { pending } = useFormStatus();
  const styles =
    tone === "primary"
      ? "bg-surface-inverse text-ink-inverse hover:opacity-90"
      : tone === "danger"
        ? "border border-bad-line text-bad hover:bg-bad-bg"
        : "border border-line text-ink hover:bg-surface-muted";
  return (
    <button
      type="submit"
      disabled={pending}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-desc font-medium transition disabled:opacity-50 ${styles}`}
    >
      {icon}
      {pending ? busy : label}
    </button>
  );
}

function Result({ state }: { state: RunActionState | null }) {
  if (!state?.error && !state?.ok) return null;
  return (
    <p className={`mt-2 text-meta ${state.error ? "text-bad" : "text-ok"}`}>
      {state.error ?? state.ok}
    </p>
  );
}

/**
 * Start a run, from a picker of ventures.
 *
 * A venture whose Pack fails validation is listed and disabled with the count inline,
 * never hidden. Hiding it answers "why can I not provision this venture" with silence,
 * which is the question the picker exists to answer.
 */
export function StartRun({
  candidates,
}: {
  candidates: {
    venture_id: string;
    display_name: string;
    blocked_reason: string | null;
  }[];
}) {
  const [open, setOpen] = useState(false);
  const [state, action] = useFormState<RunActionState | null, FormData>(
    startRunAction,
    null,
  );

  const startable = candidates.filter((c) => !c.blocked_reason);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-lg bg-surface-inverse px-3 py-1.5 text-desc font-medium text-ink-inverse transition hover:opacity-90"
      >
        <PlayerPlay className="h-4 w-4" />
        Start run
      </button>
    );
  }

  return (
    <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-ink">Start a run</h3>
          <p className="mt-0.5 text-meta text-ink-muted">
            From gate 0, against the venture&rsquo;s live Pack.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-meta text-ink-muted underline underline-offset-2"
        >
          Cancel
        </button>
      </div>

      <form action={action} className="mt-3 space-y-3">
        <div className="space-y-1.5">
          {candidates.map((candidate) => (
            <label
              key={candidate.venture_id}
              className={`flex items-start gap-2 rounded-lg border px-3 py-2 ${
                candidate.blocked_reason
                  ? "border-line bg-surface-muted"
                  : "border-line hover:bg-surface-muted"
              }`}
            >
              <input
                type="radio"
                name="venture_id"
                value={candidate.venture_id}
                disabled={Boolean(candidate.blocked_reason)}
                required
                className="mt-1"
              />
              <span className="min-w-0">
                <span
                  className={`block text-desc ${
                    candidate.blocked_reason ? "text-ink-muted" : "text-ink"
                  }`}
                >
                  {candidate.display_name}
                </span>
                {candidate.blocked_reason ? (
                  <span className="block text-meta text-bad">
                    {candidate.blocked_reason}
                  </span>
                ) : null}
              </span>
            </label>
          ))}
          {candidates.length === 0 ? (
            <p className="text-meta text-ink-muted">
              No venture has a Pack. Gate 1 refuses a run without one.
            </p>
          ) : null}
        </div>
        {startable.length ? (
          <Submit label="Start run" busy="Starting…" tone="primary" />
        ) : (
          <p className="text-meta text-ink-muted">
            Nothing here can start a run yet.
          </p>
        )}
      </form>
      <Result state={state} />
    </div>
  );
}

/** Continue from the gate the run stopped at. Not a separate mechanism — `advance`. */
export function Resume({ venture }: { venture: ProvisioningCard }) {
  const [state, action] = useFormState<RunActionState | null, FormData>(
    resumeRunAction,
    null,
  );
  if (!venture.run) return null;

  if (!venture.resumable) {
    return venture.resume_blocked_because ? (
      <p className="text-meta text-ink-muted">{venture.resume_blocked_because}</p>
    ) : null;
  }

  return (
    <form action={action}>
      <input type="hidden" name="run_id" value={venture.run.run_id} />
      <input type="hidden" name="venture_id" value={venture.venture_id} />
      <Submit
        label={`Resume from gate ${venture.run.current_gate}`}
        busy="Resuming…"
        icon={<PlayerPlay className="h-3.5 w-3.5" />}
      />
      <Result state={state} />
    </form>
  );
}

/** A fresh run from gate 0. The previous run keeps its record. */
export function Rerun({ ventureId }: { ventureId: string }) {
  const [state, action] = useFormState<RunActionState | null, FormData>(
    rerunAction,
    null,
  );
  return (
    <form action={action}>
      <input type="hidden" name="venture_id" value={ventureId} />
      <Submit label="Re-run" busy="Starting…" icon={<Refresh className="h-3.5 w-3.5" />} />
      <Result state={state} />
    </form>
  );
}

/**
 * Decline at a gate awaiting a decision.
 *
 * Only rendered when a gate is actually waiting on a human. A reject button on a run
 * nothing has put to a human would be a way to stop a run mid-flight while dressing it
 * as a review — and abandoning a run is a different act, on the run's own page.
 */
export function Reject({ venture }: { venture: ProvisioningCard }) {
  const [open, setOpen] = useState(false);
  const [state, action] = useFormState<RunActionState | null, FormData>(
    rejectRunAction,
    null,
  );
  if (!venture.run || venture.run.status !== "awaiting_human") return null;

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-lg border border-bad-line px-3 py-1.5 text-desc font-medium text-bad transition hover:bg-bad-bg"
      >
        <X className="h-3.5 w-3.5" />
        Reject
      </button>
    );
  }

  return (
    <form action={action} className="w-full max-w-md space-y-2">
      <input type="hidden" name="run_id" value={venture.run.run_id} />
      <input type="hidden" name="venture_id" value={venture.venture_id} />
      <label className="block text-meta text-ink-secondary">
        Why these artifacts are being declined
        <textarea
          name="note"
          rows={2}
          required
          className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
          placeholder="Read by whoever provisions this venture next."
        />
      </label>
      <div className="flex items-center gap-2">
        <Submit label="Reject run" busy="Rejecting…" tone="danger" />
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-meta text-ink-muted underline underline-offset-2"
        >
          Cancel
        </button>
      </div>
      <Result state={state} />
    </form>
  );
}

/**
 * Every prior run for this venture.
 *
 * Fetched on demand rather than with the page: history is worth having and not worth
 * loading for every venture on every render. Provisioning is iterative — the same gate
 * failing four times is a different problem from four gates failing once, and only the
 * list shows that.
 */
export function RunHistory({
  ventureId,
  total,
}: {
  ventureId: string;
  total: number;
}) {
  const [runs, setRuns] = useState<HistoryRun[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (total === 0) return null;

  if (runs === null) {
    return (
      <div>
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setError(null);
            ventureHistory(ventureId)
              .then(setRuns)
              .catch(() => setError("Could not load history."))
              .finally(() => setBusy(false));
          }}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted disabled:opacity-50"
        >
          <History className="h-3.5 w-3.5" />
          {busy ? "Loading…" : `History (${total})`}
        </button>
        {error ? <p className="mt-2 text-meta text-bad">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="w-full">
      <div className="flex items-center justify-between gap-3">
        <span className="text-meta text-ink-muted">
          {runs.length} run{runs.length === 1 ? "" : "s"} for this venture
        </span>
        <button
          type="button"
          onClick={() => setRuns(null)}
          className="text-meta text-ink-muted underline underline-offset-2"
        >
          Hide
        </button>
      </div>
      <ul className="mt-2 space-y-2">
        {runs.map((run) => (
          <li key={run.run_id} className="border-t border-line pt-2">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
              <code className="text-ident text-ink-muted">
                {run.run_id.slice(0, 8)}
              </code>
              <span className="text-desc text-ink">{run.display_status}</span>
              <span className="text-meta text-ink-muted">
                {run.gates_passed} gate{run.gates_passed === 1 ? "" : "s"} cleared · Pack{" "}
                <span className="font-mono">{run.pack_version}</span> ·{" "}
                <Ago iso={run.started_at} />
                {run.actor ? ` · started by ${run.actor}` : ""}
              </span>
            </div>
            {run.reason ? (
              <p className="mt-0.5 text-meta text-ink-secondary">{run.reason}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
