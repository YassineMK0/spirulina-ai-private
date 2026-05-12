"""
Scenario-based MQTT simulator for SpirulinaAI model testing.

Each anomaly scenario is followed by a short COOLDOWN of normal readings so
the monitor's dedup key resets before the next alert fires.
"""

import json
import random
import time

import paho.mqtt.client as mqtt

BROKER                = "broker.hivemq.com"
PORT                  = 1883
CONTAINER             = "container-01"
TOPIC                 = f"spirulina/sensors/{CONTAINER}"
INTERVAL              = 10  # seconds per reading (5s was too fast for HiveMQ public broker)
READINGS_PER_SCENARIO = 25  # longer window so monitor (15s) fires >= 8 times

# Normal baseline used for cooldown phases between anomalies
NORMAL = {
    "pH":          (9.8,  9.9),
    "EC":          (2000, 2100),
    "DO":          (7.0,  7.2),
    "temperature": (33.0, 33.5),
    "luminosity":  (10500, 10500),
    "turbidity":   (150,  160),
    "status":      "ok",
}

SCENARIOS = [
    # ── 1. Baseline ────────────────────────────────────────────────────────
    {
        "name":    "NORMAL -- expect: no alert, M1 normal, M3 not_ready",
        **NORMAL,
    },
    # ── 2. pH crash ────────────────────────────────────────────────────────
    {
        "name":        "pH CRASH -- expect: M1 anomaly + CRITICAL alert",
        "pH":          (9.5,  6.5),   # crosses < 7.5 monitor threshold
        "EC":          (2000, 2200),
        "DO":          (7.0,  6.8),   # stays healthy
        "temperature": (33.0, 33.0),
        "luminosity":  (10000, 9800),
        "turbidity":   (155,  165),
        "status":      "ok",
    },
    # cooldown
    {"name": "COOLDOWN", **NORMAL},
    # ── 3. DO decline ──────────────────────────────────────────────────────
    {
        "name":        "DO DECLINE -- expect: M1 anomaly + low oxygen warning",
        "pH":          (9.8,  9.8),
        "EC":          (2000, 2050),
        "DO":          (7.0,  2.8),   # crosses < 4.0 threshold early
        "temperature": (33.0, 33.5),
        "luminosity":  (10000, 9500),
        "turbidity":   (155,  170),
        "status":      "ok",
    },
    # cooldown — also brings DO back to normal so overheating has clean start
    {"name": "COOLDOWN", **NORMAL},
    # ── 4. Overheating ─────────────────────────────────────────────────────
    {
        "name":        "OVERHEATING -- expect: M1 anomaly + overheating warning",
        "pH":          (9.8,  9.7),
        "EC":          (2050, 2100),
        "DO":          (7.0,  7.0),   # DO stays healthy (clean start after cooldown)
        "temperature": (33.5, 42.0),  # crosses > 39 threshold by step 7
        "luminosity":  (10000, 9800),
        "turbidity":   (165,  175),
        "status":      "warning",
    },
    # cooldown
    {"name": "COOLDOWN", **NORMAL},
    # ── 5. Harvest ready ───────────────────────────────────────────────────
    {
        "name":        "HARVEST READY -- expect: M3 harvest + harvest alert",
        "pH":          (9.8,  9.9),
        "EC":          (2100, 2300),
        "DO":          (7.0,  7.2),
        "temperature": (33.5, 34.0),
        "luminosity":  (10500, 11500),
        "turbidity":   (200,  360),   # crosses > 300 threshold by step 13
        "status":      "ok",
    },
    # cooldown
    {"name": "COOLDOWN", **NORMAL},
]


def lerp(start, end, t):
    return start + (end - start) * t


def jitter(val, pct=0.012):
    return round(val * (1 + random.uniform(-pct, pct)), 2)


def build_reading(scenario, step, total):
    t = step / max(total - 1, 1)
    return {
        "pH":          jitter(lerp(*scenario["pH"],          t)),
        "EC":          round(jitter(lerp(*scenario["EC"],    t)), 1),
        "DO":          jitter(lerp(*scenario["DO"],          t)),
        "temperature": jitter(lerp(*scenario["temperature"], t)),
        "luminosity":  round(lerp(*scenario["luminosity"],   t), 0),
        "turbidity":   round(jitter(lerp(*scenario["turbidity"], t)), 1),
        "status":      scenario["status"],
    }


client = mqtt.Client()
client.connect(BROKER, PORT, 60)

total_sent = 0
cycle      = 0

print(f"[sim] connected -> {BROKER}  topic={TOPIC}\n")

while True:
    for s_idx, scenario in enumerate(SCENARIOS):
        steps = 8 if scenario["name"] == "COOLDOWN" else READINGS_PER_SCENARIO

        print(f"\n{'='*62}")
        print(f"[sim] {s_idx+1}/{len(SCENARIOS)}  {scenario['name']}")
        print(f"{'='*62}")

        for step in range(steps):
            reading = build_reading(scenario, step, steps)
            client.publish(TOPIC, json.dumps(reading))
            total_sent += 1

            pct = int((step + 1) / steps * 25)
            bar = "#" * pct + "-" * (25 - pct)
            print(f"  [{bar}] {step+1:02d}/{steps}  "
                  f"pH={reading['pH']:.2f}  "
                  f"DO={reading['DO']:.2f}  "
                  f"temp={reading['temperature']:.1f}  "
                  f"turb={reading['turbidity']:.1f}  "
                  f"total={total_sent}")

            time.sleep(INTERVAL)

    cycle += 1
    print(f"\n[sim] --- cycle {cycle} complete, restarting ---\n")
