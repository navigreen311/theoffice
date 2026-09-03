import Link from "next/link";
import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { AlertTriangle, Check, Minus, X } from "@/components/icons";
import { AsOf, Ago } from "@/components/local-time";
import {
  api,
  NotAuthenticated,
  type BoundCertification,
  type CurriculumQuality,
  type CurriculumSection,
} from "@/lib/api";

import { Authoring, RawCurriculum, Versions } from "./authoring";

export const dynamic = "force-dynamic";

/**
 * One module's curriculum.
 *
 * The page dumped the content as raw JSON under an `authored` badge. The content it was
 * dumping is `"what_it_does": "Documented."` — so the badge was true in the sense the
 * old rule meant and false in every sense that matters, and the JSON made it a reader's
 * job to notice.
 *
 * Now: each of the eight sections on its own row, with the specific reason it fails.
 * "Placeholder — the entire section reads 'Documented.'" is actionable; a green badge
 * over a JSON blob is not.
 */

type Detail = {
  as_of: string;
  forge_id: string;
  module_id: string;
  live: {
    instruction_version: string;
    forge_api_version: string;
    version_sensitivity: string;
    content_hash: string;
    content: Record<string, unknown>;
  } | null;
  quality: CurriculumQuality;
  certifications_bound: BoundCertification[];
  versions: {
    instruction_version: string;
    forge_api_version: string;
    version_sensitivity: string;
    content_hash: string;
    author: string | null;
    authored_at: string;
    superseded_at: string | null;
  }[];
  certification_states: Record<string, number>;
};

function SectionIcon({ state }: { state: string }) {
  const className = "mt-0.5 h-3.5 w-3.5 shrink-0";
  if (state === "complete") return <Check className={`${className} text-ok`} />;
  if (state === "thin") return <AlertTriangle className={`${className} text-warn`} />;
  if (state === "missing") return <Minus className={`${className} text-bad`} />;
  return <X className={`${className} text-bad`} />;
}

/** One section, with its content or the specific reason it fails. */
function Section({
  section,
  value,
}: {
  section: CurriculumSection;
  value: unknown;
}) {
  const body =
    typeof value === "string"
      ? value
      : Array.isArray(value)
        ? null
        : value && typeof value === "object"
          ? null
          : String(value ?? "");

  return (
    <li className="flex gap-2 border-t border-line py-2.5">
      <SectionIcon state={section.state} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <span className="text-[14px] font-medium text-ink">{section.title}</span>
          <code className="text-ident text-ink-muted">{section.section}</code>
        </div>

        {/* The reason names the defect, for whoever has to fix it. */}
        {section.reason ? (
          <p
            className={`mt-0.5 text-meta ${
              section.state === "thin" ? "text-warn" : "text-bad"
            }`}
          >
            {section.reason}
          </p>
        ) : null}

        {body !== null && body !== "" ? (
          <p className="mt-1 text-desc text-ink-secondary">{body}</p>
        ) : null}

        {Array.isArray(value) && value.length ? (
          <ul className="mt-1 space-y-0.5">
            {value.map((entry, index) => (
              <li key={index} className="text-desc text-ink-secondary">
                · {String(entry)}
              </li>
            ))}
          </ul>
        ) : null}

        {value && typeof value === "object" && !Array.isArray(value) ? (
          <dl className="mt-1 space-y-0.5">
            {Object.entries(value as Record<string, unknown>).map(([key, entry]) => (
              <div key={key} className="flex flex-wrap gap-x-2">
                <dt className="font-mono text-meta text-ink-muted">{key}</dt>
                <dd className="text-desc text-ink-secondary">{String(entry)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </li>
  );
}

export default async function InstructionDetailPage({
  params,
}: {
  params: { forge: string; module: string };
}) {
  const forge = decodeURIComponent(params.forge);
  const moduleId = decodeURIComponent(params.module);

  let detail: Detail;
  try {
    detail = await api.get<Detail>(
      `/api/instructions/${encodeURIComponent(forge)}/${encodeURIComponent(moduleId)}`,
    );
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const { quality, live } = detail;
  const bound = detail.certifications_bound;
  const content = (live?.content ?? {}) as Record<string, unknown>;

  return (
    <div className="space-y-6">
      <Breadcrumb
        trail={[
          { label: "Dashboard", href: "/" },
          { label: "Instructions", href: "/instructions" },
          { label: moduleId },
        ]}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-page font-medium text-ink">
            <span className="font-mono">{moduleId}</span>
          </h1>
          <p className="mt-1 text-desc text-ink-secondary">
            Curriculum, not documentation. content_hash binds certification to this exact
            text.
          </p>
        </div>
        <span className="text-meta text-ink-muted">
          <AsOf iso={detail.as_of} />
        </span>
      </div>

      {/*
        The blocking finding: agents certified against a document that does not teach the
        module. Named, not counted — these are people whose certifications have to be
        redone.
      */}
      {quality.teaches_nothing && bound.length > 0 ? (
        <section className="rounded-xl border border-bad-line bg-bad-bg px-5 py-4">
          <h2 className="flex items-center gap-1.5 text-section font-medium text-bad">
            <AlertTriangle className="h-4 w-4" />
            This curriculum is a {quality.state === "missing" ? "fragment" : "stub"}, and{" "}
            {bound.length} agent{bound.length === 1 ? " is" : "s are"} certified against
            it
          </h2>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            {/* Precise, because "5 of 8 contain placeholder text" would count the thin
                one, and thin is real content that does not go far enough — a different
                problem needing different work. */}
            {quality.placeholder_sections.length} of {quality.total} sections contain
            placeholder text rather than content
            {quality.missing_sections.length
              ? `, ${quality.missing_sections.length} more are absent`
              : ""}
            {quality.thin_sections.length
              ? `, and ${quality.thin_sections.length} are thin`
              : ""}
            . Those certifications were earned against a document that does not teach the
            module. They read as valid and are not.
          </p>
          <ul className="mt-2 space-y-0.5">
            {bound.map((cert) => (
              <li key={cert.office_agent_id} className="text-desc text-ink-secondary">
                <Link
                  href={`/agents/${encodeURIComponent(cert.office_agent_id)}`}
                  className="underline underline-offset-2"
                >
                  {cert.agent_name ?? cert.office_agent_id.slice(0, 8)}
                </Link>{" "}
                <span className="text-ink-muted">
                  {cert.department} · {cert.state} · {cert.certified_tier}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-section font-medium text-ink">The eight sections</h2>
          <span className="text-meta text-ink-muted">
            {quality.complete} of {quality.total} complete
            {live ? ` · v${live.instruction_version}` : ""}
          </span>
        </div>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Eight required sections. A curriculum missing its failure signatures reads fine
          and teaches nothing about the case that matters.
        </p>

        <ul className="mt-3">
          {quality.sections.map((section) => (
            <Section
              key={section.section}
              section={section}
              value={content[section.section]}
            />
          ))}
        </ul>

        <div className="mt-3 border-t border-line pt-3">
          <RawCurriculum content={content} />
        </div>
      </section>

      <Authoring
        forge={forge}
        moduleId={moduleId}
        content={content}
        certificationCount={bound.length}
        agentNames={bound.map((c) => c.agent_name ?? "an agent")}
        currentVersion={live?.instruction_version ?? null}
        forgeApiVersion={live?.forge_api_version ?? ""}
      />

      <Versions versions={detail.versions} />
    </div>
  );
}
