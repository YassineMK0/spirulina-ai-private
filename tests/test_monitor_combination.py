"""Tests for the 24h combination-model cron wiring added this session:
agent.monitor._build_daily_context, agent.monitor.run_combination_model_check,
and data.store.SensorStore.get_since.

Uses the real sqlite-backed sensor_store singleton with unique throwaway
container IDs (cleaned up via sensor_store.clear() in a fixture) rather than
mocking the DB layer -- these are genuinely integration tests for the cron
job's data path, not pure unit tests.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

import agent.monitor as monitor
from agent.sensors import _cache
from data.store import sensor_store


class _SyncThread:
    """Runs the target immediately instead of spawning a real thread, so
    alert-dispatch assertions don't race a fixed sleep() under load (the
    suite-wide run flaked with a 1s sleep when the daemon thread hadn't
    finished yet -- this makes the tests deterministic instead)."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
        self._target, self._args, self._kwargs = target, args, kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def _push_history(container_id: str, hours_back: int = 24, n: int = 13, **overrides):
    """Push n readings spaced evenly over the last `hours_back` hours."""
    now = datetime.now(timezone.utc)
    for i in range(n):
        ts = now - timedelta(hours=hours_back) + timedelta(hours=(hours_back / (n - 1)) * i)
        hour = ts.hour
        row = {
            "timestamp":   ts.isoformat(),
            "pH":          9.8,
            "EC":          16200.0,
            "DO":          7.1,
            "temperature": 36.0 + 2 * ((hour % 24) / 24.0),
            "luminosity":  15000 + 5000 * ((hour % 24) / 24.0),
            "turbidity":   200.0,
            "status":      "ok",
        }
        row.update(overrides if i == 0 else {})
        sensor_store.push(container_id, row)
    return now


@pytest.fixture
def container_id():
    cid = f"__test_{id(object())}__"
    yield cid
    sensor_store.clear(cid)
    _cache.pop(cid, None)
    monitor._active_sessions.pop("test-user", None)
    monitor._last_combination_alerts.pop("test-user", None)


# =============================================================================
# data.store.SensorStore.get_since
# =============================================================================

class TestGetSince:
    def test_excludes_rows_before_since(self, container_id, tmp_path=None):
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=48)
        sensor_store.push(container_id, {"timestamp": old.isoformat(), "pH": 9.0, "temperature": 20.0})
        sensor_store.push(container_id, {"timestamp": now.isoformat(), "pH": 9.8, "temperature": 36.0})

        since = (now - timedelta(hours=24)).isoformat()
        rows = sensor_store.get_since(container_id, since)

        assert len(rows) == 1
        assert rows[0]["pH"] == 9.8

    def test_returns_rows_oldest_first(self, container_id):
        now = datetime.now(timezone.utc)
        for i, ph in enumerate([9.0, 9.5, 9.8]):
            ts = now - timedelta(hours=2 - i)
            sensor_store.push(container_id, {"timestamp": ts.isoformat(), "pH": ph, "temperature": 36.0})

        since = (now - timedelta(hours=24)).isoformat()
        rows = sensor_store.get_since(container_id, since)

        assert [r["pH"] for r in rows] == [9.0, 9.5, 9.8]

    def test_does_not_require_every_column_present(self, container_id):
        # get_latest() drops rows with any null sensor column -- get_since()
        # must not, since daily_context aggregation only needs whichever
        # columns are present (e.g. temperature/luminosity without EC).
        now = datetime.now(timezone.utc)
        sensor_store.push(container_id, {"timestamp": now.isoformat(), "temperature": 36.0})

        since = (now - timedelta(hours=24)).isoformat()
        rows = sensor_store.get_since(container_id, since)

        assert len(rows) == 1
        assert rows[0]["temperature"] == 36.0
        assert rows[0]["pH"] is None


# =============================================================================
# agent.monitor._build_daily_context
# =============================================================================

