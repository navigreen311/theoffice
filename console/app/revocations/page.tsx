import { redirect } from "next/navigation";

import { AsOf, LocalTime } from "@/components/local-time";
import { Term } from "@/components/term";
import { api, NotAuthenticated } from "@/lib/api";
import { REVOCATION_SCOPE, ROLE } from "@/lib/vocabulary";

import { RevokeForm } from "./form";
import { ReinstateForm } from "./reinstate";

export const dynamic = "force-dynamic";

/**
 * Revocation Controls — Part 17, and §1.4.
 *
 * With no queue to drain and no front desk to stop, revocation is the kill switch. The
 * screen states the blast radius of each scope next to the control, because "revoke" on
 * a Forge and "revoke" on one grant are the same word for very different acts.
 *
 * Four things were missing, all of them about what happens around the act rather than
 * the act itself: nothing showed what is currently revoked, nothing showed what any
 * revocation had ever cost, re-enabling had no ritual on screen, and the form asked for
 * UUIDs by hand.
 */

const SCOPES = [
  {
    scope: "agent_module",
    authority: "venture_operator",
    effect: "One grant revoked.",
  },
  {
    scope: "agent",
    authority: "venture_operator",
    effect: "This agent cannot reach any Forge.",
  },
  {
    scope: "venture",
    authority: "compliance_officer",
    effect: "Every grant for this engagement, including ones issued later.",
  },
  {
    scope: "forge",
    authority: "ivan",
    effect: "The broker refuses all calls to this Forge, for every agent.",
  },
];

type Targets = {
  as_of: string;
  agents: { id: string; name: string | null; detail: string | null }[];
  ventures: { id: string; name: string | null; detail: string | null }[];
  forges: { id: string; name: string | null; detail: string | null }[];
  grants: { forge_id: string; module_id: string; office_agent_id: string }[];
};

type HistoryRow = {
  revocation_id: string;
  scope: string;
  reason: string;
  office_agent_id: string | null;
  agent_name: string | null;
  forge_id: string | null;
  module_id: string | null;
  venture_id: string | null;
  revoked_at: string;
  revoked_by_name: string | null;
  revoked_by_role: string;
  reinstated_at: string | null;
  reinstated_by_name: string | null;
  reinstatement_reason: string | null;
  second_human_name: string | null;
  blast_radius: Record<string, number | string | null>;
  duration_hours: number;
  active: boolean;
};

function targetOf(row: HistoryRow): string {
  if (row.scope === "venture") return row.venture_id ?? "unknown venture";
  if (row.scope === "forge") return row.forge_id ?? "unknown Forge";
  if (row.scope === "agent") return row.agent_name ?? row.office_agent_id ?? "unknown agent";
  return `${row.agent_name ?? row.office_agent_id ?? "agent"} · ${row.forge_id}/${row.module_id}`;
}

