"""Single entry point for the agent: combines the rule engine, the
Local Outlier Factor combination-anomaly model, and the seasonal residual
check (Temperature/Luminosite) into one verdict.

Usage from the agent (pseudocode, after reading rows from SQLite):
    detector = AnomalyDetector.load()
    result = detector.evaluate(
        snapshot={"pH": 9.8, "EC": 16.2, "DO_mgL": 7.1,
                  "Temperature": 36.5, "Luminosite": 18000, "Turbidite": 0.8},
        previous=last_reading_dict_or_None,
        minutes_since_prev=5.0,
        hour_of_day=14.3,
        daily_context=rolling_24h_aggregates_dict_or_None,
    )
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import joblib
import numpy as np

from . import rules, seasonal

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


class AnomalyDetector:
    def __init__(self, combination_artifact: dict, baseline: dict):
        self.model = combination_artifact["model"]
        self.scaler = combination_artifact["scaler"]
        self.feature_cols = combination_artifact["feature_cols"]
        self.baseline = baseline

    @classmethod
    def load(cls, artifacts_dir: Path = ARTIFACTS_DIR) -> "AnomalyDetector":
        combination_artifact = joblib.load(artifacts_dir / "combination_model.joblib")
        baseline = seasonal.load_baseline(artifacts_dir / "seasonal_baseline.json")
        return cls(combination_artifact, baseline)

    def _score_combination_model(self, daily_context: dict) -> Optional[dict]:
        """daily_context must supply all of self.feature_cols (rolling 24h
        mean/min/max for Temperature & Luminosite, current sparse-sensor
        values and their day-over-day diffs). Returns None if the caller
        doesn't have enough history yet to build the vector."""
        try:
            row = [daily_context[c] for c in self.feature_cols]
        except KeyError:
            return None
        X = self.scaler.transform([row])
        score = float(self.model.decision_function(X)[0])
        is_anomaly = bool(self.model.predict(X)[0] == -1)
        return {"anomaly": is_anomaly, "score": score}

    def _score_seasonal(self, snapshot: dict, hour_of_day: float) -> dict:
        out = {}
        for sensor in ("Temperature", "Luminosite"):
            if sensor in snapshot:
                z = seasonal.residual_zscore(self.baseline, sensor, hour_of_day, snapshot[sensor])
                out[sensor] = {"zscore": z, "anomaly": abs(z) >= 4.0}
        return out

    def evaluate(
        self,
        snapshot: dict,
        previous: Optional[dict] = None,
        minutes_since_prev: Optional[float] = None,
        hour_of_day: Optional[float] = None,
        daily_context: Optional[dict] = None,
    ) -> dict:
        rule_findings = rules.evaluate_rules(snapshot, previous, minutes_since_prev)

        seasonal_result = self._score_seasonal(snapshot, hour_of_day) if hour_of_day is not None else {}

        combination_result = self._score_combination_model(daily_context) if daily_context is not None else None

        max_rule_severity = max((f.severity for f in rule_findings), default=0)
        seasonal_triggered = any(v["anomaly"] for v in seasonal_result.values())
        combination_triggered = bool(combination_result and combination_result["anomaly"])

        if max_rule_severity == 3:
            overall_severity = 3
        elif max_rule_severity == 2 or combination_triggered:
            overall_severity = 2
        elif max_rule_severity == 1 or seasonal_triggered:
            overall_severity = 1
        else:
            overall_severity = 0

        return {
            "overall_severity": overall_severity,  # 0=ok,1=info,2=warning,3=critical
            "rule_findings": [f.__dict__ for f in rule_findings],
            "seasonal": seasonal_result,
            "combination_model": combination_result,
        }
