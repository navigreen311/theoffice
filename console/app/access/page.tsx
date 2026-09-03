import { redirect } from "next/navigation";

import { AsOf } from "@/components/local-time";
import { Card } from "@/components/ui";
import { api, ApiError, NotAuthenticated, type VentureRow } from "@/lib/api";

import { CreateHumanForm, RoleForm } from "./forms";
import {
  MissingPeopleBanner,
  PrivilegeBanner,
  RoleReference,
  type Concentration,
  type MissingPerson,
  type RoleRow,
} from "./overview";
import { People, SuspendFixtures, type Row } from "./people";

export const dynamic = "force-dynamic";

/**
 * Access — who may operate this system.
 *
 * This screen exists because until it did, **a deployed Office needed somebody with a
 * shell to create its second operator.** The rules it renders are enforced in the API
 * rather than here — a second copy of an authorisation rule is a second copy that
 * eventually disagrees, and the one in the browser would be the one nobody audits. What
 * this screen owes the operator is that the rules are *visible* before they click.
 *
 * What it did not owe them, and delivered anyway, was 179 rows that all looked like
 * colleagues. 178 are fixtures this project's own test paths created, and 94 of those
 * hold `ivan` — the authority for Forge-scope revocation. That was on the page, spread
 * across ninety-five rows, which is the same as not being there.
 *
 * Active revocations used to be duplicated here and on the Revocation page. One
 * implementation, on the page that owns the re-enable ritual; this one links to it.
 */

type Overview = {
  as_of: string;
  accounts: Row[];
  counts: {
    total: number;
    people: number;
    fixtures: number;
    active_fixtures: number;
    never_seen: number;
    mfa_enrolled: number;
  };
  concentration: Concentration;
  missing_people: MissingPerson[];
  unreferenced_roles: string[];
  roles: RoleRow[];
};

function Metric({ label, value, of }: { label: string; value: number; of?: number }) {
  return (
    <div className="rounded-xl border border-line bg-surface-muted px-4 py-3">
      <div className="text-desc text-ink-muted">{label}</div>
      <div className="text-[24px] font-medium leading-tight text-ink">
        {value}
        {of !== undefined ? (
          <span className="text-desc text-ink-muted"> of {of}</span>
        ) : null}
      </div>
    </div>
  );
}

export default async function AccessPage({
  searchParams,
}: {
  searchParams: Record<string, string | undefined>;
}) {
  let overview: Overview;
  let ventures: VentureRow[];

  try {
    [overview, ventures] = await Promise.all([
      api.get<Overview>("/api/access/overview"),
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

  // Real accounts by default. The count that is hidden is stated beside the list, so
  // the filter cannot quietly shrink what the page appears to be about.
  const origin = searchParams.origin ?? "";
  const visible =
    origin === "all"
      ? overview.accounts
      : origin === "test_fixture"
        ? overview.accounts.filter((row) => row.origin === "test_fixture")
        : overview.accounts.filter((row) => row.origin !== "test_fixture");

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-page font-medium text-ink">Access</h1>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            Every action here is audited with you as the actor. A role may be granted only
            by somebody holding a stronger one, and never to yourself.
          </p>
        </div>
        <AsOf iso={overview.as_of} />
      </div>

      <PrivilegeBanner
        concentration={overview.concentration}
        counts={overview.counts}
        action={<SuspendFixtures count={overview.counts.active_fixtures} />}
      />

      <MissingPeopleBanner missing={overview.missing_people} />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="People" value={overview.counts.people} of={overview.counts.total} />
        <Metric label="Test fixtures" value={overview.counts.fixtures} />
        <Metric
          label="Never signed in"
          value={overview.counts.never_seen}
          of={overview.counts.total}
        />
        <Metric
          label="MFA enrolled"
          value={overview.counts.mfa_enrolled}
          of={overview.counts.people}
        />
      </div>

      <RoleReference roles={overview.roles} />

      <People
        people={visible}
        hiddenFixtures={origin === "all" ? 0 : overview.counts.fixtures}
        ventures={ventures.map((venture) => venture.venture_id)}
      />

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Add a person</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Their token is shown once, here, and is not recoverable.
        </p>
        <div className="mt-3">
          <CreateHumanForm
            ventures={ventures.map((venture) => venture.venture_id)}
            holders={Object.fromEntries(
              overview.roles.map((role) => [role.role, role.holders]),
            )}
          />
        </div>
      </section>

      {/* Granting and removing a role. This went missing in the rebuild, which left the
          only route to a role being to create a new account with one - the exact shape
          of over-granting this page now warns about. */}
      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Change a role</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          You may grant a role weaker than your own, and never to yourself — so that
          every role anybody holds was granted by somebody else, and the log says who.
        </p>
        <div className="mt-3">
          <RoleForm
            humans={visible.map((person) => ({
              human_id: person.human_id,
              display_name: person.display_name,
            }))}
            ventures={ventures.map((venture) => venture.venture_id)}
          />
        </div>
      </section>
    </div>
  );
}
