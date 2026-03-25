# --- Simple mmWave + webcam fusion ---
from threading import Thread
from datetime import datetime
import time
import os
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from individualsensors.mmwave_sensor import MmwaveSensor
from individualsensors.object_detection_sensor import ObjectDetectionSensor
import requests

from profile_utils import profile_main
"""
Enhanced sensor_fusion.py
- Real-time sensor monitoring
- Analytics/AI integration 
- Occupancy status output
- Dashboard update callback
"""

# --- MediaPipe face detection utility ---
def analyze_webcam(image_path, detector=None, log_file=None):
    """MediaPipe face detection: Returns True if a face is detected in the image. Logs headcount if log_file is provided."""
    if image_path and os.path.exists(image_path):
        img = cv2.imread(image_path)
        if img is None:
            return False
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_img)
        if detector is None:
            # Setup MediaPipe detector (default model path, can be customized)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            model_path = os.path.join(base_dir, "models", "efficientdet_lite0.tflite")
            base_options = python.BaseOptions(model_asset_path=model_path)
            options = vision.ObjectDetectorOptions(base_options=base_options, score_threshold=0.5, max_results=10)
            detector = vision.ObjectDetector.create_from_options(options)
        detection_result = detector.detect(mp_image)
        face_count = len(detection_result.detections) if detection_result.detections else 0
        if log_file is not None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_file, "a") as f:
                f.write(f"{timestamp},{face_count}\n")
        if face_count > 0:
            print(f"[Webcam] Face(s) detected in {image_path}: {face_count}")
            return True
        else:
            print(f"[Webcam] No face detected in {image_path}")
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
        self._presence_hold_until = 0
        self.vision = ObjectDetectionSensor(enable_display=False)
        self.mmwave = MmwaveSensor(log_interval=5)
        # Cache for last sent values
        self._last_sent_presence = None
        self._last_sent_headcount = None

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
        # --- Full-cycle RTT start ---
        full_cycle_start = time.time()

        presence, distance = self.mmwave.get_presence_and_distance()

        now = time.time()
        if presence:
            self._presence_hold_until = now + 5   # keep vision alive 5s after last detection
        
        if now < self._presence_hold_until:
            self.vision.enable()
        else:
            self.vision.disable()

        person_count = self.vision.get_headcount()
        occupancy = presence or person_count > 0
        self.status = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'mmwave_presence': presence,
            'occupancy': occupancy,
            'usage_metrics': self.compute_usage_metrics(occupancy),
            'headcount': person_count,
        }
        # Only send update if presence or headcount changed
        if self.dashboard_callback:
            if (self._last_sent_presence != presence) or (self._last_sent_headcount != person_count):
                self.dashboard_callback(self.status, full_cycle_start)
                self._last_sent_presence = presence
                self._last_sent_headcount = person_count
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
        self.vision.start()
        Thread(target=self._event_loop, daemon=True).start()

    def stop(self):
        self.running = False
        self.vision.stop()
        self.mmwave.stop_logging()

    def _event_loop(self):
        while self.running:
            self.fuse_and_analyze()
            time.sleep(self.poll_interval)

if __name__ == "__main__":
    # Dashboard callback function
    def dashboard_callback(status, full_cycle_start=None):
        """Send live sensor data to dashboard and measure RTTs asynchronously."""
        def send_update():
            import time
            print(f"[DEBUG] Sending status to dashboard: {status}")
            try:
                dashboard_url = 'http://192.168.137.1:5000/api/sensor-update'
                network_start = time.time()
                response = requests.post(
                    dashboard_url,
                    json=status,
                    timeout=2
                )
                network_end = time.time()
                network_rtt_ms = (network_end - network_start) * 1000
                # Full-cycle RTT: from start of fuse_and_analyze to after dashboard response
                if full_cycle_start is not None:
                    full_cycle_rtt_ms = (network_end - full_cycle_start) * 1000
                    print(f"Dashboard update: {response.status_code} | Network RTT: {network_rtt_ms:.2f} ms | Full-cycle RTT: {full_cycle_rtt_ms:.2f} ms")
                else:
                    print(f"Dashboard update: {response.status_code} | Network RTT: {network_rtt_ms:.2f} ms")
            except Exception as e:
                print(f"Dashboard connection failed: {e}")
        Thread(target=send_update, daemon=True).start()

    def main():
        fusion = SensorFusion(dashboard_callback=dashboard_callback)
        fusion.start()
        try:
            while True:
                time.sleep(2)
        except KeyboardInterrupt:
            fusion.stop()
            print("[Fusion] Monitoring stopped.")

    # Use profile_utils to run profiling
    profile_main(
        main,
        extra_functions=[SensorFusion.fuse_and_analyze, dashboard_callback]
    )