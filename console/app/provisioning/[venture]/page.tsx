import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import {
  api,
  NotAuthenticated,
  type GateRow,
  type PackDetail,
  type RunDetail,
  type RunSummary,
} from "@/lib/api";
import { gateLabel, gateSeverity, relativeAge, runSeverity } from "@/lib/severity";

import {
  AbortForm,
  AdvanceForm,
  ReviewForm,
  SignOffForm,
  StartRunForm,
} from "../forms";

export const dynamic = "force-dynamic";

/**
 * The gate ladder — Part 17 screen 13.
 *
 * Sixteen rows, always, including the gates that have not run. A ladder that listed
 * only what happened would show a run blocked at 9.5 as a tidy list of nine passes,
 * which reads as nearly finished rather than as stopped six gates short.
 *
 * Three verdicts rendered three ways. `awaiting_human` is not `blocked` and not
 * `passed`: rendered as a pass the operator stops looking, rendered as blocked they go
 * hunting for a defect instead of reading the artifacts they are being asked to review.
 */

/** Evidence, rendered rather than hidden. A verdict with no visible basis is an opinion. */
function Evidence({ evidence }: { evidence: Record<string, unknown> }) {
  const entries = Object.entries(evidence);
  if (entries.length === 0) return null;
  return (
    <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[max-content_1fr]">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-neutral-500">{key}</dt>
          <dd className="break-words font-mono text-neutral-800">
            {typeof value === "object" && value !== null
              ? JSON.stringify(value)
              : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * What Gate 4 asks a human to look at, expanded.
 *
 * The approval queue taught this: a one-click decision beside a collapsed payload is a
 * rubber-stamp machine — every action authorised, audited, and producing exactly the
 * outcome the control exists to prevent. Gate 4 is the same shape, so the numbers the
 * reviewer is accountable for are on screen before the form, not behind a disclosure.
 */
function ReviewBrief({ evidence }: { evidence: Record<string, unknown> }) {
  const capacity = evidence.capacity as Record<string, number> | undefined;
  const unfilled = (evidence.unfilled_positions ?? []) as {
    position: string;
    unfilled: number;
  }[];
  const warnings = (evidence.warnings ?? []) as string[];

  return (
    <div className="space-y-3">
      {capacity ? (
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            ["certified_and_free", "Certified and free"],
            ["certified_but_allocated", "Certified, allocated elsewhere"],
            ["produced_not_yet_certified", "Produced, not yet certified"],
          ].map(([key, label]) => (
            <div key={key} className="rounded border border-neutral-200 p-3">
              <div className="text-2xl font-semibold">{capacity[key] ?? "—"}</div>
              <div className="mt-1 text-xs text-neutral-600">{label}</div>
            </div>
          ))}
        </div>
      ) : null}

      <div>
        <h4 className="text-xs font-medium text-neutral-700">
          Unfilled positions ({unfilled.length})
        </h4>
        {unfilled.length === 0 ? (
          <p className="text-xs text-neutral-500">
            Every position is filled by a certified agent.
          </p>
        ) : (
          <ul className="mt-1 space-y-0.5 text-xs">
            {unfilled.map((u) => (
              <li key={u.position}>
                <Badge severity="warn">
                  {u.position} — {u.unfilled} unfilled
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h4 className="text-xs font-medium text-neutral-700">
          Generator warnings ({warnings.length})
        </h4>
        {warnings.length === 0 ? (
          <p className="text-xs text-neutral-500">None.</p>
        ) : (
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-neutral-700">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function GateLadder({ ladder }: { ladder: GateRow[] }) {
  return (
    <ol className="space-y-2">
      {ladder.map((g) => (
        <li
          key={g.gate}
          className={`rounded border p-3 ${
            g.is_current ? "border-neutral-900 bg-neutral-50" : "border-neutral-200"
          }`}
        >
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-mono text-xs text-neutral-500">Gate {g.gate}</span>
            <span className="text-sm font-medium">{g.title}</span>
            <Badge severity={gateSeverity(g.verdict)}>{gateLabel(g.verdict)}</Badge>
            {g.recorded_at ? (
              <span className="text-xs text-neutral-400">
                {relativeAge(g.recorded_at)}
              </span>
            ) : null}
          </div>
          {g.reason ? (
            <p className="mt-1 text-xs text-neutral-700">{g.reason}</p>
          ) : null}
          {/* Evidence is expanded on the gate being acted on, because that is the one
              whose numbers a decision is about to rest on. */}
          {g.is_current ? <Evidence evidence={g.evidence} /> : null}
        </li>
      ))}
    </ol>
  );
}

export default async function ProvisioningVenturePage({
  params,
}: {
  params: { venture: string };
}) {
  const venture = decodeURIComponent(params.venture);

  let runs: RunSummary[];
  let pack: PackDetail;
  try {
    [runs, pack] = await Promise.all([
      api.get<RunSummary[]>(
        `/api/provisioning/runs?venture_id=${encodeURIComponent(venture)}`,
      ),
      api.get<PackDetail>(`/api/packs/${encodeURIComponent(venture)}`),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  // No Pack and no run is not a venture this screen can act on. Rendering an empty
  // ladder for a mistyped slug would offer a "Start a run" button for a venture that
  // does not exist, and Gate 1 would refuse it with a message about a missing Pack.
  if (!pack.live && pack.versions.length === 0 && runs.length === 0) notFound();

  const current = runs.find((r) =>
    ["running", "blocked", "awaiting_human"].includes(r.status),
  );
  const latest = current ?? runs[0];

  let detail: RunDetail | null = null;
  if (latest) {
    detail = await api.get<RunDetail>(`/api/provisioning/runs/${latest.run_id}`);
  }

  const currentGate = detail?.ladder.find((g) => g.is_current);
  const isOpen =
    detail !== null && ["running", "blocked", "awaiting_human"].includes(detail.status);
  const atGate4 = isOpen && detail?.current_gate === "4";
  const atGate10 = isOpen && detail?.current_gate === "10";

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-base font-semibold">{venture} — provisioning</h2>
          <p className="mt-1 text-xs text-neutral-500">
            {pack.live
              ? `Live Pack ${pack.live.pack_version} · ${pack.live.content_hash.slice(0, 16)}…`
              : "No live Pack — Gate 1 refuses a run without one."}
          </p>
        </div>
        <Link
          href={`/packs/${encodeURIComponent(venture)}`}
          className="text-sm text-neutral-600 underline underline-offset-2"
        >
          Pack editor →
        </Link>
      </div>

      {detail === null ? (
        <Card title="No run yet" subtitle="A run provisions the Pack that is live when it starts.">
          <StartRunForm venture={venture} />
        </Card>
      ) : (
        <>
          <Card
            title={`Run ${detail.run_id.slice(0, 8)} — Pack ${detail.pack_version}`}
            subtitle={
              detail.artifacts_hash
                ? `Artifacts ${detail.artifacts_hash.slice(0, 24)}…`
                : "Artifacts have not been generated yet — Gate 3 does that."
            }
          >
            <div className="flex flex-wrap items-center gap-3">
              <Badge severity={runSeverity(detail.status)}>{detail.status}</Badge>
              <span className="text-sm text-neutral-700">
                at gate <span className="font-mono">{detail.current_gate}</span> —{" "}
                {currentGate?.title}
              </span>
            </div>
          </Card>

          {atGate4 && currentGate ? (
            <Card
              title="Gate 4 — human review"
              subtitle="This gate waits. It does not pass on its own, and nothing advances until a named human records what they read."
            >
              <div className="space-y-4">
                <ReviewBrief evidence={currentGate.evidence} />
                <ReviewForm runId={detail.run_id} venture={venture} />
              </div>
            </Card>
          ) : null}

          {atGate10 ? (
            <Card
              title="Gate 10 — named-human sign-off"
              subtitle="Bound to the artifact hash. Separation of duties applies: whoever recorded the Gate 4 review cannot sign this."
            >
              <SignOffForm
                runId={detail.run_id}
                venture={venture}
                artifactsHash={detail.artifacts_hash}
              />
            </Card>
          ) : null}

          {isOpen ? (
            <div className="grid gap-4 md:grid-cols-2">
              <Card title="Advance">
                <AdvanceForm
                  runId={detail.run_id}
                  venture={venture}
                  currentGate={detail.current_gate}
                />
              </Card>
              <Card title="Abandon">
                <AbortForm runId={detail.run_id} venture={venture} />
              </Card>
            </div>
          ) : (
            <Card
              title={`This run is ${detail.status}`}
              subtitle="A completed or abandoned run cannot be advanced. Start a new one."
            >
              <StartRunForm venture={venture} />
            </Card>
          )}

          <Card title="Gate ladder" subtitle="All sixteen, including the ones still ahead.">
            <GateLadder ladder={detail.ladder} />
          </Card>
        </>
      )}

      <Card title="Run history">
        <Table
          head={["Run", "Pack", "Status", "Gate", "Started", "Completed"]}
          empty="No run has been started for this venture."
        >
          {runs.map((r) => (
            <Row key={r.run_id}>
              <Cell mono>{r.run_id.slice(0, 8)}</Cell>
              <Cell mono>{r.pack_version}</Cell>
              <Cell>
                <Badge severity={runSeverity(r.status)}>{r.status}</Badge>
              </Cell>
              <Cell mono>{r.current_gate}</Cell>
              <Cell>{relativeAge(r.started_at)}</Cell>
              <Cell>{r.completed_at ? relativeAge(r.completed_at) : "—"}</Cell>
            </Row>
          ))}
        </Table>
      </Card>
    </div>
  );
}
