import Link from "next/link";
import { redirect } from "next/navigation";

import { Ago } from "@/components/local-time";
import { AlertTriangle, CircleCheck, CONTROL_ICON } from "@/components/icons";
import {
  api,
  NotAuthenticated,
  type ChainStatus,
  type ComplianceOverview,
  type IncidentRow,
  type Paged,
} from "@/lib/api";
import { controlSeverity, incidentSeverity } from "@/lib/severity";

import { ExportForm, RunControlsButton, SchedulingNote } from "./compliance-forms";

export const dynamic = "force-dynamic";

/**
 * Compliance — Part 17.
 *
 * The job of this page is to be honest about what is *not* known, which is harder than
 * reporting what is: an empty incident list and a verified chain look identical whether
 * the checks ran this morning or have never run at all.
 *
 * The rebuild changes who it is written for. It used to tell a reader who already knew
 * the system what state it was in — four snake_case identifiers and a count. Now it
 * states a conclusion, says what each control does in a sentence, gives every number a
 * denominator, and puts the compliance frameworks on the compliance page.
 *
 * Three things did not change and must not:
 *
 *   * control freshness sits **above** incidents, deliberately;
 *   * the banner does not disappear when everything is fine — it turns green and says
 *     so, because health communicated by the absence of a warning is indistinguishable
 *     from a warning that failed to render;
 *   * every sentence about evidence is kept verbatim. That copy is the point of the
 *     page, and "tightening" it is how a page stops saying the difficult thing.
 */

const TONE = {
  ok: {
    surface: "border-ok-line bg-ok-bg",
    text: "text-ok",
  },
  warn: {
    surface: "border-warn-line bg-warn-bg",
    text: "text-warn",
  },
  bad: {
    surface: "border-bad-line bg-bad-bg",
    text: "text-bad",
  },
  critical: {
    surface: "border-critical-line bg-critical-bg",
    text: "text-critical",
  },
  neutral: {
    surface: "border-neutral2-line bg-neutral2-bg",
    text: "text-neutral2",
  },
} as const;

