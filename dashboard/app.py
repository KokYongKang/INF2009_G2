# app.py
from flask import Flask, render_template, abort, request
from utils import paginate_items, ROOMS_PER_PAGE, ALERTS_PER_PAGE, utcnow_naive
from services import (
    build_room_overview_rows,
    build_overview_summary,
    build_admin_alerts,
    ensure_weekly_utilisation_fresh,
)
from room_service import get_room_detail_payload
from db import get_db

app = Flask(__name__)

@app.route("/api/sensor-update", methods=["POST"])
def sensor_update():
    """
    Receive live sensor data from Raspberry Pi and persist into MongoDB.
    Expected JSON (example):
      {
        "room_id": "SIT-DR-01",
        "headcount": 3,
        "mmwave_presence": true
      }
    """
    data = request.get_json(silent=True) or {}
    room_id = data.get("room_id", "SIT-DR-01")

    # Basic validation
    try:
        headcount = int(data.get("headcount", 0) or 0)
    except ValueError:
        return {"status": "error", "message": "headcount must be an integer"}, 400

    mmwave_presence = 1 if bool(data.get("mmwave_presence", False)) else 0

    now = utcnow_naive()
    db = get_db()

    # Update latest snapshot (room_state)
    db["room_state"].update_one(
        {"room_id": room_id},
        {"$set": {
            "room_id": room_id,
            "data_source": "Live",
            "headcount": headcount,
            "mmwave_presence": mmwave_presence,
            "last_updated": now,
            "last_mmwave_update": now,   # since this payload included mmWave
            "last_camera_update": now,   # since this payload included headcount
        }},
        upsert=True
    )

    # Optional: write logs (so your "Recent Event Logs" becomes truly DB-backed)
    db["event_logs"].insert_many([
        {
            "room_id": room_id,
            "timestamp": now,
            "source": "mmWave",
            "event": "mmWave presence detected" if mmwave_presence else "mmWave no presence",
            "value": mmwave_presence,
        },
        {
            "room_id": room_id,
            "timestamp": now,
            "source": "Camera",
            "event": "Camera headcount updated",
            "value": headcount,
        }
    ])

    return {"status": "ok", "received": {"room_id": room_id, "headcount": headcount, "mmwave_presence": mmwave_presence}}

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
@app.route("/overview")
def overview():
    room_page = request.args.get("room_page", type=int) or request.args.get("rooms_page", default=1, type=int)
    alert_page = request.args.get("alert_page", type=int) or request.args.get("alerts_page", default=1, type=int)

    rows = build_room_overview_rows()
    summary = build_overview_summary(rows)
    all_admin_alerts = build_admin_alerts(rows)

    room_pagination = paginate_items(rows, room_page, ROOMS_PER_PAGE)
    alert_pagination = paginate_items(all_admin_alerts, alert_page, ALERTS_PER_PAGE)

    # ✅ Ensure weekly utilisation for the current week exists / is fresh
    ensure_weekly_utilisation_fresh()

    db = get_db()

    overview_chart_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    doc = db.weekly_utilisation.find_one(
        {"scope": "overall", "room_id": None},
        sort=[("week_start", -1)]
    )

    if doc and isinstance(doc.get("values"), dict):
        values_map = doc["values"]
        overview_chart_values = [
            int(values_map.get(day, 0) or 0)
            for day in overview_chart_labels
        ]
    else:
        # fallback (only if DB empty)
        overview_chart_values = [0, 0, 0, 0, 0, 0, 0]

    return render_template(
        "overview.html",
        active_page="overview",
        summary=summary,
        rooms=room_pagination["items"],
        admin_alerts=alert_pagination["items"],
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
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)