import type { Config } from "tailwindcss";

/**
 * Every colour resolves to a CSS variable defined in `app/globals.css`.
 *
 * No hex literal appears in a component, which is what makes dark mode a definition
 * rather than a second set of classes somebody has to remember. It also means a
 * severity can never be chosen ad hoc: there is no `red-100` to reach for, only `bad`,
 * and `bad` is dark-mode-correct by construction.
 */
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          page: "var(--surface-0)",
          muted: "var(--surface-1)",
          DEFAULT: "var(--surface-2)",
          inverse: "var(--surface-inverse)",
        },
        line: {
          DEFAULT: "var(--border)",
          strong: "var(--border-strong)",
        },
        ink: {
          DEFAULT: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          muted: "var(--text-muted)",
          inverse: "var(--text-inverse)",
        },

        // Severity is a named scale, not an ad-hoc colour per component. A dashboard
        // that renders "never verified" in a reassuring grey manufactures confidence,
        // so the palette makes the failing states loud by construction.
        ok: "var(--text-success)",
        "ok-bg": "var(--bg-success)",
        "ok-line": "var(--border-success)",

        warn: "var(--text-warning)",
        "warn-bg": "var(--bg-warning)",
        "warn-line": "var(--border-warning)",

        bad: "var(--text-danger)",
        "bad-bg": "var(--bg-danger)",
        "bad-line": "var(--border-danger)",

        critical: "var(--text-critical)",
        "critical-bg": "var(--bg-critical)",
        "critical-line": "var(--border-critical)",

        neutral2: "var(--text-neutral)",
        "neutral2-bg": "var(--bg-neutral)",
        "neutral2-line": "var(--border-neutral)",
      },
      fontSize: {
        // The scale this console uses, named so a component cannot invent a seventh size.
        //
        // `page` was missing while fifteen call sites already used `text-page` for their
        // title. `page` exists under `colors.surface`, so the class reads as though it
        // resolves, and it compiled to nothing at all: every page title took its size
        // from whatever it inherited. A dead utility class is invisible in review and in
        // the browser - it is not a wrong colour or a wrong size, it is no rule.
        page: ["18px", { lineHeight: "1.35" }],
        section: ["16px", { lineHeight: "1.4" }],
        rowtitle: ["15px", { lineHeight: "1.4" }],
        body: ["14px", { lineHeight: "1.5" }],
        desc: ["13px", { lineHeight: "1.5" }],
        meta: ["12px", { lineHeight: "1.45" }],
        ident: ["11px", { lineHeight: "1.4" }],
      },
    },
  },
  plugins: [],
} satisfies Config;
