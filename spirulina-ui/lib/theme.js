/* ─────────────────────────────────────────────────────────────
   Theme tokens — DARK and LIGHT
   Components import { useTheme } from "@/lib/ThemeContext"
   and call const { C } = useTheme().
   The legacy static C = DARK so pages not yet on the hook
   continue to get a reasonable dark look.
───────────────────────────────────────────────────────────── */

export const DARK = {
  // ── Backgrounds ───────────────────────────────────────────
  bg:        "#000000",
  surface:   "#0A0A0A",
  panel:     "#111111",
  card:      "#161616",
  card2:     "#1C1C1E",
  card3:     "#111111",

  // ── Borders ───────────────────────────────────────────────
  border:    "#2A2A2A",
  border2:   "#383838",
  border3:   "#222222",

  // ── Accent (emerald green) ─────────────────────────────────
  green:       "#10B981",
  greenSoft:   "#052E20",
  greenGlow:   "rgba(16,185,129,0.12)",
  greenAlpha8: "rgba(16,185,129,0.08)",

  // ── Secondary accent ──────────────────────────────────────
  teal:        "#06B6D4",

  // ── Alerts ───────────────────────────────────────────────
  amber:       "#F59E0B",
  amberSoft:   "#1C1100",
  red:         "#EF4444",
  redSoft:     "#1C0808",

  // ── Text ─────────────────────────────────────────────────
  text:      "#F5F5F5",
  text2:     "#A3A3A3",
  text3:     "#525252",
  textCode:  "#34D399",

  // ── Glows ────────────────────────────────────────────────
  glowSm:    "0 0 0 1px rgba(16,185,129,0.12), 0 4px 16px rgba(0,0,0,0.6)",
  glowMd:    "0 0 0 1px rgba(16,185,129,0.18), 0 8px 32px rgba(0,0,0,0.7)",
  glowLg:    "0 0 0 1px rgba(16,185,129,0.25), 0 16px 48px rgba(0,0,0,0.8)",
  cardShadow:"0 1px 3px rgba(0,0,0,0.5), 0 4px 16px rgba(0,0,0,0.4)",
  redGlow:   "0 0 0 1px rgba(239,68,68,0.18), 0 4px 16px rgba(0,0,0,0.5)",

  // ── Gradients ─────────────────────────────────────────────
  gradientTop:   "linear-gradient(90deg,#10B981,#06B6D4,transparent)",
  gradientCard:  "linear-gradient(135deg,#111111,#161616)",
  gradientGreen: "linear-gradient(90deg,#10B981,#06B6D4)",

  // ── Typography ───────────────────────────────────────────
  sans: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif",
  mono: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace",
  serif: "'Instrument Serif', Georgia, serif",
};

export const LIGHT = {
  // ── Backgrounds ───────────────────────────────────────────
  bg:        "#FFFFFF",
  surface:   "#F9FAFB",
  panel:     "#F3F4F6",
  card:      "#FFFFFF",
  card2:     "#F9FAFB",
  card3:     "#F3F4F6",

  // ── Borders ───────────────────────────────────────────────
  border:    "#E5E7EB",
  border2:   "#D1D5DB",
  border3:   "#EDEDED",

  // ── Accent ────────────────────────────────────────────────
  green:       "#059669",
  greenSoft:   "#ECFDF5",
  greenGlow:   "rgba(5,150,105,0.10)",
  greenAlpha8: "rgba(5,150,105,0.06)",

  // ── Secondary accent ──────────────────────────────────────
  teal:        "#0891B2",

  // ── Alerts ────────────────────────────────────────────────
  amber:       "#D97706",
  amberSoft:   "#FEF3C7",
  red:         "#DC2626",
  redSoft:     "#FEE2E2",

  // ── Text ──────────────────────────────────────────────────
  text:      "#0A0A0A",
  text2:     "#4B5563",
  text3:     "#9CA3AF",
  textCode:  "#065F46",

  // ── Glows / Shadows ───────────────────────────────────────
  glowSm:    "0 0 0 1px rgba(5,150,105,0.10), 0 2px 8px rgba(0,0,0,0.07)",
  glowMd:    "0 0 0 1px rgba(5,150,105,0.15), 0 4px 16px rgba(0,0,0,0.10)",
  glowLg:    "0 0 0 1px rgba(5,150,105,0.20), 0 8px 32px rgba(0,0,0,0.12)",
  cardShadow:"0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.06)",
  redGlow:   "0 0 0 1px rgba(220,38,38,0.12), 0 2px 8px rgba(0,0,0,0.06)",

  // ── Gradients ─────────────────────────────────────────────
  gradientTop:   "linear-gradient(90deg,#059669,#0891B2,transparent)",
  gradientCard:  "linear-gradient(135deg,#F0FDF4,#ECFDF5)",
  gradientGreen: "linear-gradient(90deg,#059669,#0891B2)",

  // ── Typography ───────────────────────────────────────────
  sans:  "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif",
  mono:  "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace",
  serif: "'Instrument Serif', Georgia, serif",
};

// Legacy default export — dark theme so un-migrated components look right
export const C = DARK;
