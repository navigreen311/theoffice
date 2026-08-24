"use client";

import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { Copy, FileText, Plus } from "@/components/icons";
import type { PackTemplateCategory } from "@/lib/api";

import {
  loadStarterAction,
  publishDraftAction,
  saveDraftAction,
  type EditorState,
  type NewPackState,
} from "./actions";

function Submit({ label, busy }: { label: string; busy: string }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-lg bg-surface-inverse px-3 py-1.5 text-desc font-medium text-ink-inverse transition hover:opacity-90 disabled:opacity-50"
    >
      {pending ? busy : label}
    </button>
  );
}

function Quiet({ label, busy }: { label: string; busy: string }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted disabled:opacity-50"
    >
      {pending ? busy : label}
    </button>
  );
}

const field =
  "mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink";

/**
 * The content hash, with a way to take it somewhere.
 *
 * A hash the reader cannot copy is decoration. This one is what a provisioning run
 * recorded and what an audit entry references, so the useful act is getting it out of
 * the page and into whatever they are comparing it against.
 */
export function Hash({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  return (
    <button
      type="button"
      title={value}
      onClick={() => {
        void navigator.clipboard?.writeText(value).then(() => setCopied(true));
      }}
      className="group inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 font-mono text-meta text-ink-muted transition hover:bg-surface-muted hover:text-ink"
    >
      <span>
        {label} {value.slice(0, 12)}…
      </span>
      <Copy className="h-3 w-3 opacity-0 transition group-hover:opacity-70" />
      {copied ? <span className="font-sans text-ok">copied</span> : null}
    </button>
  );
}

/** Promote the draft. Separate form so the button carries its own pending state. */
export function PublishDraft({ ventureId }: { ventureId: string }) {
  const [state, action] = useFormState<EditorState | null, FormData>(
    publishDraftAction,
    null,
  );
  return (
    <form action={action}>
      <input type="hidden" name="venture_id" value={ventureId} />
      <Quiet label="Publish draft" busy="Publishing…" />
      {state?.error || state?.ok ? (
        <p className={`mt-2 text-meta ${state.error ? "text-bad" : "text-ok"}`}>
          {state.error ?? state.ok}
        </p>
      ) : null}
    </form>
  );
}

/**
 * New Pack — three ways in, one way out.
 *
 * Paste, template and duplicate differ only in where the text comes from. All three end
 * at the same textarea and the same save, so there is one code path that stores a Pack
 * and one place a Pack can be wrong. A separate "create from template" endpoint that
 * wrote its own row would be a second way to author a Pack, and the second way is
 * always the one that skips a check.
 *
 * Everything is saved as a **draft**. Drafts cannot provision — `packs.live` does not
 * return one — so a half-written Pack is storable without being reachable.
 */
export function NewPack({
  categories,
  existing,
}: {
  categories: PackTemplateCategory[];
  existing: { venture_id: string; display_name: string }[];
}) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"paste" | "template" | "duplicate">("template");
  const [source, setSource] = useState("");

  const [starter, loadStarter] = useFormState<NewPackState | null, FormData>(
    loadStarterAction,
    null,
  );
  const [saved, save] = useFormState<NewPackState | null, FormData>(
    saveDraftAction,
    null,
  );

  // A loaded starter replaces the textarea. Keyed on the text itself so re-loading the
  // same template does not clobber edits the operator has already made to it.
  useEffect(() => {
    if (starter?.loaded) setSource(starter.loaded);
  }, [starter?.loaded]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-lg bg-surface-inverse px-3 py-1.5 text-desc font-medium text-ink-inverse transition hover:opacity-90"
      >
        <Plus className="h-4 w-4" />
        New Pack
      </button>
    );
  }

  const tab = (value: typeof mode, label: string) => (
    <button
      key={value}
      type="button"
      onClick={() => setMode(value)}
      className={`rounded-lg px-2.5 py-1 text-desc transition ${
        mode === value
          ? "bg-surface-inverse text-ink-inverse"
          : "border border-line text-ink-secondary hover:bg-surface-muted"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="rounded-2xl border border-line bg-surface p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-ink">New Pack</h3>
          <p className="mt-1 text-meta text-ink-muted">
            Saved as a draft at version 0.1.0. A draft cannot provision — Gate 1 does not
            find it — so it is safe to save one that still fails the validator.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-meta text-ink-muted underline underline-offset-2"
        >
          Cancel
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {tab("template", "From a template")}
        {tab("duplicate", "Copy an existing Pack")}
        {tab("paste", "Paste YAML")}
      </div>

      {mode !== "paste" ? (
        <form action={loadStarter} className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
          <input type="hidden" name="mode" value={mode} />
          {mode === "template" ? (
            <>
              <label className="text-meta text-ink-secondary">
                Category
                <select name="category" className={field} defaultValue="">
                  <option value="" disabled>
                    Choose one
                  </option>
                  {categories.map((c) => (
                    <option key={c.category} value={c.category}>
                      {c.category}
                      {c.frameworks.length
                        ? ` · ${c.frameworks.join(", ")}`
                        : " · no frameworks"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-meta text-ink-secondary">
                Venture name <span className="text-ink-muted">(optional)</span>
                <input name="venture_name" className={field} placeholder="Leave blank for REPLACE_ME" />
              </label>
            </>
          ) : (
            <>
              <label className="text-meta text-ink-secondary sm:col-span-2">
                Copy from
                <select name="from_venture" className={field} defaultValue="">
                  <option value="" disabled>
                    Choose a Pack
                  </option>
                  {existing.map((v) => (
                    <option key={v.venture_id} value={v.venture_id}>
                      {v.display_name}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          <div className="flex items-end">
            <Quiet label="Load" busy="Loading…" />
          </div>
        </form>
      ) : null}

      {starter?.error ? (
        <p className="mt-2 text-meta text-bad">{starter.error}</p>
      ) : starter?.ok ? (
        <p className="mt-2 flex items-start gap-1.5 text-meta text-ink-secondary">
          <FileText className="mt-px h-3.5 w-3.5 shrink-0" />
          {starter.ok}
        </p>
      ) : null}

      <form action={save} className="mt-4 space-y-3">
        <label className="block text-meta text-ink-secondary">
          Pack source
          <textarea
            name="yaml_source"
            value={source}
            onChange={(event) => setSource(event.target.value)}
            rows={mode === "paste" && !source ? 8 : 16}
            spellCheck={false}
            placeholder={
              mode === "paste"
                ? "Paste a schema-v3 Business Pack…"
                : "Load a starting point above, or type here."
            }
            className="mt-1 w-full rounded-lg border border-line bg-surface p-3 font-mono text-meta text-ink"
          />
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-meta text-ink-secondary">
            Version
            <input
              name="pack_version"
              defaultValue="0.1.0"
              className="ml-2 w-24 rounded-lg border border-line bg-surface px-2 py-1 font-mono text-meta text-ink"
            />
          </label>
          <Submit label="Save as draft" busy="Saving…" />
        </div>
      </form>

      {saved?.error ? <p className="mt-2 text-meta text-bad">{saved.error}</p> : null}
      {saved?.ok ? (
        <div className="mt-3 rounded-xl border border-line bg-surface-muted p-3">
          <p className="text-meta text-ink">{saved.ok}</p>
          {saved.failing?.length ? (
            <ul className="mt-2 space-y-1">
              {saved.failing.map((rule) => (
                <li key={rule.rule_id} className="text-meta text-ink-secondary">
                  <span className="font-mono text-bad">{rule.rule_id}</span> {rule.message}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
