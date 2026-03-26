import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta


class EdgeCache:
    def __init__(
        self,
        room_id="SIT-DR-01",
        db_path=None,
        retention_minutes=60,
        pending_retention_hours=72,
        max_history_rows=5000,
    ):
        self.room_id = room_id
        self.retention_minutes = retention_minutes
        self.pending_retention_hours = pending_retention_hours
        self.max_history_rows = max_history_rows

        base_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        self.db_path = db_path or os.path.join(data_dir, "edge_cache.db")
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS latest_state (
                    room_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS history_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    headcount INTEGER NOT NULL,
                    mmwave_presence INTEGER NOT NULL,
                    occupancy INTEGER NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS recent_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    event TEXT NOT NULL,
                    value TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_updates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_room_time ON history_samples(room_id, timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_room_time ON recent_logs(room_id, timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pending_created ON pending_updates(created_at)"
            )
            conn.commit()

    def save_latest_state(self, status: dict):
        now_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO latest_state (room_id, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(room_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
            """, (
                status.get("room_id", self.room_id),
                json.dumps(status),
                now_iso,
            ))
            conn.commit()

    def get_latest_state(self, room_id=None):
        room_id = room_id or self.room_id
        with self._lock, self._connect() as conn:
            row = conn.execute("""
                SELECT state_json
                FROM latest_state
                WHERE room_id = ?
            """, (room_id,)).fetchone()

        if not row:
            return None

        return json.loads(row["state_json"])

    def add_history_sample(self, status: dict):
        room_id = status.get("room_id", self.room_id)
        timestamp = status.get("timestamp")
        headcount = int(status.get("headcount", 0) or 0)
        mmwave_presence = 1 if bool(status.get("mmwave_presence", False)) else 0
        occupancy = 1 if bool(status.get("occupancy", False)) else 0

        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO history_samples (room_id, timestamp, headcount, mmwave_presence, occupancy)
                VALUES (?, ?, ?, ?, ?)
            """, (room_id, timestamp, headcount, mmwave_presence, occupancy))
            conn.commit()

        self.prune_old_data()

    def get_recent_history(self, room_id=None, limit=12):
        room_id = room_id or self.room_id
        with self._lock, self._connect() as conn:
            rows = conn.execute("""
                SELECT room_id, timestamp, headcount, mmwave_presence, occupancy
                FROM history_samples
                WHERE room_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (room_id, limit)).fetchall()

        return list(reversed([dict(r) for r in rows]))

    def add_change_logs(self, status: dict):
        room_id = status.get("room_id", self.room_id)
        timestamp = status.get("timestamp")
        mmwave_presence = 1 if bool(status.get("mmwave_presence", False)) else 0
        headcount = int(status.get("headcount", 0) or 0)

        mmwave_event = "mmWave presence detected" if mmwave_presence else "mmWave no presence"

        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO recent_logs (room_id, timestamp, source, event, value)
                VALUES (?, ?, ?, ?, ?)
            """, (room_id, timestamp, "mmWave", mmwave_event, str(mmwave_presence)))

            conn.execute("""
                INSERT INTO recent_logs (room_id, timestamp, source, event, value)
                VALUES (?, ?, ?, ?, ?)
            """, (room_id, timestamp, "Camera", "Camera headcount updated", str(headcount)))

            conn.commit()

        self.prune_old_data()

    def get_recent_logs(self, room_id=None, limit=10):
        room_id = room_id or self.room_id
        with self._lock, self._connect() as conn:
            rows = conn.execute("""
                SELECT timestamp, source, event, value
                FROM recent_logs
                WHERE room_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (room_id, limit)).fetchall()

        return [dict(r) for r in rows]

    def enqueue_unsent_update(self, payload: dict):
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO pending_updates (payload_json, created_at)
                VALUES (?, ?)
            """, (
                json.dumps(payload),
                datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            ))
            conn.commit()

    def get_pending_updates(self, limit=20):
        with self._lock, self._connect() as conn:
            rows = conn.execute("""
                SELECT id, payload_json, retry_count
                FROM pending_updates
                ORDER BY id ASC
                LIMIT ?
            """, (limit,)).fetchall()

        return [
            {
                "id": row["id"],
                "payload": json.loads(row["payload_json"]),
                "retry_count": row["retry_count"],
            }
            for row in rows
        ]

    def mark_update_sent(self, update_id: int):
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM pending_updates WHERE id = ?", (update_id,))
            conn.commit()

    def mark_update_failed(self, update_id: int, error: str):
        with self._lock, self._connect() as conn:
            conn.execute("""
                UPDATE pending_updates
                SET retry_count = retry_count + 1,
                    last_error = ?
                WHERE id = ?
            """, (str(error)[:300], update_id))
            conn.commit()

    def pending_count(self):
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM pending_updates").fetchone()
        return int(row["c"])

    def prune_old_data(self):
        history_cutoff = (
            datetime.utcnow() - timedelta(minutes=self.retention_minutes)
        ).replace(microsecond=0).isoformat() + "Z"

        pending_cutoff = (
            datetime.utcnow() - timedelta(hours=self.pending_retention_hours)
        ).replace(microsecond=0).isoformat() + "Z"

        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM history_samples WHERE timestamp < ?", (history_cutoff,))
            conn.execute("DELETE FROM recent_logs WHERE timestamp < ?", (history_cutoff,))
            conn.execute("DELETE FROM pending_updates WHERE created_at < ?", (pending_cutoff,))

            row = conn.execute("SELECT COUNT(*) AS c FROM history_samples").fetchone()
            total = int(row["c"])
            overflow = max(0, total - self.max_history_rows)

            if overflow > 0:
                conn.execute("""
                    DELETE FROM history_samples
                    WHERE id IN (
                        SELECT id
                        FROM history_samples
                        ORDER BY id ASC
                        LIMIT ?
                    )
                """, (overflow,))

            conn.commit()