"""
MQTT crash simulator — tests the 4 confirmed M1 IsolationForest detections.

M1 confirmed detections (AlgaePool / Delobel, June 2026):
  1. chlorella_invasion  — pH drops below 8.5  (Chlorella or CO2 over-injection)
  2. ec_dilution         — EC drops below 12 mS/cm  (tap left open / dilution)
  3. heater_fault        — temperature exceeds 41 C  (heater malfunction)
  4. ph_alkalinity       — pH rises above 11.5  (CO2 outgassing / N over-fertilization)

Usage:
    python "mqtt simulator/sensors.py"
    python "mqtt simulator/sensors.py" --scenario chlorella_invasion
    python "mqtt simulator/sensors.py" --gap 20
"""

import json
import time
import argparse
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# ── Config (matches backend .env) ─────────────────────────────────────────────
BROKER    = "test.mosquitto.org"
PORT      = 1883
CONTAINER = "container-01"
TOPIC     = f"spirulina/sensors/{CONTAINER}"

# ── Normal baseline — AlgaePool healthy culture (Delobel, June 2026) ─────────
# EC in µS/cm (raw sensor). predict_df auto-converts to mS/cm for the model.
NORMAL = {
    "pH":          9.9,       # optimal 9.5-11.0
    "EC":          20000.0,   # 20 mS/cm = 20000 µS/cm (optimal 15-22 mS/cm)
    "DO":          7.5,       # optimal 6-9 mg/L
    "temperature": 36.0,      # optimal 34-39 C
    "luminosity":  12000.0,
    "turbidity":   200.0,     # optimal 114-456 NTU
    "status":      "ok",
}

# ── The 4 confirmed M1 detections ─────────────────────────────────────────────
SCENARIOS = [
    {
        "name":    "chlorella_invasion",
        "label":   "CHLORELLA INVASION  (pH 7.0 -- critical < 8.5 -- cause: pH)",
        "reading": {**NORMAL, "pH": 7.0},
    },
    {
        "name":    "ec_dilution",
        "label":   "EC DILUTION  (EC 8000 uS/cm = 8 mS/cm -- critical < 12 mS/cm -- cause: EC)",
        "reading": {**NORMAL, "EC": 8000.0},
    },
    {
        "name":    "heater_fault",
        "label":   "HEATER FAULT  (temp 43 C -- critical > 41 C -- cause: temperature)",
        "reading": {**NORMAL, "temperature": 43.0},
    },
    {
        "name":    "ph_alkalinity",
        "label":   "pH ALKALINITY OVERRUN  (pH 12.0 -- critical > 11.5 -- cause: pH)",
        "reading": {**NORMAL, "pH": 12.0},
    },
]


# ── MQTT setup ────────────────────────────────────────────────────────────────

connected = False

def on_connect(client, userdata, flags, reason_code, properties=None):
    global connected
    rc = reason_code if isinstance(reason_code, int) else reason_code.value
    connected = (rc == 0)

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
except AttributeError:
    client = mqtt.Client()

client.on_connect = on_connect
print(f"[sim] connecting to {BROKER}:{PORT} ...")
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()
time.sleep(2)

if not connected:
    print("[sim] ERROR: could not connect to broker")
    raise SystemExit(1)

print(f"[sim] connected  topic={TOPIC}\n")


# ── Helpers ───────────────────────────────────────────────────────────────────

def publish(reading: dict, label: str):
    reading["timestamp"] = datetime.now(timezone.utc).isoformat()
    result = client.publish(TOPIC, json.dumps(reading), qos=1)
    result.wait_for_publish(timeout=5)
    status = "OK" if result.is_published() else "FAILED"
    print(f"  [{status}] published  pH={reading['pH']}  DO={reading['DO']}  "
          f"temp={reading['temperature']}  EC={reading['EC']}  turb={reading['turbidity']}")


def reset_to_normal():
    publish(dict(NORMAL), "reset")


def countdown(seconds: int, msg: str):
    for i in range(seconds, 0, -1):
        print(f"\r  {msg}  {i}s ...", end="", flush=True)
        time.sleep(1)
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--scenario", default="all", help="Scenario name or 'all'")
parser.add_argument("--gap",      type=int, default=25,
                    help="Seconds to wait after each crash (default 25 = monitor cycle 15s + LLM ~8s)")
args = parser.parse_args()

if args.scenario == "all":
    selected = SCENARIOS
else:
    selected = [s for s in SCENARIOS if s["name"] == args.scenario]
    if not selected:
        print(f"Unknown scenario '{args.scenario}'")
        print("Available:", ", ".join(s["name"] for s in SCENARIOS))
        raise SystemExit(1)

print(f"Running {len(selected)} scenario(s)  gap={args.gap}s\n")

for i, sc in enumerate(selected, 1):
    print(f"[{i}/{len(selected)}] {sc['label']}")
    publish(sc["reading"], sc["name"])
    countdown(args.gap, "waiting for monitor")
    reset_to_normal()
    time.sleep(3)
    print()

print("[sim] all scenarios done")
client.loop_stop()
client.disconnect()
