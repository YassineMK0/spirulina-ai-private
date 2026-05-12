"use client";
import { C } from "@/lib/theme";
import { Dot, Label, AgentAvatar, ToolPills } from "@/components/atoms";

const SensorMini = ({ label, val, unit, opt, isAlert }) => {
  const color = isAlert ? C.red : C.green;
  return (
    <div style={{ flex: 1, minWidth: 68, padding: "6px 8px", borderRadius: 6, background: isAlert ? C.redSoft : C.card2, border: `1px solid ${isAlert ? "#4A1010" : C.border}` }}>
      <div style={{ fontSize: 8, color: isAlert ? "#B06060" : C.text3, marginBottom: 2, fontFamily: C.mono }}>{label}{isAlert ? " ▲" : ""}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color, fontFamily: C.sans }}>{val}<span style={{ fontSize: 9, fontWeight: 400 }}>{unit}</span></div>
      <div style={{ fontSize: 7.5, color: C.text3, fontFamily: C.mono }}>opt {opt}</div>
    </div>
  );
};

const DiagnosisContent = ({ content }) => (
  <>
    <div style={{ marginBottom: 9, fontSize: 11 }}>
      <strong style={{ color: C.text }}>Root cause: </strong>{content.cause}
    </div>
    {content.sensors?.length > 0 && (
      <div style={{ display: "flex", gap: 5, marginBottom: 9, flexWrap: "wrap" }}>
        {content.sensors.map((s, i) => <SensorMini key={i} {...s} />)}
      </div>
    )}
    {content.action?.note && (
      <div style={{ background: C.card2, border: `1px solid ${C.border2}`, borderRadius: 7, padding: "8px 11px" }}>
        <Label>RECOMMENDED ACTION</Label>
        {content.action.dose && <><span style={{ color: C.text }}>Add </span><strong style={{ color: C.green, fontSize: 13 }}>{content.action.dose}</strong><span style={{ color: C.text2 }}> — </span></>}
        <span style={{ color: C.text2 }}>{content.action.note}</span>
      </div>
    )}
  </>
);

