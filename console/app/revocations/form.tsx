"use client";

import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { AlertTriangle } from "@/components/icons";
import { Badge, Button, inputClass } from "@/components/ui";

import { blastRadiusAction, revokeAction } from "./actions";
import { Picker, type Option } from "./picker";

/**
 * The kill switch, made usable at the moment it is used.
 *
 * `useFormState` from react-dom, not `useActionState` from react: the latter is React 19
 * and this project pins 18.3.1. Both `tsc --noEmit` and `next build` pass with the React
 * 19 hook and the page throws in the browser, which has cost this project two reported
 * outages.
 *
 * Three things this form did not do. It asked for four UUIDs as free text — this is the
 * emergency control, and nobody recalls a UUID under pressure; a typo either fails or
 * stops the wrong thing, and the second is worse. It rendered all four fields at once
 * with hint text naming which scopes used each, which is documentation for whoever wrote
 * the form. And a single red button issued a revocation that, at Forge scope, stops
 * every agent in the portfolio.
 *
 * **No authority pre-checking.** The API decides whether you may act, once, and reports
 * the refusal. Blast radius is a count of what exists, not an opinion about permission —
 * showing somebody the size of what they are about to stop is not a second implementation
 * of the rule about whether they may.
 */

export type Scope = "agent_module" | "agent" | "venture" | "forge";

const SCOPES: {
  scope: Scope;
  label: string;
  effect: string;
  authority: string;
  fields: ("office_agent_id" | "forge_id" | "module_id" | "venture_id")[];
}[] = [
  {
    scope: "agent_module",
    label: "One grant",
    effect: "One grant revoked.",
    authority: "venture_operator",
    fields: ["office_agent_id", "forge_id", "module_id"],
  },
  {
    scope: "agent",
    label: "One agent",
    effect: "This agent cannot reach any Forge.",
    authority: "venture_operator",
    fields: ["office_agent_id"],
  },
  {
    scope: "venture",
    label: "A venture",
    effect: "Every grant for this engagement, including ones issued later.",
    authority: "compliance_officer",
    fields: ["venture_id"],
  },
  {
    scope: "forge",
    label: "A whole Forge",
    effect: "The broker refuses all calls to this Forge, for every agent.",
    authority: "ivan",
    fields: ["forge_id"],
  },
];

export type Radius = {
  scope: string;
  effect: string;
  required_role: string;
  agents: number;
  grants: number;
  ventures: number;
  in_flight_calls: number;
  shifts_today: number | null;
  forward_looking: string | null;
  needs_two_humans_to_lift: boolean;
};

function Submit({ label, busy }: { label: string; busy: string }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="danger" disabled={pending}>
      {pending ? busy : label}
    </Button>
  );
}

function Figure({ value, label }: { value: string | number; label: string }) {
  return (
    <div>
      <div className="text-[18px] font-medium leading-tight text-bad">{value}</div>
      <div className="text-ident text-ink-muted">{label}</div>
    </div>
  );
}

