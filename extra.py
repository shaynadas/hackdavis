"""
cv_pipeline_pi.py — Pi-optimized version
Uses ONNX Runtime instead of ultralytics/torch.
~3-5x faster on Pi 4. ~50MB install instead of 2GB.
"""

import cv2
import json
import time
import threading
import math
import numpy as np
import requests
from collections import deque
from dataclasses import dataclass
from typing import Optional

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    print("[cv_pipeline] WARNING: onnxruntime not installed. Using mock output.")

# ── Backend Integration ───────────────────────────────────────────────────────
BACKEND_URL = "http://localhost:8000"
PUSH_INTERVAL_MS = 500

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
IOU_THRESHOLD           = 0.45

# Pi optimizations
INPUT_SIZE              = 320          # Smaller = much faster
INFERENCE_EVERY_N_FRAMES = 3           # Skip frames between detections


# ── Centroid Tracker (unchanged) ──────────────────────────────────────────────
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

    def update(self, detections: list[tuple]) -> dict[int, Track]:
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


# ── ONNX YOLO Inference ───────────────────────────────────────────────────────
class YOLOOnnx:
    def __init__(self, model_path: str = "yolov8n.onnx"):
        # Use 4 threads on Pi 4 (it has 4 cores)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(model_path, sess_options=opts, providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape
        self.input_size = INPUT_SIZE

    def __call__(self, frame) -> list:
        """Returns list of (cx, cy, x1, y1, x2, y2, cls)"""
        h, w = frame.shape[:2]

        # Letterbox resize
        scale = min(self.input_size / w, self.input_size / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(frame, (new_w, new_h))
        padded = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
        pad_x = (self.input_size - new_w) // 2
        pad_y = (self.input_size - new_h) // 2
        padded[pad_y:pad_y+new_h, pad_x:pad_x+new_w] = resized

        # Preprocess: BGR->RGB, HWC->CHW, normalize
        img = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
        img = img.transpose(2, 0, 1).astype(np.float32) / 255.0
        img = np.expand_dims(img, 0)

        # Inference
        outputs = self.session.run(None, {self.input_name: img})[0]
        # Output shape: (1, 84, num_boxes) for YOLOv8 — 4 bbox + 80 classes

        # Postprocess
        outputs = outputs[0].T  # (num_boxes, 84)
        boxes = outputs[:, :4]
        scores = outputs[:, 4:]

        # Filter to classes we care about
        class_ids = scores.argmax(axis=1)
        confs = scores.max(axis=1)
        mask = (confs > CONF_THRESHOLD) & np.isin(class_ids, ALL_CLASSES)
        boxes, confs, class_ids = boxes[mask], confs[mask], class_ids[mask]

        if len(boxes) == 0:
            return []

        # Convert from cx,cy,w,h to x1,y1,x2,y2 in input space
        cx, cy, bw, bh = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        x1 = cx - bw / 2
        y1 = cy - bh / 2
        x2 = cx + bw / 2
        y2 = cy + bh / 2

        # NMS
        bboxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)
        keep = cv2.dnn.NMSBoxes(
            bboxes_xyxy.tolist(),
            confs.tolist(),
            CONF_THRESHOLD,
            IOU_THRESHOLD,
        )

        detections = []
        if len(keep) > 0:
            keep = keep.flatten() if hasattr(keep, 'flatten') else keep
            for i in keep:
                # Unscale from input_size back to original frame
                bx1 = (x1[i] - pad_x) / scale
                by1 = (y1[i] - pad_y) / scale
                bx2 = (x2[i] - pad_x) / scale
                by2 = (y2[i] - pad_y) / scale
                ccx = int((bx1 + bx2) / 2)
                ccy = int((by1 + by2) / 2)
                detections.append((ccx, ccy, int(bx1), int(by1), int(bx2), int(by2), int(class_ids[i])))

        return detections


# ── Classify ──────────────────────────────────────────────────────────────────
def classify_traffic(tracks: dict, frame_height: int) -> dict:
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

    hazard = stopped_count > 0 or lead_status == "braking"
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
        return "braking" # align with backend enum
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
    if lead is None:
        return "far"
    y_frac = lead.centroid[1] / frame_height
    if y_frac > 0.75:
        return "close"
    elif y_frac > 0.55:
        return "medium"
    return "far"


def _detect_accident(vehicles: list) -> bool:
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


