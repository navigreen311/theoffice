/**
 * Where each top-level block starts in a Pack document.
 *
 * The sidebar describes the buffer somebody is typing into, not the stored Pack, so the
 * line numbers and the present/absent state are read from the text on every keystroke.
 * A parsed model could not answer either question: it has no line numbers, and an
 * optional field with a default reads as present even when the document never mentions
 * it.
 *
 * Deliberately not a YAML parse. Most of the time somebody is editing, the document does
 * not parse — that is the state the sidebar is most useful in, and a parser would return
 * nothing exactly then.
 */

export type BlockPosition = {
  name: string;
  /** 1-indexed line of the block's key. */
  line: number;
};

/** A top-level key: column zero, a name, a colon. Not a comment, not a list item. */
const TOP_LEVEL = /^([A-Za-z_][A-Za-z0-9_]*):/;

export function findBlocks(source: string): BlockPosition[] {
  const out: BlockPosition[] = [];
  source.split("\n").forEach((text, index) => {
    const match = TOP_LEVEL.exec(text);
    if (match) out.push({ name: match[1], line: index + 1 });
  });
  return out;
}

export type SidebarBlock = {
  name: string;
  required: boolean;
  /** Null when the document does not contain this block. */
  line: number | null;
  present: boolean;
  /** Rule ids that read this block and are failing or unevaluable. */
  problems: { rule_id: string; verdict: string }[];
};

/**
 * The sidebar's rows: every block the schema defines, in document order, whether or not
 * the document contains it.
 *
 * A missing block is information. A list of the blocks that happen to exist cannot say
 * "this Pack has no kpi_targets", which is the one thing a reader cannot discover by
 * scrolling.
 */
export function sidebarBlocks(
  schema: { name: string; required: boolean }[],
  source: string,
  rules: { rule_id: string; verdict: string; blocks: string[]; evaluable: boolean }[],
): SidebarBlock[] {
  const found = new Map(findBlocks(source).map((b) => [b.name, b.line]));

  return schema.map((block) => {
    const line = found.get(block.name) ?? null;
    return {
      name: block.name,
      required: block.required,
      line,
      present: line !== null,
      // Only what is worth marking. A rule that passes says nothing about this block
      // that the reader needs while navigating.
      problems: rules
        .filter(
          (rule) =>
            rule.blocks.includes(block.name) &&
            (rule.verdict === "FAIL" || rule.verdict === "WARN" || !rule.evaluable),
        )
        .map((rule) => ({ rule_id: rule.rule_id, verdict: rule.verdict })),
    };
  });
}

/**
 * The block a given line falls inside — the scroll-spy's question.
 *
 * Blocks are ordered by line, so this is the last block whose key is at or above the
 * line. A line above the first block (the file's header comment) belongs to no block.
 */
export function blockAtLine(
  blocks: SidebarBlock[],
  line: number,
): string | null {
  let current: string | null = null;
  for (const block of blocks) {
    if (block.line !== null && block.line <= line) current = block.name;
    else if (block.line !== null) break;
  }
  return current;
}
