"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { Dots, Plus } from "@/components/icons";
import { validationSummary } from "@/lib/severity";
import { slugify } from "@/lib/slug";

import {
  createVentureAction,
  publishPackAction,
  setLifecycleAction,
  validatePackAction,
  type VentureState,
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

function Result({ state }: { state: VentureState | null }) {
  if (!state?.error && !state?.ok) return null;
  return (
    <p className={`mt-2 text-desc ${state.error ? "text-bad" : "text-ok"}`}>
      {state.error ?? state.ok}
    </p>
  );
}

const field =
  "mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink";

/**
 * Create a venture, two ways.
 *
 * "Start from a Pack" validates before anything is created, because a Pack that fails
 * Gate 2 wastes a provisioning run and the failure surfaces after Gates 0 and 1 have
 * already reported healthy. "Start blank" takes the five fields a draft needs and
 * leaves the rest to the Pack editor.
 *
 * `prefill` is how the portfolio panel hands over a venture that is named but not
 * authored — the same flow, with the name and category already in it.
 */
export function NewVenture({
  prefill,
}: {
  prefill?: { display_name: string; category: string; slug: string } | null;
}) {
  const [open, setOpen] = useState(Boolean(prefill));
  const [mode, setMode] = useState<"blank" | "pack">("blank");
  const [name, setName] = useState(prefill?.display_name ?? "");
  const [slug, setSlug] = useState(prefill?.slug ?? "");

  const [created, create] = useFormState(createVentureAction, null);
  const [validated, validatePack] = useFormState(validatePackAction, null);
  const [published, publishPack] = useFormState(publishPackAction, null);

  const derived = slug || slugify(name);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-lg bg-surface-inverse px-3 py-1.5 text-desc font-medium text-ink-inverse transition hover:opacity-90"
      >
        <Plus size={16} />
        New venture
      </button>
    );
  }

  return (
    <div className="rounded-xl border-[0.5px] border-line bg-surface px-5 py-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-section font-medium text-ink">New venture</h2>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-meta text-ink-muted underline underline-offset-2"
        >
          cancel
        </button>
      </div>

      <div className="mt-3 flex gap-2">
        {(["blank", "pack"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`rounded-lg border px-3 py-1 text-desc ${
              mode === m
                ? "border-ink bg-surface-inverse text-ink-inverse"
                : "border-line text-ink-secondary"
            }`}
          >
            {m === "blank" ? "Start blank" : "Start from a Pack"}
          </button>
        ))}
      </div>

      {mode === "blank" ? (
        <form action={create} className="mt-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="block text-meta text-ink-secondary">Name</span>
              <input
                className={field}
                name="display_name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Collingswood &amp; Co."
              />
            </label>
            <label className="block">
              <span className="block text-meta text-ink-secondary">
                Slug — editable now, immutable after
              </span>
              <input
                className={`${field} font-mono`}
                name="slug"
                value={derived}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="collingswood"
              />
              <span className="mt-1 block text-meta text-ink-muted">
                Every venture-scoped table keys on this. It is not the display name.
              </span>
            </label>
            <label className="block">
              <span className="block text-meta text-ink-secondary">Category</span>
              <input
                className={field}
                name="category"
                defaultValue={prefill?.category ?? ""}
                placeholder="Outbound voice"
              />
            </label>
            <label className="block">
              <span className="block text-meta text-ink-secondary">Environment</span>
              <select className={field} name="environment" defaultValue="sandbox">
                <option value="sandbox">sandbox</option>
                <option value="production">production</option>
              </select>
            </label>
          </div>

          <p className="text-meta text-ink-muted">
            Created in draft. A draft has no Pack, so there is nothing to generate a
            runtime config from and nothing to grant against — it cannot receive grants,
            appointments or a budget until a Pack exists.
          </p>

          <Submit label="Create draft" busy="Creating…" />
          <Result state={created} />
        </form>
      ) : (
        <div className="mt-4 space-y-3">
          <p className="text-desc text-ink-secondary">
            Paste a schema-v3 Business Pack. It is validated against all 28 rules before
            anything is created — the venture id comes from the document, never from
            this form.
          </p>

          <form action={validatePack} className="space-y-3">
            <textarea
              className={`${field} font-mono`}
              name="yaml_source"
              rows={12}
              spellCheck={false}
              placeholder="schema_version: 3&#10;identity:&#10;  venture_name: …"
            />
            <div className="flex gap-3">
              <Submit label="Validate" busy="Validating…" />
            </div>
          </form>

          {validated?.report ? <PackReport state={validated} /> : null}
          <Result state={validated} />

          <form action={publishPack} className="space-y-2 border-t border-line pt-3">
            <p className="text-meta text-ink-muted">
              Publishing does not require a clean report — Gate 2 refuses a failing Pack
              in the run, where refusing means something. It also does not start a run.
            </p>
            <textarea
              className={`${field} font-mono`}
              name="yaml_source"
              rows={4}
              spellCheck={false}
              placeholder="paste the same Pack here to publish it"
            />
            <label className="block max-w-xs">
              <span className="block text-meta text-ink-secondary">Version</span>
              <input className={field} name="pack_version" defaultValue="1.0.0" />
            </label>
            <Submit label="Publish Pack" busy="Publishing…" />
            <Result state={published} />
          </form>
        </div>
      )}
    </div>
  );
}

