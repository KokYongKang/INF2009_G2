# --- Simple mmWave + webcam fusion ---
from threading import Thread, Lock
from datetime import datetime, timezone, timedelta
import time
import os
import uuid
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from individualsensors.mmwave_sensor import MmwaveSensor
from individualsensors.object_detection_sensor import ObjectDetectionSensor

import paho.mqtt.client as mqtt

from profile_utils import profile_main
from edge_cache import EdgeCache

"""
Enhanced sensor_fusion.py
- keeps your original local fusion logic
- keeps "only send when changed"
- adds local edge cache on the Pi
- adds retry queue for failed dashboard sync
"""

LIVE_ROOM_ID = os.getenv("LIVE_ROOM_ID", "SIT-DR-01")

# MQTT setup
MQTT_BROKER = "192.168.137.18"
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", None)
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", None)

mqtt_client = mqtt.Client()
if MQTT_USERNAME and MQTT_PASSWORD:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)


def analyze_webcam(image_path, detector=None, log_file=None):
    """MediaPipe face detection: Returns True if a face is detected in the image. Logs headcount if log_file is provided."""
    if image_path and os.path.exists(image_path):
        img = cv2.imread(image_path)
        if img is None:
            return False
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_img)
        if detector is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            model_path = os.path.join(base_dir, "models", "efficientdet_lite0.tflite")
            base_options = python.BaseOptions(model_asset_path=model_path)
            options = vision.ObjectDetectorOptions(
                base_options=base_options,
                score_threshold=0.5,
                max_results=10
            )
            detector = vision.ObjectDetector.create_from_options(options)
        detection_result = detector.detect(mp_image)
        face_count = len(detection_result.detections) if detection_result.detections else 0
        if log_file is not None:
            sg_tz = timezone(timedelta(hours=8))
            timestamp = datetime.now(sg_tz).strftime("%Y-%m-%d %H:%M:%S")
            with open(log_file, "a") as f:
                f.write(f"{timestamp},{face_count}\n")
        if face_count > 0:
            print(f"[Webcam] Face(s) detected in {image_path}: {face_count}")
            return True
        else:
            print(f"[Webcam] No face detected in {image_path}")
    return False


class SensorFusion:
    def __init__(self, poll_interval=1.0, dashboard_callback=None, room_id=LIVE_ROOM_ID):
        self.poll_interval = poll_interval
        self.dashboard_callback = dashboard_callback
        self.running = False
        self.room_id = room_id

        self.status = {
            "room_id": room_id,
            "timestamp": None,
            "mmwave_presence": False,
            "webcam_person": None,
            "occupancy": False,
            "usage_metrics": {},
            "headcount": 0,
            "last_mmwave_update": None,
            "last_camera_update": None,
        }

        self._presence_hold_until = 0
        self.vision = ObjectDetectionSensor(enable_display=False)
        self.mmwave = MmwaveSensor(log_interval=5)

        # keep original "only send when changed" behaviour
        self._last_sent_presence = None
        self._last_sent_headcount = None

        # new local edge cache
        self.edge_cache = EdgeCache(room_id=room_id, retention_minutes=60)

    def get_latest_webcam_image(self):
        images_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "images")
        try:
            images = [f for f in os.listdir(images_dir) if f.endswith(".jpg")]
            if not images:
                return None
            latest = max(images, key=lambda x: os.path.getmtime(os.path.join(images_dir, x)))
            return os.path.join(images_dir, latest)
        except Exception:
            return None

    def _now_iso_sg(self):
        sg_tz = timezone(timedelta(hours=8))
        return datetime.now(sg_tz).replace(microsecond=0).isoformat()

    def fuse_and_analyze(self):
        full_cycle_start = time.time()

        presence, distance = self.mmwave.get_presence_and_distance()

        now = time.time()
        if presence:
            self._presence_hold_until = now + 5

        if now < self._presence_hold_until:
            self.vision.enable()
        else:
            self.vision.disable()

        person_count = self.vision.get_headcount()
        occupancy = presence or person_count > 0
        event_timestamp = self._now_iso_sg()

        self.status = {
            "room_id": self.room_id,
            "timestamp": event_timestamp,
            "mmwave_presence": bool(presence),
            "occupancy": bool(occupancy),
            "usage_metrics": self.compute_usage_metrics(occupancy),
            "headcount": int(person_count),
            "last_mmwave_update": event_timestamp,
            "last_camera_update": event_timestamp,
            "distance": distance,
        }

        # always keep recent data on the edge
        self.edge_cache.save_latest_state(self.status)
        self.edge_cache.add_history_sample(self.status)

        # keep original trigger: only sync on meaningful changes
        changed = (
            self._last_sent_presence != presence or
            self._last_sent_headcount != person_count
        )

        if self.dashboard_callback and changed:
            self.edge_cache.add_change_logs(self.status)

            sync_payload = {
                "event_id": uuid.uuid4().hex,
                "room_id": self.room_id,
                "event_timestamp": event_timestamp,
                "headcount": int(person_count),
                "mmwave_presence": bool(presence),
                "occupancy": bool(occupancy),
            }

            # queue first, then try sending
            self.edge_cache.enqueue_unsent_update(sync_payload)
            self.dashboard_callback(sync_payload, full_cycle_start)

            self._last_sent_presence = presence
            self._last_sent_headcount = person_count

        return self.status

    def compute_usage_metrics(self, occupancy):
        if not hasattr(self, "_usage_count"):
            self._usage_count = 0
        if occupancy:
            self._usage_count += 1
        return {"usage_count": self._usage_count}

    def start(self):
        self.running = True
        self.mmwave.start_logging()
        self.vision.start()
        Thread(target=self._event_loop, daemon=True).start()
        Thread(target=self._sync_cached_updates, daemon=True).start()

    def stop(self):
        self.running = False
        self.vision.stop()
        self.mmwave.stop_logging()

    def _event_loop(self):
        while self.running:
            self.fuse_and_analyze()
            time.sleep(self.poll_interval)

    def _sync_cached_updates(self):
        while self.running:
            try:
                if self.dashboard_callback and self.edge_cache.pending_count() > 0:
                    self.dashboard_callback(None, None)
            except Exception as e:
                print(f"[EdgeSync] background flush trigger failed: {e}")
            time.sleep(2)


