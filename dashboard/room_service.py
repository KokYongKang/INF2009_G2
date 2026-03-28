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

# For demo use: keep DR-01 always within a current booking window
FORCE_LIVE_DEMO_BOOKING = os.getenv("FORCE_LIVE_DEMO_BOOKING", "1") == "1"

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


def _sg_now_naive():
    """
    Build a Singapore-local naive datetime from UTC naive time.
    Used only for booking/demo display logic.
    """
    return utcnow_naive() + timedelta(hours=8)


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


def _empty_booking_details():
    return {
        "booking_window": "-",
        "booked_by": "-",
        "minutes_remaining": None,
        "grace_period_mins": None,
        "grace_status": "-",
        "grace_remaining": None,
        "release_recommendation": "-",
    }


def _build_demo_booking_doc(room_id: str, now_local_naive: datetime):
    """
    Build a synthetic booking that is always active 'right now' for demo purposes.
    Example:
    - starts 5 minutes ago
    - ends 55 minutes from now

    IMPORTANT:
    This uses Singapore-local naive time so the displayed booking window
    matches the actual time the user sees on screen.
    """
    start_dt = now_local_naive - timedelta(minutes=5)
    end_dt = now_local_naive + timedelta(minutes=55)

    booked_by = "RBS reservation (mock)"

    return {
        "booking_id": f"demo-{room_id}",
        "room_id": room_id,
        "booked_by": booked_by,
        "reserved_by": booked_by,
        "reserver_name": booked_by,
        "user_name": booked_by,

        "start_time": start_dt,
        "end_time": end_dt,
        "booking_start": start_dt,
        "booking_end": end_dt,
        "start": start_dt,
        "end": end_dt,

        "grace_period_mins": 10,
        "grace_period_minutes": 10,

        "is_mock": True,
    }


def get_room_detail_payload(room_id: str):
    now = utcnow_naive()          # keep for sensor/state timestamps
    booking_now = _sg_now_naive() # use for booking/demo display logic

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
            .limit(100)
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

    # Demo override: always show a CURRENT booking for the live room
    if FORCE_LIVE_DEMO_BOOKING and room_id == LIVE_ROOM_ID:
        booking_doc = _build_demo_booking_doc(room_id, booking_now)

    edge_state = _edge_get_latest_state(room_id) if room_id == LIVE_ROOM_ID else None
    edge_history = _edge_get_recent_history(room_id, limit=100) if room_id == LIVE_ROOM_ID else []
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

    booking_active = is_booking_active(booking_doc, booking_now) if booking_doc else False

    # For room-detail UI, only show "Booked" if the booking is actually active NOW
    booking_doc_for_ui = booking_doc if booking_active else None
    booking_status = "Booked" if booking_doc_for_ui else "Free"
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

    def _build_chart_points(docs, interval_mins=5, max_points=12):
        """
        Build chart points using two rules:
        1. Every interval_mins with no change -> plot 0 (baseline vacant)
        2. Occupancy changes -> plot immediately with actual value
        Returns the last max_points entries.
        """
        if not docs:
            return [], []

        points = []
        prev_occupancy = None
        last_plotted_ts = None

        for doc in docs:
            ts = _coerce_utc_naive_dt(doc.get("timestamp"))
            if not ts:
                continue
            occupancy = int(doc.get("occupancy", 0) or 0)

            if occupancy != prev_occupancy:
                points.append((ts, occupancy))
                last_plotted_ts = ts
                prev_occupancy = occupancy
            elif last_plotted_ts and (ts - last_plotted_ts).total_seconds() >= interval_mins * 60:
                points.append((ts, 0))
                last_plotted_ts = ts

        if docs:
            last_ts = _coerce_utc_naive_dt(docs[-1].get("timestamp"))
            last_occ = int(docs[-1].get("occupancy", 0) or 0)
            if not points or points[-1][0] != last_ts:
                points.append((last_ts, last_occ))

        points = points[-max_points:]
        labels = [dt_to_sg_hhmm(ts) if ts else "-" for ts, _ in points]
        values = [val for _, val in points]
        return labels, values

    if history_docs:
        chart_labels, chart_values = _build_chart_points(history_docs)
    elif edge_history:
        chart_labels, chart_values = _build_chart_points(edge_history)
    else:
        base_time = datetime.now() - timedelta(minutes=55)
        chart_values = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0]
        chart_labels = [(base_time + timedelta(minutes=5 * i)).strftime("%H:%M") for i in range(len(chart_values))]

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

    if booking_doc_for_ui:
        booking_details = build_booking_details_from_doc(
            booking_doc=booking_doc_for_ui,
            booking_status=booking_status,
            now_utc_naive=booking_now,
            booking_mismatch=booking_mismatch,
            sensor_occupied=sensor_occupied,
        )
    else:
        booking_details = _empty_booking_details()

    return state, chart_labels, chart_values, event_logs, room_alerts, booking_details