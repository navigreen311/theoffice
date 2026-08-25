import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { CircleCheck, Minus } from "@/components/icons";
import { Ago, AsOf, LocalTime } from "@/components/local-time";
import { api, ApiError, NotAuthenticated } from "@/lib/api";
import { severityTone, type Taxonomy } from "@/lib/incidents";

import { AppendAccountForm } from "../forms";
import { SlaAge } from "../sla";
import { ResolveIncidentForm } from "../../access/forms";

export const dynamic = "force-dynamic";

/**
 * One incident.
 *
 * There was no view of a single incident at all: the list was the whole feature, so an
 * incident's trace, its linked calls and whatever anybody did about it existed only in
 * the database.
 *
 * Two things are kept visibly apart. **The detection** is what was seen, and it is never
 * editable — the table refuses UPDATE and this page offers nothing that would try.
 * **The response** is a timeline of appended accounts, each with a name and a time.
 * Merging them would let the response quietly rewrite the finding, which is the whole
 * reason `incident` is append-only.
 *
 * Each of Part 9's five stages is either accounted for or explicitly outstanding. A
 * stage rendered as an empty row reads as "nothing to say here"; what it means is that
 * nobody has said it.
 */

type Account = {
  account_id: number;
  stage: string;
  account: string;
  written_at: string;
  written_by_name: string;
};

type Detail = {
  incident_id: string;
  severity: string;
  kind: string;
  kind_meaning: string;
  venture_id: string | null;
  office_agent_id: string | null;
  agent_name: string | null;
  forge_id: string | null;
  module_id: string | null;
  trace_id: string | null;
  detail: Record<string, unknown>;
  raised_at: string;
  detection_source: string;
  reported_by_name: string | null;
  resolution: string | null;
  resolved_at: string | null;
  as_of: string;
  resolved_by_name: string | null;
  stages: {
    stage: string;
    label: string;
    hint: string;
    accounted: boolean;
    accounts: Account[];
  }[];
  linked_calls: {
    call_id: string;
    office_agent_id: string;
    forge_id: string;
    module_id: string;
    status_code: number | null;
    ts_start: string;
    venture_id: string;
  }[];
};

