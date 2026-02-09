
"""
mmWave sensor integration for Raspberry Pi using rd03d library.
"""

import time
import csv
from datetime import datetime
from rd03d import RD03D

def mmwave_detect():
    print("[mmWave] Initializing RD03D mmWave sensor...")
    radar = RD03D(uart_port='/dev/ttyAMA0', baudrate=256000, multi_mode=False)
    print("[mmWave] Waiting for sensor data...")
    import os
    csv_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'mmwave')
    os.makedirs(csv_dir, exist_ok=True)
    csv_path = os.path.join(csv_dir, "mmwave_logistic_data.csv")
    with open(csv_path, mode="a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        # Write header if file is empty
        if csvfile.tell() == 0:
            writer.writerow(["timestamp", "presence", "distance", "angle", "speed", "x", "y"])
        try:
            while True:
                if radar.update():
                    target1 = radar.get_target(1)
                    presence = 1 if target1.distance > 0 else 0
                    row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), presence, target1.distance, target1.angle, target1.speed, target1.x, target1.y]
                    writer.writerow(row)
                    print(f"[mmWave] Logged: {row}")
                else:
                    print("[mmWave] No radar data received.")
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("[mmWave] Stopped by user.")

if __name__ == "__main__":
    mmwave_detect()