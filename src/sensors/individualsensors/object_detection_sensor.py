import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import threading
import time
from pathlib import Path

class ObjectDetectionSensor:
    def __init__(
        self,
        camera_index=0,
        width=320,
        height=240,
        score_threshold=0.5,
        max_results=10,
        model_path=None,
        enable_display=False
    ):
        self.enabled = False
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.enable_display = enable_display

        self.running = False
        self.current_person_count = 0

        base_dir = Path(__file__).resolve().parent
        self.model_path = model_path or (base_dir / "models" / "efficientdet_lite0.tflite")

        base_options = python.BaseOptions(model_asset_path=str(self.model_path))
        options = vision.ObjectDetectorOptions(
            base_options=base_options,
            score_threshold=score_threshold,
            max_results=max_results
        )
        self.detector = vision.ObjectDetector.create_from_options(options)

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if hasattr(self, "cap"):
            self.cap.release()
        cv2.destroyAllWindows()
        self.detector.close()

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False
        self.current_person_count = 0

    def get_headcount(self):
        return self.current_person_count

    def _run(self):
        self.cap = cv2.VideoCapture(self.camera_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        while self.running:
            if not self.enabled:
                time.sleep(0.2)
                continue
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            result = self.detector.detect(mp_image)

            person_count = 0
            if result.detections:
                for d in result.detections:
                    if d.categories[0].category_name.lower() == "person":
                        person_count += 1

                        if self.enable_display:
                            bbox = d.bounding_box
                            cv2.rectangle(
                                frame,
                                (bbox.origin_x, bbox.origin_y),
                                (bbox.origin_x + bbox.width, bbox.origin_y + bbox.height),
                                (0, 255, 0),
                                2
                            )

            self.current_person_count = person_count

            if self.enable_display:
                cv2.putText(
                    frame,
                    f"People: {person_count}",
                    (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2
                )
                cv2.imshow("Person Detection", frame)
                if cv2.waitKey(1) & 0xFF == 27:
                    self.running = False