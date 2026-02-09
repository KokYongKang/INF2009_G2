import unittest
from src.microphone_sensor import microphone_detect

class TestMicrophoneSensor(unittest.TestCase):
    def test_microphone_detect(self):
        result = microphone_detect()
        self.assertIn(result, [True, False])

if __name__ == "__main__":
    unittest.main()
