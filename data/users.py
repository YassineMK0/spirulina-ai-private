"""User management store for SpirulinaAI — PostgreSQL-backed with in-memory fallback."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

_DATABASE_URL = os.getenv("DATABASE_URL", "")

_USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id             TEXT        PRIMARY KEY,
    email          TEXT        UNIQUE NOT NULL,
    password_hash  TEXT        NOT NULL,
    tier           TEXT        NOT NULL DEFAULT 'free'
                   CHECK (tier IN ('free', 'pro', 'admin')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
"""


# ---------------------------------------------------------------------------
# PostgreSQL implementation
# ---------------------------------------------------------------------------

class PostgresUserStore:
    def __init__(self, database_url: str) -> None:
        from psycopg2 import pool as pg_pool
        self._pool = pg_pool.ThreadedConnectionPool(minconn=1, maxconn=5, dsn=database_url)
        self._apply_schema()

    def _conn(self):
        return self._pool.getconn()

    def _release(self, conn) -> None:
        self._pool.putconn(conn)

    def _apply_schema(self) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_USERS_DDL)
            conn.commit()
            print("[users] PostgreSQL schema ready")
        finally:
            self._release(conn)

    def has_any_user(self) -> bool:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM users LIMIT 1")
                return cur.fetchone() is not None
        finally:
            self._release(conn)

    def create_user(self, email: str, password_hash: str, tier: str = "free") -> str:
        uid = str(uuid.uuid4())
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (id, email, password_hash, tier) VALUES (%s, %s, %s, %s)",
                    (uid, email.lower().strip(), password_hash, tier),
                )
            conn.commit()
        finally:
            self._release(conn)
        return uid

    def get_by_email(self, email: str) -> dict | None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, email, password_hash, tier, created_at FROM users WHERE email = %s",
                    (email.lower().strip(),),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "id":            row[0],
                    "email":         row[1],
                    "password_hash": row[2],
                    "tier":          row[3],
                    "created_at":    row[4].isoformat() if row[4] else "",
                }
        finally:
            self._release(conn)

    def get_by_id(self, user_id: str) -> dict | None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, email, password_hash, tier, created_at FROM users WHERE id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "id":            row[0],
                    "email":         row[1],
                    "password_hash": row[2],
                    "tier":          row[3],
                    "created_at":    row[4].isoformat() if row[4] else "",
                }
        finally:
            self._release(conn)

    def list_users(self) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT u.id, u.email, u.tier, u.created_at,
                           COALESCE(COUNT(m.id) FILTER (WHERE m.role = 'user'), 0)::int AS msg_count
                    FROM users u
                    LEFT JOIN conversations c ON c.user_id = u.id
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    GROUP BY u.id
                    ORDER BY u.created_at DESC
                """)
                return [
                    {
                        "id":            r[0],
                        "email":         r[1],
                        "tier":          r[2],
                        "created_at":    r[3].isoformat() if r[3] else "",
                        "message_count": r[4],
                    }
                    for r in cur.fetchall()
                ]
        finally:
            self._release(conn)

    def delete_user(self, user_id: str) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # Conversations cascade-delete their messages, so just delete convs then user
                cur.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
        finally:
            self._release(conn)

    def update_tier(self, user_id: str, tier: str) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET tier = %s WHERE id = %s", (tier, user_id))
            conn.commit()
        finally:
            self._release(conn)

    def update_password(self, user_id: str, password_hash: str) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
            conn.commit()
        finally:
            self._release(conn)

    def count_messages(self, user_id: str) -> int:
        """Total user-sent messages across all conversations (for free-tier limit)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(m.id) FROM messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    WHERE c.user_id = %s AND m.role = 'user'
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
        finally:
            self._release(conn)


# ---------------------------------------------------------------------------
# In-memory fallback
# ---------------------------------------------------------------------------

class InMemoryUserStore:
    def __init__(self) -> None:
        self._users: dict[str, dict] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def has_any_user(self) -> bool:
        return bool(self._users)

    def create_user(self, email: str, password_hash: str, tier: str = "free") -> str:
        uid = str(uuid.uuid4())
        self._users[uid] = {
            "id": uid, "email": email.lower().strip(),
            "password_hash": password_hash, "tier": tier, "created_at": self._now(),
        }
        return uid

    def get_by_email(self, email: str) -> dict | None:
        e = email.lower().strip()
        return next((u for u in self._users.values() if u["email"] == e), None)

    def get_by_id(self, user_id: str) -> dict | None:
        return self._users.get(user_id)

    def list_users(self) -> list[dict]:
        return sorted(self._users.values(), key=lambda u: u["created_at"], reverse=True)

    def delete_user(self, user_id: str) -> None:
        self._users.pop(user_id, None)

    def update_tier(self, user_id: str, tier: str) -> None:
        if user_id in self._users:
            self._users[user_id]["tier"] = tier

    def update_password(self, user_id: str, password_hash: str) -> None:
        if user_id in self._users:
            self._users[user_id]["password_hash"] = password_hash

    def count_messages(self, user_id: str) -> int:
        return 0  # no cross-store integration; limit not enforced without PG


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _build_store():
    if _DATABASE_URL:
        try:
            return PostgresUserStore(_DATABASE_URL)
        except Exception as exc:
            print(f"[users] PostgreSQL unavailable ({exc}) — using in-memory fallback")
    return InMemoryUserStore()


user_store = _build_store()
