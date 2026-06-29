"use client";
import { useState, useEffect } from "react";
import { C } from "@/lib/theme";
import { Tag, Label, Dot } from "@/components/atoms";
import { getModelOutputs } from "@/lib/api";


const LiveRow = ({ k, v, color }) => (
  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
    <span style={{ fontSize: 8.5, color: C.text3, fontFamily: C.mono }}>{k}</span>
    <span style={{ fontSize: 10, fontWeight: 700, fontFamily: C.mono, color: color || C.text }}>{v}</span>
  </div>
);

function LiveOutput({ data, error, loading }) {
  const box = { background: C.card2, border: `1px solid ${C.border2}`, borderRadius: 7, padding: "10px 12px" };
  if (loading)  return <div style={{ ...box, color: C.text3, fontFamily: C.mono, fontSize: 9 }}>Running…</div>;
  if (error)    return <div style={{ ...box, border: "1px solid #4A1010", color: C.red, fontFamily: C.mono, fontSize: 9 }}>{error}</div>;
  if (!data)    return <div style={{ ...box, color: C.text3, fontFamily: C.mono, fontSize: 9 }}>Waiting for sensor data…</div>;
  return <div style={box}>{data}</div>;
}

export default function ModelsPage({ containerId }) {
  const [outputs, setOutputs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastRun, setLastRun] = useState(null);

  useEffect(() => {
    if (!containerId) return;
    let cancelled = false;

    const poll = async () => {
      const data = await getModelOutputs(containerId);
      if (cancelled) return;
      setOutputs(data);
      setLoading(false);
      if (data && !data.error) setLastRun(new Date().toTimeString().slice(0, 8));
    };

    poll();
    const id = setInterval(poll, 15_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [containerId]);

  const m1 = outputs?.m1 || {};

  const m1Color = m1.anomaly ? C.red : C.green;
  const m1Tag   = m1.error ? "ERROR" : m1.anomaly ? "ANOMALY" : m1.severity !== undefined ? "NORMAL" : "PENDING";
  const severityColor = m1.severity === "critical" ? C.red : m1.severity === "warning" ? C.amber : C.green;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "14px 18px", display: "flex", flexDirection: "column", gap: 11 }}>

      {/* Status bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: C.card, border: `1px solid ${C.border}`, borderRadius: 9 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 9, fontFamily: C.mono, color: C.text3 }}>
          <Dot size={5} blink={!loading} color={loading ? C.text3 : C.green} />
          {loading
            ? "Running models…"
            : outputs?.error === "no_data"
            ? "No sensor history yet — waiting for readings"
            : `Last run: ${lastRun}  ·  ${outputs?.readings ?? 0} readings`}
        </div>
        <span style={{ fontSize: 8.5, fontFamily: C.mono, color: C.text3 }}>auto-refresh 15s</span>
      </div>

      {/* M1 — Anomaly Detector (rule engine + seasonal check) */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
        <div style={{ padding: "13px 15px", display: "flex", alignItems: "center", gap: 11, borderBottom: `1px solid ${C.border}` }}>
          <div style={{ width: 34, height: 34, borderRadius: 8, background: C.redSoft, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, fontFamily: C.mono, color: C.red, flexShrink: 0 }}>M1</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Anomaly Detector</div>
            <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono, marginTop: 1 }}>Rule engine + seasonal check · LOF combination model (24h cron)</div>
          </div>
          <Tag color={m1.anomaly ? C.red : m1.error ? C.red : C.green}>{m1Tag}</Tag>
        </div>
        <div style={{ padding: "13px 15px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <Label>INPUT FEATURES</Label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {["pH","EC","DO","temperature","luminosity"].map((f) => (
                <span key={f} style={{ fontSize: 8.5, background: C.card2, border: `1px solid ${C.border2}`, borderRadius: 4, padding: "2px 6px", color: C.text2, fontFamily: C.mono }}>{f}</span>
              ))}
            </div>
          </div>
          <div>
            <Label>LIVE OUTPUT</Label>
            <LiveOutput error={m1.error} loading={loading} data={m1.severity !== undefined ? (
              <>
                <LiveRow k="anomaly"  v={m1.anomaly ? "YES" : "no"} color={m1Color} />
                <LiveRow k="severity" v={m1.severity || "ok"}       color={severityColor} />
                {(m1.rule_findings || []).map((f, i) => (
                  <LiveRow key={i} k={f.parameter} v={f.label} color={f.severity >= 3 ? C.red : C.amber} />
                ))}
              </>
            ) : null} />
          </div>
        </div>
      </div>

    </div>
  );
}
