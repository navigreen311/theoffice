import { redirect } from "next/navigation";

import { AsOf } from "@/components/local-time";
import { api, ApiError, NotAuthenticated, type VentureRow } from "@/lib/api";

import { ChainIntegrity, type ChainState } from "./chain";
import { AuditLog, type Detail, type Entry } from "./log";

export const dynamic = "force-dynamic";

/**
 * Audit — the evidence every other page leans on.
 *
 * Chain integrity stays above the log. That ordering was already right and is unchanged:
 * entries below are meaningless if this is broken, so it is read first.
 *
 * What was wrong was the claim above it. "Chain integrity verified over 1,157 entries"
 * came from a check run on page load and recorded nowhere, while Compliance read the last
 * recorded control result — 73 entries, from the previous day. Two screens, one property,
 * both truthful, and they disagreed. The page now reports the recorded verification, so
 * they cannot: it is the same row.
 */

type Glossary = { events: { event_type: string; label: string; meaning: string; written_by: string; family: string }[] };
type Page = {
  as_of: string;
  rows: Entry[];
  total: number;
  page: number;
  pages: number;
  excluded_fixtures: number;
};
type Shape = {
  counted: number;
  fixtures_excluded: number;
  by_event_type: { value: string; label: string | null; count: number }[];
  by_actor: { value: string; count: number }[];
  by_venture: { value: string; count: number }[];
};

const FILTERS = [
  "event_type",
  "venture_id",
  "trace_id",
  "actor_id",
  "since",
  "until",
  "include_fixtures",
] as const;

function Tally({
  title,
  rows,
}: {
  title: string;
  rows: { value: string; label?: string | null; count: number }[];
}) {
  const top = rows.slice(0, 8);
  return (
    <div>
      <h3 className="text-desc font-medium text-ink">{title}</h3>
      <ul className="mt-1">
        {top.map((row) => (
          <li
            key={row.value}
            className="flex items-baseline justify-between gap-3 border-t border-line py-1 first:border-t-0"
          >
            <span className="text-meta text-ink-secondary">{row.label ?? row.value}</span>
            <span className="font-mono text-meta text-ink">{row.count}</span>
          </li>
        ))}
        {rows.length > top.length ? (
          <li className="pt-1 text-meta text-ink-muted">
            and {rows.length - top.length} more
          </li>
        ) : null}
        {rows.length === 0 ? (
          <li className="py-1 text-meta text-ink-muted">nothing in range</li>
        ) : null}
      </ul>
    </div>
  );
}

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Record<string, string | undefined>;
}) {
  const query = new URLSearchParams();
  for (const key of FILTERS) {
    if (searchParams[key]) query.set(key, searchParams[key] as string);
  }
  if (searchParams.page) query.set("page", searchParams.page);

  // Only the parameters that have a value. An empty string is not an absent parameter:
  // FastAPI refuses `include_fixtures=` with a 422 because "" is not a boolean, which
  // took the whole page down with a 500.
  const shapeQuery = new URLSearchParams();
  for (const key of ["include_fixtures", "since", "until"] as const) {
    if (searchParams[key]) shapeQuery.set(key, searchParams[key] as string);
  }

  let chain: { recorded_verification: ChainState };
  let entries: Page;
  let glossary: Glossary;
  let shape: Shape;
  let ventures: VentureRow[];
  try {
    [chain, entries, glossary, shape, ventures] = await Promise.all([
      api.get<{ recorded_verification: ChainState }>("/api/audit/chain"),
      api.get<Page>(`/api/audit/entries?${query}`),
      api.get<Glossary>("/api/audit/events"),
      api.get<Shape>(`/api/audit/shape?${shapeQuery}`),
      api.get<VentureRow[]>("/api/ventures"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  // The expanded entry, read server-side. The browser never talks to the API.
  let detail: Detail | null = null;
  if (searchParams.expand) {
    try {
      detail = await api.get<Detail>(`/api/audit/${searchParams.expand}`);
    } catch (error) {
      if (error instanceof NotAuthenticated) redirect("/login");
      if (!(error instanceof ApiError && error.status === 404)) throw error;
    }
  }

  // Actors present in the log, so "what did Dana do" is answerable without knowing a
  // UUID. Built from the rows rather than from the roster: an account that has never
  // acted is not a useful filter option, and one that has been removed still needs to be.
  const actors = [
    ...new Map(
      entries.rows
        .filter((row) => row.actor_id && row.actor_name)
        .map((row) => [row.actor_id as string, row.actor_name as string]),
    ),
  ].map(([id, name]) => ({ id, name }));

  const exportQuery = new URLSearchParams(query);

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-page font-medium text-ink">Audit</h1>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            Every action in this console is written here before anything else happens.
          </p>
        </div>
        <AsOf iso={entries.as_of} />
      </div>

      <ChainIntegrity chain={chain.recorded_verification} />

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-section font-medium text-ink">Shape</h2>
          <span className="text-meta text-ink-muted">
            {shape.counted} entries in range
            {shape.fixtures_excluded > 0
              ? ` · ${shape.fixtures_excluded} fixtures excluded`
              : ""}
          </span>
        </div>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Counts before paging. A spike in one event type is the kind of thing that only
          shows up in aggregate.
        </p>
        <div className="mt-3 grid gap-6 sm:grid-cols-3">
          <Tally title="By event type" rows={shape.by_event_type} />
          <Tally title="By actor" rows={shape.by_actor} />
          <Tally title="By venture" rows={shape.by_venture} />
        </div>
      </section>

      <AuditLog
        rows={entries.rows}
        total={entries.total}
        page={entries.page}
        pages={entries.pages}
        excludedFixtures={entries.excluded_fixtures}
        eventTypes={glossary.events}
        actors={actors}
        ventures={ventures.map((venture) => venture.venture_id)}
        truncated={entries.pages > 1}
        detail={detail}
      />

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Export</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Part 9 requires structured record export on demand. The export carries the
          filters that produced it, whether fixtures were included, and the chain
          verification state at the time — an export that does not say those things looks
          like evidence and is not.
        </p>
        <a
          href={`/api/audit/export?${exportQuery}`}
          className="mt-3 inline-block rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
        >
          Export these {entries.total} entries
        </a>
        <p className="mt-2 text-meta text-ink-muted">
          {searchParams.include_fixtures === "true"
            ? "Fixtures are included in this export and it will say so."
            : `Fixtures are excluded and the export will say so — ${entries.excluded_fixtures} entries.`}
        </p>
      </section>

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">What each event means</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Event names reached this page as raw identifiers with no glossary anywhere, and
          the filter asked you to type one — usable only by somebody who already knew the
          answer.
        </p>
        <ul className="mt-3">
          {glossary.events.map((event) => (
            <li key={event.event_type} className="border-t border-line py-2 first:border-t-0">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="text-desc font-medium text-ink">{event.label}</span>
                <code className="text-ident text-ink-muted">{event.event_type}</code>
                <span className="ml-auto font-mono text-ident text-ink-muted">
                  {event.written_by}
                </span>
              </div>
              <p className="mt-0.5 max-w-3xl text-meta text-ink-secondary">
                {event.meaning}
              </p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
