# Backseat Driver 🏎️

**Backseat Driver** is a real-time eco-driving copilot built for HackDavis. It fuses live phone telemetry, computer vision, traffic data, road grade, and vehicle physics to give drivers moment-to-moment advice on the most fuel-efficient speed to maintain — reducing unnecessary emissions without requiring any modification to the vehicle.

> *"Given where the car is, how fast it's moving, what the road ahead looks like, what traffic is doing, and what vehicle is being driven — what speed should the driver target right now to save fuel?"*

---

## Table of Contents

- [Why It Exists](#why-it-exists)
- [System Architecture](#system-architecture)
- [Components](#components)
  - [Backend API](#backend-api)
  - [Frontend Dashboard](#frontend-dashboard)
  - [Mobile App](#mobile-app)
  - [CV Pipeline](#cv-pipeline)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)

---

## Why It Exists

Most fuel waste happens during avoidable driving behavior:

- Hard acceleration out of stops
- Late braking that wastes kinetic energy
- Maintaining highway speed while traffic is already slowing
- Accelerating uphill aggressively when coasting would do
- Idling unnecessarily

Backseat Driver addresses this by fusing every available signal into a single, real-time eco-score and plain-English recommendation — delivered by voice so the driver's eyes stay on the road.

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         iPhone (Mobile App)                       │
│   GPS · Accelerometer · Gyroscope → POST /telemetry              │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                     FastAPI Backend  (:8000)                       │
│                                                                    │
│  /telemetry   /location   /perception   /road-context             │
│  /recommendation/live   /voice/*   /vin/*                         │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐    │
│  │ Eco Optimizer│  │ TomTom       │  │ ElevenLabs STT + TTS │    │
│  │ (physics)    │  │ Traffic API  │  │ (VIN capture, voice  │    │
│  └──────────────┘  └──────────────┘  │  advice)             │    │
│  ┌──────────────┐  ┌──────────────┐  └──────────────────────┘    │
│  │ NHTSA VIN    │  │ Open-Meteo   │                               │
│  │ Decoder      │  │ Elevation    │                               │
│  └──────────────┘  └──────────────┘                              │
└────────────────────────────┬─────────────────────────────────────┘
                             │
         ┌───────────────────┴───────────────────┐
         │                                       │
┌────────▼────────┐                   ┌──────────▼──────────┐
│  CV Pipeline    │                   │  React Dashboard     │
│  (:8001)        │                   │  (:5173)             │
│                 │                   │                      │
│  YOLOv8n        │                   │  Live recommendation │
│  Centroid       │──POST /perception▶│  Speed + RPM charts  │
│  Tracking       │  /update          │  Perception state    │
│  MJPEG stream   │                   │  Phone map widget    │
└─────────────────┘                   └──────────────────────┘
```

---

## Components

### Backend API

**Location:** `backend/`  
**Port:** `8000`  
**Stack:** Python · FastAPI · Pydantic · Uvicorn

The backend is the central decision engine. It maintains in-memory state for location, telemetry, perception, and vehicle profile, and serves a live recommendation on every poll.

**Key modules:**

| File | Purpose |
|---|---|
| `main.py` | All API routes and in-memory state management |
| `eco_optimizer.py` | Physics-based speed and RPM optimizer |
| `models.py` | All Pydantic request/response models |
| `services/vin_service.py` | NHTSA VIN decoder |
| `services/elevation_service.py` | Open-Meteo elevation + road grade |
| `services/traffic_service.py` | TomTom live traffic |
| `services/speed_limit_service.py` | OpenStreetMap speed limit lookup |
| `services/elevenlabs_service.py` | ElevenLabs STT transcription + TTS synthesis |

**How `GET /recommendation/live` works:**

1. Takes the latest GPS position from the phone (`/telemetry`) or from `/location/update`
2. Fetches live traffic speed and congestion from TomTom
3. Fetches the posted speed limit from OpenStreetMap
4. Calculates road grade from Open-Meteo elevation using the last two GPS positions
5. Merges the latest perception state from the CV pipeline (or mocked fallback)
6. Runs the physics optimizer to compute optimal speed, estimated RPM, recommended action, eco score, and a plain-English voice line

---

### Frontend Dashboard

**Location:** `backseat-driver/`  
**Port:** `5173`  
**Stack:** React · TypeScript · Vite · Tailwind CSS · Recharts · Leaflet

A real-time monitoring dashboard for the driver's seat or a co-pilot screen.

**Panels:**

| Panel | Description |
|---|---|
| **Phone** | Connection indicator + live Leaflet map with GPS marker updating as the phone moves |
| **Recommendation** | Current action (coast, maintain, accelerate), optimal speed, eco score, safety level, and natural language advice |
| **Speed Chart** | Live rolling chart of current speed vs. optimal speed vs. traffic speed |
| **RPM / Eco Chart** | Estimated engine RPM and eco score over time |
| **Perception State** | Latest output from the CV pipeline (traffic state, lead vehicle, hazards) |
| **Location** | Raw GPS coordinates and GPS stream toggle |
| **Road Context** | Speed limit, traffic speed, road grade, congestion level |
| **Vehicle** | Currently loaded vehicle profile (set via VIN) |
| **Voice** | ElevenLabs TTS/STT status and last voice recommendation line |
| **Raw JSON** | Full debug view of every data payload |

---

### Mobile App

**Location:** `mobile/`  
**Stack:** React Native · Expo · TypeScript

The iPhone app acts as the vehicle's sensor suite. It streams real-time sensor data to the backend over your local Wi-Fi network every second.

**What it streams (`POST /telemetry`):**

```json
{
  "timestamp": 1778417589.39,
  "accel": { "x": 0.02, "y": -0.01, "z": 9.81 },
  "gyro":  { "alpha": 0.0, "beta": 0.1, "gamma": -0.3 },
  "gps": {
    "latitude": 38.5449,
    "longitude": -121.7405,
    "speed": 16.7,
    "heading": 84.2,
    "altitude": 21.0,
    "accuracy": 5
  }
}
```

The backend extracts the GPS fields to update location state, computes speed in mph, and triggers grade calculation when the phone has moved more than 15 meters.

**Setup:**

```bash
cd mobile
npm install
npm start        # Opens Expo Go QR code
```

Scan the QR code with the **Expo Go** app on your iPhone. The app will automatically POST telemetry to the backend at the IP address shown when you run `./start.sh`.

> **Important:** Your phone and laptop must be on the same Wi-Fi network.

---

### CV Pipeline

**Location:** `cv_pipeline.py`  
**Port:** `8001`  
**Stack:** Python · YOLOv8n · OpenCV · FastAPI · Uvicorn

The CV pipeline runs on the laptop and uses the built-in webcam to detect and track vehicles, pedestrians, and hazards in real time. Every 500ms it pushes a structured perception report to the backend's `/perception/update` endpoint, which feeds directly into the live recommendation.

**Detection classes:**

| Class | Tracked As |
|---|---|
| Person (0) | Pedestrian |
| Car (2) | Vehicle |
| Motorcycle (3) | Vehicle |
| Bus (5) | Vehicle |
| Truck (7) | Vehicle |

**Output fields pushed to backend:**

```json
{
  "traffic_state": "slowing",
  "lead_vehicle_status": "braking",
  "lead_vehicle_distance": "close",
  "stopped_vehicle_detected": true,
  "hazard_detected": true,
  "pedestrian_detected": false,
  "possible_incident": false,
  "confidence": 0.82

}
```


**Video streams (available in browser):**

| URL | Description |
|---|---|
| `http://localhost:8001/video_feed?type=smooth` | Raw camera feed at full framerate |
| `http://localhost:8001/video_feed?type=annotated` | YOLO bounding boxes + perception overlay |

**Running modes:**

```bash
python cv_pipeline.py 0        # Live webcam (default)
python cv_pipeline.py mock     # Simulated traffic scenarios (no camera needed)
python cv_pipeline.py 0 --no-push    # Webcam but don't push to backend
python cv_pipeline.py 0 --no-window  # Headless mode, no preview window
```

---

## Getting Started

### Prerequisites

- **Python 3.10+** with pip
- **Node.js 18+** with npm
- **Expo Go** installed on your iPhone

### 1. Clone the repo

```bash
git clone https://github.com/shaynadas/hackdavis.git
cd hackdavis
```

### 2. Set up the backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in your API keys (see below)
cd ..
```

### 3. Set up the frontend dashboard

```bash
cd backseat-driver
npm install
cd ..
```

### 4. Set up the mobile app

```bash
cd mobile
npm install
cd ..
```

### 5. Start everything

```bash
./start.sh
```

This will:
- Start the **Backend API** on port 8000
- Start the **CV Pipeline** (webcam) on port 8001
- Start the **Frontend Dashboard** on port 5173
- Print the **EXPO TELEMETRY URL** — enter this in the mobile app

```bash
./start.sh debug    # Show all service logs and HTTP status codes
```

### 6. Start the mobile app separately

```bash
cd mobile
npm start
```

Scan the QR code with Expo Go on your iPhone. Make sure your phone is on the same Wi-Fi network as your laptop.

---

## Environment Variables

Create `backend/.env` with the following:

```env
# TomTom (live traffic)
TOMTOM_API_KEY=your_key_here

# ElevenLabs (voice — STT + TTS)
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
ELEVENLABS_STT_MODEL_ID=scribe_v2
ELEVENLABS_TTS_MODEL_ID=eleven_flash_v2_5
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
```

All external services have graceful fallbacks if keys are missing:
- **TomTom** → falls back to mock traffic data
- **ElevenLabs** → voice endpoints return 503 but all other endpoints remain functional
- **Open-Meteo** (elevation) → free, no key required
- **NHTSA VIN** → free, no key required
- **OpenStreetMap** (speed limits) → free, no key required

---

## API Reference

Full interactive docs available at `http://localhost:8000/docs` when the backend is running.

### Core Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Backend health check |
| `GET` | `/recommendation/live` | Live eco-driving recommendation using latest sensor state |
| `GET` | `/recommendation/demo` | Demo recommendation using hardcoded payload |
| `POST` | `/recommendation` | Full recommendation from a complete JSON payload |

### Telemetry & State

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/telemetry` | Receive iPhone sensor data (GPS, accel, gyro) |
| `GET` | `/telemetry/latest` | Get the most recent phone telemetry packet |
| `POST` | `/location/update` | Manually update GPS location |
| `GET` | `/location/latest` | Get the most recent location |
| `POST` | `/perception/update` | Push CV pipeline output |
| `GET` | `/perception/latest` | Get the most recent perception state |
| `POST` | `/road-context/update` | Manually push road context |
| `GET` | `/road-context/latest` | Get the most recent road context |
| `GET` | `/vehicle/latest` | Get the confirmed vehicle profile |
| `DELETE` | `/vehicle/latest` | Clear the vehicle profile |

### VIN & Voice

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/vin/typed` | Submit a VIN as text; returns decoded vehicle + session ID |
| `POST` | `/vin/confirm` | Confirm or reject a VIN capture session |
| `POST` | `/voice/vin-capture` | Submit voice audio; transcribes and extracts VIN |
| `POST` | `/voice/confirm-vin` | Submit yes/no audio to confirm a VIN session |
| `POST` | `/voice/speak` | Synthesize arbitrary text to speech (returns MP3) |
| `POST` | `/voice/speak-recommendation` | Synthesize a full recommendation payload to speech |
| `GET` | `/voice/status` | Check ElevenLabs STT/TTS configuration status |

### External Data

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/vin/decode` | Decode a VIN using NHTSA |
| `GET` | `/elevation` | Get elevation at a lat/lon (Open-Meteo) |
| `POST` | `/grade` | Calculate road grade between two coordinates |
| `GET` | `/traffic/tomtom` | Get live traffic at a lat/lon (TomTom) |
| `GET` | `/traffic/mock` | Get mock traffic data |

---

## Project Structure

```
hackdavis/
├── start.sh                    # One-command startup for all services
├── cv_pipeline.py              # YOLOv8 camera perception + FastAPI server
├── yolov8n.pt                  # YOLOv8 nano model weights
│
├── backend/
│   ├── main.py                 # All API routes
│   ├── eco_optimizer.py        # Physics-based eco driving optimizer
│   ├── models.py               # Pydantic models
│   ├── mock_data.py            # Demo/fallback data
│   ├── requirements.txt
│   ├── .env                    # API keys (not committed)
│   └── services/
│       ├── vin_service.py      # NHTSA VIN decode
│       ├── elevation_service.py # Open-Meteo elevation + grade
│       ├── traffic_service.py  # TomTom traffic
│       ├── speed_limit_service.py # OSM speed limits
│       └── elevenlabs_service.py  # STT + TTS
│
├── backseat-driver/            # React + Vite dashboard
│   └── src/
│       ├── App.tsx
│       ├── api.ts
│       └── components/
│
└── mobile/                     # Expo React Native app
    └── app/
        └── (tabs)/
            └── index.tsx       # Telemetry streaming screen
```