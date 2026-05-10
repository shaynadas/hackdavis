"""
cv_pipeline.py — Person A: Camera / CV Perception
Eco-Driving Copilot MVP

Real-time integration with backend via /perception/update endpoint.
"""

import cv2
import json
import time
import threading
import math
import requests
from collections import deque
from dataclasses import dataclass
from typing import Optional

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("[cv_pipeline] WARNING: ultralytics not installed. Using mock output.")

# ── Backend Integration ───────────────────────────────────────────────────────
BACKEND_URL = "http://localhost:8000"
PUSH_INTERVAL_MS = 500  # Push to backend every 500ms to avoid overwhelming it

# ── Constants ──────────────────────────────────────────────────────────────────
VEHICLE_CLASSES         = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
PEDESTRIAN_CLASS        = 0      # YOLO class 0 = person
ALL_CLASSES             = list(VEHICLE_CLASSES.keys()) + [PEDESTRIAN_CLASS]
STOPPED_SPEED_THRESHOLD = 5.0    # px/s
SLOW_SPEED_THRESHOLD    = 15.0   # px/s
BRAKING_SPEED_DROP      = 8.0    # px/s drop over history = braking
TRACK_MAX_AGE           = 10
HISTORY_LEN             = 15
CONF_THRESHOLD          = 0.30


# ── Centroid Tracker ───────────────────────────────────────────────────────────
@dataclass
class Track:
    id: int
    centroid: tuple
    history: deque          # (cx, cy, timestamp)
    age: int = 0
    speed_px_s: float = 0.0
    bbox: tuple = (0, 0, 0, 0)
    cls: int = 2            # YOLO class id


class CentroidTracker:
    def __init__(self):
        self.next_id = 0
        self.tracks: dict[int, Track] = {}

    def update(self, detections: list[tuple]) -> dict[int, Track]:
        """detections: list of (cx, cy, x1, y1, x2, y2, cls)"""
        now = time.time()

        if not detections:
            dead = [tid for tid, t in self.tracks.items() if t.age >= TRACK_MAX_AGE]
            for tid in dead:
                del self.tracks[tid]
            for t in self.tracks.values():
                t.age += 1
            return self.tracks

        det_centroids = [(d[0], d[1]) for d in detections]
        det_bboxes    = [(d[2], d[3], d[4], d[5]) for d in detections]
        det_classes   = [d[6] for d in detections]

        if not self.tracks:
            for i, (cx, cy) in enumerate(det_centroids):
                self._new_track(cx, cy, det_bboxes[i], det_classes[i], now)
            return self.tracks

        track_ids   = list(self.tracks.keys())
        track_cents = [self.tracks[tid].centroid for tid in track_ids]
        matched_tracks = set()
        matched_dets   = set()

        for di, (cx, cy) in enumerate(det_centroids):
            best_dist, best_tid = float("inf"), None
            for ti, tid in enumerate(track_ids):
                if ti in matched_tracks:
                    continue
                dist = math.hypot(cx - track_cents[ti][0], cy - track_cents[ti][1])
                if dist < best_dist:
                    best_dist, best_tid = dist, (ti, tid)

            if best_tid and best_dist < 80:
                ti, tid = best_tid
                matched_tracks.add(ti)
                matched_dets.add(di)
                t = self.tracks[tid]
                t.centroid = (cx, cy)
                t.bbox = det_bboxes[di]
                t.cls  = det_classes[di]
                t.history.append((cx, cy, now))
                t.age = 0
                t.speed_px_s = self._calc_speed(t.history)

        for di, (cx, cy) in enumerate(det_centroids):
            if di not in matched_dets:
                self._new_track(cx, cy, det_bboxes[di], det_classes[di], now)

        dead = []
        for ti, tid in enumerate(track_ids):
            if ti not in matched_tracks:
                self.tracks[tid].age += 1
            if self.tracks[tid].age >= TRACK_MAX_AGE:
                dead.append(tid)
        for tid in set(dead):
            self.tracks.pop(tid, None)

        return self.tracks

    def _new_track(self, cx, cy, bbox, cls, now):
        h = deque(maxlen=HISTORY_LEN)
        h.append((cx, cy, now))
        self.tracks[self.next_id] = Track(
            id=self.next_id, centroid=(cx, cy), history=h, bbox=bbox, cls=cls
        )
        self.next_id += 1

    @staticmethod
    def _calc_speed(history: deque) -> float:
        if len(history) < 2:
            return 0.0
        x1, y1, t1 = history[0]
        x2, y2, t2 = history[-1]
        dt = t2 - t1
        return 0.0 if dt < 1e-6 else math.hypot(x2 - x1, y2 - y1) / dt


