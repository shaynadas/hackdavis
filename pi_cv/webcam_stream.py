"""
webcam_stream.py — view the Pi's webcam in your laptop browser

Run on the Pi:
    python webcam_stream.py            # uses /dev/video0
    python webcam_stream.py 1          # uses /dev/video1
    python webcam_stream.py 0 --port 8080

The Pi prints its IP. Open that URL in any browser on your laptop or
phone (same Wi-Fi). You'll see the live camera feed with an FPS overlay.
No display, no X forwarding, no extra installs needed.

Press Ctrl+C to stop.
"""

import cv2
import sys
import time
import threading
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ── parse args ────────────────────────────────────────────────────────────────
CAM_INDEX = 0
PORT = 8080
W, H = 640, 480

args = sys.argv[1:]
i = 0
while i < len(args):
    a = args[i]
    if a.isdigit():
        CAM_INDEX = int(a)
    elif a == '--port' and i + 1 < len(args):
        PORT = int(args[i+1]); i += 1
    elif a == '--size' and i + 1 < len(args):
        W, H = map(int, args[i+1].split('x')); i += 1
    i += 1


# ── camera ────────────────────────────────────────────────────────────────────
cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not cap.isOpened():
    print(f'[stream] ERROR: cannot open /dev/video{CAM_INDEX}')
    print(f'[stream] try: python probe_camera.py to find the right index')
    sys.exit(1)


# ── background grabber, encodes JPEG once per frame ───────────────────────────
state = {'jpeg': None, 'fps': 0.0}
lock = threading.Lock()

def grabber():
    fps_t, fps_n, fps = time.time(), 0, 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.01); continue

        fps_n += 1
        now = time.time()
        if now - fps_t >= 1.0:
            fps = fps_n / (now - fps_t)
            fps_n, fps_t = 0, now

        cv2.putText(frame, f'/dev/video{CAM_INDEX}  {fps:.1f} FPS',
                    (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            with lock:
                state['jpeg'] = jpg.tobytes()
                state['fps']  = fps

threading.Thread(target=grabber, daemon=True).start()


# ── HTTP server ───────────────────────────────────────────────────────────────
INDEX_HTML = b'''<!doctype html>
<html><head><meta charset="utf-8"><title>Pi cam</title>
<style>
  body{margin:0;background:#111;color:#eee;font-family:system-ui,sans-serif;text-align:center}
  img{max-width:100vw;max-height:92vh;display:block;margin:0 auto}
  h2{margin:10px;font-weight:400}
</style></head>
<body><h2>Pi webcam (/dev/video%d)</h2>
<img src="/stream" alt="Live feed">
</body></html>''' % CAM_INDEX


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass  # quiet

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(INDEX_HTML)))
            self.end_headers()
            self.wfile.write(INDEX_HTML)
            return

        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Age', '0')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type',
                             'multipart/x-mixed-replace; boundary=--frame')
            self.end_headers()
            try:
                while True:
                    with lock:
                        jpg = state['jpeg']
                    if jpg is None:
                        time.sleep(0.05); continue
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(f'Content-Length: {len(jpg)}\r\n\r\n'.encode())
                    self.wfile.write(jpg)
                    self.wfile.write(b'\r\n')
                    time.sleep(0.04)  # cap at ~25 FPS over the network
            except (BrokenPipeError, ConnectionResetError):
                return
            return

        self.send_error(404)


def my_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


if __name__ == '__main__':
    ip = my_ip()
    print(f'[stream] camera /dev/video{CAM_INDEX} at {W}x{H} MJPG')
    print(f'[stream] open in browser:  http://{ip}:{PORT}')
    print(f'[stream] also reachable:   http://localhost:{PORT}  (on the Pi)')
    print(f'[stream] Ctrl+C to stop')
    try:
        ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print('\n[stream] stopped')
        cap.release()
