"""
generate_drive.py
=================
Builds a 2-minute (~120s) synthetic drive through downtown Davis, CA and writes
it to drive_timeline.json. The output is one frame per second matching the
backend Pydantic schemas in backend/models.py:

  - LocationInput      -> /location/update
  - PerceptionInput    -> /perception/update     (+ extra `lead_vehicle_distance_m`)
  - RoadContextInput   -> /road-context/update
  - VehicleProfileInput (single, written once into the timeline header)

The route follows real Davis streets:

    Start: 3rd St & B St            (38.5440, -121.7438)
      east on 3rd St (residential, 25 mph) ...
      stop sign at 3rd & D St with a lead vehicle braking ...
      continue east to 3rd & F St ...
      right turn south on F St (35 mph arterial, slight grade) ...
      brief pedestrian event approaching 1st St ...
      right turn west on 1st St back to B St
    End:   1st St & B St            (38.5408, -121.7438)

Total distance ~0.95 mi, average speed ~28 mph including stops.

Run:
    python3 generate_drive.py
Outputs:
    drive_timeline.json next to this script.
"""

import json
import math
import os
from typing import Tuple, List, Dict, Any

# ---------------------------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------------------------

EARTH_R_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_M * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def step_along(
    lat: float, lon: float, heading_deg_val: float, distance_m: float
) -> Tuple[float, float]:
    """Move (lat, lon) by `distance_m` along `heading_deg_val`."""
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    h = math.radians(heading_deg_val)
    d = distance_m / EARTH_R_M
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(h))
    l2 = l1 + math.atan2(
        math.sin(h) * math.sin(d) * math.cos(p1),
        math.cos(d) - math.sin(p1) * math.sin(p2),
    )
    return math.degrees(p2), math.degrees(l2)


# ---------------------------------------------------------------------------
# Route definition: (lat, lon, segment_speed_limit_mph, segment_label)
# Vertices are real Davis intersections. Heading is computed segment-to-segment.
# ---------------------------------------------------------------------------

WAYPOINTS: List[Dict[str, Any]] = [
    {"name": "3rd & B",  "lat": 38.5440, "lon": -121.7438, "speed_limit_mph": 25, "road": "3rd St"},
    {"name": "3rd & C",  "lat": 38.5440, "lon": -121.7420, "speed_limit_mph": 25, "road": "3rd St"},
    {"name": "3rd & D",  "lat": 38.5440, "lon": -121.7404, "speed_limit_mph": 25, "road": "3rd St"},
    {"name": "3rd & E",  "lat": 38.5440, "lon": -121.7385, "speed_limit_mph": 25, "road": "3rd St"},
    {"name": "3rd & F",  "lat": 38.5440, "lon": -121.7368, "speed_limit_mph": 25, "road": "3rd St"},
    {"name": "F & 2nd",  "lat": 38.5424, "lon": -121.7368, "speed_limit_mph": 35, "road": "F St"},
    {"name": "F & 1st",  "lat": 38.5408, "lon": -121.7368, "speed_limit_mph": 35, "road": "F St"},
    {"name": "1st & E",  "lat": 38.5408, "lon": -121.7385, "speed_limit_mph": 30, "road": "1st St"},
    {"name": "1st & D",  "lat": 38.5408, "lon": -121.7404, "speed_limit_mph": 30, "road": "1st St"},
    {"name": "1st & C",  "lat": 38.5408, "lon": -121.7420, "speed_limit_mph": 30, "road": "1st St"},
    {"name": "1st & B",  "lat": 38.5408, "lon": -121.7438, "speed_limit_mph": 30, "road": "1st St"},
]


# ---------------------------------------------------------------------------
# Speed profile (mph) per second for 121 frames (t=0..120 inclusive).
# Hand-tuned to feel like a real city drive with one stop sign and a slowdown.
# ---------------------------------------------------------------------------

