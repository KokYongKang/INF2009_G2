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

BOOKED_ROOMS = {"SIT-DR-01", "SIT-DR-02", "SIT-DR-04", "SIT-DR-05"}
ALL_5 = ["SIT-DR-01", "SIT-DR-02", "SIT-DR-03", "SIT-DR-04", "SIT-DR-05"]

def main(force: bool):
    db = get_db()
    col = db.bookings
    col.create_index("room_id", unique=True)

    now = utcnow_naive()
    start_time = now - timedelta(minutes=5)
    end_time = now + timedelta(minutes=55)

    inserted = updated = skipped = deleted = 0

    for rid in ALL_5:
        if rid in BOOKED_ROOMS:
            existing = col.find_one({"room_id": rid})
            if existing and not force:
                skipped += 1
                continue

            doc = {
                "room_id": rid,
                "start_time": start_time,
                "end_time": end_time,
                "booked_by": "RBS reservation (mock)",
                "grace_period_mins": 10,
                "updated_at": now,
            }

            res = col.update_one({"room_id": rid}, {"$set": doc}, upsert=True)
            if res.upserted_id:
                inserted += 1
            else:
                updated += 1
        else:
            res = col.delete_many({"room_id": rid})
            deleted += res.deleted_count

    print(f"✅ bookings seeded: inserted={inserted}, updated={updated}, skipped={skipped}, deleted={deleted}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Overwrite bookings for these rooms if they already exist")
    args = parser.parse_args()
    main(args.force)