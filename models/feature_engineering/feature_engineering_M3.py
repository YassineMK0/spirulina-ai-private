"""Feature engineering for M3 Harvest Scheduler LightGBM.

The agent calls this explicitly before passing data to the model:

  Step 1 — fetch last 6 sensor readings from S3
  Step 2 — features = build_features(raw_df)
  Step 3 — schedule(features, m3_artifact, m2_artifact)

Input columns required:
  date, pH, EC, DO, temperature, luminosity, turbidity

Minimum rows: 6 (5 history + today) to compute rolling_turbidity_5d and mu_3d.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


FEATURE_COLUMNS = [
    "turbidity",
    "mu_3d",
    "delta_turbidity_3d",
    "rolling_turbidity_5d",
    "EC",
    "pH",
    "day_of_cycle",
    "days_since_last_harvest",
]

MIN_HISTORY_ROWS = 6


def _harvest_stats(turbidity: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Estimate day_of_cycle and days_since_last_harvest from turbidity pattern.

    A turbidity drop > 30% signals a harvest or cycle reset.
    """
    pct_change = turbidity.pct_change()
    cycle_days, days_since = [], []
    cycle_day, days_since_harvest = 1, 0

    for i, change in enumerate(pct_change):
        if i == 0 or (not pd.isna(change) and change < -0.30):
            cycle_day, days_since_harvest = 1, 0
        cycle_days.append(cycle_day)
        days_since.append(days_since_harvest)
        cycle_day += 1
        days_since_harvest += 1

    return (
        pd.Series(cycle_days, index=turbidity.index, dtype="int32"),
        pd.Series(days_since, index=turbidity.index, dtype="int32"),
    )


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all M3 features from raw sensor readings.

    Parameters
    ----------
    df : DataFrame
        Raw sensor readings sorted oldest first.
        Required columns: date, pH, EC, DO, temperature, luminosity, turbidity.

    Returns
    -------
    DataFrame with original columns plus all engineered features.
    The last row contains today's features ready for prediction.
    """
    g = df.copy().sort_values("date").reset_index(drop=True)

    g["rolling_turbidity_5d"] = g["turbidity"].rolling(5, min_periods=3).mean()
    g["delta_turbidity_3d"] = g["turbidity"].diff(3)

    turb_lag3 = g["turbidity"].shift(3)
    g["mu_3d"] = np.log(
        g["turbidity"].clip(lower=0.1) / turb_lag3.clip(lower=0.1)
    ) / 3

    g["day_of_cycle"], g["days_since_last_harvest"] = _harvest_stats(g["turbidity"])

    return g
