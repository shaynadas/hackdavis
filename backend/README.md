# Eco-Driving Recommendation API

This is the backend service for the real-time eco-driving recommendation app. It combines phone GPS/location data, traffic context, road grade, vehicle profiles, and CV/perception signals to optimize driving speed and estimated RPM.

## Setup Instructions

1. `cd backend`
2. `python -m venv venv`
3. `source venv/bin/activate`
4. `pip install -r requirements.txt`
5. `cp .env.example .env`
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
