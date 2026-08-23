import { describe, expect, it } from "vitest";

import {
  capacityTriple,
  compareTiers,
  controlSeverity,
  coverageLabel,
  coverageSeverity,
  gateLabel,
  gateSeverity,
  incidentSeverity,
  isHealthy,
  isRubberStamp,
  relativeAge,
  runSeverity,
  validationSummary,
} from "./severity";

/**
 * These test the one thing a UI can get wrong that matters: misrepresenting state.
 *
 * A dashboard cannot bypass a control - it can only call the API, whose write surface is
 * pinned. But it can render "never verified" in a reassuring grey, and that manufactures
 * confidence, which is worse than showing nothing at all.
 */

describe("control severity", () => {
  it("renders never_run as failing, not neutral", () => {
    // U1 - the rule of this increment. Neutral is exactly how a broken sweep survives
    // for a quarter: it reads as "nothing to report".
    expect(controlSeverity("never_run")).toBe("bad");
    expect(controlSeverity("never_run")).not.toBe("neutral");
    expect(isHealthy("never_run")).toBe(false);
  });

  it("renders stale as failing", () => {
    // U2 - a passing result from nine days ago says nothing about today.
    expect(controlSeverity("stale")).toBe("bad");
    expect(isHealthy("stale")).toBe(false);
  });

  it("renders failing as critical", () => {
    expect(controlSeverity("failing")).toBe("critical");
    expect(isHealthy("failing")).toBe(false);
  });

  it("treats only fresh as healthy", () => {
    // U4 - the green path must be reachable, or the dashboard is just an alarm.
    const states = ["fresh", "stale", "never_run", "failing"] as const;
    expect(states.filter(isHealthy)).toEqual(["fresh"]);
  });
});

describe("incident severity", () => {
  it("maps the known severities", () => {
    expect(incidentSeverity("CRITICAL")).toBe("critical");
    expect(incidentSeverity("HIGH")).toBe("bad");
    expect(incidentSeverity("MEDIUM")).toBe("warn");
  });

  it("renders an unrecognised severity loudly rather than quietly", () => {
    // Guessing "probably fine" for a value nobody anticipated is the same mistake as a
    // silent default in a verdict map.
    expect(incidentSeverity("SOMETHING_NEW")).toBe("bad");
  });
});

describe("tier comparison", () => {
  it("flags a certified tier below the declared one", () => {
    // U5 - Part 10.1. Part 17 asks for both side by side precisely because they
    // disagree, and a screen showing one would hide every place they do.
    const result = compareTiers("auto_execute", "propose");
    expect(result.capped).toBe(true);
    expect(result.effective).toBe("propose");
    expect(result.note).toContain("capped");
  });

  it("does not flag agreement", () => {
    expect(compareTiers("propose", "propose").capped).toBe(false);
    expect(compareTiers("suggest", "auto_execute").capped).toBe(false);
  });

  it("treats uncertified as not-a-tier rather than a weaker one", () => {
    const result = compareTiers("auto_execute", null);
    expect(result.capped).toBe(true);
    expect(result.effective).toBeNull();
    expect(result.note).toContain("not assignable");
  });
});

describe("relative age", () => {
  it("says never rather than showing an empty cell", () => {
    expect(relativeAge(null)).toBe("never");
    expect(relativeAge(undefined)).toBe("never");
  });

  it("formats recent and old timestamps", () => {
    expect(relativeAge(new Date(Date.now() - 30_000).toISOString())).toMatch(/s ago$/);
    expect(relativeAge(new Date(Date.now() - 7_200_000).toISOString())).toMatch(/h ago$/);
    expect(relativeAge(new Date(Date.now() - 864_000_000).toISOString())).toMatch(/d ago$/);
  });

  it("does not crash on a malformed timestamp", () => {
    expect(relativeAge("not-a-date")).toBe("unknown");
  });
});

describe("rubber-stamp threshold", () => {
  it("flags a decision faster than the threshold", () => {
    // V4 - Part 14. Naming the number on screen is what makes the control something
    // the UI cooperates with rather than something it quietly erodes.
    expect(isRubberStamp(2)).toBe(true);
    expect(isRubberStamp(4.9)).toBe(true);
  });

  it("does not flag a considered decision", () => {
    expect(isRubberStamp(5)).toBe(false);
    expect(isRubberStamp(120)).toBe(false);
  });

  it("does not flag an undecided proposal", () => {
    // A pending proposal has no review time. Treating null as "fast" would flag every
    // item in the queue before anybody touched it.
    expect(isRubberStamp(null)).toBe(false);
    expect(isRubberStamp(undefined)).toBe(false);
  });
});

describe("capacity triple", () => {
  it("returns all three numbers in a fixed order", () => {
    // V5 - one number hides the state: free alone looks like a hiring problem, add
    // allocated and it is scheduling, add uncertified and it is a SimForge backlog.
    const result = capacityTriple({
      certified_and_free: 2,
      certified_but_allocated: 9,
      produced_not_yet_certified: 14,
    });
    expect(result.map((r) => r.value)).toEqual([2, 9, 14]);
    expect(result[0].label).toContain("free");
    expect(result[1].label).toContain("allocated");
    expect(result[2].label).toContain("not yet certified");
  });

  it("refuses to render a partial set rather than quietly dropping one", () => {
    expect(() =>
      capacityTriple({ certified_and_free: 2, certified_but_allocated: 9 }),
    ).toThrow(/produced_not_yet_certified/);
  });

  it("renders zeroes rather than treating them as missing", () => {
    const result = capacityTriple({
      certified_and_free: 0,
      certified_but_allocated: 0,
      produced_not_yet_certified: 0,
    });
    expect(result.map((r) => r.value)).toEqual([0, 0, 0]);
  });
});

