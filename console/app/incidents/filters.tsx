"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { FILTER_KEYS } from "@/lib/incidents";

/**
 * Filters for the incident list.
 *
 * The empty state said "Nothing matches", which implies a filter, and there was none —
 * so an empty list read as "your filter excluded everything" when it meant "there are
 * none". Two opposite readings of the same screen.
 *
 * The fix is either to stop claiming a filter or to build one. A log nobody can narrow
 * is unusable at the point it matters, so: filters, and an empty state that says which
 * of the two it is.
 */

export type FilterState = {
  severity?: string;
  kind?: string;
  venture_id?: string;
  state?: string;
  since?: string;
};

export function IncidentFilters({
  severities,
  kinds,
  ventures,
  shown,
  total,
}: {
  severities: { value: string; display: string }[];
  kinds: { kind: string; label: string }[];
  ventures: string[];
  shown: number;
  total: number;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const active = FILTER_KEYS.filter((key) => params.get(key));

  function set(key: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    // Paging is invalidated by any filter change: page 3 of a narrower result set is
    // usually empty, and an empty page reads as an empty log.
    next.delete("offset");
    router.push(`${pathname}?${next.toString()}`);
  }

  const select =
    "mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink";

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-meta text-ink-muted">
          Severity
          <select
            className={select}
            value={params.get("severity") ?? ""}
            onChange={(event) => set("severity", event.target.value)}
          >
            <option value="">Any</option>
            {severities.map((severity) => (
              <option key={severity.value} value={severity.value}>
                {severity.display}
              </option>
            ))}
          </select>
        </label>

        <label className="text-meta text-ink-muted">
          Kind
          <select
            className={select}
            value={params.get("kind") ?? ""}
            onChange={(event) => set("kind", event.target.value)}
          >
            <option value="">Any</option>
            {kinds.map((kind) => (
              <option key={kind.kind} value={kind.kind}>
                {kind.label}
              </option>
            ))}
          </select>
        </label>

        <label className="text-meta text-ink-muted">
          Venture
          <select
            className={select}
            value={params.get("venture_id") ?? ""}
            onChange={(event) => set("venture_id", event.target.value)}
          >
            <option value="">Any</option>
            {ventures.map((venture) => (
              <option key={venture} value={venture}>
                {venture}
              </option>
            ))}
          </select>
        </label>

        <label className="text-meta text-ink-muted">
          State
          <select
            className={select}
            value={params.get("state") ?? ""}
            onChange={(event) => set("state", event.target.value)}
          >
            <option value="">Open only</option>
            <option value="all">Open and resolved</option>
            <option value="resolved">Resolved only</option>
          </select>
        </label>

        <label className="text-meta text-ink-muted">
          Raised since
          <input
            type="date"
            className={select}
            value={params.get("since") ?? ""}
            onChange={(event) => set("since", event.target.value)}
          />
        </label>

        {active.length > 0 ? (
          <button
            type="button"
            onClick={() => router.push(pathname)}
            className="pb-1.5 text-meta text-ink-muted underline underline-offset-2"
          >
            Clear {active.length} filter{active.length === 1 ? "" : "s"}
          </button>
        ) : null}

        <span className="ml-auto pb-1.5 text-meta text-ink-muted">
          {shown} of {total}
        </span>
      </div>
    </section>
  );
}
