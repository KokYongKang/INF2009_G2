# --- Simple mmWave + webcam fusion ---
from threading import Thread
from datetime import datetime
import time
import os
import cv2
from ultralytics import YOLO
from TestingSensors.mmwave_sensor import MmwaveSensor

"""
Enhanced sensor_fusion.py
- Real-time sensor monitoring
- Analytics/AI integration 
- Occupancy status output
- Dashboard update callback
"""

def analyze_webcam(image_path):
    """YOLO person detection: Returns True if a person is detected in the image."""
    if image_path and os.path.exists(image_path):
        mtime = os.path.getmtime(image_path)
        if time.time() - mtime < 60:
            try:
                model = YOLO('yolov8n.pt')  # Use YOLOv8 nano for speed
                results = model(image_path) 
                for r in results:
                    for box in r.boxes:
                        cls = int(box.cls[0])
                        # COCO class 0 is 'person'
                        if cls == 0:
                            print(f"[Webcam] Person detected in {image_path}")
                            return True
                print(f"[Webcam] No person detected in {image_path}")
            except Exception as e:
                print(f"[Webcam] YOLO error: {e}")
    return False

# --- Real-time monitoring and fusion ---
class SensorFusion:
    def __init__(self, poll_interval=1.0, dashboard_callback=None):
        self.poll_interval = poll_interval
        self.dashboard_callback = dashboard_callback
        self.running = False
        self.status = {
            'timestamp': None,
            'mmwave_presence': False,
            'webcam_person': None,
            'occupancy': False,
            'usage_metrics': {},
        }
        self.mmwave = MmwaveSensor()

    def get_latest_webcam_image(self):
        images_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'images')
        try:
            images = [f for f in os.listdir(images_dir) if f.endswith('.jpg')]
            if not images:
                return None
            latest = max(images, key=lambda x: os.path.getmtime(os.path.join(images_dir, x)))
            return os.path.join(images_dir, latest)
        except Exception:
            return None

    def fuse_and_analyze(self):
        presence, distance = self.mmwave.get_presence_and_distance()
        webcam_img = self.get_latest_webcam_image()
        webcam_person = analyze_webcam(webcam_img)
        occupancy = any([
            presence,
            webcam_person is True
        ])
        self.status = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'mmwave_presence': presence,
            'webcam_person': webcam_person,
            'occupancy': occupancy,
            'usage_metrics': self.compute_usage_metrics(occupancy),
        }
        if self.dashboard_callback:
            self.dashboard_callback(self.status)
        return self.status

    def compute_usage_metrics(self, occupancy):
        if not hasattr(self, '_usage_count'):
            self._usage_count = 0
        if occupancy:
            self._usage_count += 1
        return {'usage_count': self._usage_count}

    def start(self):
        self.running = True
        self.mmwave.start_logging()
        Thread(target=self._event_loop, daemon=True).start()

    def stop(self):
        self.running = False
        self.mmwave.stop_logging()
        self.mmwave.close()

    def _event_loop(self):
        print("mmWave monitoring for presence...")
        while self.running:
            presence, distance = self.mmwave.get_presence_and_distance()
            self.mmwave.log_to_csv(presence, distance)
            if presence:
                print("mmWave detected presence! Activating Webcam")
                try:
                    images_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'images')
                    os.makedirs(images_dir, exist_ok=True)
                    cap = cv2.VideoCapture(0)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    model = YOLO('yolov8n.pt')
                    yolo_person_detected = False
                    end_time = time.time() + 10  # Activate webcam for 10 seconds
                    frame_count = 0
                    while time.time() < end_time and self.running:
                        ret, frame = cap.read()
                        if ret:
                            frame_count += 1
                            results = model(frame)
                            for r in results:
                                for box in r.boxes:
                                    cls = int(box.cls[0])
                                    if cls == 0:
                                        print(f"YOLO: Person detected in frame {frame_count}")
                                        yolo_person_detected = True
                        else:
                            print("Failed to capture webcam frame.")
                        time.sleep(1)
                    cap.release()
                    if yolo_person_detected:
                        print("Occupancy set: Person detected by YOLO.")
                        self.status['webcam_person'] = True
                        self.status['occupancy'] = True
                    else:
                        print("No person detected by YOLO.")
                        self.status['webcam_person'] = False
                except Exception as e:
                    print(f"Webcam/YOLO error: {e}")
                print("Monitoring period ended. Returning to mmWave listening.")
            else:
                time.sleep(self.poll_interval)

if __name__ == "__main__":
    fusion = SensorFusion()
    fusion.start()
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        fusion.stop()
        print("[Fusion] Monitoring stopped.")