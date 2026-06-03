"""PostgreSQL-backed conversation store for SpirulinaAI.

Persists conversations and messages exactly like a Claude-web-style chat:
  - Each conversation has an id, title (auto from first message), timestamps
  - Messages are ordered rows with role + content

Falls back to an InMemoryConversationStore if DATABASE_URL is not set,
so the server still starts without PostgreSQL configured.

Usage
-----
    from data.conversations import conversation_store
    conv_id = conversation_store.create_conversation("user-123", "pH dropped to 8.1")
    conversation_store.add_message(conv_id, "user", "My pH dropped...")
    history  = conversation_store.get_messages(conv_id)   # [{role, content}, ...]
    convs    = conversation_store.list_conversations("user-123")
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Optional


_DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# ---------------------------------------------------------------------------
# Schema (applied once on first connection)
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    title       TEXT        NOT NULL DEFAULT 'New conversation',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_user_updated
    ON conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT        PRIMARY KEY,
    conversation_id TEXT        NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user','assistant')),
    content         TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_msg_conv_created
    ON messages (conversation_id, created_at);
"""


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class ConversationStore:
    def create_conversation(self, user_id: str, title: str = "New conversation") -> str:
        raise NotImplementedError

    def list_conversations(self, user_id: str) -> list[dict]:
        raise NotImplementedError

    def get_messages(self, conversation_id: str) -> list[dict]:
        raise NotImplementedError

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        raise NotImplementedError

    def delete_conversation(self, conversation_id: str) -> None:
        raise NotImplementedError

    def update_title(self, conversation_id: str, title: str) -> None:
        raise NotImplementedError

    def conversation_exists(self, conversation_id: str) -> bool:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# PostgreSQL implementation
# ---------------------------------------------------------------------------

class PostgresConversationStore(ConversationStore):

    def __init__(self, database_url: str) -> None:
        import psycopg2
        from psycopg2 import pool as pg_pool

        self._pool = pg_pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=database_url,
        )
        self._apply_schema()

    # ── internal helpers ────────────────────────────────────────────────────

    def _conn(self):
        return self._pool.getconn()

    def _release(self, conn) -> None:
        self._pool.putconn(conn)

    def _apply_schema(self) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_DDL)
            conn.commit()
            print("[conversations] PostgreSQL schema ready")
        finally:
            self._release(conn)

    # ── public API ──────────────────────────────────────────────────────────

    def create_conversation(self, user_id: str, title: str = "New conversation") -> str:
        cid = str(uuid.uuid4())
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO conversations (id, user_id, title) VALUES (%s, %s, %s)",
                    (cid, user_id, title),
                )
            conn.commit()
        finally:
            self._release(conn)
        return cid

    def list_conversations(self, user_id: str) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.id, c.title, c.created_at, c.updated_at,
                           COUNT(m.id)::int AS message_count
                    FROM   conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    WHERE  c.user_id = %s
                    GROUP  BY c.id
                    ORDER  BY c.updated_at DESC
                    """,
                    (user_id,),
                )
                return [
                    {
                        "id":            r[0],
                        "title":         r[1],
                        "created_at":    r[2].isoformat() if r[2] else "",
                        "updated_at":    r[3].isoformat() if r[3] else "",
                        "message_count": r[4],
                    }
                    for r in cur.fetchall()
                ]
        finally:
            self._release(conn)

    def get_messages(self, conversation_id: str) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY created_at",
                    (conversation_id,),
                )
                return [{"role": r[0], "content": r[1]} for r in cur.fetchall()]
        finally:
            self._release(conn)

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        mid = str(uuid.uuid4())
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO messages (id, conversation_id, role, content) VALUES (%s, %s, %s, %s)",
                    (mid, conversation_id, role, content),
                )
                cur.execute(
                    "UPDATE conversations SET updated_at = NOW() WHERE id = %s",
                    (conversation_id,),
                )
            conn.commit()
        finally:
            self._release(conn)

    def delete_conversation(self, conversation_id: str) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
            conn.commit()
        finally:
            self._release(conn)

    def update_title(self, conversation_id: str, title: str) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE conversations SET title = %s, updated_at = NOW() WHERE id = %s",
                    (title, conversation_id),
                )
            conn.commit()
        finally:
            self._release(conn)

    def conversation_exists(self, conversation_id: str) -> bool:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM conversations WHERE id = %s LIMIT 1",
                    (conversation_id,),
                )
                return cur.fetchone() is not None
        finally:
            self._release(conn)


# ---------------------------------------------------------------------------
# In-memory fallback (no PostgreSQL)
# ---------------------------------------------------------------------------

class InMemoryConversationStore(ConversationStore):
    """Process-local store — resets on server restart. Used when DATABASE_URL is unset."""

    def __init__(self) -> None:
        self._conversations: dict[str, dict] = {}
        self._messages: dict[str, list[dict]] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_conversation(self, user_id: str, title: str = "New conversation") -> str:
        cid  = str(uuid.uuid4())
        now  = self._now()
        self._conversations[cid] = {
            "id": cid, "user_id": user_id, "title": title,
            "created_at": now, "updated_at": now,
        }
        self._messages[cid] = []
        return cid

    def list_conversations(self, user_id: str) -> list[dict]:
        return sorted(
            [
                {**c, "message_count": len(self._messages.get(c["id"], []))}
                for c in self._conversations.values()
                if c["user_id"] == user_id
            ],
            key=lambda x: x["updated_at"],
            reverse=True,
        )

    def get_messages(self, conversation_id: str) -> list[dict]:
        return list(self._messages.get(conversation_id, []))

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        if conversation_id not in self._messages:
            self._messages[conversation_id] = []
        self._messages[conversation_id].append({"role": role, "content": content})
        if conversation_id in self._conversations:
            self._conversations[conversation_id]["updated_at"] = self._now()

    def delete_conversation(self, conversation_id: str) -> None:
        self._conversations.pop(conversation_id, None)
        self._messages.pop(conversation_id, None)

    def update_title(self, conversation_id: str, title: str) -> None:
        if conversation_id in self._conversations:
            self._conversations[conversation_id]["title"] = title
            self._conversations[conversation_id]["updated_at"] = self._now()

    def conversation_exists(self, conversation_id: str) -> bool:
        return conversation_id in self._conversations


# ---------------------------------------------------------------------------
# Factory — pick implementation based on env
# ---------------------------------------------------------------------------

def _build_store() -> ConversationStore:
    if _DATABASE_URL:
        try:
            store = PostgresConversationStore(_DATABASE_URL)
            return store
        except Exception as exc:
            print(f"[conversations] PostgreSQL unavailable ({exc}) — using in-memory fallback")
    else:
        print("[conversations] DATABASE_URL not set — using in-memory conversation store")
    return InMemoryConversationStore()


conversation_store: ConversationStore = _build_store()


# ---------------------------------------------------------------------------
# Utility: auto-title from first user message
# ---------------------------------------------------------------------------

def make_title(message: str, max_len: int = 50) -> str:
    """Derive a conversation title from the first user message."""
    text = message.strip()
    # Strip common filler starters
    for prefix in ("can you ", "could you ", "please ", "help me ", "i want to ", "je veux "):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    text = text[:1].upper() + text[1:]  # capitalise first letter
    return text[:max_len].rstrip(" .,;:") + ("…" if len(text) > max_len else "")
