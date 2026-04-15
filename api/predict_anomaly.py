"""
FastAPI router for real-time spirulina anomaly detection.

Mount in api/main.py:

    from api.predict_anomaly import router as anomaly_router, load_artifacts

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        load_artifacts()        # <- add this line
        ...existing startup...
        yield

    app.include_router(anomaly_router)

Endpoint:
    POST /predict/anomaly
        Input : SensorReading  (6 raw sensor values + timestamp — exactly what MQTT delivers)
        Output: AnomalyPrediction

Feature engineering is handled by data/features.py — the same module used at
training time.  This guarantees training/serving consistency: any change to
feature logic only needs to be made once.

The last 288 readings (24 h) are held in an in-memory deque.  Rolling features
are recomputed from that buffer on every request.  Cold-start (< 288 readings)
is handled gracefully via min_periods=1.
"""

from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# Feature engineering — single source of truth shared with models/train_anomaly.py
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from data.features import compute_features, FEATURE_COLS, SENSORS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BUFFER_SIZE:   int  = 288   # 24 h of 5-min readings
ARTIFACTS_DIR: Path = Path(__file__).parent.parent / "models" / "saved"

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_artifacts: dict[str, Any] | None = None
_buffer: deque[dict[str, Any]] = deque(maxlen=BUFFER_SIZE)


# ---------------------------------------------------------------------------
# Pydantic I/O models
# ---------------------------------------------------------------------------

class SensorReading(BaseModel):
    """Raw 6-sensor snapshot — exactly what an MQTT message delivers."""

    timestamp: datetime = Field(..., description="UTC timestamp of the reading")
    ph:        float    = Field(..., ge=0.0,  le=14.0,      description="pH")
    ec:        float    = Field(..., ge=0.0,  le=15_000.0,  description="EC in µS/cm")
    do_mg:     float    = Field(..., ge=0.0,  le=30.0,      description="Dissolved O2 in mg/L")
    temp:      float    = Field(..., ge=0.0,  le=80.0,      description="Temperature in °C")
    turbidity: float    = Field(..., ge=0.0,  le=10_000.0,  description="Turbidity in NTU")
    lux:       float    = Field(..., ge=0.0,  le=200_000.0, description="Light intensity in lux")


class AnomalyPrediction(BaseModel):
    """Anomaly detection result returned for each sensor reading."""

    anomaly:            bool             = Field(..., description="True if anomaly detected")
    score:              float            = Field(..., description="Normalised anomaly score [0, 1]")
    severity:           str              = Field(..., description="normal | low | medium | critical")
    sensor_attribution: dict[str, float] = Field(
        ..., description="Per-sensor share of the anomaly score (values sum to 1.0)"
    )
    inference_time_ms:  float = Field(..., description="End-to-end latency in ms")
    buffer_size:        int   = Field(..., description="Readings currently in the rolling buffer")
    cold_start:         bool  = Field(..., description="True when buffer has < 288 readings")


# ---------------------------------------------------------------------------
# Artefact loading
# ---------------------------------------------------------------------------

def load_artifacts() -> None:
    """
    Load trained model artefacts from ARTIFACTS_DIR into module-level state.

    Call once from the FastAPI lifespan before the first request arrives.
    Raises RuntimeError if any required file is missing (train first).
    """
    global _artifacts

    required = ["isolation_forest.pkl", "xgboost_clf.pkl",
                "scaler.pkl", "feature_cols.json", "model_metadata.json"]
    missing  = [f for f in required if not (ARTIFACTS_DIR / f).exists()]
    if missing:
        raise RuntimeError(
            f"[predict_anomaly] Missing artefacts in {ARTIFACTS_DIR}: {missing}\n"
            "Run: python models/train_anomaly.py"
        )

    clf_if:   IsolationForest = joblib.load(ARTIFACTS_DIR / "isolation_forest.pkl")
    clf_xgb                   = joblib.load(ARTIFACTS_DIR / "xgboost_clf.pkl")
    scaler:   StandardScaler  = joblib.load(ARTIFACTS_DIR / "scaler.pkl")
    metadata: dict            = json.loads((ARTIFACTS_DIR / "model_metadata.json").read_text())

    _artifacts = {"clf_if": clf_if, "clf_xgb": clf_xgb,
                  "scaler": scaler, "metadata": metadata}
    print(f"[predict_anomaly] Loaded artefacts from {ARTIFACTS_DIR}  "
          f"({len(FEATURE_COLS)} features)")


def _get_artifacts() -> dict[str, Any]:
    """Return artefacts, lazy-loading on first call if necessary."""
    global _artifacts
    if _artifacts is None:
        load_artifacts()
    return _artifacts  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Feature vector construction
# ---------------------------------------------------------------------------

