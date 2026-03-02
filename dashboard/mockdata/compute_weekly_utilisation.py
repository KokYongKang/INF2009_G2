from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

from db import get_db
from utils import utcnow_naive

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
OCCUPIED_STATES = {"Occupied", "Full", "Overcapacity"}  # treat as occupied


def monday_start(dt: datetime) -> datetime:
    start = dt - timedelta(days=dt.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def safe_dt(val) -> Optional[datetime]:
    """Handle Mongo datetime OR string timestamps."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=None) if val.tzinfo else val
    if isinstance(val, str):
        s = val.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                pass
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except Exception:
            return None
    return None


def compute_occupied_minutes_for_day(
    events: List[Tuple[datetime, str]], day0: datetime, day1: datetime
) -> int:
    """
    events: sorted list of (timestamp, state_str) for ONE room (or any consistent stream)
    Assume state carries forward until next event.
    Default state is Vacant if no prior info.
    """
    total = 0
    current_state = "Vacant"
    current_time = day0

    for ts, state in events:
        if ts < day0:
            # prior state before day start
            current_state = state
            continue
        if ts >= day1:
            break

        # accumulate from current_time -> ts
        if current_state in OCCUPIED_STATES:
            total += int((ts - current_time).total_seconds() // 60)

        current_time = ts
        current_state = state

    # tail of the day
    if current_state in OCCUPIED_STATES:
        total += int((day1 - current_time).total_seconds() // 60)

    return max(0, min(1440, total))


def compute_overall_week_utilisation(week_start: datetime) -> Dict[str, int]:
    """
    Overall utilisation across all rooms (12 rooms) = average occupied minutes across rooms.

    For each day:
      total_occ_minutes = sum(occupied_minutes_per_room)
      utilisation% = total_occ_minutes / (1440 * num_rooms) * 100

    IMPORTANT:
    - Future days (after 'today') are forced to 0, so we don't "predict" utilisation.
    """
    db = get_db()
    week_end = week_start + timedelta(days=7)
    now = utcnow_naive()

    # Get all room ids (denominator = number of configured rooms)
    rooms = list(db.rooms.find({}, {"_id": 0, "room_id": 1}).sort("room_id", 1))
    room_ids = [r["room_id"] for r in rooms]
    n_rooms = max(1, len(room_ids))  # avoid divide by zero

    # Pull occupancy evaluation logs for all rooms within the week
    raw = list(
        db.event_logs.find(
            {
                "room_id": {"$in": room_ids},
                "timestamp": {"$gte": week_start, "$lt": week_end},
                "event": {"$regex": "Occupancy status evaluated", "$options": "i"},
            },
            {"_id": 0, "room_id": 1, "timestamp": 1, "value": 1},
        ).sort("timestamp", 1)
    )

    values: Dict[str, int] = {}

    for i, day in enumerate(DAYS):
        day0 = week_start + timedelta(days=i)
        day1 = day0 + timedelta(days=1)

        # ✅ Do not compute future days (avoid filling Tue–Sun when it's still Monday)
        if day0.date() > now.date():
            values[day] = 0
            continue

        total_occ = 0

        for rid in room_ids:
            room_events = [
                (safe_dt(e.get("timestamp")), str(e.get("value") or "").strip())
                for e in raw
                if e.get("room_id") == rid
            ]
            room_events = [(t, s) for t, s in room_events if t and s]
            room_events.sort(key=lambda x: x[0])

            total_occ += compute_occupied_minutes_for_day(room_events, day0, day1)

        util = int(round((total_occ / (1440 * n_rooms)) * 100))
        values[day] = util

    return values


def upsert_overall_week(values: Dict[str, int], week_start: datetime):
    db = get_db()
    now = utcnow_naive()

    db.weekly_utilisation.update_one(
        {
            "scope": "overall",
            "room_id": None,
            "week_start": week_start.strftime("%Y-%m-%d %H:%M"),
        },
        {"$set": {
            "scope": "overall",
            "room_id": None,
            "week_start": week_start.strftime("%Y-%m-%d %H:%M"),
            "values": values,
            "updated_at": now.strftime("%Y-%m-%d %H:%M"),
        }},
        upsert=True,
    )


def compute_and_store_current_week():
    now = utcnow_naive()
    ws = monday_start(now)
    values = compute_overall_week_utilisation(ws)
    upsert_overall_week(values, ws)
    print("✅ Updated overall weekly utilisation for week_start:", ws.strftime("%Y-%m-%d %H:%M"))


if __name__ == "__main__":
    compute_and_store_current_week()