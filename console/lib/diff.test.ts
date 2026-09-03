import { describe, expect, it } from "vitest";

import { diffLines, summarise, withContext } from "./diff";

describe("diffLines", () => {
  it("reports nothing for identical text", () => {
    const text = "a\nb\nc";
    expect(diffLines(text, text).every((line) => line.kind === "same")).toBe(true);
  });

  it("keeps line numbers on both sides so an error can cite one", () => {
    const lines = diffLines("a\nb\nc", "a\nx\nc");
    const removed = lines.find((line) => line.kind === "remove");
    const added = lines.find((line) => line.kind === "add");
    expect(removed).toMatchObject({ before: 2, after: null, text: "b" });
    expect(added).toMatchObject({ before: null, after: 2, text: "x" });
  });

  it("handles an append and a truncation", () => {
    expect(diffLines("a", "a\nb").filter((l) => l.kind === "add")).toHaveLength(1);
    expect(diffLines("a\nb", "a").filter((l) => l.kind === "remove")).toHaveLength(1);
  });
});

describe("summarise", () => {
  const live = [
    "schema_version: 3",
    "identity:",
    "  venture_name: Greenstone",
    "budget:",
    "  monthly_usd_cap: 4000",
  ].join("\n");

  it("names the blocks a change touches, not just the line count", () => {
    const edited = live.replace("4000", "9000");
    const summary = summarise(live, edited);
    expect(summary.added).toBe(1);
    expect(summary.removed).toBe(1);
    // The point of the summary: *where*, so a reviewer knows what to look at.
    expect(summary.blocks).toEqual(["budget"]);
    expect(summary.identical).toBe(false);
  });

  it("says identical rather than rendering an empty diff", () => {
    // An empty panel reads as "the diff failed to load", which is the opposite of the
    // reassurance the reviewer is looking for.
    expect(summarise(live, live)).toMatchObject({
      added: 0,
      removed: 0,
      identical: true,
    });
  });

  it("does not mistake a comment or a list item for a block", () => {
    const before = ["# a comment", "market:", "  - one"].join("\n");
    const after = ["# a comment", "market:", "  - two"].join("\n");
    expect(summarise(before, after).blocks).toEqual(["market"]);
  });

  it("attributes an added block to itself", () => {
    const after = `${live}\ntriggers:\n  - on_call`;
    expect(summarise(live, after).blocks).toEqual(["triggers"]);
  });
});

describe("withContext", () => {
  it("collapses unchanged runs but keeps context around every change", () => {
    const before = Array.from({ length: 40 }, (_, i) => `line ${i}`).join("\n");
    const after = before.replace("line 20", "line twenty");

    const collapsed = withContext(diffLines(before, after), 2);
    expect(collapsed).toContain("gap");

    const kept = collapsed.filter((row): row is Exclude<typeof row, "gap"> =>
      row !== "gap",
    );
    // Both sides of the change survive, and the forty-line file does not.
    expect(kept.some((row) => row.text === "line twenty")).toBe(true);
    expect(kept.length).toBeLessThan(40);
  });
});
