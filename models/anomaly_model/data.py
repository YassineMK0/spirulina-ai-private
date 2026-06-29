"""Feature extraction from iot_features_5min.csv.

The CSV mixes two genuinely different data densities:
- pH, EC, DO_mgL, Turbidite: ~1 real reading/day, the rest is linear
  interpolation (flagged by *_is_interpolated). Only the real rows are
  used for training.
- Temperature, Luminosite: real 5-min readings throughout. Used to build
  same-day context features and the seasonal baseline.
"""
from pathlib import Path

import numpy as np
import pandas as pd

CSV_PATH = Path(__file__).parent.parent / "iot_features_5min.csv"

SPARSE_COLS = ["pH", "EC", "DO_mgL", "Turbidite"]
DENSE_COLS = ["Temperature", "Luminosite"]


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH)

    # "EC" and "Luminosite" in the raw CSV are NOT in mS/cm / lux — they're
    # raw sensor units. EC_mScm_approx (x1.514) and Luminosite_lux_approx
    # (x120) are the calibrated values, matching what the production Atlas
    # EZO-EC kit (mS/cm) and DFRobot SEN0390 (lux) actually report. Replace
    # in place so every threshold/feature downstream is in real units.
    df["EC_raw"] = df["EC"]
    df["EC"] = df["EC_mScm_approx"]
    df["Luminosite_raw"] = df["Luminosite"]
    df["Luminosite"] = df["Luminosite_lux_approx"]

    masks = df[[f"{c if c != 'DO_mgL' else 'DO'}_is_interpolated" for c in SPARSE_COLS]]
    assert (masks.nunique(axis=1) == 1).all(), "expected the 4 sparse sensors to share one real/interpolated mask"
    df["day_index"] = np.floor(df["time_days"]).astype(int)
    df["hour_of_day"] = (df["time_days"] % 1.0) * 24.0
    return df


def real_daily_records(df: pd.DataFrame) -> pd.DataFrame:
    """One row per real (non-interpolated) daily reading, with same-day
    Temperature/Luminosite context aggregated from the dense signal."""
    real = df.loc[~df["pH_is_interpolated"], ["day_index", "time_days", *SPARSE_COLS]].copy()

    dense_daily = (
        df.groupby("day_index")[DENSE_COLS]
        .agg(["mean", "min", "max"])
    )
    dense_daily.columns = [f"{col}_{stat}" for col, stat in dense_daily.columns]

    merged = real.merge(dense_daily, on="day_index", how="left").sort_values("day_index").reset_index(drop=True)

    for col in SPARSE_COLS:
        merged[f"{col}_diff"] = merged[col].diff()

    return merged


def feature_matrix(records: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Select + clean the columns that go into the combination model.

    Turbidite/Turbidite_diff are intentionally excluded: production's
    turbidity sensor reports NTU and no NTU->OD680 conversion exists yet,
    so a live snapshot can never supply this feature (see README). Drop it
    here too so the trained feature_cols always matches what the live
    detector can actually fill in."""
    feature_cols = [
        "pH", "EC", "DO_mgL",
        "Temperature_mean", "Temperature_min", "Temperature_max",
        "Luminosite_mean", "Luminosite_min", "Luminosite_max",
        "pH_diff", "EC_diff", "DO_mgL_diff",
    ]
    X = records[feature_cols].copy()
    # first row has no diff; fill with 0 (no day-over-day change observed yet)
    X = X.fillna(0.0)
    return X, feature_cols
