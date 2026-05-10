"""
cv_pipeline.py — Person A: Camera / CV Perception
Eco-Driving Copilot MVP

Real-time integration with backend via /perception/update endpoint.
Also hosts a FastAPI server on port 8001 to stream both smooth and annotated MJPEG video.
"""

import cv2
import json
import time
import threading
import math
import requests
import numpy as np
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

    # ── accident: heuristic, multiple stopped vehicles clustered ──
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

        self.latest_raw_frame_jpg = None
        self.latest_annotated_frame_jpg = None
        self.raw_frame = None

        self._running     = False
        self._capture_thread = None
        self._inference_thread = None
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
        if self.use_mock:
            self._capture_thread = threading.Thread(target=self._mock_loop, daemon=True)
            self._capture_thread.start()
        else:
            self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._capture_thread.start()
            self._inference_thread = threading.Thread(target=self._inference_loop, daemon=True)
            self._inference_thread.start()
        print(f"[cv_pipeline] Started. source={self.source} mock={self.use_mock}")

    def stop(self):
        self._running = False

    def get_result(self) -> dict:
        with self._lock:
            return dict(self.latest)

    def get_frame(self):
        with self._lock:
            return None if self.latest_frame is None else self.latest_frame.copy()

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
            if resp.status_code != 200:
                print(f"[cv_pipeline] Backend returned {resp.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[cv_pipeline] Failed to push to backend: {e}")

    def _capture_loop(self):
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            print(f"[cv_pipeline] Cannot open '{self.source}'.")
            self._running = False
            return

        while self._running:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            
            # Save raw frame for smooth video feed
            ret_enc, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            jpg_bytes = buffer.tobytes() if ret_enc else None

            with self._lock:
                self.raw_frame = frame.copy()
                self.latest_raw_frame_jpg = jpg_bytes
            
            # Sleep slightly to not hog CPU, 30FPS is ~0.033
            time.sleep(0.01)

        cap.release()

    def _inference_loop(self):
        while self._running:
            frame_to_process = None
            with self._lock:
                if self.raw_frame is not None:
                    frame_to_process = self.raw_frame.copy()

            if frame_to_process is None:
                time.sleep(0.05)
                continue
            
            # Run YOLO (choppy because it takes time)
            h, w = frame_to_process.shape[:2]
            results = self.model(frame_to_process, classes=ALL_CLASSES, conf=CONF_THRESHOLD, verbose=False)

            detections = []
            for box in results[0].boxes:
                cls = int(box.cls[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx, cy = (x1+x2)//2, (y1+y2)//2
                detections.append((cx, cy, x1, y1, x2, y2, cls))

            tracks = self.tracker.update(detections)
            perception = classify_traffic(tracks, h)

            annotated = results[0].plot()
            line1 = f"{perception['traffic_state']} | lead: {perception['lead_vehicle_status']} {perception['lead_vehicle_distance']}"
            cv2.putText(annotated, line1, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            if perception["hazard_detected"]:
                cv2.putText(annotated, "HAZARD", (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            if perception["pedestrian_detected"]:
                cv2.putText(annotated, "PED", (10, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
            if perception["possible_incident"]:
                cv2.putText(annotated, "INCIDENT", (10, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            ret_enc, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            jpg_bytes = buffer.tobytes() if ret_enc else None

            with self._lock:
                self.latest = perception
                self.latest_annotated_frame_jpg = jpg_bytes

            self._push_to_backend(perception)

    def _mock_loop(self):
        scenarios = [
            {"traffic_state": "clear",    "lead_vehicle_status": "none",    "lead_vehicle_distance": "far",    "stopped_vehicle_detected": False, "possible_incident": False, "hazard_detected": False, "pedestrian_detected": False, "confidence": 0.88},
            {"traffic_state": "moderate", "lead_vehicle_status": "moving",  "lead_vehicle_distance": "far",    "stopped_vehicle_detected": False, "possible_incident": False, "hazard_detected": False, "pedestrian_detected": False, "confidence": 0.72},
            {"traffic_state": "slowing",  "lead_vehicle_status": "braking", "lead_vehicle_distance": "medium", "stopped_vehicle_detected": False, "possible_incident": False, "hazard_detected": False, "pedestrian_detected": True,  "confidence": 0.76},
            {"traffic_state": "slowing",  "lead_vehicle_status": "braking", "lead_vehicle_distance": "close",  "stopped_vehicle_detected": True,  "possible_incident": False, "hazard_detected": True,  "pedestrian_detected": False, "confidence": 0.82},
            {"traffic_state": "stopped",  "lead_vehicle_status": "stopped", "lead_vehicle_distance": "close",  "stopped_vehicle_detected": True,  "possible_incident": False, "hazard_detected": True,  "pedestrian_detected": False, "confidence": 0.84},
        ]
        i = 0
        while self._running:
            scenario = dict(scenarios[i % len(scenarios)])
            
            # Generate a mock smooth frame (changes position slightly)
            frame_raw = np.zeros((480, 640, 3), dtype=np.uint8)
            x_offset = int(math.sin(time.time() * 2) * 50)
            cv2.putText(frame_raw, "MOCK CAMERA FEED (SMOOTH)", (100 + x_offset, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
            ret1, buf1 = cv2.imencode('.jpg', frame_raw, [cv2.IMWRITE_JPEG_QUALITY, 80])
            
            # Generate mock annotated frame (choppy)
            frame_ann = frame_raw.copy()
            cv2.putText(frame_ann, "ANNOTATED YOLO VIEW", (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            cv2.putText(frame_ann, f"State: {scenario['traffic_state']}", (100, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            
            # Draw a fake bounding box that moves around
            box_x = 250 + x_offset
            box_y = 300
            cv2.rectangle(frame_ann, (box_x, box_y), (box_x + 100, box_y + 80), (0, 255, 0), 3)
            cv2.putText(frame_ann, "ID:99 12.0px/s", (box_x, box_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            ret2, buf2 = cv2.imencode('.jpg', frame_ann, [cv2.IMWRITE_JPEG_QUALITY, 80])

            with self._lock:
                self.latest = scenario
                self.latest_raw_frame_jpg = buf1.tobytes() if ret1 else None
                self.latest_annotated_frame_jpg = buf2.tobytes() if ret2 else None

            self._push_to_backend(scenario)
            i += 1
            time.sleep(1)

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
    from fastapi.responses import StreamingResponse

    app = FastAPI(title="Eco-Copilot CV Pipeline")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    _pipeline: Optional[CVPipeline] = None

    # App state globals
    GLOBAL_SOURCE = 0
    GLOBAL_USE_MOCK = False
    GLOBAL_PUSH_ENABLED = True

    @app.on_event("startup")
    async def startup():
        global _pipeline
        _pipeline = CVPipeline(source=GLOBAL_SOURCE, use_mock=GLOBAL_USE_MOCK, push_enabled=GLOBAL_PUSH_ENABLED)
        _pipeline.start()

    @app.on_event("shutdown")
    async def shutdown():
        if _pipeline:
            _pipeline.stop()

    @app.get("/vision")
    def get_vision():
        if _pipeline is None:
            return CVPipeline._mock_result()
        return _pipeline.get_result()

    def generate_frames(stream_type: str):
        while True:
            if _pipeline is not None:
                if stream_type == "smooth" and _pipeline.latest_raw_frame_jpg:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + _pipeline.latest_raw_frame_jpg + b'\r\n')
                elif stream_type != "smooth" and _pipeline.latest_annotated_frame_jpg:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + _pipeline.latest_annotated_frame_jpg + b'\r\n')
                else:
                    time.sleep(0.05)
            else:
                time.sleep(0.1)
            # Cap the framerate of the MJPEG stream to avoid flooding network
            time.sleep(0.03)

    @app.get("/video_feed")
    def video_feed(type: str = Query("smooth", description="Stream type: 'smooth' or 'annotated'")):
        return StreamingResponse(generate_frames(type), media_type="multipart/x-mixed-replace; boundary=frame")

except ImportError:
    print("[cv_pipeline] FastAPI not available.")
    app = None


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import uvicorn

    # Usage: python cv_pipeline.py [source] [--no-push] [--no-window]
    # source: "0" for webcam (default), "mock" for mock data, or path to video file
    # --no-push: disable pushing to backend
    # --no-window: disable the live preview window

    source = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "0"
    push_enabled = "--no-push" not in sys.argv
    show_window  = "--no-window" not in sys.argv

    use_mock = source == "mock"
    src = int(source) if source.isdigit() else source

    print(f"[cv_pipeline] Starting with source={source}, push_enabled={push_enabled}, window={show_window}")
    print(f"[cv_pipeline] Backend URL: {BACKEND_URL}")

    # Start FastAPI which will internally start the CVPipeline
    if app:
        GLOBAL_SOURCE = src
        GLOBAL_USE_MOCK = use_mock
        GLOBAL_PUSH_ENABLED = push_enabled
        print("[cv_pipeline] Starting FastAPI server on port 8001")
        uvicorn.run(app, host="0.0.0.0", port=8001)
    else:
        # Fallback if no FastAPI — run pipeline directly with optional window
        pipeline = CVPipeline(source=src, use_mock=use_mock, push_enabled=push_enabled)
        pipeline.start()

        last_print = 0.0
        try:
            print("[cv_pipeline] Running... press q in the window or Ctrl+C to stop.")
            while True:
                if show_window and not use_mock:
                    frame = pipeline.get_result()
                    if frame is not None:
                        cv2.waitKey(1)
                else:
                    time.sleep(0.05)

                now = time.time()
                if now - last_print >= 1.0:
                    result = pipeline.get_result()
                    print(f"[{time.strftime('%H:%M:%S')}] {json.dumps(result)}")
                    last_print = now
        except KeyboardInterrupt:
            print("\n[cv_pipeline] Stopping...")
        finally:
            pipeline.stop()
            if show_window:
                cv2.destroyAllWindows()
            print("[cv_pipeline] Stopped.")
