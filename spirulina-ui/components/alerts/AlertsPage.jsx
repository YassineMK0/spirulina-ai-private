"use client";
import { useMemo, useState } from "react";
import { useTheme } from "@/lib/ThemeContext";
import { Tag } from "@/components/atoms";

// Friendly, non-technical copy -- an operator shouldn't have to know what
// "rule engine" or "LOF" means to understand their own tank.
const SOURCE_LABEL = {
  rule:         "Live Check",
  model:        "AI Watch",
  "rule+model": "Confirmed",
  "model-24h":  "Daily Review",
};

const SENSOR_LABEL = {
  pH: "pH Level", EC: "Nutrient Level", DO: "Oxygen Level",
  temperature: "Temperature", turbidity: "Water Density",
  status: "Sensor Health", combination_model: "Overall Pattern",
};

const SEVERITIES = ["critical", "medium", "low"];
const DEDUP_WINDOW_MS = 3 * 60 * 60 * 1000; // collapse repeats of the same breach within 3h

// Older stored alerts (from before alert text was rewritten to be plain-
// language) still carry a technical "🚨 CRITICAL — container-01:" prefix and
// a trailing "_Source: ..._" line baked into the message. New alerts never
// have either -- severity/source are shown as badges from structured fields
// instead -- but this keeps historical alerts from looking broken/technical.
function cleanMessage(text) {
  if (!text) return "";
  return text
    .replace(/^[^\w]*\**\s*(CRITICAL|WARNING|HARVEST)\s*—\s*[\w-]+\**:?\s*\n*/i, "")
    .replace(/\n*_Source:[^\n]*_\s*$/i, "")
    .trim();
}

function groupSignature(a) {
  // `detail` is a coarse, direction-aware breach signature from the backend
  // (e.g. "pH:7" vs "pH:12") -- without it, two genuinely different episodes
  // on the same sensor (a crash vs a spike) collapse into one card, since
  // rules.py uses a single label for both directions of a given check.
  return `${a.source}|${a.severity}|${(a.affected || []).slice().sort().join(",")}|${a.detail || ""}`;
}

// Chronological (oldest -> newest) collapse of consecutive same-signature
// alerts, then returned newest-first for display.
function buildTimeline(alerts) {
  const sorted = [...alerts].sort((a, b) => {
    const ta = a.createdAt ? new Date(a.createdAt).getTime() : 0;
    const tb = b.createdAt ? new Date(b.createdAt).getTime() : 0;
    return ta - tb;
  });

  const groups = [];
  for (const a of sorted) {
    const key = groupSignature(a);
    const t = a.createdAt ? new Date(a.createdAt).getTime() : null;
    const last = groups[groups.length - 1];
    if (last && last.key === key && (t == null || last.lastAtMs == null || t - last.lastAtMs <= DEDUP_WINDOW_MS)) {
      last.count += 1;
      last.lastAt = a.time;
      last.lastAtMs = t;
      last.text = a.text;
      last.id = a.id;
    } else {
      groups.push({
        key, id: a.id, text: a.text, severity: a.severity,
        source: a.source, affected: a.affected, count: 1,
        firstAt: a.time, lastAt: a.time, lastAtMs: t, createdAt: a.createdAt,
      });
    }
  }
  return groups.reverse();
}

function dayLabel(iso) {
  if (!iso) return "Undated";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Undated";
  const now = new Date();
  const startOfDay = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diffDays = Math.round((startOfDay(now) - startOfDay(d)) / 86_400_000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, {
    month: "short", day: "numeric",
    year: d.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
  });
}

