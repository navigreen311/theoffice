import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { assess, assessSection, SECTION_ORDER } from "./curriculum";

/**
 * The same cases the Python suite reads.
 *
 * These rules exist twice: `broker/curriculum_quality.py` refuses a publish and fails
 * V11, this file greys out the Publish button as somebody types. Two implementations of
 * one rule drift, and the drift here is worse than usual - the form would say a section
 * is fine and the server would reject the save, or the form would say it is a stub and
 * the server would take it.
 *
 * So neither side owns the cases. A rule added to one implementation without the other
 * fails on the side that was not updated.
 */
const cases = JSON.parse(
  readFileSync(
    join(__dirname, "..", "..", "tests", "fixtures", "curriculum_cases.json"),
    "utf-8",
  ),
) as { cases: { name: string; section: string; value: unknown; state: string }[] };

describe("assessSection agrees with the Python rules", () => {
  it("has cases to check", () => {
    expect(cases.cases.length).toBeGreaterThan(10);
  });

  for (const testCase of cases.cases) {
    it(testCase.name, () => {
      expect(assessSection(testCase.section, testCase.value).state).toBe(
        testCase.state,
      );
    });
  }
});

describe("assess", () => {
  it("reports the live curriculum as a stub", () => {
    // The content in the database, which the page badged `authored`.
    const live = {
      what_it_does: "Documented.",
      what_it_does_not_do: "Documented.",
      inputs: { a: "b" },
      correct_sequence: ["a", "b"],
      failure_signatures: { silent_partial: "short result" },
      retry_vs_escalate: "Retry 5xx twice; escalate 4xx.",
      never_do: ["Never re-submit after a 200"],
      compliance_coupling: ["tsr_disclosure_required"],
    };
    const result = assess(live);
    expect(result.state).toBe("stub");
    expect(result.teachesNothing).toBe(true);
  });

  it("assesses every required section", () => {
    // A section nobody assesses is a section that can quietly become a placeholder.
    expect(assess({}).sections.map((s) => s.section)).toEqual([...SECTION_ORDER]);
  });

  it("reads a JSON structure typed into a textarea as that structure", () => {
    // The form holds everything as text. Without this, a real `inputs` map typed in
    // would read as one long prose blob and always pass.
    expect(assessSection("inputs", '{"a": "b"}').state).toBe("stub");
    expect(
      assessSection("correct_sequence", '["a", "b"]').state,
    ).toBe("stub");
  });
});
