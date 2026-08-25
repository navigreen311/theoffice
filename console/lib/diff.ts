/**
 * A unified diff between two Pack sources.
 *
 * This document gets signed. Its hash binds Gate 10 signatures and pins every
 * provisioning run that started from it, so "what is different from the live version"
 * is the question a reviewer has to answer before publishing — and there was no way to
 * ask it. The reviewer's alternative was reading two YAML documents side by side.
 *
 * Implemented here rather than pulled in, because a diff library is a dependency on the
 * one page in the console that must not surprise anybody, and the algorithm is a
 * standard LCS in forty lines. No dependency also means no CSP question.
 */

export type DiffLine = {
  kind: "same" | "add" | "remove";
  /** Line number in the old text; null for an addition. */
  before: number | null;
  /** Line number in the new text; null for a removal. */
  after: number | null;
  text: string;
};

export type DiffSummary = {
  added: number;
  removed: number;
  /** Top-level YAML blocks touched, so a reader knows where to look. */
  blocks: string[];
  identical: boolean;
};

/** Longest common subsequence over lines. */
function lcs(a: string[], b: string[]): number[][] {
  const table: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i][j] =
        a[i] === b[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  return table;
}

export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const table = lcs(a, b);

  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ kind: "same", before: i + 1, after: j + 1, text: a[i] });
      i++;
      j++;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      out.push({ kind: "remove", before: i + 1, after: null, text: a[i] });
      i++;
    } else {
      out.push({ kind: "add", before: null, after: j + 1, text: b[j] });
      j++;
    }
  }
  while (i < a.length) {
    out.push({ kind: "remove", before: i + 1, after: null, text: a[i] });
    i++;
  }
  while (j < b.length) {
    out.push({ kind: "add", before: null, after: j + 1, text: b[j] });
    j++;
  }
  return out;
}

/**
 * Which top-level block a line belongs to.
 *
 * A YAML top-level key is one at column zero ending in a colon. Comments and list items
 * are not keys. This is deliberately not a YAML parse: the diff has to work on text
 * that does not parse yet, which is most of the time somebody is editing.
 */
function blockAt(lines: string[], index: number): string | null {
  for (let k = index; k >= 0; k--) {
    const line = lines[k];
    if (!line || line.startsWith("#") || line.startsWith(" ") || line.startsWith("-")) {
      continue;
    }
    const match = /^([A-Za-z_][A-Za-z0-9_]*):/.exec(line);
    if (match) return match[1];
  }
  return null;
}

export function summarise(before: string, after: string): DiffSummary {
  const lines = diffLines(before, after);
  const added = lines.filter((line) => line.kind === "add").length;
  const removed = lines.filter((line) => line.kind === "remove").length;

  const beforeLines = before.split("\n");
  const afterLines = after.split("\n");
  const blocks = new Set<string>();
  for (const line of lines) {
    if (line.kind === "same") continue;
    const block =
      line.kind === "add"
        ? blockAt(afterLines, (line.after ?? 1) - 1)
        : blockAt(beforeLines, (line.before ?? 1) - 1);
    if (block) blocks.add(block);
  }

  return {
    added,
    removed,
    blocks: [...blocks].sort(),
    // Byte-identical, which must be said rather than shown as an empty diff: an empty
    // panel reads as "the diff failed to load".
    identical: before === after,
  };
}

/** Collapse long runs of unchanged lines, keeping context around each change. */
export function withContext(lines: DiffLine[], context = 3): (DiffLine | "gap")[] {
  const keep = new Set<number>();
  lines.forEach((line, index) => {
    if (line.kind === "same") return;
    for (let k = index - context; k <= index + context; k++) {
      if (k >= 0 && k < lines.length) keep.add(k);
    }
  });

  const out: (DiffLine | "gap")[] = [];
  let skipping = false;
  lines.forEach((line, index) => {
    if (keep.has(index)) {
      out.push(line);
      skipping = false;
    } else if (!skipping) {
      out.push("gap");
      skipping = true;
    }
  });
  return out;
}
