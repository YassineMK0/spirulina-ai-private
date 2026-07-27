"""Integration tests for FastAPI endpoints using TestClient.

All heavy startup side-effects (MQTT, scheduler, model loading) are bypassed
by replacing the lifespan with a no-op. Each test patches dependencies at
their source module rather than api.main, because the route handlers use
local imports (e.g. `from agent.memory import memory_store` inside the fn).
"""
import pytest
from contextlib import asynccontextmanager, ExitStack
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ── App fixture ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan replaced by a no-op (no MQTT, no scheduler).

    All protected routes now depend on api.auth.require_auth. Overriding it
    here (rather than crafting real JWTs per test) authenticates every
    request as user "user1" — matching the user_id already used throughout
    this file's conversation/chat tests — while still letting individual
    tests override it again to check the 401/403 paths explicitly."""
    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    from api.main import app
    from api.auth import require_auth
    app.router.lifespan_context = _noop_lifespan
    app.dependency_overrides[require_auth] = lambda: {"sub": "user1", "email": "user1@test.com", "tier": "free"}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


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
        """Return the mocks needed for /chat tests.

        user_store and conversation_store are real sqlite-backed singletons
        in production -- must be mocked here, not just agent.memory, or
        tests silently accumulate real rows (and eventually trip the
        free-tier message cap) in the project's actual databases."""
        mock_memory = MagicMock()
        mock_memory.get.return_value = []
        mock_memory.save.return_value = None

        mock_user_store = MagicMock()
        mock_user_store.get_by_id.return_value = None       # falls back to req.tier
        mock_user_store.count_messages.return_value = 0

        mock_conv_store = MagicMock()
        mock_conv_store.conversation_exists.return_value = False
        mock_conv_store.create_conversation.return_value = "conv-1"
        mock_conv_store.get_messages.return_value = []

        invoke = graph_invoke or (lambda state: self._graph_result())
        mock_graph = MagicMock()
        mock_graph.invoke = invoke
        return mock_memory, mock_user_store, mock_conv_store, mock_graph

    def _chat_patches(self, mock_graph, mock_user_store, mock_conv_store, mock_memory):
        stack = ExitStack()
        stack.enter_context(patch("api.main._get_graph", return_value=mock_graph))
        stack.enter_context(patch("agent.memory.memory_store", mock_memory))
        stack.enter_context(patch("agent.monitor.register_session"))
        stack.enter_context(patch("data.users.user_store", mock_user_store))
        stack.enter_context(patch("data.conversations.conversation_store", mock_conv_store))
        return stack

    def test_returns_200_with_valid_payload(self, client):
        mock_memory, mock_user_store, mock_conv_store, mock_graph = self._patches()
        with self._chat_patches(mock_graph, mock_user_store, mock_conv_store, mock_memory):
            res = client.post("/chat", json={"message": "What is optimal pH?"})
        assert res.status_code == 200

    def test_response_contains_expected_fields(self, client):
        mock_memory, mock_user_store, mock_conv_store, mock_graph = self._patches()
        with self._chat_patches(mock_graph, mock_user_store, mock_conv_store, mock_memory):
            body = client.post("/chat", json={"message": "What is optimal pH?"}).json()
        for field in ("response", "content", "tools_used", "intent", "confidence"):
            assert field in body

    def test_response_text_matches_graph_output(self, client):
        mock_memory, mock_user_store, mock_conv_store, mock_graph = self._patches()
        with self._chat_patches(mock_graph, mock_user_store, mock_conv_store, mock_memory):
            body = client.post("/chat", json={"message": "What is optimal pH?"}).json()
        assert "9.5" in body["response"]

    def test_default_tier_is_free(self, client):
        captured = {}
        def capture_invoke(state):
            captured["tier"] = state.get("tier")
            return self._graph_result()

        mock_memory, mock_user_store, mock_conv_store, mock_graph = self._patches(capture_invoke)
        with self._chat_patches(mock_graph, mock_user_store, mock_conv_store, mock_memory):
            client.post("/chat", json={"message": "hello"})
        assert captured.get("tier") == "free"

    def test_pro_tier_forwarded_to_graph(self, client):
        captured = {}
        def capture_invoke(state):
            captured["tier"] = state.get("tier")
            return self._graph_result()

        mock_memory, mock_user_store, mock_conv_store, mock_graph = self._patches(capture_invoke)
        with self._chat_patches(mock_graph, mock_user_store, mock_conv_store, mock_memory):
            client.post("/chat", json={"message": "hello", "tier": "pro"})
        assert captured.get("tier") == "pro"


# ── Conversation CRUD (/conversations/{user_id}[/{conv_id}]) ──────────────────
# Replaced the old /history/{user_id} endpoint -- conversations are now the
# unit of persisted chat history, not a single flat per-user history.

