"""Temporary rotating sensor data generator for alert testing.

Replaces sensors.py during testing — delete this file when done.

Usage:
    In api/main.py or agent/nodes.py, swap the import temporarily:
        from agent.sensors_test import get_sensor_reading, format_sensor_summary

How it works:
    container_id "test-rotating" cycles through 6 states every 5 minutes.
    Each state triggers a different alert. The scheduler fires every 5 min
    so each check produces a new alert type.

    Cycle (repeats every 30 min):
        slot 0  (min  0-4 )  -> healthy       (no alert)
        slot 1  (min  5-9 )  -> ph-crash       (pH too low)
        slot 2  (min 10-14)  -> heat-stress    (temp too high)
        slot 3  (min 15-19)  -> high-ec        (conductivity too high)
        slot 4  (min 20-24)  -> multi-anomaly  (multiple issues)
        slot 5  (min 25-29)  -> harvest-ready  (OD680 high)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone


_ROTATION = [
    # slot 0 — healthy, no alert
    {
        "ph": 9.5, "temperature_c": 33.0, "od680": 0.85,
        "conductivity_ms": 20.0, "dissolved_o2_pct": 95.0,
        "light_lux": 10_000, "co2_ppm": 480,
        "status": "ok",
    },
    # slot 1 — pH crash
    {
        "ph": 7.2, "temperature_c": 32.0, "od680": 0.70,
        "conductivity_ms": 20.5, "dissolved_o2_pct": 78.0,
        "light_lux": 9_500, "co2_ppm": 720,
        "status": "warning",
    },
    # slot 2 — heat stress
    {
        "ph": 9.4, "temperature_c": 41.5, "od680": 0.60,
        "conductivity_ms": 23.0, "dissolved_o2_pct": 65.0,
        "light_lux": 14_000, "co2_ppm": 390,
        "status": "warning",
    },
    # slot 3 — high EC
    {
        "ph": 9.3, "temperature_c": 33.0, "od680": 0.55,
        "conductivity_ms": 38.0, "dissolved_o2_pct": 80.0,
        "light_lux": 9_000, "co2_ppm": 430,
        "status": "warning",
    },
    # slot 4 — multiple anomalies
    {
        "ph": 7.8, "temperature_c": 40.0, "od680": 0.40,
        "conductivity_ms": 28.0, "dissolved_o2_pct": 55.0,
        "light_lux": 13_000, "co2_ppm": 850,
        "status": "error",
    },
    # slot 5 — harvest ready
    {
        "ph": 9.6, "temperature_c": 33.5, "od680": 1.15,
        "conductivity_ms": 21.0, "dissolved_o2_pct": 98.0,
        "light_lux": 11_000, "co2_ppm": 460,
        "status": "ok",
    },
]

# Change interval in seconds — match your scheduler interval
_INTERVAL = 30   # 30 seconds for testing


def get_sensor_reading(container_id: str) -> dict:
    if not container_id:
        return {}

    ts = datetime.now(timezone.utc).isoformat()

    if container_id == "test-rotating":
        slot = int(time.time()) // _INTERVAL % len(_ROTATION)
        data = dict(_ROTATION[slot])
        data["timestamp"] = ts
        print(f"  [sensors_test] rotating slot {slot} -> status={data['status']}")
        return data

    # fall through to normal static containers
    from agent.sensors import get_sensor_reading as _real
    return _real(container_id)


def format_sensor_summary(reading: dict) -> str:
    from agent.sensors import format_sensor_summary as _real
    return _real(reading)
