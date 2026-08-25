"use client";

import { useState } from "react";

import { Ago } from "@/components/local-time";
import type { PackVersion } from "@/lib/api";
import { diffLines, summarise, withContext } from "@/lib/diff";

import { restoreAsDraftAction, versionSource } from "../actions";

/**
 * Version history, in an order a reader can follow.
 *
 * It listed `0.0.1-smoke superseded · 1.2.0-draft superseded · 1.0.0 live ·
 * 1.1.0-draft superseded` — a superseded version sitting above a live one, which reads
 * as a broken sort no matter what the underlying logic is. It was sorted correctly, by
 * authored time; what was wrong is that one word covered two different events. A draft
 * somebody abandoned and a released version replaced by a later release are not the
 * same thing, and separating them makes the order legible.
 *
 * The section has always promised that "a run names the version it provisioned" and
 * never delivered it: the history listed versions, the provisioning screen listed runs,
 * and joining them was the reader's job.
 */

const TONE: Record<string, string> = {
  live: "border-ok-line bg-ok-bg text-ok",
  draft: "border-warn-line bg-warn-bg text-warn",
};

function tone(version: PackVersion): string {
  return TONE[version.status] ?? "border-line bg-surface-muted text-ink-muted";
}

function Row({
  venture,
  version,
  liveSource,
  compareTo,
  onCompare,
}: {
  venture: string;
  version: PackVersion;
  liveSource: string | null;
  compareTo: string | null;
  onCompare: (versionId: string | null) => void;
}) {
  const [diff, setDiff] = useState<{ before: string; after: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [restored, setRestored] = useState<string | null>(null);

  const selected = compareTo === version.pack_version;

  return (
    <li className="border-t border-line py-2.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-desc text-ink">{version.pack_version}</span>
        <span className={`rounded-lg border px-2 py-0.5 text-meta ${tone(version)}`}>
          {/* Names what became of it, rather than one word for four outcomes. */}
          {version.disposition}
        </span>
        <code className="text-ident text-ink-muted">
          {version.content_hash.slice(0, 12)}…
        </code>
        <span className="text-meta text-ink-muted">
          {/* The promise this section has always made, kept. */}
          {version.runs > 0 ? (
            <>
              provisioned by {version.runs} run{version.runs === 1 ? "" : "s"}
              {version.last_run_at ? (
                <>
                  {" · last "}
                  <Ago iso={version.last_run_at} />
                </>
              ) : null}
            </>
          ) : (
            "never provisioned"
          )}
        </span>
        <span className="ml-auto text-meta text-ink-muted">
          {version.author ? `${version.author} · ` : ""}
          authored <Ago iso={version.authored_at} />
          {version.superseded_at ? (
            <>
              {/* The same column records when a release was replaced and when a draft
                  was dropped. Calling both "superseded" reintroduces, in the timestamp,
                  the conflation the disposition just removed. */}
              {version.status === "abandoned" ? " · abandoned " : " · superseded "}
              <Ago iso={version.superseded_at} />
            </>
          ) : null}
        </span>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            if (diff) {
              setDiff(null);
              return;
            }
            setBusy(true);
            const other = compareTo && compareTo !== version.pack_version
              ? compareTo
              : null;
            Promise.all([
              versionSource(venture, version.pack_version),
              other ? versionSource(venture, other) : Promise.resolve(liveSource ?? ""),
            ])
              .then(([mine, theirs]) => setDiff({ before: theirs, after: mine }))
              .finally(() => setBusy(false));
          }}
          className="text-meta text-ink-muted underline underline-offset-2 hover:text-ink"
        >
          {busy
            ? "Loading…"
            : diff
              ? "Hide diff"
              : compareTo && compareTo !== version.pack_version
                ? `Diff against ${compareTo}`
                : "Diff against live"}
        </button>

        <button
          type="button"
          onClick={() => onCompare(selected ? null : version.pack_version)}
          className={`text-meta underline underline-offset-2 ${
            selected ? "text-ink" : "text-ink-muted hover:text-ink"
          }`}
        >
          {selected ? "Comparing against this" : "Compare against this"}
        </button>

        <form
          action={async (form: FormData) => {
            const result = await restoreAsDraftAction(null, form);
            setRestored(result.error ?? result.ok ?? null);
          }}
        >
          <input type="hidden" name="venture_id" value={venture} />
          <input type="hidden" name="pack_version" value={version.pack_version} />
          <button
            type="submit"
            className="text-meta text-ink-muted underline underline-offset-2 hover:text-ink"
          >
            Restore as draft
          </button>
        </form>
      </div>

      {restored ? <p className="mt-1 text-meta text-ink-secondary">{restored}</p> : null}

      {diff ? <InlineDiff before={diff.before} after={diff.after} /> : null}
    </li>
  );
}

