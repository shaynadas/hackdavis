import httpx
import math
from models import CoordinateInput

async def get_elevation(lat: float, lon: float) -> dict:
    url = f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            if "elevation" in data and len(data["elevation"]) > 0:
                return {"elevation_m": data["elevation"][0], "source": "open-meteo", "error": None}
    except Exception as e:
        return {"elevation_m": 0.0, "source": "mock", "error": str(e)}
    return {"elevation_m": 0.0, "source": "mock", "error": "Unknown error"}

async def get_elevations(points: list[CoordinateInput]) -> list[dict]:
    # Could be batched but for simplicity keeping it individual or basic fallback
    results = []
    for p in points:
        results.append(await get_elevation(p.lat, p.lon))
    return results

def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000  # radius of Earth in meters
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi_1) * math.cos(phi_2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

async def calculate_grade(start: CoordinateInput, end: CoordinateInput) -> dict:
    start_elev = await get_elevation(start.lat, start.lon)
    end_elev = await get_elevation(end.lat, end.lon)
    
    dist_m = haversine_distance_m(start.lat, start.lon, end.lat, end.lon)
    if dist_m < 1.0:
        return {
            "grade_percent": 0.0,
            "elevation_change_m": 0.0,
            "horizontal_distance_m": dist_m,
            "source": start_elev["source"] if start_elev["source"] == end_elev["source"] else "mixed",
            "error": "Distance too short"
        }
    
    elev_change = end_elev["elevation_m"] - start_elev["elevation_m"]
    grade_percent = (elev_change / dist_m) * 100.0
    
    return {
        "grade_percent": grade_percent,
        "elevation_change_m": elev_change,
        "horizontal_distance_m": dist_m,
        "source": start_elev["source"] if start_elev["source"] == end_elev["source"] else "mixed",
        "error": start_elev.get("error") or end_elev.get("error")
    }
