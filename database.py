"""
Smart Classroom Monitor – Database Module
==========================================
SQLite database operations for sensor readings, alerts, events, and settings.
Thread-safe: each call creates its own connection.
"""

import sqlite3
import threading
import logging
import json
from datetime import datetime, timezone

import config

log = logging.getLogger(__name__)

_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def _get_conn():
    """Return a new SQLite connection with row-factory enabled."""
    conn = sqlite3.connect(config.DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_db():
    """Create tables and seed default settings if they don't exist."""
    conn = _get_conn()
    try:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                temperature REAL,
                humidity    REAL,
                light       TEXT,
                light_raw   INTEGER,
                distance    REAL,
                pir1        INTEGER,
                pir2        INTEGER,
                source      TEXT    DEFAULT 'demo',
                created_at  TEXT    DEFAULT (datetime('now'))
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                description TEXT    NOT NULL,
                severity    TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL,
                sensor      TEXT,
                status      TEXT    DEFAULT 'active',
                resolved_at TEXT,
                source      TEXT    DEFAULT 'demo'
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                event       TEXT    NOT NULL,
                sensor      TEXT,
                reading     TEXT,
                source      TEXT    DEFAULT 'demo'
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Create indexes for common queries
        cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_ts ON sensor_readings(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_readings_source ON sensor_readings(source)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp)")

        # Seed default settings
        for key, val in config.DEFAULT_SETTINGS.items():
            cur.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(val)),
            )

        conn.commit()
        log.info("Database initialised at %s", config.DATABASE_PATH)
    except Exception:
        log.exception("Failed to initialise database")
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sensor readings
# ---------------------------------------------------------------------------

def save_reading(data: dict, source: str = "demo"):
    """Insert a single sensor reading row."""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO sensor_readings
               (timestamp, temperature, humidity, light, light_raw,
                distance, pir1, pir2, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                data.get("temperature"),
                data.get("humidity"),
                data.get("light"),
                data.get("light_raw"),
                data.get("distance"),
                int(data["pir1"]) if data.get("pir1") is not None else None,
                int(data["pir2"]) if data.get("pir2") is not None else None,
                source,
            ),
        )
        conn.commit()
    except Exception:
        log.exception("Failed to save reading")
    finally:
        conn.close()


def save_readings_batch(readings: list[dict], source: str = "demo"):
    """Insert multiple sensor readings in a single fast transaction."""
    if not readings:
        return
    conn = _get_conn()
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                r.get("timestamp", now_iso),
                r.get("temperature"),
                r.get("humidity"),
                r.get("light"),
                r.get("light_raw"),
                r.get("distance"),
                int(r["pir1"]) if r.get("pir1") is not None else None,
                int(r["pir2"]) if r.get("pir2") is not None else None,
                source,
            )
            for r in readings
        ]
        conn.executemany(
            """INSERT INTO sensor_readings
               (timestamp, temperature, humidity, light, light_raw,
                distance, pir1, pir2, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
    except Exception:
        log.exception("Failed to save batch readings")
    finally:
        conn.close()


def get_latest_reading(source: str | None = None) -> dict | None:
    """Return the most recent sensor reading, optionally filtered by source."""
    conn = _get_conn()
    try:
        if source:
            row = conn.execute(
                "SELECT * FROM sensor_readings WHERE source=? ORDER BY timestamp DESC LIMIT 1",
                (source,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM sensor_readings ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_history(
    sensor: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 500,
    offset: int = 0,
    source: str | None = None,
) -> list[dict]:
    """Return historical readings with optional filters and pagination."""
    conn = _get_conn()
    try:
        clauses, params = [], []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if start:
            clauses.append("timestamp >= ?")
            params.append(start)
        if end:
            clauses.append("timestamp <= ?")
            params.append(end)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        if sensor and sensor in (
            "temperature", "humidity", "light", "light_raw",
            "distance", "pir1", "pir2",
        ):
            cols = f"id, timestamp, {sensor}, source"
        else:
            cols = "*"

        sql = f"SELECT {cols} FROM sensor_readings {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_readings_count(
    sensor: str | None = None,
    start: str | None = None,
    end: str | None = None,
    source: str | None = None,
) -> int:
    """Count readings matching the given filters."""
    conn = _get_conn()
    try:
        clauses, params = [], []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if start:
            clauses.append("timestamp >= ?")
            params.append(start)
        if end:
            clauses.append("timestamp <= ?")
            params.append(end)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM sensor_readings {where}", params
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def save_alert(
    title: str,
    description: str,
    severity: str,
    sensor: str | None = None,
    source: str = "demo",
) -> int:
    """Insert an alert and return its id."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO alerts (title, description, severity, timestamp, sensor, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, description, severity,
             datetime.now(timezone.utc).isoformat(), sensor, source),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_alerts(status: str | None = None, limit: int = 50) -> list[dict]:
    """Return alerts, newest first."""
    conn = _get_conn()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE status=? ORDER BY timestamp DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resolve_alert(alert_id: int) -> bool:
    """Mark an alert as resolved."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE alerts SET status='resolved', resolved_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), alert_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def save_event(
    event: str,
    sensor: str | None = None,
    reading: str | None = None,
    source: str = "demo",
):
    """Log a system event."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO events (timestamp, event, sensor, reading, source) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), event, sensor, reading, source),
        )
        conn.commit()
    except Exception:
        log.exception("Failed to save event")
    finally:
        conn.close()


def get_events(limit: int = 50) -> list[dict]:
    """Return recent events, newest first."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_settings() -> dict:
    """Return all settings as a plain dict (values are JSON-decoded)."""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                result[r["key"]] = r["value"]
        return result
    finally:
        conn.close()


def get_setting(key: str):
    """Return a single setting value (JSON-decoded) or None."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            return config.DEFAULT_SETTINGS.get(key)
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]
    finally:
        conn.close()


def update_settings(settings_dict: dict):
    """Upsert multiple settings."""
    conn = _get_conn()
    try:
        for key, val in settings_dict.items():
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(val)),
            )
        conn.commit()
    except Exception:
        log.exception("Failed to update settings")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

def clear_demo_data():
    """Delete all demo-sourced readings, alerts, and events."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM sensor_readings WHERE source='demo'")
        conn.execute("DELETE FROM alerts WHERE source='demo'")
        conn.execute("DELETE FROM events WHERE source='demo'")
        conn.commit()
        log.info("Demo data cleared")
    except Exception:
        log.exception("Failed to clear demo data")
    finally:
        conn.close()

