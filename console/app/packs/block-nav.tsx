"use client";

import { AlertTriangle, Minus } from "@/components/icons";
import { SchemaBar } from "@/components/schema-bar";
import type { SidebarBlock } from "@/lib/blocks";

/**
 * Block navigation for a 342-line document.
 *
 * Every block the schema defines, in document order, present or not. A list of the
 * blocks that happen to exist could not say "this Pack has no kpi_targets", and that is
 * the one thing a reader cannot find by scrolling — the absence has no line to scroll to.
 *
 * Icons appear only on rows that need one: a failing rule, or an absent block. Marking
 * every row would make the two that matter indistinguishable from the fifteen that do
 * not, which is the failure mode of a status column that always has something in it.
 */

function Row({
  block,
  active,
  onJump,
}: {
  block: SidebarBlock;
  active: boolean;
  onJump: (name: string) => void;
}) {
  const failing = block.problems.some((p) => p.verdict === "FAIL" || p.verdict === "WARN");
  const title = block.problems.length
    ? `${block.name} — ${block.problems
        .map((p) => `${p.rule_id} ${p.verdict === "NOT_RUN" ? "not evaluable here" : "fails here"}`)
        .join(", ")}`
    : block.present
      ? block.name
      : `${block.name} — not in this document${block.required ? " (required)" : ""}`;

  return (
    <li>
      <button
        type="button"
        title={title}
        onClick={() => onJump(block.name)}
        disabled={!block.present}
        className={`flex w-full items-center gap-1.5 rounded-md px-1.5 py-[3px] text-left text-meta transition ${
          active ? "bg-surface-muted text-ink" : "text-ink-secondary"
        } ${block.present ? "hover:bg-surface-muted" : "cursor-default opacity-70"}`}
      >
        <span className="w-3.5 shrink-0">
          {failing ? (
            <AlertTriangle className="h-3.5 w-3.5 text-bad" />
          ) : !block.present ? (
            <Minus className="h-3.5 w-3.5 text-ink-muted" />
          ) : null}
        </span>
        <span className="min-w-0 flex-1 truncate">{block.name}</span>
        {/* No line number for a block the document does not contain: there is nowhere
            to go, and a number would imply there is. */}
        <span className="shrink-0 font-mono text-[10px] text-ink-muted">
          {block.line ?? ""}
        </span>
      </button>
    </li>
  );
}

export function BlockNav({
  blocks,
  active,
  onJump,
}: {
  blocks: SidebarBlock[];
  active: string | null;
  onJump: (name: string) => void;
}) {
  const present = blocks.filter((block) => block.present);
  const missing = blocks.filter((block) => !block.present);

  return (
    <>
      {/* Below 1024px a seventeen-row list above the document is worse than no
          navigation: it pushes the thing being edited off the screen. */}
      <div className="lg:hidden">
        <label className="block text-meta text-ink-muted">
          Jump to block
          <select
            value={active ?? ""}
            onChange={(event) => onJump(event.target.value)}
            className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
          >
            <option value="">Choose a block</option>
            {blocks.map((block) => (
              <option key={block.name} value={block.name} disabled={!block.present}>
                {block.name}
                {block.present ? ` · line ${block.line}` : " · not in this document"}
                {block.problems.length ? " ·  ⚠" : ""}
              </option>
            ))}
          </select>
        </label>
      </div>

      <nav
        aria-label="Pack blocks"
        className="sticky top-4 hidden w-[210px] shrink-0 self-start rounded-xl border border-line bg-surface p-3 lg:block"
      >
        <SchemaBar
          present={present.length}
          total={blocks.length}
          label="Blocks"
          compact
        />
        <ul className="mt-2 max-h-[calc(100vh-16rem)] space-y-px overflow-y-auto">
          {blocks.map((block) => (
            <Row
              key={block.name}
              block={block}
              active={active === block.name}
              onJump={onJump}
            />
          ))}
        </ul>
        {missing.length ? (
          <p className="mt-2 border-t border-line pt-2 text-[10px] text-ink-muted">
            {missing.length} block{missing.length === 1 ? "" : "s"} not in this document
            {missing.some((block) => block.required) ? (
              <span className="text-bad">
                {" "}
                · {missing.filter((b) => b.required).length} required
              </span>
            ) : null}
          </p>
        ) : null}
      </nav>
    </>
  );
}
