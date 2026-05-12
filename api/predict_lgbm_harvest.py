"""M3 Harvest Scheduler — 3-day harvest window prediction.

Given the last 6 sensor readings, returns a harvest recommendation for:
  today, tomorrow, and the day after.

Each day is scored independently using the same M3 model:
  - Today       : scored on real sensor data
  - Tomorrow    : scored on M2-projected turbidity (or growth extrapolation)
  - Day after   : scored on further extrapolation

The agent can then tell the operator:
  "You can harvest 15% today. If you wait until tomorrow you can harvest 25%.
   In 2 days the window reaches 35% — optimal yield."

Production usage:
  1. Agent fetches last 6 sensor readings from S3.
  2. Calls schedule(recent_rows, m3_artifact, m2_artifact).
  3. Returns the 3-day schedule + recommendation string.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import joblib
import numpy as np
import pandas as pd

from models.feature_engineering.feature_engineering_M3 import build_features


ARTIFACTS_DIR = Path(__file__).parent.parent / "models" / "saved"
M3_ARTIFACT_PATH = ARTIFACTS_DIR / "m3_lgbm_artifact.joblib"
M2_ARTIFACT_PATH = ARTIFACTS_DIR / "m2_lgbm_turbidity_artifact.joblib"


# ── Turbidity projection ──────────────────────────────────────────────────────

def _project_turbidity(recent_rows: pd.DataFrame, m2_artifact: dict | None,
                       days_ahead: int) -> float:
    """Estimate turbidity N days from now.

    Uses M2 LightGBM for day+1 if available, then rolls forward using
    current growth rate (mu_3d) for day+2 and beyond.
    """
    features = build_features(recent_rows)
    today = features.iloc[-1]
    today_turbidity = float(today["turbidity"])
    mu = float(today["mu_3d"]) if not np.isnan(today.get("mu_3d", np.nan)) else 0.03

    if days_ahead == 1 and m2_artifact is not None:
        try:
            feat_cols = m2_artifact["feature_columns"]
            today_feat = features.iloc[[-1]][feat_cols].copy()
            if not today_feat.isna().any().any():
                p50 = float(m2_artifact["models"]["p50"].predict(today_feat)[0])
                return max(p50, 10.0)
        except Exception:
            pass

    # Fallback: simple exponential growth extrapolation
    return float(np.clip(today_turbidity * np.exp(mu * days_ahead), 10.0, 950.0))


def _build_projected_row(recent_rows: pd.DataFrame, projected_turbidity: float,
                         days_ahead: int) -> pd.DataFrame:
    """Build a synthetic sensor row for a projected future state.

    Only turbidity changes meaningfully in the short-term projection.
    EC depletes at today's rate. Other sensors stay approximately stable.
    """
    features = build_features(recent_rows)
    today = features.iloc[-1].copy()

    # Build a small extended dataframe to recompute rolling features
    extended = recent_rows.copy().sort_values("date").reset_index(drop=True)

    import datetime
    last_date = pd.to_datetime(extended["date"].iloc[-1])

    for d in range(1, days_ahead + 1):
        new_date = last_date + datetime.timedelta(days=d)
        turb = projected_turbidity if d == days_ahead else float(
            np.clip(float(today["turbidity"]) * np.exp(float(today.get("mu_3d", 0.03)) * d), 10.0, 950.0)
        )
        delta_ec = float(today.get("delta_EC", -60)) if "delta_EC" in today.index else -60.0
        new_row = {
            "date": new_date.strftime("%Y-%m-%d"),
            "pH": float(today["pH"]),
            "EC": max(float(today["EC"]) + delta_ec * d, 1500.0),
            "DO": float(today["DO"]),
            "temperature": float(today["temperature"]),
            "luminosity": float(today["luminosity"]),
            "turbidity": round(turb, 2),
        }
        extended = pd.concat(
            [extended, pd.DataFrame([new_row])], ignore_index=True
        )

    projected_features = build_features(extended)
    return projected_features.iloc[[-1]]


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_row(row_features: pd.DataFrame, artifact: dict) -> dict:
    model = artifact["model"]
    feature_cols = artifact["feature_columns"]
    label_map_inv = artifact["label_map_inv"]
    harvest_pct = artifact["harvest_pct"]

    feat = row_features[feature_cols].copy()
    if feat.isna().any().any():
        return {"label": "not_ready", "harvest_pct": 0, "confidence": 0.0}

    proba = model.predict_proba(feat)[0]
    pred_class = int(np.argmax(proba))
    label = label_map_inv[pred_class]
    confidence = round(float(proba[pred_class]), 3)

    return {
        "label": label,
        "harvest_pct": harvest_pct[label],
        "confidence": confidence,
    }


def _reason(label: str, day: str, harvest_pct: int) -> str:
    messages = {
        "not_ready": f"Culture not ready on {day} — too early or still in fast growth.",
        "light": f"{day.capitalize()}: light harvest window ({harvest_pct}%) — culture growing but harvestable.",
        "moderate": f"{day.capitalize()}: moderate harvest window ({harvest_pct}%) — growth is slowing.",
        "heavy": f"{day.capitalize()}: optimal harvest window ({harvest_pct}%) — plateau phase, harvest soon.",
    }
    return messages.get(label, "")


def _recommendation(schedule: dict) -> str:
    priority = {"not_ready": 0, "light": 1, "moderate": 2, "heavy": 3}
    days = ["today", "tomorrow", "day_after"]

    best_day = max(days, key=lambda d: priority[schedule[d]["label"]])
    best = schedule[best_day]

    if best["label"] == "not_ready":
        return "Culture not ready for harvest. Continue monitoring."

    if best_day == "today":
        return (
            f"Harvest {best['harvest_pct']}% today."
            if schedule["tomorrow"]["label"] not in ("moderate", "heavy")
            else f"Harvest {best['harvest_pct']}% today or wait — tomorrow may offer a better window."
        )
    if best_day == "tomorrow":
        today_pct = schedule["today"]["harvest_pct"]
        return (
            f"Wait until tomorrow — harvest {best['harvest_pct']}% "
            f"instead of {today_pct}% today for better yield."
        )

    today_pct = schedule["today"]["harvest_pct"]
    tomorrow_pct = schedule["tomorrow"]["harvest_pct"]
    return (
        f"Wait 2 days — harvest {best['harvest_pct']}% for maximum yield "
        f"(vs {tomorrow_pct}% tomorrow or {today_pct}% today)."
    )


# ── Main schedule function ────────────────────────────────────────────────────

def schedule(
    recent_rows: pd.DataFrame,
    m3_artifact: dict,
    m2_artifact: dict | None = None,
) -> dict:
    """Generate a 3-day harvest schedule.

    Parameters
    ----------
    recent_rows : DataFrame
        Last 6 daily sensor readings sorted oldest first.
        Columns: date, pH, EC, DO, temperature, luminosity, turbidity.
    m3_artifact : dict
        Loaded from m3_lgbm_artifact.joblib.
    m2_artifact : dict, optional
        Loaded from m2_growth/m2_lgbm_artifact.joblib.
        If provided, M2 is used for tomorrow's turbidity projection.
        If not, simple growth extrapolation is used instead.

    Returns
    -------
    dict with keys: today, tomorrow, day_after, recommendation
    """
    min_rows = m3_artifact.get("min_history_rows", 6)
    if len(recent_rows) < min_rows:
        raise ValueError(
            f"Need at least {min_rows} rows (5 history + today). Got {len(recent_rows)}."
        )

    recent_rows = recent_rows.sort_values("date").reset_index(drop=True)

    # Score today on real data
    today_features = build_features(recent_rows)
    today_score = _score_row(today_features.iloc[[-1]], m3_artifact)

    # Project and score tomorrow
    turb_d1 = _project_turbidity(recent_rows, m2_artifact, days_ahead=1)
    tomorrow_row = _build_projected_row(recent_rows, turb_d1, days_ahead=1)
    tomorrow_score = _score_row(tomorrow_row, m3_artifact)

    # Project and score day after
    turb_d2 = _project_turbidity(recent_rows, m2_artifact=None, days_ahead=2)
    day_after_row = _build_projected_row(recent_rows, turb_d2, days_ahead=2)
    day_after_score = _score_row(day_after_row, m3_artifact)

    result = {
        "today": {**today_score, "reason": _reason(today_score["label"], "today", today_score["harvest_pct"])},
        "tomorrow": {**tomorrow_score, "reason": _reason(tomorrow_score["label"], "tomorrow", tomorrow_score["harvest_pct"])},
        "day_after": {**day_after_score, "reason": _reason(day_after_score["label"], "day after tomorrow", day_after_score["harvest_pct"])},
    }
    result["recommendation"] = _recommendation(result)
    return result


def load_artifacts() -> tuple[dict, dict | None]:
    m3 = joblib.load(M3_ARTIFACT_PATH)
    m2 = joblib.load(M2_ARTIFACT_PATH) if M2_ARTIFACT_PATH.exists() else None
    return m3, m2


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse, json

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=ARTIFACTS_DIR.parent.parent / "dataset" / "raw_sensor_data.csv",
    )
    parser.add_argument("--rows", type=int, default=6)
    args = parser.parse_args()

    m3_artifact, m2_artifact = load_artifacts()
    df = pd.read_csv(args.input).tail(args.rows)
    result = schedule(df, m3_artifact, m2_artifact)

    print("\nM3 Harvest Schedule")
    print("=" * 50)
    for day in ["today", "tomorrow", "day_after"]:
        d = result[day]
        print(f"\n{day.upper()}")
        print(f"  Label:       {d['label']}")
        print(f"  Harvest:     {d['harvest_pct']}%")
        print(f"  Confidence:  {d['confidence']}")
        print(f"  Reason:      {d['reason']}")

    print(f"\nRECOMMENDATION: {result['recommendation']}")


if __name__ == "__main__":
    main()
