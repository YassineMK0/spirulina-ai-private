"""Unit tests for M1 (LSTM anomaly), M2 (LightGBM turbidity), M3 (harvest scheduler).

These tests run WITHOUT loading real model artifacts — all models and scalers
are mocked so tests stay fast and work without GPUs or large files.
"""
import json
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch


# ── Fixtures ───────────────────────────────────────────────────────────────────

def make_sensor_df(n=20, start="2024-01-01"):
    """Build a synthetic sensor DataFrame with n rows."""
    dates = pd.date_range(start, periods=n, freq="D").strftime("%Y-%m-%d").tolist()
    return pd.DataFrame({
        "date":        dates,
        "pH":          [9.8] * n,
        "EC":          [2100.0] * n,
        "DO":          [7.2] * n,
        "temperature": [33.0] * n,
        "luminosity":  [11000.0] * n,
        "turbidity":   [180.0] * n,
    })


def make_m1_artifact(window_size=12, threshold=0.05, score_min=0.0, score_max=0.2):
    """Return a mock M1 artifact dict (no Keras model)."""
    from sklearn.preprocessing import MinMaxScaler
    scaler = MinMaxScaler()
    scaler.fit(np.random.rand(50, 6))

    artifact = {
        "scaler": scaler,
        "window_size": window_size,
        "sensor_columns": ["pH", "EC", "DO", "temperature", "luminosity", "turbidity"],
        "score_min": score_min,
        "score_max": score_max,
        "threshold": threshold,
    }
    # Mock Keras model — predict() returns reconstructed windows identical to input (zero error)
    mock_model = MagicMock()
    mock_model.predict = lambda windows, **kw: windows  # perfect reconstruction
    artifact["_model"] = mock_model
    return artifact


# ── M1 helper functions ────────────────────────────────────────────────────────

class TestM1Helpers:
    def test_severity_critical(self):
        from api.predict_lstm import _severity
        assert _severity(0.80) == "critical"
        assert _severity(0.99) == "critical"

    def test_severity_medium(self):
        from api.predict_lstm import _severity
        assert _severity(0.55) == "medium"
        assert _severity(0.79) == "medium"

    def test_severity_low(self):
        from api.predict_lstm import _severity
        assert _severity(0.0)  == "low"
        assert _severity(0.54) == "low"

    def test_norm_score_clamps_to_01(self):
        from api.predict_lstm import _norm_score
        assert _norm_score(0.0, 0.0, 0.2) == pytest.approx(0.0)
        assert _norm_score(0.2, 0.0, 0.2) == pytest.approx(1.0)
        assert _norm_score(-1.0, 0.0, 0.2) == pytest.approx(0.0)  # below min
        assert _norm_score(99.0, 0.0, 0.2) == pytest.approx(1.0)  # above max

    def test_norm_score_zero_range(self):
        from api.predict_lstm import _norm_score
        # score_max == score_min — should not divide by zero
        result = _norm_score(0.1, 0.1, 0.1)
        assert 0.0 <= result <= 1.0

    def test_trend_direction_declining(self):
        from api.predict_lstm import _trend_direction
        assert _trend_direction([0.1, 0.2, 0.35]) == "declining"

    def test_trend_direction_recovering(self):
        from api.predict_lstm import _trend_direction
        assert _trend_direction([0.9, 0.7, 0.5]) == "recovering"

    def test_trend_direction_stable(self):
        from api.predict_lstm import _trend_direction
        assert _trend_direction([0.5, 0.51, 0.50]) == "stable"

    def test_trend_direction_single_value(self):
        from api.predict_lstm import _trend_direction
        # Needs at least 2 valid values to compute a delta
        assert _trend_direction([0.8]) == "stable"

    def test_trend_direction_all_nan(self):
        from api.predict_lstm import _trend_direction
        assert _trend_direction([float("nan"), float("nan")]) == "stable"

    def test_sensor_attribution_sums_correctly(self):
        from api.predict_lstm import _sensor_attribution
        cols = ["pH", "EC", "DO", "temperature", "luminosity", "turbidity"]
        window = np.ones((12, 6)) * 0.5
        recon  = np.ones((12, 6)) * 0.4
        # All sensors have equal error, so all attributions should be equal
        attr = _sensor_attribution(window, recon, cols)
        values = list(attr.values())
        assert all(abs(v - values[0]) < 0.001 for v in values)

    def test_sensor_attribution_returns_all_columns(self):
        from api.predict_lstm import _sensor_attribution
        cols = ["pH", "EC", "DO", "temperature", "luminosity", "turbidity"]
        w = np.random.rand(12, 6)
        r = np.random.rand(12, 6)
        attr = _sensor_attribution(w, r, cols)
        assert set(attr.keys()) == set(cols)


# ── M1 predict_df ──────────────────────────────────────────────────────────────

