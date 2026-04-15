"""
Generate ~15,000 timesteps of synthetic spirulina cultivation sensor data.

Outputs ONLY raw sensor readings — no feature engineering.
Feature engineering lives in data/features.py and is shared with the API.

Run from project root:
    python data/generate_data.py

Output columns:
    timestamp, ph, ec, do_mg, temp, turbidity, lux, is_anomaly, anomaly_type

Files written (next to this script):
    spirulina_train.csv   – 80 % temporal split (no shuffle)
    spirulina_test.csv    – 20 % temporal split

Anomaly types:
    ph_spike      – pH > 10.8  (CO2 deficiency),   DO also rises
    ph_drop       – pH < 8.0   (acid contamination), turbidity rises
    ec_collapse   – EC < 1800  (nutrient pump failure), progressive
    temp_runaway  – Temp > 38 °C (cooling failure),  DO drops
    do_hypoxia    – DO < 4 mg/L (aerator failure),   pH drops
    contamination – turbidity spike + pH chaos + EC drain
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
N_STEPS: int     = 15_000
STEP_MIN: int    = 5          # minutes between readings
START_DATE: str  = "2024-01-01"
RANDOM_SEED: int = 42
TRAIN_FRAC: float = 0.80

DATA_DIR: Path = Path(__file__).parent

# Anomaly spec — n_test controls how many events land in the test split
# so both train and test have ~7-8 % anomaly rate
_ANOMALY_SPEC: list[dict] = [
    {"type": "ph_spike",      "n_events": 4, "n_test": 1, "duration": (25,  45),  "severity": (0.70, 1.0)},
    {"type": "ph_drop",       "n_events": 4, "n_test": 1, "duration": (35,  58),  "severity": (0.70, 1.0)},
    {"type": "ec_collapse",   "n_events": 2, "n_test": 1, "duration": (95,  145), "severity": (0.75, 1.0)},
    {"type": "temp_runaway",  "n_events": 4, "n_test": 1, "duration": (42,  70),  "severity": (0.70, 1.0)},
    {"type": "do_hypoxia",    "n_events": 4, "n_test": 0, "duration": (28,  52),  "severity": (0.75, 1.0)},
    {"type": "contamination", "n_events": 3, "n_test": 0, "duration": (42,  68),  "severity": (0.70, 1.0)},
]


# ---------------------------------------------------------------------------
# Ramp helpers
# ---------------------------------------------------------------------------

def _bell(n: int) -> np.ndarray:
    """Smooth bell ramp: 0 -> 1 -> 0 over n steps."""
    return np.sin(np.linspace(0, np.pi, n))


def _ramp(n: int) -> np.ndarray:
    """Linear ramp: 0 -> 1 over n steps."""
    return np.linspace(0.0, 1.0, n)


# ---------------------------------------------------------------------------
# Normal baseline
# ---------------------------------------------------------------------------

def _simulate_ec(n: int, rng: np.random.Generator) -> np.ndarray:
    """
    EC with nutrient consumption drift (-0.05/step) and smooth auto-dosing every ~48 h.

    Dosing is spread over 18 steps (90 min) using a sine ramp so that the
    ec_delta_30min and ec_zscore features stay within the normal range.
    An instantaneous +300 jump creates ec_delta_30min z-score ~5 which the
    Isolation Forest correctly flags as anomalous — smoothing prevents this.
    """
    DOSE_RAMP = 18          # steps over which one dosing event is spread
    pending   = np.zeros(n) # pre-scheduled smooth dose increments

    # Pre-compute all dosing events
    for t in range(576, n, 576):
        amount = rng.uniform(200, 400)
        ramp   = np.sin(np.linspace(0, np.pi / 2, DOSE_RAMP)) ** 2  # smooth S-curve
        ramp  /= ramp.sum()                                           # normalise to 1
        end    = min(t + DOSE_RAMP, n)
        pending[t:end] += amount * ramp[:end - t]

    ec = np.empty(n)
    ec[0] = 2800.0
    for i in range(1, n):
        ec[i] = ec[i - 1] - 0.05 + pending[i] + rng.normal(0.0, 2.5)
        ec[i] = float(np.clip(ec[i], 1500, 4200))
    return ec


def _simulate_turbidity(n: int, rng: np.random.Generator) -> np.ndarray:
    """
    Turbidity driven by logistic biomass growth with harvests every ~10 days.
    Range: 50–800 NTU.
    """
    harvest_steps = 2880          # 10 days at 5-min intervals
    biomass = np.zeros(n)
    i = 0
    while i < n:
        end = min(i + harvest_steps, n)
        t = np.linspace(0.0, 1.0, end - i)
        biomass[i:end] = 0.05 + 0.87 / (1.0 + np.exp(-6.0 * (t - 0.40)))
        i = end

    return np.clip(100.0 + 400.0 * biomass + rng.normal(0, 15, n), 50.0, 800.0)


def _generate_normal_baseline(
    n: int, start_date: str, rng: np.random.Generator
) -> pd.DataFrame:
    """
    Realistic normal sensor readings with circadian and biological cycles.

    Inter-sensor correlations modelled:
        lux  -> temp  (solar heating)
        lux  -> do_mg (photosynthesis)
        lux  -> ph    (CO2 consumption raises pH during daylight)
    """
    ts    = pd.date_range(start_date, periods=n, freq=f"{STEP_MIN}min")
    hours = (ts.hour + ts.minute / 60.0).to_numpy()

    # Lux: bell curve 07:00-19:00, peak ~35 000 lux + cloud variation
    day   = (hours >= 7.0) & (hours <= 19.0)
    lux   = np.where(day, 35_000 * np.sin(np.pi * (hours - 7) / 12) ** 2, 0.0)
    lux  *= np.clip(rng.normal(1.0, 0.12, n), 0.2, 1.0)
    lux  += rng.uniform(0, 300, n)
    lux   = np.clip(lux, 0.0, 60_000.0)
    lx    = lux / 35_000.0                 # normalised [0, ~1]

    temp     = np.clip(32.0 + 3.5 * lx + rng.normal(0, 0.25, n), 22.0, 38.0)
    do_mg    = np.clip( 8.0 + 2.5 * lx + rng.normal(0, 0.25, n),  5.0, 14.0)
    ph_cycle = 0.45 * np.sin(2 * np.pi * (hours - 6.0) / 18.0)
    ph       = np.clip(9.5 + ph_cycle + rng.normal(0, 0.07, n), 8.2, 10.8)
    ec       = _simulate_ec(n, rng)
    turb     = _simulate_turbidity(n, rng)

    return pd.DataFrame({
        "timestamp": ts,
        "ph":        ph,
        "ec":        ec,
        "do_mg":     do_mg,
        "temp":      temp,
        "turbidity": turb,
        "lux":       lux,
    })


# ---------------------------------------------------------------------------
# Anomaly placement
# ---------------------------------------------------------------------------

def _place_events(
    n: int,
    spec: list[dict],
    rng: np.random.Generator,
    min_gap: int = 200,
) -> list[tuple[int, int, str, float]]:
    """
    Place events at non-overlapping positions.

    n_test events per type are forced into the test split [split_idx, n]
    so both splits have a similar anomaly rate.

    Returns list of (start, duration, anomaly_type, severity).
    """
    events: list[tuple[int, int, str, float]] = []
    occupied = np.zeros(n, dtype=bool)
    split_idx = int(n * TRAIN_FRAC)

    bounds = {
        "train": (200,            split_idx - 100),
        "test":  (split_idx + 50, n - 200),
    }

    for item in spec:
        atype  = item["type"]
        lo, hi = item["duration"]
        ls, hs = item["severity"]
        n_test  = int(item.get("n_test", 0))
        regions = ["test"] * n_test + ["train"] * (item["n_events"] - n_test)
        rng.shuffle(regions)

        for region in regions:
            b_lo, b_hi = bounds[region]
            if b_lo >= b_hi - 1:
                b_lo, b_hi = 200, n - 200

            for _ in range(200):
                dur   = int(rng.integers(lo, hi + 1))
                avail = b_hi - dur
                if avail <= b_lo:
                    continue
                start = int(rng.integers(b_lo, avail))
                ps, pe = max(0, start - min_gap), min(n, start + dur + min_gap)
                if not occupied[ps:pe].any():
                    occupied[start: start + dur] = True
                    events.append((start, dur, atype, float(rng.uniform(ls, hs))))
                    break

    return events


# ---------------------------------------------------------------------------
# Anomaly injection
# ---------------------------------------------------------------------------

def _inject_anomalies(
    df: pd.DataFrame,
    events: list[tuple[int, int, str, float]],
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Overwrite sensor values at each anomaly window and set label columns.

    Works directly on numpy arrays to avoid pandas .loc inclusive-slice issues.
    """
    df = df.copy()
    ph  = df["ph"].to_numpy(float)
    ec  = df["ec"].to_numpy(float)
    do_ = df["do_mg"].to_numpy(float)
    tmp = df["temp"].to_numpy(float)
    trb = df["turbidity"].to_numpy(float)

    is_anom  = np.zeros(len(df), dtype=int)
    anom_typ = np.full(len(df), "normal", dtype=object)

    for start, dur, atype, sev in events:
        s, e  = start, start + dur
        bell  = _bell(dur)
        ramp  = _ramp(dur)
        chaos = rng.normal(0.0, 0.2, dur)

        if atype == "ph_spike":
            ph[s:e]  = np.clip(ph[s:e]  + sev * 3.5 * bell,   9.0, 14.0)
            do_[s:e] = np.clip(do_[s:e] + sev * 2.0 * bell,   0.0, 18.0)

        elif atype == "ph_drop":
            ph[s:e]  = np.clip(ph[s:e]  - sev * 4.5 * bell,   3.0, 10.0)
            trb[s:e] = np.clip(trb[s:e] + sev * 450 * bell,   0.0, 2000.0)

        elif atype == "ec_collapse":
            ec[s:e]  = np.clip(ec[s:e]  - sev * 2200 * ramp, 300.0, 4200.0)

        elif atype == "temp_runaway":
            tmp[s:e] = np.clip(tmp[s:e] + sev * 16.0 * ramp,  20.0, 56.0)
            do_[s:e] = np.clip(do_[s:e] - sev *  7.0 * ramp,   0.0, 14.0)

        elif atype == "do_hypoxia":
            do_[s:e] = np.clip(do_[s:e] - sev * 10.0 * bell,   0.0, 14.0)
            ph[s:e]  = np.clip(ph[s:e]  - sev *  1.5 * bell,   6.5, 10.0)

        elif atype == "contamination":
            trb[s:e] = np.clip(
                trb[s:e] + sev * 900 * bell + rng.uniform(0, 120, dur),
                0.0, 2000.0,
            )
            ph[s:e]  = np.clip(ph[s:e]  + sev * 2.0 * chaos,   6.5, 13.0)
            ec[s:e]  = np.clip(ec[s:e]  - sev * 600 * bell,   300.0, 4200.0)

        is_anom[s:e]  = 1
        anom_typ[s:e] = atype

    df["ph"]           = ph
    df["ec"]           = ec
    df["do_mg"]        = do_
    df["temp"]         = tmp
    df["turbidity"]    = trb
    df["is_anomaly"]   = is_anom
    df["anomaly_type"] = anom_typ
    return df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Generate raw sensor data and write train/test CSVs — no feature engineering."""
    rng = np.random.default_rng(RANDOM_SEED)

    print("[generate] Building normal baseline...")
    df = _generate_normal_baseline(N_STEPS, START_DATE, rng)

    print("[generate] Injecting anomaly events...")
    events = _place_events(N_STEPS, _ANOMALY_SPEC, rng)
    df     = _inject_anomalies(df, events, rng)

    ratio = df["is_anomaly"].mean()
    print(f"[generate] Anomaly ratio: {ratio:.2%}  ({df['is_anomaly'].sum()} / {N_STEPS} steps)")
    for t, c in df[df["is_anomaly"] == 1]["anomaly_type"].value_counts().items():
        print(f"           {t:<16} {c:>5} steps")

    # Temporal 80/20 split — NO shuffle
    split = int(N_STEPS * TRAIN_FRAC)
    df_train = df.iloc[:split].reset_index(drop=True)
    df_test  = df.iloc[split:].reset_index(drop=True)

    print(
        f"[generate] Train: {len(df_train):,} rows  "
        f"({df_train['is_anomaly'].mean():.2%} anomaly)\n"
        f"           Test:  {len(df_test):,} rows  "
        f"({df_test['is_anomaly'].mean():.2%} anomaly)"
    )

    # Output columns: only raw sensor data + labels
    # Feature engineering is done separately via data/features.py
    cols = ["timestamp", "ph", "ec", "do_mg", "temp", "turbidity", "lux",
            "is_anomaly", "anomaly_type"]

    df_train[cols].to_csv(DATA_DIR / "spirulina_train.csv", index=False)
    df_test[cols].to_csv( DATA_DIR / "spirulina_test.csv",  index=False)

    print(f"[generate] -> {DATA_DIR / 'spirulina_train.csv'}")
    print(f"[generate] -> {DATA_DIR / 'spirulina_test.csv'}")
    print("[generate] Done. No feature engineering — run features.py or train_anomaly.py next.")


if __name__ == "__main__":
    main()
