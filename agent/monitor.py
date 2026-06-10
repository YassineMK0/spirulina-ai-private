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
    ("EC",          ">",  30000.0, "warning",  "high salinity"),   # 30 mS/cm = 30000 µS/cm
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
    """Run M1 IsolationForest on the container history. Returns {} silently on failure."""
    try:
        import pandas as pd
        from agent.sensors import get_history
        from api.predict_isolationforest import predict_df, load_artifact

        history = get_history(container_id)
        if not history:
            return {}

        artifact = load_artifact()
        df       = pd.DataFrame(history)
        result   = predict_df(df, artifact)
        last     = result.iloc[-1]

        import numpy as np
        import json as _json
        score = float(last["anomaly_score"]) if not np.isnan(last["anomaly_score"]) else 0.0
        attr_raw = last.get("sensor_attribution", "{}")
        attr = _json.loads(attr_raw) if isinstance(attr_raw, str) else (attr_raw or {})
        return {
            "anomaly":            bool(last["is_anomaly"]),
            "score":              round(score, 4),
            "severity":           str(last["severity"]),
            "trend":              str(last["trend_direction"]),
            "sensor_attribution": attr,
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

    # Upgrade severity if ML model says critical
    if ml_result and ml_result.get("severity") == "critical" and severity != "critical":
        severity = "critical"
        emoji = _SEVERITY_EMOJI["critical"]

    # Current sensor readings for context
    _sensor_keys = ("pH", "EC", "DO", "temperature", "turbidity", "luminosity")
    sensor_lines = "\n".join(
        f"  {k}: {sensor[k]}" for k in _sensor_keys if k in sensor
    )

    # ML attribution block (which sensors drove the anomaly and by how much)
    ml_lines = ""
    if ml_result and ml_result.get("anomaly"):
        attr = ml_result.get("sensor_attribution") or {}
        top = list(attr.items())[:3]
        attr_str = (
            ", ".join(f"{k} ({round(v * 100)}%)" for k, v in top)
            if top else "undetermined"
        )
        ml_lines = (
            f"\nM1 IsolationForest model:\n"
            f"  severity={ml_result.get('severity','?').upper()}  "
            f"score={ml_result.get('score', 0):.3f}  "
            f"trend={ml_result.get('trend', 'stable')}\n"
            f"  primary anomaly drivers: {attr_str}\n"
        )

    # Try LLM-generated alert
    try:
        from rag.generator.generate import reasoning_generate
        from rag.retriever.retrieve import retrieve, format_context

        context = format_context(retrieve("spirulina anomaly diagnosis corrective action", top_k=4))

        prompt = (
            f"=== AUTOMATIC ALERT — Container {container_id} ===\n\n"
            f"Current sensor readings:\n{sensor_lines}\n\n"
            f"Triggered threshold alerts:\n{breach_lines}\n"
            f"{ml_lines}\n"
            f"You are an expert spirulina cultivation assistant (AlgaePool protocol, Dominique Delobel, June 2026).\n"
            f"Answer in exactly 3 sentences:\n"
            f"1. Name the specific problem using the exact sensor values "
            f"(e.g. 'pH of 7.0 indicates Chlorella contamination or CO2 over-injection', "
            f"'temperature of 42 C signals heater malfunction', "
            f"'DO of 2.5 mg/L means oxygen depletion from bacterial bloom').\n"
            f"2. State the one action the operator must take RIGHT NOW (be specific — "
            f"e.g. 'add NaHCO3 to raise pH', 'shut off heater and add cold water', "
            f"'increase aeration to emergency level').\n"
            f"3. State what happens if untreated within 2 hours (be direct about culture loss).\n"
            f"Start with '{emoji} {severity.upper()} — {container_id}:' then give sentence 1, 2, 3.\n"
            f"Do NOT repeat the threshold table. Use the exact sensor values from above."
        )

        text = reasoning_generate(
            question=prompt,
            context=context,
            history=[],
            sensor_state=sensor,
        )
        return text.strip()

    except Exception:
        labels = ", ".join(b["label"] for b in breaches)
        vals = "  ".join(f"{k}={sensor.get(k,'?')}" for k in _sensor_keys if k in sensor)
        return (
            f"{emoji} **{severity.upper()} — {container_id}**\n\n"
            f"**{labels}**\n\n"
            f"{vals}\n\n"
            f"Take immediate corrective action."
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

    The threshold + ML check runs synchronously (fast, < 1 s).
    The Groq LLM call is offloaded to a daemon thread so the scheduler
    job returns immediately and never blocks the next 15-second tick.
    """
    import threading
    from agent.sensors import get_sensor_reading

    if not _active_sessions:
        print("[monitor] no active sessions — skipping check")
        return

    for user_id, container_id in list(_active_sessions.items()):
        try:
            sensor    = get_sensor_reading(container_id)
            print(f"[monitor] checking {container_id} for {user_id[:8]}...  pH={sensor.get('pH')} DO={sensor.get('DO')} temp={sensor.get('temperature')} EC={sensor.get('EC')}")
            breaches  = check_thresholds(sensor)
            ml_result = _run_ml_prediction(container_id)

            ml_anomaly = ml_result.get("anomaly", False)
            if not breaches and not ml_anomaly:
                _last_alerts.pop(user_id, None)
                continue

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

            breach_key = ",".join(sorted(b["label"] for b in breaches))
            if _last_alerts.get(user_id) == breach_key:
                continue

            # Mark dedup NOW so next tick doesn't re-fire while LLM is running
            _last_alerts[user_id] = breach_key

            severity = max(
                (b["severity"] for b in breaches),
                key=lambda s: {"harvest": 0, "warning": 1, "critical": 2}[s],
            )

            # Offload the slow Groq call — scheduler job returns immediately
            def _llm_and_push(uid, cid, s, br, ml, sev):
                try:
                    text = generate_alert_text(cid, s, br, ml)
                    if not text:
                        return
                    try:
                        from data.alerts import alert_store
                        alert_store.save(uid, cid, text, sev)
                    except Exception as _e:
                        print(f"[monitor] alert DB save failed: {_e}")
                    push_alert_fn(uid, text)
                except Exception as exc:
                    print(f"[monitor] alert generation failed: {exc}")

            threading.Thread(
                target=_llm_and_push,
                args=(user_id, container_id, sensor, breaches, ml_result, severity),
                daemon=True,
                name=f"alert-{container_id[:8]}",
            ).start()

        except Exception as exc:
            print(f"[monitor] error checking {container_id} for {user_id}: {exc}")
