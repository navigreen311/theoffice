"use client";

import { useNow } from "@/components/local-time";
import { ageAgainstSla, type Taxonomy } from "@/lib/incidents";

/**
 * How long an incident has been open, against the marker for its severity.
 *
 * A client component because it reads the clock, and the clock is read in exactly one
 * place in this console. Computing an age during SSR renders a number the browser
 * disagrees with a moment later, and React responds by discarding the tree — which
 * reaches the reader as "Application error: a client-side exception has occurred".
 *
 * `useNow` returns null until mounted, so the server renders nothing here and the
 * browser fills it in. An age that appears a frame late is not a defect; an age that
 * takes the page down is.
 */
export function SlaAge({
  raisedAt,
  severity,
  taxonomy,
  resolved,
}: {
  raisedAt: string;
  severity: string;
  taxonomy: Taxonomy;
  resolved: boolean;
}) {
  const now = useNow();
  const sla = ageAgainstSla(raisedAt, severity, taxonomy, resolved, now);

  if (!sla.label) return null;
  return (
    <span className={`text-meta ${sla.overdue ? "text-bad" : "text-ink-muted"}`}>
      {sla.label}
    </span>
  );
}
