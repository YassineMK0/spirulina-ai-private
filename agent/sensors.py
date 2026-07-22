"""Sensor reading interface — MQTT subscriber.

Configure via environment variables:
    MQTT_BROKER_URL=mqtt://your-broker.example.com:1883
    MQTT_TOPIC_PREFIX=spirulina/sensors

Readings arrive on topic: {MQTT_TOPIC_PREFIX}/{container_id}

Expected JSON payload per message:
    {
      "pH":          9.5,    // 6.0 – 11.0
      "EC":          2500.0, // µS/cm
      "DO":          6.6,    // mg/L
      "temperature": 33.0,   // °C
      "luminosity":  10000.0,// lux
      "turbidity":   200.0,  // NTU
      "timestamp":   "2026-05-07T10:00:00Z",
      "status":      "ok"    // "ok" | "warning" | "error"
    }

Call start_mqtt_subscriber() once from the FastAPI lifespan.
Call get_sensor_reading(container_id) from nodes.py to get the latest cached reading.
Call get_history(container_id) to get the rolling buffer for ML model inference.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("spirulina.sensors")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MQTT_BROKER_URL   = os.getenv("MQTT_BROKER_URL",   "mqtt://localhost:1883")
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX",  "spirulina/sensors")

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_cache: dict[str, dict] = {}   # latest reading per container (in-memory only)
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# MQTT subscriber
# ---------------------------------------------------------------------------

def start_mqtt_subscriber() -> None:
    """Start background MQTT subscriber thread.

    Connects to MQTT_BROKER_URL and subscribes to {MQTT_TOPIC_PREFIX}/+
    (wildcard — one topic per container).  Call once from FastAPI lifespan.
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        log.error("paho-mqtt not installed — MQTT updates disabled. Install: pip install paho-mqtt")
        return

    host, port = _parse_broker_url(MQTT_BROKER_URL)
    topic      = f"{MQTT_TOPIC_PREFIX}/+"

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        _mqtt_v2 = True
    except AttributeError:
        client = mqtt.Client()
        _mqtt_v2 = False

    def on_connect(client, userdata, flags, reason_code, properties=None):
        rc = reason_code if isinstance(reason_code, int) else reason_code.value
        if rc == 0:
            client.subscribe(topic)
            log.info("MQTT connected  topic=%s", topic)
        else:
            log.error("MQTT connection failed  rc=%s", rc)

    def on_message(client, userdata, msg):
        try:
            container_id = msg.topic.split("/")[-1]
            reading: dict = json.loads(msg.payload.decode())
            reading.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
            reading.setdefault("status", "ok")
            with _lock:
                _cache[container_id] = reading
            from data.store import sensor_store
            sensor_store.push(container_id, reading)
            log.info("received  container=%s  pH=%s  EC=%s  DO=%s",
                     container_id, reading.get("pH"), reading.get("EC"), reading.get("DO"))
        except Exception as exc:
            log.error("MQTT message parse error: %s", exc, exc_info=True)

    if _mqtt_v2:
        def on_disconnect(_client, _userdata, _disconnect_flags, reason_code, _properties):
            rc = reason_code.value if hasattr(reason_code, "value") else reason_code
            if rc != 0:
                log.warning("MQTT disconnect rc=%s — reconnecting", rc)
    else:
        def on_disconnect(_client, _userdata, rc):
            if rc != 0:
                log.warning("MQTT disconnect rc=%s — reconnecting", rc)

    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect

    def _run():
        import time as _time
        delay = 5
        while True:
            try:
                client.connect(host, port, keepalive=60)
                client.loop_forever()
            except Exception as exc:
                log.error("MQTT error: %s — retrying in %ds", exc, delay)
            _time.sleep(delay)
            delay = min(delay * 2, 60)

    threading.Thread(target=_run, daemon=True, name="mqtt-subscriber").start()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_sensor_reading(container_id: str) -> dict[str, Any]:
    """Return the latest reading for a container -- live MQTT cache first,
    falling back to the last persisted DB row if no live reading has
    arrived yet (e.g. no MQTT broker connected in this environment).

    Single source of truth for "what's the current reading" -- used by both
    GET /sensors/{container_id} (the Dashboard) and the chat agent's
    read_sensors node. They must not diverge: previously only the API route
    had the DB fallback inlined, so the Dashboard could show a real reading
    while the chat agent saw an empty {} for the same container and had no
    way to answer "what's my pH right now".

    Returns empty dict if there is truly no reading anywhere.
    Callers should treat empty dict as 'no data' rather than an error.
    """
    if not container_id:
        return {}
    with _lock:
        live = dict(_cache.get(container_id, {}))
    if live:
        return live

    try:
        from data.store import sensor_store
        rows = sensor_store.get_latest(container_id, n=1)
    except Exception:
        return {}
    if not rows:
        return {}

    r = rows[0]
    return {
        "pH": r.get("pH"), "EC": r.get("EC"), "DO": r.get("DO"),
        "temperature": r.get("temperature"), "luminosity": r.get("luminosity"),
        "turbidity": r.get("turbidity"), "timestamp": r.get("date"),
        "status": "ok", "source": "db",
    }


