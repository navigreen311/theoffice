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

/**
 * Part 14's rubber-stamp threshold, surfaced in the UI rather than only enforced
 * after the fact.
 *
 * The API raises a MEDIUM incident when an approval lands in under five seconds. A
 * screen that shows a one-click Approve next to a collapsed payload will generate those
 * incidents by design — it bypasses nothing, and produces exactly the outcome the
 * control exists to prevent.
 *
 * Naming the number on screen is not enforcement. It is the difference between a screen
 * that cooperates with a control and one that quietly erodes it.
 */
export const RUBBER_STAMP_SECONDS = 5;

/** Whether a decision was fast enough to be flagged as a rubber stamp. */
export function isRubberStamp(reviewSeconds: number | null | undefined): boolean {
  return reviewSeconds !== null && reviewSeconds !== undefined
    ? reviewSeconds < RUBBER_STAMP_SECONDS
    : false;
}

/**
 * The three capacity numbers (§7.2). Refuses to render a partial set.
 *
 * "One number hides the state": free alone looks like a hiring problem, add allocated
 * and it is a scheduling problem, add uncertified and it is a SimForge backlog. A helper
 * that quietly dropped a missing field would reintroduce exactly that.
 */
export function capacityTriple(input: {
  certified_and_free?: number;
  certified_but_allocated?: number;
  produced_not_yet_certified?: number;
}): { label: string; value: number }[] {
  const keys = [
    ["certified_and_free", "Certified and free"],
    ["certified_but_allocated", "Certified, allocated elsewhere"],
    ["produced_not_yet_certified", "Produced, not yet certified"],
  ] as const;

  return keys.map(([key, label]) => {
    const value = input[key];
    if (typeof value !== "number") {
      throw new Error(
        `capacity is missing ${key}; all three numbers are reported together because one hides the state`,
      );
    }
    return { label, value };
  });
}

/**
 * Gate verdicts. **Three, never two.**
 *
 * `awaiting_human` is neither a pass nor a failure, and a UI that renders it as either
 * defeats the gate it is describing. Rendered as a pass, the operator stops looking.
 * Rendered as blocked, they go hunting for a defect instead of reading the artifacts
 * they are being asked to review.
 *
 * `null` — a gate that has not run — is its own case for the same reason `NOT_RUN` is
 * everywhere else in this system: it is not a pass, and it is not a failure either.
 */
export type GateVerdict = "passed" | "blocked" | "awaiting_human" | null;

export function gateSeverity(verdict: GateVerdict): Severity {
  switch (verdict) {
    case "passed":
      return "ok";
    case "blocked":
      return "bad";
    case "awaiting_human":
      return "warn";
    default:
      return "neutral";
  }
}

/** The word on screen. Never abbreviated to "pending", which reads as "nearly done". */
export function gateLabel(verdict: GateVerdict): string {
  switch (verdict) {
    case "passed":
      return "passed";
    case "blocked":
      return "blocked";
    case "awaiting_human":
      return "awaiting a human";
    default:
      return "not run";
  }
}

/** Run status → severity. `awaiting_human` is again distinct from `blocked`. */
export function runSeverity(status: string): Severity {
  switch (status) {
    case "complete":
      return "ok";
    case "running":
      return "neutral";
    case "awaiting_human":
      return "warn";
    case "blocked":
      return "bad";
    case "aborted":
      return "neutral";
    default:
      // An unrecognised status is loud, not quiet — the same rule incidentSeverity
      // follows. Guessing "probably fine" for a value nobody anticipated is how a new
      // state ships rendered as a success.
      return "bad";
  }
}

/**
 * What a validator report says, without collapsing the three outcomes.
 *
 * NOT_RUN is deliberately not folded into "fine". A Pack whose bridge check could not
 * run has not been validated, and an editor that renders it as a green tick teaches the
 * operator to read it that way.
 */
export function validationSummary(report: {
  failures: string[];
  warnings: string[];
  not_run: string[];
  rules_checked: number;
}): { severity: Severity; text: string } {
  const { failures, warnings, not_run, rules_checked } = report;
  const parts = [
    `${failures.length} FAIL`,
    `${warnings.length} WARN`,
    `${not_run.length} NOT_RUN`,
    `of ${rules_checked} rules`,
  ];
  const severity: Severity =
    failures.length > 0 ? "bad" : not_run.length > 0 ? "warn" : "ok";
  return { severity, text: parts.join(", ") };
}