class TestConversations:
    def test_list_returns_stored_conversations(self, client):
        stored = [{"id": "c1", "title": "pH question"}]
        mock_store = MagicMock()
        mock_store.list_conversations.return_value = stored
        with patch("data.conversations.conversation_store", mock_store):
            res = client.get("/conversations/user1")
        assert res.status_code == 200
        assert res.json() == stored

    def test_create_returns_id_and_title(self, client):
        mock_store = MagicMock()
        mock_store.create_conversation.return_value = "new-conv-id"
        with patch("data.conversations.conversation_store", mock_store):
            res = client.post("/conversations/user1", json={"title": "My chat"})
        assert res.status_code == 201
        assert res.json() == {"id": "new-conv-id", "title": "My chat"}

    def test_get_messages_returns_404_when_missing(self, client):
        mock_store = MagicMock()
        mock_store.conversation_exists.return_value = False
        with patch("data.conversations.conversation_store", mock_store):
            res = client.get("/conversations/user1/missing-conv")
        assert res.status_code == 404

    def test_get_messages_returns_stored_messages(self, client):
        stored = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        mock_store = MagicMock()
        mock_store.conversation_exists.return_value = True
        mock_store.get_messages.return_value = stored
        with patch("data.conversations.conversation_store", mock_store):
            res = client.get("/conversations/user1/conv1")
        assert res.status_code == 200
        assert res.json() == stored

    def test_delete_calls_store_and_returns_status(self, client):
        mock_store = MagicMock()
        with patch("data.conversations.conversation_store", mock_store):
            res = client.delete("/conversations/user1/conv1")
        assert res.status_code == 200
        assert res.json() == {"status": "deleted"}
        mock_store.delete_conversation.assert_called_once_with("conv1")

    def test_rename_calls_store_and_returns_title(self, client):
        mock_store = MagicMock()
        with patch("data.conversations.conversation_store", mock_store):
            res = client.patch("/conversations/user1/conv1/title", json={"title": "New title"})
        assert res.status_code == 200
        assert res.json() == {"status": "updated", "title": "New title"}
        mock_store.update_title.assert_called_once_with("conv1", "New title")


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
    # The only ML model now is M1 (rule engine + seasonal check, see
    # models/anomaly_model). The endpoint just wraps
    # agent.monitor._run_ml_prediction's output under an "m1" key.

    def test_returns_no_data_when_prediction_empty(self, client):
        with patch("agent.monitor._run_ml_prediction", return_value={}):
            res = client.get("/models/container-01")
        assert res.status_code == 200
        assert res.json().get("error") == "no_data"

    def test_returns_m1_key_with_anomaly_detector_output(self, client):
        ml = {"anomaly": False, "severity": None, "rule_findings": [], "seasonal": {}}
        with patch("agent.monitor._run_ml_prediction", return_value=ml):
            res = client.get("/models/container-01")
        assert res.status_code == 200
        assert res.json()["m1"] == ml


# ── Auth enforcement ─────────────────────────────────────────────────────────
# Regression tests for the 2026-07-27 fix: require_auth/require_admin were
# defined in api/auth.py but never wired into api/main.py's routes, so any
# caller could read/write any user's data by just naming a user_id. The
# `client` fixture overrides require_auth to always succeed as "user1" (so
# every other test above stays green); these tests remove that override for
# one request at a time to prove the real dependency is actually in effect.

class TestAuthEnforcement:
    def test_chat_requires_auth(self, client):
        from api.main import app
        from api.auth import require_auth
        saved = app.dependency_overrides.pop(require_auth)
        try:
            res = client.post("/chat", json={"message": "hi"})
        finally:
            app.dependency_overrides[require_auth] = saved
        assert res.status_code == 401

    def test_conversations_rejects_unauthenticated(self, client):
        from api.main import app
        from api.auth import require_auth
        saved = app.dependency_overrides.pop(require_auth)
        try:
            res = client.get("/conversations/user1")
        finally:
            app.dependency_overrides[require_auth] = saved
        assert res.status_code == 401

    def test_conversations_rejects_another_users_id(self, client):
        # client fixture authenticates as "user1" -- fetching "user2"'s
        # conversations must be forbidden, not silently served.
        res = client.get("/conversations/user2")
        assert res.status_code == 403

    def test_alert_history_rejects_another_users_id(self, client):
        res = client.get("/alerts/user2/history")
        assert res.status_code == 403

    def test_sensors_requires_auth(self, client):
        from api.main import app
        from api.auth import require_auth
        saved = app.dependency_overrides.pop(require_auth)
        try:
            res = client.get("/sensors/container-01")
        finally:
            app.dependency_overrides[require_auth] = saved
        assert res.status_code == 401

    def test_status_requires_admin_not_just_login(self, client):
        # require_admin decodes the token itself rather than going through a
        # Depends(require_auth) sub-dependency, so it must be overridden
        # separately from require_auth to simulate "logged in, wrong tier".
        from fastapi import HTTPException
        from api.main import app
        from api.auth import require_admin

        def _free_tier_denied():
            raise HTTPException(status_code=403, detail="Admin access required")

        app.dependency_overrides[require_admin] = _free_tier_denied
        try:
            res = client.get("/status")
        finally:
            app.dependency_overrides.pop(require_admin, None)
        assert res.status_code == 403

    def test_debug_endpoint_requires_admin(self, client):
        # No auth override at all here -- confirms the route is locked down
        # by default (401 missing-token, the floor every admin route falls
        # back to) rather than silently open like it was before the fix.
        res = client.post("/debug/run-combination-check/container-01")
        assert res.status_code in (401, 403)