export default async function RevocationsPage() {
  let targets: Targets;
  let history: HistoryRow[];
  let humans: { human_id: string; display_name: string; status: string }[] = [];
  try {
    [targets, history] = await Promise.all([
      api.get<Targets>("/api/revocations/targets"),
      api.get<HistoryRow[]>("/api/revocations/history"),
    ]);
    try {
      humans = await api.get<typeof humans>("/api/humans");
    } catch {
      // `/api/humans` needs compliance_officer. A venture operator can still revoke and
      // still lift the two narrow scopes, neither of which needs a second human — so an
      // empty list here is a smaller capability, not a broken page.
      humans = [];
    }
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const active = history.filter((row) => row.active);

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-page font-medium text-ink">Revocation</h1>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            Checked live at the broker on every call, never cached — a revoked
            agent&rsquo;s NEXT call fails, not its next session.
          </p>
        </div>
        <AsOf iso={targets.as_of} />
      </div>

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">The four scopes</h2>
        <table className="mt-2 w-full border-collapse">
          <thead>
            <tr className="border-b border-line text-left">
              <th className="py-2 pr-3 text-meta font-medium text-ink-muted">Scope</th>
              <th className="py-2 pr-3 text-meta font-medium text-ink-muted">Effect</th>
              <th className="py-2 text-meta font-medium text-ink-muted">Authority</th>
            </tr>
          </thead>
          <tbody>
            {SCOPES.map((s) => (
              <tr key={s.scope} className="border-b border-line last:border-0">
                <td className="py-2 pr-3">
                  <Term value={s.scope} from={REVOCATION_SCOPE} />
                </td>
                <td className="py-2 pr-3 text-desc text-ink-secondary">{s.effect}</td>
                <td className="py-2">
                  <Term value={s.authority} from={ROLE} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 max-w-3xl text-meta text-ink-muted">
          The console does not pre-check your authority. The API checks it twice — role
          strength for the scope, and whether you operate that venture — and reports the
          refusal. A second opinion here would eventually disagree with the first.
        </p>
      </section>

      <RevokeForm
        agents={targets.agents}
        ventures={targets.ventures}
        forges={targets.forges}
        grants={targets.grants}
      />

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Currently revoked</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          What the broker is refusing right now. Every one of these is checked live on
          every call.
        </p>

        {active.length === 0 ? (
          <p className="mt-3 text-desc text-ink-secondary">
            {targets.grants.length === 0
              ? "Nothing is revoked. No agent holds a grant yet, so there is nothing to revoke."
              : "Nothing is revoked. Every live grant is currently usable."}
          </p>
        ) : (
          <ul className="mt-3">
            {active.map((row) => (
              <li
                key={row.revocation_id}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line py-2.5 first:border-t-0"
              >
                <Term value={row.scope} from={REVOCATION_SCOPE} />
                <span className="text-rowtitle font-medium text-ink">{targetOf(row)}</span>
                <span className="text-meta text-ink-secondary">{row.reason}</span>
                <span className="ml-auto text-meta text-ink-muted">
                  {row.revoked_by_name ?? "unknown"} ·{" "}
                  <LocalTime iso={row.revoked_at} />
                </span>
                <div className="w-full">
                  <ReinstateForm
                    revocationId={row.revocation_id}
                    scope={row.scope}
                    targetName={targetOf(row)}
                    humans={humans.map((h) => ({
                      id: h.human_id,
                      name: h.display_name,
                      detail: h.status,
                    }))}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Every revocation ever issued</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Regulator-export material: the reason, who acted, what it stopped at the time,
          how long it lasted, and who lifted it. Re-enabling appends an account and never
          removes the record.
        </p>

        {history.length === 0 ? (
          <p className="mt-3 text-desc text-ink-secondary">
            No revocation has ever been issued.
          </p>
        ) : (
          <ul className="mt-3">
            {history.map((row) => (
              <li
                key={row.revocation_id}
                className="border-t border-line py-2.5 first:border-t-0"
              >
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <Term value={row.scope} from={REVOCATION_SCOPE} />
                  <span className="text-rowtitle font-medium text-ink">
                    {targetOf(row)}
                  </span>
                  <span
                    className={`rounded-lg border px-2 py-0.5 text-meta ${
                      row.active
                        ? "border-bad-line bg-bad-bg text-bad"
                        : "border-line bg-surface-muted text-ink-secondary"
                    }`}
                  >
                    {row.active
                      ? `active ${Math.round(row.duration_hours)}h`
                      : `lasted ${Math.round(row.duration_hours)}h`}
                  </span>
                  <span className="ml-auto text-meta text-ink-muted">
                    {row.revoked_by_name ?? "unknown"} ({row.revoked_by_role}) ·{" "}
                    <LocalTime iso={row.revoked_at} />
                  </span>
                </div>

                <p className="mt-1 text-desc text-ink-secondary">{row.reason}</p>

                {typeof row.blast_radius?.grants === "number" ? (
                  <p className="mt-1 text-meta text-ink-muted">
                    Stopped {row.blast_radius.agents} agents and{" "}
                    {row.blast_radius.grants} grants, {row.blast_radius.in_flight_calls}{" "}
                    calls in flight — counted when it was issued, not now.
                  </p>
                ) : null}

                {row.reinstated_at ? (
                  <p className="mt-1 text-meta text-ink-secondary">
                    Re-enabled by {row.reinstated_by_name ?? "unknown"}
                    {row.second_human_name ? ` with ${row.second_human_name}` : ""} ·{" "}
                    <LocalTime iso={row.reinstated_at} /> — {row.reinstatement_reason}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
