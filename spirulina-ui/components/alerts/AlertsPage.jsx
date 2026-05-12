"use client";
import { C } from "@/lib/theme";
import { Tag } from "@/components/atoms";

export default function AlertsPage({ alerts = [], onGoChat }) {
  const palette = {
    critical: { bg: C.redSoft,   bd: "#4A1010", col: C.red   },
    medium:   { bg: C.amberSoft, bd: "#4A2808", col: C.amber },
    low:      { bg: C.card,      bd: C.border,  col: C.green },
    normal:   { bg: C.card,      bd: C.border,  col: C.green },
  };

  if (alerts.length === 0) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: C.text3, fontFamily: C.mono, fontSize: 12 }}>
        No alerts yet.
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "14px 18px", display: "flex", flexDirection: "column", gap: 9 }}>
      {[...alerts].reverse().map((a, i) => {
        const p = palette[a.severity] || palette.normal;
        return (
          <div key={i} style={{ background: p.bg, border: `1px solid ${p.bd}`, borderRadius: 11, padding: "13px 14px" }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8, marginBottom: 7 }}>
              <div style={{ display: "flex", gap: 9, alignItems: "flex-start" }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: p.col, flexShrink: 0, marginTop: 3, animation: i === 0 ? "blink 1.2s infinite" : undefined }} />
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: p.col, marginBottom: 2 }}>
                    M1 Anomaly · {a.severity?.toUpperCase()}
                  </div>
                  <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono }}>Score {a.score?.toFixed(3)} · Trend: {a.trend}</div>
                </div>
              </div>
              <Tag color={i === 0 ? C.red : C.green}>{i === 0 ? "ACTIVE" : "PAST"}</Tag>
            </div>
            <div style={{ fontSize: 11, color: C.text2, lineHeight: 1.55, marginBottom: 8, paddingLeft: 17 }}>{a.text}</div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, paddingLeft: 17 }}>
              <span style={{ fontSize: 8.5, color: C.text3, fontFamily: C.mono }}>{a.time}</span>
              {i === 0 && (
                <button onClick={onGoChat} style={{ marginLeft: "auto", fontSize: 10, padding: "4px 12px", borderRadius: 20, background: C.redSoft, color: C.red, border: "1px solid #4A1010", fontWeight: 600 }}>
                  Ask agent →
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