def get_history(container_id: str, n: int = 7) -> list[dict]:
    """Return the last n readings from the DB for ML model inference.

    Fetches latest 6 stored readings + the newest MQTT reading (current cache).
    Returns oldest-first with keys: date, pH, EC, DO, temperature, luminosity, turbidity.

    n=7 gives M3 enough history (min 6) while including today's live reading.
    """
    from data.store import sensor_store

    # Last n-1 from DB (persistent history)
    rows = sensor_store.get_latest(container_id, n=n - 1)

    # Append current live reading from MQTT cache if available
    with _lock:
        live = _cache.get(container_id)
    if live:
        live_row = _to_history_row(live)
        # Avoid duplicating if DB already has this timestamp
        if not rows or rows[-1]["date"] != live_row["date"]:
            rows.append(live_row)

    return rows


def format_sensor_summary(reading: dict) -> str:
    """Format a sensor reading as a compact string for the LLM system prompt."""
    if not reading:
        return ""
    parts = []
    if "pH"          in reading: parts.append(f"pH: {reading['pH']}")
    if "temperature" in reading: parts.append(f"Temp: {reading['temperature']} C")
    if "turbidity"   in reading: parts.append(f"Turbidity: {reading['turbidity']} NTU")
    if "EC"          in reading: parts.append(f"EC: {reading['EC']} uS/cm")
    if "DO"          in reading: parts.append(f"DO: {reading['DO']} mg/L")
    if "luminosity"  in reading: parts.append(f"Luminosity: {reading['luminosity']} lux")
    if "status"      in reading: parts.append(f"Status: {reading['status']}")
    if "timestamp"   in reading: parts.append(f"Recorded: {reading['timestamp']}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_history_row(reading: dict) -> dict:
    """Convert a raw MQTT reading to the unified row format for M1/M2/M3."""
    return {
        "date":        reading.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "pH":          float(reading.get("pH",          9.5)),
        "EC":          float(reading.get("EC",          2000.0)),
        "DO":          float(reading.get("DO",          6.6)),
        "temperature": float(reading.get("temperature", 33.0)),
        "luminosity":  float(reading.get("luminosity",  10000.0)),
        "turbidity":   float(reading.get("turbidity",   200.0)),
    }


def _parse_broker_url(url: str) -> tuple[str, int]:
    """Parse mqtt://host:port or mqtts://host:port into (host, port)."""
    clean = url.replace("mqtts://", "").replace("mqtt://", "")
    if ":" in clean:
        host, port_str = clean.rsplit(":", 1)
        return host, int(port_str)
    return clean, 1883


# ---------------------------------------------------------------------------
# Crash simulator  (python agent/sensors.py ...)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import time as _time

    # Normal baseline — AlgaePool values (Delobel, June 2026). EC in µS/cm.
    _NORMAL = {
        "pH": 9.9, "EC": 20000.0, "DO": 7.5,
        "temperature": 36.0, "luminosity": 12000.0, "turbidity": 200.0,
    }

    # check_thresholds (agent.monitor, the fast 15-min loop) now delegates
    # pH/EC/Temperature/DO/Luminosite directly to models/anomaly_model/rules.py
    # -- the same expert table _run_ml_prediction's M1 detector uses -- so the
    # two used to disagree (different hardcoded numbers) and are now unified:
    # a rule-table finding is caught by both at once, reported as source
    # "rule+model". Two things still only go through one path each because
    # rules.py has no equivalent: turbidity/harvest (source "rule" only --
    # agent's NTU turbidity sensor has no OD680 calibration for rules.py's
    # Turbidite check) and pure seasonal drift (source "model" only -- a
    # Temperature/Luminosite z-score anomaly with no rule threshold crossed).
    _SCENARIOS = {
        "ph_crash":    {"overrides": {"pH": 7.0},
                        "expect": "critical (pH<8.5) -- source=rule+model"},
        "ph_high":     {"overrides": {"pH": 12.0},
                        "expect": "critical (pH>11.5) -- source=rule+model"},
        "temp_hot":    {"overrides": {"temperature": 43.0},
                        "expect": "critical (temp>41) -- source=rule+model"},
        "temp_cold":   {"overrides": {"temperature": 15.0},
                        "expect": "critical (temp<20) -- source=rule+model"},
        "harvest":     {"overrides": {"turbidity": 820.0},
                        "expect": "harvest tier (turbidity>300 NTU) -- source=rule (no OD680 calibration, M1 not evaluated)"},
        "ec_dilution": {"overrides": {"EC": 5000.0},
                        "expect": "critical (5 mS/cm < 10) -- source=rule+model (was M1-only before rule/M1 unification)"},
        "ec_high":     {"overrides": {"EC": 35000.0},
                        "expect": "critical (35 mS/cm > 30) -- source=rule+model"},
        "do_low":      {"overrides": {"DO": 2.0},
                        "expect": "critical (DO<4, daytime) -- source=rule+model"},
        "multi":       {"overrides": {"pH": 7.0, "DO": 2.0, "temperature": 43.0},
                        "expect": "3 simultaneous critical findings (pH, DO, temperature) -- source=rule+model"},
    }

    parser = argparse.ArgumentParser(description="Spirulina MQTT crash simulator")
    parser.add_argument("--container", default="container-01", help="Container ID")
    parser.add_argument("--broker",    default=MQTT_BROKER_URL,  help="MQTT broker URL")
    parser.add_argument("--scenario",  default="all",
                        help="Scenario name or 'all' (default: all)")
    parser.add_argument("--gap",       type=int, default=17,
                        help="Seconds between scenarios (default 17 - one monitor cycle "
                             "*if* the backend was started with MONITOR_RULE_INTERVAL_SECONDS=15 "
                             "for testing; production default is 900s/15min, see api/main.py)")
    parser.add_argument("--sequential", action="store_true",
                        help="Send scenarios one by one with --gap between each. "
                             "Default: send all simultaneously for a burst of alerts.")
    parser.add_argument("--api",       default="http://localhost:8000",
                        help="Backend URL for status check (default: http://localhost:8000)")
    parser.add_argument("--check",     action="store_true",
                        help="Check backend status before sending (shows sessions, queues, cache)")
    parser.add_argument("--backfill-24h", action="store_true",
                        help="Seed 24h of synthetic history directly into the DB (bypassing MQTT) "
                             "with one deliberately anomalous reading, so the combination-model "
                             "(LOF) 24h cron job has enough data to score immediately instead of "
                             "waiting for real history to accumulate. Exits after seeding.")
    args = parser.parse_args()

    # ── Backfill 24h of history for the combination-model (LOF) test ──────────
    if args.backfill_24h:
        from datetime import datetime, timedelta, timezone
        from data.store import sensor_store

        now = datetime.now(timezone.utc)
        n = 13
        for i in range(n):
            ts = now - timedelta(hours=24) + timedelta(hours=2 * i)
            hour = ts.hour
            row = {
                "timestamp":   ts.isoformat(),
                "pH":          9.8, "EC": 20000.0, "DO": 7.5,
                "temperature": 36.0 + 2 * ((hour % 24) / 24.0),
                "luminosity":  12000 + 5000 * ((hour % 24) / 24.0),
                "turbidity":   200.0, "status": "ok",
            }
            if i == 0:
                # Deliberate outlier day, modeled on a flagged day from
                # train.py's real benchmark (see model_comparison_report.md):
                # elevated EC + DO relative to the rest of the window.
                row.update({"pH": 9.65, "EC": 27000.0, "DO": 16.0})
            sensor_store.push(args.container, row)
        print(f"[backfill] seeded {n} readings over the last 24h for container={args.container}")
        print(f"[backfill] day 0 is anomalous: pH=9.65 EC=27000 DO=16.0 (vs normal pH=9.8 EC=20000 DO=7.5)")
        print(f"[backfill] now publish a live MQTT reading (any --scenario) so get_sensor_reading() has a cache hit,")
        print(f"[backfill] then trigger the check: curl -X POST {args.api}/debug/run-combination-check/{args.container}")
        raise SystemExit(0)

    # ── Optional backend status check ─────────────────────────────────────────
    if args.check:
        try:
            import urllib.request as _req, json as _json
            with _req.urlopen(f"{args.api}/status", timeout=3) as r:
                s = _json.loads(r.read())
            print("[backend status]")
            print(f"  event_loop_ready   : {s.get('event_loop_ready')}")
            print(f"  active_sessions    : {s.get('active_sessions')}")
            print(f"  sse_connected_users: {s.get('sse_connected_users')}")
            print(f"  cached_containers  : {s.get('cached_containers')}")
            sessions = s.get("active_sessions", {})
            queues   = s.get("sse_connected_users", [])
            if not sessions:
                print()
                print("  WARNING: no active sessions — open the app and visit the Alerts tab first")
            if not queues:
                print()
                print("  WARNING: no SSE connections — no user will receive alerts")
            print()
        except Exception as e:
            print(f"[backend status] could not reach {args.api}/status: {e}")
            print("  Is the backend running?")
            print()

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("ERROR: paho-mqtt not installed. Run: pip install paho-mqtt")
        raise SystemExit(1)

    host, port = _parse_broker_url(args.broker)

    connected = False

    def _on_connect(client, userdata, flags, reason_code, properties=None):
        global connected
        rc = reason_code if isinstance(reason_code, int) else reason_code.value
        connected = rc == 0
        if connected:
            print(f"[sim] connected to {args.broker}")
        else:
            print(f"[sim] connection failed rc={rc}")

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    client.on_connect = _on_connect
    client.connect(host, port, keepalive=60)
    client.loop_start()

    _time.sleep(1.5)
    if not connected:
        print("[sim] could not connect to broker — is it running?")
        raise SystemExit(1)

    topic = f"{MQTT_TOPIC_PREFIX}/{args.container}"

    def _publish(overrides: dict, label: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = {**_NORMAL, **overrides, "timestamp": now, "status": "ok"}
        result = client.publish(topic, json.dumps(payload), qos=1)
        result.wait_for_publish(timeout=3)
        changes = ", ".join(f"{k}={v}" for k, v in overrides.items()) or "(normal)"
        ok = "OK" if result.is_published() else "FAILED"
        print(f"  -> [{ok}] [{label}]  {changes}")

    def _publish_normal(label: str = "normal") -> None:
        _publish({}, label)

    # Select scenarios to run
    if args.scenario == "all":
        selected = list(_SCENARIOS.items())
    elif args.scenario in _SCENARIOS:
        selected = [(args.scenario, _SCENARIOS[args.scenario])]
    else:
        print(f"Unknown scenario '{args.scenario}'. Available: {', '.join(_SCENARIOS)}")
        raise SystemExit(1)

    print(f"\n[sim] target container : {args.container}")
    print(f"[sim] broker           : {args.broker}")
    print(f"[sim] mode             : {'sequential (gap=' + str(args.gap) + 's)' if args.sequential else 'burst (all at once)'}")
    print(f"[sim] scenarios        : {len(selected)}")
    print()

    if args.sequential:
        for name, scenario in selected:
            print(f"[scenario] {name}")
            print(f"  [expect] {scenario['expect']}")
            _publish(scenario["overrides"], name)
            print(f"  waiting {args.gap}s for monitor cycle...")
            _time.sleep(args.gap)
            _publish_normal("reset")
            _time.sleep(1)
            print()
    else:
        # Burst: send all scenarios back-to-back within 2 seconds.
        # The monitor fires once per cycle — it sees the LAST published reading.
        # For maximum coverage, send the most critical one last.
        ordered = sorted(selected, key=lambda x: x[0])  # alphabetical, "multi" fires last
        print("[sim] sending burst...")
        for name, scenario in ordered:
            print(f"  [expect] {name}: {scenario['expect']}")
            _publish(scenario["overrides"], name)
            _time.sleep(0.3)
        print(f"\n[sim] done — monitor fires in up to {args.gap}s")
        print("[sim] only the LAST published reading (alphabetically 'multi') will be the one")
        print("[sim] actually evaluated by the next monitor cycle in burst mode -- use --sequential")
        print("[sim] to see each scenario evaluated and reset individually.")
        print("[sim] check the Alerts panel in the app")

    client.loop_stop()
    client.disconnect()
    print("\n[sim] disconnected.")
