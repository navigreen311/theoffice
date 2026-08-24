"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { AlertTriangle } from "@/components/icons";
import type { PackDetail, RuleRow } from "@/lib/api";

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
 * Three acts, three forms, deliberately not one form with three buttons. Validate writes
 * nothing. Saving a draft stores a document that cannot provision — `packs.live` does not
 * return it, so Gate 1 cannot find it. Publishing supersedes the live Pack and changes
 * what the next run provisions. Those are different consequences and a shared submit
 * handler puts them one keystroke apart.
 *
 * `useFormState` from `react-dom` rather than `useActionState` — this is React 18.3.1,
 * where the latter type-checks, builds, and throws at render.
 */

const STATE_LABEL: Record<string, string> = {
  failing: "cannot provision",
  not_validated: "not validated",
  warnings: "provisions with warnings",
  valid: "can provision",
};

const STATE_TONE: Record<string, string> = {
  failing: "border-bad-line bg-bad-bg text-bad",
  // Not neutral. An unknown about whether a Pack can provision is a warning.
  not_validated: "border-warn-line bg-warn-bg text-warn",
  warnings: "border-warn-line bg-warn-bg text-warn",
  valid: "border-ok-line bg-ok-bg text-ok",
};

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

/** The rules that are not a PASS, in the same vocabulary the directory uses. */
function Rules({ rows }: { rows: RuleRow[] }) {
  if (rows.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1">
      {rows.map((row) => (
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
          <span className="text-meta text-ink-muted">{row.verdict}</span> {row.message}
        </li>
      ))}
    </ul>
  );
}

function Result({ state }: { state: EditorState | NewPackState | null }) {
  if (!state) return null;

  if (state.error) return <p className="mt-3 text-desc text-bad">{state.error}</p>;
  if (state.ok) return <p className="mt-3 text-desc text-ok">{state.ok}</p>;

  const report = state.report;
  if (!report) return null;

  if (!report.parsed) {
    return (
      <p className="mt-3 text-desc text-bad">
        Not a schema-v3 Business Pack: {report.error}
      </p>
    );
  }

  const notable = report.results.filter((row) => row.verdict !== "PASS");
  const checked = report.rules_checked ?? report.results.length;

  return (
    <div className="mt-3">
      <p className="text-desc text-ink-secondary">
        {report.failures.length
          ? `${report.failures.length} of ${checked} rules failing.`
          : report.not_run.length
            ? `${report.not_run.length} of ${checked} rules could not run. That is not a pass — those rules need the world, and nothing about this document answers them.`
            : `All ${checked} rules passed.`}
      </p>
      <Rules rows={notable} />
    </div>
  );
}

export function PackEditor({
  venture,
  detail,
  activeRun,
  signatures,
}: {
  venture: string;
  detail: PackDetail;
  activeRun: { run_id: string; status: string; current_gate: string } | null;
  signatures: number;
}) {
  // The draft, in preference to the live Pack. Opening the live version over an
  // unpublished draft is how somebody's work disappears: the draft is still stored, it
  // just is not on the screen built to work on it, and the next save overwrites it.
  const editing = detail.draft ?? detail.live;
  const initialSource = editing?.yaml_source ?? "";

  const [source, setSource] = useState(initialSource);
  const [validation, validate] = useFormState(validateAction, null);
  const [saved, save] = useFormState<NewPackState | null, FormData>(saveDraftAction, null);
  const [publication, publish] = useFormState(publishAction, null);
  const [promotion, promote] = useFormState(publishDraftAction, null);

  const dirty = source !== initialSource;
  const state = detail.validation?.state;

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-line bg-surface">
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <h2 className="text-section font-medium text-ink">
              {detail.draft ? "Draft" : detail.live ? "Live Pack" : "New Pack"}
              {editing ? (
                <span className="ml-2 font-mono text-desc text-ink-secondary">
                  {editing.pack_version}
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
          {state ? (
            <span
              className={`shrink-0 rounded-lg border px-2 py-0.5 text-meta ${STATE_TONE[state]}`}
            >
              {STATE_LABEL[state]}
              {detail.validation
                ? ` · ${detail.validation.rules_checked} of ${detail.validation.rules_total} rules checked`
                : ""}
            </span>
          ) : null}
        </header>

        <div className="p-5">
          {detail.validation?.notable.length ? (
            <div className="mb-4">
              <p className="text-meta text-ink-muted">
                As stored — not counting your unsaved edits
              </p>
              <Rules rows={detail.validation.notable} />
            </div>
          ) : null}

          <textarea
            className="w-full rounded-lg border border-line bg-surface p-3 font-mono text-meta text-ink"
            rows={24}
            spellCheck={false}
            value={source}
            onChange={(event) => setSource(event.target.value)}
            aria-label="Pack YAML source"
          />

          <div className="mt-4 flex flex-wrap items-end gap-4">
            <form action={validate}>
              <input type="hidden" name="yaml_source" value={source} />
              <p className="mb-2 max-w-xs text-meta text-ink-muted">
                Runs every rule against this text. Writes nothing.
              </p>
              <Submit label="Validate" busy="Validating…" />
            </form>

            <form action={save} className="space-y-1">
              <input type="hidden" name="yaml_source" value={source} />
              <label className="block text-meta text-ink-muted">
                Draft version
                <input
                  name="pack_version"
                  defaultValue={detail.draft?.pack_version ?? "0.1.0"}
                  className="ml-2 w-28 rounded-lg border border-line bg-surface px-2 py-1 font-mono text-meta text-ink"
                />
              </label>
              <p className="max-w-xs text-meta text-ink-muted">
                A draft cannot provision — Gate 1 does not find it — so it is safe to save
                one that still fails.
              </p>
              <Submit label="Save as draft" busy="Saving…" />
            </form>

            <form action={publish} className="space-y-1">
              <input type="hidden" name="yaml_source" value={source} />
              <label className="block text-meta text-ink-muted">
                Publish as version
                <input
                  name="pack_version"
                  placeholder="1.1.0"
                  className="ml-2 w-28 rounded-lg border border-line bg-surface px-2 py-1 font-mono text-meta text-ink"
                />
              </label>
              <p className="max-w-xs text-meta text-ink-muted">
                Supersedes the live Pack. Does not start a run.
              </p>
              <Submit label="Publish this text" busy="Publishing…" tone="primary" />
            </form>
          </div>

          {/* What publishing will disturb, said before it happens rather than
              discovered afterwards. Both facts are invisible from an editor. */}
          <div className="mt-4 space-y-1.5">
            {activeRun ? (
              <p className="flex items-start gap-1.5 text-desc text-ink-secondary">
                <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0 text-warn" />
                Run {activeRun.run_id.slice(0, 8)} is {activeRun.status} at gate{" "}
                {activeRun.current_gate} — it is pinned to the version it started from, so
                publishing does not change what it provisions. A new run picks up the new
                Pack.
              </p>
            ) : null}
            {signatures > 0 ? (
              <p className="flex items-start gap-1.5 text-desc text-ink-secondary">
                <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0 text-warn" />
                {signatures} Gate 10 signature{signatures === 1 ? "" : "s"} on record —
                void against the artifacts a changed Pack generates. Nothing revokes them;
                they stop matching, and Gate 11 refuses to activate.
              </p>
            ) : null}
            {dirty ? (
              <p className="text-desc text-ink-muted">
                Unsaved edits. Nothing is written until you save a draft or publish.
              </p>
            ) : null}
            {editing ? <Hash value={editing.content_hash} label="stored hash" /> : null}
          </div>

          <Result state={validation} />
          <Result state={saved} />
          <Result state={publication} />
        </div>
      </section>

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
