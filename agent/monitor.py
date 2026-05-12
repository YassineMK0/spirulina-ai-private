"""Proactive container monitor — threshold rules + alert generation.

Fires on a schedule (every 5 min via APScheduler in api/main.py).
For each active session with a container_id, reads sensors and checks
hardcoded thresholds. When a threshold is breached, generates a short
plain-language alert using the reasoning LLM.

Threshold rules (hardcoded — ML models will replace these later):
    pH          < 7.5             -> CRITICAL alert
    pH          > 10.8            -> WARNING
    temperature > 39 C            -> WARNING
    temperature < 20 C            -> WARNING
    od680       > 1.4             -> HARVEST alert
    conductivity_ms > 35          -> WARNING
    dissolved_o2_pct < 60         -> WARNING
    status == "error"             -> CRITICAL alert
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Threshold rules
# ---------------------------------------------------------------------------

# Each rule: (sensor_key, operator, threshold, severity, short_label)
# severity: "critical" | "warning" | "harvest"
_RULES: list[tuple[str, str, float, str, str]] = [
    ("pH",          "<",  7.5,    "critical", "pH crash"),
    ("pH",          ">",  10.8,   "warning",  "pH too high"),
    ("temperature", ">",  39.0,   "warning",  "overheating"),
    ("temperature", "<",  20.0,   "warning",  "too cold"),
    ("turbidity",   ">",  300.0,  "harvest",  "ready to harvest"),
    ("EC",          ">",  3500.0, "warning",  "high salinity"),
    ("DO",          "<",  4.0,    "warning",  "low oxygen"),
]

_SEVERITY_EMOJI = {
    "critical": "🚨",
    "warning":  "⚠️",
    "harvest":  "🌾",
}


def check_thresholds(sensor: dict) -> list[dict]:
    """Return a list of breached rules for the given sensor reading.

    Each breach is a dict:
        { key, value, threshold, operator, severity, label, emoji }
    """
    breaches = []
    for key, op, threshold, severity, label in _RULES:
        value = sensor.get(key)
        if value is None:
            continue
        breached = (op == "<" and value < threshold) or \
                   (op == ">" and value > threshold)
        if breached:
            breaches.append({
                "key":       key,
                "value":     value,
                "threshold": threshold,
                "operator":  op,
                "severity":  severity,
                "label":     label,
                "emoji":     _SEVERITY_EMOJI[severity],
            })

    # Also check status field directly
    if sensor.get("status") == "error" and not any(b["severity"] == "critical" for b in breaches):
        breaches.append({
            "key":      "status",
            "value":    "error",
            "threshold": None,
            "operator": "==",
            "severity": "critical",
            "label":    "sensor error",
            "emoji":    "🚨",
        })

    return breaches


def _run_ml_prediction(container_id: str) -> dict:
    """Run M1 LSTM anomaly model on the container history. Returns {} silently on failure."""
    try:
        import pandas as pd
        from agent.sensors import get_history
        from api.predict_lstm import predict_df, load_artifact

        history = get_history(container_id)
        if not history:
            return {}

        artifact = load_artifact()
        df       = pd.DataFrame(history)
        result   = predict_df(df, artifact)
        last     = result.iloc[-1]

        import numpy as np
        score    = float(last["anomaly_score"]) if not np.isnan(last["anomaly_score"]) else 0.0
        return {
            "anomaly":  bool(last["is_anomaly"]),
            "score":    round(score, 4),
            "severity": str(last["severity"]),
            "trend":    str(last["trend_direction"]),
        }
    except Exception as exc:
        print(f"[monitor] ML prediction failed: {exc}")
        return {}


def generate_alert_text(
    container_id: str,
    sensor: dict,
    breaches: list[dict],
    ml_result: dict | None = None,
) -> str:
    """Generate a short plain-language alert from the reasoning LLM.

    Falls back to a template-based message if the LLM call fails.
    """
    if not breaches:
        return ""

    # Build a compact breach summary for the prompt
    breach_lines = "\n".join(
        f"- {b['label'].upper()}: {b['key']} = {b['value']} "
        f"(threshold: {b['operator']} {b['threshold']})"
        for b in breaches
    )
    severity = max(
        (b["severity"] for b in breaches),
        key=lambda s: {"harvest": 0, "warning": 1, "critical": 2}[s],
    )
    emoji = _SEVERITY_EMOJI[severity]

    # Enrich with ML model result if available
    ml_lines = ""
    if ml_result and ml_result.get("anomaly"):
        ml_lines = (
            f"\nML Anomaly Model (M1-LSTM):\n"
            f"- Severity: {ml_result.get('severity', '?').upper()}\n"
            f"- Score: {ml_result.get('score', 0):.3f}\n"
            f"- Trend: {ml_result.get('trend', 'unknown')}\n"
        )
        if ml_result.get("severity") == "critical" and severity != "critical":
            severity = "critical"
            emoji = _SEVERITY_EMOJI["critical"]

    # Try LLM-generated alert
    try:
        from rag.generator.generate import reasoning_generate
        from agent.sensors import format_sensor_summary
        from rag.retriever.retrieve import retrieve, format_context

        context = format_context(retrieve("sensor anomaly alert spirulina", top_k=3))
        sensor_summary = format_sensor_summary(sensor)

        prompt = (
            f"Container {container_id} has triggered an automatic alert.\n\n"
            f"Breached thresholds:\n{breach_lines}\n"
            f"{ml_lines}\n"
            f"Write a short alert message (3-4 sentences max) for the container owner. "
            f"Tell them what is wrong, what to do right now, and what happens if they wait. "
            f"Start with '{emoji} Alert:'"
        )

        text = reasoning_generate(
            question=prompt,
            context=context,
            history=[],
            sensor_state=sensor,
        )
        return text.strip()

    except Exception:
        # Fallback: template-based alert
        labels = ", ".join(b["label"] for b in breaches)
        return (
            f"{emoji} **Auto-alert — {container_id}**\n\n"
            f"Threshold breached: **{labels}**\n\n"
            f"Check your container now and take corrective action."
        )


# ---------------------------------------------------------------------------
# Active session registry — maps user_id -> container_id
# ---------------------------------------------------------------------------
# Updated by the API on each /chat request.
# The scheduler reads this to know which containers to monitor.

_active_sessions: dict[str, str] = {}   # { user_id: container_id }
_last_alerts:     dict[str, str] = {}   # { user_id: last alert text } — dedup


def register_session(user_id: str, container_id: str) -> None:
    """Called by the API every time a chat request comes in."""
    if container_id:
        _active_sessions[user_id] = container_id
    elif user_id in _active_sessions:
        del _active_sessions[user_id]


def get_active_sessions() -> dict[str, str]:
    return dict(_active_sessions)


# ---------------------------------------------------------------------------
# Main check — called by the scheduler
# ---------------------------------------------------------------------------

def run_monitor_check(push_alert_fn) -> None:
    """Check all active sessions and push alerts for any breaches.

    Args:
        push_alert_fn: async callable(user_id, alert_text) that sends the
                       alert to the user's SSE stream.
    """
    from agent.sensors import get_sensor_reading

    for user_id, container_id in list(_active_sessions.items()):
        try:
            sensor    = get_sensor_reading(container_id)
            breaches  = check_thresholds(sensor)
            ml_result = _run_ml_prediction(container_id)

            # Trigger alert on threshold breach OR ML-detected anomaly
            ml_anomaly = ml_result.get("anomaly", False)
            if not breaches and not ml_anomaly:
                _last_alerts.pop(user_id, None)   # reset dedup on clean check
                continue

            # If ML fires but no threshold rule matched, create a synthetic breach entry
            if ml_anomaly and not breaches:
                top_sensor = (
                    max(ml_result["sensor_attribution"], key=ml_result["sensor_attribution"].get)
                    if ml_result.get("sensor_attribution") else "sensor"
                )
                breaches = [{
                    "key":       top_sensor,
                    "value":     sensor.get(top_sensor, "?"),
                    "threshold": None,
                    "operator":  "ml",
                    "severity":  ml_result.get("severity", "warning"),
                    "label":     f"ML anomaly ({top_sensor})",
                    "emoji":     _SEVERITY_EMOJI.get(ml_result.get("severity", "warning"), "⚠️"),
                }]

            # Dedup key = sorted breach labels (not LLM text — LLMs are non-deterministic)
            breach_key = ",".join(sorted(b["label"] for b in breaches))
            if _last_alerts.get(user_id) == breach_key:
                continue

            alert_text = generate_alert_text(container_id, sensor, breaches, ml_result)
            _last_alerts[user_id] = breach_key
            push_alert_fn(user_id, alert_text)

        except Exception as exc:
            print(f"[monitor] error checking {container_id} for {user_id}: {exc}")
