import unittest
from src.mmwave_sensor import mmwave_detect

class TestMMWaveSensor(unittest.TestCase):
    def test_mmwave_detect(self):
        result = mmwave_detect()
        self.assertIn(result, [True, False])

if __name__ == "__main__":
    unittest.main()
