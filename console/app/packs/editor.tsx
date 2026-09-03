"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { AlertTriangle } from "@/components/icons";
import type { PackDetail, StagedRule } from "@/lib/api";
import { blockAtLine, sidebarBlocks } from "@/lib/blocks";
import { diffLines, summarise, withContext } from "@/lib/diff";

import { BlockNav } from "./block-nav";

import {
  publishAction,
  publishDraftAction,
  saveDraftAction,
  validateAction,
  type EditorState,
  type NewPackState,
} from "./actions";
import { Hash } from "./forms";

/**
 * The Pack editor.
 *
 * Three acts, three groups, deliberately not one row of buttons. Validate writes
 * nothing. Saving a draft stores a document that cannot provision — `packs.live` does
 * not return it, so Gate 1 cannot find it. Publishing supersedes the live Pack and
 * changes what the next run provisions. Those are different consequences, and the
 * version field each one uses has to sit inside the group that uses it: two loose
 * fields beside three loose buttons is an invitation to type a version into the wrong
 * one.
 *
 * `useFormState` from `react-dom` rather than `useActionState` — this is React 18.3.1,
 * where the latter type-checks, builds, and throws at render.
 */

/**
 * The editor fills the viewport rather than growing the page, so the sidebar and the
 * action bar stay put while the document moves. Resizable, and the resize is remembered.
 */
const EDITOR_HEIGHT = "calc(100vh - 240px)";

function Submit({
  label,
  busy,
  tone = "quiet",
}: {
  label: string;
  busy: string;
  tone?: "primary" | "quiet";
}) {
  const { pending } = useFormStatus();
  const styles =
    tone === "primary"
      ? "bg-surface-inverse text-ink-inverse hover:opacity-90"
      : "border border-line text-ink hover:bg-surface-muted";
  return (
    <button
      type="submit"
      disabled={pending}
      className={`inline-flex items-center rounded-lg px-3 py-1.5 text-desc font-medium transition disabled:opacity-50 ${styles}`}
    >
      {pending ? busy : label}
    </button>
  );
}

