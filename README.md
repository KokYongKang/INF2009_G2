

# Edge-based Room Occupancy Detection

Project for real-time, robust room occupancy detection using sensor fusion, edge caching, and a web dashboard.

**GitHub Repository:** 

## Features
- **mmWave sensor integration:** Detects presence and distance using radar.
- **Webcam/Camera integration:** Detects and counts people using object detection (MediaPipe, EfficientDet).
- **Sensor fusion:** Combines mmWave and camera data for robust occupancy estimation.
- **Edge cache:** Local SQLite cache for resilience and offline operation.
- **MQTT-based real-time updates:** Fast, event-driven communication between sensors and dashboard.
- **Web dashboard:** Flask app for live monitoring, analytics, and alerting.
- **Booking integration:** (Demo/mock) Shows booking status and detects mismatches.
- **Alerting:** Detects overcapacity, booking mismatches, sensor offline, and more.

## System Architecture

```
┌────────────┐      MQTT      ┌──────────────┐
│  Sensors   │───────────────▶│   Dashboard  │
│ (mmWave,   │               │ (Flask+DB)   │
│  Camera)   │◀───────────────│  Edge Cache  │
└────────────┘   (bi-dir)     └──────────────┘
```

1. **Sensors** (Raspberry Pi):
   - mmWave sensor (RD03D) for presence/distance
   - Camera for headcount (MediaPipe/EfficientDet)
   - Sensor fusion logic (Python)
   - Publishes occupancy/headcount via MQTT
   - Local edge cache (SQLite) for state/history/logs
2. **Dashboard** (Flask):
   - Receives MQTT updates, updates MongoDB
   - Visualizes live state, history, and alerts
   - Fallback to edge cache if DB/network is down
   - Booking/room config in MongoDB
   - Alerting for overcapacity, mismatches, sensor offline

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the dashboard (Flask app):
   ```bash
   cd dashboard
   flask run
   ```
3. Run the sensor fusion script:
   ```bash
   cd src/sensors
   python sensor_fusion.py
   ```

## Folder Structure
- `dashboard/` : Flask app, MQTT subscriber, DB/cache logic, templates
- `src/sensors/` : Sensor fusion, edge cache, individual sensor drivers
- `data/` : Sensor logs, images, audio, edge cache DB
- `docs/` : Documentation



## Usage
1. **Start the dashboard:**
   - View real-time room occupancy, sensor status, and alerts.
2. **Sensor operation:**
   - Sensors run on a Pi, fusing mmWave and camera data.
   - Only significant changes (e.g., occupancy transitions) are published via MQTT.
   - If network is down, all state/history/logs are cached locally (SQLite).
3. **Dashboard backend:**
   - Receives MQTT messages, updates MongoDB, and triggers UI updates.
   - If MongoDB is unavailable, dashboard can read from edge cache for the live room.
4. **Alerts:**
   - Overcapacity, booking mismatch, sensor offline, and more are detected and shown.

---


---

## Project Diary (Development Log)

### Initial Version (HTTP, CSV, Basic Sensors)
- Used HTTP POSTs for sensor data updates to the dashboard.
- Focused on mmWave and camera integration
- Local CSV logging for sensor data.
- Dashboard polled for updates, not real-time.

### Sensor Fusion & Camera Integration
- Added webcam-based headcount using MediaPipe/EfficientDet.
- Developed fusion logic: room is occupied if either mmWave detects presence or camera detects people.
- Improved accuracy and reduced false negatives.

### Migration to MQTT & Edge Cache
- Migrated from HTTP to MQTT for real-time, event-driven updates (lower latency, less polling).
- Implemented robust MQTT subscriber in dashboard (Flask) to process sensor events.
- Added edge cache (SQLite) on the Pi:
   - Stores latest state, history, and logs locally.
   - Queues unsent updates if network is down, retries when back online.
   - Dashboard can read from edge cache if DB is unavailable.
- Refactored code for modularity: services, utils, DB, cache, and sensor logic separated.

### Dashboard, Alerts, and Analytics
- Dashboard shows live state, history charts, and event logs per room.
- Alerting logic for:
   - Overcapacity (headcount > room capacity)
   - Booking mismatch (room booked but vacant, or vice versa)
   - Sensor offline (no update in threshold time)
   - Room full
- Weekly utilization analytics auto-refreshes for charts.

### Testing, Challenges, and Lessons Learned
- Simulated and real sensor data tested end-to-end (sensor → MQTT → dashboard → DB).
- Verified cache fallback, data consistency, and recovery from network outages.
- Improved error handling, logging, and retry logic for edge cache.
- Lessons:
   - MQTT is far superior to HTTP for real-time, event-driven IoT.
   - Edge caching is essential for resilience in real-world deployments.
   - Sensor fusion (mmWave + camera) greatly improves reliability.
   - Modular codebase makes future changes and debugging much easier.



## Authors
- Team G2

