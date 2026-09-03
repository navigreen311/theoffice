"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { Badge, Button, inputClass } from "@/components/ui";
import type { Taxonomy } from "@/lib/incidents";

import { appendAccountAction, raiseIncidentAction, type IncidentActionState } from "./actions";

/**
 * `useFormState` from react-dom, not `useActionState` from react.
 *
 * `useActionState` is React 19 and this project pins 18.3.1. Both `tsc --noEmit` and
 * `next build` pass with the React 19 hook; the page throws in the browser. That has
 * cost this project two reported outages, so it is written down at every call site.
 */

function Submit({ label, busy }: { label: string; busy: string }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending}>
      {pending ? busy : label}
    </Button>
  );
}

function Result({ state }: { state: IncidentActionState | null }) {
  if (!state) return null;
  return (
    <p className="mt-2">
      <Badge severity={state.error ? "bad" : "ok"}>{state.error ?? state.ok}</Badge>
    </p>
  );
}

/**
 * Filing an incident nobody's control caught.
 *
 * The blueprint names three detection sources — agent flag, external report, regulator
 * inquiry — and only the first arrives on its own. There was no way to record the other
 * two, so a regulator's question lived in somebody's inbox while this page showed an
 * empty list, and an empty list reads as calm.
 *
 * Only the kinds a person can file are offered. Letting somebody file
 * `audit_chain_broken` by hand would claim a check ran that did not, which is the same
 * class of untruth as counting a fixture as content.
 */
export function RaiseIncidentForm({
  taxonomy,
  ventures,
}: {
  taxonomy: Taxonomy;
  ventures: string[];
}) {
  const [state, action] = useFormState(raiseIncidentAction, null);
  const [summary, setSummary] = useState("");

  const filable = taxonomy.kinds.filter((kind) => kind.source === "human");

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <h2 className="text-section font-medium text-ink">Raise an incident</h2>
      <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
        For what the controls cannot see: an external report, or a regulator&rsquo;s
        question. Filed incidents carry your name and are marked as hand-filed, so one is
        never mistaken for something a check caught. Like every incident, it cannot be
        edited afterwards — the response is appended.
      </p>

      <form action={action} className="mt-3 space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-meta text-ink-muted">
            Detection source
            <select name="detection_source" className={inputClass} defaultValue="external_report">
              <option value="external_report">External report</option>
              <option value="regulator_inquiry">Regulator inquiry</option>
            </select>
          </label>

          <label className="text-meta text-ink-muted">
            Kind
            <select name="kind" className={inputClass} defaultValue="external_report">
              {filable.map((kind) => (
                <option key={kind.kind} value={kind.kind}>
                  {kind.label}
                </option>
              ))}
            </select>
          </label>

          <label className="text-meta text-ink-muted">
            Severity
            <select name="severity" className={inputClass} defaultValue="MEDIUM">
              {taxonomy.severities.map((severity) => (
                <option key={severity.value} value={severity.value}>
                  {severity.display} — respond within {severity.sla_hours}h
                </option>
              ))}
            </select>
          </label>

          <label className="text-meta text-ink-muted">
            Venture
            <select name="venture_id" className={inputClass} defaultValue="">
              <option value="">Not venture-specific</option>
              {ventures.map((venture) => (
                <option key={venture} value={venture}>
                  {venture}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="block text-meta text-ink-muted">
          What was reported
          <span className="block text-meta text-ink-muted">
            This becomes the detection, and the first entry in the response timeline. It
            cannot be edited later.
          </span>
          <textarea
            name="summary"
            rows={3}
            required
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            className={inputClass}
          />
        </label>

        <div className="flex flex-wrap items-center gap-3">
          <Submit label="Raise incident" busy="Raising…" />
          {summary.trim().length === 0 ? (
            <span className="text-meta text-ink-muted">
              A kind and a severity with nothing attached is a label, not a detection.
            </span>
          ) : null}
        </div>

        <Result state={state} />
      </form>
    </section>
  );
}

/**
 * Appending one account to an incident's response.
 *
 * The only write on the detail page. There is no edit and no delete here or in the
 * database — `incident_account` carries the same append-only trigger as the other
 * ledgers. A stage accounted for wrongly is corrected by appending a later account to
 * the same stage, so the timeline shows what was believed and when that changed.
 */
export function AppendAccountForm({
  incidentId,
  stages,
  defaultStage,
}: {
  incidentId: string;
  stages: { stage: string; label: string; hint: string }[];
  defaultStage: string;
}) {
  const [state, action] = useFormState(appendAccountAction, null);

  return (
    <form action={action} className="space-y-3">
      <input type="hidden" name="incident_id" value={incidentId} />

      <div className="grid gap-3 sm:grid-cols-[220px_1fr]">
        <label className="text-meta text-ink-muted">
          Stage
          <select name="stage" className={inputClass} defaultValue={defaultStage}>
            {stages.map((stage) => (
              <option key={stage.stage} value={stage.stage}>
                {stage.label}
              </option>
            ))}
          </select>
        </label>

        <label className="text-meta text-ink-muted">
          Account
          <textarea name="account" rows={3} required className={inputClass} />
        </label>
      </div>

      <Submit label="Append account" busy="Appending…" />
      <Result state={state} />
    </form>
  );
}
