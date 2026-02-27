from flask import Flask, render_template, abort, request
from utils import paginate_items, ROOMS_PER_PAGE, ALERTS_PER_PAGE, ROOMS
from services import build_room_overview_rows, build_overview_summary, build_admin_alerts
from room_service import get_room_detail_payload

app = Flask(__name__)

# -----------------------------
# API Endpoints
# -----------------------------
@app.route('/api/sensor-update', methods=['POST'])
def sensor_update():
    """Receive live sensor data from Raspberry Pi"""
    data = request.get_json()
    
    if not data:
        return {"status": "error", "message": "No data received"}, 400
    
    # Update SIT-DR-01 room data in ROOMS array
    room = next((r for r in ROOMS if r["room_id"] == "SIT-DR-01"), None)
    if room:
        room["headcount"] = data.get("headcount", 0)
        room["mmwave_presence"] = 1 if data.get("mmwave_presence") else 0
        room["last_updated"] = data.get("timestamp", "")
        room["data_source"] = "Live"
        
        print(f"Updated SIT-DR-01: headcount={room['headcount']}, mmwave={room['mmwave_presence']}")
        return {"status": "ok", "received": data}
    else:
        return {"status": "error", "message": "Room SIT-DR-01 not found"}, 404

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

    # Get data from services
    rows = build_room_overview_rows()
    summary = build_overview_summary(rows)
    all_admin_alerts = build_admin_alerts(rows)

    # Paginate data
    room_pagination = paginate_items(rows, room_page, ROOMS_PER_PAGE)
    alert_pagination = paginate_items(all_admin_alerts, alert_page, ALERTS_PER_PAGE)

    # Chart data
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
    # Get room data from service
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
    app.run(host='0.0.0.0', port=5000, debug=True)