# ── Classify ───────────────────────────────────────────────────────────────────
def classify_traffic(tracks: dict, frame_height: int) -> dict:
    roi_y = frame_height * 0.4

    vehicles    = [t for t in tracks.values() if t.cls in VEHICLE_CLASSES and t.centroid[1] >= roi_y]
    pedestrians = [t for t in tracks.values() if t.cls == PEDESTRIAN_CLASS]

    vehicle_count = len(vehicles)
    stopped_count = sum(1 for t in vehicles if t.speed_px_s < STOPPED_SPEED_THRESHOLD)
    slow_count    = sum(1 for t in vehicles if STOPPED_SPEED_THRESHOLD <= t.speed_px_s < SLOW_SPEED_THRESHOLD)

    # ── traffic_state ──
    if vehicle_count == 0:
        state, confidence = "clear", 0.85
    elif stopped_count >= max(1, vehicle_count * 0.5):
        state, confidence = "stopped", 0.82
    elif (stopped_count + slow_count) >= max(1, vehicle_count * 0.4):
        state, confidence = "slowing", 0.76
    elif slow_count >= max(1, vehicle_count * 0.3):
        state, confidence = "moderate", 0.70
    else:
        state, confidence = "clear", 0.80

    # ── lead vehicle ──
    lead = max(vehicles, key=lambda t: t.centroid[1]) if vehicles else None

    lead_status   = _lead_status(lead)
    lead_distance = _lead_distance(lead, frame_height)

    if lead_distance == "close" and state in ("slowing", "stopped"):
        confidence = min(0.95, confidence + 0.08)

    # ── hazard: stopped vehicle in ROI or lead braking ──
    hazard = stopped_count > 0 or lead_status == "braking"

    # ── accident: heuristic — multiple stopped vehicles clustered ──
    accident = _detect_accident(vehicles)

    return {
        "traffic_state":           state,
        "lead_vehicle_status":     lead_status,
        "lead_vehicle_distance":   lead_distance,
        "stopped_vehicle_detected": stopped_count > 0,
        "possible_incident":       accident,
        "hazard_detected":         hazard,
        "pedestrian_detected":     len(pedestrians) > 0,
        "confidence":              round(confidence, 2),
    }


