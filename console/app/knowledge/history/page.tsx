import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { Ago } from "@/components/local-time";
import { api, NotAuthenticated } from "@/lib/api";

import { KnowledgeFilters } from "../filters";
import { NoteForm } from "../forms";
import { KnowledgeTabs } from "../tabs";

export const dynamic = "force-dynamic";

/**
 * Historical records.
 *
 * Sixty-one entries, sixty of them abandoned provisioning runs summarised "console smoke
 * test". They are filtered out of the default view and never deleted: this store refuses
 * UPDATE and DELETE, and a bad entry is answered with a compensating entry.
 */

type Row = {
  record_id: number;
  venture_id: string;
  record_type: string;
  summary: string;
  actor_type: string;
  recorded_at: string;
  origin: string;
};

type Page = {
  rows: Row[];
  total: number;
  page: number;
  pages: number;
  excluded_fixtures: number;
};

export default async function HistoryPage({
  searchParams,
}: {
  searchParams: Record<string, string | undefined>;
}) {
  const query = new URLSearchParams();
  for (const key of [
    "search",
    "venture_id",
    "origin",
    "record_type",
    "actor_type",
    "include_fixtures",
    "page",
  ]) {
    if (searchParams[key]) query.set(key, searchParams[key] as string);
  }

  let data: Page;
  let ventures: { venture_id: string }[];
  try {
    [data, ventures] = await Promise.all([
      api.get<Page>(`/api/knowledge/history?${query.toString()}`),
      api.get<{ venture_id: string }[]>("/api/ventures"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  return (
    <div className="space-y-6">
      <Breadcrumb
        trail={[
          { label: "Dashboard", href: "/" },
          { label: "Knowledge", href: "/knowledge" },
          { label: "History" },
        ]}
      />

      <div>
        <h1 className="text-page font-medium text-ink">Historical Records</h1>
        <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
          Append-only. This cannot be edited or deleted afterwards.
        </p>
      </div>

      <KnowledgeTabs />

      <KnowledgeFilters
        basePath="/knowledge/history"
        searchLabel="Search summaries"
        ventures={ventures.map((venture) => venture.venture_id)}
        extra={{ name: "actor_type", label: "Recorded by", options: ["human", "system"] }}
        excludedFixtures={data.excluded_fixtures}
        total={data.total}
        page={data.page}
        pages={data.pages}
      />

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        {data.rows.length === 0 ? (
          <p className="text-desc text-ink-secondary">
            {data.excluded_fixtures > 0
              ? `Nothing but test data. ${data.excluded_fixtures} smoke fixtures are excluded from this view.`
              : "No record matches this filter."}
          </p>
        ) : (
          <ul>
            {data.rows.map((row) => (
              <li key={row.record_id} className="border-t border-line py-2 first:border-t-0">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-mono text-meta text-ink-muted">
                    {row.record_type}
                  </span>
                  <span className="text-meta text-ink-muted">{row.venture_id}</span>
                  <span
                    className={`rounded-lg border px-2 py-0.5 text-meta ${
                      row.origin === "test_fixture"
                        ? "border-warn-line bg-warn-bg text-warn"
                        : "border-line bg-surface-muted text-ink-secondary"
                    }`}
                  >
                    {row.origin === "test_fixture" ? "test fixture" : row.actor_type}
                  </span>
                  <span className="ml-auto text-meta text-ink-muted">
                    <Ago iso={row.recorded_at} />
                  </span>
                </div>
                <p className="mt-0.5 text-desc text-ink-secondary">{row.summary}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <NoteForm ventures={ventures.map((venture) => venture.venture_id)} />
    </div>
  );
}
