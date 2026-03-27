# services.py
from datetime import datetime, timedelta

from db import get_db
from utils import (
    utcnow_naive,
    dt_to_sg_str,
    now_str_sg,
    get_occupancy_label,
    is_sensor_occupied,
    MMWAVE_STALE_SECS,
    CAMERA_STALE_SECS,
)

# -----------------------------
# Internal datetime coercion
# -----------------------------
def _coerce_utc_naive_dt(val):
    """
    Convert DB timestamp (datetime or string) into a UTC-naive datetime.
    Supports:
      - datetime (naive or tz-aware)
      - ISO strings: "2026-03-02T15:30:00", "2026-03-02T15:30:00Z"
      - Common strings: "2026-03-02 15:30:00", "2026-03-02 15:30"
    Returns None if cannot parse.
    """
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


# -----------------------------
# Booking helpers (DB-based)
# -----------------------------
def is_booking_active(booking_doc, now_utc_naive):
    if not booking_doc:
        return False

    start_raw = booking_doc.get("start_time")
    end_raw = booking_doc.get("end_time")
    grace = int(booking_doc.get("grace_period_mins", 0) or 0)

    start = _coerce_utc_naive_dt(start_raw)
    end = _coerce_utc_naive_dt(end_raw)

    if not start or not end:
        return False

    return start <= now_utc_naive <= (end + timedelta(minutes=grace))


