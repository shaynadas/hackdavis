import httpx

def normalize_vin_response(raw_response: dict) -> dict:
    results = raw_response.get("Results", [])
    data = {
        "Make": None,
        "Model": None,
        "Model Year": None,
        "Trim": None
    }
    
    for item in results:
        val = item.get("Value")
        if val and str(val).strip():
            var_name = item.get("Variable")
            if var_name in data:
                data[var_name] = str(val).strip()
                
    try:
        year = int(data["Model Year"]) if data["Model Year"] else None
    except:
        year = None
        
    return {
        "year": year,
        "make": data["Make"],
        "model": data["Model"],
        "trim": data["Trim"]
    }

async def decode_vin(vin: str) -> dict:
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            normalized = normalize_vin_response(data)
            return {
                "success": True,
                "source": "nhtsa_vpic",
                "year": normalized["year"],
                "make": normalized["make"],
                "model": normalized["model"],
                "trim": normalized["trim"],
                "error": None
            }
    except Exception as e:
        return {
            "success": False,
            "source": "nhtsa_vpic",
            "year": None,
            "make": None,
            "model": None,
            "trim": None,
            "error": str(e)
        }
