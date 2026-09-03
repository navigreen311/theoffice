import Link from "next/link";

import { AlertTriangle, CircleCheck } from "@/components/icons";

/**
 * What the Access page says before it lists a single person.
 *
 * The roster showed 179 accounts as 179 rows and every one of them looked like a
 * colleague. 178 are test fixtures; 94 of those hold `ivan`, the authority for
 * Forge-scope revocation — each could stop every agent on every Forge in the portfolio.
 * That fact was on the page, spread across ninety-five rows, which is the same as not
 * being there.
 *
 * Two banners, and they are different kinds of problem. Privilege concentration is a
 * live exposure: it is red, it counts, and it offers the action. A person a Pack names
 * who has no account is a blocked gate rather than an exposure — it is amber, and the
 * only useful thing it can do is name them.
 */

export type Concentration = {
  role: string;
  total: number;
  fixtures: number;
  people: number;
  expected_max: number;
  raised: boolean;
  authorises: string[];
  active_fixtures: number;
};

export type MissingPerson = {
  human_name: string;
  role: string;
  venture_id: string;
  reason: string;
};

export type RoleRow = {
  role: string;
  meaning: string;
  revocation_scopes: string[];
  holders: number;
  fixture_holders: number;
  expected_min: number;
  expected_max: number;
  required_by_a_pack: boolean;
  unheld_but_required: boolean;
  over_held: boolean;
};

export function PrivilegeBanner({
  concentration,
  counts,
  action,
}: {
  concentration: Concentration;
  counts: { fixtures: number; active_fixtures: number };
  action: React.ReactNode;
}) {
  if (!concentration.raised) {
    return (
      <section className="rounded-xl border border-ok-line bg-ok-bg px-5 py-4">
        <h2 className="flex items-center gap-1.5 text-section font-medium text-ok">
          <CircleCheck className="h-4 w-4" />
          {concentration.total} account{concentration.total === 1 ? "" : "s"} hold{" "}
          {concentration.role}, all of them people
        </h2>
      </section>
    );
  }

  const scopes = concentration.authorises.join(", ");

  return (
    <section className="rounded-xl border border-bad-line bg-bad-bg px-5 py-4">
      <h2 className="flex items-center gap-1.5 text-section font-medium text-bad">
        <AlertTriangle className="h-4 w-4" />
        {concentration.fixtures} test account
        {concentration.fixtures === 1 ? "" : "s"} hold the highest role in the system
      </h2>

      <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
        {concentration.total} accounts hold{" "}
        <code className="text-ident">{concentration.role}</code> · all ventures.{" "}
        {concentration.people === 1
          ? "One is a real person."
          : `${concentration.people} are real people.`}{" "}
        The rest are fixtures left by this project&rsquo;s own test paths — the smoke
        script and the checks run while building this console each create an account and
        never remove it.
      </p>

      <p className="mt-2 max-w-3xl text-desc text-ink-secondary">
        That role is the authority for{" "}
        <code className="text-ident">{scopes}</code>-scope revocation — each of these can
        stop every agent on every Forge.
        {concentration.active_fixtures > 0
          ? ` ${concentration.active_fixtures} of them are active right now.`
          : " All of them are already suspended."}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Link
          href={`/access?origin=test_fixture&role=${encodeURIComponent(concentration.role)}`}
          className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
        >
          Review the {concentration.fixtures}
        </Link>
        {counts.active_fixtures > 0 ? action : null}
      </div>

      <p className="mt-2 text-meta text-ink-muted">
        Suspension, never deletion. It is reversible and audited, and it leaves the record
        of who held what and who granted it intact — which is the property this page
        exists to protect.
      </p>
    </section>
  );
}

export function MissingPeopleBanner({ missing }: { missing: MissingPerson[] }) {
  if (missing.length === 0) return null;

  return (
    <section className="rounded-xl border border-warn-line bg-warn-bg px-5 py-4">
      <h2 className="flex items-center gap-1.5 text-section font-medium text-warn">
        <AlertTriangle className="h-4 w-4" />
        {missing.map((person) => person.human_name).join(", ")}{" "}
        {missing.length === 1 ? "has" : "have"} no account
      </h2>
      <ul className="mt-2 space-y-1">
        {missing.map((person) => (
          <li key={person.human_name} className="max-w-3xl text-desc text-ink-secondary">
            {person.reason}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * What each role confers, and how many people hold it.
 *
 * Roles were bare strings — `ivan`, `venture_operator`, `compliance_officer` — with no
 * definition anywhere in this console. Somebody granting one could not tell what they
 * were handing over, which is a poor position to be in on the screen whose own copy says
 * a role may only be granted by somebody holding a stronger one.
 */
export function RoleReference({ roles }: { roles: RoleRow[] }) {
  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <h2 className="text-section font-medium text-ink">What each role confers</h2>
      <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
        Revocation scopes come from the authority matrix the API enforces, not from this
        page — a second copy would eventually describe an arrangement that had changed.
      </p>

      <ul className="mt-3">
        {roles.map((role) => (
          <li key={role.role} className="border-t border-line py-3 first:border-t-0">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <code className="text-ident text-ink">{role.role}</code>
              <span className="text-meta text-ink-muted">
                {role.holders} {role.holders === 1 ? "person holds" : "people hold"} it
                {role.fixture_holders > 0
                  ? ` · ${role.fixture_holders} test account${role.fixture_holders === 1 ? "" : "s"} too`
                  : ""}
              </span>
              {role.unheld_but_required ? (
                <span className="rounded-lg border border-bad-line bg-bad-bg px-2 py-0.5 text-meta text-bad">
                  a Pack needs this role and nobody holds it
                </span>
              ) : null}
              {role.over_held ? (
                <span className="rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 text-meta text-warn">
                  more holders than the expected {role.expected_max}
                </span>
              ) : null}
            </div>
            <p className="mt-1 max-w-3xl text-desc text-ink-secondary">{role.meaning}</p>
            {role.revocation_scopes.length > 0 ? (
              <p className="mt-1 text-meta text-ink-muted">
                Authorises revocation at{" "}
                {role.revocation_scopes.map((scope) => (
                  <code key={scope} className="text-ident">
                    {scope}{" "}
                  </code>
                ))}
                scope.
              </p>
            ) : (
              <p className="mt-1 text-meta text-ink-muted">
                Authorises no revocation scope of its own.
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
