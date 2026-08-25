import { describe, expect, it } from "vitest";

import { blockAtLine, findBlocks, sidebarBlocks } from "./blocks";

const DOC = [
  "# BUSINESS PACK — a header comment",
  "#",
  "schema_version: 3",
  "",
  "identity:",
  "  venture_name: Greenstone",
  "  legal_entity: Greenstone Holdings LLC",
  "",
  "market:",
  "  target_geographies:",
  "    - Las Vegas, NV",
  "budget:",
  "  monthly_usd_cap: 4000",
].join("\n");

const SCHEMA = [
  { name: "schema_version", required: false },
  { name: "identity", required: true },
  { name: "market", required: true },
  { name: "budget", required: true },
  { name: "kpi_targets", required: false },
];

describe("findBlocks", () => {
  it("finds top-level keys with their line numbers", () => {
    expect(findBlocks(DOC)).toEqual([
      { name: "schema_version", line: 3 },
      { name: "identity", line: 5 },
      { name: "market", line: 9 },
      { name: "budget", line: 12 },
    ]);
  });

  it("ignores comments, indented keys and list items", () => {
    // `venture_name` and `target_geographies` are nested; a sidebar that offered them
    // as blocks would not match the schema it claims to be showing.
    const names = findBlocks(DOC).map((b) => b.name);
    expect(names).not.toContain("venture_name");
    expect(names).not.toContain("target_geographies");
  });

  it("still works on a document that does not parse", () => {
    // The state the sidebar is most useful in. A YAML parser returns nothing here.
    const broken = "identity:\n  venture_name: [unclosed\nbudget:\n  cap: 1";
    expect(findBlocks(broken).map((b) => b.name)).toEqual(["identity", "budget"]);
  });
});

describe("sidebarBlocks", () => {
  it("renders a block the document does not contain", () => {
    // The one thing a reader cannot discover by scrolling.
    const rows = sidebarBlocks(SCHEMA, DOC, []);
    const kpi = rows.find((row) => row.name === "kpi_targets");
    expect(kpi).toMatchObject({ present: false, line: null });
    expect(rows).toHaveLength(SCHEMA.length);
  });

  it("keeps schema order, not document order", () => {
    expect(sidebarBlocks(SCHEMA, DOC, []).map((r) => r.name)).toEqual(
      SCHEMA.map((s) => s.name),
    );
  });

  it("marks a block a failing rule reads, and names the rule", () => {
    const rows = sidebarBlocks(SCHEMA, DOC, [
      { rule_id: "V18", verdict: "FAIL", blocks: ["budget"], evaluable: true },
      { rule_id: "V3", verdict: "PASS", blocks: ["market"], evaluable: true },
    ]);
    expect(rows.find((r) => r.name === "budget")?.problems).toEqual([
      { rule_id: "V18", verdict: "FAIL" },
    ]);
    // A passing rule marks nothing. An all-icons sidebar hides the rows that matter.
    expect(rows.find((r) => r.name === "market")?.problems).toEqual([]);
  });

  it("marks a block whose rule could not be evaluated", () => {
    const rows = sidebarBlocks(SCHEMA, DOC, [
      { rule_id: "V24", verdict: "NOT_RUN", blocks: ["budget"], evaluable: false },
    ]);
    expect(rows.find((r) => r.name === "budget")?.problems).toHaveLength(1);
  });
});

describe("blockAtLine", () => {
  const rows = sidebarBlocks(SCHEMA, DOC, []);

  it("returns the block a line falls inside", () => {
    expect(blockAtLine(rows, 6)).toBe("identity");
    expect(blockAtLine(rows, 11)).toBe("market");
    expect(blockAtLine(rows, 13)).toBe("budget");
  });

  it("returns null above the first block", () => {
    // The file's header comment belongs to no block, and claiming otherwise would
    // highlight a row for content that is not in it.
    expect(blockAtLine(rows, 1)).toBeNull();
  });

  it("is unaffected by blocks the document does not contain", () => {
    expect(blockAtLine(rows, 13)).toBe("budget");
  });
});
