import Link from "next/link";
import { redirect } from "next/navigation";

import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import { api, NotAuthenticated, type AgentRow } from "@/lib/api";
import { compareTiers } from "@/lib/severity";

export const dynamic = "force-dynamic";

/**
 * Agent Registry — Part 17: "certified tier vs declared tier side by side".
 *
 * Side by side because Part 10.1 says the certified tier caps the declared one, and a
 * screen showing only one would hide every place they disagree. The disagreement is the
 * information.
 */
export default async function AgentsPage() {
  let agents: AgentRow[];
  try {
    agents = await api.get<AgentRow[]>("/api/agents");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  return (
    <Card
      title="Agent registry"
      subtitle="The Office appoints agents. The Village creates them. Certified tier caps declared tier."
    >
      <Table
        head={[
          "Agent",
          "Department",
          "Status",
          "Grants",
          "Declared",
          "Certified",
          "Effective",
        ]}
        empty="No agents hold Office identities yet. Phase 0.2 issues them from the Village roster."
      >
        {agents.map((agent) => {
          const tiers = compareTiers(
            agent.declared_tier_floor,
            agent.certified_tier_floor,
          );
          return (
            <Row key={agent.office_agent_id}>
              <Cell>
                <Link
                  href={`/agents/${agent.office_agent_id}`}
                  className="font-medium text-neutral-900 underline underline-offset-2"
                >
                  {agent.agent_name}
                </Link>
              </Cell>
              <Cell>{agent.department}</Cell>
              <Cell>
                <Badge severity={agent.status === "active" ? "ok" : "bad"}>
                  {agent.status}
                </Badge>
              </Cell>
              <Cell>{agent.live_grants}</Cell>
              <Cell mono>{agent.declared_tier_floor ?? "—"}</Cell>
              <Cell mono>{agent.certified_tier_floor ?? "—"}</Cell>
              <Cell>
                {tiers.capped ? (
                  <Badge severity="warn">{tiers.note}</Badge>
                ) : (
                  <span className="text-xs text-neutral-500">{tiers.effective ?? "—"}</span>
                )}
              </Cell>
            </Row>
          );
        })}
      </Table>
    </Card>
  );
}
