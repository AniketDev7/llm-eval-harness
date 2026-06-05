import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0b1220",
        surface: "#0f172a",
        card: "#1e293b",
        border: "#334155",
        muted: "#94a3b8",
        text: "#e2e8f0",
        accent: "#22c55e",
        warn: "#eab308",
        danger: "#ef4444",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
