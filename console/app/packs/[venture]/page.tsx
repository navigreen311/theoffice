import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { AsOf, Ago } from "@/components/local-time";
import {
  api,
  NotAuthenticated,
  type Gates,
  type PackDetail,
  type PackVersion,
  type RunSummary,
} from "@/lib/api";

import { PackEditor } from "../editor";

export const dynamic = "force-dynamic";

/**
 * Pack Editor for one venture — Part 17 screen 12.
 *
 * The directory rebuild gave Packs drafts, templates, four validation states and a
 * publish step, and none of it reached this screen — which is where the work those
 * things describe actually happens. So a draft saved from the directory was invisible
 * here, the editor opened the live Pack over the top of it, and there was no way to save
 * a draft or publish one.
 *
 * The version history is not decoration. A run records the version it started from and
 * stays pinned to it, so "which text did this run provision" is a question an operator
 * asks after the fact, and it is unanswerable if the editor only shows the current one.
 */

const STATUS_TONE: Record<PackVersion["status"], string> = {
  draft: "border-line bg-surface-muted text-ink-secondary",
  live: "border-ok-line bg-ok-bg text-ok",
  superseded: "border-line bg-surface-muted text-ink-muted",
};

function Versions({ versions }: { versions: PackVersion[] }) {
  if (versions.length === 0) {
    return (
      <p className="mt-2 text-desc text-ink-secondary">
        No version has been stored for this venture.
      </p>
    );
  }

  return (
    <ul className="mt-3 space-y-2">
      {versions.map((version) => (
        <li
          key={version.pack_version}
          className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line pt-2"
        >
          <span className="font-mono text-desc text-ink">{version.pack_version}</span>
          {/*
            Keyed on `status`, never on `superseded_at`. A draft has no `superseded_at`
            either, so the old check rendered an unpublished draft with a green "live"
            badge — two rows both claiming to be the version in force.
          */}
          <span
            className={`rounded-lg border px-2 py-0.5 text-meta ${STATUS_TONE[version.status]}`}
          >
            {version.status}
          </span>
          <code className="text-ident text-ink-muted">
            {version.content_hash.slice(0, 12)}…
          </code>
          <span className="ml-auto text-meta text-ink-muted">
            authored <Ago iso={version.authored_at} />
            {version.superseded_at ? (
              <>
                {" · superseded "}
                <Ago iso={version.superseded_at} />
              </>
            ) : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default async function PackEditorPage({
  params,
}: {
  params: { venture: string };
}) {
  const venture = decodeURIComponent(params.venture);

  let detail: PackDetail;
  let runs: RunSummary[];
  let gates: Gates;
  try {
    [detail, runs, gates] = await Promise.all([
      api.get<PackDetail>(`/api/packs/${encodeURIComponent(venture)}`),
      api.get<RunSummary[]>(
        `/api/provisioning/runs?venture_id=${encodeURIComponent(venture)}`,
      ),
      api.get<Gates>(`/api/ventures/${encodeURIComponent(venture)}/gates`),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  // A venture with neither a Pack nor a run is not a venture this screen knows about.
  // Rendering an empty editor for a mistyped slug would invite publishing a Pack under
  // a venture id nobody meant, and the id is not a parameter anywhere downstream — it
  // comes from the document.
  if (!detail.live && !detail.draft && detail.versions.length === 0 && runs.length === 0) {
    notFound();
  }

  const active = runs.find((run) =>
    ["running", "blocked", "awaiting_human"].includes(run.status),
  );
  const gate10 = gates.signoffs.find((s) => s.gate === "gate_10")?.signatures ?? 0;

  return (
    <div className="space-y-6">
      <Breadcrumb
        trail={[
          { label: "Dashboard", href: "/" },
          { label: "Packs", href: "/packs" },
          { label: venture },
        ]}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-page font-medium text-ink">{venture} — Business Pack</h1>
          <p className="mt-1 text-desc text-ink-secondary">
            Publishing supersedes the live version and starts nothing. Provisioning is a
            separate act on a separate screen.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-meta text-ink-muted">
            <AsOf iso={detail.as_of} />
          </span>
          <Link
            href={`/provisioning/${encodeURIComponent(venture)}`}
            className="text-desc text-ink underline underline-offset-2"
          >
            Provisioning
          </Link>
        </div>
      </div>

      <PackEditor
        venture={venture}
        detail={detail}
        activeRun={
          active
            ? {
                run_id: active.run_id,
                status: active.status,
                current_gate: active.current_gate,
              }
            : null
        }
        signatures={gate10}
      />

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Version history</h2>
        <p className="mt-0.5 text-desc text-ink-secondary">
          Superseded versions stay readable — a run names the version it provisioned.
        </p>
        <Versions versions={detail.versions} />
      </section>
    </div>
  );
}
