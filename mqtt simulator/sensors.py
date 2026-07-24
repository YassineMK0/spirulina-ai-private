"""
MQTT alert simulator — exercises every alert source the backend can emit.

Sources (see agent/monitor.py):
  rule        threshold breach caught ONLY by the agent's fast check_thresholds
              path (turbidity/harvest, sensor status=error) -- the M1 anomaly
              detector never sees these fields at all.
  rule+model  a pH/EC/Temperature/DO/Luminosite breach severity>=2. Both
              check_thresholds and the M1 detector (models/anomaly_model)
              read the same rules.py expert table, so any such breach is
              always caught by both at once -- there is no way to trigger
              only one of the two for these five sensors.
  model-24h   the combination model (Local Outlier Factor), scored once a
              day against a container's own rolling 24h history. Needs
              --backfill-24h to seed history, then the debug endpoint to
              score it on demand instead of waiting for the daily cron.
  model       pure ML-only (no rule breach) is NOT reachable via a single
              MQTT reading: the seasonal Temperature/Luminosite z-score check
              caps overall_severity at 1 on its own (see detector.py's
              severity ladder), and _run_ml_prediction only calls that an
              anomaly at overall_severity>=2. Left out of this simulator
              because there is currently no input that produces it.

Scenarios (10): chlorella_invasion, ec_dilution, heater_fault, ph_alkalinity,
ec_high, temp_cold, do_crash, ph_drift_warning (severity=medium, the only
non-critical one), turbidity_harvest, sensor_error.

Not covered, on purpose: rate-of-change rules (needs precisely-timed
back-to-back readings, not a single snapshot) and the Turbidite/OD680 check
(unreachable via the live pipeline regardless -- agent's NTU sensor has no
OD680 calibration).

Usage:
    python "mqtt simulator/sensors.py"
    python "mqtt simulator/sensors.py" --scenario turbidity_harvest
    python "mqtt simulator/sensors.py" --gap 20
    python "mqtt simulator/sensors.py" --backfill-24h --container container-01
    curl -X POST http://localhost:8000/debug/run-combination-check/container-01
"""

import json
import time
import argparse
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# ── Config (matches backend .env) ─────────────────────────────────────────────
BROKER    = "test.mosquitto.org"
PORT      = 1883
CONTAINER = "container-01"  # default; overridable via --container

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

# ── Scenarios covering every reachable alert source ───────────────────────────
SCENARIOS = [
    # rule+model — severity-3 breaches on the shared rules.py table; both
    # check_thresholds and the M1 detector fire on these independently.
    {
        "name":    "chlorella_invasion",
        "label":   "CHLORELLA INVASION  (pH 7.0 -- critical < 8.5 -- source=rule+model)",
        "reading": {**NORMAL, "pH": 7.0},
    },
    {
        "name":    "ec_dilution",
        "label":   "EC DILUTION  (EC 8000 uS/cm = 8 mS/cm -- critical < 10 mS/cm -- source=rule+model)",
        "reading": {**NORMAL, "EC": 8000.0},
    },
    {
        "name":    "heater_fault",
        "label":   "HEATER FAULT  (temp 43 C -- critical > 41 C -- source=rule+model)",
        "reading": {**NORMAL, "temperature": 43.0},
    },
    {
        "name":    "ph_alkalinity",
        "label":   "pH ALKALINITY OVERRUN  (pH 12.0 -- critical > 11.5 -- source=rule+model)",
        "reading": {**NORMAL, "pH": 12.0},
    },
    {
        "name":    "ec_high",
        "label":   "EC OVERCONCENTRATION  (EC 35000 uS/cm = 35 mS/cm -- critical > 30 mS/cm -- source=rule+model)",
        "reading": {**NORMAL, "EC": 35000.0},
    },
    {
        "name":    "temp_cold",
        "label":   "TEMPERATURE COLLAPSE  (temp 15 C -- critical < 20 C -- source=rule+model)",
        "reading": {**NORMAL, "temperature": 15.0},
    },
    {
        "name":    "do_crash",
        "label":   "OXYGEN DEPLETION  (DO 2.0 mg/L, daytime -- critical < 4.0 mg/L -- source=rule+model)",
        "reading": {**NORMAL, "DO": 2.0},
    },
    {
        "name":    "ph_drift_warning",
        "label":   "pH DRIFT  (pH 11.2 -- warning, outside 9.5-11 optimal but under the 11.5 critical line "
                   "-- severity=medium -- source=rule+model)",
        "reading": {**NORMAL, "pH": 11.2},
    },
    # rule only — fields the M1 detector never looks at, so the ML path
    # can't agree even though the reading is otherwise anomalous.
    {
        "name":    "turbidity_harvest",
        "label":   "READY TO HARVEST  (turbidity 820 NTU -- >300 NTU -- source=rule, no OD680 calibration for M1)",
        "reading": {**NORMAL, "turbidity": 820.0},
    },
    {
        "name":    "sensor_error",
        "label":   "SENSOR ERROR  (status=error, readings otherwise normal -- source=rule, M1 doesn't see status)",
        "reading": {**NORMAL, "status": "error"},
    },
]


