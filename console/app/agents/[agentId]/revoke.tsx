"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { revokeAction, type RosterState } from "../actions";

/**
 * Revocation, from the page where somebody decides to do it.
 *
 * This is the kill switch under the brokered model: the Forge logs attribute every call
 * to the tenant, so pulling a grant is the only way to stop a specific agent reaching a
 * specific Forge. It was absent from the agent's own page entirely.
 *
 * A reason is required and recorded against the operator's name. A revocation nobody can
 * explain afterwards is indistinguishable from a mistake.
 */
export function Revoke({
  officeAgentId,
  grantId,
  scope,
  label,
}: {
  officeAgentId: string;
  grantId?: string;
  scope: "grant" | "agent";
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const [state, action] = useFormState<RosterState | null, FormData>(revokeAction, null);
  const { pending } = useFormStatus();

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg border border-bad-line px-2.5 py-1 text-meta font-medium text-bad transition hover:bg-bad-bg"
      >
        {label}
      </button>
    );
  }

  return (
    <form action={action} className="w-full max-w-md space-y-2">
      <input type="hidden" name="office_agent_id" value={officeAgentId} />
      {grantId ? <input type="hidden" name="grant_id" value={grantId} /> : null}
      <input type="hidden" name="scope" value={scope} />
      <label className="block text-meta text-ink-secondary">
        Why
        <input
          name="reason"
          required
          placeholder="Recorded against your name in the append-only log."
          className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
        />
      </label>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-lg bg-bad px-3 py-1.5 text-desc font-medium text-ink-inverse transition hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "Revoking…" : label}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-meta text-ink-muted underline underline-offset-2"
        >
          Cancel
        </button>
      </div>
      {state?.error || state?.ok ? (
        <p className={`text-meta ${state.error ? "text-bad" : "text-ok"}`}>
          {state.error ?? state.ok}
        </p>
      ) : null}
    </form>
  );
}