export default async function IncidentDetailPage({
  params,
}: {
  params: { incidentId: string };
}) {
  let incident: Detail;
  let taxonomy: Taxonomy;
  try {
    [incident, taxonomy] = await Promise.all([
      api.get<Detail>(`/api/incidents/${params.incidentId}`),
      api.get<Taxonomy>("/api/incidents/taxonomy"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const label =
    taxonomy.kinds.find((k) => k.kind === incident.kind)?.label ?? incident.kind;
  const outstanding = incident.stages.filter((stage) => !stage.accounted);
  const summary =
    typeof incident.detail?.summary === "string" ? incident.detail.summary : null;

  return (
    <div className="space-y-3">
      <Breadcrumb
        trail={[
          { label: "Dashboard", href: "/" },
          { label: "Incidents", href: "/incidents" },
          { label: label },
        ]}
      />

      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-page font-medium text-ink">{label}</h1>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            {incident.kind_meaning}
          </p>
        </div>
        <AsOf iso={incident.as_of} />
      </div>

      {/* The detection, as recorded. Never editable. */}
      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-section font-medium text-ink">The detection</h2>
          <span
            className={`rounded-lg border px-2 py-0.5 text-meta ${severityTone(
              incident.severity,
            )}`}
          >
            {incident.severity.toLowerCase()}
          </span>
          <code className="text-ident text-ink-muted">{incident.kind}</code>
          <span className="ml-auto text-meta text-ink-muted">
            raised <LocalTime iso={incident.raised_at} />
          </span>
        </div>

        <p className="mt-2 max-w-3xl text-desc text-ink-secondary">
          This is what was seen. It is never edited: a later finding is a new incident
          referencing the same trace, because a detection that can be rewritten is worth
          less than the row it sits in.
        </p>

        {summary ? (
          <p className="mt-3 rounded-lg border border-line bg-surface-muted px-3 py-2 text-desc text-ink">
            {summary}
          </p>
        ) : null}

        <dl className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
          {[
            ["Detection source", incident.detection_source.replace(/_/g, " ")],
            ["Filed by", incident.reported_by_name ?? "a control, not a person"],
            ["Venture", incident.venture_id ?? "not venture-specific"],
            [
              "Agent",
              incident.agent_name ?? incident.office_agent_id ?? "no agent named",
            ],
            [
              "Forge module",
              incident.forge_id
                ? `${incident.forge_id}/${incident.module_id ?? "—"}`
                : "no module named",
            ],
            ["Trace", incident.trace_id ?? "no trace"],
          ].map(([term, value]) => (
            <div key={term}>
              <dt className="text-meta text-ink-muted">{term}</dt>
              <dd className="text-desc text-ink">{value}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-3">
          {incident.resolved_at ? (
            <p className="text-meta text-ok">
              Resolved <Ago iso={incident.resolved_at} /> by{" "}
              {incident.resolved_by_name ?? "unknown"} — {incident.resolution}
            </p>
          ) : (
            <SlaAge
              raisedAt={incident.raised_at}
              severity={incident.severity}
              taxonomy={taxonomy}
              resolved={false}
            />
          )}
        </div>
      </section>

      {/* The response. Appended, never edited. */}
      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h2 className="text-section font-medium text-ink">The response</h2>
          <span className="text-meta text-ink-muted">
            {outstanding.length === 0
              ? "every stage accounted for"
              : `${outstanding.length} of ${incident.stages.length} stages outstanding`}
          </span>
        </div>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Part 9&rsquo;s five stages. Each is either accounted for or outstanding, said
          rather than left blank — an empty row reads as nothing to report, and it means
          nobody has reported anything.
        </p>

        <ol className="mt-3">
          {incident.stages.map((stage) => (
            <li key={stage.stage} className="border-t border-line py-3 first:border-t-0">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                {stage.accounted ? (
                  <CircleCheck className="h-4 w-4 text-ok" />
                ) : (
                  <Minus className="h-4 w-4 text-ink-muted" />
                )}
                <span className="text-rowtitle font-medium text-ink">{stage.label}</span>
                <span className="text-meta text-ink-muted">{stage.hint}</span>
                {!stage.accounted ? (
                  <span className="ml-auto rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 text-meta text-warn">
                    outstanding
                  </span>
                ) : null}
              </div>

              {stage.accounts.map((account) => (
                <div
                  key={account.account_id}
                  className="mt-2 rounded-lg border border-line bg-surface-muted px-3 py-2"
                >
                  <p className="text-desc text-ink">{account.account}</p>
                  <p className="mt-1 text-meta text-ink-muted">
                    {account.written_by_name} · <LocalTime iso={account.written_at} />
                  </p>
                </div>
              ))}
            </li>
          ))}
        </ol>
      </section>

      {incident.linked_calls.length > 0 ? (
        <section className="rounded-xl border border-line bg-surface px-5 py-4">
          <h2 className="text-section font-medium text-ink">
            Calls under this trace
          </h2>
          <p className="mt-0.5 text-desc text-ink-secondary">
            The link a responder actually follows: an incident names a trace, and the
            question is always what else happened under it.
          </p>
          <ul className="mt-3">
            {incident.linked_calls.map((call) => (
              <li
                key={call.call_id}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line py-2 first:border-t-0"
              >
                <code className="text-ident text-ink">
                  {call.forge_id}/{call.module_id}
                </code>
                <span className="text-meta text-ink-muted">{call.venture_id}</span>
                <span className="text-meta text-ink-muted">
                  {call.status_code ?? "in flight"}
                </span>
                <span className="ml-auto text-meta text-ink-muted">
                  <LocalTime iso={call.ts_start} />
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Append an account</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          The only write on this page. There is no edit and no delete, here or in the
          database — correcting an account means appending a later one, so the timeline
          shows what was believed and when that changed.
        </p>
        <div className="mt-3">
          <AppendAccountForm
            incidentId={incident.incident_id}
            stages={taxonomy.stages}
            defaultStage={outstanding[0]?.stage ?? "post_mortem"}
          />
        </div>
      </section>

      {!incident.resolved_at ? (
        <section className="rounded-xl border border-line bg-surface px-5 py-4">
          <h2 className="text-section font-medium text-ink">Close this incident</h2>
          <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
            Closing appends an account of what was done and leaves the detection intact.
            It can only be done once: a second resolution would replace who closed it and
            why.
          </p>
          <div className="mt-3">
            <ResolveIncidentForm incidentId={incident.incident_id} />
          </div>
        </section>
      ) : null}

      <p className="text-meta text-ink-muted">
        <Link href="/incidents" className="underline underline-offset-2">
          All incidents
        </Link>
      </p>
    </div>
  );
}
