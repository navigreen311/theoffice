import { redirect } from "next/navigation";

import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import {
  api,
  NotAuthenticated,
  type ChainStatus,
  type HealthResponse,
  type IncidentRow,
  type Paged,
} from "@/lib/api";
import { controlSeverity, incidentSeverity, relativeAge } from "@/lib/severity";

export const dynamic = "force-dynamic";

/**
 * Compliance Dashboard — Part 17.
 *
 * The screen this increment exists to get right. Its job is to be honest about what is
 * *not* known, which is harder than reporting what is: an empty incident list and a
 * verified chain look identical whether the checks ran this morning or have never run
 * at all.
 *
 * So control freshness is shown first, above the incidents, and `never_run` is red.
 */
export default async function CompliancePage() {
  let health: HealthResponse;
  let chain: ChainStatus;
  let incidents: Paged<IncidentRow>;

  try {
    [health, chain, incidents] = await Promise.all([
      api.get<HealthResponse>("/api/health"),
      api.get<ChainStatus>("/api/audit/chain"),
      api.get<Paged<IncidentRow>>("/api/incidents?limit=25"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const controls = Object.entries(health.controls).sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className="space-y-6">
      {!health.healthy ? (
        <div className="rounded border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          <strong>{health.unhealthy.length} control(s) not verified:</strong>{" "}
          {health.unhealthy.join(", ")}.
          <span className="ml-1 text-bad/80">
            An absence of findings from a check that did not run is not evidence.
          </span>
        </div>
      ) : null}

      <Card
        title="Control freshness"
        subtitle="Shown above incidents deliberately: a quiet incident list means nothing if the check producing it is stale."
      >
        <Table head={["Control", "State", "Last run", "Checked", "Max age"]}>
          {controls.map(([name, control]) => (
            <Row key={name}>
              <Cell mono>{name}</Cell>
              <Cell>
                <Badge severity={controlSeverity(control.state)}>{control.state}</Badge>
              </Cell>
              <Cell>{relativeAge(control.last_run)}</Cell>
              <Cell>
                {/* The denominator, always. "Verified" without a count cannot be
                    distinguished from "verified nothing". */}
                {control.denominator ?? "—"}
              </Cell>
              <Cell>{control.max_age_days}d</Cell>
            </Row>
          ))}
        </Table>
      </Card>

      <Card
        title="Audit chain"
        subtitle="Until Forges carry per-agent identity this ledger is the only per-agent record anywhere."
      >
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <Badge severity={chain.ok ? "ok" : "critical"}>
            {chain.ok ? "verified" : "BROKEN"}
          </Badge>
          <span className="text-neutral-600">
            {chain.checked_count.toLocaleString()} entries
          </span>
          {chain.tail_gap > 0 ? (
            <Badge severity="warn">
              tail gap {chain.tail_gap} — deletion or rolled-back inserts, investigate
            </Badge>
          ) : null}
          {chain.first_break_audit_id !== null ? (
            <Badge severity="critical">first break at #{chain.first_break_audit_id}</Badge>
          ) : null}
        </div>
        <p className="mt-3 text-xs text-neutral-500">{chain.reason}</p>
      </Card>

      <Card
        title="Open incidents"
        subtitle="Unresolved only. Detections, not workflow — an incident is never edited, and resolving one appends an account of what was done."
      >
        <Table
          head={["Severity", "Kind", "Venture", "Module", "Raised"]}
          empty="No unresolved incidents. Check the control freshness above before reading that as good news — a check that never ran raises nothing."
        >
          {incidents.items.map((incident) => (
            <Row key={incident.incident_id}>
              <Cell>
                <Badge severity={incidentSeverity(incident.severity)}>
                  {incident.severity}
                </Badge>
              </Cell>
              <Cell mono>{incident.kind}</Cell>
              <Cell>{incident.venture_id ?? "—"}</Cell>
              <Cell mono>{incident.module_id ?? "—"}</Cell>
              <Cell>{relativeAge(incident.raised_at)}</Cell>
            </Row>
          ))}
        </Table>
      </Card>
    </div>
  );
}
