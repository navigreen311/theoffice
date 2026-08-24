"use client";

import { useState } from "react";

import { Ago } from "@/components/local-time";
import type { RunSummary } from "@/lib/api";
import { relativeAge } from "@/lib/severity";

/**
 * The underlying evidence, behind a toggle.
 *
 * It used to be the default view: three capacity numbers as an object literal and a
 * warnings array with escaped quotes, printed at the human who is about to take
 * responsibility for what they read. Engineers do need it — a rendered summary is a
 * summary, and when the two disagree the raw object is the one that is true — so it
 * stays, one click away rather than first.
 */
export function RawEvidence({ evidence }: { evidence: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-meta text-ink-muted underline underline-offset-2 hover:text-ink"
      >
        {open ? "Hide raw" : "View raw"}
      </button>
      {open ? (
        <pre className="mt-2 overflow-x-auto rounded-xl bg-surface-muted p-3 font-mono text-meta text-ink-secondary">
          {JSON.stringify(evidence, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}

/** Display vocabulary. `awaiting_human` and `aborted` are column values, not sentences. */
function label(status: string, gate: string): string {
  switch (status) {
    case "awaiting_human":
      return `awaiting review at gate ${gate}`;
    case "aborted":
      // "Aborted" reads as a crash. Somebody chose to stop this.
      return "abandoned";
    case "rejected":
      return `rejected at gate ${gate}`;
    case "complete":
      return "complete";
    case "blocked":
      return `stopped at gate ${gate}`;
    default:
      return `${status} at gate ${gate}`;
  }
}

function tone(status: string): string {
  // Abandonment and rejection must not share a colour. One says the run was dropped;
  // the other is a judgement about the artifacts.
  if (status === "rejected") return "border-bad-line bg-bad-bg text-bad";
  if (status === "aborted") return "border-line bg-surface-muted text-ink-secondary";
  if (status === "complete") return "border-ok-line bg-ok-bg text-ok";
  if (status === "blocked") return "border-bad-line bg-bad-bg text-bad";
  return "border-warn-line bg-warn-bg text-warn";
}

/** "an eighth", not "a 8th". The sentence is the finding; a broken ordinal undercuts it. */
const ORDINALS = [
  "", "", "a second", "a third", "a fourth", "a fifth", "a sixth", "a seventh",
  "an eighth", "a ninth", "a tenth", "an eleventh", "a twelfth",
];

function nth(n: number): string {
  return ORDINALS[n] ?? `a ${n}th`;
}

/**
 * Run history, read rather than listed.
 *
 * Six runs, all against Pack 1.0.0, all stopped at gate 4, rendered as six identical
 * rows. The pattern is the most useful fact on the page and the table made the reader
 * derive it — and the conclusion it leads to, that re-running changes nothing, is
 * exactly what somebody about to press Re-run needs to know.
 */
export function RunHistoryTable({ runs }: { runs: RunSummary[] }) {
  const [expanded, setExpanded] = useState(false);

  if (runs.length === 0) {
    return (
      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Run history</h2>
        <p className="mt-0.5 text-desc text-ink-secondary">
          No run has been started for this venture.
        </p>
      </section>
    );
  }

  const gates = new Set(runs.map((run) => run.current_gate));
  const versions = new Set(runs.map((run) => run.pack_version));
  const furthest = runs.reduce(
    (best, run) => Math.max(best, run.gates_passed),
    0,
  );

  // The finding, computed. "None past gate 4" is only true if every run stopped there.
  const stuck = runs.length > 1 && gates.size === 1 && versions.size === 1;
  const onlyGate = [...gates][0];
  const onlyVersion = [...versions][0];

  // Older runs with the same outcome carry no new information. Collapsed rather than
  // dropped: the count is the evidence for the pattern above.
  const RECENT = 3;
  const recent = runs.slice(0, RECENT);
  const older = runs.slice(RECENT);
  const shown = expanded ? runs : recent;

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <h2 className="text-section font-medium text-ink">
        Run history — {runs.length} run{runs.length === 1 ? "" : "s"}
        {stuck ? `, none past gate ${onlyGate}` : ""}
      </h2>
      {stuck ? (
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Every run used Pack {onlyVersion} and stopped at the same gate. Nothing has
          changed between attempts, so nothing will change on the next one.
        </p>
      ) : (
        <p className="mt-0.5 text-desc text-ink-secondary">
          Furthest any run reached: {furthest} gate{furthest === 1 ? "" : "s"} cleared.
        </p>
      )}

      {stuck ? (
        <p className="mt-3 rounded-xl border border-warn-line bg-warn-bg px-3 py-2 text-desc text-warn">
          Re-running without editing the Pack will produce this same result{" "}
          {nth(runs.length + 1)} time.
        </p>
      ) : null}

      <ul className="mt-3 space-y-2">
        {shown.map((run) => (
          <li
            key={run.run_id}
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line pt-2"
          >
            <code className="text-ident text-ink-muted">
              {run.run_id.slice(0, 8)}
            </code>
            <span
              className={`rounded-lg border px-2 py-0.5 text-meta ${tone(run.status)}`}
            >
              {label(run.status, run.current_gate)}
            </span>
            {/* On every row. When consecutive runs share a version, that is the signal
                that nothing changed between them. */}
            <span className="text-meta text-ink-muted">
              Pack <span className="font-mono">{run.pack_version}</span>
            </span>
            <span className="text-meta text-ink-muted">
              {run.gates_passed} cleared
            </span>
            <span className="ml-auto text-meta text-ink-muted">
              started <Ago iso={run.started_at} />
              {run.completed_at ? ` · ended $<Ago iso={run.completed_at} />` : ""}
            </span>
          </li>
        ))}
      </ul>

      {older.length > 0 && !expanded ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-2 text-meta text-ink-muted underline underline-offset-2 hover:text-ink"
        >
          {older.length} older run{older.length === 1 ? "" : "s"}
          {new Set(older.map((run) => run.status)).size === 1
            ? `, ${older.length === 1 ? "" : "all "}${label(
                older[0].status,
                older[0].current_gate,
              )}`
            : ""}{" "}
          · show all
        </button>
      ) : null}
      {expanded ? (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="mt-2 text-meta text-ink-muted underline underline-offset-2 hover:text-ink"
        >
          Show fewer
        </button>
      ) : null}
    </section>
  );
}
