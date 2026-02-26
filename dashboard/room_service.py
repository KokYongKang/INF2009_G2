from datetime import datetime, timedelta
from utils import get_occupancy_label, is_sensor_occupied, ROOMS
from services import build_room_alerts_for_state, build_booking_details

def get_room_detail_payload(room_id: str):
    """Get detailed payload for a specific room"""
    room = next((r for r in ROOMS if r["room_id"] == room_id), None)
    if not room:
        return None

    now = datetime.now()

    status = get_occupancy_label(room["headcount"], room["capacity"])
    occupancy_rate = round((room["headcount"] / room["capacity"]) * 100, 1) if room["capacity"] else 0
    sensor_occupied = is_sensor_occupied(room["headcount"], room["mmwave_presence"])
    booking_mismatch = room["booking_status"] == "Booked" and not sensor_occupied

    # Mock telemetry freshness timestamps (real system would come from actual data pipeline)
    mmwave_update_dt = now - timedelta(minutes=1)
    camera_update_dt = now - timedelta(minutes=1, seconds=10)
    fusion_update_dt = now - timedelta(seconds=20)

    state = {
        "room_id": room["room_id"],
        "room_name": room["room_name"],
        "capacity": room["capacity"],
        "headcount": room["headcount"],
        "status": status,
        "mmwave_presence": room["mmwave_presence"],
        "occupancy_rate": occupancy_rate,
        "last_updated": now.strftime("%Y-%m-%d %H:%M:%S"),
        "mmwave_online": True,
        "camera_online": True,
        "fusion_online": True,
        "dashboard_online": True,
        "data_source": room["data_source"],
        "booking_status": room["booking_status"],
        "sensor_occupied": sensor_occupied,
        "booking_mismatch": booking_mismatch,
        "last_mmwave_update": mmwave_update_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "last_camera_update": camera_update_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "last_fusion_update": fusion_update_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "fusion_confidence": "High" if (room["mmwave_presence"] == 1 and room["headcount"] > 0) else "Medium",
    }

    # Placeholder chart data
    base_time = now - timedelta(minutes=55)
    chart_values = [2, 0, 1, 4, 0, 3, 3, 0, 1, 4, 0, room["headcount"]]
    chart_labels = [
        (base_time + timedelta(minutes=5 * i)).strftime("%H:%M")
        for i in range(len(chart_values))
    ]

    # Placeholder event logs
    event_logs = [
        {
            "time": (now - timedelta(minutes=18)).strftime("%Y-%m-%d %H:%M:%S"),
            "event": "mmWave presence detected" if room["mmwave_presence"] else "mmWave no presence",
            "source": "mmWave",
            "value": room["mmwave_presence"],
        },
        {
            "time": (now - timedelta(minutes=17)).strftime("%Y-%m-%d %H:%M:%S"),
            "event": "Camera headcount updated",
            "source": "Camera",
            "value": room["headcount"],
        },
        {
            "time": (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
            "event": "Occupancy status evaluated",
            "source": "Fusion",
            "value": status,
        },
    ]

    room_alerts = build_room_alerts_for_state(state)
    booking_details = build_booking_details(state, now)

    return state, chart_labels, chart_values, event_logs, room_alerts, booking_details

def get_room_by_id(room_id: str):
    """Get room data by ID"""
    return next((r for r in ROOMS if r["room_id"] == room_id), None)

def get_all_rooms():
    """Get all rooms data"""
    return ROOMS

def update_room_data(room_id: str, updates: dict):
    """Update room data (for future implementation)"""
    room = get_room_by_id(room_id)
    if room:
        room.update(updates)
        return True
    return False
