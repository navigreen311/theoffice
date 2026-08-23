"use client";

import { useFormState, useFormStatus } from "react-dom";

import { Badge, Button, Card, Field, inputClass } from "@/components/ui";

import { revokeAction } from "./actions";

/**
 * `useFormState` / `useFormStatus` from react-dom, not `useActionState` from react.
 *
 * `useActionState` is React 19. This project pins React 18.3.1 per the blueprint stack,
 * and the 18.x equivalent lives in react-dom. Worth a comment because **both `tsc
 * --noEmit` and `next build` passed with the React 19 hook** — the types resolved, the
 * bundle compiled, and the page threw `useActionState is not a function` only when a
 * real request rendered it.
 *
 * A green build is not proof the app runs.
 */

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="danger" disabled={pending}>
      {pending ? "Revoking…" : "Revoke"}
    </Button>
  );
}

export function RevokeForm() {
  const [state, action] = useFormState(revokeAction, null);

  return (
    <Card title="Issue a revocation">
      <form action={action} className="space-y-3">
        <Field label="Scope">
          <select name="scope" className={inputClass} defaultValue="agent_module">
            <option value="agent_module">agent_module — one grant</option>
            <option value="agent">agent — no Forge at all</option>
            <option value="venture">venture — the whole engagement</option>
            <option value="forge">forge — every agent, this Forge</option>
          </select>
        </Field>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Agent id" hint="agent_module, agent">
            <input className={inputClass} name="office_agent_id" />
          </Field>
          <Field label="Forge id" hint="agent_module, forge">
            <input className={inputClass} name="forge_id" />
          </Field>
          <Field label="Module id" hint="agent_module">
            <input className={inputClass} name="module_id" />
          </Field>
          <Field label="Venture id" hint="venture">
            <input className={inputClass} name="venture_id" />
          </Field>
        </div>

        <Field
          label="Reason"
          hint="Required. Stored on the revocation and surfaced in regulator exports."
        >
          <textarea className={inputClass} name="reason" rows={2} required />
        </Field>

        <SubmitButton />

        {state?.error ? (
          <p className="pt-2">
            <Badge severity="bad">{state.error}</Badge>
          </p>
        ) : null}
        {state?.ok ? (
          <p className="pt-2">
            <Badge severity="ok">{state.ok}</Badge>
          </p>
        ) : null}
      </form>
    </Card>
  );
}