function Result({ state }: { state: EditorState | NewPackState | null }) {
  if (!state) return null;
  if (state.error) return <p className="mt-2 text-desc text-bad">{state.error}</p>;
  if (state.ok) return <p className="mt-2 text-desc text-ok">{state.ok}</p>;

  const report = state.report;
  if (!report) return null;
  if (!report.parsed) {
    return (
      <p className="mt-2 text-desc text-bad">
        Not a schema-v3 Business Pack: {report.error}
      </p>
    );
  }

  const notable = report.results.filter((row) => row.verdict !== "PASS");
  const checked = report.rules_checked ?? report.results.length;
  const unrun = report.not_run.length;

  return (
    <div className="mt-2">
      <p className="text-desc text-ink-secondary">
        {report.failures.length
          ? `${report.failures.length} of ${checked} rules failing.`
          : unrun
            ? `${checked - unrun} passed, ${unrun} could not be evaluated against this text.`
            : `All ${checked} rules passed.`}
      </p>
      <ul className="mt-1 space-y-1">
        {notable.map((row) => (
          <li key={row.rule_id} className="text-desc text-ink-secondary">
            <span
              className={`font-mono text-meta ${
                row.verdict === "FAIL"
                  ? "text-bad"
                  : row.verdict === "WARN"
                    ? "text-warn"
                    : "text-ink-muted"
              }`}
            >
              {row.rule_id}
            </span>{" "}
            {row.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ validation */

function RuleRows({ rules }: { rules: StagedRule[] }) {
  return (
    <ul className="mt-1.5 space-y-1.5">
      {rules.map((rule) => (
        <li key={rule.rule_id} className="text-desc text-ink-secondary">
          <span className="font-mono text-meta text-ink">{rule.rule_id}</span>{" "}
          {rule.message}
          {/*
            A bare NOT_RUN tells a reader something did not happen without telling them
            what would. Every rule this stage could not settle names the gate that will.
          */}
          {rule.why_not_here ? (
            <span className="block text-meta text-warn">
              Gate {rule.settled_at_gate} evaluates this. {rule.why_not_here}
            </span>
          ) : rule.rechecked_later && rule.rechecked_reason ? (
            <span className="block text-meta text-ink-muted">
              Re-checked at gate {rule.settled_at_gate}. {rule.rechecked_reason}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/**
 * The result of validating at *this* stage, stated as three numbers.
 *
 * It used to read `can provision · 28 of 28 rules checked`, and both halves overclaimed.
 * "28 of 28 checked" counted a rule that could not be evaluated as though it had been.
 * And "can provision" is a claim about the whole pipeline that Gate 2 is not in a
 * position to make: V13 passes here on a conservative estimate and is evaluated again
 * at Gate 4.5 against the real Task Ledger, where Greenstone fails it. The honest
 * finding is narrower — no blocking failures *at this stage*.
 */
function ValidationSummary({ report }: { report: PackDetail["validation"] }) {
  const [open, setOpen] = useState(false);
  if (!report) return null;

  // Strongest state present. A failure outranks an unevaluable rule, which outranks a
  // clean pass — never the other way round.
  const tone = report.failed
    ? "border-bad-line bg-bad-bg text-bad"
    : report.not_evaluable || report.rechecked_later
      ? "border-warn-line bg-warn-bg text-warn"
      : "border-ok-line bg-ok-bg text-ok";

  const headline = report.failed
    ? `${report.failed} blocking failure${report.failed === 1 ? "" : "s"} at this stage`
    : "No blocking failures at this stage";

  const passed = report.rules.filter((r) => r.verdict === "PASS");
  const failed = report.rules.filter((r) => r.verdict === "FAIL" || r.verdict === "WARN");
  const notEvaluable = report.rules.filter((r) => !r.evaluable);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`rounded-lg border px-2.5 py-1 text-left text-meta transition ${tone}`}
      >
        <span className="font-medium">{headline}</span>
        <span className="ml-2">
          {report.passed} passed · {report.failed} failed · {report.not_evaluable} not
          evaluable at this stage
        </span>
        <span className="ml-2 underline underline-offset-2">
          {open ? "hide rules" : `all ${report.rules_total} rules`}
        </span>
      </button>

      {report.rechecked_later ? (
        <p className="mt-1 text-meta text-ink-muted">
          {report.rechecked_later} rule
          {report.rechecked_later === 1 ? " passes" : "s pass"} here on an estimate and
          {report.rechecked_later === 1 ? " is" : " are"} evaluated again at a later gate
          against generated output.
        </p>
      ) : null}

      {open ? (
        <div className="mt-3 space-y-4 rounded-xl border border-line bg-surface-muted p-4">
          {failed.length ? (
            <section>
              <h4 className="text-meta text-bad">Failed ({failed.length})</h4>
              <RuleRows rules={failed} />
            </section>
          ) : null}

          {notEvaluable.length ? (
            <section>
              <h4 className="text-meta text-warn">
                Not evaluable at this stage ({notEvaluable.length})
              </h4>
              <RuleRows rules={notEvaluable} />
            </section>
          ) : null}

          <section>
            <h4 className="text-meta text-ink-muted">Passed ({passed.length})</h4>
            <RuleRows rules={passed} />
          </section>
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------------ diff */

function DiffView({
  before,
  after,
  beforeLabel,
}: {
  before: string;
  after: string;
  beforeLabel: string;
}) {
  const summary = useMemo(() => summarise(before, after), [before, after]);
  const rows = useMemo(
    () => withContext(diffLines(before, after)),
    [before, after],
  );

  if (summary.identical) {
    // Said, not shown as an empty panel: an empty diff reads as one that failed to load.
    return (
      <p className="rounded-xl border border-line bg-surface-muted px-4 py-3 text-desc text-ink-secondary">
        No changes from {beforeLabel}.
      </p>
    );
  }

  return (
    <div className="rounded-xl border border-line">
      <p className="border-b border-line px-4 py-2 text-desc text-ink-secondary">
        <span className="text-ok">{summary.added} added</span>,{" "}
        <span className="text-bad">{summary.removed} removed</span>
        {summary.blocks.length ? (
          <>
            {" "}
            across {summary.blocks.length} block
            {summary.blocks.length === 1 ? "" : "s"}:{" "}
            <span className="font-mono">{summary.blocks.join(", ")}</span>
          </>
        ) : null}
        <span className="text-ink-muted"> · against {beforeLabel}</span>
      </p>
      <div className="max-h-[32rem] overflow-auto">
        <table className="w-full border-collapse font-mono text-meta">
          <tbody>
            {rows.map((row, index) =>
              row === "gap" ? (
                <tr key={`gap-${index}`}>
                  <td colSpan={3} className="px-3 py-1 text-center text-ink-muted">
                    ⋯
                  </td>
                </tr>
              ) : (
                <tr
                  key={`${row.kind}-${row.before}-${row.after}-${index}`}
                  className={
                    row.kind === "add"
                      ? "bg-ok-bg"
                      : row.kind === "remove"
                        ? "bg-bad-bg"
                        : ""
                  }
                >
                  <td className="w-12 select-none px-2 text-right text-ink-muted">
                    {row.before ?? ""}
                  </td>
                  <td className="w-12 select-none px-2 text-right text-ink-muted">
                    {row.after ?? ""}
                  </td>
                  <td
                    className={`whitespace-pre-wrap px-2 ${
                      row.kind === "add"
                        ? "text-ok"
                        : row.kind === "remove"
                          ? "text-bad"
                          : "text-ink-secondary"
                    }`}
                  >
                    {row.kind === "add" ? "+" : row.kind === "remove" ? "-" : " "}
                    {row.text}
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- publish confirm */

function suggestVersion(live: string | null, summary: { blocks: string[] }): string {
  if (!live) return "1.0.0";
  const parts = live.split(".").map((n) => Number.parseInt(n, 10));
  if (parts.length !== 3 || parts.some(Number.isNaN)) return "";
  // A change to what the venture *is* — its positions, budget or bindings — is not a
  // patch. Editable either way; this only saves typing.
  const structural = ["positions_required", "budget", "forge_dependencies", "human_capacity"];
  const minor = summary.blocks.some((block) => structural.includes(block));
  return minor
    ? `${parts[0]}.${parts[1] + 1}.0`
    : `${parts[0]}.${parts[1]}.${parts[2] + 1}`;
}

/* ---------------------------------------------------------------------- editor */

export function PackEditor({
  venture,
  detail,
  signatures,
}: {
  venture: string;
  detail: PackDetail;
  signatures: number;
}) {
  // The draft, in preference to the live Pack. Opening the live version over an
  // unpublished draft is how somebody's work disappears: the draft is still stored, it
  // just is not on the screen built to work on it, and the next save overwrites it.
  const editing = detail.draft ?? detail.live;
  const initialSource = editing?.yaml_source ?? "";
  const liveSource = detail.live?.yaml_source ?? "";

  const [source, setSource] = useState(initialSource);
  const [view, setView] = useState<"edit" | "diff">("edit");
  const [confirming, setConfirming] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const gutter = useRef<HTMLPreElement>(null);

  const [validation, validate] = useFormState(validateAction, null);
  const [saved, save] = useFormState<NewPackState | null, FormData>(saveDraftAction, null);
  const [publication, publish] = useFormState(publishAction, null);
  const [promotion, promote] = useFormState(publishDraftAction, null);

  const dirty = source !== initialSource;
  const summary = useMemo(() => summarise(liveSource, source), [liveSource, source]);
  const lineCount = source.split("\n").length;

  // Read from the buffer, not the stored Pack: the sidebar has to follow what is being
  // typed, including a document that does not parse yet.
  const blocks = useMemo(
    () => sidebarBlocks(detail.schema.blocks, source, detail.validation?.rules ?? []),
    [detail.schema.blocks, detail.validation?.rules, source],
  );

  /** Scroll the textarea so a block's first line is at the top, and focus it. */
  const jumpTo = useCallback(
    (name: string) => {
      const block = blocks.find((candidate) => candidate.name === name);
      const element = textarea.current;
      if (!block?.line || !element) return;

      // The offset of the line's first character, so the caret lands in the block
      // rather than merely near it.
      const offset = source
        .split("\n")
        .slice(0, block.line - 1)
        .reduce((total, line) => total + line.length + 1, 0);

      const lineHeight =
        Number.parseFloat(getComputedStyle(element).lineHeight) || 20;
      element.focus();
      element.setSelectionRange(offset, offset);
      element.scrollTop = (block.line - 1) * lineHeight;
      setActive(name);
    },
    [blocks, source],
  );

  // Deep link. `/packs/greenstone#budget` opens on budget, which is what the
  // provisioning screen's "Fix in Pack editor" points at.
  useEffect(() => {
    const hash = decodeURIComponent(window.location.hash.replace("#", ""));
    if (hash) jumpTo(hash);
    // Once, on mount. Re-running as the buffer changes would yank the caret back.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Which block the top of the viewport is in. Throttled to one frame. */
  const onScroll = useCallback(() => {
    const element = textarea.current;
    if (!element) return;
    const lineHeight =
      Number.parseFloat(getComputedStyle(element).lineHeight) || 20;
    const topLine = Math.floor(element.scrollTop / lineHeight) + 1;
    setActive(blockAtLine(blocks, topLine));
  }, [blocks]);

  // The page says "not counting your unsaved edits" and nothing indicated whether there
  // were any. Leaving with them is losing them, so the browser asks first.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // A resize is a preference about this screen, not about this Pack, so it is restored
  // for whoever set it and never travels anywhere. Guarded: a private window or blocked
  // site data throws on access rather than returning null.
  useEffect(() => {
    const element = textarea.current;
    if (!element) return;
    try {
      const saved = window.localStorage.getItem("pack-editor-height");
      if (saved) element.style.height = saved;
    } catch {
      /* storage unavailable; the default height is correct anyway */
    }
    const observer = new ResizeObserver(() => {
      try {
        window.localStorage.setItem("pack-editor-height", element.style.height);
      } catch {
        /* nothing to do; the resize still applies for this session */
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const knownFailures = (detail.validation?.rules ?? []).filter(
    (rule) => rule.verdict === "FAIL" || rule.verdict === "WARN" || !rule.evaluable,
  );

  return (
    <div className="space-y-4">
      {/*
        Two columns. `min-w-0` on the editor is load-bearing: without it the monospace
        content sets the flex item's minimum width and the document pushes the sidebar
        off the screen instead of scrolling.
      */}
      <div className="flex flex-col gap-3 lg:flex-row">
        <BlockNav blocks={blocks} active={active} onJump={jumpTo} />

        <section className="min-w-0 flex-1 rounded-xl border border-line bg-surface">
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-section font-medium text-ink">
              {detail.draft ? "Draft" : detail.live ? "Live Pack" : "New Pack"}
              {editing ? (
                <span className="ml-2 font-mono text-desc text-ink-secondary">
                  {editing.pack_version}
                </span>
              ) : null}
              {dirty ? (
                <span className="ml-2 rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 text-meta text-warn">
                  unsaved edits
                </span>
              ) : null}
            </h2>
            <p className="mt-0.5 max-w-2xl text-desc text-ink-secondary">
              YAML, schema v3. The hash is taken over these exact bytes, because a
              reviewer signs a document rather than a parse tree.
            </p>
            {detail.draft && detail.live ? (
              <p className="mt-1 text-meta text-ink-muted">
                Editing the draft. Version {detail.live.pack_version} stays live until you
                publish.
              </p>
            ) : null}
          </div>
          <ValidationSummary report={detail.validation} />
        </header>

        {/* A compact bar rather than controls floating above the document. */}
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-2">
          {(["edit", "diff"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setView(mode)}
              className={`rounded-lg px-2.5 py-1 text-desc transition ${
                view === mode
                  ? "bg-surface-inverse text-ink-inverse"
                  : "border border-line text-ink-secondary hover:bg-surface-muted"
              }`}
            >
              {mode === "edit"
                ? "Edit"
                : `Diff against live${detail.live ? ` ${detail.live.pack_version}` : ""}`}
            </button>
          ))}
          <span className="ml-auto text-meta text-ink-muted">
            {lineCount} lines
            {summary.identical
              ? " · identical to live"
              : ` · ${summary.added + summary.removed} changed`}
          </span>
        </div>

        <div className="px-5 py-4">
          <p className="text-meta text-ink-muted">
            As stored — not counting your unsaved edits
          </p>

          <div className="mt-3">
            {view === "edit" ? (
              <div className="flex overflow-hidden rounded-lg border border-line bg-surface">
                {/*
                  Line numbers, so a validator message can cite one. Scrolled in step
                  with the textarea rather than independently: two panes that scroll
                  apart are worse than no numbers at all.
                */}
                <pre
                  aria-hidden
                  ref={gutter}
                  className="select-none overflow-hidden border-r border-line bg-surface-muted px-2 py-3 text-right font-mono text-meta leading-[1.45rem] text-ink-muted"
                  style={{ height: EDITOR_HEIGHT }}
                >
                  {Array.from({ length: lineCount }, (_, i) => i + 1).join("\n")}
                </pre>
                <textarea
                  ref={textarea}
                  onScroll={(event) => {
                    if (gutter.current) {
                      gutter.current.scrollTop = event.currentTarget.scrollTop;
                    }
                    onScroll();
                  }}
                  // `whitespace-pre` keeps wrapping off, which the gutter and the
                  // scroll-spy both depend on: they map scroll offset to line number by
                  // assuming one visual row per line.
                  className="min-h-[400px] flex-1 resize-y overflow-auto whitespace-pre bg-surface p-3 font-mono text-meta leading-[1.45rem] text-ink outline-none"
                  style={{ height: EDITOR_HEIGHT }}
                  spellCheck={false}
                  value={source}
                  onChange={(event) => setSource(event.target.value)}
                  aria-label="Pack YAML source"
                />
              </div>
            ) : detail.live ? (
              <DiffView
                before={liveSource}
                after={source}
                beforeLabel={`live ${detail.live.pack_version}`}
              />
            ) : (
              <p className="rounded-xl border border-line bg-surface-muted px-4 py-3 text-desc text-ink-secondary">
                No live version to compare against — nothing has been published for this
                venture yet.
              </p>
            )}
          </div>

          {/*
            Three groups, each with the field it uses, publish separated because it is
            the only one with a consequence beyond this page. These stay below the
            document as the reference — the version fields live here — and the pinned
            bar carries shortcuts to the same three actions.
          */}
          <div className="mt-5 flex flex-wrap items-stretch gap-3">
            <form
              id="pack-validate"
              action={validate}
              className="min-w-[13rem] flex-1 rounded-xl border border-line px-4 py-3"
            >
              <input type="hidden" name="yaml_source" value={source} />
              <h3 className="text-desc font-medium text-ink">Validate</h3>
              <p className="mb-3 mt-1 text-meta text-ink-muted">
                Runs every rule against this text. Writes nothing.
              </p>
              <Submit label="Validate" busy="Validating…" />
              <Result state={validation} />
            </form>

            <form
              id="pack-save-draft"
              action={save}
              className="min-w-[15rem] flex-1 rounded-xl border border-line px-4 py-3"
            >
              <input type="hidden" name="yaml_source" value={source} />
              <h3 className="text-desc font-medium text-ink">Save as draft</h3>
              <p className="mb-2 mt-1 text-meta text-ink-muted">
                A draft cannot provision — Gate 1 does not find it — so it is safe to save
                one that still fails.
              </p>
              <label className="mb-3 block text-meta text-ink-muted">
                Draft version
                <input
                  name="pack_version"
                  defaultValue={detail.draft?.pack_version ?? "0.1.0"}
                  className="ml-2 w-28 rounded-lg border border-line bg-surface px-2 py-1 font-mono text-meta text-ink"
                />
              </label>
              <Submit label="Save as draft" busy="Saving…" />
              <Result state={saved} />
            </form>

            <form
              id="pack-publish"
              action={publish}
              className="min-w-[16rem] flex-1 rounded-xl border border-bad-line bg-bad-bg px-4 py-3"
            >
              <input type="hidden" name="yaml_source" value={source} />
              <h3 className="text-desc font-medium text-ink">Publish</h3>
              <p className="mb-2 mt-1 text-meta text-ink-secondary">
                Supersedes the live Pack. Does not start a run.
              </p>
              <label className="mb-3 block text-meta text-ink-muted">
                Publish as version
                <input
                  name="pack_version"
                  defaultValue={suggestVersion(
                    detail.live?.pack_version ?? null,
                    summary,
                  )}
                  className="ml-2 w-28 rounded-lg border border-line bg-surface px-2 py-1 font-mono text-meta text-ink"
                />
              </label>

              {confirming ? (
                <div className="space-y-2">
                  <div className="rounded-lg border border-line bg-surface px-3 py-2">
                    <p className="text-meta text-ink">
                      {detail.live ? (
                        <>
                          <span className="font-mono">{detail.live.pack_version}</span> →
                          the version above
                        </>
                      ) : (
                        "First published version for this venture"
                      )}
                    </p>
                    <p className="mt-1 text-meta text-ink-secondary">
                      {summary.identical
                        ? "Byte-identical to the live Pack."
                        : `${summary.added} lines added, ${summary.removed} removed${
                            summary.blocks.length
                              ? ` across ${summary.blocks.length}: ${summary.blocks.join(", ")}`
                              : ""
                          }.`}
                    </p>
                    {knownFailures.length ? (
                      <p className="mt-1 text-meta text-warn">
                        Carries{" "}
                        {knownFailures.map((rule) => rule.rule_id).join(", ")} —{" "}
                        {knownFailures.some((r) => !r.evaluable)
                          ? "including rules a later gate has still to settle."
                          : "already failing."}
                      </p>
                    ) : null}
                    {signatures > 0 ? (
                      <p className="mt-1 text-meta text-bad">
                        {signatures} Gate 10 signature
                        {signatures === 1 ? "" : "s"} bind to artifacts generated from the
                        live Pack. Publishing changes those artifacts, so the signatures
                        stop matching — nothing revokes them, and Gate 11 refuses.
                      </p>
                    ) : null}
                    <p className="mt-1 text-meta text-ink-muted">
                      Does not start a run. Provisioning is a separate act.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Submit label="Publish" busy="Publishing…" tone="primary" />
                    <button
                      type="button"
                      onClick={() => setConfirming(false)}
                      className="text-meta text-ink-muted underline underline-offset-2"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirming(true)}
                  className="inline-flex items-center rounded-lg border border-line bg-surface px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
                >
                  Publish this text…
                </button>
              )}
              <Result state={publication} />
            </form>
          </div>

          <div className="mt-4 space-y-1.5">
            {detail.bindings.open_runs.map((run) => (
              <p
                key={run.run_id}
                className="flex items-start gap-1.5 text-desc text-ink-secondary"
              >
                <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0 text-warn" />
                Run {run.run_id.slice(0, 8)} is {run.status} at gate {run.current_gate} —
                pinned to {run.pack_version}, so publishing does not change what it
                provisions. A new run picks up the new Pack.
              </p>
            ))}
            {editing ? (
              <div>
                <Hash value={editing.content_hash} label="stored hash" />
                <p className="mt-0.5 text-meta text-ink-muted">
                  Every provisioning run records the Pack hash it started from, and Gate
                  10 signatures bind to the artifacts this document generates.
                </p>
              </div>
            ) : null}
          </div>
        </div>

        {/*
          Pinned. The three actions used to sit below 342 lines of document, so editing
          budget at line 230 meant scrolling past 229 lines to reach it and 112 more to
          act on it.

          These are shortcuts to the same three forms below, submitted by `form=`, so
          there is one implementation of each action and the two cannot drift. Publish
          still opens its confirmation - a pinned button that skipped it would be a
          one-click supersede, which is exactly what the confirmation exists to prevent.
        */}
        <div className="sticky bottom-0 flex flex-wrap items-center gap-3 rounded-b-xl border-t border-line bg-surface px-5 py-2.5">
          <span className={`text-meta ${dirty ? "text-warn" : "text-ink-muted"}`}>
            {dirty ? "Unsaved edits" : "No unsaved edits"}
          </span>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button
              type="submit"
              form="pack-validate"
              className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
            >
              Validate
            </button>
            <button
              type="submit"
              form="pack-save-draft"
              className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
            >
              Save draft
            </button>
            <button
              type="button"
              onClick={() => {
                setConfirming(true);
                document
                  .getElementById("pack-publish")
                  ?.scrollIntoView({ block: "center" });
              }}
              className="rounded-lg bg-surface-inverse px-3 py-1.5 text-desc font-medium text-ink-inverse transition hover:opacity-90"
            >
              Publish…
            </button>
          </div>
        </div>
      </section>
      </div>

      {detail.draft ? (
        <section className="rounded-xl border border-line bg-surface px-5 py-4">
          <h2 className="text-section font-medium text-ink">
            Publish draft {detail.draft.pack_version}
          </h2>
          <p className="mt-0.5 max-w-2xl text-desc text-ink-secondary">
            Promotes the stored draft as it is — not the text in the box above, which is
            only stored once you save it. Publishing supersedes{" "}
            {detail.live ? `version ${detail.live.pack_version}` : "nothing"} and changes
            what the next provisioning run provisions.
          </p>
          <form action={promote} className="mt-3">
            <input type="hidden" name="venture_id" value={venture} />
            <Submit label="Publish draft" busy="Publishing…" />
          </form>
          <Result state={promotion} />
        </section>
      ) : null}
    </div>
  );
}