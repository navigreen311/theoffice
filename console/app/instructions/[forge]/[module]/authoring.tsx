"use client";

import { useMemo, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { AlertTriangle, Check, X } from "@/components/icons";
import { Ago } from "@/components/local-time";
import { assessSection, SECTION_GUIDANCE, SECTION_ORDER } from "@/lib/curriculum";

import { authorAction, type AuthoringState } from "./actions";

/**
 * Writing a curriculum.
 *
 * The page displayed instruction content and offered no way to produce it. The whole
 * Teach section depends on this content existing, and the only content that existed was
 * a placeholder somebody had inserted to get past the `NOT NULL`.
 *
 * The completeness assessment runs as you type, using the same rules the server uses to
 * refuse a publish — so the form cannot tell you a section is fine and then have the
 * save rejected, which is the failure mode of a client-side copy of a server rule. The
 * rules live in `lib/curriculum.ts`, mirroring `broker/curriculum_quality.py`, and a
 * test asserts the two agree on the cases that matter.
 */

function Submit({
  label,
  busy,
  tone = "quiet",
  disabled,
}: {
  label: string;
  busy: string;
  tone?: "primary" | "quiet";
  disabled?: boolean;
}) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending || disabled}
      className={`rounded-lg px-3 py-1.5 text-desc font-medium transition disabled:opacity-50 ${
        tone === "primary"
          ? "bg-surface-inverse text-ink-inverse hover:opacity-90"
          : "border border-line text-ink hover:bg-surface-muted"
      }`}
    >
      {pending ? busy : label}
    </button>
  );
}

