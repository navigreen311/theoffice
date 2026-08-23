import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Severity is a named scale, not an ad-hoc colour per component. A dashboard
        // that renders "never verified" in a reassuring grey manufactures confidence,
        // so the palette makes the failing states loud by construction.
        ok: "#15803d",
        warn: "#b45309",
        bad: "#b91c1c",
        critical: "#7f1d1d",
      },
    },
  },
  plugins: [],
} satisfies Config;
