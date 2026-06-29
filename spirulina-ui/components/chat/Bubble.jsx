"use client";
import { useState } from "react";
import { useTheme } from "@/lib/ThemeContext";
import { AgentAvatar } from "@/components/atoms";
import MarkdownRenderer from "@/components/chat/MarkdownRenderer";

/* ── Sensor mini-card ───────────────────────────────────────────────────── */
function SensorMini({ label, val, unit, opt, isAlert }) {
  const { C } = useTheme();
  return (
    <div style={{
      flex: "1 1 70px", padding: "8px 10px", borderRadius: 8,
      background: isAlert ? `${C.redSoft}` : C.card2,
      border: `1px solid ${isAlert ? C.red + "40" : C.border}`,
    }}>
      <div style={{ fontSize: 9, color: isAlert ? C.red : C.text3, marginBottom: 3, fontFamily: C.mono }}>
        {label}{isAlert ? " ↑" : ""}
      </div>
      <div style={{ fontSize: 16, fontWeight: 700, color: isAlert ? C.red : C.green, fontFamily: C.mono }}>
        {val}<span style={{ fontSize: 10, fontWeight: 400, marginLeft: 1 }}>{unit}</span>
      </div>
      <div style={{ fontSize: 9, color: C.text3, fontFamily: C.mono, marginTop: 2 }}>opt {opt}</div>
    </div>
  );
}

/* ── Diagnosis card ─────────────────────────────────────────────────────── */
function DiagnosisContent({ content }) {
  const { C } = useTheme();
  return (
    <div>
      {content.sensors?.length > 0 && (
        <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
          {content.sensors.map((s, i) => <SensorMini key={i} {...s} />)}
        </div>
      )}
      <MarkdownRenderer content={content.cause} />
      {content.action?.note && (
        <div style={{
          marginTop: 10, background: C.card2,
          border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 13px",
        }}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: 1.2, color: C.text3, fontFamily: C.mono, marginBottom: 6, textTransform: "uppercase" }}>
            Recommended Action
          </div>
          <MarkdownRenderer content={content.action.note} />
        </div>
      )}
    </div>
  );
}

