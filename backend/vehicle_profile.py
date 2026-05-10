import json
import os
from models import VehicleProfileInput

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PROFILES_FILE = os.path.join(DATA_DIR, "vehicle_profiles.json")

def load_vehicle_profiles() -> dict:
    if os.path.exists(PROFILES_FILE):
        with open(PROFILES_FILE, "r") as f:
            return json.load(f)
    return {}

def get_default_vehicle_profile(vehicle_type="sedan") -> dict:
    profiles = load_vehicle_profiles()
    key = f"default_{vehicle_type}"
    return profiles.get(key, profiles.get("default_sedan", {}))

def get_vehicle_profile(make: str, model: str, year: int = None, trim: str = None) -> dict:
    profiles = load_vehicle_profiles()
    # Simple search
    for key, profile in profiles.items():
        if profile.get("make") == make and profile.get("model") == model:
            if year and profile.get("year") != year:
                continue
            if trim and profile.get("trim") != trim:
                continue
            return profile
    return None

def resolve_vehicle_profile(request_profile: VehicleProfileInput) -> dict:
    if request_profile:
        # Check if full profile is provided
        if request_profile.gear_ratios and request_profile.mass_kg:
            prof = getattr(request_profile, "model_dump", request_profile.dict)(exclude_none=True)
            if "source" not in prof:
                prof["source"] = "provided_profile"
            return prof
        
        # Check by make/model
        if request_profile.make and request_profile.model:
            profile = get_vehicle_profile(
                request_profile.make,
                request_profile.model,
                request_profile.year,
                request_profile.trim
            )
            if profile:
                if getattr(request_profile, "vin", None):
                    profile["source"] = "vin_decoded_then_local_profile"
                else:
                    profile["source"] = "local_profile"
                return profile
                
    prof = get_default_vehicle_profile("sedan")
    prof["source"] = "default_sedan"
    if request_profile and getattr(request_profile, "vin", None):
        prof["source"] = "vin_failed_default_sedan"
    return prof
