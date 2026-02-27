# api_service.py
from db import get_db
from utils import utcnow_naive

def process_sensor_update(payload: dict):
    """
    Expected payload:
      - headcount: int
      - mmwave_presence: bool/int
    """
    db = get_db()
    now = utcnow_naive()

    room_id = "SIT-DR-01"
    headcount = int(payload.get("headcount", 0) or 0)
    mmwave_presence = 1 if payload.get("mmwave_presence") else 0

    # Update latest state
    state_update = {
        "room_id": room_id,
        "data_source": "Live",
        "headcount": headcount,
        "mmwave_presence": mmwave_presence,
        "last_updated": now,
        "last_mmwave_update": now,
        "last_camera_update": now,
    }

    db.room_state.update_one({"room_id": room_id}, {"$set": state_update}, upsert=True)

    # Append event logs
    db.event_logs.insert_many([
        {
            "room_id": room_id,
            "timestamp": now,
            "source": "mmWave",
            "event": "mmWave presence updated",
            "value": mmwave_presence,
        },
        {
            "room_id": room_id,
            "timestamp": now,
            "source": "Camera",
            "event": "Camera headcount updated",
            "value": headcount,
        },
    ])

    return state_update