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
import requests

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
        self.mmwave = MmwaveSensor(log_interval=5)

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
        # Use MediaPipe face detection 
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
            'headcount': 1 if webcam_person else 0,
            'faces_detected': 1 if webcam_person else 0
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

    def _event_loop(self):
        print("mmWave monitoring for presence...")
        # Setup MediPipe face detector once for efficiency
        base_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(base_dir, "individualsensors", "models", "blaze_face_short_range.tflite")
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.5)
        detector = vision.FaceDetector.create_from_options(options)
        # Headcount log file path
        log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'images', 'headcount_log.csv')
        while self.running:
            presence, distance = self.mmwave.get_presence_and_distance()
            if presence:
                print("mmWave detected presence! Activating Webcam")
                try:
                    images_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'images')
                    os.makedirs(images_dir, exist_ok=True)
                    cap = cv2.VideoCapture(0)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    person_detected = False
                    end_time = time.time() + 10  # Activate webcam for 10 seconds
                    frame_count = 0
                    while time.time() < end_time and self.running:
                        ret, frame = cap.read()
                        if ret:
                            frame_count += 1
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                            detection_result = detector.detect(mp_image)

                            person_count = 0

                            if detection_result.detections:
                                for detection in detection_result.detections:
                                    category = detection.categories[0]
                                    if category.category_name == "person":
                                        person_count += 1

                                        bbox = detection.bounding_box
                                        x, y, w, h = bbox.origin_x, bbox.origin_y, bbox.width, bbox.height

                                        cv2.rectangle(
                                        frame,
                                        (x, y),
                                        (x + w, y + h),
                                        (0, 255, 0),
                                        2
                                        )

                            # Log person count for each frame
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            with open(log_file, "a") as f:
                                f.write(f"{timestamp},{person_count}\n")
                            # Overlay person count on frame
                            cv2.putText(
                                frame,
                                f"No. of people: {person_count}",
                                (10, 40),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                1,
                                (0, 255, 0),
                                2
                            )
                            cv2.imshow("Person Detection - MediaPipe", frame)
                            # Allow exit on ESC
                            if cv2.waitKey(1) & 0xFF == 27:
                                print("ESC pressed, exiting webcam early.")
                                break
                            if person_count > 0:
                                print(f"MediaPipe: People detected in frame {frame_count}: {person_count}")
                                person_detected = True
                        else:
                            print("Failed to capture webcam frame.")
                    cap.release()
                    cv2.destroyAllWindows()
                    if person_detected:
                        print("Occupancy set: Face detected by MediaPipe.")
                        self.status['webcam_person'] = True
                        self.status['occupancy'] = True
                    else:
                        print("No face detected by MediaPipe.")
                        self.status['webcam_person'] = False
                except Exception as e:
                    print(f"Webcam/MediaPipe error: {e}")
                print("Monitoring period ended. Returning to mmWave listening.")
            # Always sleep for poll_interval at the end of each loop
            self.fuse_and_analyze()  # Update status and dashboard every loop
            time.sleep(self.poll_interval)

if __name__ == "__main__":
    # Dashboard callback function
    def dashboard_callback(status):
        """Send live sensor data to dashboard"""
        print(f"[DEBUG] Sending status to dashboard: {status}")
        try:
            # Update this with your laptop's IP address
            dashboard_url = 'http://LAPTOPIP:5000/api/sensor-update'
            response = requests.post(
                dashboard_url,
                json=status,
                timeout=2
            )
            print(f"Dashboard update: {response.status_code}")
        except Exception as e:
            print(f"Dashboard connection failed: {e}")
    
    fusion = SensorFusion(dashboard_callback=dashboard_callback)
    fusion.start()
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        fusion.stop()
        print("[Fusion] Monitoring stopped.")