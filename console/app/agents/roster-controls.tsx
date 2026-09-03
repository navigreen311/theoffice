"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { AlertTriangle, Plus, Refresh } from "@/components/icons";
import type { DepartmentOption, RosterAgent, RosterDepartment } from "@/lib/api";

import {

  importRosterAction,
  issueIdentitiesAction,
  previewRosterAction,
  registerAgentAction,
  type RosterState,
} from "./actions";

/**
 * Roster controls.
 *
 * There is no "add agent" here and there must not be. The page's own subtitle states the
 * model — the Village creates agents, The Office appoints them — and a control that
 * created one would contradict it and become a second source of truth for who exists.
 *
 * What these do instead: import what the Village reports, record an agent it cannot
 * report, and issue identities for agents that already exist.
 */

function Submit({
  label,
  busy,
  tone = "quiet",
}: {
  label: string;
  busy: string;
  tone?: "primary" | "quiet";
}) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-desc font-medium transition disabled:opacity-50 ${
        tone === "primary"
          ? "bg-surface-inverse text-ink-inverse hover:opacity-90"
          : "border border-line text-ink hover:bg-surface-muted"
      }`}
    >
      {pending ? busy : label}
    </button>
  );
}

function Result({ state }: { state: RosterState | null }) {
  if (!state?.error && !state?.ok) return null;
  return (
    <p className={`mt-2 text-desc ${state.error ? "text-bad" : "text-ok"}`}>
      {state.error ?? state.ok}
    </p>
  );
}

function Diff({ diff }: { diff: NonNullable<RosterState["diff"]> }) {
  return (
    <div className="mt-3 space-y-3 rounded-xl border border-line bg-surface-muted p-4">
      <p className="text-desc text-ink">
        {diff.incoming_total} agents in this roster · {diff.current_total} currently
        recorded · {diff.unchanged} unchanged
      </p>

      {diff.added.length ? (
        <section>
          <h4 className="text-meta text-ok">New to the roster ({diff.added.length})</h4>
          <p className="mt-1 text-meta text-ink-muted">
            Recorded as Village agents. They still need an Office identity before they
            can be appointed.
          </p>
          <ul className="mt-1 space-y-0.5">
            {diff.added.slice(0, 12).map((row) => (
              <li key={row.village_agent_ref} className="text-desc text-ink-secondary">
                {row.agent_name}{" "}
                <span className="text-ink-muted">· {row.department}</span>
              </li>
            ))}
            {diff.added.length > 12 ? (
              <li className="text-meta text-ink-muted">
                and {diff.added.length - 12} more
              </li>
            ) : null}
          </ul>
        </section>
      ) : null}

      {diff.departed.length ? (
        <section className="rounded-lg border border-bad-line bg-bad-bg px-3 py-2">
          <h4 className="flex items-center gap-1.5 text-meta text-bad">
            <AlertTriangle className="h-3.5 w-3.5" />
            Departed the Village ({diff.departed.length})
          </h4>
          <ul className="mt-1 space-y-0.5">
            {diff.departed.map((row) => (
              <li key={row.village_agent_ref} className="text-desc text-ink-secondary">
                {row.agent_name}
                {row.has_identity ? (
                  <span className="text-bad">
                    {" "}
                    — holds an Office identity
                    {row.live_grants
                      ? ` and ${row.live_grants} live grant${row.live_grants === 1 ? "" : "s"}. Revoke them.`
                      : ". Suspend the identity."}
                  </span>
                ) : (
                  <span className="text-ink-muted"> — no Office identity</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {diff.moved.length ? (
        <section>
          <h4 className="text-meta text-warn">
            Changed department ({diff.moved.length})
          </h4>
          <ul className="mt-1 space-y-0.5">
            {diff.moved.map((row) => (
              <li key={row.village_agent_ref} className="text-desc text-ink-secondary">
                {row.agent_name}: {row.from_department} → {row.to_department}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

export function RosterSync({ departments }: { departments: DepartmentOption[] }) {
  const [open, setOpen] = useState<"none" | "sync" | "register">("none");
  const [preview, doPreview] = useFormState<RosterState | null, FormData>(
    previewRosterAction,
    null,
  );
  const [applied, doImport] = useFormState<RosterState | null, FormData>(
    importRosterAction,
    null,
  );
  const [registered, doRegister] = useFormState<RosterState | null, FormData>(
    registerAgentAction,
    null,
  );

  if (open === "none") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setOpen("sync")}
          className="inline-flex items-center gap-1.5 rounded-lg bg-surface-inverse px-3 py-1.5 text-desc font-medium text-ink-inverse transition hover:opacity-90"
        >
          <Refresh className="h-4 w-4" />
          Sync from Village roster
        </button>
        <button
          type="button"
          onClick={() => setOpen("register")}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
        >
          <Plus className="h-4 w-4" />
          Register Village agent
        </button>
      </div>
    );
  }

  return (
    <div className="w-full rounded-2xl border border-line bg-surface p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-ink">
            {open === "sync" ? "Sync from Village roster" : "Register Village agent"}
          </h3>
          <p className="mt-0.5 max-w-2xl text-meta text-ink-muted">
            {open === "sync"
              ? "Paste the Village's roster as CSV (ref, name, department) or JSON. Nothing is written until you have seen what it would change."
              : "For an agent the Village has but the roster export cannot see. The Village's own reference is required — without it there is nothing for a later import to reconcile against."}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen("none")}
          className="text-meta text-ink-muted underline underline-offset-2"
        >
          Cancel
        </button>
      </div>

      {open === "sync" ? (
        <>
          <form action={doPreview} className="mt-4 space-y-2">
            <textarea
              name="roster"
              rows={8}
              defaultValue={preview?.source ?? ""}
              spellCheck={false}
              placeholder={"village:ada-sourcing, Ada Sourcing, Research & Market Intelligence\nvillage:bo-ops, Bo Ops, Client Success & Operations"}
              className="w-full rounded-lg border border-line bg-surface p-3 font-mono text-meta text-ink"
            />
            <Submit label="Show what this would change" busy="Reading…" />
          </form>
          <Result state={preview} />
          {preview?.diff ? (
            <>
              <Diff diff={preview.diff} />
              <form action={doImport} className="mt-3">
                <input type="hidden" name="roster" value={preview.source ?? ""} />
                <Submit label="Apply this roster" busy="Importing…" tone="primary" />
              </form>
              <Result state={applied} />
            </>
          ) : null}
        </>
      ) : (
        <>
          <form action={doRegister} className="mt-4 grid gap-3 sm:grid-cols-3">
            <label className="text-meta text-ink-secondary">
              Village reference
              <input
                name="village_agent_ref"
                required
                placeholder="village:ada-sourcing"
                className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 font-mono text-meta text-ink"
              />
            </label>
            <label className="text-meta text-ink-secondary">
              Name
              <input
                name="agent_name"
                required
                className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
              />
            </label>
            <label className="text-meta text-ink-secondary">
              Department
              <select
                name="department"
                required
                defaultValue=""
                className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
              >
                <option value="" disabled>
                  Choose one
                </option>
                {departments.map((option) => (
                  <option key={option.department} value={option.department}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="sm:col-span-3">
              <Submit label="Record agent" busy="Recording…" />
            </div>
          </form>
          <Result state={registered} />
        </>
      )}
    </div>
  );
}

/**
 * Issue identities for a whole department, or for one agent.
 *
 * The bulk form is the useful one: a department arrives from the Village together, and
 * issuing twelve identities one at a time is how nine departments come to have none.
 */
export function IssueIdentities({
  department,
  agents,
}: {
  department?: RosterDepartment;
  agents: RosterAgent[];
}) {
  const [state, action] = useFormState<RosterState | null, FormData>(
    issueIdentitiesAction,
    null,
  );

  const eligible = agents.filter(
    (agent) => !agent.has_identity && agent.village_agent_ref && agent.roster_status === "active",
  );
  if (eligible.length === 0) return null;

  return (
    <form action={action} className="mt-2">
      {eligible.map((agent) => (
        <input
          key={agent.village_agent_ref}
          type="hidden"
          name="village_agent_ref"
          value={agent.village_agent_ref ?? ""}
        />
      ))}
      <Submit
        label={
          department
            ? `Issue identities for all ${eligible.length} in ${department.department}`
            : `Issue ${eligible.length} identit${eligible.length === 1 ? "y" : "ies"}`
        }
        busy="Issuing…"
      />
      <Result state={state} />
    </form>
  );
}