# -----------------------------
# Weekly utilisation auto-refresh
# -----------------------------
def monday_start(dt: datetime) -> datetime:
    start = dt - timedelta(days=dt.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def ensure_weekly_utilisation_fresh(max_age_hours: int = 1):
    """
    Ensures weekly_utilisation has the current week's overall doc.
    Recomputes if missing or older than max_age_hours.

    Called from /overview so the chart stays up to date without cron.
    """
    # IMPORTANT: compute_weekly_utilisation.py imports dashboard.* in your setup
    from mockdata.compute_weekly_utilisation import compute_and_store_current_week

    db = get_db()
    now = utcnow_naive()
    ws = monday_start(now)
    ws_key = ws.strftime("%Y-%m-%d %H:%M")

    doc = db.weekly_utilisation.find_one(
        {"scope": "overall", "room_id": None, "week_start": ws_key},
        {"_id": 0, "updated_at": 1},
    )

    if not doc:
        compute_and_store_current_week()
        return

    updated_at = doc.get("updated_at")
    updated_dt = _coerce_utc_naive_dt(updated_at)  # handles string/datetime
    if not updated_dt or (now - updated_dt) > timedelta(hours=max_age_hours):
        compute_and_store_current_week()


# -----------------------------
# Overview (DB read + join)
# -----------------------------
def build_room_overview_rows():
    db = get_db()
    now = utcnow_naive()

    rooms_cfg = list(db.rooms.find({}, {"_id": 0}).sort("room_id", 1))
    room_ids = [r["room_id"] for r in rooms_cfg]

    states = list(db.room_state.find({"room_id": {"$in": room_ids}}, {"_id": 0}))
    state_map = {s["room_id"]: s for s in states}

    bookings = list(db.bookings.find({"room_id": {"$in": room_ids}}, {"_id": 0}))
    booking_map = {b["room_id"]: b for b in bookings}

    rows = []
    for r in rooms_cfg:
        rid = r["room_id"]
        capacity = int(r.get("capacity", 0) or 0)

        s = state_map.get(rid, {})
        headcount = int(s.get("headcount", 0) or 0)
        mmwave_presence = int(s.get("mmwave_presence", 0) or 0)
        data_source = s.get("data_source", "Mock")

        last_updated_dt = s.get("last_updated") or now
        last_mmwave_dt = s.get("last_mmwave_update")
        last_camera_dt = s.get("last_camera_update")

        mmwave_online = bool(
            last_mmwave_dt and (now - last_mmwave_dt).total_seconds() <= MMWAVE_STALE_SECS
        )
        camera_online = bool(
            last_camera_dt and (now - last_camera_dt).total_seconds() <= CAMERA_STALE_SECS
        )

        sensor_occupied = is_sensor_occupied(headcount, mmwave_presence)
        occupancy_label = get_occupancy_label(headcount, capacity)

        # Dashboard rule: booking record exists => Booked
        booking_doc = booking_map.get(rid)
        booking_status = "Booked" if booking_doc else "Free"

        # If you only want mismatch when booking is active, change to:
        # booking_mismatch = (is_booking_active(booking_doc, now) and not sensor_occupied)
        booking_mismatch = (booking_status == "Booked" and not sensor_occupied)

        room_name = r.get("room_name") or rid.replace("-", " ")

        rows.append(
            {
                "room_id": rid,
                "room_name": room_name,
                "capacity": capacity,
                "data_source": data_source,
                "booking_status": booking_status,
                "mismatch": booking_mismatch,
                "headcount": headcount,
                "mmwave_presence": mmwave_presence,
                "sensor_occupied": sensor_occupied,
                "sensor_occupancy_text": "Occupied" if sensor_occupied else "Vacant",
                "occupancy_label": occupancy_label,
                "mmwave_online": mmwave_online,
                "camera_online": camera_online,
                "last_updated": dt_to_sg_str(last_updated_dt),
                "occupancy_rate": round((headcount / capacity) * 100, 1) if capacity > 0 else 0,
            }
        )

    return rows


def build_overview_summary(rows):
    total_rooms = len(rows)
    occupied_now = sum(1 for r in rows if r["sensor_occupied"])
    vacant_now = total_rooms - occupied_now
    mismatch_alerts = sum(1 for r in rows if r["mismatch"])

    return {
        "total_rooms": total_rooms,
        "occupied_now": occupied_now,
        "vacant_now": vacant_now,
        "mismatch_alerts": mismatch_alerts,
        "last_updated": now_str_sg(),
    }


# -----------------------------
# Alerts (computed, not stored)
# -----------------------------
def build_admin_alerts(rows):
    alerts = []

    for r in rows:
        if r["mismatch"]:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "BOOKED_VACANT",
                    "room_id": r["room_id"],
                    "room_name": r["room_name"],
                    "title": "Booked room appears vacant",
                    "message": f"{r['room_name']} is booked but sensors indicate vacant.",
                    "timestamp": r["last_updated"],
                }
            )

        if r["occupancy_label"] == "Overcapacity":
            alerts.append(
                {
                    "severity": "critical",
                    "code": "OVERCAPACITY",
                    "room_id": r["room_id"],
                    "room_name": r["room_name"],
                    "title": "Room overcapacity",
                    "message": f"{r['room_name']} exceeds capacity ({r['headcount']}/{r['capacity']}).",
                    "timestamp": r["last_updated"],
                }
            )

        if r["booking_status"] == "Free" and r["sensor_occupied"]:
            alerts.append(
                {
                    "severity": "info",
                    "code": "UNBOOKED_OCCUPIED",
                    "room_id": r["room_id"],
                    "room_name": r["room_name"],
                    "title": "Unbooked room is occupied",
                    "message": f"{r['room_name']} is occupied but booking status is Free.",
                    "timestamp": r["last_updated"],
                }
            )

        if r["occupancy_label"] == "Full":
            alerts.append(
                {
                    "severity": "info",
                    "code": "ROOM_FULL",
                    "room_id": r["room_id"],
                    "room_name": r["room_name"],
                    "title": "Room at full capacity",
                    "message": f"{r['room_name']} is full ({r['headcount']}/{r['capacity']}).",
                    "timestamp": r["last_updated"],
                }
            )

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (severity_rank.get(a["severity"], 99), a["room_name"]))
    return alerts


