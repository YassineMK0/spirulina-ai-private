"use client";
import { C } from "@/lib/theme";

export const Dot = ({ color = C.green, size = 6, blink = false }) => (
  <div style={{ width: size, height: size, borderRadius: "50%", background: color, flexShrink: 0, animation: blink ? "blink 1.6s infinite" : undefined }} />
);

export const Tag = ({ children, color = C.green }) => (
  <span style={{ fontSize: 8, fontWeight: 600, letterSpacing: 0.5, padding: "2px 7px", borderRadius: 20, fontFamily: C.mono, color, background: color + "18", border: `1px solid ${color}44` }}>
    {children}
  </span>
);

export const Label = ({ children }) => (
  <div style={{ fontSize: 8.5, fontWeight: 600, letterSpacing: 1.5, color: C.text3, fontFamily: C.mono, marginBottom: 7 }}>
    {children}
  </div>
);

export const AgentAvatar = ({ size = 26 }) => (
  <div style={{ width: size, height: size, borderRadius: 7, background: `linear-gradient(140deg,#0F3A1E,${C.green})`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
    <svg viewBox="0 0 12 12" fill="none" width={size * 0.54} height={size * 0.54}>
      <path d="M6 .5C3.5.5 2 2.2 2 4c0 2.5 4 7.5 4 7.5s4-5 4-7.5C10 2.2 8.5.5 6 .5z" fill={C.green} />
      <circle cx="6" cy="4" r="1.6" fill="#0C1410" />
    </svg>
  </div>
);

export const ToolPills = ({ tools }) => tools?.length ? (
  <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 5 }}>
    {tools.map((t, i) => (
      <span key={i} style={{ fontSize: 8, fontFamily: C.mono, padding: "2px 6px", borderRadius: 4, background: C.card2, color: C.text3, border: `1px solid ${C.border2}` }}>✓ {t}</span>
    ))}
  </div>
) : null;

export const SpinnerDots = () => (
  <div style={{ display: "flex", gap: 5, padding: "10px 14px", background: C.card, border: `1px solid ${C.border}`, borderRadius: "3px 12px 12px 12px" }}>
    {[0, 1, 2].map(i => (
      <div key={i} style={{ width: 6, height: 6, borderRadius: "50%", background: C.green, animation: `blink 1.1s ${i * 0.18}s infinite` }} />
    ))}
  </div>
);
