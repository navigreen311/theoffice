import { redirect } from "next/navigation";

import { Ago } from "@/components/local-time";
import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import {
  api,
  ApiError,
  NotAuthenticated,
  type HumanRow,
  type RevocationRow,
  type VentureRow,
} from "@/lib/api";
import { relativeAge } from "@/lib/severity";

import {
  CreateHumanForm,
  ReinstateForm,
  ReissueForm,
  RoleForm,
  StatusForm,
} from "./forms";

export const dynamic = "force-dynamic";

/**
 * Access — who may operate this system, and what is currently revoked.
 *
 * This screen exists because until it did, **a deployed Office needed somebody with a
 * shell to create its second operator.** `create_human` and `grant_role` were domain
 * functions called by tests and by the smoke script, and by nothing a human could reach.
 *
 * It is the most privilege-sensitive screen in the console, and the rules it renders are
 * enforced in the API rather than here — a second copy of an authorisation rule is a
 * second copy that eventually disagrees, and the one in the browser would be the one
 * nobody audits. What this screen owes the operator is that the rules are *visible*
 * before they click, not that it re-checks them.
 */
export default async function AccessPage() {
  let humans: HumanRow[];
  let revocations: RevocationRow[];
  let ventures: VentureRow[];

  try {
    [humans, revocations, ventures] = await Promise.all([
      api.get<HumanRow[]>("/api/humans"),
      api.get<RevocationRow[]>("/api/revocations"),
      api.get<VentureRow[]>("/api/ventures"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    // A venture operator can reach this URL and must not see the roster. Who holds
    // `ivan` is a map of whom to compromise, so the refusal is explained rather than
    // rendered as a broken page.
    if (error instanceof ApiError && error.status === 403) {
      return (
        <Card title="Not your screen">
          <p className="text-sm text-ink-secondary">
            Access administration requires <code>compliance_officer</code> or above. The
            roster of who can act on this system — and which of them holds{" "}
            <code>ivan</code> — is not a read for a venture operator.
          </p>
        </Card>
      );
    }
    throw error;
  }

  const ventureIds = ventures.map((v) => v.venture_id);
  const administrators = humans.filter(
    (h) => h.status === "active" && h.roles.some((r) => r.role === "ivan"),
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold">Access</h2>
        <p className="mt-1 text-xs text-ink-muted">
          Every action here is audited with you as the actor. A role may be granted only
          by somebody holding a stronger one, and never to yourself.
        </p>
      </div>

      {/* The number that must never reach zero. A system with no administrator cannot
          appoint one, and the only recovery is a shell on the database — which is the
          dependency this screen exists to remove. */}
      <Card title="Administrators">
        <div className="flex flex-wrap items-center gap-3">
          <Badge severity={administrators.length > 1 ? "ok" : "warn"}>
            {administrators.length} active
          </Badge>
          <span className="text-sm text-ink-secondary">
            {administrators.map((a) => a.display_name).join(", ") || "none"}
          </span>
        </div>
        {administrators.length < 2 ? (
          <p className="mt-2 text-xs text-warn">
            One administrator is a single point of failure. The last one cannot be
            suspended or demoted — that guard keeps the system administrable, and it is
            not a substitute for a second person.
          </p>
        ) : null}
      </Card>

      <Card title="People" subtitle="Status is read live: a suspension takes effect on their next request.">
        <Table
          head={["Name", "Email", "Roles", "Status", "Created", ""]}
          empty="Nobody has access. That cannot happen while you are reading this."
        >
          {humans.map((h) => (
            <Row key={h.human_id}>
              <Cell>{h.display_name}</Cell>
              <Cell mono>{h.email}</Cell>
              <Cell>
                {h.roles.length === 0 ? (
                  <Badge>no role — cannot act</Badge>
                ) : (
                  <span className="flex flex-wrap gap-1">
                    {h.roles.map((r) => (
                      <Badge
                        key={`${r.role}-${r.venture_id ?? "*"}`}
                        severity={r.role === "ivan" ? "warn" : "neutral"}
                      >
                        {r.role}
                        {r.venture_id ? ` · ${r.venture_id}` : " · all"}
                      </Badge>
                    ))}
                  </span>
                )}
              </Cell>
              <Cell>
                <Badge severity={h.status === "active" ? "ok" : "bad"}>{h.status}</Badge>
              </Cell>
              <Cell><Ago iso={h.created_at} /></Cell>
              <Cell>
                <div className="space-y-3">
                  <StatusForm humanId={h.human_id} status={h.status} />
                  <ReissueForm humanId={h.human_id} self={false} />
                </div>
              </Cell>
            </Row>
          ))}
        </Table>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title="Add a person"
          subtitle="Their token is shown once, here, and is not recoverable."
        >
          <CreateHumanForm ventures={ventureIds} />
        </Card>

        <Card title="Change a role">
          <RoleForm
            humans={humans.map((h) => ({
              human_id: h.human_id,
              display_name: h.display_name,
            }))}
            ventures={ventureIds}
          />
        </Card>
      </div>

      <Card
        title="Active revocations"
        subtitle="Revocation is the kill switch, checked on every call and never cached. Lifting one is a decision worth a sentence."
      >
        <Table
          head={["Scope", "Subject", "Reason", "Revoked", "By role", ""]}
          empty="Nothing is revoked."
        >
          {revocations.map((r) => (
            <Row key={r.revocation_id}>
              <Cell>
                <Badge severity="bad">{r.scope}</Badge>
              </Cell>
              <Cell>
                {r.agent_name ??
                  r.forge_id ??
                  r.venture_id ??
                  r.office_agent_id ??
                  "—"}
                {r.module_id ? ` · ${r.module_id}` : ""}
              </Cell>
              <Cell>{r.reason}</Cell>
              <Cell><Ago iso={r.revoked_at} /></Cell>
              <Cell mono>{r.revoked_by_role}</Cell>
              <Cell>
                <ReinstateForm revocationId={r.revocation_id} />
              </Cell>
            </Row>
          ))}
        </Table>
      </Card>
    </div>
  );
}
