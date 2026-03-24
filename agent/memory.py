"""Per-user conversation memory store.

Auto-selects backend based on REDIS_URL env var:
  - REDIS_URL set  -> RedisMemoryStore  (persistent, survives restarts)
  - REDIS_URL unset -> InMemoryStore    (process-local, lost on restart)

Usage:
    from agent.memory import memory_store

    history = memory_store.get(user_id)          # list[dict]
    memory_store.save(user_id, updated_history)  # auto-caps at MAX_TURNS
    memory_store.clear(user_id)                  # wipe history
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from threading import Lock

MAX_TURNS  = 10    # keep last N user+assistant pairs (= 2*N messages)
REDIS_TTL  = 60 * 60 * 24 * 7   # 7 days in seconds
REDIS_KEY  = "spirulina:chat:{user_id}"


# ---------------------------------------------------------------------------
# Abstract interface — implement this for Redis / any other backend
# ---------------------------------------------------------------------------

class BaseMemoryStore(ABC):

    @abstractmethod
    def get(self, user_id: str) -> list[dict]:
        """Return the stored chat history for *user_id* (newest-last order)."""

    @abstractmethod
    def save(self, user_id: str, history: list[dict]) -> None:
        """Persist *history* for *user_id*, capped to the last MAX_TURNS turns."""

    @abstractmethod
    def clear(self, user_id: str) -> None:
        """Delete the history for *user_id*."""


# ---------------------------------------------------------------------------
# In-memory implementation (default)
# ---------------------------------------------------------------------------

class InMemoryStore(BaseMemoryStore):
    """Thread-safe dict-backed store.  Data lives only as long as the process."""

    def __init__(self, max_turns: int = MAX_TURNS) -> None:
        self._store: dict[str, list[dict]] = {}
        self._lock  = Lock()
        self._max   = max_turns * 2   # each turn = 1 user msg + 1 assistant msg

    def get(self, user_id: str) -> list[dict]:
        with self._lock:
            return list(self._store.get(user_id, []))

    def save(self, user_id: str, history: list[dict]) -> None:
        # Keep only the most recent messages within the cap
        capped = history[-self._max:] if len(history) > self._max else history
        with self._lock:
            self._store[user_id] = list(capped)

    def clear(self, user_id: str) -> None:
        with self._lock:
            self._store.pop(user_id, None)


# ---------------------------------------------------------------------------
# Redis implementation
# ---------------------------------------------------------------------------

class RedisMemoryStore(BaseMemoryStore):
    """Redis-backed store.  Conversations persist across restarts.

    Requires:  pip install redis
    Env var:   REDIS_URL=redis://localhost:6379  (or Upstash/Railway URL)

    Each user's history is stored as a JSON list under:
        spirulina:chat:<user_id>
    with a 7-day TTL that resets on every save.
    """

    def __init__(self, url: str, max_turns: int = MAX_TURNS, ttl: int = REDIS_TTL) -> None:
        import redis as _redis
        self._client = _redis.from_url(url, decode_responses=True)
        self._max    = max_turns * 2
        self._ttl    = ttl

    def _key(self, user_id: str) -> str:
        return REDIS_KEY.format(user_id=user_id)

    def get(self, user_id: str) -> list[dict]:
        raw = self._client.get(self._key(user_id))
        if not raw:
            return []
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []

    def save(self, user_id: str, history: list[dict]) -> None:
        capped = history[-self._max:] if len(history) > self._max else history
        self._client.setex(self._key(user_id), self._ttl, json.dumps(capped))

    def clear(self, user_id: str) -> None:
        self._client.delete(self._key(user_id))


# ---------------------------------------------------------------------------
# Singleton — auto-selects backend from env
# ---------------------------------------------------------------------------

def _build_store() -> BaseMemoryStore:
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            store = RedisMemoryStore(url=redis_url)
            store._client.ping()   # fail fast if URL is wrong
            print(f"[memory] using Redis store ({redis_url.split('@')[-1]})")
            return store
        except Exception as exc:
            print(f"[memory] Redis unavailable ({exc}) — falling back to InMemory")
    else:
        print("[memory] REDIS_URL not set — using InMemory store")
    return InMemoryStore()


memory_store: BaseMemoryStore = _build_store()
