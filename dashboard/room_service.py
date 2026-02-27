# room_service.py
from datetime import datetime, timedelta

from db import get_db
from utils import (
    utcnow_naive,
    dt_to_sg_str,
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

def get_room_detail_payload(room_id: str):
    db = get_db()
    now = utcnow_naive()  # ✅ always use UTC-naive for comparisons

    room_cfg = db.rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room_cfg:
        return None

    state_doc = db.room_state.find_one({"room_id": room_id}, {"_id": 0}) or {}
    booking_doc = db.bookings.find_one({"room_id": room_id}, {"_id": 0})
    # latest 10 logs
    logs = list(db.event_logs.find({"room_id": room_id}, {"_id": 0}).sort("timestamp", -1).limit(10))

    capacity = int(room_cfg.get("capacity", 0) or 0)
    room_name = room_cfg.get("room_name") or room_id.replace("-", " ")

    headcount = int(state_doc.get("headcount", 0) or 0)
    mmwave_presence = int(state_doc.get("mmwave_presence", 0) or 0)
    data_source = state_doc.get("data_source", "Mock")

    last_updated_dt = state_doc.get("last_updated") or now
    last_mmwave_dt = state_doc.get("last_mmwave_update")
    last_camera_dt = state_doc.get("last_camera_update")

    mmwave_online = bool(last_mmwave_dt and (now - last_mmwave_dt).total_seconds() <= MMWAVE_STALE_SECS)
    camera_online = bool(last_camera_dt and (now - last_camera_dt).total_seconds() <= CAMERA_STALE_SECS)

    sensor_occupied = is_sensor_occupied(headcount, mmwave_presence)
    status = get_occupancy_label(headcount, capacity)
    occupancy_rate = round((headcount / capacity) * 100, 1) if capacity else 0

    booking_status = "Booked" if is_booking_active(booking_doc, now) else "Free"
    booking_mismatch = (booking_status == "Booked" and not sensor_occupied)

    # what your templates use
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

        # ✅ display-friendly times (SG strings), but comparisons use UTC-naive above
        "last_updated": dt_to_sg_str(last_updated_dt),
        "last_mmwave_update": dt_to_sg_str(last_mmwave_dt) if last_mmwave_dt else "-",
        "last_camera_update": dt_to_sg_str(last_camera_dt) if last_camera_dt else "-",

        "mmwave_online": mmwave_online,
        "camera_online": camera_online,
    }

    # placeholder chart data (until you store real time-series)
    base_time = datetime.now() - timedelta(minutes=55)
    chart_values = [2, 0, 1, 4, 0, 3, 3, 0, 1, 4, 0, headcount]
    chart_labels = [(base_time + timedelta(minutes=5 * i)).strftime("%H:%M") for i in range(len(chart_values))]

    # logs formatted for UI
    if logs:
        event_logs = [
            {
                "time": dt_to_sg_str(l.get("timestamp")) if l.get("timestamp") else "-",
                "event": l.get("event", "-"),
                "source": l.get("source", "-"),
                "value": l.get("value", "-"),
            }
            for l in logs
        ]
    else:
        event_logs = []

    room_alerts = build_room_alerts_for_state(state)
    booking_details = build_booking_details_from_doc(
        booking_doc=booking_doc,
        booking_status=booking_status,
        now_utc_naive=now,              # ✅ critical fix
        booking_mismatch=booking_mismatch,
        sensor_occupied=sensor_occupied,
    )

    return state, chart_labels, chart_values, event_logs, room_alerts, booking_details