export function RevokeForm({
  agents,
  ventures,
  forges,
  grants,
}: {
  agents: Option[];
  ventures: Option[];
  forges: Option[];
  grants: { forge_id: string; module_id: string; office_agent_id: string }[];
}) {
  const [state, action] = useFormState(revokeAction, null);
  const [scope, setScope] = useState<Scope>("agent_module");
  const [agent, setAgent] = useState("");
  const [forge, setForge] = useState("");
  const [module, setModule] = useState("");
  const [venture, setVenture] = useState("");
  const [reason, setReason] = useState("");
  const [radius, setRadius] = useState<Radius | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");

  const chosen = SCOPES.find((s) => s.scope === scope)!;
  const uses = (field: string) => chosen.fields.includes(field as never);

  // Modules are only meaningful for a chosen agent and Forge, so the third picker is
  // narrowed by the first two rather than listing every module in the portfolio.
  const modules = grants
    .filter((g) => (!agent || g.office_agent_id === agent) && (!forge || g.forge_id === forge))
    .map((g) => ({ id: g.module_id, name: g.module_id, detail: g.forge_id }));

  const target = uses("venture_id")
    ? ventures.find((v) => v.id === venture)
    : uses("office_agent_id") && scope === "agent"
      ? agents.find((a) => a.id === agent)
      : uses("forge_id") && scope === "forge"
        ? forges.find((f) => f.id === forge)
        : null;

  const ready =
    chosen.fields.every((field) =>
      field === "office_agent_id"
        ? agent
        : field === "forge_id"
          ? forge
          : field === "module_id"
            ? module
            : venture,
    ) && reason.trim().length > 0;

  // Blast radius follows the selection. It is a read: it says nothing about whether the
  // caller may act, and the console still asks nobody's permission on their behalf.
  useEffect(() => {
    let cancelled = false;
    const complete = chosen.fields.every((field) =>
      field === "office_agent_id"
        ? agent
        : field === "forge_id"
          ? forge
          : field === "module_id"
            ? module
            : venture,
    );
    if (!complete) {
      setRadius(null);
      return;
    }
    blastRadiusAction({
      scope,
      office_agent_id: agent || null,
      forge_id: forge || null,
      module_id: module || null,
      venture_id: venture || null,
    })
      .then((result) => {
        if (!cancelled) setRadius(result);
      })
      .catch(() => {
        if (!cancelled) setRadius(null);
      });
    return () => {
      cancelled = true;
    };
  }, [scope, agent, forge, module, venture, chosen.fields]);

  // Typing the name is required where a mistake stops an engagement or a portfolio.
  const needsTypedName = scope === "venture" || scope === "forge";
  const confirmed = !needsTypedName || typed.trim() === (target?.name ?? "");

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <h2 className="text-section font-medium text-ink">Issue a revocation</h2>

      <form action={action} className="mt-3 space-y-4">
        <input type="hidden" name="scope" value={scope} />
        <input type="hidden" name="office_agent_id" value={uses("office_agent_id") ? agent : ""} />
        <input type="hidden" name="forge_id" value={uses("forge_id") ? forge : ""} />
        <input type="hidden" name="module_id" value={uses("module_id") ? module : ""} />
        <input type="hidden" name="venture_id" value={uses("venture_id") ? venture : ""} />

        <div>
          <span className="text-meta text-ink-muted">What to stop</span>
          <div className="mt-1 flex flex-wrap gap-2">
            {SCOPES.map((option) => (
              <button
                key={option.scope}
                type="button"
                onClick={() => {
                  setScope(option.scope);
                  setConfirming(false);
                  setTyped("");
                }}
                className={`rounded-lg border px-3 py-1.5 text-desc transition ${
                  scope === option.scope
                    ? "border-line-strong bg-surface-muted font-medium text-ink"
                    : "border-line text-ink-secondary hover:bg-surface-muted"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
          {/* The effect and required authority, restated for the chosen scope rather
              than left in a table above the form. */}
          <p className="mt-2 text-desc text-ink-secondary">
            {chosen.effect}{" "}
            <span className="text-ink-muted">
              Requires <code className="text-ident">{chosen.authority}</code> or higher.
            </span>
          </p>
        </div>

        {/* Only the fields this scope uses. */}
        <div className="grid gap-3 sm:grid-cols-2">
          {uses("office_agent_id") ? (
            <Picker label="Agent" options={agents} value={agent} onChange={setAgent} />
          ) : null}
          {uses("forge_id") ? (
            <Picker label="Forge" options={forges} value={forge} onChange={setForge} />
          ) : null}
          {uses("module_id") ? (
            <Picker
              label="Module"
              options={modules}
              value={module}
              onChange={setModule}
              empty="No live grant matches that agent and Forge."
            />
          ) : null}
          {uses("venture_id") ? (
            <Picker label="Venture" options={ventures} value={venture} onChange={setVenture} />
          ) : null}
        </div>

        {radius ? (
          <div className="rounded-xl border border-bad-line bg-bad-bg px-4 py-3">
            <h3 className="flex items-center gap-1.5 text-desc font-medium text-bad">
              <AlertTriangle className="h-4 w-4" />
              What this stops
            </h3>
            <div className="mt-2 flex flex-wrap gap-x-8 gap-y-3">
              <Figure value={radius.agents} label="agents affected" />
              <Figure value={radius.grants} label="live grants revoked" />
              <Figure value={radius.in_flight_calls} label="in-flight calls that fail" />
              <Figure
                value={radius.shifts_today === null ? "n/a" : radius.shifts_today}
                label="shifts affected today"
              />
            </div>
            {radius.forward_looking ? (
              <p className="mt-2 text-meta text-ink-secondary">{radius.forward_looking}</p>
            ) : null}
            {radius.shifts_today === null ? (
              <p className="mt-1 text-meta text-ink-muted">
                Shifts are per agent and venture; a Forge-wide stop does not map onto
                one, so this is not zero — it does not apply.
              </p>
            ) : null}
          </div>
        ) : null}

        <label className="block text-meta text-ink-muted">
          Reason
          <span className="block text-meta text-ink-muted">
            Required. Stored on the revocation and surfaced in regulator exports.
          </span>
          <textarea
            name="reason"
            rows={2}
            required
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className={inputClass}
          />
        </label>

        {!confirming ? (
          <button
            type="button"
            disabled={!ready}
            onClick={() => setConfirming(true)}
            className="rounded-lg border border-bad-line px-3 py-1.5 text-desc font-medium text-bad transition hover:bg-bad-bg disabled:opacity-50"
          >
            Review and revoke…
          </button>
        ) : (
          <div className="rounded-xl border border-bad-line bg-bad-bg px-4 py-3">
            <h3 className="text-desc font-medium text-bad">
              Revoke {chosen.label.toLowerCase()}: {target?.name ?? module ?? "selection"}
            </h3>
            <ul className="mt-2 space-y-1 text-meta text-ink-secondary">
              <li>{chosen.effect}</li>
              {radius ? (
                <li>
                  {radius.agents} agents · {radius.grants} live grants ·{" "}
                  {radius.in_flight_calls} in-flight calls
                  {radius.shifts_today !== null ? ` · ${radius.shifts_today} shifts today` : ""}
                </li>
              ) : null}
              {radius?.forward_looking ? <li>{radius.forward_looking}</li> : null}
              <li>Reason: {reason.trim()}</li>
              <li>
                {radius?.needs_two_humans_to_lift
                  ? "Re-enabling this needs a written account and a second named human."
                  : "Re-enabling this needs a written account and your name."}
              </li>
            </ul>

            {needsTypedName ? (
              <label className="mt-3 block text-meta text-ink-muted">
                Type <span className="font-medium text-ink">{target?.name}</span> to
                confirm
                <input
                  className={inputClass}
                  value={typed}
                  onChange={(event) => setTyped(event.target.value)}
                />
              </label>
            ) : null}

            <div className="mt-3 flex flex-wrap items-center gap-3">
              {confirmed ? (
                <Submit label="Revoke now" busy="Revoking…" />
              ) : (
                <Button type="button" variant="danger" disabled>
                  Revoke now
                </Button>
              )}
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="text-meta text-ink-muted underline underline-offset-2"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {state?.error ? (
          <p className="pt-1">
            <Badge severity="bad">{state.error}</Badge>
          </p>
        ) : null}
        {state?.ok ? (
          <p className="pt-1">
            <Badge severity="ok">{state.ok}</Badge>
          </p>
        ) : null}
      </form>
    </section>
  );
}
