/**
 * The incident taxonomy as the console sees it.
 *
 * The values themselves come from `/api/incidents/taxonomy`, which reads
 * `broker/incident_taxonomy.py`. Nothing here re-declares a severity or a kind: a screen
 * holding its own copy of an enumeration is one that disagrees with the database the
 * first time a value is added, and the disagreement shows up as a row rendering blank.
 *
 * What lives here is presentation — the colour a severity carries and how an age reads
 * against its marker — which is the console's business and nobody else's.
 */

export type Taxonomy = {
  severities: { value: string; display: string; tone: string; sla_hours: number }[];
  kinds: {
    kind: string;
    label: string;
    source: string;
    meaning: string;
    raised_by: string;
    aliases: string[];
  }[];
  detection_sources: string[];
  stages: { stage: string; label: string; hint: string }[];
};

/**
 * Severity colour. `low` is deliberately neutral: a log where every row is coloured is
 * one where no row stands out, which costs exactly the attention colour is spent to buy.
 */
export function severityTone(severity: string): string {
  switch (severity.toUpperCase()) {
    case "CRITICAL":
      return "border-critical-line bg-critical-bg text-critical";
    case "HIGH":
      return "border-bad-line bg-bad-bg text-bad";
    case "MEDIUM":
      return "border-warn-line bg-warn-bg text-warn";
    default:
      return "border-line bg-surface-muted text-ink-secondary";
  }
}

/**
 * How long this has been open, against the marker for its severity.
 *
 * The markers are the console's own and the copy says so. Nothing in the blueprint fixes
 * a response time, and presenting an invented number as an external obligation would be
 * worse than showing no marker: it would be a rule nobody agreed to, enforced by a
 * colour.
 */
export function ageAgainstSla(
  raisedAt: string,
  severity: string,
  taxonomy: Taxonomy,
  resolved: boolean,
  now: number | null,
): { label: string; overdue: boolean; hours: number } {
  // `now` is required and nullable on purpose. It has no default, because a default of
  // `Date.now()` would let a server component call this during SSR, render an age, and
  // then disagree with the browser a moment later - the hydration failure this console
  // has already shipped twice. The clock is read in one place, `useNow`, which returns
  // null until the component has mounted.
  if (now === null) return { label: "", overdue: false, hours: 0 };

  const hours = (now - new Date(raisedAt).getTime()) / 3_600_000;
  const target = taxonomy.severities.find(
    (s) => s.value.toUpperCase() === severity.toUpperCase(),
  );

  if (resolved || !target) {
    return { label: "", overdue: false, hours };
  }

  const overdue = hours > target.sla_hours;
  const rounded = hours < 48 ? `${Math.round(hours)}h` : `${Math.round(hours / 24)}d`;
  return {
    label: overdue
      ? `open ${rounded} — past the ${target.sla_hours}h console marker for ${target.display}`
      : `open ${rounded} of ${target.sla_hours}h`,
    overdue,
    hours,
  };
}

/**
 * The query parameters the incident list filters on.
 *
 * Here rather than beside the filter component, which is a client module. A server
 * component that imports a plain value from a `"use client"` file gets a proxy, and
 * iterating that proxy fails with "Cannot read Symbol exports. Only named exports are
 * supported on a client module imported on the server" - a server-render error, not a
 * type error, so `tsc` and `next build` both pass and the page 500s on first request.
 *
 * Components cross that boundary. Values do not.
 */
export const FILTER_KEYS = [
  "severity",
  "kind",
  "venture_id",
  "state",
  "since",
] as const;

export type FilterKey = (typeof FILTER_KEYS)[number];
