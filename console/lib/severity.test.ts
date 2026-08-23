import { describe, expect, it } from "vitest";

import {
  compareTiers,
  controlSeverity,
  incidentSeverity,
  isHealthy,
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
