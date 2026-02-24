from flask import Flask, render_template, abort, request
from datetime import datetime, timedelta

app = Flask(__name__)

# -----------------------------
# Config (pagination sizes)
# -----------------------------
ROOMS_PER_PAGE = 12   # set to 5 / 10 / 12 depending on what you want
ALERTS_PER_PAGE = 2   # set to 2 or 3 (UI preference)


def paginate_items(items, page: int, per_page: int):
    total_items = len(items)
    total_pages = max(1, (total_items + per_page - 1) // per_page)

    # clamp page
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paged_items = items[start_idx:end_idx]

    if total_items == 0:
        start_item = 0
        end_item = 0
    else:
        start_item = start_idx + 1
        end_item = min(end_idx, total_items)

    return {
        "items": paged_items,
        "page": page,
        "per_page": per_page,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
        "start_item": start_item,
        "end_item": end_item,
    }

# -----------------------------
# Helpers
# -----------------------------
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_occupancy_label(headcount: int, capacity: int) -> str:
    if headcount <= 0:
        return "Vacant"
    if headcount < capacity:
        return "Occupied"
    if headcount == capacity:
        return "Full"
    return "Overcapacity"


def is_sensor_occupied(headcount: int, mmwave_presence: int) -> bool:
    return bool(mmwave_presence == 1 or headcount > 0)


# -----------------------------
# Mock room data (admin overview)
# DR-01 is your "live" prototype room
# Others are mock rows to demonstrate scalability
# -----------------------------
ROOMS = [
    {
        "room_id": "SIT-DR-01",
        "room_name": "SIT DR-01",
        "capacity": 6,
        "booking_status": "Booked",
        "headcount": 3,
        "mmwave_presence": 1,
        "data_source": "Live",
    },
    {
        "room_id": "SIT-DR-02",
        "room_name": "SIT DR-02",
        "capacity": 6,
        "booking_status": "Booked",
        "headcount": 0,
        "mmwave_presence": 0,
        "data_source": "Mock",
    },
    {
        "room_id": "SIT-DR-03",
        "room_name": "SIT DR-03",
        "capacity": 8,
        "booking_status": "Free",
        "headcount": 0,
        "mmwave_presence": 0,
        "data_source": "Mock",
    },
    {
        "room_id": "SIT-DR-04",
        "room_name": "SIT DR-04",
        "capacity": 6,
        "booking_status": "Booked",
        "headcount": 6,
        "mmwave_presence": 1,
        "data_source": "Mock",
    },
    {
        "room_id": "SIT-DR-05",
        "room_name": "SIT DR-05",
        "capacity": 10,
        "booking_status": "Booked",
        "headcount": 2,
        "mmwave_presence": 1,
        "data_source": "Mock",
    },
]


def build_room_overview_rows():
    rows = []
    for room in ROOMS:
        sensor_occupied = is_sensor_occupied(room["headcount"], room["mmwave_presence"])
        occupancy_label = get_occupancy_label(room["headcount"], room["capacity"])
        mismatch = room["booking_status"] == "Booked" and not sensor_occupied

        rows.append(
            {
                **room,
                "last_updated": now_str(),
                "sensor_occupied": sensor_occupied,
                "sensor_occupancy_text": "Occupied" if sensor_occupied else "Vacant",
                "occupancy_label": occupancy_label,
                "mismatch": mismatch,
                "occupancy_rate": round((room["headcount"] / room["capacity"]) * 100, 1)
                if room["capacity"] > 0
                else 0,
            }
        )
    return rows


def build_overview_summary(rows):
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


# -----------------------------
# NEW: Room-level helpers
# -----------------------------
def build_room_alerts_for_state(state):
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


def get_room_detail_payload(room_id: str):
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


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
@app.route("/overview")
def overview():
    # Support both param styles just in case your template uses either
    room_page = request.args.get("room_page", type=int)
    if room_page is None:
        room_page = request.args.get("rooms_page", default=1, type=int)

    alert_page = request.args.get("alert_page", type=int)
    if alert_page is None:
        alert_page = request.args.get("alerts_page", default=1, type=int)

    rows = build_room_overview_rows()
    summary = build_overview_summary(rows)
    all_admin_alerts = build_admin_alerts(rows)

    room_pagination = paginate_items(rows, room_page, ROOMS_PER_PAGE)
    alert_pagination = paginate_items(all_admin_alerts, alert_page, ALERTS_PER_PAGE)

    overview_chart_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    overview_chart_values = [62, 71, 68, 75, 81, 44, 39]

    return render_template(
        "overview.html",
        active_page="overview",
        summary=summary,

        # paged data
        rooms=room_pagination["items"],
        admin_alerts=alert_pagination["items"],

        # pagination metadata (your template needs these)
        room_pagination=room_pagination,
        alert_pagination=alert_pagination,

        overview_chart_labels=overview_chart_labels,
        overview_chart_values=overview_chart_values,
    )


@app.route("/rooms/<room_id>")
def room_detail(room_id):
    payload = get_room_detail_payload(room_id)
    if payload is None:
        abort(404)

    state, chart_labels, chart_values, event_logs, room_alerts, booking_details = payload
    return render_template(
        "room_detail.html",
        active_page="overview",
        state=state,
        event_logs=event_logs,
        chart_labels=chart_labels,
        chart_values=chart_values,
        room_alerts=room_alerts,
        booking_details=booking_details,
    )


if __name__ == "__main__":
    app.run(debug=True)