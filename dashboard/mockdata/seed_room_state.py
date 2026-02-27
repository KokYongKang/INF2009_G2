# dashboard/mockdata/seed_room_state.py
import os, sys

# Add /dashboard (parent of /mockdata) into Python import path
DASHBOARD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if DASHBOARD_DIR not in sys.path:
    sys.path.insert(0, DASHBOARD_DIR)

    
import argparse
from datetime import datetime, timedelta
from utils import utcnow_naive

# Ensure we import db.py from /dashboard (parent folder)
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import db as db_module
from db import get_db

BASE_STATE = {
    "SIT-DR-01": {"data_source": "Live", "headcount": 3, "mmwave_presence": 1},
    "SIT-DR-02": {"data_source": "Mock", "headcount": 0, "mmwave_presence": 0},
    "SIT-DR-03": {"data_source": "Mock", "headcount": 0, "mmwave_presence": 0},
    "SIT-DR-04": {"data_source": "Mock", "headcount": 6, "mmwave_presence": 1},
    "SIT-DR-05": {"data_source": "Mock", "headcount": 2, "mmwave_presence": 1},
}


def main(force: bool):
    db = get_db()
    print("Using db.py at:", db_module.__file__)
    print("DB name:", db.name)

    col = db["room_state"]
    col.create_index("room_id", unique=True)

    now = utcnow_naive()

    inserted = updated = skipped = 0

    for room_id, s in BASE_STATE.items():
        existing = col.find_one({"room_id": room_id})

        if existing and not force:
            skipped += 1
            continue

        doc = {
            "room_id": room_id,
            "data_source": s["data_source"],
            "headcount": int(s["headcount"]),
            "mmwave_presence": int(s["mmwave_presence"]),
            "last_updated": now,
            "last_mmwave_update": now - timedelta(seconds=20),
            "last_camera_update": now - timedelta(seconds=35),
        }

        res = col.update_one({"room_id": room_id}, {"$set": doc}, upsert=True)

        if res.upserted_id is not None:
            inserted += 1
        else:
            updated += 1

    print(f"✅ room_state seeded: inserted={inserted}, updated={updated}, skipped={skipped}")
    print("room_state count now:", col.count_documents({}))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Overwrite/update docs if they already exist")
    args = parser.parse_args()
    main(args.force)