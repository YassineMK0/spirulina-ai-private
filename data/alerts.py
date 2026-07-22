"""Persistent alert store — saves every fired alert to PostgreSQL."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

_DATABASE_URL = os.getenv("DATABASE_URL", "")

_DDL = """
CREATE TABLE IF NOT EXISTS alerts (
    id           TEXT        PRIMARY KEY,
    user_id      TEXT        NOT NULL,
    container_id TEXT        NOT NULL,
    message      TEXT        NOT NULL,
    severity     TEXT        NOT NULL DEFAULT 'warning',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- source/affected classify each alert (which detector fired, which sensors)
-- for the per-user alert history -- added after the initial table, so these
-- are migrated in with ADD COLUMN IF NOT EXISTS rather than the CREATE above.
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS source   TEXT NOT NULL DEFAULT 'rule';
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS affected TEXT;
CREATE INDEX IF NOT EXISTS idx_alerts_container
    ON alerts (container_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_user
    ON alerts (user_id, created_at DESC);
"""


# ---------------------------------------------------------------------------
# PostgreSQL implementation
# ---------------------------------------------------------------------------

class PostgresAlertStore:
    def __init__(self, database_url: str) -> None:
        from psycopg2 import pool as pg_pool
        self._pool = pg_pool.ThreadedConnectionPool(minconn=1, maxconn=5, dsn=database_url)
        self._apply_schema()

    def _conn(self):      return self._pool.getconn()
    def _release(self, c): self._pool.putconn(c)

    def _apply_schema(self) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_DDL)
            conn.commit()
            print("[alerts] PostgreSQL schema ready")
        finally:
            self._release(conn)

    def save(
        self,
        user_id: str,
        container_id: str,
        message: str,
        severity: str = "warning",
        source: str = "rule",
        affected: list[str] | None = None,
        created_at: str | None = None,
    ) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                if created_at:
                    cur.execute(
                        "INSERT INTO alerts (id, user_id, container_id, message, severity, source, affected, created_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (str(uuid.uuid4()), user_id, container_id, message, severity,
                         source, json.dumps(affected or []), created_at),
                    )
                else:
                    cur.execute(
                        "INSERT INTO alerts (id, user_id, container_id, message, severity, source, affected) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (str(uuid.uuid4()), user_id, container_id, message, severity,
                         source, json.dumps(affected or [])),
                    )
            conn.commit()
        finally:
            self._release(conn)

    @staticmethod
    def _row_to_dict(r) -> dict:
        try:
            affected = json.loads(r[6]) if r[6] else []
        except (TypeError, ValueError):
            affected = []
        return {
            "id":           r[0],
            "user_id":      r[1],
            "container_id": r[2],
            "message":      r[3],
            "severity":     r[4],
            "created_at":   r[5].isoformat() if r[5] else "",
            "affected":     affected,
            "source":       r[7],
        }

    def get_recent(self, container_id: str, limit: int = 10) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, container_id, message, severity, created_at, affected, source
                    FROM alerts
                    WHERE container_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (container_id, limit),
                )
                return [self._row_to_dict(r) for r in cur.fetchall()]
        finally:
            self._release(conn)

    def get_recent_for_user(self, user_id: str, limit: int = 10) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, container_id, message, severity, created_at, affected, source
                    FROM alerts
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                return [self._row_to_dict(r) for r in cur.fetchall()]
        finally:
            self._release(conn)


# ---------------------------------------------------------------------------
# In-memory fallback
# ---------------------------------------------------------------------------

class InMemoryAlertStore:
    def __init__(self) -> None:
        self._alerts: list[dict] = []

    def save(
        self,
        user_id: str,
        container_id: str,
        message: str,
        severity: str = "warning",
        source: str = "rule",
        affected: list[str] | None = None,
        created_at: str | None = None,
    ) -> None:
        self._alerts.append({
            "id":           str(uuid.uuid4()),
            "user_id":      user_id,
            "container_id": container_id,
            "message":      message,
            "severity":     severity,
            "source":       source,
            "affected":     affected or [],
            "created_at":   created_at or datetime.now(timezone.utc).isoformat(),
        })
        self._alerts = self._alerts[-200:]  # keep last 200

    def get_recent(self, container_id: str, limit: int = 10) -> list[dict]:
        return [a for a in reversed(self._alerts) if a["container_id"] == container_id][:limit]

    def get_recent_for_user(self, user_id: str, limit: int = 10) -> list[dict]:
        return [a for a in reversed(self._alerts) if a["user_id"] == user_id][:limit]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _build_store():
    if _DATABASE_URL:
        try:
            return PostgresAlertStore(_DATABASE_URL)
        except Exception as exc:
            print(f"[alerts] PostgreSQL unavailable ({exc}) — using in-memory fallback")
    return InMemoryAlertStore()


alert_store = _build_store()