class TestM1PredictDf:
    def test_output_columns_present(self):
        from api.predict_lstm import predict_df
        df = make_sensor_df(n=20)
        artifact = make_m1_artifact()
        result = predict_df(df, artifact)
        expected_cols = {"date", "pH", "EC", "DO", "temperature", "luminosity", "turbidity",
                         "anomaly_score", "is_anomaly", "severity", "sensor_attribution", "trend_direction"}
        assert expected_cols.issubset(set(result.columns))

    def test_output_length_equals_input_length(self):
        from api.predict_lstm import predict_df
        df = make_sensor_df(n=20)
        result = predict_df(df, make_m1_artifact())
        assert len(result) == len(df)

    def test_is_anomaly_is_boolean(self):
        from api.predict_lstm import predict_df
        result = predict_df(make_sensor_df(n=20), make_m1_artifact())
        assert result["is_anomaly"].dtype == bool

    def test_severity_values_are_valid(self):
        from api.predict_lstm import predict_df
        result = predict_df(make_sensor_df(n=20), make_m1_artifact())
        assert set(result["severity"].unique()).issubset({"critical", "medium", "low"})

    def test_sensor_attribution_is_valid_json(self):
        from api.predict_lstm import predict_df
        result = predict_df(make_sensor_df(n=20), make_m1_artifact())
        for v in result["sensor_attribution"]:
            parsed = json.loads(v)
            assert isinstance(parsed, dict)

    def test_raises_on_missing_columns(self):
        from api.predict_lstm import predict_df
        df = make_sensor_df(n=20).drop(columns=["pH"])
        with pytest.raises(ValueError, match="Missing required columns"):
            predict_df(df, make_m1_artifact())

    def test_raises_on_unparseable_date(self):
        from api.predict_lstm import predict_df
        df = make_sensor_df(n=5)
        df.loc[0, "date"] = "not-a-date"
        with pytest.raises(ValueError, match="Could not parse date"):
            predict_df(df, make_m1_artifact())

    def test_scores_nan_for_rows_before_window(self):
        from api.predict_lstm import predict_df
        # Only 5 rows but window_size=12 — all scores should be NaN
        df = make_sensor_df(n=5)
        result = predict_df(df, make_m1_artifact(window_size=12))
        assert result["anomaly_score"].isna().all()


# ── M2 helpers ─────────────────────────────────────────────────────────────────

def make_m2_artifact():
    """Return a mock M2 artifact."""
    mock_model = MagicMock()
    mock_model.predict = lambda X: np.array([150.0])
    return {
        "models": {"p10": mock_model, "p50": mock_model, "p90": mock_model},
        "feature_columns": None,  # handled by mock build_features
    }


class TestM2Predict:
    def test_output_keys_present(self):
        from api.predict_lgbm import predict
        df = make_sensor_df(n=6)
        artifact = make_m2_artifact()

        with patch("api.predict_lgbm.build_features") as mock_build:
            features_df = pd.DataFrame({
                "date": pd.to_datetime(["2024-01-06"]),
                "pH": [9.8], "EC": [2100.0],
            })
            mock_build.return_value = features_df
            artifact["feature_columns"] = ["pH", "EC"]
            result = predict(df, artifact)

        assert "low" in result
        assert "prediction" in result
        assert "high" in result
        assert "date" in result

    def test_prediction_within_low_high_range(self):
        from api.predict_lgbm import predict
        df = make_sensor_df(n=6)

        p10_mock = MagicMock(); p10_mock.predict = lambda X: np.array([100.0])
        p50_mock = MagicMock(); p50_mock.predict = lambda X: np.array([150.0])
        p90_mock = MagicMock(); p90_mock.predict = lambda X: np.array([200.0])

        artifact = {
            "models": {"p10": p10_mock, "p50": p50_mock, "p90": p90_mock},
            "feature_columns": ["pH", "EC"],
        }

        with patch("api.predict_lgbm.build_features") as mock_build:
            features_df = pd.DataFrame({
                "date": pd.to_datetime(["2024-01-06"]),
                "pH": [9.8], "EC": [2100.0],
            })
            mock_build.return_value = features_df
            result = predict(df, artifact)

        assert result["low"] <= result["prediction"] <= result["high"]

    def test_raises_when_features_empty(self):
        from api.predict_lgbm import predict
        df = make_sensor_df(n=1)
        artifact = make_m2_artifact()
        artifact["feature_columns"] = ["pH", "EC"]

        with patch("api.predict_lgbm.build_features") as mock_build:
            mock_build.return_value = pd.DataFrame()
            with pytest.raises(ValueError, match="Not enough recent rows"):
                predict(df, artifact)


# ── M3 helper functions ────────────────────────────────────────────────────────

