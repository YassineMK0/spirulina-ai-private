"""
Shared feature engineering for the spirulina anomaly detector.

This module is the single source of truth for feature computation.
It is imported by:
    - models/train_anomaly.py  (batch, fits on train CSV)
    - api/predict_anomaly.py   (streaming, computes on a rolling buffer)

Usage — batch (training / offline evaluation):
    from data.features import compute_features, FEATURE_COLS

    df_raw    = pd.read_csv("data/spirulina_train.csv")
    df_feats  = compute_features(df_raw)        # adds 73 derived columns
    X         = df_feats[FEATURE_COLS].to_numpy()

Usage — streaming (MQTT / real-time inference):
    from data.features import compute_features, FEATURE_COLS

    # buffer is a list of raw dicts (oldest first), built from MQTT messages:
    # {"timestamp": ..., "ph": ..., "ec": ..., "do_mg": ...,
    #  "temp": ..., "turbidity": ..., "lux": ...}
    df_buf   = pd.DataFrame(buffer)
    df_feats = compute_features(df_buf)
    x_last   = df_feats[FEATURE_COLS].iloc[-1].to_numpy()  # feature vector for latest reading

Input columns required:
    timestamp (datetime-like), ph, ec, do_mg, temp, turbidity, lux

All other columns (is_anomaly, anomaly_type, …) are passed through unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Sensor list and window definitions
# ---------------------------------------------------------------------------

SENSORS: list[str] = ["ph", "ec", "do_mg", "temp", "turbidity", "lux"]

# Rolling windows: label -> number of 5-min steps
WINDOWS: dict[str, int] = {
    "30min": 6,   # 6  × 5 min = 30 min
    "1h":    12,  # 12 × 5 min = 1 h
    "6h":    72,  # 72 × 5 min = 6 h
}

# Delta (rate-of-change) windows
DELTA_WINDOWS: dict[str, int] = {
    "30min": 6,
    "1h":    12,
}

_EPS: float = 0.01   # prevents division-by-zero in z-score


# ---------------------------------------------------------------------------
# Feature column list (computed once at module load)
# ---------------------------------------------------------------------------

def _build_feature_col_list() -> list[str]:
    """Return the ordered list of feature column names produced by compute_features()."""
    cols: list[str] = []
    cols += SENSORS                                                     # 6  raw sensors
    for s in SENSORS:
        for lbl in WINDOWS:
            cols += [f"{s}_mean_{lbl}", f"{s}_std_{lbl}", f"{s}_zscore_{lbl}"]  # 18+18+18
        for lbl in DELTA_WINDOWS:
            cols.append(f"{s}_delta_{lbl}")                             # 12 deltas
    cols += ["hour_sin", "hour_cos", "day_sin", "day_cos"]              # 4  cyclic
    cols += ["do_lux_ratio", "ph_temp_ratio", "ec_turb_ratio"]          # 3  ratios
    return cols


FEATURE_COLS: list[str] = _build_feature_col_list()   # 79 features total


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add all derived features to a raw sensor DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: timestamp, ph, ec, do_mg, temp, turbidity, lux.
        Any extra columns (is_anomaly, anomaly_type, …) are preserved.

    Returns
    -------
    pd.DataFrame
        Original DataFrame with 73 additional feature columns appended.
        Row order and index are preserved.

    Notes
    -----
    - Rolling windows use min_periods=1 so the function works on a buffer of
      any length (cold-start safe).  Rows with fewer than `window` predecessors
      will have partial-window statistics, which is physically correct.
    - The function is stateless and side-effect free: it never modifies `df`.
    """
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    _add_rolling_features(df)
    _add_cyclic_features(df)
    _add_ratio_features(df)

    return df


# ---------------------------------------------------------------------------
# Feature sub-routines (not part of the public API)
# ---------------------------------------------------------------------------

def _add_rolling_features(df: pd.DataFrame) -> None:
    """
    Compute rolling mean, std, z-score, and delta for each sensor.

    Rolling z-score = (value − rolling_mean) / (rolling_std + ε).

    During a ph_spike that pushes pH from 9.5 to 13.0:
        ph_zscore_6h ≈ (13.0 − 9.6) / 0.2 ≈ 17  → trivially isolated by IsolationForest.
    During normal operation:
        ph_zscore_6h is typically in [−3, +3].
    """
    for sensor in SENSORS:
        s = df[sensor]
        for lbl, w in WINDOWS.items():
            mean = s.rolling(w, min_periods=1).mean()
            std  = s.rolling(w, min_periods=1).std().fillna(0.0)
            df[f"{sensor}_mean_{lbl}"]   = mean
            df[f"{sensor}_std_{lbl}"]    = std
            df[f"{sensor}_zscore_{lbl}"] = (s - mean) / (std + _EPS)
        for lbl, w in DELTA_WINDOWS.items():
            df[f"{sensor}_delta_{lbl}"] = s.diff(w).fillna(0.0)


def _add_cyclic_features(df: pd.DataFrame) -> None:
    """
    Encode timestamp as sine/cosine so the model knows the time of day.

    Without this, the model cannot distinguish lux=0 at midnight (normal)
    from lux=0 at noon (anomaly / sensor failure).
    """
    hour = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60.0
    doy  = df["timestamp"].dt.dayofyear.astype(float)
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    df["day_sin"]  = np.sin(2 * np.pi * doy  / 365.0)
    df["day_cos"]  = np.cos(2 * np.pi * doy  / 365.0)


def _add_ratio_features(df: pd.DataFrame) -> None:
    """
    Add inter-sensor ratios that capture cross-sensor relationships.

    do_lux_ratio  : DO relative to light — collapses during aerator failure
                    even when light is fine.
    ph_temp_ratio : disrupted by both temperature extremes and pH anomalies.
    ec_turb_ratio : nutrient concentration per unit of biomass — drops sharply
                    when EC collapses while turbidity (biomass) is still high.
    """
    df["do_lux_ratio"]  = df["do_mg"]  / (df["lux"]       + 1.0)
    df["ph_temp_ratio"] = df["ph"]     / (df["temp"]       + _EPS)
    df["ec_turb_ratio"] = df["ec"]     / (df["turbidity"]  + 1.0)


# ---------------------------------------------------------------------------
# Utility: save / load feature column list
# ---------------------------------------------------------------------------

def save_feature_cols(path: Path | str) -> None:
    """Write FEATURE_COLS to a JSON file (used by model artefacts)."""
    Path(path).write_text(json.dumps(FEATURE_COLS, indent=2))


def load_feature_cols(path: Path | str) -> list[str]:
    """Load and return feature columns from a saved JSON file."""
    return json.loads(Path(path).read_text())