const HarvestContent = ({ content }) => {
  const today = content.schedule?.today   || {};
  const tmrw  = content.schedule?.tomorrow || {};
  const d2    = content.schedule?.day_after || {};
  const tf    = content.turbidity_forecast || {};

  const days = [
    { key: "today",     data: today, label: "TODAY"     },
    { key: "tomorrow",  data: tmrw,  label: "TOMORROW"  },
    { key: "day_after", data: d2,    label: "DAY AFTER" },
  ];

  const best    = days.reduce((a, b) => (b.data.harvest_pct || 0) > (a.data.harvest_pct || 0) ? b : a, days[0]);
  const bestPct = best.data.harvest_pct || 0;

  return (
    <>
      {bestPct > 0 ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", background: C.greenSoft, border: "1px solid #234830", borderRadius: 8, marginBottom: 9 }}>
          <div style={{ fontSize: 18 }}>⏳</div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: C.green }}>
              {best.key === "today" ? "Harvest today" : `Wait — harvest ${best.label.toLowerCase()}`}
            </div>
            <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono }}>
              {bestPct}% yield · M3 confidence {Math.round((best.data.confidence || 0) * 100)}%
            </div>
          </div>
        </div>
      ) : (
        <div style={{ padding: "8px 10px", background: C.card2, borderRadius: 8, marginBottom: 9, fontSize: 11, color: C.text2 }}>
          Culture not ready for harvest yet.
        </div>
      )}

      <div style={{ fontSize: 11.5, color: C.text2, marginBottom: 9, lineHeight: 1.6 }}>{content.body}</div>

      <div style={{ display: "flex", gap: 6, marginBottom: 9 }}>
        {days.map((d, i) => (
          <div key={i} style={{ flex: 1, background: d.key === best.key && bestPct > 0 ? C.greenSoft : C.card2, border: `1px solid ${d.key === best.key && bestPct > 0 ? "#234830" : C.border}`, borderRadius: 7, padding: "8px 10px", textAlign: "center" }}>
            <div style={{ fontSize: 8.5, color: C.text3, fontFamily: C.mono, marginBottom: 3 }}>{d.label}</div>
            <div style={{ fontSize: 16, fontWeight: 800, color: d.key === best.key && bestPct > 0 ? C.green : C.text, fontFamily: C.sans }}>{d.data.harvest_pct || 0}%</div>
            <div style={{ fontSize: 8, color: C.text3, marginTop: 2 }}>{d.data.label || "not_ready"}</div>
          </div>
        ))}
      </div>

      {content.recommendation && (
        <div style={{ background: C.card2, border: `1px solid ${C.border2}`, borderRadius: 7, padding: "8px 10px", fontSize: 10.5, color: C.text2, lineHeight: 1.55 }}>
          <Label>M3 RECOMMENDATION</Label>
          {content.recommendation}
        </div>
      )}

      {tf.prediction && (
        <div style={{ marginTop: 8, background: C.card2, border: `1px solid ${C.border2}`, borderRadius: 7, padding: "8px 10px" }}>
          <Label>M2 TURBIDITY FORECAST (TOMORROW)</Label>
          <div style={{ display: "flex", gap: 8 }}>
            {[["LOW", tf.low], ["PREDICTED", tf.prediction], ["HIGH", tf.high]].map(([lbl, v], i) => (
              <div key={i} style={{ flex: 1, textAlign: "center" }}>
                <div style={{ fontSize: 7.5, color: C.text3, fontFamily: C.mono }}>{lbl}</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: i === 1 ? C.green : C.text2 }}>{v?.toFixed(1)}</div>
                <div style={{ fontSize: 7.5, color: C.text3, fontFamily: C.mono }}>NTU</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
};

export default function Bubble({ msg }) {
  const t = msg.time || "";

  if (msg.role === "alert") return (
    <div className="msg-enter" style={{ background: C.redSoft, border: "1px solid #4A1010", borderRadius: 10, padding: "10px 13px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
        <Dot color={C.red} blink />
        <span style={{ fontSize: 8.5, fontWeight: 700, letterSpacing: 1, color: "#A04040", fontFamily: C.mono }}>SSE ALERT · M1 ANOMALY DETECTOR</span>
        <span style={{ marginLeft: "auto", fontSize: 8, color: C.text3, fontFamily: C.mono }}>{t}</span>
      </div>
      <div style={{ fontSize: 12.5, fontWeight: 700, color: C.red }}>{msg.text}</div>
    </div>
  );

  if (msg.role === "user") return (
    <div className="msg-enter" style={{ display: "flex", justifyContent: "flex-end" }}>
      <div style={{ maxWidth: "78%", padding: "9px 13px", borderRadius: "12px 12px 3px 12px", background: C.greenSoft, border: "1px solid #234830", color: "#C0EED0", fontSize: 12.5, lineHeight: 1.55 }}>
        {msg.text}
        <div style={{ fontSize: 8, color: C.text3, fontFamily: C.mono, marginTop: 4, textAlign: "right" }}>{t}</div>
      </div>
    </div>
  );

  if (msg.role === "agent") {
    const content = msg.content || { type: "text", text: msg.text || "" };
    return (
      <div className="msg-enter" style={{ display: "flex", gap: 9 }}>
        <AgentAvatar />
        <div style={{ flex: 1, minWidth: 0 }}>
          <ToolPills tools={msg.tools} />
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: "3px 12px 12px 12px", padding: "11px 13px", fontSize: 12, lineHeight: 1.65, color: C.text2 }}>
            {content.type === "diagnosis" && <DiagnosisContent content={content} />}
            {content.type === "harvest"   && <HarvestContent content={content} />}
            {(content.type === "text" || !content.type) && (
              <div style={{ color: C.text2, lineHeight: 1.7 }}>{content.text || msg.text}</div>
            )}
            <div style={{ fontSize: 8, color: C.text3, fontFamily: C.mono, marginTop: 8, textAlign: "right" }}>{t}</div>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
