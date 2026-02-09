import time
import json
import sounddevice as sd
import soundfile as sf
import cv2
import numpy as np
from datetime import datetime

# --- mmWave Sensor Mock ---


def read_mmwave_sensor():
    # Simulate presence detection (replace with real sensor reading)
    return {'timestamp': datetime.now().isoformat(), 'presence': np.random.choice([True, False])}

# --- Microphone Data Collection ---


def record_audio(duration=2, samplerate=16000, channels=1):
    print("Recording audio...")
    audio = sd.rec(int(duration * samplerate),
                   samplerate=samplerate, channels=channels, dtype='int16')
    sd.wait()
    return audio, samplerate


def save_audio(audio, samplerate, folder):
    filename = datetime.now().strftime("%Y%m%d_%H%M%S.wav")
    filepath = f"{folder}/{filename}"
    sf.write(filepath, audio, samplerate)
    print(f"Saved audio: {filepath}")

# --- Webcam Data Collection ---


def capture_image(folder):
    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    if ret:
        filename = datetime.now().strftime("%Y%m%d_%H%M%S.jpg")
        filepath = f"{folder}/{filename}"
        cv2.imwrite(filepath, frame)
        print(f"Saved image: {filepath}")
    else:
        print("Failed to capture image.")
    cap.release()

# --- mmWave Data Logging ---


def save_mmwave(data, folder):
    filename = datetime.now().strftime("%Y%m%d_mmwave.json")
    filepath = f"{folder}/{filename}"
    with open(filepath, 'w') as f:
        json.dump(data, f)
    print(f"Saved mmWave data: {filepath}")


if __name__ == "__main__":
    audio_folder = "data/audio"
    image_folder = "data/images"
    mmwave_folder = "data/mmwave"

    while True:
        # 1. mmWave sensor
        mmwave_data = read_mmwave_sensor()
        save_mmwave(mmwave_data, mmwave_folder)

        # 2. Microphone
        audio, sr = record_audio(duration=2)
        save_audio(audio, sr, audio_folder)

        # 3. Webcam
        capture_image(image_folder)

        # Wait before next cycle
        time.sleep(10)  # Collect every 10 seconds
