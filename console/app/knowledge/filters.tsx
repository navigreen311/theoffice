"use client";

import { useRouter, useSearchParams } from "next/navigation";

/**
 * Search, filter and paging, driven through the URL.
 *
 * A filtered view is a link — "the sixty test personas" is a thing somebody sends to
 * somebody else — and a filter held in component state cannot be sent anywhere.
 *
 * `include_fixtures` is off by default and says so when it is hiding something. A list
 * that silently drops 120 of 132 rows and reports the remaining 12 as the total is the
 * same failure as counting the fixtures as content.
 */

const field = "rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink";

export function KnowledgeFilters({
  basePath,
  searchLabel,
  ventures,
  extra,
  excludedFixtures,
  total,
  page,
  pages,
}: {
  basePath: string;
  searchLabel: string;
  ventures?: string[];
  extra?: { name: string; label: string; options: string[] };
  excludedFixtures: number;
  total: number;
  page: number;
  pages: number;
}) {
  const router = useRouter();
  const params = useSearchParams();

  function set(key: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    // Any filter change invalidates the page number: page 3 of a narrower result set is
    // usually empty, which reads as "nothing matched".
    if (key !== "page") next.delete("page");
    router.push(next.size ? `${basePath}?${next.toString()}` : basePath);
  }

  const includeFixtures = params.get("include_fixtures") === "true";

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-meta text-ink-muted">
          {searchLabel}
          <input
            defaultValue={params.get("search") ?? ""}
            onBlur={(event) => set("search", event.target.value.trim())}
            onKeyDown={(event) => {
              if (event.key === "Enter") set("search", event.currentTarget.value.trim());
            }}
            className={`mt-1 block w-56 ${field}`}
          />
        </label>

        {ventures?.length ? (
          <label className="text-meta text-ink-muted">
            Venture
            <select
              value={params.get("venture_id") ?? ""}
              onChange={(event) => set("venture_id", event.target.value)}
              className={`mt-1 block ${field}`}
            >
              <option value="">All</option>
              {ventures.map((venture) => (
                <option key={venture} value={venture}>
                  {venture}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {extra ? (
          <label className="text-meta text-ink-muted">
            {extra.label}
            <select
              value={params.get(extra.name) ?? ""}
              onChange={(event) => set(extra.name, event.target.value)}
              className={`mt-1 block ${field}`}
            >
              <option value="">Any</option>
              {extra.options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <label className="text-meta text-ink-muted">
          Origin
          <select
            value={params.get("origin") ?? ""}
            onChange={(event) => set("origin", event.target.value)}
            className={`mt-1 block ${field}`}
          >
            <option value="">Any</option>
            <option value="authored">Authored</option>
            <option value="system">System</option>
            <option value="test_fixture">Test fixture</option>
          </select>
        </label>

        <label className="flex items-center gap-1.5 pb-1.5 text-meta text-ink-muted">
          <input
            type="checkbox"
            checked={includeFixtures}
            onChange={(event) =>
              set("include_fixtures", event.target.checked ? "true" : "")
            }
          />
          Include test fixtures
        </label>
      </div>

      <p className="text-meta text-ink-muted">
        {total} row{total === 1 ? "" : "s"}
        {pages > 1 ? ` · page ${page} of ${pages}` : ""}
        {excludedFixtures > 0
          ? ` · ${excludedFixtures} test fixture${excludedFixtures === 1 ? "" : "s"} excluded from this view`
          : ""}
      </p>

      {pages > 1 ? (
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => set("page", String(page - 1))}
            className="rounded-lg border border-line px-2.5 py-1 text-meta text-ink transition hover:bg-surface-muted disabled:opacity-40"
          >
            Previous
          </button>
          <button
            type="button"
            disabled={page >= pages}
            onClick={() => set("page", String(page + 1))}
            className="rounded-lg border border-line px-2.5 py-1 text-meta text-ink transition hover:bg-surface-muted disabled:opacity-40"
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
}
