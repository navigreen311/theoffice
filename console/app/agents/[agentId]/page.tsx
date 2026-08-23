import { redirect } from "next/navigation";

import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import { api, NotAuthenticated, type AgentDetail } from "@/lib/api";
import { compareTiers, relativeAge } from "@/lib/severity";

export const dynamic = "force-dynamic";

/**
 * Agent Identity & Grants — Part 17: "issue, scope, revoke, migration status per Forge".
 *
 * Migration status is on this screen rather than a Forge screen because it changes the
 * strength of the audit guarantee **for this agent's calls**. While a Forge is
 * `brokered`, its own logs attribute everything to the tenant, and the Office ledger is
 * the only record naming this agent. An operator looking at one agent needs that in
 * front of them, not one navigation away.
 */
export default async function AgentPage({ params }: { params: { agentId: string } }) {
  let detail: AgentDetail;
  try {
    detail = await api.get<AgentDetail>(`/api/agents/${params.agentId}`);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const { identity, grants, forge_migration_status, recent_shifts } = detail;
  const brokered = forge_migration_status.filter((f) => f.credential_mode === "brokered");

  return (
    <div className="space-y-6">
      <Card title={identity.agent_name} subtitle={identity.village_agent_ref}>
        <div className="flex flex-wrap gap-4 text-sm">
          <span>
            Department: <strong>{identity.department}</strong>
          </span>
          <Badge severity={identity.status === "active" ? "ok" : "bad"}>
            {identity.status}
          </Badge>
          {identity.revocation_reason ? (
            <span className="text-bad">Reason: {identity.revocation_reason}</span>
          ) : null}
        </div>
      </Card>

      <Card
        title="Grants"
        subtitle="A grant with either certification unit missing is not assignable — certification is the grant condition, not advisory metadata."
      >
        <Table
          head={["Forge", "Module", "Venture", "Declared", "Certified", "Assignable"]}
          empty="No grants. This agent cannot reach any Forge."
        >
          {grants.map((g) => {
            const tiers = compareTiers(g.trust_tier, g.certified_tier);
            return (
              <Row key={g.grant_id}>
                <Cell mono>{g.forge_id}</Cell>
                <Cell mono>{g.module_id}</Cell>
                <Cell>{g.venture_id}</Cell>
                <Cell mono>{g.trust_tier}</Cell>
                <Cell mono>{g.certified_tier ?? "—"}</Cell>
                <Cell>
                  {g.revoked_at ? (
                    <Badge severity="bad">revoked</Badge>
                  ) : g.is_assignable ? (
                    <Badge severity={tiers.capped ? "warn" : "ok"}>
                      {tiers.capped ? tiers.note : "assignable"}
                    </Badge>
                  ) : (
                    <Badge severity="bad">
                      {g.unit_a_state ?? "never_certified"}
                    </Badge>
                  )}
                </Cell>
              </Row>
            );
          })}
        </Table>
      </Card>

      <Card
        title="Forge migration status"
        subtitle="Brokered means the Forge logs attribute every call to the tenant — the Office ledger is the only record naming this agent."
      >
        <Table head={["Forge", "Credential mode", "Health"]}>
          {forge_migration_status.map((f) => (
            <Row key={f.forge_id}>
              <Cell mono>{f.forge_id}</Cell>
              <Cell>
                <Badge severity={f.credential_mode === "native" ? "ok" : "warn"}>
                  {f.credential_mode}
                </Badge>
              </Cell>
              <Cell>
                <Badge severity={f.health_status === "RED" ? "bad" : "ok"}>
                  {f.health_status}
                </Badge>
              </Cell>
            </Row>
          ))}
        </Table>
        {brokered.length > 0 ? (
          <p className="mt-3 text-xs text-neutral-600">
            {brokered.length} Forge(s) still brokered. Reconciliation can verify call
            counts and payload hashes against them but cannot independently corroborate
            attribution — a stated weakness, not a hidden one.
          </p>
        ) : null}
      </Card>

      <Card
        title="Recent shifts"
        subtitle="One venture per agent per shift. A failed PHI flush blocks the next assignment."
      >
        <Table
          head={["Venture", "Start", "End", "Flush"]}
          empty="Never assigned to a shift."
        >
          {recent_shifts.map((s) => (
            <Row key={s.shift_id}>
              <Cell>{s.venture_id}</Cell>
              <Cell>{relativeAge(s.shift_start)}</Cell>
              <Cell>{relativeAge(s.shift_end)}</Cell>
              <Cell>
                <Badge severity={s.flush_verified ? "ok" : "bad"}>
                  {s.flush_verified ? "verified" : "not verified"}
                </Badge>
              </Cell>
            </Row>
          ))}
        </Table>
      </Card>
    </div>
  );
}
