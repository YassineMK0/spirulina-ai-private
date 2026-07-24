"use client";
import { useMemo, useState } from "react";
import { C } from "@/lib/theme";
import { Tag } from "@/components/atoms";

const SOURCE_LABEL = {
  rule:         "Threshold Rule",
  model:        "M1 Model",
  "rule+model": "Rule + Model",
  "model-24h":  "24h Pattern Check (LOF)",
};

const SEVERITIES = ["critical", "medium", "low"];
const DEDUP_WINDOW_MS = 3 * 60 * 60 * 1000; // collapse repeats of the same breach within 3h

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
  const [filter, setFilter] = useState("all");

  const palette = {
    critical: { bg: C.redSoft,   bd: "#4A1010", col: C.red   },
    medium:   { bg: C.amberSoft, bd: "#4A2808", col: C.amber },
    low:      { bg: C.card,      bd: C.border,  col: C.green },
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
          <FilterChip key={s} active={filter === s} label={s[0].toUpperCase() + s.slice(1)} count={counts[s]} col={palette[s].col} onClick={() => setFilter(s)} />
        ))}
      </div>

      {visible.length === 0 ? (
        <div style={{ color: C.text3, fontFamily: C.mono, fontSize: 11, textAlign: "center", padding: "30px 0" }}>
          No {filter} alerts.
        </div>
      ) : visible.map((g) => {
        const p = palette[g.severity] || palette.medium;
        const day = dayLabel(g.createdAt);
        const showHeader = day !== lastDay;
        lastDay = day;
        return (
          <div key={g.id}>
            {showHeader && (
              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: 1, color: C.text3, fontFamily: C.mono, textTransform: "uppercase", margin: "6px 0 3px" }}>
                {day}
              </div>
            )}
            <div style={{ background: p.bg, border: `1px solid ${p.bd}`, borderRadius: 11, padding: "13px 14px" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8, marginBottom: 7 }}>
                <div style={{ display: "flex", gap: 9, alignItems: "flex-start" }}>
                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: p.col, flexShrink: 0, marginTop: 3, animation: g.id === latestId ? "blink 1.2s infinite" : undefined }} />
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: p.col, marginBottom: 2 }}>
                      {SOURCE_LABEL[g.source] || SOURCE_LABEL.model} · {g.severity?.toUpperCase()}
                    </div>
                    {g.affected?.length > 0 && (
                      <div style={{ fontSize: 9.5, color: C.text3, fontFamily: C.mono }}>Affected: {g.affected.join(", ")}</div>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  {g.count > 1 && <Tag color={p.col}>×{g.count}</Tag>}
                  <Tag color={g.id === latestId ? C.red : C.green}>{g.id === latestId ? "LATEST" : "PAST"}</Tag>
                </div>
              </div>
              <div style={{ fontSize: 11, color: C.text2, lineHeight: 1.55, marginBottom: 8, paddingLeft: 17 }}>{g.text}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, paddingLeft: 17 }}>
                <span style={{ fontSize: 8.5, color: C.text3, fontFamily: C.mono }}>
                  {g.count > 1 ? `first ${g.firstAt} · last ${g.lastAt}` : g.lastAt}
                </span>
                {g.id === latestId && (
                  <button onClick={onGoChat} style={{ marginLeft: "auto", fontSize: 10, padding: "4px 12px", borderRadius: 20, background: C.redSoft, color: C.red, border: "1px solid #4A1010", fontWeight: 600 }}>
                    Ask agent →
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FilterChip({ active, label, count, col, onClick }) {
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
