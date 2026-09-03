"use client";

import { useMemo, useState } from "react";

/**
 * Choose a target by name, with its id as secondary text.
 *
 * The form asked for `agent_id`, `forge_id`, `module_id` and `venture_id` as free text.
 * This is the emergency control: recalling a UUID under pressure is not something anybody
 * does, and a typo has two outcomes — it fails, or it stops something else. The second is
 * the reason this is a picker and not a validated text field.
 *
 * The id is still shown, because the id is what appears in the audit entry and in every
 * export, and somebody checking afterwards needs to recognise it.
 */

export type Option = { id: string; name: string | null; detail?: string | null };

export function Picker({
  label,
  options,
  value,
  onChange,
  empty,
}: {
  label: string;
  options: Option[];
  value: string;
  onChange: (id: string) => void;
  empty?: string;
}) {
  const [query, setQuery] = useState("");

  const matches = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return options;
    return options.filter(
      (option) =>
        (option.name ?? "").toLowerCase().includes(term) ||
        option.id.toLowerCase().includes(term) ||
        (option.detail ?? "").toLowerCase().includes(term),
    );
  }, [options, query]);

  const selected = options.find((option) => option.id === value);

  return (
    <div className="text-meta text-ink-muted">
      <span>{label}</span>

      {selected ? (
        <div className="mt-1 flex items-baseline gap-2 rounded-lg border border-line bg-surface-muted px-2 py-1.5">
          <span className="text-desc text-ink">{selected.name ?? selected.id}</span>
          <code className="text-ident text-ink-muted">{selected.id}</code>
          <button
            type="button"
            onClick={() => {
              onChange("");
              setQuery("");
            }}
            className="ml-auto text-meta text-ink-muted underline underline-offset-2"
          >
            Change
          </button>
        </div>
      ) : (
        <>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={`Search ${label.toLowerCase()}…`}
            className="mt-1 block w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
          />
          <ul className="mt-1 max-h-44 overflow-y-auto rounded-lg border border-line">
            {matches.map((option) => (
              <li key={option.id}>
                <button
                  type="button"
                  onClick={() => onChange(option.id)}
                  className="flex w-full flex-wrap items-baseline gap-2 border-b border-line px-2 py-1.5 text-left transition last:border-b-0 hover:bg-surface-muted"
                >
                  <span className="text-desc text-ink">{option.name ?? option.id}</span>
                  {option.detail ? (
                    <span className="text-meta text-ink-muted">{option.detail}</span>
                  ) : null}
                  <code className="ml-auto text-ident text-ink-muted">{option.id}</code>
                </button>
              </li>
            ))}
            {matches.length === 0 ? (
              <li className="px-2 py-1.5 text-meta text-ink-muted">
                {options.length === 0
                  ? (empty ?? `No ${label.toLowerCase()} exists yet.`)
                  : `Nothing matches "${query}".`}
              </li>
            ) : null}
          </ul>
        </>
      )}
    </div>
  );
}
