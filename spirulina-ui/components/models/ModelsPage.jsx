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
  const m2 = outputs?.m2 || {};
  const m3 = outputs?.m3 || {};

  const m1Color = m1.anomaly ? C.red : C.green;
  const m1Tag   = m1.error ? "ERROR" : m1.anomaly ? "ANOMALY" : m1.score !== undefined ? "NORMAL" : "PENDING";

  const m3Color = m3.recommendation === "heavy"    ? C.red
                : m3.recommendation === "moderate" ? C.amber
                : m3.recommendation === "light"    ? C.green
                : C.text3;

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

      {/* M1 — Anomaly Detector */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
        <div style={{ padding: "13px 15px", display: "flex", alignItems: "center", gap: 11, borderBottom: `1px solid ${C.border}` }}>
          <div style={{ width: 34, height: 34, borderRadius: 8, background: C.redSoft, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, fontFamily: C.mono, color: C.red, flexShrink: 0 }}>M1</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Anomaly Detector</div>
            <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono, marginTop: 1 }}>LSTM Autoencoder · window=12</div>
          </div>
          <Tag color={m1.anomaly ? C.red : m1.error ? C.red : C.green}>{m1Tag}</Tag>
        </div>
        <div style={{ padding: "13px 15px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <Label>INPUT FEATURES</Label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {["pH","EC","DO","temperature","luminosity","turbidity"].map((f) => (
                <span key={f} style={{ fontSize: 8.5, background: C.card2, border: `1px solid ${C.border2}`, borderRadius: 4, padding: "2px 6px", color: C.text2, fontFamily: C.mono }}>{f}</span>
              ))}
            </div>
          </div>
          <div>
            <Label>LIVE OUTPUT</Label>
            <LiveOutput error={m1.error} loading={loading} data={m1.score !== undefined ? (
              <>
                <LiveRow k="anomaly"  v={m1.anomaly ? "YES" : "no"}  color={m1Color} />
                <LiveRow k="score"    v={m1.score?.toFixed(4)}        color={m1.score > 0.55 ? C.red : C.green} />
                <LiveRow k="severity" v={m1.severity}                 color={m1.severity === "critical" ? C.red : m1.severity === "medium" ? C.amber : C.green} />
                <LiveRow k="trend"    v={m1.trend}                    color={m1.trend === "declining" ? C.red : m1.trend === "recovering" ? C.amber : C.green} />
              </>
            ) : null} />
          </div>
        </div>
      </div>

      {/* M2 — Turbidity Forecaster */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
        <div style={{ padding: "13px 15px", display: "flex", alignItems: "center", gap: 11, borderBottom: `1px solid ${C.border}` }}>
          <div style={{ width: 34, height: 34, borderRadius: 8, background: C.greenSoft, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, fontFamily: C.mono, color: C.green, flexShrink: 0 }}>M2</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Turbidity Forecaster</div>
            <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono, marginTop: 1 }}>LightGBM · quantile p10/p50/p90</div>
          </div>
          <Tag color={m2.error ? C.red : m2.prediction !== undefined ? C.green : C.text3}>
            {m2.error ? "ERROR" : m2.prediction !== undefined ? "READY" : "PENDING"}
          </Tag>
        </div>
        <div style={{ padding: "13px 15px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <Label>INPUT FEATURES</Label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {["pH","EC","DO","temperature","luminosity","turbidity","lag1–3","rolling_5d"].map((f) => (
                <span key={f} style={{ fontSize: 8.5, background: C.card2, border: `1px solid ${C.border2}`, borderRadius: 4, padding: "2px 6px", color: C.text2, fontFamily: C.mono }}>{f}</span>
              ))}
            </div>
          </div>
          <div>
            <Label>LIVE OUTPUT — TOMORROW NTU</Label>
            <LiveOutput error={m2.error} loading={loading} data={m2.prediction !== undefined ? (
              <>
                <LiveRow k="low (p10)"      v={`${m2.low} NTU`}        color={C.green} />
                <LiveRow k="forecast (p50)" v={`${m2.prediction} NTU`} color={C.green} />
                <LiveRow k="high (p90)"     v={`${m2.high} NTU`}       color={C.amber} />
              </>
            ) : null} />
          </div>
        </div>
      </div>

      {/* M3 — Harvest Scheduler */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
        <div style={{ padding: "13px 15px", display: "flex", alignItems: "center", gap: 11, borderBottom: `1px solid ${C.border}` }}>
          <div style={{ width: 34, height: 34, borderRadius: 8, background: C.amberSoft, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, fontFamily: C.mono, color: C.amber, flexShrink: 0 }}>M3</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Harvest Scheduler</div>
            <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono, marginTop: 1 }}>LightGBM Classifier · 3-day window</div>
          </div>
          <Tag color={m3.error ? C.red : m3.recommendation ? m3Color : C.text3}>
            {m3.error ? "ERROR" : m3.recommendation?.toUpperCase() || "PENDING"}
          </Tag>
        </div>
        <div style={{ padding: "13px 15px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <Label>INPUT FEATURES</Label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {["turbidity","mu_3d","delta_turbidity","rolling_5d","EC","pH","day_of_cycle"].map((f) => (
                <span key={f} style={{ fontSize: 8.5, background: C.card2, border: `1px solid ${C.border2}`, borderRadius: 4, padding: "2px 6px", color: C.text2, fontFamily: C.mono }}>{f}</span>
              ))}
            </div>
          </div>
          <div>
            <Label>LIVE OUTPUT — TODAY</Label>
            <LiveOutput error={m3.error} loading={loading} data={m3.recommendation ? (
              <>
                <LiveRow k="recommendation" v={m3.recommendation}                                        color={m3Color} />
                <LiveRow k="harvest %"      v={m3.harvest_pct != null ? `${m3.harvest_pct}%` : "—"}     color={m3Color} />
                <LiveRow k="confidence"     v={m3.confidence   != null ? m3.confidence.toFixed(2) : "—"} color={C.green} />
                <LiveRow k="tomorrow %"     v={m3.tomorrow_pct != null ? `${m3.tomorrow_pct}%` : "—"}    color={C.text3} />
              </>
            ) : null} />
          </div>
        </div>
      </div>

    </div>
  );
}
