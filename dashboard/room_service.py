from datetime import datetime, timedelta
import os
import json
import sqlite3

from db import get_db
from utils import (
    utcnow_naive,
    dt_to_sg_str,
    dt_to_sg_hhmm,
    get_occupancy_label,
    is_sensor_occupied,
    MMWAVE_STALE_SECS,
    CAMERA_STALE_SECS,
)
from services import (
    is_booking_active,
    build_room_alerts_for_state,
    build_booking_details_from_doc,
)

LIVE_ROOM_ID = os.getenv("LIVE_ROOM_ID", "SIT-DR-01")
EDGE_CACHE_DB = os.getenv(
    "EDGE_CACHE_DB",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "src", "sensors", "data", "edge_cache.db")
    ),
)


def _coerce_utc_naive_dt(val):
    if val is None:
        return None

    if isinstance(val, datetime):
        return val.replace(tzinfo=None) if val.tzinfo else val

    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None

        try:
            s2 = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s2)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except Exception:
            pass

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                continue

    return None


def _edge_connect():
    if not os.path.exists(EDGE_CACHE_DB):
        return None
    conn = sqlite3.connect(EDGE_CACHE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _edge_get_latest_state(room_id: str):
    conn = _edge_connect()
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT state_json FROM latest_state WHERE room_id = ?",
            (room_id,),
        ).fetchone()
        if not row:
            return None
        return json.loads(row["state_json"])
    except Exception:
        return None
    finally:
        conn.close()


def _edge_get_recent_history(room_id: str, limit=12):
    conn = _edge_connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT timestamp, headcount, mmwave_presence, occupancy
            FROM history_samples
            WHERE room_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (room_id, limit),
        ).fetchall()
        return list(reversed([dict(r) for r in rows]))
    except Exception:
        return []
    finally:
        conn.close()


