"""
Main entry point for sensor integration.
"""
from mmwave_sensor import mmwave_detect
from microphone_sensor import microphone_detect

def main():
    print("Starting sensor integration...")
    mmwave_result = mmwave_detect()
    print(f"mmWave sensor: {mmwave_result}")
    mic_result = microphone_detect()
    print(f"Microphone sensor: {mic_result}")

if __name__ == "__main__":
    main()