def build_speed_profile() -> List[float]:
    profile = [0.0] * 121

    # Phase A 0..6s: launch from rest to 25 mph (3rd & B)
    for t in range(0, 7):
        profile[t] = round(min(25.0, t * 4.2), 1)

    # Phase B 6..28s: cruise 25 on 3rd St
    for t in range(7, 29):
        profile[t] = 25.0 + math.sin(t * 0.4) * 0.6  # tiny natural wobble

    # Phase C 29..40s: lead vehicle braking, slow down approaching 3rd & D stop sign
    targets = [24, 22, 19, 16, 13, 10, 8, 6, 4, 2, 1, 0]
    for i, t in enumerate(range(29, 29 + len(targets))):
        profile[t] = float(targets[i])

    # Phase D 41..47s: full stop at 3rd & D
    for t in range(41, 48):
        profile[t] = 0.0

    # Phase E 48..60s: launch + accelerate east toward F St up to 28 mph
    accel = [3, 6, 10, 14, 18, 21, 24, 26, 27, 28, 28, 28, 27]
    for i, t in enumerate(range(48, 48 + len(accel))):
        profile[t] = float(accel[i])

    # Phase F 61..70s: right turn at 3rd & F (slow to 14, then ramp to 35 on F St)
    turn1 = [22, 17, 14, 16, 22, 27, 31, 33, 34, 35]
    for i, t in enumerate(range(61, 61 + len(turn1))):
        profile[t] = float(turn1[i])

    # Phase G 71..95s: cruise 32-35 down F St with slight grade + light traffic wobble
    for t in range(71, 96):
        profile[t] = 33.0 + math.sin((t - 71) * 0.5) * 1.5

    # Phase H 96..104s: pedestrian detected, decelerate hard to 12
    decel = [30, 26, 22, 18, 14, 12, 12, 12, 12]
    for i, t in enumerate(range(96, 96 + len(decel))):
        profile[t] = float(decel[i])

    # Phase I 105..114s: right turn at F & 1st (slow to 10, accelerate to 28)
    turn2 = [10, 9, 12, 16, 20, 23, 25, 27, 28, 28]
    for i, t in enumerate(range(105, 105 + len(turn2))):
        profile[t] = float(turn2[i])

    # Phase J 115..120s: gentle slowdown to arrive at 1st & B
    arrive = [26, 23, 19, 14, 8, 0]
    for i, t in enumerate(range(115, 115 + len(arrive))):
        profile[t] = float(arrive[i])

    return [round(max(0.0, v), 2) for v in profile]


# ---------------------------------------------------------------------------
# March the car along the polyline using the speed profile.
# At each second, advance position by speed*dt along current segment heading.
# When we cross a waypoint, snap to the new segment's heading.
# ---------------------------------------------------------------------------

def integrate_path(speeds_mph: List[float]) -> List[Dict[str, Any]]:
    frames: List[Dict[str, Any]] = []
    seg_idx = 0
    seg_start = WAYPOINTS[seg_idx]
    seg_end = WAYPOINTS[seg_idx + 1]
    cur_lat = seg_start["lat"]
    cur_lon = seg_start["lon"]
    seg_heading = bearing_deg(seg_start["lat"], seg_start["lon"], seg_end["lat"], seg_end["lon"])
    seg_len_m = haversine_m(seg_start["lat"], seg_start["lon"], seg_end["lat"], seg_end["lon"])
    seg_traveled_m = 0.0
    current_road = seg_start["road"]
    current_speed_limit = seg_start["speed_limit_mph"]

    for t, mph in enumerate(speeds_mph):
        m_per_s = mph * 0.44704
        if t > 0:
            # Advance along current segment by 1s of travel; if we run past the
            # end vertex, carry the remainder onto the next segment.
            remaining = m_per_s
            while remaining > 1e-6 and seg_idx < len(WAYPOINTS) - 1:
                room = seg_len_m - seg_traveled_m
                if remaining <= room:
                    cur_lat, cur_lon = step_along(cur_lat, cur_lon, seg_heading, remaining)
                    seg_traveled_m += remaining
                    remaining = 0.0
                else:
                    cur_lat, cur_lon = seg_end["lat"], seg_end["lon"]
                    remaining -= room
                    seg_idx += 1
                    if seg_idx >= len(WAYPOINTS) - 1:
                        # End of route; freeze position
                        seg_traveled_m = seg_len_m
                        break
                    seg_start = WAYPOINTS[seg_idx]
                    seg_end = WAYPOINTS[seg_idx + 1]
                    seg_heading = bearing_deg(
                        seg_start["lat"], seg_start["lon"], seg_end["lat"], seg_end["lon"]
                    )
                    seg_len_m = haversine_m(
                        seg_start["lat"], seg_start["lon"], seg_end["lat"], seg_end["lon"]
                    )
                    seg_traveled_m = 0.0
                    current_road = seg_start["road"]
                    current_speed_limit = seg_start["speed_limit_mph"]

        frames.append(
            {
                "t": t,
                "lat": round(cur_lat, 6),
                "lon": round(cur_lon, 6),
                "speed_mph": round(mph, 2),
                "heading_deg": round(seg_heading, 1),
                "road": current_road,
                "speed_limit_mph": current_speed_limit,
                "seg_idx": seg_idx,
            }
        )
    return frames


