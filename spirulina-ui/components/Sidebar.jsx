"use client";
import { C } from "@/lib/theme";
import { Dot, Label } from "@/components/atoms";

const Logo = () => (
  <div style={{ width: 30, height: 30, borderRadius: 8, background: `linear-gradient(140deg,#0F3A1E,${C.green})`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, animation: "glow 3s infinite" }}>
    <svg viewBox="0 0 12 12" fill="none" width={14} height={14}>
      <path d="M6 .5C3.5.5 2 2.2 2 4c0 2.5 4 7.5 4 7.5s4-5 4-7.5C10 2.2 8.5.5 6 .5z" fill={C.green} />
      <circle cx="6" cy="4" r="1.6" fill="#0C1410" />
    </svg>
  </div>
);

export default function Sidebar({ page, setPage, alertCount, mlStatus }) {
  const nav = [
    { k: "chat",      label: "Agent Chat",    icon: "◎", group: "WORKSPACE" },
    { k: "dashboard", label: "Dashboard",     icon: "▦", group: null        },
    { k: "alerts",    label: "Alerts",        icon: "△", group: null, badge: alertCount || 0 },
    { k: "models",    label: "ML Models",     icon: "⬡", group: "INTELLIGENCE" },
  ];

  const models = [
    { name: "M1 Anomaly Detector", color: mlStatus?.m1 === "alert" ? C.red : mlStatus?.m1 === "ok" ? C.green : C.text3, status: mlStatus?.m1?.toUpperCase() || "—" },
  ];

  return (
    <div style={{ width: 210, minWidth: 210, background: C.surface, borderRight: `1px solid ${C.border}`, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Logo */}
      <div style={{ padding: "16px 14px 12px", borderBottom: `1px solid ${C.border}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 10 }}>
          <Logo />
          <div>
            <div style={{ fontFamily: C.serif, fontSize: 16, fontStyle: "italic", color: C.text, lineHeight: 1 }}>SpirulinaAI</div>
            <div style={{ fontSize: 8, fontWeight: 600, letterSpacing: 2, color: C.green, fontFamily: C.mono }}>PRO · v3.0</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 9px", background: C.card, border: `1px solid ${C.border}`, borderRadius: 7 }}>
          <div>
            <div style={{ fontSize: 8, color: C.text3, fontFamily: C.mono }}>MQTT</div>
            <div style={{ fontSize: 10, color: C.text2, fontWeight: 500 }}>Live sensors</div>
          </div>
          <Dot size={7} blink />
        </div>
      </div>

      {/* Nav */}
      <div style={{ flex: 1, padding: "8px", overflowY: "auto" }}>
        {nav.map((item) => (
          <div key={item.k}>
            {item.group && (
              <div style={{ fontSize: 8, fontWeight: 600, letterSpacing: 1.5, color: C.text3, fontFamily: C.mono, padding: "10px 8px 5px" }}>
                {item.group}
              </div>
            )}
            <div
              onClick={() => setPage(item.k)}
              style={{
                display: "flex", alignItems: "center", gap: 8, padding: "7px 9px", borderRadius: 7, cursor: "pointer",
                background:  page === item.k ? C.greenSoft : "transparent",
                color:       page === item.k ? C.green     : C.text3,
                fontSize: 11.5, fontWeight: page === item.k ? 600 : 400, marginBottom: 1,
                transition: "background .12s, color .12s",
                borderLeft: `2px solid ${page === item.k ? C.green : "transparent"}`,
              }}
            >
              <span style={{ fontSize: 12, width: 16, textAlign: "center", flexShrink: 0 }}>{item.icon}</span>
              {item.label}
              {item.badge > 0 && (
                <span style={{ marginLeft: "auto", background: C.red, color: "#fff", fontSize: 8, padding: "1px 5px", borderRadius: 99, fontFamily: C.mono, fontWeight: 700 }}>
                  {item.badge}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Model statuses */}
      <div style={{ padding: "10px 12px", borderTop: `1px solid ${C.border}` }}>
        <Label>ACTIVE MODELS</Label>
        {models.map((m, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
            <Dot color={m.color} size={5} />
            <span style={{ fontSize: 10, color: C.text2, flex: 1 }}>{m.name}</span>
            <span style={{ fontSize: 8, fontFamily: C.mono, color: m.color }}>{m.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