function InlineDiff({ before, after }: { before: string; after: string }) {
  const summary = summarise(before, after);
  if (summary.identical) {
    return (
      <p className="mt-2 text-meta text-ink-secondary">
        Byte-identical — same content hash.
      </p>
    );
  }
  const rows = withContext(diffLines(before, after), 2);
  return (
    <div className="mt-2 rounded-lg border border-line">
      <p className="border-b border-line px-3 py-1.5 text-meta text-ink-secondary">
        <span className="text-ok">{summary.added} added</span>,{" "}
        <span className="text-bad">{summary.removed} removed</span>
        {summary.blocks.length ? (
          <>
            {" across "}
            <span className="font-mono">{summary.blocks.join(", ")}</span>
          </>
        ) : null}
      </p>
      <div className="max-h-80 overflow-auto">
        <pre className="px-3 py-2 font-mono text-meta leading-5">
          {rows.map((row, index) =>
            row === "gap" ? (
              <span key={`gap-${index}`} className="block text-ink-muted">
                ⋯
              </span>
            ) : (
              <span
                key={`${row.kind}-${index}`}
                className={`block ${
                  row.kind === "add"
                    ? "bg-ok-bg text-ok"
                    : row.kind === "remove"
                      ? "bg-bad-bg text-bad"
                      : "text-ink-secondary"
                }`}
              >
                {row.kind === "add" ? "+" : row.kind === "remove" ? "-" : " "}
                {row.text}
              </span>
            ),
          )}
        </pre>
      </div>
    </div>
  );
}

export function VersionHistory({
  venture,
  versions,
}: {
  venture: string;
  versions: PackVersion[];
}) {
  const [compareTo, setCompareTo] = useState<string | null>(null);

  const live = versions.find((version) => version.status === "live") ?? null;
  // Two groups. A draft that was never published and a released version that was later
  // replaced are different events, and interleaving them by timestamp is what made the
  // list read as unsorted.
  const published = versions.filter((version) =>
    ["live", "superseded"].includes(version.status),
  );
  const drafts = versions.filter((version) =>
    ["draft", "abandoned"].includes(version.status),
  );

  if (versions.length === 0) {
    return (
      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Version history</h2>
        <p className="mt-0.5 text-desc text-ink-secondary">
          No version has been stored for this venture.
        </p>
      </section>
    );
  }

  const group = (label: string, rows: PackVersion[]) =>
    rows.length ? (
      <div className="mt-4">
        <h3 className="text-meta text-ink-muted">{label}</h3>
        <ul>
          {rows.map((version) => (
            <Row
              key={version.pack_version}
              venture={venture}
              version={version}
              liveSource={null}
              compareTo={compareTo}
              onCompare={setCompareTo}
            />
          ))}
        </ul>
      </div>
    ) : null;

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <h2 className="text-section font-medium text-ink">Version history</h2>
      <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
        Superseded versions stay readable — a run names the version it provisioned.
      </p>
      {compareTo ? (
        <p className="mt-2 text-meta text-ink-secondary">
          Comparing against <span className="font-mono">{compareTo}</span>.{" "}
          <button
            type="button"
            onClick={() => setCompareTo(null)}
            className="underline underline-offset-2"
          >
            Compare against live {live?.pack_version ?? ""} instead
          </button>
        </p>
      ) : null}

      {group("Published", published)}
      {group("Drafts", drafts)}
    </section>
  );
}
