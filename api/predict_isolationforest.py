"""M1 IsolationForest prediction helpers.

Row-level helpers + predict_df / load_artifact for monitor.py integration.
Rule thresholds calibrated to AlgaePool production conditions per expert
Dominique Delobel (June 2026). EC is in mS/cm.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ARTIFACTS_DIR = Path(__file__).parent.parent / "models" / "saved"
ARTIFACT_PATH = ARTIFACTS_DIR / "m1_isolation_forest.joblib"


def _get(row, key: str) -> float | None:
    """Safely read a float from a row, returning None on missing/NaN."""
    try:
        v = float(row[key])
        return None if np.isnan(v) else v
    except (KeyError, TypeError, ValueError):
        return None


# ── Public API (called by app.py) ─────────────────────────────────────────────

def _raw_to_score(
    raw_scores: np.ndarray,
    score_min: float,
    score_max: float,
) -> np.ndarray:
    """Normalize IsolationForest raw scores to [0, 1]."""
    span = max(score_max - score_min, 1e-9)
    return np.clip((raw_scores - score_min) / span, 0.0, 1.0)


def _rule_score(row, rule_thresholds: dict) -> float:
    """Return a 0-1 severity score based on hard threshold violations.

    1.0 = critical violation, 0.6-0.90 = warning, 0.0 = normal.
    Takes the maximum score across all sensor checks.
    Thresholds per AlgaePool expert spec (Delobel, June 2026).
    """
    rt = rule_thresholds
    score = 0.0

    # pH static bounds
    ph = _get(row, "pH")
    if ph is not None:
        if ph < rt.get("pH_low_crit", 8.50) or ph > rt.get("pH_high_crit", 11.50):
            score = max(score, 1.0)
        elif ph < rt.get("pH_low_warn", 9.50) or ph > rt.get("pH_high_warn", 11.00):
            score = max(score, 0.70)

    # pH rate-of-change (expert: 0.3 pt/15min = warn, 0.5 pt/15min = crit -> ×4 at 1h)
    ph_d = _get(row, "pH_delta1")
    if ph_d is not None:
        if abs(ph_d) > rt.get("pH_delta_crit", 2.00):
            score = max(score, 1.0)
        elif abs(ph_d) > rt.get("pH_delta_warn", 1.20):
            score = max(score, 0.65)

    # EC (mS/cm): optimal 15-22, critical > 30
    ec = _get(row, "EC")
    if ec is not None:
        if ec < rt.get("EC_low_crit", 12.0) or ec > rt.get("EC_high_crit", 30.0):
            score = max(score, 1.0)
    ec_d = _get(row, "EC_delta1")
    if ec_d is not None and abs(ec_d) > rt.get("EC_delta_crit", 4.0):
        score = max(score, 0.85)

    # Dissolved oxygen (expert: critical < 4.0 mg/L)
    do = _get(row, "DO")
    if do is not None:
        if do < rt.get("DO_low_crit", 4.00) or do > rt.get("DO_high_crit", 12.00):
            score = max(score, 0.90)

    # Temperature (expert: critical < 20 or > 41; warning < 25 = slow growth)
    temp = _get(row, "temperature")
    if temp is not None:
        if temp < rt.get("temperature_low_crit", 20.0) or temp > rt.get("temperature_high_crit", 41.0):
            score = max(score, 0.90)
        elif temp < rt.get("temperature_low_warn", 25.0):
            score = max(score, 0.60)

    # Turbidity static + crash
    turb = _get(row, "turbidity")
    if turb is not None:
        if turb < rt.get("turbidity_low_crit", 20.0) or turb > rt.get("turbidity_high_crit", 760.0):
            score = max(score, 0.85)
    turb_d = _get(row, "turbidity_delta1")
    if turb_d is not None and abs(turb_d) > rt.get("turbidity_crash", 100.0):
        score = max(score, 0.80)

    return float(score)


def _severity(score: float) -> str:
    if score >= 0.80:
        return "critical"
    if score >= 0.55:
        return "medium"
    return "low"


def _sensor_attribution(row, sensor_stats: dict) -> dict[str, float]:
    """Return per-sensor contribution as a normalized absolute z-score dict.

    The sensor with the highest value deviated most from its training mean,
    making it the most likely driver of the anomaly.
    """
    sensors = ["pH", "EC", "DO", "temperature", "luminosity", "turbidity"]
    z: dict[str, float] = {}
    for s in sensors:
        val = _get(row, s)
        if val is None or s not in sensor_stats:
            z[s] = 0.0
            continue
        mean = sensor_stats[s]["mean"]
        std  = sensor_stats[s]["std"]
        z[s] = abs(val - mean) / (std + 1e-6)

    total = sum(z.values()) + 1e-9
    normalized = {k: round(v / total, 3) for k, v in z.items()}
    return dict(sorted(normalized.items(), key=lambda x: x[1], reverse=True))


def _trend_direction(recent_scores: list[float]) -> str:
    valid = [s for s in recent_scores if not np.isnan(s)]
    if len(valid) < 2:
        return "stable"
    deltas = [valid[i + 1] - valid[i] for i in range(len(valid) - 1)]
    avg = sum(deltas) / len(deltas)
    if avg > 0.04:
        return "declining"
    if avg < -0.04:
        return "recovering"
    return "stable"


# ── Artifact loader ───────────────────────────────────────────────────────────

def load_artifact(artifact_path: Path = ARTIFACT_PATH) -> dict:
    """Load the IsolationForest joblib artifact (Pipeline + metadata)."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return joblib.load(artifact_path)


