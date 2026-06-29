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

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger("spirulina.monitor")


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


_anomaly_detector = None  # lazy-loaded singleton (joblib load is not free)

# anomaly_model rule-finding parameter names -> agent sensor reading keys
_PARAM_TO_SENSOR_KEY = {
    "pH": "pH", "EC": "EC", "DO": "DO",
    "Temperature": "temperature", "Luminosite": "luminosity",
}


def _get_anomaly_detector():
    global _anomaly_detector
    if _anomaly_detector is None:
        from models.anomaly_model.detector import AnomalyDetector
        _anomaly_detector = AnomalyDetector.load()
    return _anomaly_detector


def _normalize_ec(ec: float | None) -> float | None:
    """Agent reports EC in uS/cm, the model was trained on mS/cm."""
    if ec is not None and ec > 100:
        return ec / 1000.0
    return ec


def _to_snapshot(row: dict) -> dict:
    """Map an agent sensor row to the anomaly_model snapshot format.

    Turbidite is intentionally omitted: the agent's turbidity sensor reports
    NTU and no NTU->OD680 conversion factor exists yet. rules.evaluate_rules
    treats a missing Turbidite key as "skip that check" (see rules.py), and
    the combination model was retrained without Turbidite as a feature
    entirely -- see models/anomaly_model/README.md.
    """
    return {
        "pH":          row.get("pH"),
        "EC":          _normalize_ec(row.get("EC")),
        "DO_mgL":      row.get("DO"),
        "Temperature": row.get("temperature"),
        "Luminosite":  row.get("luminosity"),
    }


def _build_daily_context(container_id: str) -> dict | None:
    """Aggregate the last 24h of stored readings into the feature vector the
    combination model (LOF) expects (pH/EC/DO_mgL + their day-over-day diff,
    Temperature/Luminosite mean/min/max). Returns None if there isn't enough
    history yet -- the combination-model check just skips that container
    until the agent has accumulated a day of readings."""
    from data.store import sensor_store

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = sensor_store.get_since(container_id, since)
    if len(rows) < 2:
        return None

    temps = [r["temperature"] for r in rows if r.get("temperature") is not None]
    lums  = [r["luminosity"]  for r in rows if r.get("luminosity")  is not None]
    if not temps or not lums:
        return None

    current, oldest = rows[-1], rows[0]
    ec_now = _normalize_ec(current.get("EC"))
    ec_old = _normalize_ec(oldest.get("EC"))
    if current.get("pH") is None or ec_now is None or current.get("DO") is None:
        return None

    return {
        "pH":               current["pH"],
        "EC":               ec_now,
        "DO_mgL":           current["DO"],
        "Temperature_mean": sum(temps) / len(temps),
        "Temperature_min":  min(temps),
        "Temperature_max":  max(temps),
        "Luminosite_mean":  sum(lums) / len(lums),
        "Luminosite_min":   min(lums),
        "Luminosite_max":   max(lums),
        "pH_diff":          current["pH"] - (oldest.get("pH") if oldest.get("pH") is not None else current["pH"]),
        "EC_diff":          ec_now - (ec_old if ec_old is not None else ec_now),
        "DO_mgL_diff":      current["DO"] - (oldest.get("DO") if oldest.get("DO") is not None else current["DO"]),
    }


