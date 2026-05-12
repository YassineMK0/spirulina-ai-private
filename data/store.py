"""SQLite sensor store — local S3 simulation.

Every MQTT reading is persisted here.  The ML pipeline calls get_latest()
to fetch the last N readings for a container, oldest-first — exactly what
M2 and M3 feature engineering expects (min 5 rows for M2, 6 for M3).

Schema
------
sensor_readings
    id            INTEGER  PK autoincrement
    container_id  TEXT     indexed
    ts            TEXT     ISO-8601 UTC  (indexed)
    pH            REAL
    EC            REAL     µS/cm
    DO            REAL     mg/L
    temperature   REAL     °C
    luminosity    REAL     lux
    turbidity     REAL     NTU
    status        TEXT     ok | warning | error

Usage
-----
    from data.store import sensor_store

    sensor_store.push("container-01", reading_dict)
    rows = sensor_store.get_latest("container-01", n=6)
    # rows → list[dict], oldest first, keys: date, pH, EC, DO, temperature, luminosity, turbidity
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

DB_PATH = Path(__file__).parent / "processed" / "sensors.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sensor_readings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    container_id TEXT    NOT NULL,
    ts           TEXT    NOT NULL,
    pH           REAL,
    EC           REAL,
    DO           REAL,
    temperature  REAL,
    luminosity   REAL,
    turbidity    REAL,
    status       TEXT    DEFAULT 'ok'
);
CREATE INDEX IF NOT EXISTS idx_cid_ts ON sensor_readings (container_id, ts);
"""


class SensorStore:
    """Thread-safe SQLite-backed sensor reading store."""

    def __init__(self, path: Path = DB_PATH) -> None:
        self._path = path
        self._lock = Lock()
        self._init_db()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def push(self, container_id: str, reading: dict[str, Any]) -> None:
        """Persist one MQTT reading for container_id."""
        ts = reading.get("timestamp") or datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sensor_readings
                    (container_id, ts, pH, EC, DO, temperature, luminosity, turbidity, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    container_id,
                    ts,
                    reading.get("pH"),
                    reading.get("EC"),
                    reading.get("DO"),
                    reading.get("temperature"),
                    reading.get("luminosity"),
                    reading.get("turbidity"),
                    reading.get("status", "ok"),
                ),
            )
            self._conn.commit()

    def get_latest(self, container_id: str, n: int = 6) -> list[dict[str, Any]]:
        """Return the n most recent readings for container_id, oldest first.

        Returns rows with keys: date, pH, EC, DO, temperature, luminosity, turbidity.
        These match the column names expected by feature_engineering_M2 and M3.
        """
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT ts, pH, EC, DO, temperature, luminosity, turbidity
                FROM (
                    SELECT ts, pH, EC, DO, temperature, luminosity, turbidity
                    FROM sensor_readings
                    WHERE container_id = ?
                    ORDER BY ts DESC
                    LIMIT ?
                )
                ORDER BY ts ASC
                """,
                (container_id, n),
            )
            rows = cur.fetchall()

        return [
            {
                "date":        r[0],
                "pH":          r[1],
                "EC":          r[2],
                "DO":          r[3],
                "temperature": r[4],
                "luminosity":  r[5],
                "turbidity":   r[6],
            }
            for r in rows
            if None not in (r[1], r[2], r[3], r[4], r[5], r[6])
        ]

    def count(self, container_id: str) -> int:
        """Return total number of stored readings for a container."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM sensor_readings WHERE container_id = ?",
                (container_id,),
            )
            return cur.fetchone()[0]

    def clear(self, container_id: str) -> None:
        """Delete all readings for a container (useful for tests)."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM sensor_readings WHERE container_id = ?",
                (container_id,),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()


# Module-level singleton
sensor_store = SensorStore()
