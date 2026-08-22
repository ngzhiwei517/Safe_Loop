import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)", surface: "var(--surface)", surfaceSunken: "var(--surface-sunken)",
        border: "var(--border)", ink: "var(--ink)", inkMuted: "var(--ink-muted)",
        primary: "var(--primary)", primaryStrong: "var(--primary-strong)", primaryTint: "var(--primary-tint)",
        success: "var(--success)", successStrong: "var(--success-strong)", successTint: "var(--success-tint)", successSurface: "var(--success-surface)",
        warning: "var(--warning)", warningTint: "var(--warning-tint)",
        danger: "var(--danger)", dangerStrong: "var(--danger-strong)", dangerTint: "var(--danger-tint)",
      },
      borderRadius: { card: "var(--r-card)", control: "var(--r-control)", chip: "var(--r-chip)", tile: "var(--r-tile)" },
      boxShadow: { safe: "var(--shadow)" },
    },
  },
  plugins: [],
};

export default config;
