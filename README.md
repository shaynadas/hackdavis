# Backseat Driver — Eco-Driving Copilot 🚗💨

A real-time eco-driving copilot built at **HackDavis**. It fuses phone GPS, dashcam computer vision, road/traffic/elevation context, and your specific vehicle's drivetrain profile to tell you — by voice — exactly what speed and RPM will burn the least fuel right now, while still keeping you safe.

The full system runs on a laptop (or a Raspberry Pi in the car), with a phone streaming GPS, a webcam doing perception, a React dashboard for the "god view," and an optional Arduino that mirrors the recommended RPM/speed on physical hardware.

---

## What it does

- **Recommends an optimal speed + gear/RPM** in real time, balancing fuel economy against safety.
- **Sees the road.** A YOLOv8 pipeline detects vehicles, pedestrians, lead-vehicle braking, stopped traffic, and possible incidents from a webcam feed.
- **Knows the road.** Pulls live traffic (TomTom), speed limits (OpenStreetMap Overpass), and elevation/grade (Open-Meteo) from the phone's GPS.
- **Knows your car.** Decode any VIN via NHTSA → look up gear ratios, final drive, tire size, mass → compute true engine RPM at any speed in any gear.
- **Talks to you.** ElevenLabs STT lets you read out a VIN; ElevenLabs TTS speaks each recommendation back ("Ease off the gas and coast toward 27 mph").
- **Drives hardware.** A serial bridge streams the live RPM/speed numbers to an Arduino over USB at 115200 baud.

---

## Architecture

```
                 ┌────────────────┐         ┌─────────────────────┐
   📱 Phone ─────►   /telemetry   │         │  Webcam → cv_pipeline│
   (GPS stream)  │   :8000        │◄────────│  YOLOv8  :8001       │
                 │                │ /perception/update             │
                 │   FastAPI      │         └─────────────────────┘
                 │   Backend      │◄──────── 🌐 NHTSA · TomTom ·
   💻 Dashboard ─►  eco_optimizer │          Open-Meteo · Overpass
   (React/Vite)  │                │          ElevenLabs (STT+TTS)
                 │  /recommendation│
                 └────────┬───────┘
                          │ /recommendation/demo (RPM, speed)
                          ▼
                 ┌────────────────┐
                 │ serial_bridge  │ ──USB──►  🔌 Arduino
                 └────────────────┘
```

---

## Tech stack

| Layer        | Stack                                                                 |
| ------------ | --------------------------------------------------------------------- |
| Backend      | Python · FastAPI · Uvicorn · Pydantic · httpx                         |
| CV Pipeline  | OpenCV · Ultralytics YOLOv8 (laptop) / ONNX Runtime (Pi)              |
| Frontend     | React 19 · TypeScript · Vite · Tailwind · Recharts · lucide-react     |
| Voice        | ElevenLabs Scribe v2 (STT) · ElevenLabs Flash v2.5 (TTS)              |
| External APIs| NHTSA vPIC · Open-Meteo Elevation · OpenStreetMap Overpass · TomTom   |
| Hardware     | Arduino over USB serial (`pyserial`)                                  |

---

## Repository layout

```
hackdavis/
├── backend/                  # FastAPI eco-driving service (port 8000)
│   ├── main.py               # All HTTP endpoints
│   ├── eco_optimizer.py      # Core recommendation logic (RPM/gear/speed)
│   ├── vehicle_profile.py    # Drivetrain math + defaults
│   ├── models.py             # Pydantic request/response schemas
│   ├── mock_data.py          # /recommendation/demo payload
│   ├── services/
│   │   ├── vin_service.py        # NHTSA VIN decode
│   │   ├── elevation_service.py  # Open-Meteo + haversine grade calc
│   │   ├── traffic_service.py    # TomTom live traffic
│   │   ├── speed_limit_service.py# OSM Overpass maxspeed
│   │   └── elevenlabs_service.py # STT, TTS, VIN normalization
│   └── requirements.txt
│
├── backseat-driver/          # Vite + React + TS dashboard (port 5173)
│   └── src/components/       # RecommendationPanel, SpeedChart, RPMEcoChart,
│                             # LiveVideoPanel, VoicePanel, VehiclePanel, ...
│
├── cv_pipeline.py            # YOLOv8 perception + MJPEG server (port 8001)
├── extra.py                  # Pi-optimized CV (ONNX Runtime, 3–5× faster)
├── yolov8n.pt                # Pre-downloaded YOLOv8 nano weights
├── serial_bridge.py          # Backend → Arduino USB serial bridge
└── start.sh                  # One-command launcher (backend + CV + frontend)
```

---

## Quick start

### Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- A webcam (built-in is fine)
- macOS or Linux (`start.sh` is written for macOS; trivially adaptable)
- *Optional:* ElevenLabs API key for voice; Arduino + USB cable for hardware mirror

### One-command launch

```bash
git clone https://github.com/shaynadas/hackdavis.git
cd hackdavis

# Install backend deps
cd backend && pip install -r requirements.txt && cd ..

# Install CV deps
pip install opencv-python ultralytics requests

# Install frontend deps
cd backseat-driver && npm install && cd ..

# Boot everything
chmod +x start.sh
./start.sh           # add `debug` for verbose logs: ./start.sh debug
```

