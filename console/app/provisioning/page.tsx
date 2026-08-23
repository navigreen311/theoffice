import Link from "next/link";
import { redirect } from "next/navigation";

import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import {
  api,
  NotAuthenticated,
  type PackSummary,
  type RunSummary,
} from "@/lib/api";
import { relativeAge, runSeverity } from "@/lib/severity";

export const dynamic = "force-dynamic";

/**
 * Provisioning Console index — Part 17 screen 13.
 *
 * One row per venture rather than one per run, because "how far did this venture get"
 * is the question, and a list of runs answers it only if you already know which run is
 * current. Ventures with a Pack and no run at all are listed too — an unprovisioned
 * venture and a venture blocked at gate 9.5 look identical if only runs are shown.
 */
export default async function ProvisioningPage() {
  let runs: RunSummary[];
  let packs: PackSummary[];
  try {
    [runs, packs] = await Promise.all([
      api.get<RunSummary[]>("/api/provisioning/runs"),
      api.get<PackSummary[]>("/api/packs"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  // Runs come back newest first, so the first one seen per venture is the latest.
  // `null` is a real value here, not a placeholder: a venture with a Pack and no run
  // is a distinct state from a venture blocked partway through one, and the two look
  // identical if only runs are listed.
  const latest = new Map<string, RunSummary | null>();
  for (const run of runs) {
    if (!latest.has(run.venture_id)) latest.set(run.venture_id, run);
  }
  for (const pack of packs) {
    if (!latest.has(pack.venture_id)) latest.set(pack.venture_id, null);
  }

  const rows = [...latest.entries()].sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold">Provisioning</h2>
        <p className="mt-1 text-xs text-neutral-500">
          Sixteen gates from a Business Pack to a live venture. A run stops at the first
          gate that blocks and says which.
        </p>
      </div>

      <Card
        title="Ceiling in this deployment: gate 9.5"
        subtitle="Stated here rather than discovered at the gate."
      >
        <p className="text-sm text-neutral-700">
          SimForge&rsquo;s held-out adversarial partition does not exist yet, so no run
          started from this console can pass gate 9.5 and no venture can reach gate 12.
          That is <strong>blocked</strong>, not skipped: a run that skipped certification
          would produce a venture reading as fully provisioned that has been certified
          for nothing. There is no override, deliberately.
        </p>
      </Card>

      <Card title="Ventures">
        <Table
          head={["Venture", "Latest run", "Status", "Gate", "Gates passed", "Started", ""]}
          empty="No venture has a Pack yet."
        >
          {rows.map(([venture, run]) => (
            <Row key={venture}>
              <Cell>{venture}</Cell>
              <Cell mono>{run ? run.run_id.slice(0, 8) : "—"}</Cell>
              <Cell>
                {run ? (
                  <Badge severity={runSeverity(run.status)}>{run.status}</Badge>
                ) : (
                  <Badge severity="neutral">never run</Badge>
                )}
              </Cell>
              <Cell mono>{run ? run.current_gate : "—"}</Cell>
              <Cell>{run ? `${run.gates_passed} of 16` : "0 of 16"}</Cell>
              <Cell>{run ? relativeAge(run.started_at) : "—"}</Cell>
              <Cell>
                <Link
                  href={`/provisioning/${encodeURIComponent(venture)}`}
                  className="text-sm underline underline-offset-2"
                >
                  Open →
                </Link>
              </Cell>
            </Row>
          ))}
        </Table>
      </Card>
    </div>
  );
}