/* ── Tool call log ──────────────────────────────────────────────────────── */
function ToolCallLog({ calls }) {
  const { C } = useTheme();
  const [open, setOpen] = useState(false);
  if (!calls?.length) return null;
  return (
    <div style={{ borderTop: `1px solid ${C.border}`, background: C.card2 }}>
      <button onClick={() => setOpen(!open)} style={{
        width: "100%", display: "flex", alignItems: "center", gap: 8,
        padding: "6px 14px", background: "none", border: "none", textAlign: "left",
      }}>
        <span style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono }}>
          {open ? "▾" : "▸"} Tool calls ({calls.length})
        </span>
      </button>
      {open && (
        <div className="plan-reveal" style={{ padding: "0 14px 10px", display: "flex", flexDirection: "column", gap: 5 }}>
          {calls.map((tc, i) => (
            <div key={i} style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 6, padding: "7px 10px" }}>
              <div style={{ fontSize: 10.5, fontWeight: 500, color: C.teal, fontFamily: C.mono, marginBottom: tc.args && Object.keys(tc.args).length ? 4 : 0 }}>
                ⚡ {tc.tool}
              </div>
              {tc.args && Object.keys(tc.args).length > 0 && (
                <div style={{ fontSize: 10.5, fontFamily: C.mono, color: C.text3, lineHeight: 1.6 }}>
                  {Object.entries(tc.args).map(([k, v]) => (
                    <span key={k} style={{ marginRight: 10 }}>
                      <span style={{ color: C.text3 }}>{k}=</span>
                      <span style={{ color: C.green }}>{String(v)}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Main Bubble ────────────────────────────────────────────────────────── */
export default function Bubble({ msg }) {
  const { C } = useTheme();
  const [planOpen, setPlanOpen] = useState(false);
  const t = msg.time || "";

  /* Alert */
  if (msg.role === "alert") {
    return (
      <div className="msg-enter scan-lines" style={{
        background: C.redSoft, border: `1px solid ${C.red}30`,
        borderRadius: 10, padding: "11px 14px",
        boxShadow: C.redGlow, position: "relative", overflow: "hidden",
      }}>
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 1, background: `linear-gradient(90deg, ${C.red}, transparent)` }} />
        <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5 }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: C.red, animation: "blink 1.2s infinite", flexShrink: 0 }} />
          <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: 1, color: C.red, fontFamily: C.mono, textTransform: "uppercase" }}>
            Anomaly Alert
          </span>
          <span style={{ marginLeft: "auto", fontSize: 9, color: C.text3, fontFamily: C.mono }}>{t}</span>
        </div>
        <div style={{ fontSize: 13, fontWeight: 500, color: C.text, lineHeight: 1.5 }}>{msg.text}</div>
      </div>
    );
  }

  /* User */
  if (msg.role === "user") {
    return (
      <div className="msg-enter" style={{ display: "flex", justifyContent: "flex-end" }}>
        <div style={{
          maxWidth: "72%", padding: "10px 14px",
          borderRadius: "14px 14px 3px 14px",
          background: C.card2, border: `1px solid ${C.border2}`,
          color: C.text, fontSize: 13.5, lineHeight: 1.6,
          boxShadow: C.cardShadow,
        }}>
          {msg.text}
          <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono, marginTop: 6, textAlign: "right" }}>{t}</div>
        </div>
      </div>
    );
  }

  /* Agent */
  if (msg.role === "agent") {
    const content   = msg.content   || { type: "text", text: msg.text || "" };
    const plan      = msg.plan      || "";
    const toolCalls = msg.tool_calls || [];
    const tools     = msg.tools     || [];
    const isAgentic = toolCalls.length > 0;

    return (
      <div className="msg-enter" style={{ display: "flex", gap: 10 }}>
        <AgentAvatar />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            background: C.card, border: `1px solid ${C.border}`,
            borderRadius: "3px 12px 12px 12px",
            overflow: "hidden", boxShadow: C.cardShadow,
          }}>
            {/* Top accent line */}
            <div style={{ height: 1, background: C.gradientTop }} />

            {/* Header */}
            <div style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "7px 14px", borderBottom: `1px solid ${C.border}`,
              background: C.card2,
            }}>
              <span style={{ fontSize: 11.5, fontWeight: 600, color: C.text }}>SpirulinaAI</span>

              {isAgentic && (
                <span style={{
                  fontSize: 9.5, padding: "2px 7px", borderRadius: 4,
                  background: `${C.teal}14`, color: C.teal,
                  border: `1px solid ${C.teal}30`, fontFamily: C.mono,
                }}>
                  ⚡ agentic · {toolCalls.length} tool{toolCalls.length !== 1 ? "s" : ""}
                </span>
              )}

              {!isAgentic && tools.length > 0 && (
                <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                  {tools.slice(0, 5).map((tool, i) => (
                    <span key={i} style={{
                      fontSize: 9.5, padding: "1px 6px", borderRadius: 4,
                      background: C.panel, color: C.text3,
                      border: `1px solid ${C.border}`, fontFamily: C.mono,
                    }}>{tool}</span>
                  ))}
                </div>
              )}

              <span style={{ marginLeft: "auto", fontSize: 9.5, color: C.text3, fontFamily: C.mono }}>{t}</span>
            </div>

            {/* Plan panel */}
            {plan && (
              <div style={{ borderBottom: `1px solid ${C.border}` }}>
                <button onClick={() => setPlanOpen(!planOpen)} style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 8,
                  padding: "7px 14px", background: "none", border: "none",
                }}>
                  <span style={{ fontSize: 9.5, fontWeight: 500, color: C.text3, fontFamily: C.mono }}>
                    {planOpen ? "▾" : "▸"} Agent plan
                  </span>
                  <div style={{ flex: 1, height: 1, background: C.border }} />
                </button>
                {planOpen && (
                  <div className="plan-reveal" style={{ padding: "4px 14px 12px" }}>
                    <MarkdownRenderer content={plan} dimmed />
                  </div>
                )}
              </div>
            )}

            {/* Main content */}
            <div style={{ padding: "13px 14px" }}>
              {content.type === "diagnosis" && <DiagnosisContent content={content} />}
              {(content.type === "text" || !content.type) && (
                <MarkdownRenderer content={content.text || msg.text || ""} />
              )}
            </div>

            {/* Tool call log */}
            {isAgentic && <ToolCallLog calls={toolCalls} />}
          </div>
        </div>
      </div>
    );
  }

  return null;
}
