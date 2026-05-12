"use client";
import { useState, useEffect } from "react";

import { C } from "@/lib/theme";
import { Tag, Label } from "@/components/atoms";

const SensorCard = ({ label, val, unit, color, min, max, oMin, oMax, trend, status = "ok" }) => {
  const pct = Math.min(Math.max(((parseFloat(val) - min) / (max - min)) * 100, 2), 98);
  const oS  = ((oMin - min) / (max - min)) * 100;
  const oW  = ((oMax - oMin) / (max - min)) * 100;
  const bg  = status === "alert" ? C.redSoft  : status === "warn" ? C.amberSoft : C.card;
  const bd  = status === "alert" ? "#4A1010"  : status === "warn" ? "#4A2808"   : C.border;
  const tagColor = status === "alert" ? C.red : status === "warn" ? C.amber : C.green;
  const tagLabel = status === "alert" ? "CRITICAL" : status === "warn" ? "HIGH" : "OK";
  return (
    <div style={{ background: bg, border: `1px solid ${bd}`, borderRadius: 11, padding: "13px 14px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: 9.5, color: C.text3, fontWeight: 600, letterSpacing: 0.3, fontFamily: C.mono }}>{label}</span>
        <Tag color={tagColor}>{tagLabel}</Tag>
      </div>
      <div style={{ fontSize: 25, fontWeight: 800, color, lineHeight: 1, fontFamily: C.sans }}>
        {val}<span style={{ fontSize: 11, fontWeight: 400 }}>{unit}</span>
      </div>
      {trend && <div style={{ fontSize: 9.5, color, fontFamily: C.mono, marginTop: 3, marginBottom: 6, opacity: 0.8 }}>{trend}</div>}
      <div style={{ position: "relative", height: 3, borderRadius: 99, background: C.border2, margin: "9px 0 5px" }}>
        <div style={{ position: "absolute", left: `${oS}%`, width: `${oW}%`, height: "100%", background: C.greenSoft, borderRadius: 99 }} />
        <div style={{ position: "absolute", left: `${pct}%`, top: -4.5, width: 12, height: 12, borderRadius: "50%", background: color, border: `2px solid ${bg}`, transform: "translateX(-50%)" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8.5, color: C.text3, fontFamily: C.mono }}>
        <span>{min}{unit}</span><span>opt {oMin}–{oMax}</span><span>{max}{unit}</span>
      </div>
    </div>
  );
};

function useDataAge(timestamp) {
  const [age, setAge] = useState(null);
  useEffect(() => {
    if (!timestamp) return;
    const update = () => {
      const secs = Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000);
      if (secs < 60)  setAge(`${secs}s ago`);
      else            setAge(`${Math.floor(secs / 60)}m ago`);
    };
    update();
    const id = setInterval(update, 5000);
    return () => clearInterval(id);
  }, [timestamp]);
  return age;
}

export default function DashboardPage({ sensorData }) {
  const s   = sensorData || {};
  const age = useDataAge(s.timestamp);

  const cards = [
    { label: "pH LEVEL",        val: s.pH          ?? "—", unit: "",        color: C.red,   min: 7,  max: 12,  oMin: 9.5,  oMax: 10.5, trend: "live", status: s.pH && s.pH < 9.5 ? "alert" : "ok" },
    { label: "TEMPERATURE",     val: s.temperature ?? "—", unit: " °C",     color: C.amber, min: 20, max: 45,  oMin: 30,   oMax: 37,   trend: "live", status: s.temperature && s.temperature > 37 ? "warn" : "ok" },
    { label: "TURBIDITY",       val: s.turbidity   ?? "—", unit: " NTU",    color: C.green, min: 0,  max: 500, oMin: 50,   oMax: 250,  trend: "live" },
    { label: "EC",              val: s.EC          ?? "—", unit: " µS/cm",  color: C.green, min: 0,  max: 5000,oMin: 1500, oMax: 3000, trend: "live", status: s.EC && s.EC > 3000 ? "warn" : "ok" },
    { label: "DISSOLVED O₂",    val: s.DO          ?? "—", unit: " mg/L",   color: C.green, min: 0,  max: 12,  oMin: 6,    oMax: 8,    trend: "live" },
    { label: "LUMINOSITY",      val: s.luminosity  ?? "—", unit: " lux",    color: C.green, min: 0,  max: 30000,oMin:8000, oMax: 15000,trend: "live" },
  ];

  if (!sensorData) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: C.text3, fontFamily: C.mono, fontSize: 12 }}>
        Waiting for MQTT data…
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "14px 18px", display: "flex", flexDirection: "column", gap: 11 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 9 }}>
        {cards.map((c, i) => <SensorCard key={i} {...c} />)}
      </div>
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 11, padding: "13px 15px" }}>
        <Label>LAST READING</Label>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono }}>
            {s.timestamp ? new Date(s.timestamp).toLocaleString() : "—"}
            &nbsp;·&nbsp;Status: <span style={{ color: s.status === "ok" ? C.green : C.amber }}>{s.status ?? "—"}</span>
            {s.source === "db" && <span style={{ color: C.amber }}>&nbsp;· cached</span>}
          </div>
          {age && (
            <span style={{
              fontSize: 8.5, fontFamily: C.mono, fontWeight: 700, padding: "2px 8px", borderRadius: 99,
              background: age.includes("m") && parseInt(age) > 1 ? C.amberSoft : C.greenSoft,
              color:      age.includes("m") && parseInt(age) > 1 ? C.amber     : C.green,
            }}>
              {age}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
