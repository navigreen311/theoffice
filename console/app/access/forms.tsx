"use client";

import { useFormState, useFormStatus } from "react-dom";

import { Badge, Button, Field, inputClass } from "@/components/ui";

import {
  createHumanAction,
  reinstateAction,
  reissueTokenAction,
  resolveIncidentAction,
  setRoleAction,
  setStatusAction,
  type AccessState,
} from "./actions";

const ROLES = ["venture_operator", "compliance_officer", "ivan"] as const;

function Submit({
  label,
  busy,
  variant,
  name,
  value,
}: {
  label: string;
  busy: string;
  variant?: "default" | "danger";
  name?: string;
  value?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" name={name} value={value} variant={variant} disabled={pending}>
      {pending ? busy : label}
    </Button>
  );
}

/**
 * A result, and — when there is one — a token.
 *
 * The token is rendered once and is not recoverable. It is deliberately not put in a
 * copy-to-clipboard control that could fail silently, and deliberately not truncated:
 * an operator who half-copies a credential finds out at the login screen.
 */
function Result({ state }: { state: AccessState | null }) {
  if (!state) return null;
  return (
    <div className="mt-2 space-y-2">
      <p>
        <Badge severity={state.error ? "bad" : "ok"}>{state.error ?? state.ok}</Badge>
      </p>
      {state.token ? (
        <div className="rounded border border-warn/40 bg-warn/10 p-3">
          <p className="text-xs font-medium text-warn">
            Shown once. There is no route that can produce it again.
          </p>
          <code className="mt-1 block break-all font-mono text-xs text-ink">
            {state.token}
          </code>
        </div>
      ) : null}
    </div>
  );
}

export function CreateHumanForm({ ventures }: { ventures: string[] }) {
  const [state, action] = useFormState(createHumanAction, null);
  return (
    <form action={action} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <input className={inputClass} name="display_name" />
        </Field>
        <Field label="Email">
          <input className={inputClass} name="email" type="email" />
        </Field>
        <Field
          label="Initial role"
          hint="Optional. You can only grant a role weaker than your own."
        >
          <select className={inputClass} name="role" defaultValue="">
            <option value="">none</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Venture" hint="Blank means every venture — what ivan holds.">
          <select className={inputClass} name="venture_id" defaultValue="">
            <option value="">all ventures</option>
            {ventures.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Submit label="Create" busy="Creating…" />
      <Result state={state} />
    </form>
  );
}

/**
 * Grant or remove one role.
 *
 * Grant and remove are separate submit values rather than a checkbox: taking somebody's
 * authority away should not be one mis-click from giving it, and it should not be
 * possible to do both in one action.
 */
export function RoleForm({
  humans,
  ventures,
}: {
  humans: { human_id: string; display_name: string }[];
  ventures: string[];
}) {
  const [state, action] = useFormState(setRoleAction, null);
  return (
    <form action={action} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Person">
          <select className={inputClass} name="human_id" defaultValue="">
            <option value="" disabled>
              Choose
            </option>
            {humans.map((h) => (
              <option key={h.human_id} value={h.human_id}>
                {h.display_name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Role">
          <select className={inputClass} name="role" defaultValue={ROLES[0]}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Venture" hint="Blank = every venture.">
          <select className={inputClass} name="venture_id" defaultValue="">
            <option value="">all ventures</option>
            {ventures.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <p className="text-xs text-ink-secondary">
        You may grant a role weaker than your own, and never to yourself — so that every
        role anybody holds was granted by somebody else, and the log says who.
      </p>
      <div className="flex gap-3">
        <Button type="submit" name="intent" value="grant">
          Grant
        </Button>
        <Button type="submit" name="intent" value="revoke" variant="danger">
          Remove
        </Button>
      </div>
      <Result state={state} />
    </form>
  );
}

export function StatusForm({
  humanId,
  status,
}: {
  humanId: string;
  status: string;
}) {
  const [state, action] = useFormState(setStatusAction, null);
  const suspending = status === "active";
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="human_id" value={humanId} />
      <input
        type="hidden"
        name="intent"
        value={suspending ? "suspended" : "active"}
      />
      <Field label="Reason" hint="Recorded against your name.">
        <input className={inputClass} name="reason" />
      </Field>
      <Submit
        label={suspending ? "Suspend" : "Reactivate"}
        busy="Working…"
        variant={suspending ? "danger" : "default"}
      />
      <Result state={state} />
    </form>
  );
}

export function ReissueForm({ humanId, self }: { humanId: string; self: boolean }) {
  const [state, action] = useFormState(reissueTokenAction, null);
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="human_id" value={humanId} />
      {self ? (
        <p className="text-xs text-warn">
          This is you. Rotating invalidates the token this session is using — you will
          be signed out and will need the new one.
        </p>
      ) : null}
      <Submit label="Reissue token" busy="Reissuing…" variant="danger" />
      <Result state={state} />
    </form>
  );
}

export function ReinstateForm({ revocationId }: { revocationId: string }) {
  const [state, action] = useFormState(reinstateAction, null);
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="revocation_id" value={revocationId} />
      <Field label="Why is this being lifted?" hint="Required, and kept on the record.">
        <input className={inputClass} name="reason" />
      </Field>
      <Submit label="Reinstate" busy="Reinstating…" />
      <Result state={state} />
    </form>
  );
}

/**
 * Resolve an incident.
 *
 * The account of what was done is required and is the whole content of the act — the
 * incident keeps its severity, its kind and its detail, because a detection that can be
 * rewritten is worth less than the row it sits in.
 */
export function ResolveIncidentForm({ incidentId }: { incidentId: string }) {
  const [state, action] = useFormState(resolveIncidentAction, null);
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="incident_id" value={incidentId} />
      <Field
        label="What was done about it?"
        hint="Appended to the incident, not written over it. Also recorded as institutional history."
      >
        <textarea className={inputClass} name="resolution" rows={2} />
      </Field>
      <Submit label="Resolve" busy="Resolving…" />
      <Result state={state} />
    </form>
  );
}