describe("gate verdicts", () => {
  // C11 - three verdicts, three renderings. This is the piece of presentation logic
  // that can defeat the gate it describes: awaiting_human rendered as a pass and the
  // operator stops looking; rendered as blocked and they hunt for a defect instead of
  // reading the artifacts they are being asked to review.
  it("renders awaiting_human as neither passed nor blocked", () => {
    expect(gateSeverity("passed")).toBe("ok");
    expect(gateSeverity("blocked")).toBe("bad");
    expect(gateSeverity("awaiting_human")).toBe("warn");

    const all = ["passed", "blocked", "awaiting_human"] as const;
    const severities = all.map(gateSeverity);
    expect(new Set(severities).size).toBe(3);
  });

  it("treats a gate that has not run as its own case, not as a pass", () => {
    expect(gateSeverity(null)).toBe("neutral");
    expect(gateSeverity(null)).not.toBe(gateSeverity("passed"));
    expect(gateLabel(null)).toBe("not run");
  });

  it("spells awaiting_human out rather than abbreviating it to pending", () => {
    // "Pending" reads as nearly done. This gate is not nearly done; it is stopped
    // until a named human does something.
    expect(gateLabel("awaiting_human")).toBe("awaiting a human");
    expect(gateLabel("awaiting_human")).not.toContain("pending");
  });
});

describe("run status", () => {
  it("keeps awaiting_human distinct from blocked", () => {
    expect(runSeverity("awaiting_human")).toBe("warn");
    expect(runSeverity("blocked")).toBe("bad");
    expect(runSeverity("complete")).toBe("ok");
  });

  it("renders an unrecognised status loudly rather than quietly", () => {
    // The same rule incidentSeverity follows. A new status shipped as a green tick is
    // how a state nobody anticipated gets read as success.
    expect(runSeverity("half_provisioned")).toBe("bad");
  });
});

describe("validation summary", () => {
  it("never folds NOT_RUN into a pass", () => {
    const summary = validationSummary({
      failures: [],
      warnings: ["V7"],
      not_run: ["V2"],
      rules_checked: 27,
    });
    expect(summary.severity).toBe("warn");
    expect(summary.text).toContain("1 NOT_RUN");
  });

  it("reports the denominator even when everything passed", () => {
    const summary = validationSummary({
      failures: [],
      warnings: [],
      not_run: [],
      rules_checked: 27,
    });
    expect(summary.severity).toBe("ok");
    expect(summary.text).toContain("of 27 rules");
  });

  it("is bad when anything fails, whatever else is true", () => {
    const summary = validationSummary({
      failures: ["V14"],
      warnings: [],
      not_run: [],
      rules_checked: 27,
    });
    expect(summary.severity).toBe("bad");
  });
});

describe("knowledge base coverage", () => {
  // The refinement this increment adds: two of the five stores block provisioning and
  // three do not. Rendering both gaps the same red teaches an operator that red here
  // means "eventually", which is how the one that means "now" gets skipped.
  it("distinguishes a blocking gap from an advisory one", () => {
    const gap = { covered: 3, denominator: 7 };
    expect(coverageSeverity({ ...gap, blocking: true })).toBe("bad");
    expect(coverageSeverity({ ...gap, blocking: false })).toBe("warn");
  });

  it("is ok only when the gap is actually closed", () => {
    expect(coverageSeverity({ covered: 7, denominator: 7, blocking: true })).toBe("ok");
    expect(coverageSeverity({ covered: 6, denominator: 7, blocking: true })).toBe("bad");
  });

  it("treats nothing-to-cover as neither a pass nor a failure", () => {
    // No modules registered means no instructions are owed. That is not a green tick:
    // a denominator of zero is the absence of a question, and colouring it as success
    // is how an empty system reads as a healthy one.
    expect(coverageSeverity({ covered: 0, denominator: 0, blocking: true })).toBe(
      "neutral",
    );
  });

  it("does not read a bare count as coverage", () => {
    // A store with no denominator can report twelve entries and still be missing the
    // one that matters. Non-zero is neutral, never ok.
    expect(coverageSeverity({ count: 12, blocking: false })).toBe("neutral");
    expect(coverageSeverity({ count: 12, blocking: false })).not.toBe("ok");
    expect(coverageSeverity({ count: 0, blocking: false })).toBe("warn");
    expect(coverageSeverity({ count: 0, blocking: true })).toBe("bad");
  });

  it("labels a gap with both halves of the fraction", () => {
    expect(coverageLabel({ covered: 3, denominator: 7 })).toBe("3 of 7 · 4 missing");
    expect(coverageLabel({ covered: 7, denominator: 7 })).toBe("7 of 7");
    expect(coverageLabel({ count: 1 })).toBe("1 entry");
    expect(coverageLabel({ count: 0 })).toBe("0 entries");
  });
});
