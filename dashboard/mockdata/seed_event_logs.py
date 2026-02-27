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

ROOMS_5 = ["SIT-DR-01", "SIT-DR-02", "SIT-DR-03", "SIT-DR-04", "SIT-DR-05"]

def make_logs(room_id: str, now: datetime):
    if room_id == "SIT-DR-01":
        mmwave_val, cam_val, status_val = 1, 3, "Occupied"
    elif room_id == "SIT-DR-02":
        mmwave_val, cam_val, status_val = 0, 0, "Vacant"
    elif room_id == "SIT-DR-03":
        mmwave_val, cam_val, status_val = 0, 0, "Vacant"
    elif room_id == "SIT-DR-04":
        mmwave_val, cam_val, status_val = 1, 6, "Full"
    else:
        mmwave_val, cam_val, status_val = 1, 2, "Occupied"

    return [
        {
            "room_id": room_id,
            "timestamp": now - timedelta(minutes=18),
            "source": "mmWave",
            "event": "mmWave presence detected" if mmwave_val else "mmWave no presence",
            "value": mmwave_val,
        },
        {
            "room_id": room_id,
            "timestamp": now - timedelta(minutes=17),
            "source": "Camera",
            "event": "Camera headcount updated",
            "value": cam_val,
        },
        {
            "room_id": room_id,
            "timestamp": now - timedelta(minutes=5),
            "source": "Fusion",
            "event": "Occupancy status evaluated",
            "value": status_val,
        },
    ]

def main(force: bool):
    db = get_db()
    col = db.event_logs
    col.create_index([("room_id", 1), ("timestamp", -1)])

    now = utcnow_naive()
    inserted = skipped_rooms = deleted = 0

    for rid in ROOMS_5:
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
    parser.add_argument("--force", action="store_true", help="Delete + reseed logs for these 5 rooms")
    args = parser.parse_args()
    main(args.force)