# ── Main Pipeline ─────────────────────────────────────────────────────────────
class CVPipeline:
    def __init__(self, source=0, use_mock=False, model_path="yolov8n.onnx", backend_url=BACKEND_URL, push_enabled=True):
        self.source   = source
        self.use_mock = use_mock or not ONNX_AVAILABLE
        self.backend_url = backend_url
        self.push_enabled = push_enabled
        self.tracker  = CentroidTracker()
        self.latest   = self._mock_result()
        self.latest_frame_jpg = None
        self._running = False
        self._thread  = None
        self._lock    = threading.Lock()
        self.frame_count = 0
        self.last_detections = []
        self._last_push = 0.0

        if not self.use_mock:
            print(f"[cv_pipeline] Loading ONNX model: {model_path}")
            try:
                self.model = YOLOOnnx(model_path)
                print("[cv_pipeline] ONNX model ready.")
            except Exception as e:
                print(f"[cv_pipeline] Failed to load ONNX: {e}. Falling back to mock.")
                self.use_mock = True

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

        # Lower capture resolution helps a lot on Pi
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        last_log = time.time()
        fps_count = 0

        while self._running:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            t0 = time.time()

            # Skip frames — only run YOLO every N frames
            if self.frame_count % INFERENCE_EVERY_N_FRAMES == 0:
                self.last_detections = self.model(frame)

            tracks = self.tracker.update(self.last_detections)
            result = classify_traffic(tracks, frame.shape[0])

            # Annotate frame
            for tid, t in tracks.items():
                x1, y1, x2, y2 = t.bbox
                color = (0, 255, 0) if t.speed_px_s > STOPPED_SPEED_THRESHOLD else (0, 0, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = f"ID:{tid} {t.speed_px_s:.1f}px/s"
                cv2.putText(frame, label, (x1, max(0, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            state = result["traffic_state"]
            cv2.putText(frame, f"State: {state}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 0), 2)
            cv2.putText(frame, f"Lead: {result['lead_vehicle_status']} ({result['lead_vehicle_distance']})", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            ret_enc, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            jpg_bytes = buffer.tobytes() if ret_enc else None

            with self._lock:
                self.latest = result
                self.latest_frame_jpg = jpg_bytes

            self._push_to_backend(result)

            self.frame_count += 1
            fps_count += 1

            # FPS log every 5s
            if time.time() - last_log > 5:
                print(f"[cv_pipeline] FPS: {fps_count / 5:.1f}")
                fps_count = 0
                last_log = time.time()

        cap.release()

    def _mock_loop(self):
        scenarios = [
            {"traffic_state": "clear",    "lead_vehicle_status": "none",    "lead_vehicle_distance": "far",   "stopped_vehicle_detected": False, "possible_incident": False, "hazard_detected": False, "pedestrian_detected": False, "confidence": 0.88},
            {"traffic_state": "moderate", "lead_vehicle_status": "moving",  "lead_vehicle_distance": "far",    "stopped_vehicle_detected": False, "possible_incident": False, "hazard_detected": False, "pedestrian_detected": False, "confidence": 0.72},
            {"traffic_state": "slowing",  "lead_vehicle_status": "braking", "lead_vehicle_distance": "medium", "stopped_vehicle_detected": False, "possible_incident": False, "hazard_detected": False, "pedestrian_detected": True,  "confidence": 0.76},
            {"traffic_state": "slowing",  "lead_vehicle_status": "braking", "lead_vehicle_distance": "close",  "stopped_vehicle_detected": True,  "possible_incident": False, "hazard_detected": True,  "pedestrian_detected": False, "confidence": 0.82},
            {"traffic_state": "stopped",  "lead_vehicle_status": "stopped", "lead_vehicle_distance": "close",  "stopped_vehicle_detected": True,  "possible_incident": False, "hazard_detected": True,  "pedestrian_detected": False, "confidence": 0.84},
        ]
        i = 0
        while self._running:
            scenario = dict(scenarios[i % len(scenarios)])
            
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "MOCK DATA MODE", (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            cv2.putText(frame, f"State: {scenario['traffic_state']}", (150, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 0), 2)
            ret_enc, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            jpg_bytes = buffer.tobytes() if ret_enc else None

            with self._lock:
                self.latest = scenario
                self.latest_frame_jpg = jpg_bytes
            
            self._push_to_backend(scenario)

            i += 1
            time.sleep(3)

    @staticmethod
    def _mock_result() -> dict:
        return {
            "traffic_state":            "clear",
            "lead_vehicle_status":      "none",
            "lead_vehicle_distance":    "far",
            "stopped_vehicle_detected": False,
            "possible_incident":        False,
            "hazard_detected":          False,
            "pedestrian_detected":      False,
            "confidence":               0.85,
        }


# ── FastAPI ───────────────────────────────────────────────────────────────────
try:
    from fastapi import FastAPI, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse

    app = FastAPI(title="Eco-Copilot CV Pipeline (Pi)")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    _pipeline: Optional[CVPipeline] = None

    # Global config
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

    @app.post("/vision/source")
    def set_source(path: str = Query(...)):
        global _pipeline
        if _pipeline:
            _pipeline.stop()
        src = 0 if path == "0" else path
        _pipeline = CVPipeline(source=src)
        _pipeline.start()
        return {"status": "ok", "source": path}

    def generate_frames():
        while True:
            if _pipeline and _pipeline.latest_frame_jpg:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + _pipeline.latest_frame_jpg + b'\r\n')
            else:
                time.sleep(0.1)
            time.sleep(0.05)

    @app.get("/video_feed")
    def video_feed():
        return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

except ImportError:
    print("[cv_pipeline] FastAPI not available.")
    app = None


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import uvicorn
    
    source_arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "mock"
    push_enabled = "--no-push" not in sys.argv
    use_mock = source_arg == "mock"
    src = 0 if source_arg == "0" else source_arg

    print(f"[cv_pipeline] Starting with source={source_arg}, push_enabled={push_enabled}")
    print(f"[cv_pipeline] Backend URL: {BACKEND_URL}")
    print("[cv_pipeline] Starting API on http://0.0.0.0:8001")
    print("[cv_pipeline] Video feed available at http://localhost:8001/video_feed")

    GLOBAL_SOURCE = src
    GLOBAL_USE_MOCK = use_mock
    GLOBAL_PUSH_ENABLED = push_enabled

    if app:
        uvicorn.run(app, host="0.0.0.0", port=8001)
    else:
        print("[cv_pipeline] FastAPI not installed. Cannot stream video or expose API.")
        pipeline = CVPipeline(source=src, use_mock=use_mock, push_enabled=push_enabled)
        pipeline.start()
        try:
            print("[cv_pipeline] Running in CLI mode only... Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            pipeline.stop()