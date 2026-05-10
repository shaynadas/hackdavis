"""
cv_pipeline_pi.py — Raspberry Pi 4B optimized version
Eco-Driving Copilot MVP

Same output schema, same /vision endpoint, same backend push to
/perception/update, same mock mode, same CLI flags as cv_pipeline.py.

What changed for the Pi:
  - NCNN model preferred over .pt        (3-5x faster on ARM)
  - Threaded camera grabber + MJPG       (kills USB latency and stale buffers)
  - imgsz=320                            (Pi can't do 640 at usable FPS)
  - V4L2 backend explicit                (default GStreamer path is slow)
  - Manual annotation                    (results[0].plot() is too slow)
  - No frame-rate sleep on webcam        (Pi is the bottleneck, run flat out)
  - Video files still play at real time  (grabber paces itself)

Before running:
    python -c "from ultralytics import YOLO; YOLO('yolov8n.pt').export(format='ncnn', imgsz=320)"
This produces ./yolov8n_ncnn_model/ which this script auto-detects.
"""

import cv2
import json
import time
import threading
import math
import os
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
PUSH_INTERVAL_MS = 500

# ── Pi Performance Knobs ──────────────────────────────────────────────────────
NCNN_MODEL_DIR = "yolov8n_ncnn_model"
PT_FALLBACK    = "yolov8n.pt"
INFERENCE_IMGSZ = 320          # MUST match what you exported NCNN at
CAPTURE_WIDTH   = 640
CAPTURE_HEIGHT  = 480

# ── Constants ──────────────────────────────────────────────────────────────────
VEHICLE_CLASSES         = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
PEDESTRIAN_CLASS        = 0
ALL_CLASSES             = list(VEHICLE_CLASSES.keys()) + [PEDESTRIAN_CLASS]
STOPPED_SPEED_THRESHOLD = 5.0
SLOW_SPEED_THRESHOLD    = 15.0
BRAKING_SPEED_DROP      = 8.0
TRACK_MAX_AGE           = 10
HISTORY_LEN             = 15
CONF_THRESHOLD          = 0.30


# ── Centroid Tracker (unchanged from cv_pipeline.py) ──────────────────────────
@dataclass
class Track:
    id: int
    centroid: tuple
    history: deque
    age: int = 0
    speed_px_s: float = 0.0
    bbox: tuple = (0, 0, 0, 0)
    cls: int = 2


class CentroidTracker:
    def __init__(self):
        self.next_id = 0
        self.tracks: dict[int, Track] = {}

    def update(self, detections):
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
        matched_tracks, matched_dets = set(), set()

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
    def _calc_speed(history):
        if len(history) < 2:
            return 0.0
        x1, y1, t1 = history[0]
        x2, y2, t2 = history[-1]
        dt = t2 - t1
        return 0.0 if dt < 1e-6 else math.hypot(x2 - x1, y2 - y1) / dt


# ── Classify (unchanged from cv_pipeline.py) ──────────────────────────────────
def classify_traffic(tracks, frame_height):
    roi_y = frame_height * 0.4

    vehicles    = [t for t in tracks.values() if t.cls in VEHICLE_CLASSES and t.centroid[1] >= roi_y]
    pedestrians = [t for t in tracks.values() if t.cls == PEDESTRIAN_CLASS]

    vehicle_count = len(vehicles)
    stopped_count = sum(1 for t in vehicles if t.speed_px_s < STOPPED_SPEED_THRESHOLD)
    slow_count    = sum(1 for t in vehicles if STOPPED_SPEED_THRESHOLD <= t.speed_px_s < SLOW_SPEED_THRESHOLD)

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

    lead = max(vehicles, key=lambda t: t.centroid[1]) if vehicles else None

    lead_status   = _lead_status(lead)
    lead_distance = _lead_distance(lead, frame_height)

    if lead_distance == "close" and state in ("slowing", "stopped"):
        confidence = min(0.95, confidence + 0.08)

    hazard   = stopped_count > 0 or lead_status == "braking"
    accident = _detect_accident(vehicles)

    return {
        "traffic_state":            state,
        "lead_vehicle_status":      lead_status,
        "lead_vehicle_distance":    lead_distance,
        "stopped_vehicle_detected": stopped_count > 0,
        "possible_incident":        accident,
        "hazard_detected":          hazard,
        "pedestrian_detected":      len(pedestrians) > 0,
        "confidence":               round(confidence, 2),
    }


