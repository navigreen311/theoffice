"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { Badge, Button, Cell, Field, Row, Table, inputClass } from "@/components/ui";
import { validationSummary } from "@/lib/severity";

import { publishAction, validateAction, type EditorState } from "./actions";

/**
 * The Pack editor.
 *
 * Two forms, not one form with two buttons. Validate writes nothing and Publish
 * supersedes the live Pack; they are different acts and a shared submit handler makes
 * them one keystroke apart. `useFormState` from `react-dom` rather than
 * `useActionState` — this is React 18.3.1, where the latter type-checks, builds, and
 * throws at render.
 */

function Submit({ label, busy }: { label: string; busy: string }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending}>
      {pending ? busy : label}
    </Button>
  );
}

function Report({ state }: { state: EditorState | null }) {
  if (!state) return null;
  if (state.error) {
    return (
      <p className="mt-3">
        <Badge severity="bad">{state.error}</Badge>
      </p>
    );
  }
  if (state.ok) {
    return (
      <p className="mt-3">
        <Badge severity="ok">{state.ok}</Badge>
      </p>
    );
  }
  const report = state.report;
  if (!report) return null;

  if (!report.parsed) {
    return (
      <p className="mt-3">
        <Badge severity="bad">Not a Business Pack: {report.error}</Badge>
      </p>
    );
  }

  const summary = validationSummary({
    failures: report.failures,
    warnings: report.warnings,
    not_run: report.not_run,
    rules_checked: report.rules_checked ?? report.results.length,
  });

  // Everything that is not a PASS, in rule order. PASS rows are omitted because
  // twenty-odd green lines is how three red ones get skimmed past - but the
  // denominator stays on screen, so "nothing to show" cannot be mistaken for
  // "nothing was checked".
  const notable = report.results.filter((r) => r.verdict !== "PASS");

  return (
    <div className="mt-4 space-y-3">
      <div className="flex items-center gap-3">
        <Badge severity={summary.severity}>{summary.text}</Badge>
        {report.not_run.length > 0 ? (
          <span className="text-xs text-neutral-600">
            NOT_RUN is not a pass — those rules need the world, and nothing about this
            document answers them.
          </span>
        ) : null}
      </div>
      <Table
        head={["Rule", "Severity", "Verdict", "Message"]}
        empty={`All ${report.rules_checked ?? report.results.length} rules passed.`}
      >
        {notable.map((r) => (
          <Row key={r.rule_id}>
            <Cell mono>{r.rule_id}</Cell>
            <Cell>{r.severity}</Cell>
            <Cell>
              <Badge
                severity={
                  r.verdict === "FAIL" ? "bad" : r.verdict === "WARN" ? "warn" : "neutral"
                }
              >
                {r.verdict}
              </Badge>
            </Cell>
            <Cell>{r.message}</Cell>
          </Row>
        ))}
      </Table>
    </div>
  );
}

export function PackEditor({
  initialSource,
  liveVersion,
  activeRun,
  signatures,
}: {
  initialSource: string;
  liveVersion: string | null;
  activeRun: { run_id: string; status: string; current_gate: string } | null;
  signatures: number;
}) {
  const [source, setSource] = useState(initialSource);
  const [validation, validate] = useFormState(validateAction, null);
  const [publication, publish] = useFormState(publishAction, null);

  const dirty = source !== initialSource;

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-neutral-200 bg-white shadow-sm">
        <header className="border-b border-neutral-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-neutral-900">
            Pack source{liveVersion ? ` — live version ${liveVersion}` : " — no live version"}
          </h2>
          <p className="mt-0.5 text-xs text-neutral-500">
            YAML, schema v3. The hash is taken over these exact bytes, because a reviewer
            signs a document rather than a parse tree.
          </p>
        </header>
        <div className="p-4">
          <textarea
            className={`${inputClass} font-mono`}
            rows={24}
            spellCheck={false}
            value={source}
            onChange={(e) => setSource(e.target.value)}
            aria-label="Pack YAML source"
          />

          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <form action={validate}>
              <input type="hidden" name="yaml_source" value={source} />
              <p className="mb-2 text-xs text-neutral-600">
                Runs all 27 rules against this draft. Writes nothing.
              </p>
              <Submit label="Validate" busy="Validating…" />
            </form>

            <form action={publish} className="space-y-2">
              <input type="hidden" name="yaml_source" value={source} />
              <Field
                label="New version"
                hint="Supersedes the live Pack. Does not start a run."
              >
                <input className={inputClass} name="pack_version" placeholder="1.1.0" />
              </Field>
              <Submit label="Publish" busy="Publishing…" />
            </form>
          </div>

          {/* What publishing will disturb, said before it happens rather than
              discovered afterwards. Both facts are invisible from an editor. */}
          <div className="mt-4 space-y-1 text-xs text-neutral-600">
            {activeRun ? (
              <p>
                <Badge severity="warn">
                  Run {activeRun.run_id.slice(0, 8)} is {activeRun.status} at gate{" "}
                  {activeRun.current_gate}
                </Badge>{" "}
                — it is pinned to the version it started from, so publishing does not
                change what it provisions. A new run picks up the new Pack.
              </p>
            ) : null}
            {signatures > 0 ? (
              <p>
                <Badge severity="warn">
                  {signatures} Gate 10 signature{signatures === 1 ? "" : "s"} on record
                </Badge>{" "}
                — void against the artifacts a changed Pack generates. Nothing revokes
                them; they stop matching, and Gate 11 refuses to activate.
              </p>
            ) : null}
            {dirty ? <p>Unsaved edits. Nothing is written until you publish.</p> : null}
          </div>

          <Report state={validation} />
          <Report state={publication} />
        </div>
      </div>
    </div>
  );
}
