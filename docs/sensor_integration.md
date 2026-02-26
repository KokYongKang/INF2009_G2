# Sensor Integration Documentation

## Overview
This document describes the integration of mmWave, microphone, and webcam sensors for real-time room occupancy detection on a Raspberry Pi.

## Sensors Used
- **mmWave Sensor**: Detects human presence.
- **Webcam**: Used for person detection and counting via lightweight AI models, providing person count and confidence score.

## Usage
- Run `src/main.py` to start the integration.
- Logs and data will be output to the console or specified files.
- For webcam-based person detection, ensure a compatible USB camera is connected to the Raspberry Pi.

## Authors
Team xx
