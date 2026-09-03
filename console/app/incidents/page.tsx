import Link from "next/link";
import { redirect } from "next/navigation";

import { AsOf, Ago } from "@/components/local-time";
import { Pager } from "@/components/pager";
import { api, NotAuthenticated, type IncidentRow, type Paged } from "@/lib/api";
import { FILTER_KEYS, severityTone, type Taxonomy } from "@/lib/incidents";

import { IncidentFilters } from "./filters";
import { ControlFreshness, type Controls } from "./freshness";
import { RaiseIncidentForm } from "./forms";
import { SlaAge } from "./sla";

export const dynamic = "force-dynamic";

/**
 * Incidents, and the one thing that closes one.
 *
 * **Resolving appends; it never edits.** The `incident` table is append-only by design:
 * "an incident is never edited; a later finding is a new incident referencing the
 * trace." A detection that can be rewritten is worth less than the row it sits in, and
 * severity is exactly the field somebody under pressure would want to lower. So this
 * screen offers no way to change one — only to record what was done about it.
 *
 * Three things this page did not do, all of which made an empty list look like calm:
 * it deferred control freshness to another screen while being able to compute it; its
 * empty state said "Nothing matches" with no filter that could exclude anything; and it
 * could not record an incident a person noticed, which is two of the three detection
 * sources the blueprint names.
 */

type Overview = {
  controls: Controls;
  open_count: number;
  total_count: number;
  as_of: string;
  by_severity: Record<string, number>;
  by_kind: {
    kind: string;
    label: string;
    open: number;
    ventures: string[];
    worst: string;
    crosses_ventures: boolean;
  }[];
};

export default async function IncidentsPage({
  searchParams,
}: {
  searchParams: Record<string, string | undefined>;
}) {
  const query = new URLSearchParams({
    limit: searchParams.limit ?? "50",
    offset: searchParams.offset ?? "0",
  });
  for (const key of FILTER_KEYS) {
    if (searchParams[key]) query.set(key, searchParams[key] as string);
  }

  let page: Paged<IncidentRow>;
  let overview: Overview;
  let taxonomy: Taxonomy;
  let ventures: { venture_id: string }[];
  try {
    [page, overview, taxonomy, ventures] = await Promise.all([
      api.get<Paged<IncidentRow>>(`/api/incidents?${query}`),
      api.get<Overview>("/api/incidents/overview"),
      api.get<Taxonomy>("/api/incidents/taxonomy"),
      api.get<{ venture_id: string }[]>("/api/ventures"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const filtering = FILTER_KEYS.some((key) => searchParams[key]);

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-page font-medium text-ink">Incidents</h1>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            Detections, not workflow. An incident is never edited — resolving one appends
            an account of what was done and leaves the detection intact.
          </p>
        </div>
        <AsOf iso={overview.as_of} />
      </div>

      <ControlFreshness controls={overview.controls} />

      {overview.by_kind.some((group) => group.crosses_ventures) ? (
        <section className="rounded-xl border border-line bg-surface px-5 py-4">
          <h2 className="text-section font-medium text-ink">Across ventures</h2>
          <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
            Grouped by kind. The same fault in two engagements is a different signal from
            two unrelated ones, and a list one incident per row shows neither.
          </p>
          <ul className="mt-3">
            {overview.by_kind
              .filter((group) => group.crosses_ventures)
              .map((group) => (
                <li
                  key={group.kind}
                  className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line py-2 first:border-t-0"
                >
                  <span className="text-rowtitle font-medium text-ink">{group.label}</span>
                  <code className="text-ident text-ink-muted">{group.kind}</code>
                  <span className="text-meta text-ink-secondary">
                    {group.open} open across {group.ventures.length} ventures:{" "}
                    {group.ventures.join(", ")}
                  </span>
                  <Link
                    href={`/incidents?kind=${encodeURIComponent(group.kind)}`}
                    className="ml-auto text-meta underline underline-offset-2"
                  >
                    See them
                  </Link>
                </li>
              ))}
          </ul>
        </section>
      ) : null}

      <IncidentFilters
        severities={taxonomy.severities}
        kinds={taxonomy.kinds}
        ventures={ventures.map((v) => v.venture_id)}
        shown={page.items.length}
        total={overview.total_count}
      />

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        {page.items.length === 0 ? (
          // The distinction the old copy blurred. "Nothing matches" and "there are none"
          // are opposite readings, and only one of them is ever good news.
          <p className="text-desc text-ink-secondary">
            {filtering
              ? `No incident matches this filter. ${overview.total_count} exist in total.`
              : overview.total_count > 0
                ? "No open incidents. All of them have been resolved."
                : "No open incidents."}
          </p>
        ) : (
          <ul>
            {page.items.map((incident) => {
              return (
                <li
                  key={incident.incident_id}
                  className="border-t border-line py-2.5 first:border-t-0"
                >
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span
                      className={`rounded-lg border px-2 py-0.5 text-meta ${severityTone(
                        incident.severity,
                      )}`}
                    >
                      {incident.severity.toLowerCase()}
                    </span>
                    <Link
                      href={`/incidents/${incident.incident_id}`}
                      className="text-rowtitle font-medium text-ink underline-offset-2 hover:underline"
                    >
                      {taxonomy.kinds.find((k) => k.kind === incident.kind)?.label ??
                        incident.kind}
                    </Link>
                    <code className="text-ident text-ink-muted">{incident.kind}</code>
                    <span className="text-meta text-ink-muted">
                      {incident.venture_id ?? "no venture"}
                    </span>
                    {incident.detection_source === "external_report" ||
                    incident.detection_source === "regulator_inquiry" ? (
                      <span className="rounded-lg border border-line bg-surface-muted px-2 py-0.5 text-meta text-ink-secondary">
                        filed by hand
                      </span>
                    ) : null}

                    <span className="ml-auto text-meta text-ink-muted">
                      raised <Ago iso={incident.raised_at} />
                    </span>
                  </div>

                  <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    {incident.resolved_at ? (
                      <span className="text-meta text-ok">
                        resolved <Ago iso={incident.resolved_at} />
                      </span>
                    ) : (
                      <SlaAge
                        raisedAt={incident.raised_at}
                        severity={incident.severity}
                        taxonomy={taxonomy}
                        resolved={false}
                      />
                    )}
                    {incident.resolution ? (
                      <span className="text-meta text-ink-secondary">
                        {incident.resolution}
                      </span>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <Pager
          page={page}
          basePath="/incidents"
          params={Object.fromEntries(
            FILTER_KEYS.map((key) => [key, searchParams[key]]),
          )}
        />
      </section>

      <RaiseIncidentForm
        taxonomy={taxonomy}
        ventures={ventures.map((v) => v.venture_id)}
      />
    </div>
  );
}
