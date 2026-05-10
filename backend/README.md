# Eco-Driving Recommendation API

This is the backend service for the real-time eco-driving recommendation app. It combines phone GPS/location data, traffic context, road grade, vehicle profiles, and CV/perception signals to optimize driving speed and estimated RPM.

## Setup Instructions

1. `cd backend`
2. `python -m venv venv`
3. `source venv/bin/activate`
4. `pip install -r requirements.txt`
5. Create `.env` from the instructions below.
6. `uvicorn main:app --reload --host 0.0.0.0 --port 8000`

The API will be available at http://localhost:8000
Interactive API documentation is available at http://localhost:8000/docs

## API Endpoints & Examples

### Health Check
```bash
curl -X GET "http://localhost:8000/health"
```

### Demo Recommendation
Returns a fully working hardcoded demo recommendation without requiring external APIs.
```bash
curl -X GET "http://localhost:8000/recommendation/demo"
```

### Get Recommendation (Full Payload)
```bash
curl -X POST "http://localhost:8000/recommendation" \
     -H "Content-Type: application/json" \
     -d '{
  "location": {
    "lat": 38.5449,
    "lon": -121.7405,
    "speed_mph": 38,
    "heading_deg": 84.2,
    "accuracy_m": 8
  },
  "road_context": {
    "speed_limit_mph": 40,
    "traffic_speed_mph": 24,
    "congestion_level": "moderate",
    "road_grade_percent": 3.2,
    "upcoming_stop_distance_m": 250,
    "incident_ahead": false
  },
  "perception": {
    "traffic_state": "slowing",
    "lead_vehicle_status": "braking",
    "lead_vehicle_distance": "close",
    "stopped_vehicle_detected": false,
    "hazard_detected": false,
    "pedestrian_detected": false,
    "cyclist_detected": false,
    "possible_incident": false,
    "confidence": 0.81
  },
  "vehicle_profile": {
    "year": 2018,
    "make": "Audi",
    "model": "A4",
    "trim": "2.0T",
    "transmission_type": "automatic",
    "mass_kg": 1600,
    "tire_width": 245,
    "aspect_ratio": 40,
    "rim_in": 18,
    "final_drive_ratio": 4.41,
    "gear_ratios": {
      "1": 3.69,
      "2": 2.15,
      "3": 1.41,
      "4": 1.03,
      "5": 0.79,
      "6": 0.63
    }
  }
}'
```

### Location Streaming
Stream location data from a device:
```bash
curl -X POST "http://localhost:8000/location/update" \
     -H "Content-Type: application/json" \
     -d '{
  "lat": 38.5449,
  "lon": -121.7405,
  "speed_mph": 38,
  "heading_deg": 84.2,
  "accuracy_m": 8
}'
```

Get latest streamed location:
```bash
curl -X GET "http://localhost:8000/location/latest"
```

Live recommendation using latest streamed location:
```bash
curl -X GET "http://localhost:8000/recommendation/live"
```

### Live Road Test Endpoints

Update Perception:
```bash
curl -X POST "http://localhost:8000/perception/update" \
  -H "Content-Type: application/json" \
  -d '{
    "traffic_state": "slowing",
    "lead_vehicle_status": "braking",
    "lead_vehicle_distance": "close",
    "stopped_vehicle_detected": false,
    "hazard_detected": false,
    "pedestrian_detected": false,
    "cyclist_detected": false,
    "possible_incident": false,
    "confidence": 0.81
  }'
```

Update Road Context:
```bash
curl -X POST "http://localhost:8000/road-context/update" \
  -H "Content-Type: application/json" \
  -d '{
    "speed_limit_mph": 40,
    "traffic_speed_mph": 24,
    "congestion_level": "moderate",
    "road_grade_percent": 3.2,
    "upcoming_stop_distance_m": 250,
    "incident_ahead": false
  }'
```

### Voice / ElevenLabs Setup

