"""
Shared state module — Person A writes tracks, Person C writes sensor data.
Person B reads everything and serves it via /state.
Lock interface agreed at Hour 1 sync.
"""

import threading
import time

_lock = threading.Lock()

# ── Contract JSON (stub values — replace with real data as A and C connect) ──
_state = {
    # Written by Person A (CV/Edge)
    "tracks": {
        # track_id → track object
        # "42": {
        #   "class": "car",          # yolo class label
        #   "bbox": [x, y, w, h],
        #   "speed_mps": 0.0,
        #   "idle": False,
        #   "idle_seconds": 0,
        #   "cumulative_co2_g": 0.0,
        #   "smoke_detected": False,
        # }
    },
    "counts": {
        "cars": 0,
        "trucks": 0,
        "buses": 0,
        "pedestrians": 0,
        "cyclists": 0,
    },
    "session_co2_g": 0.0,
    "heatmap": [],              # 32×18 flat list of CO2 per cell (will be populated by A)
    "frame_w": 1280,
    "frame_h": 720,

    # Written by Person C (Sensor/Reasoning)
    "pm25_ugm3": 0.0,           # raw sensor reading
    "fused_aq_index": 0,        # 0–100 fused index
    "sensor_mode": "live",      # "live" | "playback"
    "alerts": [],               # list of alert dicts from Prolog engine
    # alert dict: { "type": str, "message": str, "severity": "info"|"warn"|"critical", "ts": float }

    # Written by Person B (this file — traffic signal recommendation)
    "signal": {
        "current_cycle_co2_g": 0.0,
        "recommended_cycle_co2_g": 0.0,
        "reduction_pct": 0.0,
        "recommended_extension_s": 0,
    },

    # Meta
    "ts": time.time(),
    "session_start": time.time(),
}

def get():
    with _lock:
        return dict(_state)

def update(patch: dict):
    """Merge patch dict into shared state (shallow merge at top level)."""
    with _lock:
        _state.update(patch)
        _state["ts"] = time.time()

def update_signal(current_co2, recommended_co2, reduction_pct, extension_s):
    with _lock:
        _state["signal"] = {
            "current_cycle_co2_g": current_co2,
            "recommended_cycle_co2_g": recommended_co2,
            "reduction_pct": reduction_pct,
            "recommended_extension_s": extension_s,
        }
        _state["ts"] = time.time()