class TestM3Helpers:
    def test_reason_not_ready(self):
        from api.predict_lgbm_harvest import _reason
        msg = _reason("not_ready", "today", 0)
        assert "not ready" in msg.lower()

    def test_reason_heavy(self):
        from api.predict_lgbm_harvest import _reason
        msg = _reason("heavy", "today", 40)
        assert "40%" in msg
        assert "optimal" in msg.lower()

    def test_reason_moderate(self):
        from api.predict_lgbm_harvest import _reason
        msg = _reason("moderate", "tomorrow", 25)
        assert "25%" in msg

    def test_reason_light(self):
        from api.predict_lgbm_harvest import _reason
        msg = _reason("light", "today", 10)
        assert "10%" in msg

    def test_recommendation_all_not_ready(self):
        from api.predict_lgbm_harvest import _recommendation
        schedule = {
            "today":     {"label": "not_ready", "harvest_pct": 0},
            "tomorrow":  {"label": "not_ready", "harvest_pct": 0},
            "day_after": {"label": "not_ready", "harvest_pct": 0},
        }
        rec = _recommendation(schedule)
        assert "not ready" in rec.lower()

    def test_recommendation_best_is_today(self):
        from api.predict_lgbm_harvest import _recommendation
        schedule = {
            "today":     {"label": "heavy",    "harvest_pct": 40},
            "tomorrow":  {"label": "light",    "harvest_pct": 10},
            "day_after": {"label": "not_ready", "harvest_pct": 0},
        }
        rec = _recommendation(schedule)
        assert "today" in rec.lower() or "40%" in rec

    def test_recommendation_best_is_tomorrow(self):
        from api.predict_lgbm_harvest import _recommendation
        schedule = {
            "today":     {"label": "light",    "harvest_pct": 10},
            "tomorrow":  {"label": "heavy",    "harvest_pct": 40},
            "day_after": {"label": "moderate", "harvest_pct": 25},
        }
        rec = _recommendation(schedule)
        assert "tomorrow" in rec.lower()

    def test_recommendation_best_is_day_after(self):
        from api.predict_lgbm_harvest import _recommendation
        schedule = {
            "today":     {"label": "light",    "harvest_pct": 10},
            "tomorrow":  {"label": "moderate", "harvest_pct": 20},
            "day_after": {"label": "heavy",    "harvest_pct": 40},
        }
        rec = _recommendation(schedule)
        assert "2 days" in rec.lower() or "day" in rec.lower()


# ── M3 schedule — integration (mocked build_features + model) ─────────────────

class TestM3Schedule:
    def _make_m3_artifact(self):
        mock_model = MagicMock()
        mock_model.predict_proba = lambda X: np.array([[0.05, 0.15, 0.70, 0.10]])
        return {
            "model": mock_model,
            "feature_columns": ["turbidity", "mu_3d"],
            "label_map_inv": {0: "not_ready", 1: "light", 2: "moderate", 3: "heavy"},
            "harvest_pct": {"not_ready": 0, "light": 10, "moderate": 25, "heavy": 40},
            "min_history_rows": 6,
        }

    def test_raises_when_too_few_rows(self):
        from api.predict_lgbm_harvest import schedule
        df = make_sensor_df(n=3)
        m3 = self._make_m3_artifact()
        with pytest.raises(ValueError, match="Need at least"):
            schedule(df, m3)

    def test_schedule_output_keys(self):
        from api.predict_lgbm_harvest import schedule
        df = make_sensor_df(n=8)
        m3 = self._make_m3_artifact()

        with patch("api.predict_lgbm_harvest.build_features") as mock_bf:
            mock_bf.return_value = pd.DataFrame({
                "turbidity": [180.0], "mu_3d": [0.03],
                "pH": [9.8], "EC": [2100.0], "DO": [7.2],
                "temperature": [33.0], "luminosity": [11000.0],
                "date": ["2024-01-08"],
            })
            result = schedule(df, m3)

        assert "today" in result
        assert "tomorrow" in result
        assert "day_after" in result
        assert "recommendation" in result

    def test_score_row_returns_expected_keys(self):
        from api.predict_lgbm_harvest import _score_row
        m3 = self._make_m3_artifact()
        row_feat = pd.DataFrame({"turbidity": [180.0], "mu_3d": [0.03]})
        result = _score_row(row_feat, m3)
        assert "label" in result
        assert "harvest_pct" in result
        assert "confidence" in result

    def test_score_row_returns_not_ready_on_nan_features(self):
        from api.predict_lgbm_harvest import _score_row
        m3 = self._make_m3_artifact()
        row_feat = pd.DataFrame({"turbidity": [float("nan")], "mu_3d": [float("nan")]})
        result = _score_row(row_feat, m3)
        assert result["label"] == "not_ready"
        assert result["harvest_pct"] == 0
