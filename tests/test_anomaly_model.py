"""Unit tests for models/anomaly_model -- the M1 rule engine, seasonal
residual check, and combination-model (LOF) detector wired into
agent/monitor.py this session.

Covers the Turbidite-optional fix in rules.py (a real KeyError bug found
while wiring the agent -- the live snapshot never includes a Turbidite key,
and evaluate_rules used to require it unconditionally) and sanity-checks
the retrained combination model's feature set.
"""
import pytest

from models.anomaly_model import rules, seasonal
from models.anomaly_model.detector import AnomalyDetector


# =============================================================================
# rules.evaluate_rules -- Turbidite-optional fix
# =============================================================================

class TestEvaluateRulesTurbidite:
    BASE_SNAPSHOT = {
        "pH": 9.8, "EC": 16.2, "DO_mgL": 7.1,
        "Temperature": 36.5, "Luminosite": 18000.0,
    }

    def test_missing_turbidite_key_does_not_raise(self):
        # This is exactly the shape agent.monitor._to_snapshot() produces --
        # no "Turbidite" key at all (no NTU->OD680 calibration exists).
        findings = rules.evaluate_rules(self.BASE_SNAPSHOT)
        assert findings == []

    def test_turbidite_none_is_also_skipped(self):
        snap = {**self.BASE_SNAPSHOT, "Turbidite": None}
        findings = rules.evaluate_rules(snap)
        assert findings == []

    def test_turbidite_present_and_critical_is_still_caught(self):
        snap = {**self.BASE_SNAPSHOT, "Turbidite": 2.0}  # > 1.5 critical threshold
        findings = rules.evaluate_rules(snap)
        assert any(f.parameter == "Turbidite" and f.severity == 3 for f in findings)

    def test_ph_crash_caught_even_without_turbidite(self):
        snap = {**self.BASE_SNAPSHOT, "pH": 7.0}
        findings = rules.evaluate_rules(snap)
        assert any(f.parameter == "pH" and f.severity == 3 for f in findings)


# =============================================================================
# seasonal.residual_zscore
# =============================================================================

class TestSeasonalResidualZscore:
    BASELINE = {
        "Temperature": {"median": [30.0] * 24, "mad": [1.0] * 24},
    }

    def test_value_at_median_has_zero_zscore(self):
        z = seasonal.residual_zscore(self.BASELINE, "Temperature", 12.0, 30.0)
        assert z == pytest.approx(0.0)

    def test_value_far_from_median_has_large_zscore(self):
        z = seasonal.residual_zscore(self.BASELINE, "Temperature", 12.0, 40.0)
        assert abs(z) > 4.0

    def test_zero_mad_does_not_divide_by_zero(self):
        baseline = {"Temperature": {"median": [30.0] * 24, "mad": [0.0] * 24}}
        z = seasonal.residual_zscore(baseline, "Temperature", 12.0, 35.0)
        assert z == 0.0


# =============================================================================
# AnomalyDetector -- loads the real retrained artifact
# =============================================================================

class TestAnomalyDetectorLoad:
    @pytest.fixture(scope="class")
    def detector(self):
        return AnomalyDetector.load()

    def test_loads_without_error(self, detector):
        assert detector.model is not None
        assert detector.scaler is not None

    def test_feature_cols_excludes_turbidite(self, detector):
        # Retrained without Turbidite -- no NTU->OD680 calibration exists for
        # the live turbidity sensor, so it can never appear in a real
        # daily_context. See models/anomaly_model/README.md.
        assert "Turbidite" not in detector.feature_cols
        assert "Turbidite_diff" not in detector.feature_cols

    def test_evaluate_without_daily_context_skips_combination_layer(self, detector):
        result = detector.evaluate(
            snapshot={"pH": 9.8, "EC": 16.2, "DO_mgL": 7.1, "Temperature": 36.5, "Luminosite": 18000.0},
            hour_of_day=14.0,
            daily_context=None,
        )
        assert result["combination_model"] is None

    def test_evaluate_clean_snapshot_is_severity_zero(self, detector):
        result = detector.evaluate(
            snapshot={"pH": 9.8, "EC": 16.2, "DO_mgL": 7.1, "Temperature": 36.5, "Luminosite": 18000.0},
            hour_of_day=14.0,
        )
        assert result["overall_severity"] == 0

    def test_evaluate_ph_crash_is_severity_three(self, detector):
        result = detector.evaluate(
            snapshot={"pH": 7.0, "EC": 16.2, "DO_mgL": 7.1, "Temperature": 36.5, "Luminosite": 18000.0},
            hour_of_day=14.0,
        )
        assert result["overall_severity"] == 3

    def test_evaluate_daily_context_missing_feature_skips_layer(self, detector):
        # daily_context that doesn't supply every feature_cols entry ->
        # the detector must skip the layer (return None), not raise.
        result = detector.evaluate(
            snapshot={"pH": 9.8, "EC": 16.2, "DO_mgL": 7.1, "Temperature": 36.5, "Luminosite": 18000.0},
            hour_of_day=14.0,
            daily_context={"pH": 9.8},  # incomplete on purpose
        )
        assert result["combination_model"] is None

    def test_evaluate_complete_daily_context_scores_combination_layer(self, detector):
        daily_context = {
            "pH": 9.8, "EC": 16.2, "DO_mgL": 7.1,
            "Temperature_mean": 36.5, "Temperature_min": 34.0, "Temperature_max": 39.0,
            "Luminosite_mean": 18000.0, "Luminosite_min": 5000.0, "Luminosite_max": 30000.0,
            "pH_diff": 0.0, "EC_diff": 0.0, "DO_mgL_diff": 0.0,
        }
        result = detector.evaluate(
            snapshot={"pH": 9.8, "EC": 16.2, "DO_mgL": 7.1, "Temperature": 36.5, "Luminosite": 18000.0},
            hour_of_day=14.0,
            daily_context=daily_context,
        )
        assert result["combination_model"] is not None
        assert "anomaly" in result["combination_model"]
        assert "score" in result["combination_model"]
