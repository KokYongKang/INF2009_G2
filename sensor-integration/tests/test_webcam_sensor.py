import unittest
from src.webcam_sensor import webcam_detect

class TestWebcamSensor(unittest.TestCase):
    def test_webcam_detect(self):
        person_count, confidence = webcam_detect()
        self.assertIsInstance(person_count, int)
        self.assertIsInstance(confidence, float)

if __name__ == "__main__":
    unittest.main()
