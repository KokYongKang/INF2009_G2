import unittest
from src.utils import log_event

class TestUtils(unittest.TestCase):
    def test_log_event(self):
        try:
            log_event("Test event")
        except Exception as e:
            self.fail(f"log_event raised an exception: {e}")

if __name__ == "__main__":
    unittest.main()