def _lead_status(lead):
    if lead is None:
        return "none"
    if lead.speed_px_s < STOPPED_SPEED_THRESHOLD:
        return "stopped"
    if len(lead.history) >= 6:
        speeds = _speed_series(lead.history)
        early = sum(speeds[:len(speeds)//2]) / max(1, len(speeds)//2)
        late  = sum(speeds[len(speeds)//2:]) / max(1, len(speeds) - len(speeds)//2)
        if early - late > BRAKING_SPEED_DROP:
            return "braking"
    if lead.speed_px_s < SLOW_SPEED_THRESHOLD:
        return "braking"
    return "moving"


def _speed_series(history):
    pts = list(history)
    speeds = []
    for i in range(1, len(pts)):
        x1, y1, t1 = pts[i-1]
        x2, y2, t2 = pts[i]
        dt = t2 - t1
        if dt > 1e-6:
            speeds.append(math.hypot(x2-x1, y2-y1) / dt)
    return speeds or [0.0]


def _lead_distance(lead, frame_height):
    if lead is None:
        return "far"
    y_frac = lead.centroid[1] / frame_height
    if y_frac > 0.75:
        return "close"
    elif y_frac > 0.55:
        return "medium"
    return "far"


def _detect_accident(vehicles):
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


# ── Threaded Camera Grabber (NEW for Pi) ──────────────────────────────────────
class ThreadedCamera:
    """
    Always serves the latest frame, never a stale buffered one.
    For webcams: grabs as fast as USB allows, MJPG fourcc to avoid YUYV decode.
    For video files: paces itself to file FPS so testing matches real-time.
    """
    def __init__(self, src, width=CAPTURE_WIDTH, height=CAPTURE_HEIGHT):
        self._src = src
        self._is_file = not isinstance(src, int)

        if self._is_file:
            self.cap = cv2.VideoCapture(src)
        else:
            self.cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.frame = None
        self._running = True
        self._lock = threading.Lock()
        self._t = threading.Thread(target=self._grab, daemon=True)
        self._t.start()
        time.sleep(0.5)  # warm up

    def _grab(self):
        target_dt = (1.0 / self._fps) if self._is_file else 0.0
        while self._running:
            t0 = time.time()
            ok, f = self.cap.read()
            if ok:
                with self._lock:
                    self.frame = f
            elif self._is_file:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            if target_dt:
                time.sleep(max(0, target_dt - (time.time() - t0)))

    def read(self):
        with self._lock:
            return None if self.frame is None else self.frame.copy()

    def isOpened(self):
        return self.cap.isOpened()

    def stop(self):
        self._running = False
        time.sleep(0.1)
        self.cap.release()


# ── Lightweight annotation (replaces results[0].plot()) ───────────────────────
def _annotate(frame, tracks, perception):
    h = frame.shape[0]
    roi_y = int(h * 0.4)
    cv2.line(frame, (0, roi_y), (frame.shape[1], roi_y), (80, 80, 80), 1)

    for t in tracks.values():
        x1, y1, x2, y2 = t.bbox
        if t.cls == PEDESTRIAN_CLASS:
            color = (0, 200, 255)
        elif t.speed_px_s < STOPPED_SPEED_THRESHOLD:
            color = (0, 0, 255)
        else:
            color = (0, 255, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, f"#{t.id} {int(t.speed_px_s)}px/s",
                    (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    line1 = f"{perception['traffic_state']} | lead: {perception['lead_vehicle_status']} {perception['lead_vehicle_distance']}"
    cv2.putText(frame, line1, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y = 48
    if perception["hazard_detected"]:
        cv2.putText(frame, "HAZARD", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2); y += 22
    if perception["pedestrian_detected"]:
        cv2.putText(frame, "PED", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2); y += 22
    if perception["possible_incident"]:
        cv2.putText(frame, "INCIDENT", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return frame


# ── Main Pipeline ──────────────────────────────────────────────────────────────
class CVPipeline:
    def __init__(self, source=0, use_mock=False, backend_url=BACKEND_URL,
                 push_enabled=True, draw=True):
        self.source       = source
        self.use_mock     = use_mock or not YOLO_AVAILABLE
        self.backend_url  = backend_url
        self.push_enabled = push_enabled
        self.draw         = draw
        self.tracker      = CentroidTracker()
        self.latest       = self._mock_result()
        self.latest_frame = None
        self._running     = False
        self._thread      = None
        self._lock        = threading.Lock()
        self._last_push   = 0.0
        self._fps_t       = time.time()
        self._fps_n       = 0
        self._fps         = 0.0

        if not self.use_mock:
            self.model = self._load_model()

    def _load_model(self):
        if os.path.isdir(NCNN_MODEL_DIR):
            print(f"[cv_pipeline] Loading NCNN model from {NCNN_MODEL_DIR}/")
            m = YOLO(NCNN_MODEL_DIR, task="detect")
        else:
            print(f"[cv_pipeline] {NCNN_MODEL_DIR}/ not found, falling back to {PT_FALLBACK} (slower!)")
            print(f"[cv_pipeline] Run this once to fix: ")
            print(f"[cv_pipeline]   python -c \"from ultralytics import YOLO; YOLO('{PT_FALLBACK}').export(format='ncnn', imgsz={INFERENCE_IMGSZ})\"")
            m = YOLO(PT_FALLBACK)
        # Warm up so the first frame isn't slow
        import numpy as np
        dummy = np.zeros((CAPTURE_HEIGHT, CAPTURE_WIDTH, 3), dtype=np.uint8)
        m(dummy, imgsz=INFERENCE_IMGSZ, verbose=False)
        print("[cv_pipeline] Model warmed up.")
        return m

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[cv_pipeline] Started. source={self.source} mock={self.use_mock}")

    def stop(self):
        self._running = False

    def get_result(self):
        with self._lock:
            return dict(self.latest)

    def get_frame(self):
        with self._lock:
            return None if self.latest_frame is None else self.latest_frame.copy()

    def get_fps(self):
        return self._fps

    def _push_to_backend(self, result):
        if not self.push_enabled:
            return
        now = time.time() * 1000
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
            print(f"[cv_pipeline] Backend push failed: {e}")

    def _loop(self):
        if self.use_mock:
            self._mock_loop()
            return

        cam = ThreadedCamera(self.source)
        if not cam.isOpened():
            print(f"[cv_pipeline] Cannot open '{self.source}'. Falling back to mock.")
            cam.stop()
            self.use_mock = True
            self._mock_loop()
            return

        print(f"[cv_pipeline] Camera opened, running inference at imgsz={INFERENCE_IMGSZ}")

        while self._running:
            frame = cam.read()
            if frame is None:
                time.sleep(0.005)
                continue

            result = self._process_frame(frame)
            with self._lock:
                self.latest = result
            self._push_to_backend(result)
            self._tick_fps()

        cam.stop()

    def _process_frame(self, frame):
        h = frame.shape[0]

        results = self.model(
            frame,
            imgsz=INFERENCE_IMGSZ,
            classes=ALL_CLASSES,
            conf=CONF_THRESHOLD,
            verbose=False,
        )

        detections = []
        for box in results[0].boxes:
            cls = int(box.cls[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            detections.append((cx, cy, x1, y1, x2, y2, cls))

        tracks = self.tracker.update(detections)
        perception = classify_traffic(tracks, h)

        if self.draw:
            annotated = _annotate(frame.copy(), tracks, perception)
            cv2.putText(annotated, f"{self._fps:.1f} FPS",
                        (annotated.shape[1] - 110, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            with self._lock:
                self.latest_frame = annotated

        return perception

    def _tick_fps(self):
        self._fps_n += 1
        now = time.time()
        if now - self._fps_t >= 1.0:
            self._fps = self._fps_n / (now - self._fps_t)
            self._fps_n = 0
            self._fps_t = now

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
            time.sleep(1)

    @staticmethod
    def _mock_result():
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

    app = FastAPI(title="Eco-Copilot CV Pipeline (Pi)")
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
        if _pipeline is None:
            return CVPipeline._mock_result()
        return _pipeline.get_result()

    @app.get("/vision/fps")
    def get_fps():
        return {"fps": _pipeline.get_fps() if _pipeline else 0}

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

    # Usage: python cv_pipeline_pi.py [source] [--no-push] [--no-window]
    #   source: "0" for webcam (default), "mock", or video path
    #   --no-push:   disable backend push
    #   --no-window: disable preview (use this when ssh'd headless)

    source = sys.argv[1] if len(sys.argv) > 1 else "0"
    push_enabled = "--no-push" not in sys.argv
    show_window  = "--no-window" not in sys.argv

    use_mock = source == "mock"
    src = int(source) if source.isdigit() else source

    print(f"[cv_pipeline] source={source} push={push_enabled} window={show_window}")
    print(f"[cv_pipeline] backend={BACKEND_URL}")

    pipeline = CVPipeline(source=src, use_mock=use_mock,
                          push_enabled=push_enabled, draw=show_window)
    pipeline.start()

    last_print = 0.0
    try:
        print("[cv_pipeline] Running. Press q in window or Ctrl+C to stop.")
        while True:
            if show_window and not use_mock:
                frame = pipeline.get_frame()
                if frame is not None:
                    cv2.imshow("cv_pipeline_pi", frame)
                if (cv2.waitKey(1) & 0xFF) == ord('q'):
                    break
            else:
                time.sleep(0.05)

            now = time.time()
            if now - last_print >= 1.0:
                result = pipeline.get_result()
                fps = pipeline.get_fps()
                print(f"[{time.strftime('%H:%M:%S')}] {fps:.1f} FPS  {json.dumps(result)}")
                last_print = now
    except KeyboardInterrupt:
        print("\n[cv_pipeline] Stopping...")
    finally:
        pipeline.stop()
        if show_window:
            cv2.destroyAllWindows()
        print("[cv_pipeline] Stopped.")