def _lead_status(lead: Optional[Track]) -> str:
    """Is the lead vehicle braking, stopped, or moving?"""
    if lead is None:
        return "none"
    if lead.speed_px_s < STOPPED_SPEED_THRESHOLD:
        return "stopped"
    # Braking = speed was higher earlier and dropped sharply
    if len(lead.history) >= 6:
        speeds = _speed_series(lead.history)
        early = sum(speeds[:len(speeds)//2]) / max(1, len(speeds)//2)
        late  = sum(speeds[len(speeds)//2:]) / max(1, len(speeds) - len(speeds)//2)
        if early - late > BRAKING_SPEED_DROP:
            return "braking"
    if lead.speed_px_s < SLOW_SPEED_THRESHOLD:
        return "braking"  # Backend enum only has: none, moving, braking, stopped
    return "moving"


def _speed_series(history: deque) -> list:
    pts = list(history)
    speeds = []
    for i in range(1, len(pts)):
        x1, y1, t1 = pts[i-1]
        x2, y2, t2 = pts[i]
        dt = t2 - t1
        if dt > 1e-6:
            speeds.append(math.hypot(x2-x1, y2-y1) / dt)
    return speeds or [0.0]


def _lead_distance(lead: Optional[Track], frame_height: int) -> str:
    """Estimate distance based on how low in frame the lead vehicle is."""
    if lead is None:
        return "far"  # Default to "far" when no lead vehicle (backend enum doesn't have "none")
    y_frac = lead.centroid[1] / frame_height
    if y_frac > 0.75:
        return "close"
    elif y_frac > 0.55:
        return "medium"
    return "far"


def _detect_accident(vehicles: list) -> bool:
    """
    Heuristic: 2+ stopped vehicles within 60px of each other = possible accident.
    """
    stopped = [v for v in vehicles if v.speed_px_s < STOPPED_SPEED_THRESHOLD]
    if len(stopped) < 2:
        return False
    for i in range(len(stopped)):
        for j in range(i+1, len(stopped)):
            dist = math.hypot(
                stopped[i].centroid[0] - stopped[j].centroid[0],
                stopped[i].centroid[1] - stopped[j].centroid[1],
            )
            if dist < 60:
                return True
    return False


# ── Main Pipeline ──────────────────────────────────────────────────────────────
class CVPipeline:
    def __init__(self, source=0, use_mock=False, backend_url=BACKEND_URL, push_enabled=True):
        self.source       = source
        self.use_mock     = use_mock or not YOLO_AVAILABLE
        self.backend_url  = backend_url
        self.push_enabled = push_enabled
        self.tracker      = CentroidTracker()
        self.latest       = self._mock_result()
        self._running     = False
        self._thread      = None
        self._lock        = threading.Lock()
        self._last_push   = 0.0

        if not self.use_mock:
            print("[cv_pipeline] Loading YOLOv8n...")
            self.model = YOLO("yolov8n.pt")
            print("[cv_pipeline] YOLOv8n ready.")

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[cv_pipeline] Started. source={self.source} mock={self.use_mock}")

    def stop(self):
        self._running = False

    def get_result(self) -> dict:
        with self._lock:
            return dict(self.latest)

    def _push_to_backend(self, result: dict):
        """Push perception result to the backend's /perception/update endpoint."""
        if not self.push_enabled:
            return
        
        now = time.time() * 1000  # ms
        if now - self._last_push < PUSH_INTERVAL_MS:
            return
        
        self._last_push = now
        try:
            resp = requests.post(
                f"{self.backend_url}/perception/update",
                json=result,
                timeout=1.0
            )
            if resp.status_code == 200:
                print(f"[cv_pipeline] Pushed perception: {result.get('traffic_state')}")
            else:
                print(f"[cv_pipeline] Backend returned {resp.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[cv_pipeline] Failed to push to backend: {e}")

    def _loop(self):
        if self.use_mock:
            self._mock_loop()
            return

        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            print(f"[cv_pipeline] Cannot open '{self.source}'. Falling back to mock.")
            self.use_mock = True
            self._mock_loop()
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_delay = 1.0 / fps

        while self._running:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            t0 = time.time()
            result = self._process_frame(frame)
            with self._lock:
                self.latest = result
            self._push_to_backend(result)
            time.sleep(max(0, frame_delay - (time.time() - t0)))

        cap.release()

    def _process_frame(self, frame) -> dict:
        h, w = frame.shape[:2]
        results = self.model(frame, classes=ALL_CLASSES, conf=CONF_THRESHOLD, verbose=False)

        detections = []
        for box in results[0].boxes:
            cls = int(box.cls[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cx, cy = (x1+x2)//2, (y1+y2)//2
            detections.append((cx, cy, x1, y1, x2, y2, cls))

        tracks = self.tracker.update(detections)
        return classify_traffic(tracks, h)

    def _mock_loop(self):
        scenarios = [
            {"traffic_state": "clear",    "lead_vehicle_status": "none",    "lead_vehicle_distance": "far",    "stopped_vehicle_detected": False, "possible_incident": False, "hazard_detected": False, "pedestrian_detected": False, "confidence": 0.88},
            {"traffic_state": "moderate", "lead_vehicle_status": "moving",  "lead_vehicle_distance": "far",    "stopped_vehicle_detected": False, "possible_incident": False, "hazard_detected": False, "pedestrian_detected": False, "confidence": 0.72},
            {"traffic_state": "slowing",  "lead_vehicle_status": "braking", "lead_vehicle_distance": "medium", "stopped_vehicle_detected": False, "possible_incident": False, "hazard_detected": False, "pedestrian_detected": True,  "confidence": 0.76},
            {"traffic_state": "slowing",  "lead_vehicle_status": "braking", "lead_vehicle_distance": "close",  "stopped_vehicle_detected": True,  "possible_incident": False, "hazard_detected": True,  "pedestrian_detected": False, "confidence": 0.82},
            {"traffic_state": "stopped",  "lead_vehicle_status": "stopped", "lead_vehicle_distance": "close",  "stopped_vehicle_detected": True,  "possible_incident": False, "hazard_detected": True,  "pedestrian_detected": False, "confidence": 0.84},
            {"traffic_state": "stopped",  "lead_vehicle_status": "stopped", "lead_vehicle_distance": "close",  "stopped_vehicle_detected": True,  "possible_incident": True,  "hazard_detected": True,  "pedestrian_detected": True,  "confidence": 0.79},
            {"traffic_state": "moderate", "lead_vehicle_status": "moving",  "lead_vehicle_distance": "medium", "stopped_vehicle_detected": False, "possible_incident": False, "hazard_detected": False, "pedestrian_detected": False, "confidence": 0.70},
            {"traffic_state": "clear",    "lead_vehicle_status": "moving",  "lead_vehicle_distance": "far",    "stopped_vehicle_detected": False, "possible_incident": False, "hazard_detected": False, "pedestrian_detected": False, "confidence": 0.85},
        ]
        i = 0
        while self._running:
            scenario = dict(scenarios[i % len(scenarios)])
            with self._lock:
                self.latest = scenario
            self._push_to_backend(scenario)
            i += 1
            time.sleep(1)  # Push mock data every 1 second

    @staticmethod
    def _mock_result() -> dict:
        return {
            "traffic_state":            "slowing",
            "lead_vehicle_status":      "braking",
            "lead_vehicle_distance":    "close",
            "stopped_vehicle_detected": True,
            "possible_incident":        False,
            "hazard_detected":          True,
            "pedestrian_detected":      False,
            "confidence":               0.82,
        }


# ── FastAPI ────────────────────────────────────────────────────────────────────
try:
    from fastapi import FastAPI, Query
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="Eco-Copilot CV Pipeline")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    _pipeline: Optional[CVPipeline] = None

    @app.on_event("startup")
    async def startup():
        global _pipeline
        _pipeline = CVPipeline(source=0, use_mock=False)
        _pipeline.start()

    @app.on_event("shutdown")
    async def shutdown():
        if _pipeline:
            _pipeline.stop()

    @app.get("/vision")
    def get_vision():
        """
        {
          "traffic_state": "slowing",
          "lead_vehicle_status": "braking",
          "lead_vehicle_distance": "close",
          "stopped_vehicle_detected": true,
          "possible_incident": false,
          "hazard_detected": true,
          "pedestrian_detected": false,
          "confidence": 0.82
        }
        """
        if _pipeline is None:
            return CVPipeline._mock_result()
        return _pipeline.get_result()

    @app.post("/vision/source")
    def set_source(path: str = Query(..., description="Video file path or '0' for webcam")):
        global _pipeline
        if _pipeline:
            _pipeline.stop()
        src = 0 if path == "0" else path
        _pipeline = CVPipeline(source=src)
        _pipeline.start()
        return {"status": "ok", "source": path}

except ImportError:
    print("[cv_pipeline] FastAPI not available.")
    app = None


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    # Usage: python cv_pipeline.py [source] [--no-push]
    # source: "0" for webcam (default), "mock" for mock data, or path to video file
    # --no-push: disable pushing to backend
    
    source = sys.argv[1] if len(sys.argv) > 1 else "0"  # Default to webcam
    push_enabled = "--no-push" not in sys.argv
    
    use_mock = source == "mock"
    src = 0 if source == "0" else source

    print(f"[cv_pipeline] Starting with source={source}, push_enabled={push_enabled}")
    print(f"[cv_pipeline] Backend URL: {BACKEND_URL}")
    
    pipeline = CVPipeline(source=src, use_mock=use_mock, push_enabled=push_enabled)
    pipeline.start()
    
    try:
        print("[cv_pipeline] Running... Press Ctrl+C to stop.")
        while True:
            result = pipeline.get_result()
            print(f"[{time.strftime('%H:%M:%S')}] {json.dumps(result)}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[cv_pipeline] Stopping...")
    finally:
        pipeline.stop()
        print("[cv_pipeline] Stopped.")
