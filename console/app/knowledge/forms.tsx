"use client";

import { useFormState, useFormStatus } from "react-dom";

import { Badge, Button, Field, inputClass } from "@/components/ui";

import {
  authorEntryAction,
  authorPersonaAction,
  authorPlaybookAction,
  recordNoteAction,
  shareAction,
  type KnowledgeActionState,
} from "./actions";

/**
 * Authoring forms for the knowledge bases.
 *
 * `useFormState` from `react-dom`, not `useActionState` — React 18.3.1, where the
 * latter type-checks, builds, and throws at render.
 */

function Submit({ label, busy }: { label: string; busy: string }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending}>
      {pending ? busy : label}
    </Button>
  );
}

function Result({ state }: { state: KnowledgeActionState | null }) {
  if (!state) return null;
  return (
    <p className="mt-2">
      <Badge severity={state.error ? "bad" : "ok"}>{state.error ?? state.ok}</Badge>
    </p>
  );
}

/**
 * Part 6.3's six fields, all on screen at once and none behind a disclosure.
 *
 * A form that collected framework and citation and tucked the behavioural implication
 * under "advanced" would produce entries that satisfy the constraint and teach an agent
 * nothing — the fields are listed in the spec in the order a lawyer thinks and rendered
 * here in the order an agent needs, with the two that change behaviour first among the
 * free-text ones.
 */
export function ComplianceEntryForm({ knownFlags }: { knownFlags: string[] }) {
  const [state, action] = useFormState(authorEntryAction, null);
  return (
    <form action={action} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Entry ref" hint="What a Pack's library_entry_ref resolves against.">
          <input className={inputClass} name="entry_ref" placeholder="compliance/ftc-tsr-v2" />
        </Field>
        <Field label="Framework">
          <input className={inputClass} name="framework" placeholder="FTC_TSR" />
        </Field>
        <Field label="Jurisdiction" hint="Comma-separated. FEDERAL, or state codes.">
          <input className={inputClass} name="jurisdiction" placeholder="FEDERAL" />
        </Field>
        <Field
          label="Runtime flag"
          hint={
            knownFlags.length > 0
              ? `Flags in use with no entry: ${knownFlags.join(", ")}`
              : "Every flag in use is already explained."
          }
        >
          <input className={inputClass} name="runtime_flag" placeholder="tsr_disclosure_required" />
        </Field>
      </div>

      <Field label="Applicability rule" hint="When this applies, in terms an agent can evaluate.">
        <textarea className={inputClass} name="applicability_rule" rows={2} />
      </Field>
      <Field
        label="Agent-behaviour implication"
        hint="What the agent must do differently. An entry without this is a legal reference nobody can act on."
      >
        <textarea className={inputClass} name="agent_behavior_implication" rows={3} />
      </Field>
      <Field
        label="Escalation trigger"
        hint="What sends this to a human. Without it, the entry says what to notice and not what to do about it."
      >
        <textarea className={inputClass} name="escalation_trigger" rows={2} />
      </Field>
      <Field label="Citation">
        <input className={inputClass} name="citation" placeholder="16 CFR 310" />
      </Field>

      <Submit label="Write entry" busy="Writing…" />
      <Result state={state} />
    </form>
  );
}