def build_room_alerts_for_state(state):
    alerts = []

    if state["booking_mismatch"]:
        alerts.append(
            {
                "severity": "warning",
                "title": "Booked room appears vacant",
                "message": f"{state['room_name']} is booked but sensors indicate no occupancy.",
                "timestamp": state["last_updated"],
            }
        )

    if state["booking_status"] == "Free" and state["sensor_occupied"]:
        alerts.append(
            {
                "severity": "info",
                "title": "Unbooked room is occupied",
                "message": f"{state['room_name']} is occupied while booking status is Free.",
                "timestamp": state["last_updated"],
            }
        )

    if state["status"] == "Full":
        alerts.append(
            {
                "severity": "info",
                "title": "Room at full capacity",
                "message": f"Headcount is {state['headcount']}/{state['capacity']}.",
                "timestamp": state["last_updated"],
            }
        )
    elif state["status"] == "Overcapacity":
        alerts.append(
            {
                "severity": "critical",
                "title": "Room overcapacity",
                "message": f"Headcount exceeds capacity ({state['headcount']}/{state['capacity']}).",
                "timestamp": state["last_updated"],
            }
        )

    if not state["mmwave_online"]:
        alerts.append(
            {
                "severity": "critical",
                "title": "mmWave sensor offline",
                "message": "No recent mmWave update detected.",
                "timestamp": state["last_updated"],
            }
        )

    if not state["camera_online"]:
        alerts.append(
            {
                "severity": "critical",
                "title": "Camera pipeline offline",
                "message": "No recent camera update detected.",
                "timestamp": state["last_updated"],
            }
        )

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: severity_rank.get(a["severity"], 99))
    return alerts


# -----------------------------
# Booking box (detail page)
# -----------------------------
def build_booking_details_from_doc(
    booking_doc, booking_status, now_utc_naive, booking_mismatch, sensor_occupied
):
    from utils import dt_to_sg_hhmm  # avoid circular import

    if booking_status == "Booked" and booking_doc:
        start = _coerce_utc_naive_dt(booking_doc.get("start_time"))
        end = _coerce_utc_naive_dt(booking_doc.get("end_time"))
        grace_mins = int(booking_doc.get("grace_period_mins", 0) or 0)

        if not start or not end:
            booked_by = booking_doc.get("booked_by", "RBS reservation (mock)")
            return {
                "booking_window": "Booking exists (invalid time format)",
                "minutes_remaining": None,
                "booked_by": booked_by,
                "grace_period_mins": grace_mins,
                "grace_status": "N/A",
                "grace_remaining": None,
                "release_recommendation": "Check start_time/end_time in DB",
            }

        booking_window = f"{dt_to_sg_hhmm(start)} - {dt_to_sg_hhmm(end)}"
        booked_by = booking_doc.get("booked_by", "RBS reservation (mock)")

        mins_remaining = max(0, int((end - now_utc_naive).total_seconds() // 60))

        grace_end = end + timedelta(minutes=grace_mins)

        if now_utc_naive <= end:
            grace_status = "Not started"
            grace_remaining = None
        elif end < now_utc_naive <= grace_end:
            grace_status = "In grace period"
            grace_remaining = max(0, int((grace_end - now_utc_naive).total_seconds() // 60))
        else:
            grace_status = "Expired"
            grace_remaining = 0

        release_recommendation = (
            "Review for release (appears vacant)"
            if booking_mismatch
            else "No release action recommended"
        )

        return {
            "booking_window": booking_window,
            "minutes_remaining": mins_remaining,
            "booked_by": booked_by,
            "grace_period_mins": grace_mins,
            "grace_status": grace_status,
            "grace_remaining": grace_remaining,
            "release_recommendation": release_recommendation,
        }

    return {
        "booking_window": "No active booking",
        "minutes_remaining": None,
        "booked_by": "-",
        "grace_period_mins": None,
        "grace_status": "N/A",
        "grace_remaining": None,
        "release_recommendation": "Walk-in usage detected"
        if sensor_occupied
        else "Room available for walk-in",
    }