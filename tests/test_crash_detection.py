"""Crash detection test suite for M1 IsolationForest.

Builds a 30-row steady baseline, injects each crash type in the last 4 rows,
then runs predict_df and reports DETECTED / MISSED per scenario.

NOTE — EC units: the IsolationForest model was trained with EC in mS/cm
(expert spec: optimal 15–22 mS/cm). Raw MQTT payloads send EC in µS/cm.
A unit-conversion step must be applied before feeding MQTT data to the model.
This test uses mS/cm directly to test the model accurately.

Usage:
    python tests/test_crash_detection.py
    python tests/test_crash_detection.py --scenario pH_crash
    python tests/test_crash_detection.py --verbose
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings
warnings.filterwarnings("ignore")

from api.predict_isolationforest import load_artifact, predict_df


# ── Normal baseline values ────────────────────────────────────────────────────

_NORMAL = {
    "pH":          10.0,
    "EC":          18.5,    # mS/cm
    "DO":           7.5,    # mg/L
    "temperature": 36.0,    # C
    "luminosity": 12000.0,  # lux
    "turbidity":   280.0,   # NTU
}

# ── Crash scenarios ───────────────────────────────────────────────────────────
# Each entry: (name, crash_overrides, expected_severity, description)
# crash_overrides: dict of sensor -> value(s) to inject in the last crash_rows rows.
#   scalar  → same value for all crash rows
#   list    → one value per crash row (len must match crash_rows=4)

SCENARIOS: list[dict] = [
    {
        "name":        "pH_crash",
        "description": "pH drops below 8.5 critical bound",
        "crash":       {"pH": 7.80},
        "expected":    "critical",
    },
    {
        "name":        "pH_spike",
        "description": "pH rises above 11.5 critical bound",
        "crash":       {"pH": 12.10},
        "expected":    "critical",
    },
    {
        "name":        "pH_rapid_drop",
        "description": "pH drops 2.5 units in 1 hour (> 2.0 critical delta/h)",
        "crash":       {"pH": [10.0, 10.0, 9.8, 7.3]},  # last step: -2.5 delta
        "expected":    "critical",
    },
    {
        "name":        "EC_low",
        "description": "EC drops below 12.0 mS/cm critical bound",
        "crash":       {"EC": 8.0},
        "expected":    "critical",
    },
    {
        "name":        "EC_high",
        "description": "EC rises above 30.0 mS/cm critical bound",
        "crash":       {"EC": 35.0},
        "expected":    "critical",
    },
    {
        "name":        "EC_rapid_drop",
        "description": "EC drops 6 mS/cm in 1 hour (> 4.0 critical delta/h)",
        "crash":       {"EC": [18.5, 18.5, 18.5, 12.0]},  # last step: -6.5 delta
        "expected":    "critical",
    },
    {
        "name":        "DO_critical",
        "description": "Dissolved oxygen drops below 4.0 mg/L",
        "crash":       {"DO": 2.5},
        "expected":    "critical",
    },
    {
        "name":        "temp_cold",
        "description": "Temperature drops below 20 C critical bound",
        "crash":       {"temperature": 15.0},
        "expected":    "critical",
    },
    {
        "name":        "temp_overheating",
        "description": "Temperature rises above 41 C critical bound",
        "crash":       {"temperature": 43.5},
        "expected":    "critical",
    },
    {
        "name":        "turbidity_crash",
        "description": "Turbidity drops 160 NTU in 1 hour (> 100 crash threshold)",
        "crash":       {"turbidity": [280.0, 280.0, 280.0, 120.0]},  # last step: -160
        "expected":    "critical",
    },
    {
        "name":        "turbidity_depleted",
        "description": "Turbidity below 20 NTU (culture crash / washout)",
        "crash":       {"turbidity": 8.0},
        "expected":    "critical",
    },
    {
        "name":        "temp_warning",
        "description": "Temperature below 25 C warning (growth slowdown)",
        "crash":       {"temperature": 22.5},
        "expected":    "medium",
    },
    {
        "name":        "multi_crash",
        "description": "pH crash AND low DO simultaneously",
        "crash":       {"pH": 7.5, "DO": 2.8},
        "expected":    "critical",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

CRASH_ROWS = 4
HISTORY_ROWS = 30  # enough for full 16-hour rolling windows


def build_baseline(n: int = HISTORY_ROWS, seed: int = 42) -> pd.DataFrame:
    """30 rows of steady realistic sensor data — small noise only."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=pd.Timestamp.utcnow(), periods=n, freq="1h")
    return pd.DataFrame({
        "date":        dates,
        "pH":          _NORMAL["pH"]          + rng.uniform(-0.05, 0.05, n),
        "EC":          _NORMAL["EC"]          + rng.uniform(-0.20, 0.20, n),
        "DO":          _NORMAL["DO"]          + rng.uniform(-0.10, 0.10, n),
        "temperature": _NORMAL["temperature"] + rng.uniform(-0.30, 0.30, n),
        "luminosity":  _NORMAL["luminosity"]  + rng.uniform(-500,  500,  n),
        "turbidity":   _NORMAL["turbidity"]   + rng.uniform(-10,   10,   n),
    })


