import os, sys

# Add /dashboard (parent of /mockdata) into Python import path
DASHBOARD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if DASHBOARD_DIR not in sys.path:
    sys.path.insert(0, DASHBOARD_DIR)

from datetime import datetime, timedelta
from utils import utcnow_naive
import argparse

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from db import get_db

ROOMS_12 = [f"SIT-DR-{i:02d}" for i in range(1, 13)]

def make_logs(room_id: str, now: datetime):
    scenarios = {
        "SIT-DR-01": (1, 3, "Occupied"),
        "SIT-DR-02": (0, 0, "Vacant"),
        "SIT-DR-03": (0, 0, "Vacant"),
        "SIT-DR-04": (1, 8, "Overcapacity"),
        "SIT-DR-05": (1, 2, "Occupied"),
        "SIT-DR-06": (1, 6, "Full"),
        "SIT-DR-07": (1, 5, "Occupied"),
        "SIT-DR-08": (1, 2, "Occupied"),
        "SIT-DR-09": (1, 0, "Occupied"),
        "SIT-DR-10": (1, 10, "Full"),
        "SIT-DR-11": (1, 1, "Occupied"),
        "SIT-DR-12": (0, 0, "Vacant"),
    }

    mmwave_val, cam_val, status_val = scenarios.get(room_id, (0, 0, "Vacant"))

    booking_context = ""
    if room_id in {"SIT-DR-02"}:
        booking_context = " (no-show)"
    elif room_id in {"SIT-DR-05"}:
        booking_context = " (overstay)"
    elif room_id in {"SIT-DR-07"}:
        booking_context = " (walk-in)"
    elif room_id in {"SIT-DR-08"}:
        booking_context = " (booking later)"
    elif room_id in {"SIT-DR-09"}:
        booking_context = " (sensor mismatch)"

    return [
        {
            "room_id": room_id,
            "timestamp": now - timedelta(minutes=18),
            "source": "mmWave",
            "event": ("mmWave presence detected" if mmwave_val else "mmWave no presence") + booking_context,
            "value": mmwave_val,
        },
        {
            "room_id": room_id,
            "timestamp": now - timedelta(minutes=17),
            "source": "Camera",
            "event": "Camera headcount updated" + booking_context,
            "value": cam_val,
        },
        {
            "room_id": room_id,
            "timestamp": now - timedelta(minutes=5),
            "source": "Fusion",
            "event": "Occupancy status evaluated" + booking_context,
            "value": status_val,
        },
    ]

def main(force: bool):
    db = get_db()
    col = db.event_logs
    col.create_index([("room_id", 1), ("timestamp", -1)])

    now = utcnow_naive()

    inserted = skipped_rooms = deleted = 0

    for rid in ROOMS_12:
        if force:
            res = col.delete_many({"room_id": rid})
            deleted += res.deleted_count
        else:
            if col.count_documents({"room_id": rid}, limit=1) > 0:
                skipped_rooms += 1
                continue

        logs = make_logs(rid, now)
        res = col.insert_many(logs)
        inserted += len(res.inserted_ids)

    print(f"✅ event_logs seeded: inserted={inserted}, skipped_rooms={skipped_rooms}, deleted={deleted}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Delete + reseed logs for these rooms")
    args = parser.parse_args()
    main(args.force)