function Pill({
  tone,
  children,
}: {
  tone: keyof typeof TONE;
  children: React.ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-meta ${TONE[tone].surface} ${TONE[tone].text}`}
    >
      {children}
    </span>
  );
}

function Card({
  title,
  subtitle,
  action,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border-[0.5px] border-line bg-surface px-5 py-4">
      <header className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-section font-medium text-ink">{title}</h2>
          {subtitle ? (
            <p className="mt-1 max-w-3xl text-desc text-ink-secondary">{subtitle}</p>
          ) : null}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

/** A metric that always carries its denominator. */
function Metric({
  label,
  value,
  denominator,
  note,
  alarming,
}: {
  label: string;
  value: number;
  denominator: number;
  note?: string;
  alarming?: boolean;
}) {
  return (
    <div className="rounded-xl bg-surface-muted px-4 py-3">
      <div className="text-desc text-ink-secondary">{label}</div>
      <div
        className={`mt-1 text-[24px] font-medium leading-tight ${
          alarming ? "text-bad" : "text-ink"
        }`}
      >
        {value} <span className="text-ink-muted">of {denominator}</span>
      </div>
      {note ? <p className="mt-1 text-meta text-ink-muted">{note}</p> : null}
    </div>
  );
}

export default async function CompliancePage() {
  let overview: ComplianceOverview;
  let chain: ChainStatus;
  let incidents: Paged<IncidentRow>;

  try {
    [overview, chain, incidents] = await Promise.all([
      api.get<ComplianceOverview>("/api/compliance"),
      api.get<ChainStatus>("/api/audit/chain"),
      api.get<Paged<IncidentRow>>("/api/incidents?limit=25"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const verified = overview.scorecard.controls_verified;
  const allVerified = verified.value === verified.denominator;
  const unverified = overview.controls.filter((c) => !c.healthy);
  const neverRun = unverified.filter((c) => c.state === "never_run");
  const runsRecorded = overview.controls.filter((c) => c.last_run).length;

  const asOf = new Date(overview.as_of);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-section font-medium text-ink">Compliance</h1>
        {/* A compliance view with no time anchor cannot be used as evidence, and a
            screenshot of it cannot be dated. */}
        <p className="text-meta text-ink-muted">
          As of {asOf.toISOString().replace("T", " ").slice(0, 19)} UTC
        </p>
      </div>

      {/* ------------------------------------------------------------- banner */}
      {allVerified ? (
        <div
          className={`flex items-start gap-3 rounded-xl border px-5 py-4 ${TONE.ok.surface}`}
        >
          <CircleCheck size={20} className={`mt-0.5 shrink-0 ${TONE.ok.text}`} />
          <div>
            <p className={`text-body font-medium ${TONE.ok.text}`}>
              All controls verified within their max age
            </p>
            <p className="mt-1 text-desc text-ink-secondary">
              {verified.value} of {verified.denominator} controls ran inside their
              expected cadence. Findings below were produced by checks that actually
              ran.
            </p>
          </div>
        </div>
      ) : (
        <div
          className={`flex items-start gap-3 rounded-xl border px-5 py-4 ${TONE.bad.surface}`}
        >
          <AlertTriangle size={20} className={`mt-0.5 shrink-0 ${TONE.bad.text}`} />
          <div className="min-w-0">
            <p className={`text-body font-medium ${TONE.bad.text}`}>
              Compliance posture is unverified, not clean
            </p>
            <p className="mt-1 text-desc text-ink-secondary">
              {neverRun.length > 0
                ? `${neverRun.length} of ${verified.denominator} controls have never run.`
                : `${unverified.length} of ${verified.denominator} controls are not fresh.`}{" "}
              Nothing on this page below has been checked, including the empty incident
              list.{" "}
              <span className={TONE.bad.text}>
                An absence of findings from a check that did not run is not evidence.
              </span>
            </p>
            <div className="mt-3 flex flex-wrap items-start gap-4">
              <RunControlsButton
                label={`Run all ${overview.controls.filter((c) => c.runnable_from_here).length} controls now`}
                emphasis
              />
              <SchedulingNote recentRuns={runsRecorded} />
            </div>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------- scorecard */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Ventures live"
          value={overview.scorecard.ventures_live.value}
          denominator={overview.scorecard.ventures_live.denominator}
          note="a venture is live when an agent could actually act for it"
        />
        <Metric
          label="Agents with grants"
          value={overview.scorecard.agents_with_grants.value}
          denominator={overview.scorecard.agents_with_grants.denominator}
          note={overview.scorecard.agents_with_grants.note}
        />
        <Metric
          label="Frameworks in scope"
          value={overview.scorecard.frameworks_in_scope.value}
          denominator={overview.scorecard.frameworks_in_scope.denominator}
          note={overview.scorecard.frameworks_in_scope.note}
        />
        <Metric
          label="Controls verified"
          value={verified.value}
          denominator={verified.denominator}
          alarming={!allVerified}
        />
      </div>

      {/* -------------------------------------------------- control freshness */}
      <Card
        title="Control freshness"
        subtitle="Shown above incidents deliberately: a quiet incident list means nothing if the check producing it is stale."
      >
        <ul className="divide-y divide-line">
          {overview.controls.map((control) => {
            const tone = controlSeverity(control.state) as keyof typeof TONE;
            const ControlIcon = CONTROL_ICON[control.id] ?? AlertTriangle;
            const stateLabel =
              control.state === "never_run"
                ? "never run"
                : control.state === "fresh"
                  ? "verified"
                  : control.state;

            return (
              <li key={control.id} className="flex gap-3 py-4 first:pt-0 last:pb-0">
                <ControlIcon size={18} className={`mt-0.5 shrink-0 ${TONE[tone].text}`} />

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-rowtitle font-medium text-ink">
                      {control.name}
                    </span>
                    {/* Kept beside the human name for engineers, who search by it. */}
                    <code className="text-ident text-ink-muted">{control.id}</code>
                    <Pill tone={tone}>{stateLabel}</Pill>
                  </div>

                  <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
                    {control.checks}
                  </p>

                  <p className="mt-1 text-meta text-ink-muted">
                    {control.cadence}
                    {" · "}
                    {control.last_run
                      ? `last run $<Ago iso={control.last_run} />`
                      : "never run"}
                    {control.denominator !== undefined &&
                    control.denominator !== null ? (
                      <> {" · "}checked {control.denominator} item(s)</>
                    ) : null}
                    {" · "}
                    <span className={control.blocking ? TONE.bad.text : undefined}>
                      {control.consequence}
                    </span>
                  </p>

                  {!control.runnable_from_here ? (
                    <p className="mt-2 text-meta text-ink-muted">
                      Cannot be run from this page: it needs superuser credentials to
                      create a scratch database, and the API deliberately does not hold
                      them. On the host:{" "}
                      <code className="text-ident text-ink-secondary">
                        {control.host_command}
                      </code>
                    </p>
                  ) : null}
                </div>

                <div className="shrink-0">
                  {control.runnable_from_here ? (
                    <RunControlsButton control={control.id} label="Run" />
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      </Card>

      {/* ----------------------------------------------- framework coverage */}
      <Card
        title="Framework coverage by venture"
        subtitle="Every framework a Pack declares must resolve to a runtime flag and a Compliance Library entry. Missing either means the obligation is named but not enforced."
      >
        {overview.ventures.length === 0 ? (
          <p className="text-desc text-ink-secondary">
            No venture has reached this Office yet.
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {overview.ventures.map((venture) => {
              const tone =
                venture.status === "ready"
                  ? "ok"
                  : venture.status === "gaps"
                    ? "warn"
                    : "bad";
              return (
                <li key={venture.venture_id} className="py-3 first:pt-0 last:pb-0">
                  <Link
                    href={`/ventures/${encodeURIComponent(venture.venture_id)}`}
                    className="flex flex-wrap items-center gap-2"
                  >
                    <span className="text-rowtitle font-medium text-ink underline-offset-2 hover:underline">
                      {venture.venture_id}
                    </span>
                    <Pill tone={tone}>{venture.status}</Pill>
                    <span className="text-meta text-ink-muted">
                      {venture.resolved} of {venture.declared} frameworks resolve
                    </span>
                  </Link>

                  {venture.blocked_because ? (
                    <p className="mt-1 text-desc text-bad">{venture.blocked_because}</p>
                  ) : null}

                  {venture.frameworks.length === 0 ? (
                    <p className="mt-1 text-meta text-ink-muted">
                      This Pack declares no compliance surface.
                    </p>
                  ) : (
                    <ul className="mt-2 flex flex-wrap gap-2">
                      {venture.frameworks.map((f) => (
                        <li key={f.framework}>
                          <Pill tone={f.has_flag && f.has_entry ? "ok" : "warn"}>
                            {f.framework}
                            {!f.has_flag ? " · no runtime flag" : ""}
                            {!f.has_entry ? " · no library entry" : ""}
                          </Pill>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {/* ------------------------------------------------------- audit chain */}
      <Card
        title="Audit chain"
        subtitle="Until Forges carry per-agent identity this ledger is the only per-agent record anywhere."
      >
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={chain.ok ? "ok" : "critical"}>
            {chain.ok ? "verified" : "BROKEN"}
          </Pill>
          {chain.tail_gap > 0 ? (
            <Pill tone="warn">
              tail gap {chain.tail_gap} — deletion or rolled-back inserts, investigate
            </Pill>
          ) : null}
          {chain.first_break_audit_id !== null ? (
            <Pill tone="critical">first break at #{chain.first_break_audit_id}</Pill>
          ) : null}
        </div>

        <dl className="mt-3 grid gap-3 sm:grid-cols-4">
          <div>
            <dt className="text-meta text-ink-muted">Entries</dt>
            <dd className="text-body text-ink">
              {overview.chain_stats.audit_entries.toLocaleString("en-US")}
            </dd>
          </div>
          <div>
            <dt className="text-meta text-ink-muted">Chain verified through</dt>
            <dd className="text-body text-ink">
              {chain.checked_count.toLocaleString("en-US")} of{" "}
              {overview.chain_stats.audit_entries.toLocaleString("en-US")}
            </dd>
          </div>
          <div>
            <dt className="text-meta text-ink-muted">Oldest entry</dt>
            <dd className="text-body text-ink">
              <Ago iso={overview.chain_stats.oldest_entry} />
            </dd>
          </div>
          <div>
            <dt className="text-meta text-ink-muted">Last agent call</dt>
            {/* The single field that tells a reader the system has not started
                operating. Nothing else on this page conveys it. */}
            <dd
              className={`text-body ${
                overview.chain_stats.last_agent_call ? "text-ink" : "text-ink-muted"
              }`}
            >
              {overview.chain_stats.last_agent_call ? (
                <Ago iso={overview.chain_stats.last_agent_call} />
              ) : (
                "none yet"
              )}
            </dd>
          </div>
        </dl>

        <p className="mt-3 text-meta text-ink-muted">{chain.reason}</p>
      </Card>

      {/* --------------------------------------------------------- incidents */}
      <Card
        title="Open incidents"
        subtitle="Unresolved only. Detections, not workflow — an incident is never edited, and resolving one appends an account of what was done."
      >
        {incidents.items.length === 0 ? (
          <p className="text-desc text-ink-secondary">
            No unresolved incidents. Check the control freshness above before reading
            that as good news — a check that never ran raises nothing.
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {incidents.items.map((incident) => (
              <li
                key={incident.incident_id}
                className="flex flex-wrap items-center gap-3 py-2 first:pt-0 last:pb-0"
              >
                <Pill tone={incidentSeverity(incident.severity) as keyof typeof TONE}>
                  {incident.severity}
                </Pill>
                <code className="text-ident text-ink-secondary">{incident.kind}</code>
                <span className="text-desc text-ink-secondary">
                  {incident.venture_id ?? "portfolio"}
                  {incident.module_id ? ` · ${incident.module_id}` : ""}
                </span>
                <span className="ml-auto text-meta text-ink-muted">
                  <Ago iso={incident.raised_at} />
                </span>
                <Link
                  href="/incidents"
                  className="text-meta text-ink-secondary underline underline-offset-2"
                >
                  resolve →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* ------------------------------------------------------------ export */}
      <ExportForm ventures={overview.ventures.map((v) => v.venture_id)} />
    </div>
  );
}