export function PlaybookForm({ ventures }: { ventures: string[] }) {
  const [state, action] = useFormState(authorPlaybookAction, null);
  return (
    <form action={action} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Venture">
          <select className={inputClass} name="venture_id" defaultValue="">
            <option value="" disabled>
              Choose a venture
            </option>
            {ventures.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Title">
          <input className={inputClass} name="title" placeholder="Cold call opener" />
        </Field>
        <Field label="Version" hint="Supersedes the live version of this title.">
          <input className={inputClass} name="playbook_version" placeholder="1.0.0" />
        </Field>
        <Field label="Lifecycle stage" hint="Optional. Drives stage coverage at Gate 6.">
          <input className={inputClass} name="lifecycle_stage" placeholder="Source" />
        </Field>
      </div>
      <Field label="Content" hint="JSON.">
        <textarea
          className={`${inputClass} font-mono`}
          name="content"
          rows={6}
          spellCheck={false}
          defaultValue={'{\n  "steps": []\n}'}
        />
      </Field>
      <Submit label="Publish playbook" busy="Publishing…" />
      <Result state={state} />
    </form>
  );
}

/**
 * The opt-in itself.
 *
 * A reason is required, and the button that withdraws is a separate submit value rather
 * than a checkbox — withdrawing consent should not be one mis-click away from granting
 * it, and it should not be possible to do both in one action.
 */
export function ShareForm({
  playbooks,
  ventures,
}: {
  playbooks: { playbook_id: string; title: string; venture_id: string }[];
  ventures: string[];
}) {
  const [state, action] = useFormState(shareAction, null);
  return (
    <form action={action} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Playbook">
          <select className={inputClass} name="playbook_id" defaultValue="">
            <option value="" disabled>
              Choose a playbook
            </option>
            {playbooks.map((p) => (
              <option key={p.playbook_id} value={p.playbook_id}>
                {p.venture_id} · {p.title}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Share with">
          <select className={inputClass} name="to_venture_id" defaultValue="">
            <option value="" disabled>
              Choose a venture
            </option>
            {ventures.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field
        label="Reason"
        hint="Required to share. Kept after withdrawal, so the record of the decision survives."
      >
        <input className={inputClass} name="reason" />
      </Field>
      <div className="flex gap-3">
        <Button type="submit" name="intent" value="share">
          Share
        </Button>
        <Button type="submit" name="intent" value="revoke" variant="danger">
          Withdraw
        </Button>
      </div>
      <Result state={state} />
    </form>
  );
}

/**
 * Persona authoring, which is one-way.
 *
 * The form says so before you use it rather than after. `office_app` holds no SELECT on
 * `persona_body`, so this console cannot render back what it just wrote — that is Part
 * 6.4 enforced by a column privilege, and a form that quietly could not show its own
 * result would read like a defect.
 */
export function PersonaForm({ ventures }: { ventures: string[] }) {
  const [state, action] = useFormState(authorPersonaAction, null);
  return (
    <form action={action} className="space-y-3">
      <p className="rounded border border-warn/40 bg-warn/10 p-2 text-xs text-warn">
        One-way. SimForge only, never production — the runtime role this console uses
        holds no read privilege on a persona body, so what you write here cannot be
        displayed again. Reviewing one is an out-of-band act on the admin connection.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Venture">
          <select className={inputClass} name="venture_id" defaultValue="">
            <option value="" disabled>
              Choose a venture
            </option>
            {ventures.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Persona name">
          <input className={inputClass} name="persona_name" placeholder="Stalled broker" />
        </Field>
        <Field
          label="Target persona"
          hint="Which of the Pack's market.target_personas this stands in for."
        >
          <input className={inputClass} name="target_persona" />
        </Field>
        <Field label="Version">
          <input className={inputClass} name="persona_version" defaultValue="1.0.0" />
        </Field>
      </div>
      <Field label="Body" hint="JSON. Written once, never read back here.">
        <textarea
          className={`${inputClass} font-mono`}
          name="persona_body"
          rows={6}
          spellCheck={false}
          defaultValue={'{\n  "disposition": "",\n  "objections": []\n}'}
        />
      </Field>
      <Submit label="Write persona" busy="Writing…" />
      <Result state={state} />
    </form>
  );
}

export function NoteForm({ ventures }: { ventures: string[] }) {
  const [state, action] = useFormState(recordNoteAction, null);
  return (
    <form action={action} className="space-y-3">
      <Field label="Venture" hint="Leave blank for a portfolio-wide fact.">
        <select className={inputClass} name="venture_id" defaultValue="">
          <option value="">Portfolio-wide</option>
          {ventures.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Summary" hint="Append-only. This cannot be edited or deleted afterwards.">
        <textarea className={inputClass} name="summary" rows={3} />
      </Field>
      <Submit label="Record" busy="Recording…" />
      <Result state={state} />
    </form>
  );
}
