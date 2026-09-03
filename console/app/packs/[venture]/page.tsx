import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { AsOf } from "@/components/local-time";
import {
  api,
  NotAuthenticated,
  type PackDetail,
  type RunSummary,
} from "@/lib/api";

import { PackEditor } from "../editor";
import { VersionHistory } from "./history";
import { runsPath } from "@/lib/runs";

export const dynamic = "force-dynamic";

/**
 * Pack Editor for one venture — Part 17 screen 12.
 *
 * The directory rebuild gave Packs drafts, templates, validation states and a publish
 * step, and none of it reached this screen — which is where the work those things
 * describe actually happens.
 *
 * The version history is not decoration. A run records the version it started from and
 * stays pinned to it, so "which text did this run provision" is a question an operator
 * asks after the fact, and it is unanswerable if the editor only shows the current one.
 */
export default async function PackEditorPage({
  params,
}: {
  params: { venture: string };
}) {
  const venture = decodeURIComponent(params.venture);

  let detail: PackDetail;
  let runList: { runs: RunSummary[]; excluded_fixtures: number };
  try {
    [detail, runList] = await Promise.all([
      api.get<PackDetail>(`/api/packs/${encodeURIComponent(venture)}`),
      api.get<{ runs: RunSummary[]; excluded_fixtures: number }>(
        runsPath(venture),
      ),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  // The listing filters smoke-test runs out by default and says how many.
  const runs = runList.runs;

  // A venture with neither a Pack nor a run is not a venture this screen knows about.
  // Rendering an empty editor for a mistyped slug would invite publishing a Pack under
  // a venture id nobody meant, and the id is not a parameter anywhere downstream — it
  // comes from the document.
  if (!detail.live && !detail.draft && detail.versions.length === 0 && runs.length === 0) {
    notFound();
  }

  // The venture's own name for itself, out of the document. The slug is a database key
  // and reads like one; it stays, in mono, beside the name rather than instead of it.
  const source = detail.draft?.yaml_source ?? detail.live?.yaml_source ?? "";
  const displayName =
    /^\s*venture_name:\s*(.+?)\s*$/m.exec(source)?.[1] ?? venture;

  return (
    <div className="space-y-6">
      <Breadcrumb
        trail={[
          { label: "Dashboard", href: "/" },
          { label: "Packs", href: "/packs" },
          { label: displayName },
        ]}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-page font-medium text-ink">
            {displayName} — Business Pack{" "}
            <code className="text-ident font-normal text-ink-muted">{venture}</code>
          </h1>
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
        signatures={detail.bindings.gate_10_signatures}
      />

      <VersionHistory venture={venture} versions={detail.versions} />
    </div>
  );
}
