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
  name,
  value,
}: {
  label: string;
  busy: string;
  variant?: "default" | "danger" | "quiet";
  /** So two submits in one form can say which one was pressed. */
  name?: string;
  value?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <Button
      type="submit"
      variant={variant}
      disabled={pending}
      name={name}
      value={value}
    >
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
      {/*
        Above the button and labelled. A green box under "Advance" reading "6 gate(s)
        ran. Stopped at gate 4" is unreadable as either a prediction of what pressing it
        will do or a record of what pressing it did.
      */}
      {state ? (
        <p className="mb-2 text-meta text-ink-muted">Last advance:</p>
      ) : null}
      <Result state={state} />
      <p className="mb-2 mt-2 text-desc text-ink-secondary">
        Runs from gate {currentGate} until a gate stops it. Gates are not skippable.
      </p>
      <Submit label={`Advance from gate ${currentGate}`} busy="Running gates…" />
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
/**
 * Gate 4, as two actions rather than two cards.
 *
 * "Record review" and "Advance from gate 4" sat in separate cards with no stated
 * relationship, so whether advancing needed the review first — and whether recording one
 * advanced by itself — was something an operator found out by trying. Recording and
 * advancing is what almost everybody wants; recording alone is the real second case,
 * for a reviewer who is not the person who will advance.
 *
 * The hint names what to write. "What did you review?" with no guidance produces
 * one-word entries, and a one-word entry in an append-only log is worthless as evidence
 * later — which is the only reason the log exists. Deliberately no minimum length: a
 * word count produces padding, not substance.
 */
export function ReviewForm({
  runId,
  venture,
  artifactsHash,
}: {
  runId: string;
  venture: string;
  artifactsHash?: string | null;
}) {
  const [state, action] = useFormState(reviewRunAction, null);
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="run_id" value={runId} />
      <input type="hidden" name="venture_id" value={venture} />
      <Field
        label="What did you review?"
        hint={
          "Required. Recorded against your name in the append-only log." +
          " Name what you actually checked — the appointment gaps, the bill of" +
          " materials, the capacity failure above." +
          (artifactsHash ? ` Bound to artifact hash ${artifactsHash.slice(0, 8)}…` : "")
        }
      >
        {/*
          INSTRUCTIONS, NOT AN EXAMPLE ANSWER. Ruled 22 September 2026, entry 155.

          The placeholder was a worked review - "all 3 positions filled by certified
          agents ... 192 approvals/day against 144 review-minutes" - and every number in
          it was invented. It described a venture with three positions and a V13 failure
          at a ratio no Pack here has ever had.

          Two things wrong with that, and the second is the serious one. It is grey text
          a reviewer can read as a summary of the run in front of them, and it is a
          template for the review they are about to write: the fastest honest-looking
          thing to do with a filled-in example is to agree with it. A placeholder that
          suggests a conclusion is a placeholder that collects one.

          So it prompts for the work instead, and names nothing it has not been given.
        */}
        <textarea
          className={inputClass}
          name="note"
          rows={3}
          placeholder={
            "Name what you checked and what you found. Say which of the counts above " +
            "you read, what the gap report told you, and why you are advancing or " +
            "stopping."
          }
        />
      </Field>
      <div className="flex flex-wrap items-center gap-2">
        <Submit label="Record review and advance" busy="Recording…" name="then" value="advance" />
        <Submit
          label="Record review only"
          busy="Recording…"
          variant="quiet"
          name="then"
          value="record"
        />
      </div>
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
        {/*
          `required` rather than a red error rendered at page load. "Abandoning a run
          needs a reason" showing before anybody has typed anything is a validation
          failure reported against a form nobody has submitted.
        */}
        <input className={inputClass} name="note" required />
      </Field>
      <Submit label="Abandon run" busy="Abandoning…" variant="danger" />
      <Result state={state} />
    </form>
  );
}
