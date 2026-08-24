import { redirect } from "next/navigation";

import { Pager } from "@/components/pager";
import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import { api, NotAuthenticated, type IncidentRow, type Paged } from "@/lib/api";
import { incidentSeverity, relativeAge } from "@/lib/severity";

import { ResolveIncidentForm } from "../access/forms";

export const dynamic = "force-dynamic";

/**
 * Incidents, and the one thing that closes one.
 *
 * `/api/incidents` was GET-only, and `historical_record.record_type` has carried an
 * `incident_resolved` value that nothing wrote since the knowledge bases landed — an
 * enum with no producer, which is a smaller version of the hardcoded list Gate 6 used
 * to have.
 *
 * **Resolving appends; it never edits.** The `incident` table is append-only by design:
 * "an incident is never edited; a later finding is a new incident referencing the
 * trace." A detection that can be rewritten is worth less than the row it sits in, and
 * severity is exactly the field somebody under pressure would want to lower. So this
 * screen offers no way to change one — only to record what was done about it.
 */
export default async function IncidentsPage({
  searchParams,
}: {
  searchParams: { severity?: string; resolved?: string; limit?: string; offset?: string };
}) {
  const includeResolved = searchParams.resolved === "true";
  const query = new URLSearchParams({
    limit: searchParams.limit ?? "50",
    offset: searchParams.offset ?? "0",
    include_resolved: String(includeResolved),
  });
  if (searchParams.severity) query.set("severity", searchParams.severity);

  let page: Paged<IncidentRow>;
  try {
    page = await api.get<Paged<IncidentRow>>(`/api/incidents?${query}`);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-base font-semibold">Incidents</h2>
          <p className="mt-1 text-xs text-ink-muted">
            Detections, not workflow. An incident is never edited — resolving one appends
            an account of what was done and leaves the detection intact.
          </p>
        </div>
        <a
          href={`/incidents?resolved=${includeResolved ? "false" : "true"}`}
          className="text-sm underline underline-offset-2"
        >
          {includeResolved ? "open only" : "include resolved"} →
        </a>
      </div>

      <Card
        title={includeResolved ? "All incidents" : "Open incidents"}
        subtitle="An empty list is only good news if the checks that raise these are fresh — see the compliance dashboard."
      >
        <Table
          head={["Severity", "Kind", "Venture", "Raised", "State", ""]}
          empty="Nothing matches. Check control freshness before reading that as quiet."
        >
          {page.items.map((incident) => (
            <Row key={incident.incident_id}>
              <Cell>
                <Badge severity={incidentSeverity(incident.severity)}>
                  {incident.severity}
                </Badge>
              </Cell>
              <Cell mono>{incident.kind}</Cell>
              <Cell>{incident.venture_id ?? "—"}</Cell>
              <Cell>{relativeAge(incident.raised_at)}</Cell>
              <Cell>
                {incident.resolved_at ? (
                  <div className="space-y-1">
                    <Badge severity="ok">
                      resolved {relativeAge(incident.resolved_at)}
                    </Badge>
                    <p className="text-xs text-ink-secondary">{incident.resolution}</p>
                  </div>
                ) : (
                  <Badge severity="warn">open</Badge>
                )}
              </Cell>
              <Cell>
                {incident.resolved_at ? (
                  <span className="text-xs text-ink-muted">
                    Closed. A later finding is a new incident, not an edit to this one.
                  </span>
                ) : (
                  <ResolveIncidentForm incidentId={incident.incident_id} />
                )}
              </Cell>
            </Row>
          ))}
        </Table>

        <Pager
          page={page}
          basePath="/incidents"
          params={{
            severity: searchParams.severity,
            resolved: searchParams.resolved,
          }}
        />
      </Card>
    </div>
  );
}
