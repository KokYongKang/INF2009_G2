# app.py
from flask import Flask, render_template, abort, request
from utils import paginate_items, ROOMS_PER_PAGE, ALERTS_PER_PAGE
from services import build_room_overview_rows, build_overview_summary, build_admin_alerts
from room_service import get_room_detail_payload
from api_service import process_sensor_update

app = Flask(__name__)

# -----------------------------
# API Endpoints
# -----------------------------
@app.route("/api/sensor-update", methods=["POST"])
def sensor_update():
    data = request.get_json(silent=True)
    if not data:
        return {"status": "error", "message": "No data received"}, 400

    state_update = process_sensor_update(data)
    return {"status": "ok", "updated": state_update}, 200

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
@app.route("/overview")
def overview():
    room_page = request.args.get("room_page", default=1, type=int)
    alert_page = request.args.get("alert_page", default=1, type=int)

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