def _edge_get_recent_logs(room_id: str, limit=10):
    conn = _edge_connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT timestamp, source, event, value
            FROM recent_logs
            WHERE room_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (room_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def get_room_detail_payload(room_id: str):
    now = utcnow_naive()

    db_available = True
    room_cfg = None
    booking_doc = None
    state_doc = {}
    logs = []
    history_docs = []

    try:
        db = get_db()
        room_cfg = db.rooms.find_one({"room_id": room_id}, {"_id": 0})
        booking_doc = db.bookings.find_one({"room_id": room_id}, {"_id": 0})
        state_doc = db.room_state.find_one({"room_id": room_id}, {"_id": 0}) or {}
        logs = list(
            db.event_logs.find({"room_id": room_id}, {"_id": 0})
            .sort("timestamp", -1)
            .limit(10)
        )
        history_docs = list(
            db.sensor_history.find({"room_id": room_id}, {"_id": 0})
            .sort("timestamp", -1)
            .limit(12)
        )
        history_docs.reverse()
    except Exception:
        db_available = False

    # keep original mock-room behavior
    if not room_cfg:
        if room_id == LIVE_ROOM_ID:
            room_cfg = {
                "room_id": LIVE_ROOM_ID,
                "room_name": LIVE_ROOM_ID.replace("-", " "),
                "capacity": 2,
            }
        else:
            return None

    edge_state = _edge_get_latest_state(room_id) if room_id == LIVE_ROOM_ID else None
    edge_history = _edge_get_recent_history(room_id, limit=12) if room_id == LIVE_ROOM_ID else []
    edge_logs = _edge_get_recent_logs(room_id, limit=10) if room_id == LIVE_ROOM_ID else []

    capacity = int(room_cfg.get("capacity", 0) or 0)
    room_name = room_cfg.get("room_name") or room_id.replace("-", " ")

    # Prefer DB state when available; otherwise fall back to local edge cache for the live room
    if state_doc:
        headcount = int(state_doc.get("headcount", 0) or 0)
        mmwave_presence = int(state_doc.get("mmwave_presence", 0) or 0)
        data_source = state_doc.get("data_source", "Mock")
        last_updated_dt = state_doc.get("last_updated") or now
        last_mmwave_dt = state_doc.get("last_mmwave_update")
        last_camera_dt = state_doc.get("last_camera_update")
    elif edge_state:
        headcount = int(edge_state.get("headcount", 0) or 0)
        mmwave_presence = 1 if bool(edge_state.get("mmwave_presence", False)) else 0
        data_source = "Edge Cache"
        last_updated_dt = _coerce_utc_naive_dt(edge_state.get("timestamp")) or now
        last_mmwave_dt = _coerce_utc_naive_dt(edge_state.get("last_mmwave_update")) or last_updated_dt
        last_camera_dt = _coerce_utc_naive_dt(edge_state.get("last_camera_update")) or last_updated_dt
    else:
        headcount = 0
        mmwave_presence = 0
        data_source = "Mock"
        last_updated_dt = now
        last_mmwave_dt = None
        last_camera_dt = None

    mmwave_online = bool(last_mmwave_dt and (now - last_mmwave_dt).total_seconds() <= MMWAVE_STALE_SECS)
    camera_online = bool(last_camera_dt and (now - last_camera_dt).total_seconds() <= CAMERA_STALE_SECS)

    sensor_occupied = is_sensor_occupied(headcount, mmwave_presence)
    status = get_occupancy_label(headcount, capacity)
    occupancy_rate = round((headcount / capacity) * 100, 1) if capacity else 0

    booking_active = is_booking_active(booking_doc, now) if booking_doc else False
    booking_status = "Booked" if booking_doc else "Free"
    booking_mismatch = (booking_active and not sensor_occupied)

    state = {
        "room_id": room_id,
        "room_name": room_name,
        "capacity": capacity,
        "headcount": headcount,
        "status": status,
        "mmwave_presence": mmwave_presence,
        "occupancy_rate": occupancy_rate,
        "data_source": data_source,
        "booking_status": booking_status,
        "sensor_occupied": sensor_occupied,
        "booking_mismatch": booking_mismatch,
        "last_updated": dt_to_sg_str(last_updated_dt),
        "last_mmwave_update": dt_to_sg_str(last_mmwave_dt) if last_mmwave_dt else "-",
        "last_camera_update": dt_to_sg_str(last_camera_dt) if last_camera_dt else "-",
        "mmwave_online": mmwave_online,
        "camera_online": camera_online,
    }

    # real chart if DB sensor_history exists
    if history_docs:
        chart_labels = [
            dt_to_sg_hhmm(_coerce_utc_naive_dt(h.get("timestamp")))
            if h.get("timestamp") else "-"
            for h in history_docs
        ]
        chart_values = [int(h.get("headcount", 0) or 0) for h in history_docs]

    # otherwise use edge-cache history for live room
    elif edge_history:
        chart_labels = [
            dt_to_sg_hhmm(_coerce_utc_naive_dt(h.get("timestamp")))
            if h.get("timestamp") else "-"
            for h in edge_history
        ]
        chart_values = [int(h.get("headcount", 0) or 0) for h in edge_history]

    # otherwise keep your original placeholder behavior
    else:
        base_time = datetime.now() - timedelta(minutes=55)
        chart_values = [2, 0, 1, 4, 0, 3, 3, 0, 1, 4, 0, headcount]
        chart_labels = [(base_time + timedelta(minutes=5 * i)).strftime("%H:%M") for i in range(len(chart_values))]

    # prefer DB-backed logs, else fall back to edge-cache logs for live room
    if logs:
        event_logs = [
            {
                "time": dt_to_sg_str(_coerce_utc_naive_dt(l.get("timestamp"))) if l.get("timestamp") else "-",
                "event": l.get("event", "-"),
                "source": l.get("source", "-"),
                "value": l.get("value", "-"),
            }
            for l in logs
        ]
    elif edge_logs:
        event_logs = [
            {
                "time": dt_to_sg_str(_coerce_utc_naive_dt(l.get("timestamp"))) if l.get("timestamp") else "-",
                "event": l.get("event", "-"),
                "source": l.get("source", "-"),
                "value": l.get("value", "-"),
            }
            for l in edge_logs
        ]
    else:
        event_logs = []

    room_alerts = build_room_alerts_for_state(state)
    booking_details = build_booking_details_from_doc(
        booking_doc=booking_doc,
        booking_status=booking_status,
        now_utc_naive=now,
        booking_mismatch=booking_mismatch,
        sensor_occupied=sensor_occupied,
    )

    return state, chart_labels, chart_values, event_logs, room_alerts, booking_details