import Link from "next/link";
import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { AlertTriangle, Check, Minus, X } from "@/components/icons";
import { AsOf } from "@/components/local-time";
import { Term } from "@/components/term";
import {
  api,
  NotAuthenticated,
  type InstructionDirectory,
  type InstructionForge,
  type InstructionModule,
} from "@/lib/api";
import { IDEMPOTENCY, MODULE } from "@/lib/vocabulary";

export const dynamic = "force-dynamic";

/**
 * Forge Operating Instructions — Part 6.1.
 *
 * The column said `authored`, which meant a row exists. The live cre-forge curriculum
 * satisfies that with `"what_it_does": "Documented."`, `"inputs": {"a": "b"}` and
 * `"correct_sequence": ["a", "b"]` — eight sections present, none empty, a valid
 * `content_hash` over the lot, and agents certified against that hash.
 *
 * A hash of the word "Documented." is a valid hash of nothing, and every certification
 * bound to it inherits that emptiness. So the state is assessed from the content, by the
 * same module the validator and the compliance page use: three readers, one answer.
 */

const STATE_TONE: Record<string, string> = {
  complete: "border-ok-line bg-ok-bg text-ok",
  thin: "border-warn-line bg-warn-bg text-warn",
  stub: "border-bad-line bg-bad-bg text-bad",
  missing: "border-bad-line bg-bad-bg text-bad",
};

const STATE_LABEL: Record<string, string> = {
  complete: "complete",
  thin: "thin",
  stub: "stub",
  missing: "sections missing",
};

function StateIcon({ state }: { state: string }) {
  const className = "h-3.5 w-3.5 shrink-0";
  if (state === "complete") return <Check className={`${className} text-ok`} />;
  if (state === "thin") return <AlertTriangle className={`${className} text-warn`} />;
  return <X className={`${className} text-bad`} />;
}

function Metric({
  label,
  value,
  note,
  alarming,
}: {
  label: string;
  value: string;
  note?: string;
  alarming?: boolean;
}) {
  return (
    <div className="rounded-xl bg-surface-muted px-4 py-3">
      <div className="text-desc text-ink-secondary">{label}</div>
      <div
        className={`mt-1 text-[24px] font-medium leading-tight ${
          alarming ? "text-bad" : "text-ink"
        }`}
      >
        {value}
      </div>
      {note ? <p className="mt-1 text-meta text-ink-muted">{note}</p> : null}
    </div>
  );
}

function ModuleRow({ module }: { module: InstructionModule }) {
  const quality = module.quality;
  return (
    <li className="border-t border-line">
      <Link
        href={`/instructions/${encodeURIComponent(module.forge_id)}/${encodeURIComponent(module.module_id)}`}
        className="block px-1 py-2.5 transition hover:bg-surface-muted"
      >
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="self-center">
            <StateIcon state={quality.state} />
          </span>
          <Term value={module.module_id} from={MODULE} />
          <span
            className={`rounded-lg border px-2 py-0.5 text-meta ${STATE_TONE[quality.state]}`}
          >
            {STATE_LABEL[quality.state]} · {quality.complete} of {quality.total} sections
          </span>

          {/* The finding this page exists for. */}
          {module.certifications_on_hollow > 0 ? (
            <span className="rounded-lg border border-bad-line bg-bad-bg px-2 py-0.5 text-meta text-bad">
              {module.certifications_on_hollow} certification
              {module.certifications_on_hollow === 1 ? "" : "s"} rest on it
            </span>
          ) : null}

          {module.idempotency_support === "at_most_once" ? (
            <span
              title="On failure this escalates to a person rather than retrying, because a second attempt might be a second real-world action."
              className="inline-flex flex-wrap items-baseline gap-x-1.5 rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 text-meta text-warn"
            >
              <span>{IDEMPOTENCY.at_most_once}</span>
              <code className="font-mono text-ident opacity-80">at_most_once</code>
            </span>
          ) : null}

          {module.stale_forge ? (
            <span
              title={module.stale_forge}
              className="rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 text-meta text-warn"
            >
              stale — Forge moved to {module.forge_current_version}
            </span>
          ) : null}

          <span className="ml-auto font-mono text-meta text-ink-muted">
            v{module.instruction_version} · against {module.forge_api_version}
          </span>
        </div>
        {quality.state !== "complete" ? (
          <p className="mt-0.5 pl-[1.4rem] text-meta text-ink-muted">
            {quality.placeholder_sections.length
              ? `Placeholder: ${quality.placeholder_sections.join(", ")}. `
              : ""}
            {quality.missing_sections.length
              ? `Missing: ${quality.missing_sections.join(", ")}. `
              : ""}
            {quality.thin_sections.length
              ? `Thin: ${quality.thin_sections.join(", ")}.`
              : ""}
          </p>
        ) : null}
      </Link>
    </li>
  );
}

