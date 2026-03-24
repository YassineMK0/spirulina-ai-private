"""Sensor reading interface.

Mock implementation for development.  To connect real IoT data:
    - Replace the body of get_sensor_reading() with your API call
    - Keep the return schema identical so the rest of the pipeline is unaffected

Expected schema (all keys optional — missing keys are treated as unavailable):
    ph               float   6.0 – 11.0
    temperature_c    float   Celsius
    od680            float   Optical density at 680 nm (biomass proxy)
    conductivity_ms  float   mS/cm (medium salinity)
    dissolved_o2_pct float   % saturation
    light_lux        float   lux at culture surface
    co2_ppm          float   CO2 concentration in headspace
    timestamp        str     ISO-8601 UTC
    status           str     "ok" | "warning" | "error"
"""

from __future__ import annotations

import random
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Public interface — swap this body when the real API is ready
# ---------------------------------------------------------------------------

def get_sensor_reading(container_id: str) -> dict:
    """Return the latest sensor readings for *container_id*.

    Currently returns realistic mock values for a healthy spirulina culture.
    Replace with a real HTTP/MQTT call when the IoT platform is available:

        resp = requests.get(f"{SENSOR_API_URL}/containers/{container_id}/latest",
                            headers={"Authorization": f"Bearer {API_TOKEN}"})
        return resp.json()
    """
    if not container_id:
        return {}

    ts = datetime.now(timezone.utc).isoformat()

    # ── Named test containers with static, scenario-specific values ──────────
    _FAKE_CONTAINERS: dict[str, dict] = {
        # Healthy culture — all values in optimal range
        "test-healthy": {
            "ph": 9.5, "temperature_c": 33.0, "od680": 0.85,
            "conductivity_ms": 20.0, "dissolved_o2_pct": 95.0,
            "light_lux": 10_000, "co2_ppm": 480,
            "timestamp": ts, "status": "ok",
        },
        # Harvest-ready — OD680 at upper optimal, stable for days
        "test-harvest-ready": {
            "ph": 9.6, "temperature_c": 33.5, "od680": 1.15,
            "conductivity_ms": 21.0, "dissolved_o2_pct": 98.0,
            "light_lux": 11_000, "co2_ppm": 460,
            "timestamp": ts, "status": "ok",
        },
        # pH crash — dangerously low, needs bicarbonate addition
        "test-ph-crash": {
            "ph": 7.2, "temperature_c": 32.0, "od680": 0.70,
            "conductivity_ms": 20.5, "dissolved_o2_pct": 78.0,
            "light_lux": 9_500, "co2_ppm": 720,
            "timestamp": ts, "status": "warning",
        },
        # Heat stress — temperature too high
        "test-heat-stress": {
            "ph": 9.4, "temperature_c": 41.5, "od680": 0.60,
            "conductivity_ms": 23.0, "dissolved_o2_pct": 65.0,
            "light_lux": 14_000, "co2_ppm": 390,
            "timestamp": ts, "status": "warning",
        },
        # Salt build-up — EC too high
        "test-high-ec": {
            "ph": 9.3, "temperature_c": 33.0, "od680": 0.55,
            "conductivity_ms": 38.0, "dissolved_o2_pct": 80.0,
            "light_lux": 9_000, "co2_ppm": 430,
            "timestamp": ts, "status": "warning",
        },
        # Multiple anomalies — pH low + heat + low O2
        "test-multi-anomaly": {
            "ph": 7.8, "temperature_c": 40.0, "od680": 0.40,
            "conductivity_ms": 28.0, "dissolved_o2_pct": 55.0,
            "light_lux": 13_000, "co2_ppm": 850,
            "timestamp": ts, "status": "error",
        },
    }

    if container_id in _FAKE_CONTAINERS:
        return _FAKE_CONTAINERS[container_id]

    # Fallback: deterministic random values for any other container_id
    rng = random.Random(container_id)
    return {
        "ph":               round(rng.uniform(9.0, 9.8), 2),
        "temperature_c":    round(rng.uniform(30.0, 34.0), 1),
        "od680":            round(rng.uniform(0.6, 1.2), 3),
        "conductivity_ms":  round(rng.uniform(18.0, 22.0), 1),
        "dissolved_o2_pct": round(rng.uniform(85.0, 105.0), 1),
        "light_lux":        round(rng.uniform(8_000, 12_000), 0),
        "co2_ppm":          round(rng.uniform(380, 600), 0),
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "status":           "ok",
    }


def format_sensor_summary(reading: dict) -> str:
    """Format sensor readings into a compact human-readable string for the LLM."""
    if not reading:
        return ""
    lines = []
    if "ph"               in reading: lines.append(f"pH: {reading['ph']}")
    if "temperature_c"    in reading: lines.append(f"Temperature: {reading['temperature_c']} C")
    if "od680"            in reading: lines.append(f"OD680 (biomass): {reading['od680']}")
    if "conductivity_ms"  in reading: lines.append(f"Conductivity: {reading['conductivity_ms']} mS/cm")
    if "dissolved_o2_pct" in reading: lines.append(f"Dissolved O2: {reading['dissolved_o2_pct']}%")
    if "light_lux"        in reading: lines.append(f"Light: {reading['light_lux']} lux")
    if "co2_ppm"          in reading: lines.append(f"CO2: {reading['co2_ppm']} ppm")
    if "timestamp"        in reading: lines.append(f"Recorded: {reading['timestamp']}")
    return "\n".join(lines)
