"use client";
import { useState, useEffect, useMemo } from "react";
import {
  ResponsiveContainer, LineChart, Line, Area, ComposedChart,
  CartesianGrid, XAxis, YAxis, Tooltip,
} from "recharts";

import { useTheme } from "@/lib/ThemeContext";
import { Label } from "@/components/atoms";
import { getSensorHistory } from "@/lib/api";

const METRICS = [
  { key: "pH",          label: "pH LEVEL",     unit: "",       colorKey: "red"   },
  { key: "temperature", label: "TEMPERATURE",  unit: " °C",    colorKey: "amber" },
  { key: "turbidity",   label: "TURBIDITY",    unit: " NTU",   colorKey: "green" },
  { key: "EC",          label: "EC",           unit: " µS/cm", colorKey: "green" },
  { key: "DO",          label: "DISSOLVED O₂", unit: " mg/L",  colorKey: "green" },
  { key: "luminosity",  label: "LUMINOSITY",   unit: " lux",   colorKey: "green" },
];

const RANGE_PRESETS = [
  { label: "7D",  days: 7  },
  { label: "14D", days: 14 },
  { label: "30D", days: 30 },
];

function fmtTick(iso, days) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return days > 3
    ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function ChartTooltip({ active, payload, label, unit, color, C }) {
  if (!active || !payload?.length) return null;
  const v = payload[0].value;
  return (
    <div style={{
      background: C.card2, border: `1px solid ${C.border2}`, borderRadius: 8,
      padding: "6px 10px", boxShadow: C.cardShadow, fontFamily: C.mono,
    }}>
      <div style={{ fontSize: 9, color: C.text3, marginBottom: 2 }}>
        {new Date(label).toLocaleString()}
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, color }}>
        {v == null ? "—" : `${v}${unit}`}
      </div>
    </div>
  );
}

function TrendPanel({ metric, rows, days, C }) {
  const color = C[metric.colorKey];
  const gradId = `grad-${metric.key}`;
  const values = rows.map(r => r[metric.key]).filter(v => v != null);
  const latest = values.length ? values[values.length - 1] : null;

  return (
    <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 11, padding: "12px 14px 8px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
        <span style={{ fontSize: 9.5, color: C.text3, fontWeight: 600, letterSpacing: 0.3, fontFamily: C.mono }}>
          {metric.label}
        </span>
        <span style={{ fontSize: 12, fontWeight: 700, color, fontFamily: C.sans }}>
          {latest == null ? "—" : `${latest}${metric.unit}`}
        </span>
      </div>
      {values.length < 2 ? (
        <div style={{ height: 90, display: "flex", alignItems: "center", justifyContent: "center", color: C.text3, fontFamily: C.mono, fontSize: 10 }}>
          Not enough history yet
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={90}>
          <ComposedChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.12} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke={C.border} strokeWidth={1} />
            <XAxis
              dataKey="date"
              tickFormatter={(v) => fmtTick(v, days)}
              tick={{ fontSize: 8.5, fill: C.text3, fontFamily: C.mono }}
              axisLine={{ stroke: C.border }}
              tickLine={false}
              minTickGap={40}
            />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fontSize: 8.5, fill: C.text3, fontFamily: C.mono }}
              axisLine={false}
              tickLine={false}
              width={36}
            />
            <Tooltip
              content={<ChartTooltip unit={metric.unit} color={color} C={C} />}
              cursor={{ stroke: C.border2, strokeWidth: 1 }}
            />
            <Area type="monotone" dataKey={metric.key} stroke="none" fill={`url(#${gradId})`} isAnimationActive={false} connectNulls />
            <Line
              type="monotone"
              dataKey={metric.key}
              stroke={color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: color, stroke: C.card, strokeWidth: 2 }}
              isAnimationActive={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export default function TrendCharts({ containerId }) {
  const { C } = useTheme();
  const [days, setDays] = useState(14);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getSensorHistory(containerId, days).then((data) => {
      if (!cancelled) { setRows(data || []); setLoading(false); }
    });
    return () => { cancelled = true; };
  }, [containerId, days]);

  const hasData = rows.length >= 2;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Label>TRENDS</Label>
        <div style={{ display: "flex", gap: 4 }}>
          {RANGE_PRESETS.map((p) => (
            <button
              key={p.days}
              onClick={() => setDays(p.days)}
              style={{
                fontSize: 9.5, fontFamily: C.mono, fontWeight: 600,
                padding: "3px 9px", borderRadius: 99, cursor: "pointer",
                border: `1px solid ${days === p.days ? C.green : C.border}`,
                background: days === p.days ? C.greenSoft : "transparent",
                color: days === p.days ? C.green : C.text3,
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      {!loading && !hasData ? (
        <div style={{
          background: C.card, border: `1px solid ${C.border}`, borderRadius: 11,
          padding: "20px 14px", textAlign: "center", color: C.text3, fontFamily: C.mono, fontSize: 11,
        }}>
          Not enough history yet for the last {days} days
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 9, opacity: loading ? 0.5 : 1, transition: "opacity 0.15s" }}>
          {METRICS.map((m) => (
            <TrendPanel key={m.key} metric={m} rows={rows} days={days} C={C} />
          ))}
        </div>
      )}
    </div>
  );
}
