import type { ReactNode } from "react";

import { SEVERITY_CLASS, type Severity } from "@/lib/severity";

/**
 * Hand-written primitives following shadcn/ui conventions.
 *
 * `shadcn init` is an interactive CLI, and an interactive prompt in this environment
 * hangs rather than fails. These are the five primitives the current screens need, in
 * the same shape shadcn generates, so running the real CLI later drops in on top.
 */

export function Card({
  title,
  subtitle,
  children,
}: {
  title?: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-neutral-200 bg-white shadow-sm">
      {title ? (
        <header className="border-b border-neutral-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-neutral-900">{title}</h2>
          {subtitle ? (
            <p className="mt-0.5 text-xs text-neutral-500">{subtitle}</p>
          ) : null}
        </header>
      ) : null}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Badge({
  severity = "neutral",
  children,
}: {
  severity?: Severity;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs ${SEVERITY_CLASS[severity]}`}
    >
      {children}
    </span>
  );
}

export function Table({
  head,
  children,
  empty,
}: {
  head: string[];
  children: ReactNode;
  empty?: string;
}) {
  const rows = Array.isArray(children) ? children : [children];
  const isEmpty = rows.flat().filter(Boolean).length === 0;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-neutral-200 text-left">
            {head.map((h) => (
              <th key={h} className="px-2 py-2 text-xs font-medium text-neutral-500">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {isEmpty ? (
            <tr>
              <td
                colSpan={head.length}
                className="px-2 py-6 text-center text-sm text-neutral-500"
              >
                {/* An empty table says why it is empty. "Nothing here" and "nothing
                    was checked" look identical otherwise. */}
                {empty ?? "Nothing to show."}
              </td>
            </tr>
          ) : (
            children
          )}
        </tbody>
      </table>
    </div>
  );
}

export function Row({ children }: { children: ReactNode }) {
  return <tr className="border-b border-neutral-100 last:border-0">{children}</tr>;
}

export function Cell({
  children,
  mono,
}: {
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <td className={`px-2 py-2 align-top ${mono ? "font-mono text-xs" : ""}`}>
      {children}
    </td>
  );
}

export function Button({
  children,
  variant = "default",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "danger";
}) {
  const base =
    "inline-flex items-center rounded px-3 py-1.5 text-sm font-medium transition disabled:opacity-50";
  const styles =
    variant === "danger"
      ? "bg-bad text-white hover:bg-critical"
      : "bg-neutral-900 text-white hover:bg-neutral-700";
  return (
    <button className={`${base} ${styles}`} {...props}>
      {children}
    </button>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-neutral-700">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-xs text-neutral-500">{hint}</span> : null}
    </label>
  );
}

export const inputClass =
  "mt-1 w-full rounded border border-neutral-300 px-2 py-1.5 text-sm focus:border-neutral-900 focus:outline-none";