# ── Main prediction function ──────────────────────────────────────────────────

def predict_df(df: pd.DataFrame, artifact: dict) -> pd.DataFrame:
    """Score sensor rows using the IsolationForest pipeline + expert rules.

    Parameters
    ----------
    df : DataFrame
        Must contain SENSOR_COLUMNS + a 'date' column.
        Optional '_is_user_row' bool: only those rows appear in output.
    artifact : dict
        Loaded via load_artifact().

    Returns
    -------
    DataFrame with: date, pH, EC, DO, temperature, luminosity, turbidity,
        anomaly_score, is_anomaly, severity, sensor_attribution, trend_direction
    """
    from models.feature_engineering.feature_engineering_isolation_forest import (
        _prepare_input, add_features,
    )

    model           = artifact["model"]
    feature_cols    = artifact["feature_columns"]
    threshold       = artifact["threshold"]
    score_min       = artifact["score_min"]
    score_max       = artifact["score_max"]
    rule_thresholds = artifact.get("rule_thresholds", {})
    sensor_stats    = artifact.get("sensor_stats", {})

    df = _prepare_input(df)
    if df.empty:
        return df

    # MQTT sends EC in µS/cm; model trained on mS/cm. Auto-convert when needed.
    # Normal mS/cm range: 12–32. If median > 100 it's µS/cm → divide by 1000.
    if "EC" in df.columns and df["EC"].median() > 100:
        df["EC"] = df["EC"] / 1000.0

    df = (
        df.groupby("tank_id", group_keys=False)
          .apply(add_features)
          .reset_index(drop=True)
    )

    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0.0
    X = df[feature_cols].fillna(0.0)

    raw_scores = model.decision_function(X)

    # norm_ml: 0=normal, 1=most anomalous (invert _raw_to_score which gives 0=anomalous)
    norm_ml = 1.0 - _raw_to_score(raw_scores, score_min, score_max)

    n = len(df)
    rule_scores = np.array([_rule_score(df.iloc[i], rule_thresholds) for i in range(n)])

    # Hybrid: take the higher of ML and rule-based signal
    anomaly_scores = np.maximum(norm_ml, rule_scores)

    # Two independent detection layers:
    #   Layer 1 — Statistical: norm_ml >= threshold (95th percentile of normal validation
    #             scores, calibrated in train.py). ~5% false alarm rate by construction.
    #   Layer 2 — Expert rules: hard critical bounds (pH, EC, DO, temp, turbidity).
    #             Medium scores (0.55–0.79) stay visible in severity but don't fire alerts.
    is_anomaly = (norm_ml >= threshold) | (rule_scores >= 0.80)

    trend = []
    for i in range(n):
        recent = [anomaly_scores[max(0, i - 2)], anomaly_scores[max(0, i - 1)], anomaly_scores[i]]
        trend.append(_trend_direction(recent))

    attributions = [
        json.dumps(_sensor_attribution(df.iloc[i], sensor_stats)) for i in range(n)
    ]

    df["anomaly_score"]      = np.round(anomaly_scores, 4)
    df["is_anomaly"]         = is_anomaly
    df["severity"]           = [_severity(float(s)) for s in anomaly_scores]
    df["sensor_attribution"] = attributions
    df["trend_direction"]    = trend

    has_flag = "_is_user_row" in df.columns
    mask = df["_is_user_row"].fillna(True).astype(bool) if has_flag else pd.Series(True, index=df.index)

    out_cols = [
        "date", "pH", "EC", "DO", "temperature", "luminosity", "turbidity",
        "anomaly_score", "is_anomaly", "severity", "sensor_attribution", "trend_direction",
    ]
    existing = [c for c in out_cols if c in df.columns]
    return df.loc[mask, existing].reset_index(drop=True)