class TestBuildDailyContext:
    def test_returns_none_with_fewer_than_two_readings(self, container_id):
        sensor_store.push(container_id, {"pH": 9.8, "temperature": 36.0, "luminosity": 18000.0})
        assert monitor._build_daily_context(container_id) is None

    def test_returns_none_with_no_history_at_all(self, container_id):
        assert monitor._build_daily_context(container_id) is None

    def test_builds_expected_keys_with_enough_history(self, container_id):
        _push_history(container_id)
        ctx = monitor._build_daily_context(container_id)

        assert ctx is not None
        expected_keys = {
            "pH", "EC", "DO_mgL",
            "Temperature_mean", "Temperature_min", "Temperature_max",
            "Luminosite_mean", "Luminosite_min", "Luminosite_max",
            "pH_diff", "EC_diff", "DO_mgL_diff",
        }
        assert expected_keys == set(ctx.keys())

    def test_ec_is_normalized_from_uscm_to_mscm(self, container_id):
        # agent stores EC in uS/cm (e.g. 16200); the model needs mS/cm (16.2)
        _push_history(container_id)
        ctx = monitor._build_daily_context(container_id)
        assert ctx["EC"] == pytest.approx(16.2)


# =============================================================================
# agent.monitor.run_combination_model_check
# =============================================================================

class TestRunCombinationModelCheck:
    def _stub_generate_alert_text(self, monkeypatch):
        monkeypatch.setattr(monitor, "generate_alert_text", lambda *a, **k: "STUB ALERT")
        monkeypatch.setattr(threading, "Thread", _SyncThread)

    def test_no_active_sessions_does_nothing(self):
        pushed = []
        monitor.run_combination_model_check(lambda *a: pushed.append(a))
        assert pushed == []

    def test_insufficient_history_skips_silently(self, container_id):
        monitor.register_session("test-user", container_id)
        sensor_store.push(container_id, {"pH": 9.8, "temperature": 36.0, "luminosity": 18000.0})
        _cache[container_id] = {"pH": 9.8, "EC": 16200.0, "DO": 7.1, "temperature": 36.0, "luminosity": 18000.0}

        pushed = []
        monitor.run_combination_model_check(lambda *a: pushed.append(a))
        time.sleep(0.2)
        assert pushed == []

    def test_pushes_alert_on_combination_anomaly(self, container_id, monkeypatch):
        self._stub_generate_alert_text(monkeypatch)
        monitor.register_session("test-user", container_id)

        # Day 0 is a deliberate outlier vs. the rest of the 24h window --
        # mirrors the manually-verified anomalous fixture from the wiring session.
        _push_history(container_id, pH=9.0, EC=28000.0, DO=18.0)
        _cache[container_id] = {
            "pH": 9.8, "EC": 16200.0, "DO": 7.1, "temperature": 37.0, "luminosity": 18000.0,
            "turbidity": 200.0, "status": "ok",
        }

        pushed = []
        monitor.run_combination_model_check(lambda *a: pushed.append(a))

        assert len(pushed) == 1
        uid, text, sev, affected, source, created_at, detail = pushed[0]
        assert sev == "warning"
        assert affected == ["combination_model"]
        assert source == "model-24h"
        assert created_at  # real detection timestamp, not fabricated client-side
        assert detail.startswith("combination_model:")  # coarse score signature for frontend dedup

    def test_dedup_skips_repeat_alert_on_same_score(self, container_id, monkeypatch):
        self._stub_generate_alert_text(monkeypatch)
        monitor.register_session("test-user", container_id)
        _push_history(container_id, pH=9.0, EC=28000.0, DO=18.0)
        _cache[container_id] = {
            "pH": 9.8, "EC": 16200.0, "DO": 7.1, "temperature": 37.0, "luminosity": 18000.0,
            "turbidity": 200.0, "status": "ok",
        }

        pushed = []
        monitor.run_combination_model_check(lambda *a: pushed.append(a))
        monitor.run_combination_model_check(lambda *a: pushed.append(a))

        assert len(pushed) == 1  # second call deduped, no new push
