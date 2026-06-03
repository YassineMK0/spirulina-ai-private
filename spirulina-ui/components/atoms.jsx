"use client";
import { useTheme } from "@/lib/ThemeContext";

export const Dot = ({ color, size = 6, blink = false }) => {
  const { C } = useTheme();
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%",
      background: color ?? C.green, flexShrink: 0,
      animation: blink ? "blink 1.6s infinite" : undefined,
    }} />
  );
};

export const Tag = ({ children, color }) => {
  const { C } = useTheme();
  const c = color ?? C.green;
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, letterSpacing: 0.4,
      padding: "2px 8px", borderRadius: 20,
      fontFamily: C.mono, color: c,
      background: `${c}14`, border: `1px solid ${c}38`,
    }}>
      {children}
    </span>
  );
};

export const Label = ({ children }) => {
  const { C } = useTheme();
  return (
    <div style={{
      fontSize: 9, fontWeight: 600, letterSpacing: 1.4,
      color: C.text3, fontFamily: C.mono,
      textTransform: "uppercase", marginBottom: 6,
    }}>
      {children}
    </div>
  );
};

export const AgentAvatar = ({ size = 26 }) => {
  const { C } = useTheme();
  return (
    <div style={{
      width: size, height: size, borderRadius: Math.round(size * 0.3),
      background: `linear-gradient(140deg, ${C.greenSoft}, ${C.green})`,
      display: "flex", alignItems: "center", justifyContent: "center",
      flexShrink: 0, boxShadow: C.glowSm,
    }}>
      <svg viewBox="0 0 12 12" fill="none" width={size * 0.52} height={size * 0.52}>
        <path d="M6 .5C3.5.5 2 2.2 2 4c0 2.5 4 7.5 4 7.5s4-5 4-7.5C10 2.2 8.5.5 6 .5z" fill={C.green} />
        <circle cx="6" cy="4" r="1.6" fill={C.bg} />
      </svg>
    </div>
  );
};

export const ToolPills = ({ tools }) => {
  const { C } = useTheme();
  if (!tools?.length) return null;
  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 5 }}>
      {tools.map((t, i) => (
        <span key={i} style={{
          fontSize: 10, fontFamily: C.mono,
          padding: "2px 7px", borderRadius: 4,
          background: C.card2, color: C.text3,
          border: `1px solid ${C.border}`,
        }}>
          {t}
        </span>
      ))}
    </div>
  );
};

export const SpinnerDots = () => {
  const { C } = useTheme();
  return (
    <div style={{
      display: "flex", gap: 5,
      padding: "10px 14px",
      background: C.card, border: `1px solid ${C.border}`,
      borderRadius: "3px 12px 12px 12px",
      boxShadow: C.cardShadow,
    }}>
      {[0, 1, 2].map(i => (
        <div key={i} style={{
          width: 6, height: 6, borderRadius: "50%",
          background: C.green,
          animation: `blink 1.1s ${i * 0.18}s infinite`,
        }} />
      ))}
    </div>
  );
};