function PackReport({ state }: { state: VentureState }) {
  const report = state.report;
  if (!report) return null;

  if (!report.parsed) {
    return (
      <p className="rounded-lg border border-bad-line bg-bad-bg px-3 py-2 text-desc text-bad">
        Not a Business Pack: {report.error}
      </p>
    );
  }

  const summary = validationSummary({
    failures: report.failures,
    warnings: report.warnings,
    not_run: report.not_run,
    rules_checked: report.rules_checked ?? report.results.length,
  });
  const notable = report.results.filter((r) => r.verdict !== "PASS");

  return (
    <div className="space-y-2">
      <p
        className={`inline-flex rounded-md border px-2 py-0.5 text-meta ${
          summary.severity === "bad"
            ? "border-bad-line bg-bad-bg text-bad"
            : summary.severity === "warn"
              ? "border-warn-line bg-warn-bg text-warn"
              : "border-ok-line bg-ok-bg text-ok"
        }`}
      >
        {summary.text}
      </p>
      {report.not_run.length > 0 ? (
        <p className="text-meta text-ink-muted">
          NOT_RUN is not a pass — those rules need the world, and nothing about this
          document answers them.
        </p>
      ) : null}
      {notable.length > 0 ? (
        <ul className="space-y-1">
          {notable.map((r) => (
            <li key={r.rule_id} className="text-meta">
              <code className="text-ident text-ink-muted">{r.rule_id}</code>{" "}
              <span
                className={r.verdict === "FAIL" ? "text-bad" : "text-warn"}
              >
                {r.verdict}
              </span>{" "}
              <span className="text-ink-secondary">{r.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Per-venture actions. A details element, so it needs no click-outside handler. */
export function VentureMenu({
  slug,
  archived,
}: {
  slug: string;
  archived: boolean;
}) {
  const [state, action] = useFormState(setLifecycleAction, null);

  return (
    <details className="relative">
      <summary className="cursor-pointer rounded-lg border border-line px-2 py-1 text-ink-secondary hover:border-line-strong">
        <Dots size={16} />
      </summary>
      <div className="absolute right-0 z-10 mt-1 w-72 space-y-2 rounded-xl border border-line bg-surface p-3 shadow-none">
        <a
          href={`/ventures/${encodeURIComponent(slug)}`}
          className="block text-desc text-ink-secondary hover:text-ink"
        >
          Open
        </a>
        <a
          href={`/packs/${encodeURIComponent(slug)}`}
          className="block text-desc text-ink-secondary hover:text-ink"
        >
          Edit Pack
        </a>
        <a
          href={`/provisioning/${encodeURIComponent(slug)}`}
          className="block text-desc text-ink-secondary hover:text-ink"
        >
          Provisioning
        </a>

        <form action={action} className="space-y-2 border-t border-line pt-2">
          <input type="hidden" name="slug" value={slug} />
          <input
            type="hidden"
            name="state"
            value={archived ? "active" : "archived"}
          />
          <label className="block">
            <span className="block text-meta text-ink-secondary">
              {archived ? "Reason for reopening" : "Reason for archiving"}
            </span>
            <input className={field} name="reason" />
          </label>
          <p className="text-meta text-ink-muted">
            Archiving revokes nothing. Grants and the ledger outlive the decision to
            stop operating a venture.
          </p>
          <Submit
            label={archived ? "Reopen" : "Archive"}
            busy="Working…"
          />
          <Result state={state} />
        </form>
      </div>
    </details>
  );
}
