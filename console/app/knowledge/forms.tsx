"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { assessSection } from "@/lib/curriculum";

import { Badge, Button, Field, inputClass } from "@/components/ui";

import {
  authorEntryAction,
  authorPersonaAction,
  authorPlaybookAction,
  recordExclusionAction,
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


/**
 * Writing a persona, with a step between the keyboard and the irreversible act.
 *
 * The copy already said the body can never be read back from this console - the runtime
 * role holds no read privilege on it. That is exactly what made an accidental submit
 * unrecoverable through the UI: no undo, and no way to look at what was written to work
 * out what to write instead.
 *
 * So: structured fields rather than a JSON scaffold, a confirmation restating what
 * cannot be undone, and the body hash afterwards - the one thing an author can keep to
 * verify against later, since the body itself is gone from their reach the moment it
 * lands.
 */
export function PersonaWrite({ ventures }: { ventures: string[] }) {
  const [state, action] = useFormState(authorPersonaAction, null);
  const [confirming, setConfirming] = useState(false);
  const [disposition, setDisposition] = useState("");
  const [objections, setObjections] = useState("");
  const [name, setName] = useState("");

  // The same emptiness test the curriculum authoring form applies. A persona whose
  // disposition is blank is the persona-library version of `"what_it_does":
  // "Documented."`, and this store has no read path to notice it later.
  const dispositionState = assessSection("what_it_does", disposition).state;
  const empty = dispositionState === "missing" || dispositionState === "stub";

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <h2 className="text-section font-medium text-ink">Write a persona</h2>
      <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
        One-way. SimForge only, never production — the runtime role this console uses
        holds no read privilege on a persona body, so what you write here cannot be
        displayed again. Reviewing one is an out-of-band act on the admin connection.
      </p>

      <form action={action} className="mt-4 space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-meta text-ink-muted">
            Venture
            <select
              name="venture_id"
              defaultValue=""
              required
              className="mt-1 block w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
            >
              <option value="" disabled>
                Choose a venture
              </option>
              {ventures.map((venture) => (
                <option key={venture} value={venture}>
                  {venture}
                </option>
              ))}
            </select>
          </label>
          <label className="text-meta text-ink-muted">
            Persona name
            <input
              name="persona_name"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Stalled broker"
              className="mt-1 block w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
            />
          </label>
          <label className="text-meta text-ink-muted">
            Target persona
            <span className="block text-meta text-ink-muted">
              Which of the Pack&rsquo;s market.target_personas this stands in for.
            </span>
            <input
              name="target_persona"
              required
              className="mt-1 block w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
            />
          </label>
          <label className="text-meta text-ink-muted">
            Version
            <input
              name="persona_version"
              defaultValue="1.0.0"
              className="mt-1 block w-full rounded-lg border border-line bg-surface px-2 py-1.5 font-mono text-meta text-ink"
            />
          </label>
        </div>

        <label className="block text-meta text-ink-muted">
          Disposition
          <span className="block text-meta text-ink-muted">
            How this persona behaves in a scenario — what they want, what they resist.
          </span>
          <textarea
            name="disposition"
            rows={3}
            value={disposition}
            onChange={(event) => setDisposition(event.target.value)}
            className="mt-1 w-full rounded-lg border border-line bg-surface p-2 text-desc text-ink"
          />
        </label>

        <label className="block text-meta text-ink-muted">
          Objections
          <span className="block text-meta text-ink-muted">
            One per line. What this persona pushes back with.
          </span>
          <textarea
            name="objections"
            rows={3}
            value={objections}
            onChange={(event) => setObjections(event.target.value)}
            className="mt-1 w-full rounded-lg border border-line bg-surface p-2 text-desc text-ink"
          />
        </label>

        {confirming ? (
          <div className="rounded-lg border border-warn-line bg-warn-bg px-3 py-2">
            <p className="text-desc text-warn">
              {name || "This persona"} is about to be written once. You will not be able
              to read it back from this console, edit it, or check what it says — the
              role has no read privilege on the body. The hash below is what you will
              have to verify against.
            </p>
            <div className="mt-2 flex items-center gap-2">
              <Submit label="Write it" busy="Writing…" />
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="text-meta text-ink-muted underline underline-offset-2"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={empty}
              onClick={() => setConfirming(true)}
              className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted disabled:opacity-50"
            >
              Write persona…
            </button>
            {empty ? (
              <span className="text-meta text-bad">
                The disposition is empty or placeholder. A persona with nothing in it
                cannot be reviewed afterwards, because it cannot be read back.
              </span>
            ) : null}
          </div>
        )}

        <Result state={state} />
      </form>
    </section>
  );
}

/**
 * The control for a decision, not for a deletion.
 *
 * The brief asked for a purge. Neither store can be purged - `persona` is write-only to
 * this role and `historical_record` is append-only to everyone - and widening a grant to
 * put a Purge button on screen would undo a boundary that was drawn deliberately. What is
 * left is the half that was always the point: excluding these rows is a judgement, and a
 * judgement nobody wrote down is indistinguishable from a filter nobody noticed.
 */
export function RecordExclusion({ counts }: { counts: { personas: number; records: number } }) {
  const [state, action] = useFormState(recordExclusionAction, null);
  const total = counts.personas + counts.records;
  if (total === 0) return null;

  return (
    <form action={action} className="inline-flex flex-col">
      <Submit
        label={`Record this exclusion (${total})`}
        busy="Recording…"
      />
      <Result state={state} />
    </form>
  );
}
