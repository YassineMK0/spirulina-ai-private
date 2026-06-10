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
import os
import threading
from datetime import datetime, timezone
from typing import Any

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
        print("[sensors] paho-mqtt not installed — MQTT updates disabled. "
              "Install: pip install paho-mqtt")
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
            print(f"[sensors] MQTT connected  topic={topic}")
        else:
            print(f"[sensors] MQTT connection failed  rc={rc}")

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
            print(f"[sensors] received  container={container_id}  pH={reading.get('pH')}  EC={reading.get('EC')}  DO={reading.get('DO')}")
        except Exception as exc:
            print(f"[sensors] MQTT message parse error: {exc}")

    if _mqtt_v2:
        def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
            rc = reason_code.value if hasattr(reason_code, "value") else reason_code
            if rc != 0:
                print(f"[sensors] MQTT disconnect rc={rc} — reconnecting")
    else:
        def on_disconnect(client, userdata, rc):
            if rc != 0:
                print(f"[sensors] MQTT disconnect rc={rc} — reconnecting")

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
                # loop_forever returns only on explicit disconnect
            except Exception as exc:
                print(f"[sensors] MQTT error: {exc} — retrying in {delay}s")
            _time.sleep(delay)
            delay = min(delay * 2, 60)   # exponential back-off, cap at 60s

    threading.Thread(target=_run, daemon=True, name="mqtt-subscriber").start()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_sensor_reading(container_id: str) -> dict[str, Any]:
    """Return latest cached MQTT reading for a container.

    Returns empty dict if no reading has been received yet.
    Callers should treat empty dict as 'no data' rather than an error.
    """
    if not container_id:
        return {}
    with _lock:
        return dict(_cache.get(container_id, {}))


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

    # Crash values aligned to model critical bounds (EC in µS/cm; model sees mS/cm).
    # Model crits: pH < 8.5/>11.5, EC < 12 mS/cm/>30 mS/cm, temp < 20/>41, DO < 4.0, turb > 760 NTU.
    _SCENARIOS = {
        "ph_crash":    {"pH": 7.0},                                       # < 8.5  crit
        "ph_high":     {"pH": 12.0},                                      # > 11.5 crit
        "temp_hot":    {"temperature": 43.0},                             # > 41   crit
        "temp_cold":   {"temperature": 15.0},                             # < 20   crit
        "harvest":     {"turbidity": 820.0},                              # > 760 NTU crit
        "ec_dilution": {"EC": 5000.0},                                    # 5 mS/cm < 12 crit
        "ec_high":     {"EC": 35000.0},                                   # 35 mS/cm > 30 crit
        "do_low":      {"DO": 2.0},                                       # < 4.0  crit
        "multi":       {"pH": 7.0, "DO": 2.0, "temperature": 43.0},      # 3 at once
    }

    parser = argparse.ArgumentParser(description="Spirulina MQTT crash simulator")
    parser.add_argument("--container", default="container-01", help="Container ID")
    parser.add_argument("--broker",    default=MQTT_BROKER_URL,  help="MQTT broker URL")
    parser.add_argument("--scenario",  default="all",
                        help="Scenario name or 'all' (default: all)")
    parser.add_argument("--gap",       type=int, default=17,
                        help="Seconds between scenarios (default 17 — one monitor cycle)")
    parser.add_argument("--sequential", action="store_true",
                        help="Send scenarios one by one with --gap between each. "
                             "Default: send all simultaneously for a burst of alerts.")
    parser.add_argument("--api",       default="http://localhost:8000",
                        help="Backend URL for status check (default: http://localhost:8000)")
    parser.add_argument("--check",     action="store_true",
                        help="Check backend status before sending (shows sessions, queues, cache)")
    args = parser.parse_args()

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
        for name, overrides in selected:
            print(f"[scenario] {name}")
            _publish(overrides, name)
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
        for name, overrides in ordered:
            _publish(overrides, name)
            _time.sleep(0.3)
        print(f"\n[sim] done — monitor fires in up to {args.gap}s")
        print("[sim] check the Alerts panel in the app")

    client.loop_stop()
    client.disconnect()
    print("\n[sim] disconnected.")