def inject_crash(baseline: pd.DataFrame, crash: dict) -> pd.DataFrame:
    """Overwrite the last CRASH_ROWS rows with crash values."""
    df = baseline.copy()
    n = len(df)
    for col, val in crash.items():
        if isinstance(val, list):
            if len(val) != CRASH_ROWS:
                raise ValueError(f"Crash list for '{col}' must have {CRASH_ROWS} elements")
            df.loc[n - CRASH_ROWS : n - 1, col] = val
        else:
            df.loc[n - CRASH_ROWS : n - 1, col] = float(val)
    return df


def run_scenario(scenario: dict, artifact: dict, verbose: bool = False) -> dict:
    """Run a single scenario and return the result dict."""
    baseline = build_baseline()
    df = inject_crash(baseline, scenario["crash"])
    result = predict_df(df, artifact)

    # Check all crash rows (last CRASH_ROWS)
    crash_results = result.tail(CRASH_ROWS)
    any_detected = crash_results["is_anomaly"].any()
    max_score    = float(crash_results["anomaly_score"].max())
    worst_sev    = crash_results["severity"].map({"critical": 2, "medium": 1, "low": 0}).max()
    worst_label  = ["low", "medium", "critical"][worst_sev]

    status = "DETECTED" if any_detected else "MISSED"
    passed = any_detected  # any crash row flagged = pass

    if verbose:
        print(f"\n  {'-'*60}")
        print(f"  Scenario : {scenario['name']}")
        print(f"  Desc     : {scenario['description']}")
        print(f"  Expected : {scenario['expected']}  |  Got: {worst_label}")
        print(f"  Max score: {max_score:.4f}  |  Detected: {any_detected}")
        print()
        cols = ["date", "pH", "EC", "DO", "temperature", "turbidity",
                "anomaly_score", "is_anomaly", "severity"]
        avail = [c for c in cols if c in result.columns]
        print(result.tail(CRASH_ROWS)[avail].to_string(index=False))

    return {
        "name":      scenario["name"],
        "desc":      scenario["description"],
        "expected":  scenario["expected"],
        "got":       worst_label,
        "score":     max_score,
        "detected":  any_detected,
        "passed":    passed,
        "status":    status,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="M1 IsolationForest crash detection tests")
    parser.add_argument("--scenario", default="all", help="Scenario name or 'all'")
    parser.add_argument("--verbose",  action="store_true", help="Print per-row details")
    args = parser.parse_args()

    print("Loading M1 IsolationForest artifact...")
    artifact = load_artifact()
    print(f"  threshold={artifact['threshold']:.4f}  "
          f"score_range=[{artifact['score_min']:.4f}, {artifact['score_max']:.4f}]\n")

    # Select scenarios
    if args.scenario == "all":
        scenarios = SCENARIOS
    else:
        scenarios = [s for s in SCENARIOS if s["name"] == args.scenario]
        if not scenarios:
            print(f"ERROR: unknown scenario '{args.scenario}'")
            print("Available:", ", ".join(s["name"] for s in SCENARIOS))
            sys.exit(1)

    results = []
    for sc in scenarios:
        r = run_scenario(sc, artifact, verbose=args.verbose)
        results.append(r)
        icon = "PASS" if r["passed"] else "FAIL"
        print(f"[{icon}] {r['name']:<22}  score={r['score']:.4f}  "
              f"severity={r['got']:<8}  {r['desc']}")

    # Summary
    passed = sum(1 for r in results if r["passed"])
    total  = len(results)
    print()
    print("=" * 65)
    print(f"RESULT: {passed}/{total} scenarios DETECTED")
    if passed < total:
        print("\nMISSED:")
        for r in results:
            if not r["passed"]:
                print(f"  - {r['name']}: {r['desc']}")
    print("=" * 65)

    # Verify EC auto-conversion (MQTT sends uS/cm, model expects mS/cm)
    print()
    print("EC unit auto-conversion check (MQTT uS/cm -> model mS/cm)...")
    baseline_us = build_baseline()
    baseline_us["EC"] = baseline_us["EC"] * 1000.0   # simulate MQTT uS/cm values
    res_us = predict_df(baseline_us, artifact)
    ec_ok = res_us["is_anomaly"].mean() == 0.0
    print(f"  Normal data in uS/cm: anomaly_rate={res_us['is_anomaly'].mean():.0%}  "
          f"{'[PASS]' if ec_ok else '[FAIL] still flagging normal data'}")


if __name__ == "__main__":
    main()
