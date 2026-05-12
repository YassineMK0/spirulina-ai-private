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

    def on_connect(client, userdata, flags, reason_code, properties=None):
        # paho-mqtt v2: reason_code is a ReasonCode object; 0 / "Success" = connected
        rc = reason_code if isinstance(reason_code, int) else reason_code.value
        if rc == 0:
            client.subscribe(topic)
            print(f"[sensors] MQTT connected to {MQTT_BROKER_URL}  topic={topic}")
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
            # Persist to SQLite store (S3 simulation)
            from data.store import sensor_store
            sensor_store.push(container_id, reading)
        except Exception as exc:
            print(f"[sensors] MQTT message parse error: {exc}")

    def on_disconnect(client, userdata, rc):
        if rc != 0:
            print(f"[sensors] MQTT unexpected disconnect rc={rc} — reconnecting")

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()   # paho-mqtt < 2.0 fallback
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
