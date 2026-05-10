from fastapi import FastAPI, HTTPException
from typing import Dict, Any

from models import (
    RecommendationRequest, VINDecodeRequest, VINDecodeResponse,
    ElevationResponse, GradeRequest, GradeResponse, LocationInput
)
from eco_optimizer import get_recommendation
from mock_data import get_demo_recommendation_payload, get_mock_traffic
from services.vin_service import decode_vin
from services.elevation_service import get_elevation, calculate_grade
from services.traffic_service import get_traffic_context, get_tomtom_traffic

app = FastAPI(title="Eco-Driving Recommendation API")

# Simple in-memory store for latest location
latest_location: LocationInput = None

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "eco-driving-optimizer"
    }

@app.post("/recommendation")
def get_recommendation_endpoint(payload: RecommendationRequest):
    return get_recommendation(payload)

@app.get("/recommendation/demo")
def get_demo_recommendation():
    payload = get_demo_recommendation_payload()
    return get_recommendation(payload)

@app.get("/recommendation/live")
async def get_live_recommendation():
    global latest_location
    if not latest_location:
        raise HTTPException(status_code=400, detail="No location data available. Stream GPS data to /location/update first.")
    
    # In a real system, we'd fetch actual perception, road context, etc. here based on latest location.
    # For demo, we build a payload from latest location + mock everything else.
    payload = get_demo_recommendation_payload()
    payload.location = latest_location
    
    # Try updating context with tomtom
    traffic = await get_traffic_context(latest_location.lat, latest_location.lon)
    payload.road_context.traffic_speed_mph = traffic.get("speed_mph")
    
    return get_recommendation(payload)

@app.post("/location/update")
def update_location(loc: LocationInput):
    global latest_location
    latest_location = loc
    return {"status": "ok", "message": "Location updated"}

@app.get("/location/latest")
def get_latest_location():
    global latest_location
    if not latest_location:
        raise HTTPException(status_code=404, detail="No location data available")
    return latest_location

@app.post("/vin/decode", response_model=VINDecodeResponse)
async def decode_vin_endpoint(payload: VINDecodeRequest):
    res = await decode_vin(payload.vin)
    return VINDecodeResponse(**res)

@app.get("/elevation", response_model=ElevationResponse)
async def get_elevation_endpoint(lat: float, lon: float):
    res = await get_elevation(lat, lon)
    return ElevationResponse(**res)

@app.post("/grade", response_model=GradeResponse)
async def calculate_grade_endpoint(payload: GradeRequest):
    res = await calculate_grade(payload.start, payload.end)
    return GradeResponse(**res)

@app.get("/traffic/mock")
def get_mock_traffic_endpoint():
    return get_mock_traffic()

@app.get("/traffic/tomtom")
async def get_tomtom_traffic_endpoint(lat: float, lon: float):
    return await get_tomtom_traffic(lat, lon)
