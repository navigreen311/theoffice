import Link from "next/link";
import { redirect } from "next/navigation";

import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import { api, NotAuthenticated, type ForgeRow } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Forge Operating Instructions — the index.
 *
 * Part 6.1 calls these the curriculum, not a filing cabinet: they are what agents are
 * educated on and what SimForge tests against. So the column that matters most here is
 * whether a module has any at all — **a module with no instructions can never be
 * certified, so its position can never be filled.** That is a staffing blocker showing
 * up as a documentation gap, which is exactly the kind of thing nobody notices until an
 * appointment comes back empty.
 */
export default async function InstructionsPage() {
  let forges: ForgeRow[];
  try {
    forges = await api.get<ForgeRow[]>("/api/forges");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const missing = forges.flatMap((f) =>
    f.modules
      .filter((m) => !m.has_instructions)
      .map((m) => `${f.forge_id}/${m.module_id}`),
  );

  return (
    <div className="space-y-4">
      {missing.length > 0 ? (
        <div className="rounded border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-warn">
          <strong>{missing.length} module(s) have no authored instructions.</strong>{" "}
          SimForge has nothing to test against, so no agent can be certified for them and
          no position operating them can be filled.
        </div>
      ) : null}

      {forges.length === 0 ? (
        <Card title="No Forges registered">
          <p className="text-sm text-neutral-600">
            The bridge reaches nothing yet. Phase 0.3 registers a Forge with a
            credential.
          </p>
        </Card>
      ) : null}

      {forges.map((forge) => (
        <Card
          key={forge.forge_id}
          title={forge.display_name}
          subtitle={`${forge.forge_id} · api ${forge.api_version} · ${forge.credential_mode}`}
        >
          <Table
            head={["Module", "Instructions", "Version", "Sensitivity", "Idempotency"]}
            empty="No modules registered for this Forge."
          >
            {forge.modules.map((m) => (
              <Row key={m.module_id}>
                <Cell>
                  <Link
                    href={`/instructions/${encodeURIComponent(forge.forge_id)}/${encodeURIComponent(m.module_id)}`}
                    className="font-mono text-xs underline underline-offset-2"
                  >
                    {m.module_id}
                  </Link>
                </Cell>
                <Cell>
                  <Badge severity={m.has_instructions ? "ok" : "bad"}>
                    {m.has_instructions ? "authored" : "none"}
                  </Badge>
                </Cell>
                <Cell mono>{m.instruction_version ?? "—"}</Cell>
                <Cell mono>{m.version_sensitivity ?? "—"}</Cell>
                <Cell>
                  {/* at_most_once is called out because the call path refuses to
                      auto-retry it — a replay escalates to a human instead. */}
                  <Badge
                    severity={
                      m.idempotency_support === "at_most_once" ? "warn" : "neutral"
                    }
                  >
                    {m.idempotency_support}
                  </Badge>
                </Cell>
              </Row>
            ))}
          </Table>
        </Card>
      ))}
    </div>
  );
}
