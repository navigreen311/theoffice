import { redirect } from "next/navigation";

import { Card } from "@/components/ui";
import { NotAuthenticated, api } from "@/lib/api";

import { RevokeForm } from "./form";

export const dynamic = "force-dynamic";

const SCOPES = [
  {
    scope: "agent_module",
    authority: "venture_operator",
    effect: "One grant revoked.",
    fields: ["office_agent_id", "forge_id", "module_id"],
  },
  {
    scope: "agent",
    authority: "venture_operator",
    effect: "This agent cannot reach any Forge.",
    fields: ["office_agent_id"],
  },
  {
    scope: "venture",
    authority: "compliance_officer",
    effect: "Every grant for this engagement, including ones issued later.",
    fields: ["venture_id"],
  },
  {
    scope: "forge",
    authority: "ivan",
    effect: "The broker refuses all calls to this Forge, for every agent.",
    fields: ["forge_id"],
  },
];

/**
 * Revocation Controls — Part 17, and §1.4.
 *
 * With no queue to drain and no front desk to stop, revocation is the kill switch. The
 * screen states the blast radius of each scope next to the control, because "revoke" on
 * a Forge and "revoke" on one grant are the same word for very different acts.
 */
export default async function RevocationsPage() {
  try {
    await api.get("/api/health");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  return (
    <div className="space-y-6">
      <Card
        title="Revocation"
        subtitle="Checked live at the broker on every call, never cached — a revoked agent's NEXT call fails, not its next session."
      >
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-left">
              <th className="px-2 py-2 text-xs font-medium text-neutral-500">Scope</th>
              <th className="px-2 py-2 text-xs font-medium text-neutral-500">Effect</th>
              <th className="px-2 py-2 text-xs font-medium text-neutral-500">Authority</th>
            </tr>
          </thead>
          <tbody>
            {SCOPES.map((s) => (
              <tr key={s.scope} className="border-b border-neutral-100 last:border-0">
                <td className="px-2 py-2 font-mono text-xs">{s.scope}</td>
                <td className="px-2 py-2">{s.effect}</td>
                <td className="px-2 py-2 font-mono text-xs">{s.authority}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-neutral-500">
          The console does not pre-check your authority. The API checks it twice — role
          strength for the scope, and whether you operate that venture — and reports the
          refusal. A second opinion here would eventually disagree with the first.
        </p>
      </Card>

      <RevokeForm />
    </div>
  );
}
