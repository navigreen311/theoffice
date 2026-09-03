"use client";

import { useRouter, useSearchParams } from "next/navigation";
import type { DepartmentOption } from "@/lib/api";


/**
 * Search and filter the roster.
 *
 * Driven through the URL rather than component state, so a filtered roster is a link:
 * "the four agents in Finance with no identity" is a thing somebody needs to send to
 * somebody else, and a filter held in memory cannot be sent anywhere.
 */
export function Filters({
  departments,
  current,
}: {
  departments: DepartmentOption[];
  current: { search: string; department: string; identity: string; grants: string };
}) {
  const router = useRouter();
  const params = useSearchParams();

  function set(key: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.push(next.size ? `/agents?${next.toString()}` : "/agents");
  }

  const field =
    "rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink";
  const active =
    current.search || current.department || current.identity || current.grants;

  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-meta text-ink-muted">
        Search by name
        <input
          defaultValue={current.search}
          onBlur={(event) => set("search", event.target.value.trim())}
          onKeyDown={(event) => {
            if (event.key === "Enter") set("search", event.currentTarget.value.trim());
          }}
          placeholder="Ada"
          className={`mt-1 block w-48 ${field}`}
        />
      </label>

      <label className="text-meta text-ink-muted">
        Department
        <select
          value={current.department}
          onChange={(event) => set("department", event.target.value)}
          className={`mt-1 block w-64 ${field}`}
        >
          <option value="">All {departments.length}</option>
          {departments.map((option) => (
            <option key={option.department} value={option.department}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="text-meta text-ink-muted">
        Office identity
        <select
          value={current.identity}
          onChange={(event) => set("identity", event.target.value)}
          className={`mt-1 block ${field}`}
        >
          <option value="">Any</option>
          <option value="with">Has an identity</option>
          <option value="without">No identity</option>
        </select>
      </label>

      <label className="text-meta text-ink-muted">
        Grants
        <select
          value={current.grants}
          onChange={(event) => set("grants", event.target.value)}
          className={`mt-1 block ${field}`}
        >
          <option value="">Any</option>
          <option value="with">Holds a grant</option>
          <option value="without">Holds none</option>
          {/* The state the page exists to explain, as a filter. */}
          <option value="certified_no_grants">Certified, no grants</option>
        </select>
      </label>

      {active ? (
        <button
          type="button"
          onClick={() => router.push("/agents")}
          className="pb-1.5 text-meta text-ink-muted underline underline-offset-2 hover:text-ink"
        >
          Clear filters
        </button>
      ) : null}
    </div>
  );
}