You'll see something like:

```
--------------------------------------------------------
[INFO] Starting Eco-Driving Copilot...
[INFO] EXPO TELEMETRY URL (Enter this in your phone app):
       http://192.168.1.42:8000/telemetry
--------------------------------------------------------
[START] Backend API (Port 8000)...      [OK]
[START] CV Pipeline (Webcam, Port 8001) [OK]
[START] Frontend Dashboard...           [OK]
[SUCCESS] All services started successfully.
[INFO] Dashboard available at: http://localhost:5173
```

Open **http://localhost:5173** for the dashboard. Point your phone's GPS-streamer at the printed `/telemetry` URL.

### Run things individually

```bash
# Backend only
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# → docs at http://localhost:8000/docs

# CV pipeline (0 = default webcam, or pass a video path / RTSP URL)
python cv_pipeline.py 0
# → MJPEG stream at http://localhost:8001/video_feed?type=annotated

# Frontend
cd backseat-driver && npm run dev

# Arduino serial bridge (auto-detects /dev/cu.usbmodem*)
python serial_bridge.py
```

---

## Configuration

Create `backend/.env`:

```env
# ElevenLabs (voice — optional but recommended)
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
ELEVENLABS_STT_MODEL_ID=scribe_v2
ELEVENLABS_TTS_MODEL_ID=eleven_flash_v2_5
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128

# TomTom (live traffic — optional, falls back to mock)
TOMTOM_API_KEY=your_key_here
```

Create `backseat-driver/.env`:

```env
# Default; only change for road tests where the backend is on a Pi
VITE_API_BASE_URL=http://localhost:8000
```

> **Road-testing on a Raspberry Pi?** Set `VITE_API_BASE_URL` to the Pi's LAN IP (e.g. `http://192.168.1.42:8000`) so the dashboard on your laptop or phone hits the right host.

---

## Key endpoints

The full surface lives at `http://localhost:8000/docs`. Highlights:

| Method | Path                          | What it does                                                 |
| ------ | ----------------------------- | ------------------------------------------------------------ |
| GET    | `/health`                     | Liveness check                                               |
| GET    | `/recommendation/demo`        | Hardcoded demo payload — no external APIs needed             |
| GET    | `/recommendation/live`        | Real recommendation using latest GPS + traffic + grade       |
| POST   | `/recommendation`             | Recommendation from a fully-specified JSON payload           |
| POST   | `/telemetry`                  | Phone posts GPS / IMU here                                   |
| POST   | `/perception/update`          | CV pipeline posts detection summary here                     |
| POST   | `/vin/typed`                  | Type a VIN, get decoded vehicle + confirmation prompt        |
| POST   | `/voice/vin-capture`          | Speak a VIN (multipart audio) → decoded vehicle              |
| POST   | `/vin/confirm`                | Yes/no confirm a captured VIN; saves the vehicle profile     |
| POST   | `/voice/speak`                | Text → MP3 (ElevenLabs TTS)                                  |
| POST   | `/voice/speak-recommendation` | Recommendation JSON → spoken MP3                             |
| POST   | `/grade`                      | Open-Meteo road grade between two coords                     |
| GET    | `/traffic/tomtom`             | Live TomTom traffic at a coord                               |

---

## How the recommendation works

1. **Sense.** GPS (phone) → speed, position, heading. Webcam (YOLOv8) → traffic state, lead-vehicle status/distance, pedestrian/hazard flags.
2. **Contextualize.** Pull speed limit (Overpass), live traffic (TomTom), road grade (Open-Meteo elevation between successive GPS points).
3. **Model the car.** Decode VIN → year/make/model → look up gear ratios, final drive, tire size, mass. Compute tire circumference and engine RPM from speed for every plausible gear.
4. **Optimize.** Pick the (gear, target speed) pair that minimizes RPM while staying inside the safe envelope (lead-vehicle gap, speed limit, congestion). Safety overrides fuel economy on hazards or stopped traffic.
5. **Communicate.** Return JSON to the dashboard, an MP3 voice line to the phone, and an RPM/speed pair down the serial bridge to the Arduino.

---

## Hardware: Raspberry Pi build

`extra.py` is a drop-in replacement for `cv_pipeline.py` that uses **ONNX Runtime** instead of PyTorch + Ultralytics — about 3–5× faster on a Pi 4 and roughly **50 MB** of dependencies instead of 2 GB. Convert the weights once with `yolo export model=yolov8n.pt format=onnx` and point the script at the resulting `.onnx`.

The serial bridge auto-detects an Arduino at `/dev/cu.usbmodem*` and streams a JSON line per packet:

```json
{"rpm": 2400, "speed": 38}
```

---

## Acknowledgments

- **YOLOv8** by Ultralytics for perception
- **ElevenLabs** for STT + TTS
- **NHTSA vPIC**, **Open-Meteo**, **OpenStreetMap Overpass**, **TomTom** for free public APIs
- Built at **HackDavis** 🐎

---


