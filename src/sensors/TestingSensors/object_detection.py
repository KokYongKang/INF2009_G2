import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from datetime import datetime
import time
from pathlib import Path


CAMERA_WIDTH = 320
CAMERA_HEIGHT = 240
STORE_INTERVAL = 4.0  # seconds
BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "blaze_face_short_range.tflite"
LOG_FILE = BASE_DIR / "headcount_log.csv"


base_options = python.BaseOptions(model_asset_path=str(MODEL_PATH))
options = vision.FaceDetectorOptions(
    base_options=base_options,
    min_detection_confidence=0.5  # adjust if needed
)
detector = vision.FaceDetector.create_from_options(options)


cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

last_store_time = time.time()


while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame")
        break

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

    detection_result = detector.detect(mp_image)

    face_count = len(detection_result.detections) if detection_result.detections else 0

    # Overlay headcount on frame
    cv2.putText(
        frame,
        f"Headcount: {face_count}",
        (10, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    current_time = time.time()
    if current_time - last_store_time >= STORE_INTERVAL:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a") as f:
            f.write(f"{timestamp},{face_count}\n")
        last_store_time = current_time

    cv2.imshow("Face Detection - MediaPipe Tasks", frame)

    # Exit on ESC
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
detector.close()