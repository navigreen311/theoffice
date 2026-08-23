import { redirect } from "next/navigation";

import { Badge, Card, Cell, Field, Row, Table, inputClass } from "@/components/ui";
import {
  api,
  NotAuthenticated,
  type InstructionDetail,
  type InstructionDiff,
} from "@/lib/api";
import { relativeAge } from "@/lib/severity";

export const dynamic = "force-dynamic";

const CERT_SEVERITY: Record<string, "ok" | "warn" | "bad"> = {
  certified: "ok",
  stale_instructions: "bad",
  stale_forge: "bad",
  in_training: "warn",
  never_certified: "warn",
  failed: "bad",
  revoked: "bad",
};

/**
 * Instruction authoring — author, version, diff, staleness (Part 17).
 *
 * The certification-impact panel is the point of this screen. `content_hash` binds a
 * certification to a specific text, so **publishing a new version invalidates every
 * certification earned against the old one** and the agents holding them stop being
 * assignable on their very next call.
 *
 * That consequence is shown next to the version list rather than discovered afterwards
 * in an incident. An author who cannot see how many agents they are about to decertify
 * is being asked to make a staffing decision without being told it is one.
 *
 * The diff is section-level because the question an author and a reviewer actually ask
 * is whether the never-do list changed, and a line diff buries that in reformatting.
 */
export default async function InstructionPage({
  params,
  searchParams,
}: {
  params: { forge: string; module: string };
  searchParams: { from?: string; to?: string };
}) {
  const forge = decodeURIComponent(params.forge);
  const moduleId = decodeURIComponent(params.module);

  let detail: InstructionDetail;
  try {
    detail = await api.get<InstructionDetail>(
      `/api/instructions/${encodeURIComponent(forge)}/${encodeURIComponent(moduleId)}`,
    );
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  let diff: InstructionDiff | null = null;
  if (searchParams.from && searchParams.to) {
    const q = new URLSearchParams({
      from_version: searchParams.from,
      to_version: searchParams.to,
    });
    diff = await api
      .get<InstructionDiff>(
        `/api/instructions/${encodeURIComponent(forge)}/${encodeURIComponent(moduleId)}/diff?${q}`,
      )
      .catch(() => null);
  }

  const certified = detail.certification_states.certified ?? 0;

  return (
    <div className="space-y-4">
      <Card
        title={`${forge} / ${moduleId}`}
        subtitle="Curriculum, not documentation. content_hash binds certification to this exact text."
      >
        {detail.live ? (
          <div className="flex flex-wrap gap-4 text-sm">
            <span>
              version <strong>{detail.live.instruction_version}</strong>
            </span>
            <span>
              against Forge api <strong>{detail.live.forge_api_version}</strong>
            </span>
            <Badge severity="neutral">{detail.live.version_sensitivity}</Badge>
            <span className="font-mono text-xs text-neutral-500">
              {detail.live.content_hash.slice(0, 16)}…
            </span>
          </div>
        ) : (
          <p className="text-sm text-bad">
            No instructions authored. SimForge has nothing to test against, so no agent
            can be certified for this module and no position operating it can be filled.
          </p>
        )}
      </Card>

      <Card
        title="Certification impact"
        subtitle="Publishing a new version invalidates every certification earned against the current text."
      >
        <div className="flex flex-wrap gap-2">
          {Object.entries(detail.certification_states).length === 0 ? (
            <span className="text-sm text-neutral-500">
              No certifications recorded for this module.
            </span>
          ) : (
            Object.entries(detail.certification_states).map(([state, count]) => (
              <Badge key={state} severity={CERT_SEVERITY[state] ?? "neutral"}>
                {state}: {count}
              </Badge>
            ))
          )}
        </div>
        {certified > 0 ? (
          <p className="mt-3 rounded border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn">
            Authoring a new version will flip these {certified} certification(s) to
            <code className="mx-1">stale_instructions</code>. Those agents stop being
            assignable on their very next call, not their next session.
          </p>
        ) : null}
      </Card>

      <Card title="Versions">
        <form method="get" className="mb-4 grid gap-3 sm:grid-cols-3">
          <Field label="Diff from version">
            <input
              className={inputClass}
              name="from"
              defaultValue={searchParams.from ?? ""}
              placeholder="1.0.0"
            />
          </Field>
          <Field label="to version">
            <input
              className={inputClass}
              name="to"
              defaultValue={searchParams.to ?? ""}
              placeholder="2.0.0"
            />
          </Field>
        </form>

        {diff ? (
          <div className="mb-4 rounded border border-neutral-200 p-3">
            <div className="text-xs font-medium text-neutral-700">
              Section-level diff
            </div>
            <ul className="mt-2 space-y-1 text-xs text-neutral-700">
              <li>
                changed:{" "}
                <span className="font-mono">
                  {diff.changed.length ? diff.changed.join(", ") : "none"}
                </span>
              </li>
              <li>
                added:{" "}
                <span className="font-mono">
                  {diff.added.length ? diff.added.join(", ") : "none"}
                </span>
              </li>
              <li>
                removed:{" "}
                <span className="font-mono">
                  {diff.removed.length ? diff.removed.join(", ") : "none"}
                </span>
              </li>
            </ul>
          </div>
        ) : null}

        <Table
          head={["Version", "Forge api", "Sensitivity", "Authored", "State"]}
          empty="No versions. Nothing has been authored for this module."
        >
          {detail.versions.map((v) => (
            <Row key={v.instruction_version}>
              <Cell mono>{v.instruction_version}</Cell>
              <Cell mono>{v.forge_api_version}</Cell>
              <Cell mono>{v.version_sensitivity}</Cell>
              <Cell>{relativeAge(v.authored_at)}</Cell>
              <Cell>
                <Badge severity={v.superseded_at ? "neutral" : "ok"}>
                  {v.superseded_at ? "superseded" : "live"}
                </Badge>
              </Cell>
            </Row>
          ))}
        </Table>
      </Card>

      {detail.live ? (
        <Card
          title="Current content"
          subtitle="Eight required sections. A curriculum missing its failure signatures reads fine and teaches nothing about the case that matters."
        >
          <pre className="max-h-96 overflow-auto rounded border border-neutral-200 bg-neutral-50 p-3 text-xs">
            {JSON.stringify(detail.live.content, null, 2)}
          </pre>
        </Card>
      ) : null}
    </div>
  );
}
