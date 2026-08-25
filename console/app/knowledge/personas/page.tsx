import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { Ago } from "@/components/local-time";
import { api, NotAuthenticated } from "@/lib/api";

import { KnowledgeFilters } from "../filters";
import { PersonaWrite } from "../forms";
import { KnowledgeTabs } from "../tabs";

export const dynamic = "force-dynamic";

/**
 * The persona library.
 *
 * It reported sixty entries. All sixty are `Smoke NNNNNN`, written by console smoke runs,
 * standing in for the same broker — so the library holds zero personas and said sixty.
 * Fixtures are filtered out by default and the count says how many were left out.
 */

type Row = {
  persona_id: string;
  venture_id: string;
  persona_name: string;
  target_persona: string;
  persona_version: string;
  body_hash: string;
  authored_at: string;
  origin: string;
};

type Page = {
  rows: Row[];
  total: number;
  page: number;
  pages: number;
  excluded_fixtures: number;
};

export default async function PersonasPage({
  searchParams,
}: {
  searchParams: Record<string, string | undefined>;
}) {
  const query = new URLSearchParams();
  for (const key of ["search", "venture_id", "origin", "include_fixtures", "page"]) {
    if (searchParams[key]) query.set(key, searchParams[key] as string);
  }

  let data: Page;
  let ventures: { venture_id: string }[];
  try {
    [data, ventures] = await Promise.all([
      api.get<Page>(`/api/knowledge/personas?${query.toString()}`),
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
          { label: "Personas" },
        ]}
      />

      <div>
        <h1 className="text-page font-medium text-ink">Persona Library</h1>
        <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
          One-way. SimForge only, never production — the runtime role this console uses
          holds no read privilege on a persona body, so what you write here cannot be
          displayed again. Reviewing one is an out-of-band act on the admin connection.
        </p>
      </div>

      <KnowledgeTabs />

      <KnowledgeFilters
        basePath="/knowledge/personas"
        searchLabel="Search by name or target"
        ventures={ventures.map((venture) => venture.venture_id)}
        excludedFixtures={data.excluded_fixtures}
        total={data.total}
        page={data.page}
        pages={data.pages}
      />

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        {data.rows.length === 0 ? (
          <p className="text-desc text-ink-secondary">
            {data.excluded_fixtures > 0
              ? `No real persona. ${data.excluded_fixtures} test fixtures are excluded from this view — the library has nothing else in it.`
              : "No persona matches this filter."}
          </p>
        ) : (
          <ul>
            {data.rows.map((row) => (
              <li
                key={row.persona_id}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line py-2 first:border-t-0"
              >
                <span className="text-rowtitle font-medium text-ink">
                  {row.persona_name}
                </span>
                <span className="text-meta text-ink-muted">{row.target_persona}</span>
                <span className="text-meta text-ink-muted">{row.venture_id}</span>
                {row.origin === "test_fixture" ? (
                  <span className="rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 text-meta text-warn">
                    test fixture
                  </span>
                ) : null}
                <code className="text-ident text-ink-muted">
                  {row.body_hash.slice(0, 12)}…
                </code>
                <span className="ml-auto text-meta text-ink-muted">
                  v{row.persona_version} · <Ago iso={row.authored_at} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <PersonaWrite ventures={ventures.map((venture) => venture.venture_id)} />
    </div>
  );
}
