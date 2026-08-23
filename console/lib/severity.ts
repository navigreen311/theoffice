/**
 * Severity mapping — the one piece of presentation logic that can lie.
 *
 * Increment 1's risk was an API that bypasses a control. A UI cannot bypass a control;
 * it can only call the API, whose write surface is pinned by a test.
 *
 * **A UI's risk is different: it can misrepresent state.** A dashboard that renders a
 * sweep which has never run as a reassuring grey, or shows "0 incidents" without saying
 * the check that produces them is stale, is worse than no dashboard. It manufactures
 * confidence.
 *
 * So this lives in a tested pure function rather than as a Tailwind class chosen inline
 * in a component nobody will read again.
 */

export type Severity = "ok" | "warn" | "bad" | "critical" | "neutral";

/** Control states as reported by `GET /api/health`. */
export type ControlState = "fresh" | "stale" | "never_run" | "failing";

/**
 * The rule of this increment: **anything not verifiably healthy renders as
 * not-healthy.**
 *
 * `never_run` is `bad`, not `neutral`. An absence of findings from a check that did not
 * run is not evidence, and the neutral colour is exactly how a broken sweep survives for
 * a quarter — it reads as "nothing to report".
 *
 * `stale` is `bad` for the same reason: a passing result from nine days ago says nothing
 * about today.
 */
export function controlSeverity(state: ControlState): Severity {
  switch (state) {
    case "fresh":
      return "ok";
    case "stale":
    case "never_run":
      return "bad";
    case "failing":
      return "critical";
  }
}

/** Whether a control counts toward "everything is fine". Only `fresh` does. */
export function isHealthy(state: ControlState): boolean {
  return controlSeverity(state) === "ok";
}

export function incidentSeverity(severity: string): Severity {
  switch (severity.toUpperCase()) {
    case "CRITICAL":
      return "critical";
    case "HIGH":
      return "bad";
    case "MEDIUM":
      return "warn";
    case "LOW":
      return "ok";
    default:
      // An unrecognised severity is loud, not quiet. Guessing "probably fine" for a
      // value nobody anticipated is the same mistake as a silent default in a verdict
      // map.
      return "bad";
  }
}

const TIER_RANK: Record<string, number> = {
  suggest: 1,
  propose: 2,
  auto_execute: 3,
};

export type TierComparison = {
  capped: boolean;
  effective: string | null;
  note: string;
};

/**
 * Certified tier against declared tier (Part 10.1: "the Pack declares a ceiling;
 * SimForge sets the actual").
 *
 * Part 17 asks for both side by side precisely because they disagree, and a screen
 * showing only one would hide every place they do.
 */
export function compareTiers(
  declared: string | null,
  certified: string | null,
): TierComparison {
  if (!declared) {
    return { capped: false, effective: certified, note: "no grant" };
  }
  if (!certified) {
    // Uncertified is not a weaker tier; it is not a tier. The agent cannot act at all.
    return {
      capped: true,
      effective: null,
      note: "uncertified — not assignable",
    };
  }
  const d = TIER_RANK[declared] ?? 0;
  const c = TIER_RANK[certified] ?? 0;
  if (c < d) {
    return {
      capped: true,
      effective: certified,
      note: `capped: declared ${declared}, certified ${certified}`,
    };
  }
  return { capped: false, effective: declared, note: "" };
}

/** Human-readable age. Returns "never" for null rather than an empty cell. */
export function relativeAge(iso: string | null | undefined): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 90) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 90) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export const SEVERITY_CLASS: Record<Severity, string> = {
  ok: "bg-ok/10 text-ok border-ok/30",
  warn: "bg-warn/10 text-warn border-warn/30",
  bad: "bg-bad/10 text-bad border-bad/40",
  critical: "bg-critical/15 text-critical border-critical/50 font-semibold",
  neutral: "bg-neutral-100 text-neutral-600 border-neutral-300",
};