def _build_feature_vector(buffer: list[dict[str, Any]]) -> np.ndarray:
    """
    Compute the 79-dimensional feature vector for the most recent reading.

    Converts the raw-reading buffer to a DataFrame, calls the shared
    compute_features() function from data/features.py (identical to training),
    and returns the last row as shape (1, n_features).

    Parameters
    ----------
    buffer : list of raw-reading dicts, oldest first.
             Each dict must have keys: timestamp, ph, ec, do_mg, temp, turbidity, lux.
    """
    df      = pd.DataFrame(buffer)
    df_feat = compute_features(df)               # same function as training
    last    = df_feat.iloc[-1]
    row     = np.array([float(last[c]) for c in FEATURE_COLS], dtype=np.float64)
    return row.reshape(1, -1)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _normalise_score(raw: float, score_min: float, score_max: float) -> float:
    """Map a raw anomaly score to [0, 1].  Higher = more anomalous."""
    span = score_max - score_min
    return float(np.clip((raw - score_min) / span, 0.0, 1.0)) if span > 0 else 0.0


def _severity(norm_score: float, is_anomaly: bool, meta: dict) -> str:
    """
    Classify severity from a normalised anomaly score.

    Thresholds are the 33rd/66th percentiles of anomalous test-set scores,
    stored in model_metadata.json during training.
    """
    if not is_anomaly:
        return "normal"

    norm_p33 = _normalise_score(meta["severity_p33"], meta["score_min"], meta["score_max"])
    norm_p66 = _normalise_score(meta["severity_p66"], meta["score_min"], meta["score_max"])


    if norm_score < norm_p33:
        return "low"
    if norm_score < norm_p66:
        return "medium"
    return "critical"


def _sensor_attribution(X_scaled: np.ndarray) -> dict[str, float]:
    """
    Compute per-sensor contribution as the normalised sum of |z-scores|
    across all features belonging to each sensor.

    Returns a dict sorted by descending contribution, values sum to 1.0.
    """
    contrib: dict[str, float] = {s: 0.0 for s in SENSORS}
    x = X_scaled[0]

    for i, feat in enumerate(FEATURE_COLS):
        for sensor in SENSORS:
            if feat == sensor or feat.startswith(sensor + "_"):
                contrib[sensor] += abs(x[i])
                break

    total = sum(contrib.values()) or 1.0
    return {k: round(v / total, 4)
            for k, v in sorted(contrib.items(), key=lambda kv: -kv[1])}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/predict", tags=["Anomaly Detection"])


@router.post("/anomaly", response_model=AnomalyPrediction)
def predict_anomaly(reading: SensorReading) -> AnomalyPrediction:
    """
    Detect anomalies in a single spirulina sensor snapshot.

    The endpoint accepts the same 6 raw sensor values that an MQTT broker
    would publish.  Feature engineering (rolling stats, z-scores, ratios)
    is applied automatically using the shared data/features.py module.

    The in-memory buffer holds the last 288 readings (24 h) so that rolling
    window features have adequate history.  In cold-start mode the response
    includes `cold_start: true` as a reliability indicator.
    """
    t0      = time.perf_counter()
    arts    = _get_artifacts()
    clf_if: IsolationForest = arts["clf_if"]
    clf_xgb                 = arts["clf_xgb"]
    scaler: StandardScaler  = arts["scaler"]
    meta:   dict            = arts["metadata"]

    # Append raw reading to rolling buffer
    _buffer.append({
        "timestamp": reading.timestamp,
        "ph":        reading.ph,
        "ec":        reading.ec,
        "do_mg":     reading.do_mg,
        "temp":      reading.temp,
        "turbidity": reading.turbidity,
        "lux":       reading.lux,
    })

    cold_start = len(_buffer) < BUFFER_SIZE

    # Build feature vector using shared feature engineering
    try:
        X: np.ndarray = _build_feature_vector(list(_buffer))
    except Exception as exc:
        raise HTTPException(status_code=500,
                            detail=f"Feature engineering failed: {exc}") from exc

    # Score
    X_scaled:  np.ndarray = scaler.transform(X)

    # Binary decision — XGBoost with optimised probability threshold from training
    # (default 0.5 gives high precision but low recall; sweep found ~0.10 is optimal)
    xgb_proba:  float = float(clf_xgb.predict_proba(X_scaled)[0, 1])
    is_anomaly: bool  = xgb_proba >= float(meta["xgb_decision_threshold"])

    # Continuous score — Isolation Forest (for severity + attribution)
    raw_score: float = float(-clf_if.score_samples(X_scaled)[0])
    norm_score: float = _normalise_score(raw_score, meta["score_min"], meta["score_max"])

    return AnomalyPrediction(
        anomaly            = is_anomaly,
        score              = round(norm_score, 6),
        severity           = _severity(norm_score, is_anomaly, meta),
        sensor_attribution = _sensor_attribution(X_scaled),
        inference_time_ms  = round((time.perf_counter() - t0) * 1000, 3),
        buffer_size        = len(_buffer),
        cold_start         = cold_start,
    )


@router.delete("/anomaly/buffer", status_code=200)
def clear_buffer() -> dict[str, str]:
    """Clear the rolling readings buffer (e.g. when switching containers)."""
    _buffer.clear()
    return {"status": "buffer cleared"}
