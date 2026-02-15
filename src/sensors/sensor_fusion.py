# --- Simple sound detection stub ---
from threading import Thread
from datetime import datetime
import time
import csv
import os
import sounddevice as sd
import numpy as np
import cv2
from ultralytics import YOLO

"""
Enhanced sensor_fusion.py
- Real-time sensor monitoring
- Analytics/AI integration 
- Occupancy status output
- Dashboard update callback
"""

# paths to sensor data
MMWAVE_CSV = os.path.join(os.path.dirname(os.path.dirname(
    __file__)), 'data', 'mmwave', 'mmwave_logistic_data.csv')
WEBCAM_IMG_DIR = os.path.join(os.path.dirname(
    os.path.dirname(__file__)), 'data', 'images')
AUDIO_PATH = os.path.join(os.path.dirname(os.path.dirname(
    __file__)), 'data', 'audio', 'microphone_capture.wav')

# --- Sensor thresholds and parameters ---
AUDIO_DEVICE = None  # Use default device
AUDIOTHRESHOLD = 0.05  # Adjust as needed for normalized audio

def detect_sound(threshold=1000, duration=1, samplerate=16000, device=None, log_rms=False):
    """Detects if sound exceeds threshold in a short sample."""
    audio = sd.rec(int(duration * samplerate),
                   samplerate=samplerate, channels=1, dtype='int16', device=device)
    sd.wait()
    if log_rms:
        print(f"[Fusion] Raw audio buffer: {audio.flatten()[:10]} ... (showing first 10 samples)")
    if audio is None or np.isnan(audio).any() or np.all(audio == 0):
        if log_rms:
            print("[Fusion] Warning: Invalid or silent audio buffer detected.")
        return False
    audio_float = audio.astype(np.float32) / 32768.0  # Normalize to [-1, 1]
    rms = np.sqrt(np.mean(audio_float**2))
    if log_rms:
        print(f"[Fusion] RMS={rms:.4f} threshold={threshold}")
    return rms > threshold

# --- Analytics/AI hooks (to be implemented by your AI team) ---
def analyze_mmwave(row):
    """Return True if presence detected from mmWave row."""
    if not row:
        return False
    try:
        return int(row.get('presence', 0)) > 0
    except Exception:
        return False


def analyze_webcam(image_path):
    """YOLO person detection: Returns True if a person is detected in the image."""
    import os, time
    if image_path and os.path.exists(image_path):
        mtime = os.path.getmtime(image_path)
        if time.time() - mtime < 60:
            try:
                from ultralytics import YOLO
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


def analyze_audio(audio_path):
    """Stub: Analyze audio for occupancy cues. Returns True if activity detected."""
    # TODO: Integrate audio analysis here
    return None  # Placeholder

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
            'audio_activity': None,
            'occupancy': False,
            'usage_metrics': {},
        }

    def get_latest_webcam_image(self):
        try:
            images = [f for f in os.listdir(WEBCAM_IMG_DIR) if f.endswith('.jpg')]
            if not images:
                return None
            latest = max(images, key=lambda x: os.path.getmtime(os.path.join(WEBCAM_IMG_DIR, x)))
            return os.path.join(WEBCAM_IMG_DIR, latest)
        except Exception:
            return None
        except Exception:
            return None

    def get_latest_audio_path(self):
        if os.path.exists(AUDIO_PATH):
            return AUDIO_PATH
        return None

    def fuse_and_analyze(self):
        mmwave_row = self.read_mmwave_latest()
        webcam_img = self.get_latest_webcam_image()
        audio = self.get_latest_audio_path()
        mmwave_presence = analyze_mmwave(mmwave_row)
        webcam_person = analyze_webcam(webcam_img)
        audio_activity = analyze_audio(audio)
        # Simple fusion logic: occupancy if any sensor detects presence
        occupancy = any([
            mmwave_presence,
            webcam_person is True,
            audio_activity is True
        ])
        self.status = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'mmwave_presence': mmwave_presence,
            'webcam_person': webcam_person,
            'audio_activity': audio_activity,
            'occupancy': occupancy,
            'usage_metrics': self.compute_usage_metrics(occupancy),
        }
        if self.dashboard_callback:
            self.dashboard_callback(self.status)
        return self.status

    def compute_usage_metrics(self, occupancy):
        # Example: simple usage counter (extend as needed)
        if not hasattr(self, '_usage_count'):
            self._usage_count = 0
        if occupancy:
            self._usage_count += 1
        return {'usage_count': self._usage_count}

    def start(self):
        self.running = True
        Thread(target=self._event_loop, daemon=True).start()

    def stop(self):
        self.running = False

    def _event_loop(self):
        print("[Fusion] Microphone listening for sound events...")
        while self.running:
            if detect_sound(threshold=AUDIOTHRESHOLD, device=AUDIO_DEVICE, log_rms=True):
                print("[Fusion] Sound detected! Activating mmWave and webcam monitoring...")
                # Real-time webcam and YOLO detection for 60 seconds
                try:
                    images_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'images')
                    os.makedirs(images_dir, exist_ok=True)
                    cap = cv2.VideoCapture(0)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    model = YOLO('yolov8n.pt')
                    yolo_person_detected = False
                    end_time = time.time() + 60
                    frame_count = 0
                    while time.time() < end_time and self.running:
                        ret, frame = cap.read()
                        if ret:
                            frame_count += 1
                            # Save frame for debugging/analysis (Will be Removed in final version)
                            #img_path = os.path.join(images_dir, f'webcam_image_{int(time.time())}_{frame_count}.jpg')
                            #cv2.imwrite(img_path, frame)
                            #print(f"[Fusion] Webcam image saved: {img_path}")
                            # Run YOLO detection directly on frame
                            results = model(frame)
                            for r in results:
                                for box in r.boxes:
                                    cls = int(box.cls[0])
                                    if cls == 0:
                                        print(f"[Fusion] YOLO: Person detected in frame {frame_count}")
                                        yolo_person_detected = True
                        else:
                            print("[Fusion] Failed to capture webcam frame.")
                        time.sleep(1)
                    cap.release()
                    if yolo_person_detected:
                        print("[Fusion] Occupancy set: Person detected by YOLO.")
                        self.status['webcam_person'] = True
                        self.status['occupancy'] = True
                    else:
                        print("[Fusion] No person detected by YOLO.")
                        self.status['webcam_person'] = False
                except Exception as e:
                    print(f"[Fusion] Webcam/YOLO error: {e}")
                print("[Fusion] Monitoring period ended. Returning to microphone listening.")
            else:
                time.sleep(0.5)

# --- Dashboard update callback ---
def dashboard_update(status):
    print(f"[Dashboard] Update: {status}")


# --- Example usage ---
if __name__ == "__main__":
    fusion = SensorFusion(
        poll_interval=2.0, dashboard_callback=dashboard_update)
    fusion.start()
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        fusion.stop()
        print("[Fusion] Monitoring stopped.")
