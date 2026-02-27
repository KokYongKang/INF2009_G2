from datetime import datetime, timedelta
from utils import now_str, get_occupancy_label, is_sensor_occupied, ROOMS

def build_room_overview_rows():
    """Build overview rows with live sensor data"""
    rows = []
    for room in ROOMS:
        # For live room, use actual sensor data
        if room.get("data_source") == "Live" and room.get("last_updated"):
            sensor_occupied = is_sensor_occupied(room["headcount"], room["mmwave_presence"])
            last_updated = room["last_updated"]
        else:
            # Fallback to mock data
            sensor_occupied = is_sensor_occupied(room["headcount"], room["mmwave_presence"])
            last_updated = now_str()
        
        occupancy_label = get_occupancy_label(room["headcount"], room["capacity"])
        mismatch = room["booking_status"] == "Booked" and not sensor_occupied

        rows.append({
            **room,
            "last_updated": last_updated,
            "sensor_occupied": sensor_occupied,
            "sensor_occupancy_text": "Occupied" if sensor_occupied else "Vacant",
            "occupancy_label": occupancy_label,
            "mismatch": mismatch,
            "occupancy_rate": round((room["headcount"] / room["capacity"]) * 100, 1)
            if room["capacity"] > 0 else 0,
        })
    return rows

def build_overview_summary(rows):
    """Build summary statistics for overview page"""
    total_rooms = len(rows)
    occupied_now = sum(1 for r in rows if r["sensor_occupied"])
    vacant_now = total_rooms - occupied_now
    mismatch_alerts = sum(1 for r in rows if r["mismatch"])
    booked_rooms = sum(1 for r in rows if r["booking_status"] == "Booked")

    return {
        "total_rooms": total_rooms,
        "occupied_now": occupied_now,
        "vacant_now": vacant_now,
        "mismatch_alerts": mismatch_alerts,
        "booked_rooms": booked_rooms,
        "last_updated": now_str(),
    }

def build_admin_alerts(rows):
    """Build admin alerts based on room data"""
    alerts = []

    for r in rows:
        if r["mismatch"]:
            alerts.append({
                "severity": "warning",
                "code": "BOOKED_VACANT",
                "room_id": r["room_id"],
                "room_name": r["room_name"],
                "title": "Booked room appears vacant",
                "message": f'{r["room_name"]} is booked but sensors indicate vacant.',
                "timestamp": now_str(),
            })

        if r["occupancy_label"] == "Overcapacity":
            alerts.append({
                "severity": "critical",
                "code": "OVERCAPACITY",
                "room_id": r["room_id"],
                "room_name": r["room_name"],
                "title": "Room overcapacity",
                "message": f'{r["room_name"]} exceeds capacity ({r["headcount"]}/{r["capacity"]}).',
                "timestamp": now_str(),
            })

        if r["booking_status"] == "Free" and r["sensor_occupied"]:
            alerts.append({
                "severity": "info",
                "code": "UNBOOKED_OCCUPIED",
                "room_id": r["room_id"],
                "room_name": r["room_name"],
                "title": "Unbooked room is occupied",
                "message": f'{r["room_name"]} is occupied but booking status is Free.',
                "timestamp": now_str(),
            })

        if r["occupancy_label"] == "Full":
            alerts.append({
                "severity": "info",
                "code": "ROOM_FULL",
                "room_id": r["room_id"],
                "room_name": r["room_name"],
                "title": "Room at full capacity",
                "message": f'{r["room_name"]} is full ({r["headcount"]}/{r["capacity"]}).',
                "timestamp": now_str(),
            })

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (severity_rank.get(a["severity"], 99), a["room_name"]))
    return alerts

def build_room_alerts_for_state(state):
    """Build alerts for a specific room state"""
    alerts = []

    # Booked but appears vacant
    if state["booking_status"] == "Booked" and not state["sensor_occupied"]:
        alerts.append({
            "severity": "warning",
            "title": "Booked room appears vacant",
            "message": f'{state["room_name"]} is booked but sensors indicate no occupancy.',
            "timestamp": state["last_updated"],
        })

    # Occupied while room is free (walk-in usage / mismatch)
    if state["booking_status"] == "Free" and state["sensor_occupied"]:
        alerts.append({
            "severity": "info",
            "title": "Unbooked room is occupied",
            "message": f'{state["room_name"]} is occupied while booking status is Free.',
            "timestamp": state["last_updated"],
        })

    # Capacity alerts
    if state["status"] == "Full":
        alerts.append({
            "severity": "info",
            "title": "Room at full capacity",
            "message": f'Headcount is {state["headcount"]}/{state["capacity"]}.',
            "timestamp": state["last_updated"],
        })
    elif state["status"] == "Overcapacity":
        alerts.append({
            "severity": "critical",
            "title": "Room overcapacity",
            "message": f'Headcount exceeds capacity ({state["headcount"]}/{state["capacity"]}).',
            "timestamp": state["last_updated"],
        })

    # Sensor health alerts
    if not state["mmwave_online"]:
        alerts.append({
            "severity": "critical",
            "title": "mmWave sensor offline",
            "message": "No recent mmWave heartbeat detected.",
            "timestamp": state["last_updated"],
        })

    if not state["camera_online"]:
        alerts.append({
            "severity": "critical",
            "title": "Camera pipeline offline",
            "message": "Camera headcount pipeline is not updating.",
            "timestamp": state["last_updated"],
        })

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: severity_rank.get(a["severity"], 99))
    return alerts

def build_booking_details(state, current_time: datetime):
    """Build booking details for a room state"""
    if state["booking_status"] == "Booked":
        slot_start = current_time.replace(minute=0, second=0, microsecond=0)
        slot_end = slot_start + timedelta(hours=1)
        minutes_remaining = max(0, int((slot_end - current_time).total_seconds() // 60))
        booking_window = f'{slot_start.strftime("%H:%M")} - {slot_end.strftime("%H:%M")}'
        booked_by = "RBS reservation (mock)"
        grace_status = "Not in grace period"
        release_recommendation = (
            "Review for release (appears vacant)"
            if state["booking_mismatch"] else
            "No release action recommended"
        )
    else:
        booking_window = "No active booking"
        minutes_remaining = None
        booked_by = "-"
        grace_status = "N/A"
        release_recommendation = (
            "Walk-in usage detected" if state["sensor_occupied"] else "Room available for walk-in"
        )

    return {
        "booking_window": booking_window,
        "minutes_remaining": minutes_remaining,
        "booked_by": booked_by,
        "grace_status": grace_status,
        "release_recommendation": release_recommendation,
    }
