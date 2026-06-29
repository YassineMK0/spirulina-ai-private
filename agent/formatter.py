"""Response formatter — turns raw LLM text + state data into rich markdown.

Three template types
--------------------
1. RAG answer      plain answer with inline source hints
2. Sensor card     markdown table: pH / EC / Temp / OD / Light + status icons
3. Alert           INFO / WARNING / CRITICAL banner with emoji

The public entry point is ``format_message(state)``.
It auto-selects and combines the relevant templates based on intent,
has_container, and what data is actually present in state.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Sensor parameter config — thresholds for status icons
# ---------------------------------------------------------------------------

# Maps lowercase normalised key -> (label, unit, ok_range, warn_range)
# ok_range: green ✅   warn_range: amber ⚠️   outside both: red 🔴
_SENSOR_CFG: dict[str, tuple[str, str, tuple, tuple]] = {
    "ph":          ("pH",           "",       (8.5, 10.5), (8.0, 11.0)),
    "ec":          ("EC",           "mS/cm",  (1.5, 4.0),  (1.0, 5.0)),
    "temperature": ("Temperature",  "°C",     (30,  38),   (25,  42)),
    "temp":        ("Temperature",  "°C",     (30,  38),   (25,  42)),
    "od":          ("OD680",        "",       (0.4, 1.2),  (0.2, 1.5)),
    "od680":       ("OD680",        "",       (0.4, 1.2),  (0.2, 1.5)),
    "water_level": ("Water Level",  "%",      (60,  100),  (30,  60)),
    "water":       ("Water Level",  "%",      (60,  100),  (30,  60)),
    "light":       ("Light",        "lux",    (5000, 40000), (2000, 60000)),
}

# Alert level definitions
_ALERT_LEVELS = {
    "INFO":     ("ℹ️",  "INFO"),
    "WARNING":  ("⚠️",  "WARNING"),
    "CRITICAL": ("🚨", "CRITICAL"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now().strftime("%H:%M")


def _normalise_key(key: str) -> str:
    return key.lower().replace(" ", "_").replace("-", "_")


def _status_icon(value: float, ok: tuple, warn: tuple) -> str:
    lo_ok, hi_ok = ok
    lo_warn, hi_warn = warn
    if lo_ok <= value <= hi_ok:
        return "✅"
    if lo_warn <= value <= hi_warn:
        return "⚠️"
    return "🔴"


def _status_label(value: float, ok: tuple, warn: tuple) -> str:
    lo_ok, hi_ok = ok
    lo_warn, hi_warn = warn
    if lo_ok <= value <= hi_ok:
        return f"Normal ({lo_ok}–{hi_ok})"
    if value < lo_ok:
        label = "Low" if value >= lo_warn else "Critical low"
    else:
        label = "High" if value <= hi_warn else "Critical high"
    return label


def _extract_sources(rag_context: str) -> list[str]:
    """Pull unique source filenames from a format_context() string."""
    pattern = re.compile(r"\[Source \d+:\s*([^,\]]+)")
    seen: set[str] = set()
    sources: list[str] = []
    for m in pattern.finditer(rag_context):
        name = m.group(1).strip()
        if name not in seen:
            seen.add(name)
            sources.append(name)
    return sources


def _alert_level_from_sensors(sensor: dict[str, Any]) -> list[dict]:
    """Derive alert dicts from sensor readings that are out of range."""
    alerts: list[dict] = []
    for raw_key, raw_val in sensor.items():
        nk = _normalise_key(raw_key)
        cfg = _SENSOR_CFG.get(nk)
        if cfg is None:
            continue
        label, unit, ok, warn = cfg
        try:
            v = float(raw_val)
        except (TypeError, ValueError):
            continue
        icon = _status_icon(v, ok, warn)
        if icon == "🔴":
            alerts.append({
                "level": "CRITICAL",
                "parameter": label,
                "value": f"{v} {unit}".strip(),
                "message": f"**{label}** is at **{v}{' ' + unit if unit else ''}** — outside safe limits.",
                "action": f"Check your {label.lower()} immediately and take corrective action.",
            })
        elif icon == "⚠️":
            alerts.append({
                "level": "WARNING",
                "parameter": label,
                "value": f"{v} {unit}".strip(),
                "message": f"**{label}** is at **{v}{' ' + unit if unit else ''}** — approaching limits.",
                "action": f"Monitor your {label.lower()} closely over the next hour.",
            })
    return alerts


# ---------------------------------------------------------------------------
# Template 1 — Plain RAG answer with source hints
# ---------------------------------------------------------------------------

def template_rag_answer(answer: str, rag_context: str = "") -> str:
    """Return the LLM answer as-is — no source footnote appended."""
    return answer or ""


# ---------------------------------------------------------------------------
# Template 2 — Sensor status card
# ---------------------------------------------------------------------------

def template_sensor_card(sensor: dict[str, Any], container_id: str = "") -> str:
    """Markdown table of all present sensor readings with status icons."""
    if not sensor:
        return ""

    header = f"## 📊 Sensor Status"
    if container_id:
        header += f"  —  `{container_id}`"
    header += f"  ·  _{_ts()}_"

    rows: list[str] = []
    unknown_rows: list[str] = []

    for raw_key, raw_val in sensor.items():
        nk = _normalise_key(raw_key)
        cfg = _SENSOR_CFG.get(nk)
        if cfg is None:
            unknown_rows.append(f"| {raw_key} | {raw_val} | — |")
            continue
        label, unit, ok, warn = cfg
        try:
            v = float(raw_val)
            icon = _status_icon(v, ok, warn)
            status = _status_label(v, ok, warn)
            display = f"{v} {unit}".strip()
            rows.append(f"| {label} | {display} | {icon} {status} |")
        except (TypeError, ValueError):
            rows.append(f"| {label} | {raw_val} | — |")

    table = (
        "| Parameter | Value | Status |\n"
        "|-----------|-------|--------|\n"
        + "\n".join(rows + unknown_rows)
    )
    return f"{header}\n\n{table}"


# ---------------------------------------------------------------------------
# Template 3 — 60-minute prediction summary
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Template 3 — Alert banner
# ---------------------------------------------------------------------------

def template_alert(
    level: str,
    message: str,
    action: str,
    parameter: str = "",
    container_id: str = "",
) -> str:
    """INFO / WARNING / CRITICAL banner."""
    level = level.upper()
    emoji, label = _ALERT_LEVELS.get(level, ("❓", level))

    title_parts = [f"**{label}**"]
    if parameter:
        title_parts.append(f"— {parameter}")

    footer_parts = [f"*{label} · {_ts()}*"]
    if container_id:
        footer_parts.append(f"Container: `{container_id}`")

    return (
        f"{emoji} {' '.join(title_parts)}\n\n"
        f"{message}\n\n"
        f"**Action:** {action}\n\n"
        f"{' · '.join(footer_parts)}"
    )


# ---------------------------------------------------------------------------
# Dispatch — combines templates based on intent and available data
# ---------------------------------------------------------------------------

_DIVIDER = "\n\n---\n\n"


def format_message(
    raw_answer: str,
    intent: str,
    has_container: bool,
    rag_context: str,
    sensor: dict[str, Any],
    ml_outputs: dict[str, Any],
    container_id: str,
) -> str:
    """Select and combine templates based on intent and available data.

    Always includes the LLM answer (template 1).
    Adds additional cards when relevant data is present.
    """
    intent = (intent or "KNOWLEDGE").upper()
    parts: list[str] = []

    # ── SYSTEM intent or anomaly alerts ─────────────────────────────────────
    if intent == "SYSTEM" or ml_outputs.get("anomaly"):
        # Auto-detect alerts from sensor readings
        sensor_alerts = _alert_level_from_sensors(sensor)
        # Also check the M1 anomaly detector's rule findings
        if ml_outputs.get("anomaly"):
            findings = ml_outputs.get("rule_findings") or []
            detail = "; ".join(f"{f['label']} ({f['detail']})" for f in findings) or "Unusual pattern in culture data."
            sensor_alerts.append({
                "level": "WARNING",
                "parameter": "ML Anomaly",
                "message": f"**Anomaly detected** — {detail}",
                "action": "Review your sensor history and inspect the culture visually.",
            })
        for alert_data in sensor_alerts:
            parts.append(template_alert(
                level=alert_data["level"],
                message=alert_data["message"],
                action=alert_data["action"],
                parameter=alert_data.get("parameter", ""),
                container_id=container_id,
            ))

    # ── Sensor card — show for UPDATE/SYSTEM or whenever an anomaly fires ───
    if has_container and sensor and (intent in ("UPDATE", "SYSTEM") or ml_outputs.get("anomaly")):
        parts.append(template_sensor_card(sensor, container_id))

    # ── LLM answer (always last, sources appended) ───────────────────────────
    answer_block = template_rag_answer(raw_answer, rag_context)

    # Edge case 2 — no container linked for an intent that benefits from one.
    # Append a one-line tip so the user knows how to unlock sensor/ML features.
    if not has_container and intent in ("UPDATE", "HARVEST", "SYSTEM"):
        container_tip = (
            "\n\n---\n"
            "_💡 **No container linked.** Enter your Container ID to enable "
            "real-time sensor monitoring, ML predictions, and container control._"
        )
        answer_block = (answer_block or "") + container_tip

    if answer_block:
        parts.append(answer_block)

    return _DIVIDER.join(p for p in parts if p)
