import os
import httpx
from dotenv import load_dotenv

load_dotenv()

def get_mock_traffic() -> dict:
    return {
        "source": "mock",
        "speed_mph": 24,
        "congestion_level": "moderate",
        "incident_ahead": False
    }

async def get_tomtom_traffic(lat: float, lon: float) -> dict:
    api_key = os.getenv("TOMTOM_API_KEY")
    if not api_key:
        return get_mock_traffic()
        
    # Example tomtom API call for flow
    url = f"https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json?key={api_key}&point={lat},{lon}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            flow = data.get("flowSegmentData", {})
            current_speed_kph = flow.get("currentSpeed", 40)
            free_flow_speed_kph = flow.get("freeFlowSpeed", 40)
            
            speed_mph = current_speed_kph * 0.621371
            free_flow_mph = free_flow_speed_kph * 0.621371
            
            ratio = current_speed_kph / max(1, free_flow_speed_kph)
            congestion_level = "low"
            if ratio < 0.5:
                congestion_level = "heavy"
            elif ratio < 0.8:
                congestion_level = "moderate"
                
            return {
                "source": "tomtom",
                "speed_mph": speed_mph,
                "congestion_level": congestion_level,
                "incident_ahead": False # Need separate incident API for true incident mapping
            }
    except Exception:
        return get_mock_traffic()

async def get_traffic_context(lat: float, lon: float) -> dict:
    return await get_tomtom_traffic(lat, lon)
