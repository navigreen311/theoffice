"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { Badge, Button, inputClass } from "@/components/ui";

import { reinstateAction } from "./actions";
import { Picker, type Option } from "./picker";

/**
 * The re-enable ritual.
 *
 * §1.4 asks for a documented ritual and a named human, and neither existed on screen:
 * lifting a revocation meant getting its id out of the database by hand. The account is
 * required, the person is whoever is signed in, and at venture and Forge scope a second
 * named human is required too — one person's judgement created a stop that reaches an
 * engagement or the whole portfolio, and one person's judgement is not enough to end it.
 *
 * Re-enabling does not remove the revocation. Both accounts stay attached to it for ever,
 * because a history that reads cleaner than what happened is worse than no history.
 */

function Submit() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending}>
      {pending ? "Re-enabling…" : "Re-enable"}
    </Button>
  );
}

export function ReinstateForm({
  revocationId,
  scope,
  targetName,
  humans,
}: {
  revocationId: string;
  scope: string;
  targetName: string;
  humans: Option[];
}) {
  const [state, action] = useFormState(reinstateAction, null);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [second, setSecond] = useState("");

  const needsSecond = scope === "venture" || scope === "forge";
  const ready = reason.trim().length > 0 && (!needsSecond || second !== "");

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
      >
        Re-enable…
      </button>
    );
  }

  return (
    <form action={action} className="mt-2 w-full space-y-3 rounded-lg border border-line bg-surface-muted px-3 py-3">
      <input type="hidden" name="revocation_id" value={revocationId} />
      <input type="hidden" name="second_human" value={needsSecond ? second : ""} />

      <p className="text-meta text-ink-secondary">
        Re-enabling {targetName} restores what this stopped. The revocation stays in the
        record — this appends an account, it does not remove one.
      </p>

      <label className="block text-meta text-ink-muted">
        What was resolved
        <textarea
          name="reason"
          rows={2}
          required
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          className={inputClass}
        />
      </label>

      {needsSecond ? (
        <Picker
          label="Second named human (required at this scope)"
          options={humans}
          value={second}
          onChange={setSecond}
        />
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        {ready ? (
          <Submit />
        ) : (
          <Button type="button" disabled>
            Re-enable
          </Button>
        )}
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-meta text-ink-muted underline underline-offset-2"
        >
          Cancel
        </button>
        {needsSecond && second === "" ? (
          <span className="text-meta text-ink-muted">
            A {scope} stop takes two people to lift.
          </span>
        ) : null}
      </div>

      {state?.error ? <Badge severity="bad">{state.error}</Badge> : null}
      {state?.ok ? <Badge severity="ok">{state.ok}</Badge> : null}
    </form>
  );
}