# ---------------------------------------------------------------------------
# Per-frame perception + road-context overlays.
# These are scripted to match the speed-profile story so the optimizer has
# something interesting to react to.
# ---------------------------------------------------------------------------

def perception_for(t: int, frame: Dict[str, Any]) -> Dict[str, Any]:
    """Return PerceptionInput-shaped dict + numeric lead distance for the map."""
    # Defaults
    p = {
        "traffic_state": "clear",
        "lead_vehicle_status": "moving",
        "lead_vehicle_distance": "far",
        "lead_vehicle_distance_m": 80.0,
        "stopped_vehicle_detected": False,
        "hazard_detected": False,
        "pedestrian_detected": False,
        "cyclist_detected": False,
        "possible_incident": False,
        "confidence": 0.95,
    }

    # 0-6s: pulling away from B St, no real lead vehicle
    if t < 7:
        p["lead_vehicle_status"] = "none"
        p["lead_vehicle_distance"] = "far"
        p["lead_vehicle_distance_m"] = 120.0

    # 7-28s: cruising 3rd St, moderate lead vehicle far ahead
    elif t < 29:
        p["lead_vehicle_status"] = "moving"
        p["lead_vehicle_distance"] = "far"
        p["lead_vehicle_distance_m"] = round(95 - (t - 7) * 1.0, 1)  # closing slowly

    # 29-40s: lead vehicle BRAKING, gap collapsing
    elif t < 41:
        p["traffic_state"] = "slowing"
        p["lead_vehicle_status"] = "braking"
        gap = max(8.0, 60.0 - (t - 29) * 4.5)
        p["lead_vehicle_distance_m"] = round(gap, 1)
        p["lead_vehicle_distance"] = "close" if gap < 20 else "medium"

    # 41-47s: stopped at 3rd & D
    elif t < 48:
        p["traffic_state"] = "stopped"
        p["lead_vehicle_status"] = "stopped"
        p["lead_vehicle_distance"] = "close"
        p["lead_vehicle_distance_m"] = 6.5
        p["stopped_vehicle_detected"] = True

    # 48-60s: launch east, lead car pulling away
    elif t < 61:
        p["lead_vehicle_status"] = "moving"
        p["lead_vehicle_distance_m"] = round(8 + (t - 48) * 4.0, 1)
        p["lead_vehicle_distance"] = (
            "close" if p["lead_vehicle_distance_m"] < 20 else
            "medium" if p["lead_vehicle_distance_m"] < 50 else "far"
        )

    # 61-70s: right turn onto F St, clearer ahead
    elif t < 71:
        p["lead_vehicle_status"] = "moving"
        p["lead_vehicle_distance_m"] = 75.0
        p["lead_vehicle_distance"] = "far"

    # 71-95s: F St cruise with light traffic
    elif t < 96:
        p["traffic_state"] = "moderate"
        p["lead_vehicle_status"] = "moving"
        # mild oscillation
        d = 60 + math.sin((t - 71) * 0.4) * 12
        p["lead_vehicle_distance_m"] = round(d, 1)
        p["lead_vehicle_distance"] = "medium" if d < 75 else "far"

    # 96-104s: PEDESTRIAN detected, also lead car braking
    elif t < 105:
        p["traffic_state"] = "slowing"
        p["lead_vehicle_status"] = "braking"
        p["pedestrian_detected"] = True
        p["hazard_detected"] = True
        gap = max(6.0, 35.0 - (t - 96) * 3.5)
        p["lead_vehicle_distance_m"] = round(gap, 1)
        p["lead_vehicle_distance"] = "close"

    # 105-114s: turn west onto 1st St, recover
    elif t < 115:
        p["lead_vehicle_status"] = "moving"
        p["lead_vehicle_distance_m"] = 65.0
        p["lead_vehicle_distance"] = "medium"

    # 115-120s: arrival, clear
    else:
        p["lead_vehicle_status"] = "none"
        p["lead_vehicle_distance"] = "far"
        p["lead_vehicle_distance_m"] = 100.0

    return p


