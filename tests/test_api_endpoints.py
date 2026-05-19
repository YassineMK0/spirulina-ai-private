"""Integration tests for FastAPI endpoints using TestClient.

All heavy startup side-effects (MQTT, scheduler, model loading) are bypassed
by replacing the lifespan with a no-op. Each test patches dependencies at
their source module rather than api.main, because the route handlers use
local imports (e.g. `from agent.memory import memory_store` inside the fn).
"""
import pytest
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ── App fixture ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan replaced by a no-op (no MQTT, no scheduler)."""
    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    from api.main import app
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app) as c:
        yield c


# ── /health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_200(self, client):
        assert client.get("/health").status_code == 200

    def test_returns_ok_status(self, client):
        assert client.get("/health").json() == {"status": "ok"}


# ── POST /chat ─────────────────────────────────────────────────────────────────

class TestChat:
    def _graph_result(self):
        return {
            "response": "The optimal pH for spirulina is 9.5-10.5.",
            "content": {"type": "text", "text": "The optimal pH for spirulina is 9.5-10.5."},
            "tools_used": ["RAG retrieval"],
            "intent": "KNOWLEDGE",
            "confidence": 0.92,
        }

    def _patches(self, graph_invoke=None):
        """Return a tuple of patches needed for /chat tests."""
        mock_store = MagicMock()
        mock_store.get.return_value = []
        mock_store.save.return_value = None
        invoke = graph_invoke or (lambda state: self._graph_result())
        mock_graph = MagicMock()
        mock_graph.invoke = invoke
        return mock_store, mock_graph

    def test_returns_200_with_valid_payload(self, client):
        mock_store, mock_graph = self._patches()
        with (
            patch("api.main._get_graph", return_value=mock_graph),
            patch("agent.memory.memory_store", mock_store),
            patch("agent.monitor.register_session"),
        ):
            res = client.post("/chat", json={"message": "What is optimal pH?"})
        assert res.status_code == 200

    def test_response_contains_expected_fields(self, client):
        mock_store, mock_graph = self._patches()
        with (
            patch("api.main._get_graph", return_value=mock_graph),
            patch("agent.memory.memory_store", mock_store),
            patch("agent.monitor.register_session"),
        ):
            body = client.post("/chat", json={"message": "What is optimal pH?"}).json()
        for field in ("response", "content", "tools_used", "intent", "confidence"):
            assert field in body

    def test_response_text_matches_graph_output(self, client):
        mock_store, mock_graph = self._patches()
        with (
            patch("api.main._get_graph", return_value=mock_graph),
            patch("agent.memory.memory_store", mock_store),
            patch("agent.monitor.register_session"),
        ):
            body = client.post("/chat", json={"message": "What is optimal pH?"}).json()
        assert "9.5" in body["response"]

    def test_default_tier_is_free(self, client):
        captured = {}
        def capture_invoke(state):
            captured["tier"] = state.get("tier")
            return self._graph_result()

        mock_store, mock_graph = self._patches(capture_invoke)
        with (
            patch("api.main._get_graph", return_value=mock_graph),
            patch("agent.memory.memory_store", mock_store),
            patch("agent.monitor.register_session"),
        ):
            client.post("/chat", json={"message": "hello"})
        assert captured.get("tier") == "free"

    def test_pro_tier_forwarded_to_graph(self, client):
        captured = {}
        def capture_invoke(state):
            captured["tier"] = state.get("tier")
            return self._graph_result()

        mock_store, mock_graph = self._patches(capture_invoke)
        with (
            patch("api.main._get_graph", return_value=mock_graph),
            patch("agent.memory.memory_store", mock_store),
            patch("agent.monitor.register_session"),
        ):
            client.post("/chat", json={"message": "hello", "tier": "pro"})
        assert captured.get("tier") == "pro"


# ── GET /history/{user_id} ─────────────────────────────────────────────────────

class TestHistory:
    def test_returns_stored_history(self, client):
        stored = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        mock_store = MagicMock()
        mock_store.get.return_value = stored
        with patch("agent.memory.memory_store", mock_store):
            res = client.get("/history/user1")
        assert res.status_code == 200
        assert res.json() == stored

    def test_returns_empty_list_for_new_user(self, client):
        mock_store = MagicMock()
        mock_store.get.return_value = []
        with patch("agent.memory.memory_store", mock_store):
            res = client.get("/history/new_user")
        assert res.status_code == 200
        assert res.json() == []


# ── DELETE /history/{user_id} ─────────────────────────────────────────────────

class TestClearHistory:
    def test_returns_cleared_status(self, client):
        mock_store = MagicMock()
        with patch("agent.memory.memory_store", mock_store):
            res = client.delete("/history/user1")
        assert res.status_code == 200
        assert res.json() == {"status": "cleared"}

    def test_calls_memory_store_clear(self, client):
        mock_store = MagicMock()
        with patch("agent.memory.memory_store", mock_store):
            client.delete("/history/user1")
        mock_store.clear.assert_called_once_with("user1")


# ── GET /sensors/{container_id} ───────────────────────────────────────────────

class TestSensors:
    def _payload(self):
        return {
            "pH": 9.8, "EC": 2100.0, "DO": 7.2,
            "temperature": 33.0, "luminosity": 11000.0, "turbidity": 180.0,
            "timestamp": "2024-01-15T10:00:00", "status": "ok", "source": "mqtt",
        }

    def test_returns_live_sensor_data_from_mqtt_cache(self, client):
        with patch("agent.sensors.get_sensor_reading", return_value=self._payload()):
            res = client.get("/sensors/container-01")
        assert res.status_code == 200
        assert res.json()["pH"] == 9.8

    def test_falls_back_to_db_when_mqtt_cache_empty(self, client):
        db_row = {**self._payload(), "source": "db", "date": "2024-01-15T09:00:00"}
        mock_store = MagicMock()
        mock_store.get_latest.return_value = [db_row]
        with (
            patch("agent.sensors.get_sensor_reading", return_value=None),
            patch("data.store.sensor_store", mock_store),
        ):
            res = client.get("/sensors/container-01")
        assert res.status_code == 200

    def test_returns_empty_dict_when_no_data(self, client):
        mock_store = MagicMock()
        mock_store.get_latest.return_value = []
        with (
            patch("agent.sensors.get_sensor_reading", return_value=None),
            patch("data.store.sensor_store", mock_store),
        ):
            res = client.get("/sensors/unknown-container")
        assert res.status_code == 200
        assert res.json() == {}


# ── GET /models/{container_id} ────────────────────────────────────────────────

class TestModels:
    def _history(self, n=20):
        return [
            {"date": f"2024-01-{i:02d}", "pH": 9.8, "EC": 2100.0, "DO": 7.2,
             "temperature": 33.0, "luminosity": 11000.0, "turbidity": 180.0}
            for i in range(1, n + 1)
        ]

    def test_returns_no_data_when_history_empty(self, client):
        with patch("agent.sensors.get_history", return_value=[]):
            res = client.get("/models/container-01")
        assert res.status_code == 200
        assert res.json().get("error") == "no_data"

    def test_returns_m1_m2_m3_keys_when_history_present(self, client):
        # The endpoint wraps each model in try/except and returns {"error": ...}
        # on failure — so m1/m2/m3 keys are always present even without real artifacts.
        with patch("agent.sensors.get_history", return_value=self._history()):
            res = client.get("/models/container-01")
        assert res.status_code == 200
        body = res.json()
        assert "m1" in body
        assert "m2" in body
        assert "m3" in body
