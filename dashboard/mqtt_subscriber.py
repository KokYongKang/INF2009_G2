# MQTT subscriber for dashboard
# Listens to rooms/+/headcount and processes updates as if they were HTTP POSTs

import os
import json
import paho.mqtt.client as mqtt
from datetime import datetime
from db import get_db
from utils import utcnow_naive
from app import _parse_edge_timestamp

MQTT_BROKER = "192.168.137.18"
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", None)
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", None)

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected with result code {rc}")
    client.subscribe("rooms/+/headcount")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        room_id = payload.get("room_id", "SIT-DR-01")
        event_id = str(payload.get("event_id", "") or "").strip()
        headcount = int(payload.get("headcount", 0) or 0)
        mmwave_presence = 1 if bool(payload.get("mmwave_presence", False)) else 0
        occupancy = 1 if bool(payload.get("occupancy", mmwave_presence == 1 or headcount > 0)) else 0
        now = utcnow_naive()
        raw_event_time = _parse_edge_timestamp(payload.get("event_timestamp"))
        event_time = _to_naive_utc(raw_event_time) or now
        db = get_db()
        if event_id:
            existing = db["sensor_history"].find_one({"event_id": event_id}, {"_id": 1})
            if existing:
                print(f"[MQTT] Duplicate event_id {event_id}, skipping.")
                return
        db["room_state"].update_one(
            {"room_id": room_id},
            {"$set": {
                "room_id": room_id,
                "data_source": "Live",
                "headcount": headcount,
                "mmwave_presence": mmwave_presence,
                "occupancy": occupancy,
                "last_updated": event_time,
                "last_mmwave_update": event_time,
                "last_camera_update": event_time,
                "last_synced_at": now,
            }},
            upsert=True
        )
        print(f"[MQTT][DEBUG] Updated room_state for {room_id}")

        # Write live event logs for dashboard
        event_log_entries = [
            {
                "room_id": room_id,
                "timestamp": event_time,
                "event": "mmWave presence detected" if mmwave_presence else "mmWave no presence",
                "source": "mmWave",
                "value": mmwave_presence,
            },
            {
                "room_id": room_id,
                "timestamp": event_time,
                "event": "Camera headcount updated",
                "source": "Camera",
                "value": headcount,
            },
            {
                "room_id": room_id,
                "timestamp": event_time,
                "event": "Occupancy status evaluated",
                "source": "Fusion",
                "value": "Occupied" if occupancy else "Vacant",
            },
        ]
        db["event_logs"].insert_many(event_log_entries)

        sensor_doc = {
            "event_id": event_id or None,
            "room_id": room_id,
            "timestamp": event_time,
            "headcount": headcount,
            "mmwave_presence": mmwave_presence,
            "occupancy": occupancy,
            "synced_at": now,
        }
        print(f"[MQTT][DEBUG] About to insert into sensor_history: {sensor_doc}")
        db["sensor_history"].insert_one(sensor_doc)
        print(f"[MQTT][DEBUG] Inserted into sensor_history for {room_id} event_id={event_id}")
        print(f"[MQTT] Processed update for {room_id} headcount={headcount} mmwave={mmwave_presence} occupancy={occupancy}")
    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")

if __name__ == "__main__":
    client = mqtt.Client()
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    print(f"[MQTT] Subscribing to rooms/+/headcount on {MQTT_BROKER}:{MQTT_PORT}")
    client.loop_forever()
