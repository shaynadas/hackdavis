# Eco-drive CV pipeline (Raspberry Pi 4B)

Real-time car and pedestrian detection running on a Pi 4B with a USB webcam.
Uses YOLOv8n via NCNN, a centroid tracker, and a traffic-state classifier.
Pushes perception JSON to a backend over HTTP and streams the annotated
video to your laptop's browser.

## Files

| File | Role |
|---|---|
| `cv_pipeline_pi.py` | Core pipeline: camera capture, YOLO inference, tracking, classification, backend push |
| `cv_view.py` | Browser view: live YOLO output + state panel at `http://<pi-ip>:8080` |
| `probe_camera.py` | Diagnostic: lists `/dev/video*` devices, probes formats, saves snapshots |
| `webcam_stream.py` | Debug tool: raw webcam stream (no CV), useful when the pipeline is misbehaving |
| `export_ncnn.py` | One-time helper: converts YOLOv8n to NCNN format |
| `setup.sh` | One-shot installer: apt packages, venv, pip, NCNN export |
| `requirements.txt` | Python dependencies |

## First-time setup

On the Pi (Raspberry Pi OS 64-bit assumed):

```bash
chmod +x setup.sh
./setup.sh
```

Takes about 20 minutes total. Most of that is PyTorch installing and the
NCNN export running. After it finishes, **log out and back in** so the
`video` group membership applies.

## Run

Always activate the venv first:

```bash
source venv/bin/activate
```

### 1. Find your webcam

```bash
python probe_camera.py
```

Prints every `/dev/video*` device, tries to capture from each, and saves
JPEG snapshots to `./snapshots/`. The recommended index is printed at the
end. SSH-friendly, no display needed.

### 2. See live detection in your browser

```bash
python cv_view.py <index>
```

Open the URL it prints (e.g. `http://192.168.1.47:8080`) on your laptop or
phone. You'll see:
- Live video with bounding boxes (green = moving, red = stopped, orange = pedestrian)
- Track IDs and pixel-speed on each box
- Auto-updating state panel: traffic state, lead vehicle, hazards, confidence

### 3. Run headless for the full system

```bash
python cv_pipeline_pi.py <index> --no-window
```

Pipeline runs, pushes perception to the backend, no preview. This is
the production mode for the actual driving demo.

## Other modes

```bash
# Local OpenCV preview window (needs a monitor on the Pi)
python cv_pipeline_pi.py 0

# Mock perception, no camera (good for testing the backend)
python cv_pipeline_pi.py mock
python cv_view.py mock

# Don't push to backend
python cv_pipeline_pi.py 0 --no-push

# Raw webcam stream, no CV (debugging the camera)
python webcam_stream.py 0
```

## Backend integration

The pipeline POSTs JSON to `http://localhost:8000/perception/update`
every 500 ms. Edit `BACKEND_URL` at the top of `cv_pipeline_pi.py` if your
backend lives elsewhere.

JSON schema:

```json
{
  "traffic_state": "clear|moderate|slowing|stopped",
  "lead_vehicle_status": "none|moving|braking|stopped",
  "lead_vehicle_distance": "far|medium|close",
  "stopped_vehicle_detected": false,
  "possible_incident": false,
  "hazard_detected": false,
  "pedestrian_detected": false,
  "confidence": 0.85
}
```

## Performance expectations on Pi 4B (4 GB)

| Setting | FPS |
|---|---|
| YOLOv8n NCNN, imgsz=320 | 5-7 |
| YOLOv8n NCNN, imgsz=256 | 7-10 |
| YOLOv8n PyTorch, imgsz=320 | 1.5-2 (do not use this in production) |
| YOLOv8n PyTorch, imgsz=640 | <1 |

If you're seeing the bottom rows, the NCNN export didn't take effect.
Look for `Loading NCNN model from yolov8n_ncnn_model/` in the startup log.

## Troubleshooting

**`ModuleNotFoundError`**: forgot to activate the venv. `source venv/bin/activate`.

**`Cannot open /dev/video0`**: not in the `video` group. `groups` should
list it. If not, log out and back in (or reboot). Or your webcam is at a
different index, run `probe_camera.py`.

**Pipeline starts but stream is blank for 5+ seconds**: model warmup. The
first inference call always lags. Wait, then refresh the browser.

**FPS is in the basement**: check `vcgencmd get_throttled`. Not `0x0` means
the Pi is throttling from heat or undervoltage. Add a fan, use a 3 A power
supply.

**Webcam disconnects randomly**: USB underpower. Use a powered USB hub, or
upgrade to a 3 A supply.

**Webcam was index 0, now it's 1**: udev re-enumerates on plug order. Run
`probe_camera.py` again to confirm. If this keeps biting, switch to
`/dev/v4l/by-id/...` paths in `cv_pipeline_pi.py`.
# tester_hack_davis
