"""Proactive container monitor — threshold rules + alert generation.

Fires on a schedule (every 15 min via APScheduler in api/main.py).
For each active session with a container_id, reads sensors and checks
thresholds. When a threshold is breached, generates a short plain-language
alert using the reasoning LLM.

Threshold rules: pH/EC/Temperature/DO/Luminosite (+ rate-of-change) are
delegated to models/anomaly_model/rules.py -- the same expert table the M1
anomaly detector uses -- so this fast loop and the ML path never disagree on
thresholds. Only two checks stay local because they have no equivalent
there: turbidity/harvest (agent's NTU sensor has no OD680 calibration) and
raw sensor "error" status.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger("spirulina.monitor")


# ---------------------------------------------------------------------------
# Threshold rules
# ---------------------------------------------------------------------------

_HARVEST_TURBIDITY_NTU = 300.0

_SEVERITY_EMOJI = {
    "critical": "🚨",
    "warning":  "⚠️",
    "harvest":  "🌾",
}

# Findings from rules.py need at least these snapshot values to evaluate --
# evaluate_rules indexes them directly and doesn't tolerate None.
_REQUIRED_SNAPSHOT_KEYS = ("pH", "EC", "DO_mgL", "Temperature", "Luminosite")


def check_thresholds(
    sensor: dict,
    previous: dict | None = None,
    minutes_since_prev: float | None = None,
) -> list[dict]:
    """Return a list of breached rules for the given sensor reading.

    pH/EC/Temperature/DO/Luminosite checks (including rate-of-change, when
    `previous`/`minutes_since_prev` are supplied) are delegated to
    models/anomaly_model/rules.evaluate_rules -- the same table the M1
    detector uses. Severity-1 (informational) findings are not surfaced as
    breaches here; they're only actionable in aggregate via the ML path.

    Each breach is a dict:
        { key, value, threshold, operator, severity, label, detail, emoji }
    """
    from models.anomaly_model import rules as _rules

    breaches: list[dict] = []

    snapshot      = _to_snapshot(sensor)
    prev_snapshot = _to_snapshot(previous) if previous else None

    if all(snapshot.get(k) is not None for k in _REQUIRED_SNAPSHOT_KEYS):
        for f in _rules.evaluate_rules(snapshot, prev_snapshot, minutes_since_prev):
            if f.severity < 2:
                continue  # informational only, not independently alertable
            sensor_key = _PARAM_TO_SENSOR_KEY.get(f.parameter, f.parameter)
            severity   = "critical" if f.severity == 3 else "warning"
            breaches.append({
                "key":       sensor_key,
                "value":     sensor.get(sensor_key),
                "threshold": None,
                "operator":  "rule",
                "severity":  severity,
                "label":     f.label,
                "detail":    f.detail,
                "emoji":     _SEVERITY_EMOJI[severity],
            })

    # Turbidity/harvest: agent's NTU turbidity sensor has no OD680 calibration
    # yet (see _to_snapshot), so it can't go through rules.evaluate_rules.
    turbidity = sensor.get("turbidity")
    if turbidity is not None and turbidity > _HARVEST_TURBIDITY_NTU:
        breaches.append({
            "key":       "turbidity",
            "value":     turbidity,
            "threshold": _HARVEST_TURBIDITY_NTU,
            "operator":  ">",
            "severity":  "harvest",
            "label":     "ready to harvest",
            "detail":    f"turbidity={turbidity:.1f} NTU (>{_HARVEST_TURBIDITY_NTU:.0f})",
            "emoji":     _SEVERITY_EMOJI["harvest"],
        })

    # Sensor error status: no equivalent in rules.py
    if sensor.get("status") == "error" and not any(b["severity"] == "critical" for b in breaches):
        breaches.append({
            "key":       "status",
            "value":     "error",
            "threshold": None,
            "operator":  "==",
            "severity":  "critical",
            "label":     "sensor error",
            "detail":    "status=error",
            "emoji":     "🚨",
        })

    return breaches


def _breach_signature(breaches: list[dict]) -> str:
    """Coarse, direction-aware identity for a set of breaches -- used by the
    frontend to tell two genuinely different episodes on the same sensor
    apart (e.g. pH crashing to 7.0 vs pH spiking to 12.0), which the label
    alone can't do since rules.py uses one label for both directions of a
    given check. Values are rounded to the nearest whole unit so a single
    persisting episode still collapses across repeated ticks despite sensor
    noise, while genuinely different values (7 vs 12) stay distinct."""
    parts = []
    for b in sorted(breaches, key=lambda b: b["key"]):
        v = b["value"]
        v = round(v) if isinstance(v, (int, float)) else v
        parts.append(f"{b['key']}:{v}")
    return ",".join(parts)


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


# Who actually caught the anomaly -- shown verbatim in every alert so it's
# never ambiguous whether a fast threshold rule or the ML predictor fired.
_SOURCE_LABEL = {
    "rule":       "Threshold rule",
    "model":      "M1 predictor (rule engine + seasonal ML, run every 15 min)",
    "rule+model": "Threshold rule + M1 predictor (agreed independently)",
    "model-24h":  "M1 predictor -- 24h pattern check (LOF, runs once/day)",
}


def generate_alert_text(
    container_id: str,
    sensor: dict,
    breaches: list[dict],
    ml_result: dict | None = None,
    source: str = "rule",
) -> str:
    """Generate a short plain-language alert from the reasoning LLM.

    Falls back to a template-based message if the LLM call fails. Either way,
    the returned text always ends with an explicit "Source:" line stating
    whether a threshold rule or the ML predictor (or both) fired -- see
    _SOURCE_LABEL -- so that's never left to the LLM to get right or to a
    frontend badge alone to convey.
    """
    if not breaches:
        return ""

    source_line = f"\n\n_Source: {_SOURCE_LABEL.get(source, source)}_"

    # Build a compact breach summary for the prompt -- prefer the rule's own
    # detail string (exact values + threshold baked in by rules.py) when
    # available, since it's more precise than the generic key/threshold form.
    def _breach_line(b: dict) -> str:
        detail = b.get("detail") or f"{b['key']} = {b['value']} (threshold: {b['operator']} {b['threshold']})"
        return f"- {b['label'].upper()}: {detail}"

    breach_lines = "\n".join(_breach_line(b) for b in breaches)
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

        # Breaches with no numeric value (sensor status=error, equipment/
        # connectivity faults) have nothing chemistry-related to explain --
        # without an explicit guard the LLM tends to grab an unrelated number
        # from the "current sensor readings" context block and fabricate a
        # plausible-sounding but wrong water-chemistry cause for them.
        non_chemistry = [b for b in breaches if not isinstance(b["value"], (int, float))]
        guard = (
            f"\nIMPORTANT: {', '.join(b['label'] for b in non_chemistry)} has no water-chemistry "
            f"cause -- it is an equipment/sensor/connectivity problem. Do NOT invent a pH, EC, "
            f"nutrient, or temperature explanation for it; describe it as a hardware/data issue "
            f"and tell the operator to check the physical sensor and its connection.\n"
            if non_chemistry else ""
        )

        prompt = (
            f"=== AUTOMATIC ALERT — Container {container_id} ===\n\n"
            f"Current sensor readings (context only -- do not treat as anomalous unless it also "
            f"appears in 'Triggered threshold alerts' below):\n{sensor_lines}\n\n"
            f"Triggered threshold alerts (the ONLY things actually wrong -- ground sentence 1 in "
            f"these and nothing else):\n{breach_lines}\n"
            f"{ml_lines}"
            f"{guard}\n"
            f"You are an expert spirulina cultivation assistant (AlgaePool protocol, Dominique Delobel, June 2026).\n"
            f"Answer in exactly 3 sentences:\n"
            f"1. Name the specific problem using ONLY the triggered alerts above, with their exact values "
            f"(e.g. 'pH of 7.0 indicates Chlorella contamination or CO2 over-injection', "
            f"'temperature of 42 C signals heater malfunction', "
            f"'DO of 2.5 mg/L means oxygen depletion from bacterial bloom'). "
            f"Do not reference a sensor reading that isn't listed as a triggered alert.\n"
            f"2. State the one action the operator must take RIGHT NOW (be specific — "
            f"e.g. 'add NaHCO3 to raise pH', 'shut off heater and add cold water', "
            f"'increase aeration to emergency level', or for an equipment fault, 'inspect the sensor "
            f"and its wiring/connection').\n"
            f"3. State what happens if untreated within 2 hours (be direct about culture loss, or "
            f"about losing visibility into the culture if it's an equipment fault).\n"
            f"Start with '{emoji} {severity.upper()} — {container_id}:' then give sentence 1, 2, 3.\n"
            f"Do NOT repeat the threshold table. Use the exact values from the triggered alerts only. "
            f"Do NOT state which system detected this — that line is appended automatically."
        )

        text = reasoning_generate(
            question=prompt,
            context=context,
            history=[],
            sensor_state=sensor,
        )
        return text.strip() + source_line

    except Exception:
        # No LLM available -- still state exactly which rule(s)/detector fired
        # and why, using the same detail strings the LLM prompt would've used,
        # instead of a contentless generic message.
        finding_lines = "\n".join(f"- {b['label']}: {b.get('detail', b['value'])}" for b in breaches)
        return (
            f"{emoji} **{severity.upper()} — {container_id}**\n\n"
            f"{finding_lines}\n\n"
            f"Take immediate corrective action."
            f"{source_line}"
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
    from agent.sensors import get_sensor_reading, get_history

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

            # Previous reading + elapsed minutes, so check_thresholds can also
            # run rules.py's rate-of-change checks (e.g. a fast pH crash that
            # hasn't left the absolute-bounds range yet).
            previous, minutes_since_prev = None, None
            history = get_history(container_id, n=2)
            if len(history) > 1:
                previous = history[-2]
                try:
                    now_ts  = datetime.fromisoformat(sensor.get("timestamp") or history[-1]["date"])
                    prev_ts = datetime.fromisoformat(previous["date"])
                    minutes_since_prev = (now_ts - prev_ts).total_seconds() / 60.0
                except (KeyError, ValueError, TypeError):
                    minutes_since_prev = None

            breaches  = check_thresholds(sensor, previous, minutes_since_prev)
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
                    detail      = top_finding.get("detail", label)
                else:
                    param, label, detail = "sensor", "ML anomaly", "undetermined"
                sensor_key = _PARAM_TO_SENSOR_KEY.get(param, param)
                breaches = [{
                    "key":       sensor_key,
                    "value":     sensor.get(sensor_key, "?"),
                    "threshold": None,
                    "operator":  "ml",
                    "severity":  ml_result.get("severity", "warning"),
                    "label":     f"ML anomaly ({label})",
                    "detail":    detail,
                    "emoji":     _SEVERITY_EMOJI.get(ml_result.get("severity", "warning"), "⚠️"),
                }]

            breach_key = ",".join(sorted(b["label"] for b in breaches))
            if _last_alerts.get(user_id) == breach_key:
                continue

            # Mark dedup NOW so next tick doesn't re-fire while LLM is running
            _last_alerts[user_id] = breach_key

            # Timestamp the moment of detection, not whenever the (slow,
            # backgrounded) LLM call happens to finish composing the text.
            detected_at = datetime.now(timezone.utc).isoformat()

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

            detail_sig = _breach_signature(breaches)

            # Offload the slow Groq call — scheduler job returns immediately
            def _llm_and_push(uid, cid, s, br, ml, sev, aff, src, ts, det):
                try:
                    text = generate_alert_text(cid, s, br, ml, source=src)
                    if not text:
                        return
                    try:
                        from data.alerts import alert_store
                        alert_store.save(uid, cid, text, sev, source=src, affected=aff, created_at=ts, detail=det)
                    except Exception as _e:
                        log.error("alert DB save failed: %s", _e)
                    push_alert_fn(uid, text, sev, aff, src, ts, det)
                except Exception as exc:
                    log.error("alert generation failed: %s", exc, exc_info=True)

            threading.Thread(
                target=_llm_and_push,
                args=(user_id, container_id, sensor, breaches, ml_result, severity, affected, source, detected_at, detail_sig),
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
            detected_at = datetime.now(timezone.utc).isoformat()

            combo_detail = (
                f"score={combo['score']:.3f} — inhabituel par rapport "
                f"a l'historique 24h de ce site"
            )
            breach = {
                "key":       "combination_model",
                "value":     round(combo["score"], 3),
                "threshold": None,
                "operator":  "lof",
                "severity":  "warning",
                "label":     "Combination anomaly (24h pattern)",
                "detail":    combo_detail,
                "emoji":     _SEVERITY_EMOJI["warning"],
            }
            ml_result = {
                "anomaly":  True,
                "severity": "warning",
                "rule_findings": [{
                    "parameter": "combination_model",
                    "severity":  2,
                    "label":     "Anomalie combinee (LOF)",
                    "detail":    combo_detail,
                }],
                "seasonal": {},
            }

            detail_sig = f"combination_model:{round(combo['score'])}"

            def _llm_and_push(uid, cid, s, br, ml, ts, det):
                try:
                    text = generate_alert_text(cid, s, [br], ml, source="model-24h")
                    if not text:
                        return
                    try:
                        from data.alerts import alert_store
                        alert_store.save(uid, cid, text, "warning", source="model-24h",
                                          affected=["combination_model"], created_at=ts, detail=det)
                    except Exception as _e:
                        log.error("alert DB save failed: %s", _e)
                    push_alert_fn(uid, text, "warning", ["combination_model"], "model-24h", ts, det)
                except Exception as exc:
                    log.error("combination-model alert generation failed: %s", exc, exc_info=True)

            threading.Thread(
                target=_llm_and_push,
                args=(user_id, container_id, sensor, breach, ml_result, detected_at, detail_sig),
                daemon=True,
                name=f"combo-alert-{container_id[:8]}",
            ).start()

        except Exception as exc:
            log.error("combination-model check failed for %s/%s: %s", container_id, user_id, exc, exc_info=True)
