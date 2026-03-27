from datetime import datetime
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


def _parse_edge_timestamp(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            s = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            pass

    return None



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