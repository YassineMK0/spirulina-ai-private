"""Feature engineering for M2 LightGBM turbidity forecasting.

Input  : dataset/raw_sensor_data.csv
Output : models/m2_lgbm_turbidity/m2_lgbm_training_data.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).parent.parent.parent
RAW_CSV = ROOT / "dataset" / "raw_sensor_data.csv"
OUT_CSV = Path(__file__).parent / "m2_lgbm_training_data.csv"

SENSOR_COLUMNS = ["pH", "EC", "DO", "temperature", "luminosity", "turbidity"]

FEATURE_COLUMNS = [
    "pH",
    "EC",
    "DO",
    "temperature",
    "luminosity",
    "turbidity",
    "delta_pH",
    "delta_EC",
    "delta_DO",
    "delta_temperature",
    "delta_luminosity",
    "delta_turbidity",
    "turbidity_lag1",
    "turbidity_lag2",
    "turbidity_lag3",
    "DO_lag1",
    "EC_lag1",
    "mu_3d",
    "rolling_turbidity_5d",
    "rolling_DO_3d",
    "rolling_temperature_3d",
]

TARGET_COLUMN = "turbidity_next_day"


def prepare_input(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize raw sensor rows and keep chronological order per tank/run."""
    missing = [col for col in ["date", *SENSOR_COLUMNS] if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    prepared = df.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce", format="mixed")
    if prepared["date"].isna().any():
        bad_rows = prepared.index[prepared["date"].isna()].tolist()[:5]
        raise ValueError(f"Could not parse date values at rows: {bad_rows}")

    for col in SENSOR_COLUMNS:
        prepared[col] = pd.to_numeric(prepared[col], errors="coerce")

    if "tank_id" not in prepared.columns:
        prepared = prepared.sort_values("date").reset_index(drop=True)
        date_step = prepared["date"].diff()
        new_run = date_step.isna() | (date_step <= pd.Timedelta(0))
        prepared["tank_id"] = new_run.cumsum().sub(1).astype("int32")

    return prepared.sort_values(["tank_id", "date"]).reset_index(drop=True)


def add_features(group: pd.DataFrame, include_targets: bool) -> pd.DataFrame:
    """Build lag, rolling, delta, and target columns for one chronological run."""
    g = group.sort_values("date").copy()

    for col in SENSOR_COLUMNS:
        g[f"delta_{col}"] = g[col].diff(1)

    g["turbidity_lag1"] = g["turbidity"].shift(1)
    g["turbidity_lag2"] = g["turbidity"].shift(2)
    g["turbidity_lag3"] = g["turbidity"].shift(3)
    g["DO_lag1"] = g["DO"].shift(1)
    g["EC_lag1"] = g["EC"].shift(1)

    g["mu_3d"] = (
        np.log(g["turbidity"].clip(lower=0.1) / g["turbidity_lag3"].clip(lower=0.1))
        / 3
    )

    # These rolling features include today's MQTT reading during inference.
    g["rolling_turbidity_5d"] = g["turbidity"].rolling(window=5, min_periods=5).mean()
    g["rolling_DO_3d"] = g["DO"].rolling(window=3, min_periods=3).mean()
    g["rolling_temperature_3d"] = g["temperature"].rolling(window=3, min_periods=3).mean()

    if include_targets:
        g[TARGET_COLUMN] = g["turbidity"].shift(-1)

    return g


def build_features(df: pd.DataFrame, include_targets: bool = True) -> pd.DataFrame:
    """Return model-ready features, optionally with tomorrow's turbidity target."""
    prepared = prepare_input(df)
    featured = pd.concat(
        [
            add_features(group, include_targets=include_targets)
            for _, group in prepared.groupby("tank_id", sort=False)
        ],
        ignore_index=True,
    )

    columns = ["date", "tank_id", *FEATURE_COLUMNS]
    required = list(FEATURE_COLUMNS)
    if include_targets:
        columns.append(TARGET_COLUMN)
        required.append(TARGET_COLUMN)

    return featured[columns].dropna(subset=required).reset_index(drop=True)


def main() -> None:
    df = pd.read_csv(RAW_CSV)
    out = build_features(df, include_targets=True)
    out.to_csv(OUT_CSV, index=False)

    print(f"Saved {len(out):,} rows -> {OUT_CSV}")
    print(out[["turbidity", "rolling_turbidity_5d", "mu_3d", TARGET_COLUMN]].describe().round(4))


if __name__ == "__main__":
    main()
