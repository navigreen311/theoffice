import { describe, expect, it } from "vitest";

import {
  capacityTriple,
  compareTiers,
  controlSeverity,
  incidentSeverity,
  isHealthy,
  isRubberStamp,
  relativeAge,
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
