import os, sys

# Add /dashboard (parent of /mockdata) into Python import path
DASHBOARD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if DASHBOARD_DIR not in sys.path:
    sys.path.insert(0, DASHBOARD_DIR)


from datetime import datetime, timezone
from utils import utcnow_naive
import argparse

# allow "from db import get_db" when running this file directly
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from db import get_db

# BASE_ROOMS = [
#     {"room_id": "SIT-DR-01", "room_name": "SIT DR-01", "capacity": 6},
#     {"room_id": "SIT-DR-02", "room_name": "SIT DR-02", "capacity": 6},
#     {"room_id": "SIT-DR-03", "room_name": "SIT DR-03", "capacity": 8},
#     {"room_id": "SIT-DR-04", "room_name": "SIT DR-04", "capacity": 6},
#     {"room_id": "SIT-DR-05", "room_name": "SIT DR-05", "capacity": 10},
# ]

BASE_ROOMS = [
    {"room_id": "SIT-DR-01", "room_name": "SIT DR-01", "capacity": 6},
    {"room_id": "SIT-DR-02", "room_name": "SIT DR-02", "capacity": 6},
    {"room_id": "SIT-DR-03", "room_name": "SIT DR-03", "capacity": 8},
    {"room_id": "SIT-DR-04", "room_name": "SIT DR-04", "capacity": 6},
    {"room_id": "SIT-DR-05", "room_name": "SIT DR-05", "capacity": 10},

    {"room_id": "SIT-DR-06", "room_name": "SIT DR-06", "capacity": 6},
    {"room_id": "SIT-DR-07", "room_name": "SIT DR-07", "capacity": 8},
    {"room_id": "SIT-DR-08", "room_name": "SIT DR-08", "capacity": 6},
    {"room_id": "SIT-DR-09", "room_name": "SIT DR-09", "capacity": 6},
    {"room_id": "SIT-DR-10", "room_name": "SIT DR-10", "capacity": 10},
    {"room_id": "SIT-DR-11", "room_name": "SIT DR-11", "capacity": 8},
    {"room_id": "SIT-DR-12", "room_name": "SIT DR-12", "capacity": 6},
]

def main(force: bool):
    db = get_db()
    col = db.rooms
    col.create_index("room_id", unique=True)

    now = utcnow_naive()
    inserted = updated = skipped = 0

    for r in BASE_ROOMS:
        existing = col.find_one({"room_id": r["room_id"]})
        if existing and not force:
            skipped += 1
            continue

        doc = {
            "room_id": r["room_id"],
            "room_name": r["room_name"],
            "capacity": int(r["capacity"]),
            "updated_at": now,
        }
        res = col.update_one(
            {"room_id": r["room_id"]},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        if res.upserted_id:
            inserted += 1
        else:
            updated += 1

    print(f"✅ rooms seeded: inserted={inserted}, updated={updated}, skipped={skipped}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Overwrite the 5 base rooms if they already exist")
    args = parser.parse_args()
    main(args.force)