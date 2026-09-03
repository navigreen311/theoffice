import Link from "next/link";

import { AlertTriangle, CircleCheck } from "@/components/icons";

/**
 * Control freshness, stated as the fact it is.
 *
 * The page used to say "an empty list is only good news if the checks that raise these
 * are fresh — see the compliance dashboard", and then showed an empty list. The reader
 * was told the question mattered and sent somewhere else for the answer, which the page
 * could compute. A screen that knows and defers is not being careful, it is passing the
 * work back.
 *
 * The wording follows what is true rather than a sentence written in advance. The brief
 * for this rebuild asserted that all four controls had never run; three of them had run
 * by the time it was built. Naming four controls as never-run when one is would have
 * been a false alarm, and a false alarm on this banner costs exactly the attention the
 * banner exists to buy.
 */

type Freshness = {
  state: "never_run" | "fresh" | "stale" | "failing";
  healthy: boolean;
  max_age_days: number;
  age_hours?: number;
  last_run?: string;
  detail?: string;
};

export type Controls = {
  freshness: Record<string, Freshness>;
  stale: string[];
  never_ran: string[];
  all_fresh: boolean;
  total: number;
};

function list(names: string[]): string {
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export function ControlFreshness({ controls }: { controls: Controls }) {
  const { freshness, stale, never_ran: never, all_fresh: fresh, total } = controls;
  const notFresh = stale.length;
  const ran = never.filter((k) => k in freshness);

  // Every control never run is the case the original copy was written for, so it keeps
  // that wording exactly. Anything else gets a sentence describing what is actually true.
  let statement: string;
  if (fresh) {
    statement = `All ${total === 4 ? "four" : total} detection controls verified within their max age`;
  } else if (ran.length === total) {
    statement =
      `The checks that raise incidents have never run. ${never.join(", ")} have no ` +
      "results. An empty incident list reflects checks that did not run, not a quiet " +
      "system.";
  } else if (ran.length > 0 && notFresh === ran.length) {
    statement =
      `${list(ran)} ${ran.length === 1 ? "has" : "have"} never run. An empty ` +
      "incident list reflects a check that did not run, not a quiet system.";
  } else {
    const overdue = stale.filter((k) => !never.includes(k));
    const parts = [];
    if (ran.length) parts.push(`${list(ran)} ${ran.length === 1 ? "has" : "have"} never run`);
    if (overdue.length)
      parts.push(`${list(overdue)} ${overdue.length === 1 ? "is" : "are"} past its max age`);
    statement =
      `${parts.join("; ")}. An empty incident list reflects checks that did not run, ` +
      "not a quiet system.";
  }

  return (
    <section
      className={`rounded-xl border px-5 py-4 ${
        fresh
          ? "border-ok-line bg-ok-bg"
          : "border-bad-line bg-bad-bg"
      }`}
    >
      <h2
        className={`flex items-center gap-1.5 text-section font-medium ${
          fresh ? "text-ok" : "text-bad"
        }`}
      >
        {fresh ? (
          <CircleCheck className="h-4 w-4" />
        ) : (
          <AlertTriangle className="h-4 w-4" />
        )}
        {statement}
      </h2>

      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {Object.entries(freshness).map(([name, state]) => (
          <li
            key={name}
            className="flex items-baseline justify-between gap-3 rounded-lg border border-line bg-surface px-3 py-2"
          >
            <code className="text-ident text-ink">{name}</code>
            <span
              className={`text-meta ${
                state.healthy ? "text-ink-secondary" : "text-bad"
              }`}
            >
              {state.state === "never_run"
                ? "never run"
                : state.state === "fresh"
                  ? `verified ${Math.round(state.age_hours ?? 0)}h ago`
                  : state.state === "stale"
                    ? `last run ${Math.round((state.age_hours ?? 0) / 24)}d ago, max ${state.max_age_days}d`
                    : "failing"}
            </span>
          </li>
        ))}
      </ul>

      <p className="mt-3 text-meta text-ink-muted">
        An empty list is only good news if the checks that raise these are fresh — see the{" "}
        {/* The dashboard is the compliance dashboard: `/api/compliance` renders there.
            This linked to `/compliance`, which does not exist - Next prefetches a Link,
            so the 404 arrived on page load rather than on a click, and the only place it
            showed was the browser console. */}
        <Link href="/" className="underline underline-offset-2">
          compliance dashboard
        </Link>
        .
      </p>
    </section>
  );
}
