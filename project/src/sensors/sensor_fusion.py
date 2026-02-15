# --- Simple sound detection stub ---
from threading import Thread
from datetime import datetime
import time
import csv
import os
import sounddevice as sd
import numpy as np


def detect_sound(threshold=1000, duration=1, samplerate=16000):
    """Detects if sound exceeds threshold in a short sample."""
    audio = sd.rec(int(duration * samplerate),
                   samplerate=samplerate, channels=1, dtype='int16')
    sd.wait()
    rms = np.sqrt(np.mean(audio**2))
    return rms > threshold


"""
Enhanced sensor_fusion.py
- Real-time sensor monitoring
- Analytics/AI integration hooks
- Occupancy status output
- Dashboard update callback stub
"""

# Example: paths to sensor data
MMWAVE_CSV = os.path.join(os.path.dirname(os.path.dirname(
    __file__)), 'data', 'mmwave', 'mmwave_logistic_data.csv')
WEBCAM_IMG_DIR = os.path.join(os.path.dirname(
    os.path.dirname(__file__)), 'data', 'images')
AUDIO_PATH = os.path.join(os.path.dirname(os.path.dirname(
    __file__)), 'data', 'audio', 'microphone_capture.wav')

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
    """Stub: Run person detection on image. Returns True if person detected."""
    # TODO: Integrate AI model here
    return None  # Placeholder


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

    def read_mmwave_latest(self):
        try:
            with open(MMWAVE_CSV, 'r') as f:
                rows = list(csv.DictReader(f))
                return rows[-1] if rows else None
        except Exception:
            return None

    def get_latest_webcam_image(self):
        try:
            images = [f for f in os.listdir(
                WEBCAM_IMG_DIR) if f.endswith('.jpg')]
            if not images:
                return None
            latest = max(images, key=lambda x: os.path.getmtime(
                os.path.join(WEBCAM_IMG_DIR, x)))
            return os.path.join(WEBCAM_IMG_DIR, latest)
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
            if detect_sound():
                print(
                    "[Fusion] Sound detected! Activating mmWave and webcam monitoring...")
                # Monitor mmWave and webcam for 60 seconds
                end_time = time.time() + 60
                while time.time() < end_time and self.running:
                    self.fuse_and_analyze()
                    time.sleep(self.poll_interval)
                print(
                    "[Fusion] Monitoring period ended. Returning to microphone listening.")
            else:
                time.sleep(0.5)

# --- Example dashboard update callback ---


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
