import { describe, expect, it } from "vitest";

import { slugify } from "./slug";

describe("slugify", () => {
  // The same cases `tests/contract/test_ventures_api.py` asserts against the Python
  // implementation. A slug is a database key: every venture-scoped table stores it as
  // text, so the two sides producing different answers would mean the preview shows one
  // key and the row gets another.
  it("matches the server for the cases the server tests", () => {
    expect(slugify("Collingswood & Co.")).toBe("collingswood-co");
    expect(slugify("  MedLink   Pro  ")).toBe("medlink-pro");
    expect(slugify("Greenstone")).toBe("greenstone");
    expect(slugify("Burkham Wickmont")).toBe("burkham-wickmont");
  });

  it("collapses runs and trims the edges rather than emitting empty segments", () => {
    expect(slugify("a---b")).toBe("a-b");
    expect(slugify("-lead and trail-")).toBe("lead-and-trail");
  });

  it("returns empty for a name with nothing usable in it", () => {
    // The server raises here. The console shows an empty preview and lets the server
    // refuse, rather than inventing a slug from punctuation.
    expect(slugify("!!!")).toBe("");
  });
});