export default function AlertsPage({ alerts = [], onGoChat }) {
  const { C } = useTheme();
  const [filter, setFilter] = useState("all");

  const SEVERITY_META = {
    critical: { label: "Urgent",       icon: "🚨", bg: C.redSoft,   bd: "#4A1010", col: C.red   },
    medium:   { label: "Heads Up",     icon: "⚠️", bg: C.amberSoft, bd: "#4A2808", col: C.amber },
    low:      { label: "Good to Know", icon: "🌱", bg: C.card,      bd: C.border,  col: C.green },
  };

  const timeline = useMemo(() => buildTimeline(alerts), [alerts]);
  const counts = useMemo(() => {
    const c = { critical: 0, medium: 0, low: 0 };
    for (const g of timeline) if (c[g.severity] != null) c[g.severity]++;
    return c;
  }, [timeline]);
  const latestId = timeline[0]?.id;
  const visible = filter === "all" ? timeline : timeline.filter((g) => g.severity === filter);

  if (alerts.length === 0) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: C.text3, fontFamily: C.mono, fontSize: 12 }}>
        No alerts yet.
      </div>
    );
  }

  let lastDay = null;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "14px 18px", display: "flex", flexDirection: "column", gap: 9 }}>
      <div style={{ display: "flex", gap: 6 }}>
        <FilterChip active={filter === "all"} label="All" count={timeline.length} col={C.text2} onClick={() => setFilter("all")} />
        {SEVERITIES.map((s) => (
          <FilterChip key={s} active={filter === s} label={SEVERITY_META[s].label} count={counts[s]} col={SEVERITY_META[s].col} onClick={() => setFilter(s)} />
        ))}
      </div>

      {visible.length === 0 ? (
        <div style={{ color: C.text3, fontFamily: C.mono, fontSize: 11, textAlign: "center", padding: "30px 0" }}>
          Nothing here.
        </div>
      ) : visible.map((g) => {
        const meta = SEVERITY_META[g.severity] || SEVERITY_META.medium;
        const day = dayLabel(g.createdAt);
        const showHeader = day !== lastDay;
        lastDay = day;
        const isLatest = g.id === latestId;
        return (
          <div key={g.id}>
            {showHeader && (
              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: 1, color: C.text3, fontFamily: C.mono, textTransform: "uppercase", margin: "6px 0 3px" }}>
                {day}
              </div>
            )}
            <div style={{
              background: meta.bg, border: `1px solid ${meta.bd}`, borderRadius: 14,
              padding: "16px 16px 13px", boxShadow: isLatest ? `0 0 0 1px ${meta.col}22, 0 4px 18px rgba(0,0,0,0.25)` : "none",
            }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 11 }}>
                <div style={{
                  width: 34, height: 34, borderRadius: 10, flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 17, background: `${meta.col}18`,
                }}>
                  {meta.icon}
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
                    <span style={{ fontSize: 13.5, fontWeight: 800, color: meta.col }}>{meta.label}</span>
                    <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
                      {g.count > 1 && <Tag color={meta.col}>×{g.count}</Tag>}
                      {isLatest && <Tag color={meta.col}>NEW</Tag>}
                    </div>
                  </div>

                  <div style={{ fontSize: 13.5, color: C.text, lineHeight: 1.6, fontWeight: 500, marginBottom: 10 }}>
                    {cleanMessage(g.text)}
                  </div>

                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
                    {(g.affected || []).map((k) => (
                      <span key={k} style={{
                        fontSize: 9.5, fontWeight: 600, color: C.text2, background: C.card2,
                        border: `1px solid ${C.border}`, borderRadius: 20, padding: "2px 9px",
                      }}>
                        {SENSOR_LABEL[k] || k}
                      </span>
                    ))}
                    <span style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono, marginLeft: (g.affected?.length ? 2 : 0) }}>
                      {SOURCE_LABEL[g.source] || SOURCE_LABEL.model}
                    </span>
                    <span style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono }}>
                      · {g.count > 1 ? `${g.firstAt}–${g.lastAt}` : g.lastAt}
                    </span>
                    {isLatest && (
                      <button
                        onClick={() => onGoChat?.(`My container just got this alert: "${cleanMessage(g.text)}" — what should I do?`)}
                        style={{
                          marginLeft: "auto", fontSize: 10.5, padding: "5px 13px", borderRadius: 20,
                          background: meta.col, color: C.bg, border: "none", fontWeight: 700, cursor: "pointer",
                        }}
                      >
                        Ask the assistant →
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FilterChip({ active, label, count, col, onClick }) {
  const { C } = useTheme();
  return (
    <button
      onClick={onClick}
      style={{
        fontSize: 10, fontFamily: C.mono, fontWeight: 600,
        padding: "4px 10px", borderRadius: 20, cursor: "pointer",
        border: `1px solid ${active ? col : C.border}`,
        background: active ? `${col}14` : "transparent",
        color: active ? col : C.text3,
      }}
    >
      {label} {count}
    </button>
  );
}
