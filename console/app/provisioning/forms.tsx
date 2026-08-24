"use client";

import { useFormState, useFormStatus } from "react-dom";

import { Badge, Button, Field, inputClass } from "@/components/ui";

import {
  abortRunAction,
  advanceRunAction,
  reviewRunAction,
  signOffRunAction,
  startRunAction,
  type RunActionState,
} from "./actions";

/**
 * The action forms of the Provisioning Console.
 *
 * Each is a separate form with a separate server action, deliberately. Advancing a run,
 * recording a review and signing off are three different acts with three different
 * consequences, and the one that ends in agents holding production authority should not
 * be one submit handler away from the one that records a note.
 *
 * `useFormState` from `react-dom`, not `useActionState` — this is React 18.3.1, where
 * the latter type-checks, builds, and throws at render.
 */

function Submit({
  label,
  busy,
  variant,
}: {
  label: string;
  busy: string;
  variant?: "default" | "danger";
}) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant={variant} disabled={pending}>
      {pending ? busy : label}
    </Button>
  );
}

function Result({ state }: { state: RunActionState | null }) {
  if (!state) return null;
  return (
    <p className="mt-2">
      <Badge severity={state.error ? "bad" : "ok"}>{state.error ?? state.ok}</Badge>
    </p>
  );
}

export function StartRunForm({ venture }: { venture: string }) {
  const [state, action] = useFormState(startRunAction, null);
  return (
    <form action={action}>
      <input type="hidden" name="venture_id" value={venture} />
      <Submit label="Start a run" busy="Starting…" />
      <Result state={state} />
    </form>
  );
}

export function AdvanceForm({
  runId,
  venture,
  currentGate,
}: {
  runId: string;
  venture: string;
  currentGate: string;
}) {
  const [state, action] = useFormState(advanceRunAction, null);
  return (
    <form action={action}>
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="venture_id" value={venture} />
      <p className="mb-2 text-xs text-ink-secondary">
        Runs from gate {currentGate} until a gate stops it. Gates are not skippable.
      </p>
      <Submit label={`Advance from gate ${currentGate}`} busy="Running gates…" />
      <Result state={state} />
    </form>
  );
}

/**
 * Gate 4.
 *
 * This is the approval queue's hazard again in a new place: a one-click "reviewed"
 * beside a collapsed artifact summary is a rubber stamp — authorised, audited, and
 * producing exactly the outcome the gate exists to prevent. So the caller renders the
 * unfilled positions, the capacity triple and the generator warnings expanded above
 * this form, and the note is required rather than optional.
 */
export function ReviewForm({ runId, venture }: { runId: string; venture: string }) {
  const [state, action] = useFormState(reviewRunAction, null);
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="venture_id" value={venture} />
      <Field
        label="What did you review?"
        hint="Required. Recorded against your name in the append-only log."
      >
        <textarea className={inputClass} name="note" rows={3} />
      </Field>
      <Submit label="Record review" busy="Recording…" />
      <Result state={state} />
    </form>
  );
}

export function SignOffForm({
  runId,
  venture,
  artifactsHash,
}: {
  runId: string;
  venture: string;
  artifactsHash: string | null;
}) {
  const [state, action] = useFormState(signOffRunAction, null);
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="venture_id" value={venture} />
      <input type="hidden" name="artifacts_hash" value={artifactsHash ?? ""} />
      <p className="text-xs text-ink-secondary">
        Signing binds your name to{" "}
        <span className="font-mono">{artifactsHash?.slice(0, 24) ?? "—"}…</span>. If the
        artifacts have changed since this page rendered, the signature is refused rather
        than re-pointed — you would be signing something you have not read.
      </p>
      <Field label="Note" hint="Optional. Stored with the signature.">
        <input className={inputClass} name="note" />
      </Field>
      <Submit label="Sign off Gate 10" busy="Signing…" />
      <Result state={state} />
    </form>
  );
}

export function AbortForm({ runId, venture }: { runId: string; venture: string }) {
  const [state, action] = useFormState(abortRunAction, null);
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="venture_id" value={venture} />
      <Field
        label="Reason"
        hint="Abandoning frees the venture for a new run. It does not revoke anything — grants keep whatever state they are in."
      >
        <input className={inputClass} name="note" />
      </Field>
      <Submit label="Abandon run" busy="Abandoning…" variant="danger" />
      <Result state={state} />
    </form>
  );
}
