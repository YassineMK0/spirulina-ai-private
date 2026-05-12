"""Inference helper for M2 LightGBM turbidity forecasting.

Production contract:
    recent_rows = last 5 S3 readings + today's MQTT reading
    predict(recent_rows, artifact) -> low/prediction/high tomorrow turbidity
"""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd

from models.feature_engineering.feature_engineering_M2 import FEATURE_COLUMNS, build_features


ARTIFACT_PATH = Path(__file__).parent.parent / "models" / "saved" / "m2_lgbm_turbidity_artifact.joblib"


def load_artifact(path: str | Path = ARTIFACT_PATH) -> dict:
    return joblib.load(path)


def predict(recent_rows: pd.DataFrame, artifact: dict) -> dict:
    """Predict tomorrow's turbidity from recent raw sensor readings."""
    features = build_features(recent_rows, include_targets=False)
    if features.empty:
        raise ValueError(
            "Not enough recent rows to build features. Expected at least 5 chronological readings."
        )

    today = features.iloc[[-1]]
    x_today = today[artifact.get("feature_columns", FEATURE_COLUMNS)]

    p10 = float(artifact["models"]["p10"].predict(x_today)[0])
    p50 = float(artifact["models"]["p50"].predict(x_today)[0])
    p90 = float(artifact["models"]["p90"].predict(x_today)[0])
    low = min(p10, p90)
    high = max(p10, p90)
    prediction = min(max(p50, low), high)

    return {
        "low": low,
        "prediction": prediction,
        "high": high,
        "date": today["date"].iloc[0].isoformat(),
    }


def predict_from_csv(csv_path: str | Path, artifact_path: str | Path = ARTIFACT_PATH) -> dict:
    df = pd.read_csv(csv_path).tail(6)
    artifact = load_artifact(artifact_path)
    return predict(df, artifact)


def main() -> None:
    import json
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("Usage: python predict_lgbm.py path/to/recent_rows.csv")

    result = predict_from_csv(sys.argv[1])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
