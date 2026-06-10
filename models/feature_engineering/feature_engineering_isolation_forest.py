"""Feature engineering for M1 IsolationForest — 1-hour MQTT data.

Called by app.py via load_module. Three entry points:
  _prepare_input(df)          — validate + sort input
  add_features(group)         — compute 1-hour-aware features per tank
  _infer_anomaly_labels(feat) — add rule-based anomaly label column

Operating ranges calibrated to AlgaePool production conditions per expert
Dominique Delobel (June 2026):
  pH          9.5–11.0 optimal   critical < 8.5 or > 11.5
  EC          15–22 mS/cm optimal  critical > 30 mS/cm
  temperature 34–39°C  optimal   critical < 20 or > 41
  DO          6–9 mg/L optimal    critical < 4.0 mg/L
  luminosity  indicative only (no action possible on AlgaePool)
  turbidity   OD 0.3–1.2 = NTU 114–456 optimal

Window semantics at 1-hour frequency
─────────────────────────────────────
  delta1    = v(t) - v(t-1)   ->  1-hour change
  delta4    = v(t) - v(t-4)   ->  4-hour change
  roll4     = 4 readings       ->  4-hour window
  roll16    = 16 readings      ->  16-hour window (full day)
  hour_sin / hour_cos           ->  circadian encoding
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SENSOR_COLUMNS = ["pH", "EC", "DO", "temperature", "luminosity", "turbidity"]

# Hard bounds per AlgaePool expert spec (Delobel, June 2026).
# Rows outside these bounds are labeled anomalous for pseudo-ground-truth.
_RULE_BOUNDS: dict[str, tuple[float, float]] = {
    "pH":          (8.50,  11.50),
    "EC":          (12.0,  32.0),     # mS/cm
    "DO":          (4.00,  12.00),    # critical < 4.0 mg/L
    "temperature": (20.0,  41.0),     # critical < 20 or > 41
    "luminosity":  (0.0,   80000.0),  # indicative only — very wide
    "turbidity":   (20.0,  760.0),    # OD 0.05-2.0 * 380 NTU
}

# Per-sensor 1-hour delta thresholds.
# pH spec: 0.3 pt/15min = warning, 0.5 pt/15min = critical (expert Q4).
# At 1-hour: warning = 0.3×4 = 1.2/h, critical = 0.5×4 = 2.0/h.
_DELTA_THRESHOLDS: dict[str, tuple[float, float]] = {
    # (warning, critical) — absolute delta per 1-hour reading
    "pH":        (1.20, 2.00),   # mS/cm version of 0.3/0.5 per 15 min scaled to 1h
    "EC":        (2.0,  4.0),    # mS/cm sudden change (accident-level drop)
    "turbidity": (80.0, 150.0),  # NTU per hour
}

# Feature columns fed to IsolationForest.
# 6 sensors × 8 features + 2 time = 50 total.
FEATURE_COLUMNS: list[str] = []
for _col in SENSOR_COLUMNS:
    FEATURE_COLUMNS.extend([
        _col,
        f"{_col}_delta1",      # 1-hour change
        f"{_col}_delta4",      # 4-hour change
        f"{_col}_roll4_mean",  # 4-hour mean
        f"{_col}_roll4_std",   # 4-hour volatility
        f"{_col}_zscore4",     # deviation from 4-hour baseline
        f"{_col}_roll16_mean", # 16-hour mean
        f"{_col}_zscore16",    # deviation from 16-hour baseline
    ])
FEATURE_COLUMNS += ["hour_sin", "hour_cos"]


def _prepare_input(df: pd.DataFrame) -> pd.DataFrame:
    """Validate types, add required columns, sort by (tank_id, timestamp)."""
    df = df.copy()

    # Accept both 'timestamp' and 'date' column names
    if "timestamp" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"timestamp": "date"})

    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
    for col in SENSOR_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "tank_id" not in df.columns:
        df["tank_id"] = 0
    if "_is_user_row" not in df.columns:
        df["_is_user_row"] = True

    return df.sort_values(["tank_id", "date"]).reset_index(drop=True)


def add_features(group: pd.DataFrame) -> pd.DataFrame:
    """Add 1-hour-aware temporal and circadian features per tank group."""
    g = group.copy().sort_values("date").reset_index(drop=True)

    # Circadian encoding from timestamp
    hour = g["date"].dt.hour + g["date"].dt.minute / 60.0
    g["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    g["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)

    for col in SENSOR_COLUMNS:
        if col not in g.columns:
            continue
        s = g[col]

        # Rate-of-change features
        g[f"{col}_delta1"] = s.diff(1)   # 1-hour delta
        g[f"{col}_delta4"] = s.diff(4)   # 4-hour delta

        # 4-hour window (4 readings)
        r4_mean = s.rolling(4,  min_periods=1).mean()
        r4_std  = s.rolling(4,  min_periods=1).std().fillna(0.0)
        g[f"{col}_roll4_mean"] = r4_mean
        g[f"{col}_roll4_std"]  = r4_std
        g[f"{col}_zscore4"]    = (s - r4_mean) / r4_std.clip(lower=1e-6)

        # 16-hour window (16 readings)
        r16_mean = s.rolling(16, min_periods=1).mean()
        r16_std  = s.rolling(16, min_periods=1).std().fillna(0.0)
        g[f"{col}_roll16_mean"] = r16_mean
        g[f"{col}_zscore16"]    = (s - r16_mean) / r16_std.clip(lower=1e-6)

    return g


def _infer_anomaly_labels(features: pd.DataFrame) -> pd.DataFrame:
    """Add `is_anomaly_rule` column (1 = violation, 0 = normal).

    Uses AlgaePool expert bounds (Delobel, June 2026):
      - pH delta > 1.2/h = warning (= 0.3/15min scaled to 1h)
      - pH delta > 2.0/h = critical (= 0.5/15min scaled to 1h)
    """
    f = features.copy()
    is_anom = pd.Series(False, index=f.index)

    # Static bounds
    for col, (lo, hi) in _RULE_BOUNDS.items():
        if col in f.columns:
            is_anom |= f[col].lt(lo) | f[col].gt(hi)

    # 1-hour delta thresholds (warning threshold used for labeling)
    for col, (warn, _) in _DELTA_THRESHOLDS.items():
        dcol = f"{col}_delta1"
        if dcol in f.columns:
            is_anom |= f[dcol].abs().gt(warn)

    f["is_anomaly_rule"] = is_anom.astype(int)
    return f
