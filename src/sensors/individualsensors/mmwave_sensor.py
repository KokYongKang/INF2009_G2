# mmwave_sensor.py
import os
import csv
from datetime import datetime
from datetime import timezone, timedelta
from individualsensors.rd03d import RD03D
import threading
import time

MMWAVE_DISTANCE_THRESHOLD = 55000 # mm, adjust as needed

class MmwaveSensor:
    def __init__(self, uart_port='/dev/ttyAMA0', baudrate=256000, multi_mode=False, log_interval=5.0):
        self.radar = RD03D(uart_port=uart_port, baudrate=baudrate, multi_mode=multi_mode)
        self._log_thread = None
        self._log_running = False
        self._latest_presence = 0
        self._latest_distance = 0
        self.log_interval = log_interval

    def get_presence_and_distance(self):
        return self._latest_presence, self._latest_distance

    def _log_loop(self):
        while self._log_running:
            presence, distance = 0, 0
            if self.radar.update():
                target = self.radar.get_target(1)
                if target and target.distance > 0 and target.distance <= MMWAVE_DISTANCE_THRESHOLD:
                    presence, distance = 1, target.distance
                elif target:
                    presence, distance = 0, target.distance
            self._latest_presence = presence
            self._latest_distance = distance
            self.log_to_csv(presence, distance)
            time.sleep(self.log_interval)  # Log at configurable interval

    def start_logging(self):
        if not self._log_running:
            self._log_running = True
            self._log_thread = threading.Thread(target=self._log_loop, daemon=True)
            self._log_thread.start()

    def stop_logging(self):
        self._log_running = False
        if self._log_thread:
            self._log_thread.join()

    def log_to_csv(self, presence, distance):
        # Dynamically find the INF2009_G2 project root
        current = os.path.abspath(os.path.dirname(__file__))
        while True:
            if os.path.isdir(os.path.join(current, 'data')) and os.path.basename(current) == 'INF2009_G2':
                project_root = current
                break
            parent = os.path.dirname(current)
            if parent == current:
                raise RuntimeError("INF2009_G2 project root not found.")
            current = parent
        csv_dir = os.path.join(project_root, 'data', 'mmwave')
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, "mmwave_logistic_data.csv")
        try:
            write_header = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0
            with open(csv_path, mode="a", newline="") as csvfile:
                writer = csv.writer(csvfile)
                if write_header:
                    writer.writerow(["timestamp", "presence", "distance"])
                writer.writerow([
                    datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S.%f"),
                    presence,
                    distance
                ])
        except Exception as e:
            print(f"[mmWave][ERROR] Failed to log to CSV: {e}")

    def close(self):
        self.stop_logging()
        self.radar.close()
