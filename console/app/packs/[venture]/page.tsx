import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Ago } from "@/components/local-time";
import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import {
  api,
  NotAuthenticated,
  type Gates,
  type PackDetail,
  type RunSummary,
} from "@/lib/api";
import { relativeAge } from "@/lib/severity";

import { PackEditor } from "../editor";

export const dynamic = "force-dynamic";

/**
 * Pack Editor for one venture — Part 17 screen 12.
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
  if (!detail.live && detail.versions.length === 0 && runs.length === 0) notFound();

  const active = runs.find((r) =>
    ["running", "blocked", "awaiting_human"].includes(r.status),
  );
  const gate10 = gates.signoffs.find((s) => s.gate === "gate_10")?.signatures ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-base font-semibold">{venture} — Business Pack</h2>
          <p className="mt-1 text-xs text-ink-muted">
            Publishing supersedes the live version and starts nothing. Provisioning is a
            separate act on a separate screen.
          </p>
        </div>
        <Link
          href={`/provisioning/${encodeURIComponent(venture)}`}
          className="text-sm text-ink-secondary underline underline-offset-2"
        >
          Provisioning →
        </Link>
      </div>

      <PackEditor
        initialSource={detail.live?.yaml_source ?? ""}
        liveVersion={detail.live?.pack_version ?? null}
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

      <Card
        title="Version history"
        subtitle="Superseded versions stay readable — a run names the version it provisioned."
      >
        <Table
          head={["Version", "Content hash", "Authored", "State"]}
          empty="No version has been published for this venture."
        >
          {detail.versions.map((v) => (
            <Row key={v.pack_version}>
              <Cell mono>{v.pack_version}</Cell>
              <Cell mono>{v.content_hash.slice(0, 16)}…</Cell>
              <Cell><Ago iso={v.authored_at} /></Cell>
              <Cell>
                {v.superseded_at ? (
                  <Badge>superseded <Ago iso={v.superseded_at} /></Badge>
                ) : (
                  <Badge severity="ok">live</Badge>
                )}
              </Cell>
            </Row>
          ))}
        </Table>
      </Card>
    </div>
  );
}