def road_context_for(t: int, frame: Dict[str, Any]) -> Dict[str, Any]:
    speed_limit = float(frame["speed_limit_mph"])
    grade = 0.0
    congestion = "low"
    traffic_speed = speed_limit

    # F St segment (between 3rd & F and F & 1st) gets a small simulated grade
    if frame["road"] == "F St":
        # Climb gently from t≈61..78, then descend slightly
        local = t - 61
        if 0 <= local <= 30:
            grade = round(min(3.5, 0.4 + local * 0.12), 2)
        else:
            grade = 1.0

    if t < 7:
        congestion = "low"
        traffic_speed = speed_limit
    elif 29 <= t < 48:
        congestion = "moderate"
        traffic_speed = max(0.0, speed_limit * 0.4)
    elif 71 <= t < 96:
        congestion = "moderate"
        traffic_speed = round(speed_limit * 0.85, 1)
    elif 96 <= t < 115:
        congestion = "heavy"
        traffic_speed = round(speed_limit * 0.45, 1)
    else:
        congestion = "low"
        traffic_speed = speed_limit

    # Upcoming stop distance for 3rd & D
    upcoming_stop = None
    if 20 <= t < 48:
        # rough meters to the stop sign at 3rd & D
        upcoming_stop = max(0.0, round((48 - t) * 6.5, 1))
    elif 96 <= t < 105:
        upcoming_stop = max(0.0, round((105 - t) * 5.0, 1))

    incident_ahead = 96 <= t < 105

    return {
        "speed_limit_mph": speed_limit,
        "traffic_speed_mph": round(traffic_speed, 1),
        "congestion_level": congestion,
        "road_grade_percent": grade,
        "upcoming_stop_distance_m": upcoming_stop,
        "incident_ahead": incident_ahead,
    }


# ---------------------------------------------------------------------------
# Vehicle profile (matches the demo Audi A4 in backend/mock_data.py)
# ---------------------------------------------------------------------------

VEHICLE_PROFILE = {
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
        "1": 3.69, "2": 2.15, "3": 1.41, "4": 1.03, "5": 0.79, "6": 0.63
    },
    "vin": None,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_timeline() -> Dict[str, Any]:
    speeds = build_speed_profile()
    path = integrate_path(speeds)

    frames = []
    for f in path:
        t = f["t"]
        loc = {
            "lat": f["lat"],
            "lon": f["lon"],
            "speed_mph": f["speed_mph"],
            "heading_deg": f["heading_deg"],
            "accuracy_m": 5.0,
        }
        perc = perception_for(t, f)
        ctx = road_context_for(t, f)
        frames.append(
            {
                "t": t,
                "location": loc,
                "perception": perc,
                "road_context": ctx,
                "road": f["road"],
            }
        )

    total_distance_m = 0.0
    for i in range(1, len(frames)):
        total_distance_m += haversine_m(
            frames[i - 1]["location"]["lat"], frames[i - 1]["location"]["lon"],
            frames[i]["location"]["lat"], frames[i]["location"]["lon"],
        )

    return {
        "meta": {
            "city": "Davis, CA",
            "duration_s": 120,
            "frame_rate_hz": 1,
            "frame_count": len(frames),
            "total_distance_m": round(total_distance_m, 1),
            "total_distance_mi": round(total_distance_m / 1609.344, 3),
            "waypoints": WAYPOINTS,
            "vehicle_profile": VEHICLE_PROFILE,
            "schema_notes": (
                "Each frame's `location`, `perception`, and `road_context` match the "
                "Pydantic models in backend/models.py. `lead_vehicle_distance_m` is an "
                "extra numeric field for the map UI; the backend's PerceptionInput "
                "uses the categorical `lead_vehicle_distance` (far/medium/close)."
            ),
        },
        "frames": frames,
    }


def main():
    timeline = build_timeline()
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drive_timeline.json")
    with open(out_path, "w") as f:
        json.dump(timeline, f, indent=2)
    print(f"Wrote {out_path}")
    print(f"  frames: {timeline['meta']['frame_count']}")
    print(f"  distance: {timeline['meta']['total_distance_mi']} mi "
          f"({timeline['meta']['total_distance_m']} m)")
    speeds = [fr["location"]["speed_mph"] for fr in timeline["frames"]]
    print(f"  speed: min {min(speeds):.1f} / max {max(speeds):.1f} / "
          f"avg {sum(speeds)/len(speeds):.1f} mph")


if __name__ == "__main__":
    main()