# ── MQTT setup ────────────────────────────────────────────────────────────────

connected = False

def on_connect(client, userdata, flags, reason_code, properties=None):
    global connected
    rc = reason_code if isinstance(reason_code, int) else reason_code.value
    connected = (rc == 0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def publish(reading: dict, label: str):
    reading["timestamp"] = datetime.now(timezone.utc).isoformat()
    result = client.publish(TOPIC, json.dumps(reading), qos=1)
    result.wait_for_publish(timeout=5)
    status = "OK" if result.is_published() else "FAILED"
    print(f"  [{status}] published  pH={reading['pH']}  DO={reading['DO']}  "
          f"temp={reading['temperature']}  EC={reading['EC']}  turb={reading['turbidity']}  "
          f"status={reading.get('status', 'ok')}")


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
parser.add_argument("--container", default=CONTAINER, help="Container ID")
parser.add_argument("--api",       default="http://localhost:8000", help="Backend URL (used by --backfill-24h)")
parser.add_argument("--backfill-24h", action="store_true",
                    help="Seed 24h of synthetic history directly into the DB (bypassing MQTT) with one "
                         "deliberately anomalous reading, so the combination-model (LOF) 24h check has "
                         "enough data to score on demand. Exits after seeding -- does not connect to MQTT.")
parser.add_argument("--normal", action="store_true",
                    help="With --backfill-24h: seed a clean 24h window with no anomalous day, "
                         "to test that the LOF check correctly stays quiet on an unremarkable day.")
parser.add_argument("--clear-container", action="store_true",
                    help="Delete all stored history for --container first. Only meaningful with "
                         "--backfill-24h -- use on a disposable test container, never on real data.")
args = parser.parse_args()

if args.backfill_24h:
    import sys
    from datetime import timedelta
    sys.path.insert(0, ".")
    from data.store import sensor_store

    if args.clear_container:
        sensor_store.clear(args.container)
        print(f"[backfill] cleared existing history for container={args.container}")

    now = datetime.now(timezone.utc)
    n = 13
    # Span now-23h .. now (not now-24h .. now-2h+something): _build_daily_context
    # filters on ts >= now-24h evaluated AT QUERY TIME, which is always a bit
    # later than backfill time. Seeding the oldest row exactly at the now-24h
    # edge means it silently ages out of the window within seconds, so the
    # "anomaly" that fires ends up being an artifact of the row count
    # dropping from 13->12 rather than the injected outlier itself. A 1h
    # margin on the old end comfortably survives any realistic delay between
    # seeding and querying/scoring.
    for i in range(n):
        ts = now - timedelta(hours=23) + timedelta(hours=(23 / (n - 1)) * i)
        hour = ts.hour
        row = {
            "timestamp":   ts.isoformat(),
            "pH":          9.8, "EC": 20000.0, "DO": 7.5,
            "temperature": 36.0 + 2 * ((hour % 24) / 24.0),
            "luminosity":  12000 + 5000 * ((hour % 24) / 24.0),
            "turbidity":   200.0, "status": "ok",
        }
        if i == 0 and not args.normal:
            # Deliberate outlier day: elevated EC + DO relative to the rest
            # of the rolling window, modeled on a flagged day from the
            # combination model's training benchmark.
            row.update({"pH": 9.65, "EC": 27000.0, "DO": 16.0})
        sensor_store.push(args.container, row)
    print(f"[backfill] seeded {n} readings over the last 24h for container={args.container}")
    if args.normal:
        print(f"[backfill] all {n} readings are normal -- expect the LOF check to find no anomaly")
    else:
        print(f"[backfill] day 0 is anomalous: pH=9.65 EC=27000 DO=16.0 (vs normal pH=9.8 EC=20000 DO=7.5)")
    print(f"[backfill] now run this script normally (any --scenario) so get_sensor_reading() has a cache hit,")
    print(f"[backfill] then trigger the score: curl -X POST {args.api}/debug/run-combination-check/{args.container}")
    raise SystemExit(0)

TOPIC = f"spirulina/sensors/{args.container}"

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
