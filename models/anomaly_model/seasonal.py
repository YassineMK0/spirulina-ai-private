"""Hour-of-day baseline for the densely-sampled sensors (Temperature, Luminosite).

Only these two channels have genuine 5-min resolution in the historical
data, so this is the only place a residual-from-expected-curve check is
currently justified (see project memory: pH/EC/DO/Turbidite are ~99.7%
interpolation artifact at this resolution).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import DENSE_COLS

ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "seasonal_baseline.json"


def build_baseline(df: pd.DataFrame) -> dict:
    df = df.copy()
    df["hour_bin"] = df["hour_of_day"].astype(int).clip(0, 23)

    baseline = {}
    for col in DENSE_COLS:
        grouped = df.groupby("hour_bin")[col]
        median = grouped.median()
        mad = (grouped.apply(lambda s: (s - s.median()).abs().median())).clip(lower=1e-6)
        baseline[col] = {
            "median": median.reindex(range(24)).interpolate(limit_direction="both").tolist(),
            "mad": mad.reindex(range(24)).interpolate(limit_direction="both").tolist(),
        }
    return baseline


def save_baseline(baseline: dict, path: Path = ARTIFACT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=2))


def load_baseline(path: Path = ARTIFACT_PATH) -> dict:
    return json.loads(path.read_text())


def residual_zscore(baseline: dict, sensor: str, hour_of_day: float, value: float) -> float:
    """Robust z-score of `value` against the hour-of-day baseline.
    MAD is scaled by 1.4826 to be comparable to a normal std-dev."""
    hour_bin = int(hour_of_day) % 24
    median = baseline[sensor]["median"][hour_bin]
    mad = baseline[sensor]["mad"][hour_bin]
    robust_std = mad * 1.4826
    if robust_std <= 0:
        return 0.0
    return (value - median) / robust_std