function Forge({ forge }: { forge: InstructionForge }) {
  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="text-section font-medium text-ink">
          <span className="font-mono">{forge.forge_id}</span>
        </h3>
        <span className="text-meta text-ink-muted">
          {forge.written} of {forge.total} modules written
          {forge.stub ? ` · ${forge.stub} teach nothing` : ""}
          {forge.thin ? ` · ${forge.thin} thin` : ""}
        </span>
      </div>

      <ul className="mt-2">
        {forge.modules.map((module) => (
          <ModuleRow key={module.module_id} module={module} />
        ))}
      </ul>

      {forge.unwritten.length ? (
        <div className="mt-3 border-t border-line pt-3">
          <p className="text-meta text-ink-muted">
            {forge.unwritten.length} module
            {forge.unwritten.length === 1 ? "" : "s"} with no instructions at all:{" "}
            {forge.unwritten.map((m) => m.module_id).join(", ")}. No agent can be
            certified to operate {forge.unwritten.length === 1 ? "it" : "them"}.
          </p>
        </div>
      ) : null}
    </section>
  );
}

export default async function InstructionsPage() {
  let directory: InstructionDirectory;
  try {
    directory = await api.get<InstructionDirectory>("/api/instructions/directory");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const { totals } = directory;

  return (
    <div className="space-y-6">
      <Breadcrumb trail={[{ label: "Dashboard", href: "/" }, { label: "Instructions" }]} />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-page font-medium text-ink">Forge Operating Instructions</h1>
          <p className="mt-1 text-desc text-ink-secondary">
            Curriculum, not documentation. content_hash binds certification to this exact
            text.
          </p>
        </div>
        <span className="text-meta text-ink-muted">
          <AsOf iso={directory.as_of} />
        </span>
      </div>

      {/*
        The portfolio finding. `authored` hid this completely: nine modules, all badged
        authored, none of which describes what it documents.
      */}
      {totals.hollow > 0 ? (
        <section className="rounded-xl border border-bad-line bg-bad-bg px-5 py-4">
          <h2 className="flex items-center gap-1.5 text-section font-medium text-bad">
            <AlertTriangle className="h-4 w-4" />
            {totals.hollow} of {totals.modules_with_instructions} instruction sets teach
            nothing
          </h2>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            Their sections are present and their content is placeholder text.{" "}
            {totals.certifications_on_hollow > 0 ? (
              <>
                {totals.certifications_on_hollow} certification
                {totals.certifications_on_hollow === 1 ? " is" : "s are"} bound to those
                hashes — earned against documents that do not teach the module. They read
                as valid and are not.
              </>
            ) : (
              "No certification rests on them yet."
            )}{" "}
            Validator rule V11 now fails a Pack whose modules are in this state, so no
            venture can provision against them.
          </p>
        </section>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Modules with instructions"
          value={`${totals.modules_with_instructions} of ${totals.modules_with_instructions + totals.modules_without_instructions}`}
          note={`across ${totals.forges_with_instructions} of ${totals.forges_registered} registered Forges`}
        />
        <Metric
          label="Complete"
          value={`${totals.complete} of ${totals.modules_with_instructions}`}
        />
        <Metric
          label="Thin or stub"
          value={`${totals.thin + totals.hollow} of ${totals.modules_with_instructions}`}
          alarming={totals.hollow > 0}
          note={`${totals.hollow} teach nothing`}
        />
        <Metric
          label="Certifications at risk"
          value={String(totals.certifications_on_hollow)}
          alarming={totals.certifications_on_hollow > 0}
          note="Resting on a curriculum that teaches nothing"
        />
      </div>

      <div className="space-y-4">
        {directory.forges.map((forge) => (
          <Forge key={forge.forge_id} forge={forge} />
        ))}
      </div>

      {/*
        Modules the registry knows and nobody has written for. A page listing only what
        it found cannot say what is absent, and an absent curriculum is the reason an
        agent can never be certified on that module.
      */}
      {directory.unwritten.length ? (
        <section className="rounded-xl bg-surface-muted px-5 py-4">
          <h2 className="text-section font-medium text-ink">
            {directory.unwritten.length} module
            {directory.unwritten.length === 1 ? "" : "s"} with no instructions
          </h2>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            No agent can be certified to operate these, because SimForge has nothing to
            test against.
          </p>
          <ul className="mt-2 grid gap-1 sm:grid-cols-2">
            {directory.unwritten.map((module) => (
              <li
                key={`${module.forge_id}-${module.module_id}`}
                className="flex items-center gap-1.5 text-desc text-ink-secondary"
              >
                <Minus className="h-3 w-3 text-ink-muted" />
                <span className="font-mono">
                  {module.forge_id}/{module.module_id}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="text-meta text-ink-muted">
        Publishing a new version invalidates every certification earned against the
        current text.
      </p>
    </div>
  );
}