if __name__ == "__main__":
    fusion = None
    flush_lock = Lock()

    def post_status_to_dashboard(status, full_cycle_start=None):
        if not status:
            return
        topic = f"rooms/{status['room_id']}/headcount"
        import json
        payload = json.dumps(status)
        print(f"[DEBUG][MQTT] Publishing to {topic}: {payload}")
        network_start = time.time()
        mqtt_client.publish(topic, payload)
        network_end = time.time()
        network_rtt_ms = (network_end - network_start) * 1000
        if full_cycle_start is not None:
            full_cycle_rtt_ms = (network_end - full_cycle_start) * 1000
            print(
                f"MQTT publish | Network RTT: {network_rtt_ms:.2f} ms | "
                f"Full-cycle RTT: {full_cycle_rtt_ms:.2f} ms"
            )
        else:
            print(f"MQTT publish | Network RTT: {network_rtt_ms:.2f} ms")

    def flush_pending_queue(full_cycle_start=None):
        if fusion is None:
            return

        if not flush_lock.acquire(blocking=False):
            return

        try:
            pending = fusion.edge_cache.get_pending_updates(limit=20)
            if not pending:
                return

            first = True
            for item in pending:
                try:
                    post_status_to_dashboard(
                        item["payload"],
                        full_cycle_start if first else None
                    )
                    fusion.edge_cache.mark_update_sent(item["id"])
                    first = False
                except Exception as e:
                    fusion.edge_cache.mark_update_failed(item["id"], str(e))
                    print(f"Dashboard connection failed: {e}")
                    break
        finally:
            flush_lock.release()

    def dashboard_callback(status, full_cycle_start=None):
        # keep callback simple: just flush queued updates
        Thread(
            target=flush_pending_queue,
            args=(full_cycle_start,),
            daemon=True
        ).start()

    def main():
        global fusion
        fusion = SensorFusion(
            dashboard_callback=dashboard_callback,
            room_id=LIVE_ROOM_ID,
        )
        fusion.start()
        try:
            while True:
                time.sleep(2)
        except KeyboardInterrupt:
            fusion.stop()
            print("[Fusion] Monitoring stopped.")

    profile_main(
        main,
        extra_functions=[SensorFusion.fuse_and_analyze, dashboard_callback]
    )