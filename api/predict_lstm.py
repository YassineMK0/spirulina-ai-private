"""Run M1-LSTM Temporal Anomaly Detector predictions.

Scores each incoming sensor row by reconstructing the 12-day window ending
at that row. High reconstruction error = the sequence does not look like
normal culture behavior.

No feature engineering required. Feed raw sensor readings directly.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


ARTIFACTS_DIR = Path(__file__).parent.parent / "models" / "saved"
ARTIFACT_PATH = ARTIFACTS_DIR / "m1_lstm_artifact.joblib"

SENSOR_COLUMNS = ["pH", "EC", "DO", "temperature", "luminosity", "turbidity"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _severity(score: float) -> str:
    if score >= 0.80:
        return "critical"
    if score >= 0.55:
        return "medium"
    return "low"


def _trend_direction(recent_scores: list[float]) -> str:
    """Classify whether the anomaly is worsening, recovering, or stable.

    Looks at the last 3 available scores. Requires at least 2 values.
    """
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


def _norm_score(error: float, score_min: float, score_max: float) -> float:
    return float(np.clip((error - score_min) / max(score_max - score_min, 1e-9), 0.0, 1.0))


def _sensor_attribution(
    window_input: np.ndarray,
    window_recon: np.ndarray,
    sensor_cols: list[str],
) -> dict[str, float]:
    """Per-sensor mean absolute error over the last 3 timesteps of the window.

    Focuses on the most recent readings rather than the full window, which
    makes the attribution reflect the current sensor state.
    """
    last3_err = np.abs(window_input[-3:] - window_recon[-3:]).mean(axis=0)
    norm = last3_err / (last3_err.max() + 1e-9)
    return dict(
        sorted(
            zip(sensor_cols, [round(float(v), 3) for v in norm]),
            key=lambda x: x[1],
            reverse=True,
        )
    )


# ── Main prediction function ──────────────────────────────────────────────────

def predict_df(df: pd.DataFrame, artifact: dict) -> pd.DataFrame:
    """Score sensor rows using the LSTM autoencoder.

    Parameters
    ----------
    df : DataFrame
        Must contain the 6 raw sensor columns sorted by date.
        If a ``_is_user_row`` boolean column is present, only those rows are
        returned in the output (history rows are used as window context only).
    artifact : dict
        Loaded artifact from m1_lstm_artifact.joblib with ``_model`` key
        populated (see load_artifact()).

    Returns
    -------
    DataFrame with columns:
        date, pH, EC, DO, temperature, luminosity, turbidity,
        anomaly_score, is_anomaly, severity, sensor_attribution, trend_direction
    """
    model = artifact["_model"]
    scaler = artifact["scaler"]
    window_size = artifact["window_size"]
    sensor_cols = artifact["sensor_columns"]
    score_min = artifact["score_min"]
    score_max = artifact["score_max"]
    threshold = artifact["threshold"]
    norm_threshold = _norm_score(threshold, score_min, score_max)

    missing = [col for col in ["date", *sensor_cols] if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.copy()
    date_sort = pd.to_datetime(df["date"], errors="coerce", format="mixed")
    if date_sort.isna().any():
        bad_rows = df.index[date_sort.isna()].tolist()[:5]
        raise ValueError(f"Could not parse date values at rows: {bad_rows}")

    df["_date_sort"] = date_sort
    df = df.sort_values("_date_sort").drop(columns=["_date_sort"]).reset_index(drop=True)
    if "_is_user_row" in df.columns and len(df) < window_size:
        raise ValueError(
            f"Not enough recent rows to build a {window_size}-row LSTM window. "
            f"Expected {window_size - 1} history rows plus today's reading."
        )

    scaled = scaler.transform(df[sensor_cols].fillna(0)).astype(np.float32)
    n = len(scaled)

    scores = np.full(n, np.nan)
    attributions: list[dict] = [{}] * n

    if n >= window_size:
        windows = np.stack(
            [scaled[i : i + window_size] for i in range(n - window_size + 1)], axis=0
        )
        reconstructed = model.predict(windows, batch_size=256, verbose=0)
        mae = np.mean(np.abs(windows - reconstructed), axis=(1, 2))

        for wi, row_i in enumerate(range(window_size - 1, n)):
            scores[row_i] = _norm_score(mae[wi], score_min, score_max)
            attributions[row_i] = _sensor_attribution(
                windows[wi], reconstructed[wi], sensor_cols
            )

    # trend_direction uses a rolling window of the last 3 scores
    trend: list[str] = ["stable"] * n
    for i in range(n):
        if not np.isnan(scores[i]):
            recent = [scores[max(0, i - 2)], scores[max(0, i - 1)], scores[i]]
            trend[i] = _trend_direction(recent)

    # Filter to user rows for output
    has_user_flag = "_is_user_row" in df.columns
    user_mask = (
        df["_is_user_row"].fillna(True).to_numpy().astype(bool)
        if has_user_flag
        else np.ones(n, dtype=bool)
    )

    out = df[user_mask].copy()
    out_idx = np.where(user_mask)[0]
    out_scores = scores[out_idx]

    out["anomaly_score"] = np.round(out_scores, 4)
    out["is_anomaly"] = out_scores >= norm_threshold
    out["severity"] = [_severity(float(s)) if not np.isnan(s) else "low" for s in out_scores]
    out["sensor_attribution"] = [json.dumps(attributions[i]) for i in out_idx]
    out["trend_direction"] = [trend[i] for i in out_idx]

    return out[
        [
            "date", "pH", "EC", "DO", "temperature", "luminosity", "turbidity",
            "anomaly_score", "is_anomaly", "severity",
            "sensor_attribution", "trend_direction",
        ]
    ]


def load_artifact(artifact_path: Path = ARTIFACT_PATH) -> dict:
    """Load joblib artifact and attach the Keras model."""
    import tensorflow as tf  # deferred import — TF startup is slow
    artifact = joblib.load(artifact_path)
    keras_path = ARTIFACTS_DIR / "m1_lstm_autoencoder.keras"
    artifact["_model"] = tf.keras.models.load_model(str(keras_path))
    return artifact


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=ARTIFACTS_DIR.parent.parent / "dataset" / "raw_sensor_data_lstm.csv",
    )
    args = parser.parse_args()

    full_df = pd.read_csv(args.input)
    artifact = load_artifact()
    window = artifact["window_size"]

    # ── Test 1: normal sequence ───────────────────────────────────────────────
    print("=" * 70)
    print("TEST 1 — Normal sequence (expect low scores, severity=low)")
    print("=" * 70)
    normal_rows = full_df[full_df["is_anomaly"] == 0].head(window + 10)
    result_normal = predict_df(normal_rows.reset_index(drop=True), artifact)
    print(result_normal[["date", "anomaly_score", "is_anomaly", "severity", "trend_direction"]].to_string(index=False))

    # ── Test 2: anomaly sequence per type ─────────────────────────────────────
    for atype in ["pH_crash", "DO_decline", "turbidity_crash"]:
        anom_idx = full_df[full_df["anomaly_type"] == atype].index
        if len(anom_idx) == 0:
            continue

        # Take the first event: grab window rows of context before it + the event rows
        event_start = anom_idx[0]
        event_end = anom_idx[anom_idx < event_start + 10][-1] + 1
        ctx_start = max(0, event_start - window)
        segment = full_df.iloc[ctx_start:event_end].reset_index(drop=True)

        print()
        print("=" * 70)
        print(f"TEST 2 — Anomaly type: {atype} (expect scores rising, trend=declining)")
        print("=" * 70)
        result_anom = predict_df(segment, artifact)
        # show which rows are the actual anomaly rows
        result_anom["label"] = list(
            full_df.iloc[ctx_start:event_end]["anomaly_type"].values
        )
        print(result_anom[["date", "label", "anomaly_score", "is_anomaly", "severity", "trend_direction"]].to_string(index=False))


if __name__ == "__main__":
    main()
