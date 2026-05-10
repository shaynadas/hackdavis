"""
cv_view.py — see what the CV pipeline is detecting, live in your browser

Wraps the CVPipeline from cv_pipeline_pi.py and serves:
    /           HTML page with live video + perception state panel
    /stream     MJPEG multipart stream of the annotated YOLO output
    /vision     JSON of the current perception state

Run on the Pi (cv_pipeline_pi.py must be in the same folder):
    python cv_view.py            # /dev/video0, port 8080
    python cv_view.py 1          # /dev/video1
    python cv_view.py 0 --port 8090
    python cv_view.py mock       # no camera, mock perception cycling
    python cv_view.py 0 --no-push  # don't push to backend

Then open http://<pi-ip>:8080 on your laptop or phone (same Wi-Fi).
The page shows: live YOLO boxes on the video, plus a panel that
auto-updates with traffic state, lead vehicle, hazard flags, etc.
"""

import sys
import time
import socket
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from cv_pipeline_pi import CVPipeline


# ── parse args ────────────────────────────────────────────────────────────────
source = "0"
PORT = 8080
push_enabled = True

args = sys.argv[1:]
i = 0
while i < len(args):
    a = args[i]
    if a == '--port' and i + 1 < len(args):
        PORT = int(args[i+1]); i += 1
    elif a == '--no-push':
        push_enabled = False
    elif not a.startswith('--'):
        source = a
    i += 1

use_mock = source == "mock"
src = int(source) if source.isdigit() else source


# ── start the pipeline (draw=True so frames have YOLO overlay) ────────────────
pipeline = CVPipeline(
    source=src,
    use_mock=use_mock,
    push_enabled=push_enabled,
    draw=True,
)
pipeline.start()


# ── HTML page (live video + auto-updating state panel) ────────────────────────
INDEX_HTML = b'''<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eco-drive CV</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;background:#0a0a0a;color:#eee;
       font-family:system-ui,-apple-system,sans-serif}
  .wrap{max-width:900px;margin:0 auto;padding:14px;
        display:flex;flex-direction:column;align-items:center}
  h1{font-size:18px;font-weight:500;margin:6px 0}
  img{max-width:100%;border-radius:8px;background:#000}
  .panel{width:100%;display:grid;grid-template-columns:repeat(2,1fr);
         gap:6px 18px;margin-top:14px;padding:14px;
         background:#161616;border-radius:8px;font-size:14px}
  .label{color:#888}
  .value{font-weight:500}
  .alert{color:#ff5757}
  .meta{color:#666;font-size:12px;margin-top:8px}
</style></head>
<body><div class="wrap">
  <h1>Eco-drive CV pipeline</h1>
  <img src="/stream" alt="Live YOLO output">
  <div class="panel">
    <div class="label">Traffic state</div>     <div id="state" class="value">-</div>
    <div class="label">Lead vehicle</div>      <div id="lead" class="value">-</div>
    <div class="label">Lead distance</div>     <div id="dist" class="value">-</div>
    <div class="label">Stopped vehicle</div>   <div id="stopped" class="value">-</div>
    <div class="label">Hazard</div>            <div id="hazard" class="value">-</div>
    <div class="label">Pedestrian</div>        <div id="ped" class="value">-</div>
    <div class="label">Possible incident</div> <div id="incident" class="value">-</div>
    <div class="label">Confidence</div>        <div id="conf" class="value">-</div>
  </div>
  <div class="meta" id="meta">polling /vision...</div>
</div>
<script>
function flag(id, on) {
  const el = document.getElementById(id);
  el.textContent = on ? 'YES' : 'no';
  el.className = 'value ' + (on ? 'alert' : '');
}
async function poll() {
  try {
    const r = await fetch('/vision');
    const j = await r.json();
    document.getElementById('state').textContent = j.traffic_state;
    document.getElementById('lead').textContent  = j.lead_vehicle_status;
    document.getElementById('dist').textContent  = j.lead_vehicle_distance;
    document.getElementById('conf').textContent  = j.confidence;
    flag('stopped',  j.stopped_vehicle_detected);
    flag('hazard',   j.hazard_detected);
    flag('ped',      j.pedestrian_detected);
    flag('incident', j.possible_incident);
    document.getElementById('meta').textContent = 'updated ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('meta').textContent = 'fetch failed: ' + e.message;
  }
  setTimeout(poll, 400);
}
poll();
</script>
</body></html>'''


# ── HTTP handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass  # quiet, no per-request log spam

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(INDEX_HTML)))
            self.end_headers()
            self.wfile.write(INDEX_HTML)
            return

        if self.path == '/vision':
            data = json.dumps(pipeline.get_result()).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
            return

        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type',
                             'multipart/x-mixed-replace; boundary=--frame')
            self.end_headers()
            try:
                while True:
                    frame = pipeline.get_frame()
                    if frame is None:
                        time.sleep(0.05); continue
                    ok, jpg = cv2.imencode('.jpg', frame,
                                            [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if not ok:
                        time.sleep(0.05); continue
                    body = jpg.tobytes()
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(f'Content-Length: {len(body)}\r\n\r\n'.encode())
                    self.wfile.write(body)
                    self.wfile.write(b'\r\n')
                    time.sleep(0.05)  # cap network rate around 20 FPS
            except (BrokenPipeError, ConnectionResetError):
                return
            return

        self.send_error(404)


# ── helpers ───────────────────────────────────────────────────────────────────
def my_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


# ── go ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    ip = my_ip()
    print(f'[cv_view] source={source}  mock={use_mock}  push={push_enabled}')
    print(f'[cv_view] open in browser:  http://{ip}:{PORT}')
    print(f'[cv_view] also on the Pi:   http://localhost:{PORT}')
    print(f'[cv_view] Ctrl+C to stop')
    try:
        ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print('\n[cv_view] stopping...')
        pipeline.stop()
        time.sleep(0.3)
        print('[cv_view] stopped')