1. Create an ElevenLabs API key.
2. Add these to your `.env` file:
```env
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
ELEVENLABS_STT_MODEL_ID=scribe_v2
ELEVENLABS_TTS_MODEL_ID=eleven_flash_v2_5
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
```

> **Note on Voice Inputs**:
> - VIN audio input is estimated from transcription and should be confirmed by the user.
> - VINs are hard to transcribe perfectly because letters and numbers sound similar.
> - The backend returns `needs_confirmation` when confidence is below 0.9.
> - RPM and gear are estimated because there is no OBD-II.
> - Internally, users sometimes say "VIM", but it refers to the "VIN".

Check Voice Status:
```bash
curl -X GET "http://localhost:8000/voice/status"
```

Speak Text:
```bash
curl -X POST "http://localhost:8000/voice/speak" \
  -H "Content-Type: application/json" \
  -d '{"text": "Ease off the gas and coast toward 27 miles per hour."}' \
  --output advice.mp3
```

Speak Recommendation JSON:
```bash
curl -X POST "http://localhost:8000/voice/speak-recommendation" \
  -H "Content-Type: application/json" \
  -d @demo_payload.json \
  --output recommendation.mp3
```

### Voice VIN Capture Flow

The preferred hackathon flow is to prompt the user to enter their VIN (by voice or typing) and confirm it before live recommendations start.

1. User presses "Enter VIN by voice."
2. Frontend records audio until 17 characters are spoken or user pauses.
3. Frontend sends audio to `POST /voice/vin-capture`.
4. Backend returns normalized VIN, decoded vehicle details, and confirmation text.
5. Frontend calls `POST /voice/speak` with confirmation text to ask the user.
6. User answers yes/no by typing or voice.
7. If typed: `POST /vin/confirm`.
8. If spoken: `POST /voice/confirm-vin`.
9. Once confirmed, backend stores `latest_vehicle_profile`.
10. `GET /recommendation/live` uses the confirmed vehicle!

**Examples:**

Typed VIN:
```bash
curl -X POST "http://localhost:8000/vin/typed" \
  -H "Content-Type: application/json" \
  -d '{"vin": "WAUZZZ8K9JA012345"}'
```

Voice VIN capture:
```bash
curl -X POST "http://localhost:8000/voice/vin-capture" \
  -F "file=@vin_audio.wav"
```

Confirm typed yes:
```bash
curl -X POST "http://localhost:8000/vin/confirm" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "SESSION_ID_HERE", "confirmed": true}'
```

Confirm spoken yes/no:
```bash
curl -X POST "http://localhost:8000/voice/confirm-vin" \
  -F "file=@yes_audio.wav" \
  -F "session_id=SESSION_ID_HERE"
```

Get latest vehicle:
```bash
curl -X GET "http://localhost:8000/vehicle/latest"
```

Clear latest vehicle:
```bash
curl -X DELETE "http://localhost:8000/vehicle/latest"
```

*(Note: The old `/voice/recommendation-from-vin-audio` endpoint is kept as a legacy fallback, but the simplified VIN capture flow above is heavily preferred!)*

### External Services Integration (with fallback)
Decode a VIN using NHTSA API:
```bash
curl -X POST "http://localhost:8000/vin/decode" \
     -H "Content-Type: application/json" \
     -d '{"vin": "YOUR_VIN_HERE"}'
```

Get elevation using Open-Meteo API:
```bash
curl -X GET "http://localhost:8000/elevation?lat=38.5449&lon=-121.7405"
```

Calculate road grade between two points using Open-Meteo API:
```bash
curl -X POST "http://localhost:8000/grade" \
     -H "Content-Type: application/json" \
     -d '{
  "start": {"lat": 38.5449, "lon": -121.7405},
  "end": {"lat": 38.5459, "lon": -121.7395}
}'
```

Mock traffic data:
```bash
curl -X GET "http://localhost:8000/traffic/mock"
```

TomTom traffic data:
```bash
curl -X GET "http://localhost:8000/traffic/tomtom?lat=38.5449&lon=-121.7405"
```