def _run_ml_prediction(container_id: str) -> dict:
    """Run the M1 anomaly detector (rules + Isolation Forest + seasonal) on the
    container's recent history. Returns {} silently on failure."""
    try:
        from agent.sensors import get_history

        history = get_history(container_id, n=2)
        if not history:
            return {}

        current  = history[-1]
        previous = history[-2] if len(history) > 1 else None

        hour_of_day        = None
        minutes_since_prev = None
        try:
            now_ts = datetime.fromisoformat(current["date"])
            hour_of_day = now_ts.hour + now_ts.minute / 60.0
            if previous:
                prev_ts = datetime.fromisoformat(previous["date"])
                minutes_since_prev = (now_ts - prev_ts).total_seconds() / 60.0
        except (KeyError, ValueError):
            pass

        detector = _get_anomaly_detector()
        result = detector.evaluate(
            snapshot=_to_snapshot(current),
            previous=_to_snapshot(previous) if previous else None,
            minutes_since_prev=minutes_since_prev,
            hour_of_day=hour_of_day,
            daily_context=None,  # IF layer needs Turbidite -- disabled, see _to_snapshot
        )

        overall = result["overall_severity"]
        return {
            "anomaly":       overall >= 2,
            "severity":      {3: "critical", 2: "warning"}.get(overall),
            "rule_findings": result["rule_findings"],
            "seasonal":      result["seasonal"],
        }
    except Exception as exc:
        log.warning("anomaly detector failed: %s", exc)
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

    # ML findings block (which checks drove the anomaly and why)
    ml_lines = ""
    if ml_result and ml_result.get("anomaly"):
        findings = ml_result.get("rule_findings") or []
        finding_str = (
            "; ".join(f"{f['label']} ({f['detail']})" for f in findings)
            if findings else "undetermined"
        )
        seasonal_hits = [
            f"{sensor} z={v['zscore']:.1f}"
            for sensor, v in (ml_result.get("seasonal") or {}).items()
            if v.get("anomaly")
        ]
        ml_lines = (
            f"\nM1 anomaly detector:\n"
            f"  severity={ml_result.get('severity', '?').upper()}\n"
            f"  findings: {finding_str}\n"
        )
        if seasonal_hits:
            ml_lines += f"  seasonal deviation: {', '.join(seasonal_hits)}\n"

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
_last_combination_alerts: dict[str, str] = {}  # { user_id: last combination-model alert key } — dedup


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

    Runs the cheap rule engine (check_thresholds + anomaly_model's
    rules.py/seasonal.py layers) -- this is the job scheduled on the
    MONITOR_RULE_INTERVAL_SECONDS cadence (default 900s = 15min, matching
    real MQTT message cadence; see api/main.py). The combination model (LOF)
    is intentionally NOT run here -- it needs 24h of rolling history and is
    scored separately by run_combination_model_check() on its own cron job.

    The threshold + rule check runs synchronously (fast, < 1 s).
    The Groq LLM call is offloaded to a daemon thread so the scheduler
    job returns immediately and never blocks the next tick.
    """
    import threading
    from agent.sensors import get_sensor_reading

    if not _active_sessions:
        log.debug("no active sessions — skipping check")
        return

    for user_id, container_id in list(_active_sessions.items()):
        try:
            sensor    = get_sensor_reading(container_id)
            log.info("checking %s for %s  pH=%s DO=%s temp=%s EC=%s",
                     container_id, user_id[:8],
                     sensor.get("pH"), sensor.get("DO"),
                     sensor.get("temperature"), sensor.get("EC"))
            breaches  = check_thresholds(sensor)
            ml_result = _run_ml_prediction(container_id)

            ml_anomaly      = ml_result.get("anomaly", False)
            had_rule_breach = bool(breaches)  # before any ML-only synthesis below
            if not breaches and not ml_anomaly:
                _last_alerts.pop(user_id, None)
                continue

            if ml_anomaly and not breaches:
                findings = ml_result.get("rule_findings") or []
                if findings:
                    top_finding = max(findings, key=lambda f: f["severity"])
                    param       = top_finding["parameter"]
                    label       = top_finding["label"]
                else:
                    param, label = "sensor", "ML anomaly"
                sensor_key = _PARAM_TO_SENSOR_KEY.get(param, param)
                breaches = [{
                    "key":       sensor_key,
                    "value":     sensor.get(sensor_key, "?"),
                    "threshold": None,
                    "operator":  "ml",
                    "severity":  ml_result.get("severity", "warning"),
                    "label":     f"ML anomaly ({label})",
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
            # Same upgrade rule as generate_alert_text -- keep the severity saved/pushed
            # here in sync with the one baked into the alert text itself.
            if ml_result.get("severity") == "critical" and severity != "critical":
                severity = "critical"

            # Sensors actually implicated, for display (e.g. "pH, Temperature")
            affected = list(dict.fromkeys(
                [b["key"] for b in breaches] +
                [_PARAM_TO_SENSOR_KEY.get(f["parameter"], f["parameter"])
                 for f in (ml_result.get("rule_findings") or [])]
            ))

            # Who actually caught this: the agent's basic hardcoded thresholds
            # (check_thresholds, e.g. the NTU turbidity/harvest rule), the M1
            # anomaly detector (models/anomaly_model), or both independently.
            if had_rule_breach and ml_anomaly:
                source = "rule+model"
            elif had_rule_breach:
                source = "rule"
            else:
                source = "model"

            # Offload the slow Groq call — scheduler job returns immediately
            def _llm_and_push(uid, cid, s, br, ml, sev, aff, src):
                try:
                    text = generate_alert_text(cid, s, br, ml)
                    if not text:
                        return
                    try:
                        from data.alerts import alert_store
                        alert_store.save(uid, cid, text, sev)
                    except Exception as _e:
                        log.error("alert DB save failed: %s", _e)
                    push_alert_fn(uid, text, sev, aff, src)
                except Exception as exc:
                    log.error("alert generation failed: %s", exc, exc_info=True)

            threading.Thread(
                target=_llm_and_push,
                args=(user_id, container_id, sensor, breaches, ml_result, severity, affected, source),
                daemon=True,
                name=f"alert-{container_id[:8]}",
            ).start()

        except Exception as exc:
            log.error("error checking %s for %s: %s", container_id, user_id, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Combination model (LOF) check — called by its own 24h cron job
# ---------------------------------------------------------------------------

def run_combination_model_check(push_alert_fn) -> None:
    """Re-score the combination-anomaly model (Local Outlier Factor) once a
    day per active session (cron job in api/main.py — see
    models/anomaly_model/README.md: "it's a slow-moving signal").

    Unlike run_monitor_check, this never evaluates the rule/seasonal layers
    for alerting purposes (that's the 15-min job's job) — it only acts on
    detector.evaluate()'s combination_model result.
    """
    import threading
    from agent.sensors import get_sensor_reading

    if not _active_sessions:
        log.debug("no active sessions — skipping combination-model check")
        return

    for user_id, container_id in list(_active_sessions.items()):
        try:
            daily_context = _build_daily_context(container_id)
            if daily_context is None:
                log.debug("combination model: not enough 24h history yet for %s", container_id)
                continue

            sensor = get_sensor_reading(container_id)
            if not sensor:
                continue

            detector = _get_anomaly_detector()
            result = detector.evaluate(
                snapshot=_to_snapshot(sensor),
                hour_of_day=None,       # seasonal layer already covered by run_monitor_check
                daily_context=daily_context,
            )
            combo = result["combination_model"]
            if not combo or not combo["anomaly"]:
                _last_combination_alerts.pop(user_id, None)
                continue

            breach_key = f"combination:{container_id}:{round(combo['score'], 2)}"
            if _last_combination_alerts.get(user_id) == breach_key:
                continue
            _last_combination_alerts[user_id] = breach_key

            breach = {
                "key":       "combination_model",
                "value":     round(combo["score"], 3),
                "threshold": None,
                "operator":  "lof",
                "severity":  "warning",
                "label":     "Combination anomaly (24h pattern)",
                "emoji":     _SEVERITY_EMOJI["warning"],
            }
            ml_result = {
                "anomaly":  True,
                "severity": "warning",
                "rule_findings": [{
                    "parameter": "combination_model",
                    "severity":  2,
                    "label":     "Anomalie combinee (LOF)",
                    "detail":    f"score={combo['score']:.3f} — inhabituel par rapport "
                                 f"a l'historique 24h de ce site",
                }],
                "seasonal": {},
            }

            def _llm_and_push(uid, cid, s, br, ml):
                try:
                    text = generate_alert_text(cid, s, [br], ml)
                    if not text:
                        return
                    try:
                        from data.alerts import alert_store
                        alert_store.save(uid, cid, text, "warning")
                    except Exception as _e:
                        log.error("alert DB save failed: %s", _e)
                    push_alert_fn(uid, text, "warning", ["combination_model"], "model-24h")
                except Exception as exc:
                    log.error("combination-model alert generation failed: %s", exc, exc_info=True)

            threading.Thread(
                target=_llm_and_push,
                args=(user_id, container_id, sensor, breach, ml_result),
                daemon=True,
                name=f"combo-alert-{container_id[:8]}",
            ).start()

        except Exception as exc:
            log.error("combination-model check failed for %s/%s: %s", container_id, user_id, exc, exc_info=True)