/** The stored JSON, one click away. Engineers need it; it is not the default view. */
export function RawCurriculum({ content }: { content: Record<string, unknown> }) {
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
        <pre className="mt-2 overflow-x-auto rounded-xl bg-surface-muted p-3 font-mono text-[11px] leading-[1.7] text-ink-secondary">
          {JSON.stringify(content, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}

export function Versions({
  versions,
}: {
  versions: {
    instruction_version: string;
    forge_api_version: string;
    content_hash: string;
    author: string | null;
    authored_at: string;
    superseded_at: string | null;
  }[];
}) {
  const [from, setFrom] = useState(versions[versions.length - 1]?.instruction_version ?? "");
  const [to, setTo] = useState(versions[0]?.instruction_version ?? "");

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <h2 className="text-section font-medium text-ink">Versions</h2>

      {versions.length <= 1 ? (
        // The old panel offered a comparison between 1.0.0 and a placeholder "2.0.0"
        // that does not exist. With one version there is nothing to compare, and saying
        // so is better than a control that cannot work.
        <p className="mt-1 text-desc text-ink-secondary">
          Only one version exists. Nothing to compare.
        </p>
      ) : (
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="text-meta text-ink-muted">
            From
            <select
              value={from}
              onChange={(event) => setFrom(event.target.value)}
              className="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 font-mono text-meta text-ink"
            >
              {versions.map((version) => (
                <option key={version.instruction_version} value={version.instruction_version}>
                  {version.instruction_version}
                </option>
              ))}
            </select>
          </label>
          <label className="text-meta text-ink-muted">
            To
            <select
              value={to}
              onChange={(event) => setTo(event.target.value)}
              className="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 font-mono text-meta text-ink"
            >
              {versions.map((version) => (
                <option key={version.instruction_version} value={version.instruction_version}>
                  {version.instruction_version}
                </option>
              ))}
            </select>
          </label>
          <a
            href={`/api/instructions/diff?from=${from}&to=${to}`}
            className="pb-1.5 text-meta text-ink-muted underline underline-offset-2"
          >
            Compare
          </a>
        </div>
      )}

      <ul className="mt-3">
        {versions.map((version) => (
          <li
            key={version.instruction_version}
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line py-2"
          >
            <span className="font-mono text-desc text-ink">
              {version.instruction_version}
            </span>
            <code className="text-ident text-ink-muted">
              {version.content_hash.slice(0, 12)}…
            </code>
            <span className="text-meta text-ink-muted">
              against Forge {version.forge_api_version}
            </span>
            <span className="ml-auto text-meta text-ink-muted">
              {version.author ? `${version.author} · ` : "author not recorded · "}
              <Ago iso={version.authored_at} />
              {version.superseded_at ? " · superseded" : " · live"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Authoring({
  forge,
  moduleId,
  content,
  certificationCount,
  agentNames,
  currentVersion,
  forgeApiVersion,
}: {
  forge: string;
  moduleId: string;
  content: Record<string, unknown>;
  certificationCount: number;
  agentNames: string[];
  currentVersion: string | null;
  forgeApiVersion: string;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      SECTION_ORDER.map((name) => {
        const value = content[name];
        return [
          name,
          typeof value === "string"
            ? value
            : value === undefined
              ? ""
              : JSON.stringify(value, null, 2),
        ];
      }),
    ),
  );
  const [state, action] = useFormState<AuthoringState | null, FormData>(
    authorAction,
    null,
  );

  // Assessed as you type, by the same rules the server uses to refuse the publish.
  const assessed = useMemo(
    () => SECTION_ORDER.map((name) => assessSection(name, draft[name])),
    [draft],
  );
  const stubs = assessed.filter((s) => s.state === "stub" || s.state === "missing");
  const thin = assessed.filter((s) => s.state === "thin");

  if (!open) {
    return (
      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Author a new version</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Publishing a new version invalidates every certification earned against the
          current text.
        </p>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-3 rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
        >
          {currentVersion ? "Edit this curriculum" : "Write this curriculum"}
        </button>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-section font-medium text-ink">Author a new version</h2>
          <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
            Publishing a new version invalidates every certification earned against the
            current text.
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

      {certificationCount > 0 ? (
        <p className="mt-3 rounded-lg border border-warn-line bg-warn-bg px-3 py-2 text-desc text-warn">
          Authoring a new version will flip these {certificationCount} certification(s) to
          stale_instructions. Those agents stop being assignable on their very next call,
          not their next session.
          <span className="mt-1 block text-meta text-ink-secondary">
            {agentNames.join(", ")}
          </span>
        </p>
      ) : null}

      <form action={action} className="mt-4 space-y-4">
        <input type="hidden" name="forge_id" value={forge} />
        <input type="hidden" name="module_id" value={moduleId} />
        <input type="hidden" name="forge_api_version" value={forgeApiVersion} />

        {SECTION_ORDER.map((name, index) => {
          const section = assessed[index];
          return (
            <div key={name}>
              <label className="block">
                <span className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-[14px] font-medium text-ink">
                    {section.title}
                  </span>
                  <code className="text-ident text-ink-muted">{name}</code>
                  {section.state === "complete" ? (
                    <Check className="h-3.5 w-3.5 text-ok" />
                  ) : section.state === "thin" ? (
                    <span className="flex items-center gap-1 text-meta text-warn">
                      <AlertTriangle className="h-3 w-3" />
                      {section.reason}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-meta text-bad">
                      <X className="h-3 w-3" />
                      {section.reason}
                    </span>
                  )}
                </span>
                <span className="mt-0.5 block text-meta text-ink-muted">
                  {SECTION_GUIDANCE[name]}
                </span>
                <textarea
                  name={name}
                  rows={name === "what_it_does" || name === "retry_vs_escalate" ? 3 : 4}
                  value={draft[name]}
                  onChange={(event) =>
                    setDraft({ ...draft, [name]: event.target.value })
                  }
                  className="mt-1 w-full rounded-lg border border-line bg-surface p-2 font-mono text-meta text-ink"
                />
              </label>
            </div>
          );
        })}

        <div className="flex flex-wrap items-end gap-3 border-t border-line pt-3">
          <label className="text-meta text-ink-muted">
            New version
            <input
              name="instruction_version"
              defaultValue=""
              placeholder={currentVersion ? "1.1.0" : "1.0.0"}
              className="ml-2 w-24 rounded-lg border border-line bg-surface px-2 py-1 font-mono text-meta text-ink"
            />
          </label>

          <Submit label="Save as draft" busy="Saving…" />

          {/*
            Publishing a stub is what produced the current state, so the control is not
            available while one exists. The server refuses it too - this is the courtesy,
            that is the rule.
          */}
          <Submit
            label="Publish"
            busy="Publishing…"
            tone="primary"
            disabled={stubs.length > 0}
          />

          {stubs.length ? (
            <span className="pb-1.5 text-meta text-bad">
              {stubs.length} section{stubs.length === 1 ? "" : "s"} still placeholder or
              empty. Publishing a stub is what produced the current state.
            </span>
          ) : thin.length ? (
            <span className="pb-1.5 text-meta text-warn">
              {thin.length} section{thin.length === 1 ? " is" : "s are"} thin. Publishing
              is allowed; the curriculum will read as thin rather than complete.
            </span>
          ) : (
            <span className="pb-1.5 text-meta text-ok">All eight sections complete.</span>
          )}
        </div>

        {state?.error ? <p className="text-desc text-bad">{state.error}</p> : null}
        {state?.ok ? <p className="text-desc text-ok">{state.ok}</p> : null}
      </form>
    </section>
  );
}
