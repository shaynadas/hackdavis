import httpx

async def get_speed_limit(lat: float, lon: float) -> dict:
    """
    Fetches the speed limit for the nearest road using OpenStreetMap's Overpass API.
    Returns speed in mph.
    """
    query = f"""
    [out:json];
    way(around:50,{lat},{lon})["maxspeed"];
    out tags;
    """
    url = f"https://overpass-api.de/api/interpreter?data={query}"
    
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            elements = data.get("elements", [])
            if elements:
                maxspeed_str = elements[0].get("tags", {}).get("maxspeed", "")
                if maxspeed_str:
                    # 'maxspeed' could be '55 mph', '100' (kph default)
                    if "mph" in maxspeed_str:
                        return {"speed_limit_mph": float(maxspeed_str.replace("mph", "").strip()), "source": "overpass", "error": None}
                    elif "kph" in maxspeed_str or maxspeed_str.isdigit():
                        kph = float(maxspeed_str.replace("kph", "").strip())
                        return {"speed_limit_mph": kph * 0.621371, "source": "overpass", "error": None}
    except Exception as e:
        return {"speed_limit_mph": None, "source": "mock", "error": str(e)}
        
    return {"speed_limit_mph": None, "source": "mock", "error": "Not found"}
