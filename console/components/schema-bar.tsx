/**
 * How much of the schema a Pack fills in. A different question from validation: a Pack
 * can be schema-complete and still fail rules, or be missing an optional block no rule
 * covers yet.
 *
 * Shared by the Packs directory and the editor's block sidebar. Two implementations of
 * one number is how the two screens come to disagree about whether a Pack is complete —
 * the same reason `packs.validation_state` is one function rather than two.
 *
 * `label` exists because the sidebar has 200px and the directory has a card: "Schema
 * blocks" reads well in one and crowds the other out.
 */
export function SchemaBar({
  present,
  total,
  missing = [],
  requiredMissing = [],
  label = "Schema blocks",
  compact = false,
}: {
  present: number;
  total: number;
  missing?: string[];
  requiredMissing?: string[];
  label?: string;
  compact?: boolean;
}) {
  const pct = total === 0 ? 0 : Math.round((present / total) * 100);

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-meta text-ink-muted">{label}</span>
        <span className="text-meta text-ink-secondary">
          {present} of {total}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-muted">
        <div
          className={`h-full rounded-full ${
            requiredMissing.length ? "bg-bad" : "bg-ok"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {!compact && missing.length ? (
        <p className="mt-1 text-meta text-ink-muted">
          {requiredMissing.length ? (
            <span className="text-bad">
              required: {requiredMissing.join(", ")}.{" "}
            </span>
          ) : null}
          {missing.filter((block) => !requiredMissing.includes(block)).join(", ") ||
            null}
          {requiredMissing.length ? null : " — all optional"}
        </p>
      ) : null}
    </div>
  );
}
