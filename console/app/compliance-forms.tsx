"use client";

import { useFormState, useFormStatus } from "react-dom";

import { FileExport } from "@/components/icons";

import {
  exportRecordAction,
  runControlsAction,
  type ControlState,
} from "./compliance-actions";

/**
 * The two things this page lets a reader do.
 *
 * Both are deliberately plain. This page is read when something has gone wrong or when
 * a regulator has asked, and a control that animates while it works reads as a product
 * rather than a record.
 */

function Result({ state }: { state: ControlState | null }) {
  if (!state) return null;
  return (
    <div className="mt-2 text-desc">
      <p className={state.error ? "text-bad" : "text-ok"}>
        {state.error ?? state.ok}
      </p>
      {state.detail ? <p className="mt-1 text-ink-secondary">{state.detail}</p> : null}
    </div>
  );
}

export function RunControlsButton({
  control,
  label,
  emphasis = false,
}: {
  control?: string;
  label: string;
  emphasis?: boolean;
}) {
  const [state, action] = useFormState(runControlsAction, null);
  return (
    <form action={action} className="inline-block">
      {control ? <input type="hidden" name="control" value={control} /> : null}
      <RunSubmit label={label} emphasis={emphasis} />
      <Result state={state} />
    </form>
  );
}

function RunSubmit({ label, emphasis }: { label: string; emphasis: boolean }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className={
        emphasis
          ? "rounded-lg bg-surface-inverse px-3 py-1.5 text-desc font-medium text-ink-inverse transition hover:opacity-90 disabled:opacity-50"
          : "rounded-lg border border-line px-3 py-1 text-meta font-medium text-ink-secondary transition hover:border-line-strong hover:text-ink disabled:opacity-50"
      }
    >
      {pending ? "Running…" : label}
    </button>
  );
}

/**
 * The scheduling answer, which is a statement rather than a control.
 *
 * There is no in-app scheduler, and a button that claimed to configure one would be a
 * lie on the page whose entire purpose is not lying about what has been checked. What
 * schedules these in a deployment is the `sweeps` container in `compose.yaml`; locally,
 * nothing does. That is the honest content of this action.
 */
export function SchedulingNote({ recentRuns }: { recentRuns: number }) {
  return (
    <details className="mt-1">
      <summary className="cursor-pointer text-desc font-medium text-bad underline underline-offset-2">
        Schedule automatic runs
      </summary>
      <div className="mt-2 space-y-1 text-desc text-ink-secondary">
        <p>
          There is no scheduler inside this application, and this control does not
          pretend to configure one.
        </p>
        <p>
          In a deployment the <code className="text-ident">sweeps</code> service in{" "}
          <code className="text-ident">compose.yaml</code> runs{" "}
          <code className="text-ident">python -m broker sweep</code> every{" "}
          <code className="text-ident">SWEEP_INTERVAL_SECONDS</code> — hourly by default.
          On a machine running the console alone, nothing runs them at all.
        </p>
        <p>
          {recentRuns === 0
            ? "No control has run here yet, which is consistent with nothing being scheduled."
            : `${recentRuns} run(s) recorded, so something is running them.`}
        </p>
      </div>
    </details>
  );
}

export function ExportForm({ ventures }: { ventures: string[] }) {
  const [state, action] = useFormState(exportRecordAction, null);
  return (
    <details className="rounded-xl border border-line bg-surface px-5 py-4">
      <summary className="flex cursor-pointer items-center gap-2 text-body font-medium text-ink">
        <FileExport size={18} className="text-ink-secondary" />
        Export compliance record
      </summary>

      <p className="mt-2 max-w-2xl text-desc text-ink-secondary">
        Part 9: structured record export on demand — CFPB, FTC, HHS OCR, state DFI. The
        document states its own control freshness on its face and lists what it did not
        include.
      </p>

      <form action={action} className="mt-3 space-y-3">
        <div className="grid gap-3 sm:grid-cols-4">
          <label className="block">
            <span className="block text-meta text-ink-secondary">Venture</span>
            <select
              name="venture_id"
              defaultValue=""
              className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
            >
              <option value="">all ventures</option>
              {ventures.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="block text-meta text-ink-secondary">Framework</span>
            <input
              name="framework"
              placeholder="all"
              className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
            />
          </label>
          <label className="block">
            <span className="block text-meta text-ink-secondary">Since</span>
            <input
              name="since"
              type="date"
              className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
            />
          </label>
          <label className="block">
            <span className="block text-meta text-ink-secondary">Until</span>
            <input
              name="until"
              type="date"
              className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
            />
          </label>
        </div>

        <ExportSubmit />
      </form>

      {state?.error ? (
        <p className="mt-2 text-desc text-bad">{state.error}</p>
      ) : null}

      {state?.document ? (
        <div className="mt-3 space-y-2">
          {/* The freshness statement, repeated outside the document so it cannot be
              scrolled past. An export produced while controls have never run says so on
              its face, and so does this page. */}
          <p className="rounded-lg border border-bad-line bg-bad-bg px-3 py-2 text-desc text-bad">
            {state.ok}
          </p>
          <p className="text-meta text-ink-muted">
            sha256 {state.hash} — hash-stamped, not signed. There is no key material in
            this deployment; a fabricated signature would prove nothing while appearing
            to prove provenance.
          </p>
          <pre className="max-h-96 overflow-auto rounded-lg border border-line bg-surface-muted p-3 text-ident text-ink-secondary">
            {state.document}
          </pre>
        </div>
      ) : null}
    </details>
  );
}

function ExportSubmit() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:border-line-strong disabled:opacity-50"
    >
      {pending ? "Producing…" : "Produce export"}
    </button>
  );
}
