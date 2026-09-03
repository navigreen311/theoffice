/** Where the provisioning run listing is asked for, and the one flag that widens it. */

/**
 * `true` only in the smoke environment.
 *
 * The listing filters out runs started by a test-fixture account, because
 * `scripts/console-smoke.sh` drives one run per invocation and 104 of them made the
 * console read as a system that cannot get past gate 4. That filter is right, and it
 * is why the console shows an operator what is actually happening.
 *
 * It also made the gate ladder impossible to smoke-test. The smoke script signs in as
 * `smoke-<suffix>@example.invalid`, which `broker.account_origin` classifies as a
 * fixture, so the run it creates to exercise the ladder is the one run the page will
 * not show. It rendered its empty state and thirty-one checks failed on a page that was
 * working - the ladder had nothing to draw.
 *
 * So the widening is an environment flag rather than a fallback in the page. A fallback
 * - show fixtures when the real list is empty - would put the fixture runs back in front
 * of an operator in exactly the situation the filter exists for: a venture with no real
 * runs yet. The filter's whole job is to stop that page saying something untrue about
 * the state of the system, and a page that quietly changes what it means depending on
 * whether a list came back empty is harder to trust than one that does not.
 *
 * Set by the smoke script on `next start`. Nothing sets it in production, and if
 * something did, the page would show fixture runs and say so rather than mislead.
 */
export const SHOW_FIXTURE_RUNS = process.env.OFFICE_CONSOLE_SHOW_FIXTURE_RUNS === "1";

/** The runs listing for one venture, widened only where the flag is set. */
export function runsPath(venture: string): string {
  const base = `/api/provisioning/runs?venture_id=${encodeURIComponent(venture)}`;
  return SHOW_FIXTURE_RUNS ? `${base}&include_fixtures=true` : base;
}
