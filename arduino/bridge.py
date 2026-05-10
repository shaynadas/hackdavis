"""
arduino/bridge.py — Backseat Driver Arduino Bridge

Polls GET /recommendation/live from the backend every second and
sends a compact JSON line to the Arduino over USB serial.

Usage:
    python bridge.py                    # auto-detects Arduino port
    python bridge.py --port /dev/cu.usbmodem1401
    python bridge.py --port COM3        # Windows
    python bridge.py --backend http://10.0.0.99:8000

JSON sent to Arduino:
    {"opt_spd": 38.5, "opt_rpm": 2450, "cur_spd": 42.1, "action": "coast", "eco": 85,
     "lat": 38.5449, "lon": -121.7405}
    opt_spd / cur_spd are in mph (already converted by the backend).
"""

import argparse
import json
import sys
import time

try:
    import requests
except ImportError:
    print("[bridge] ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[bridge] ERROR: 'pyserial' not installed. Run: pip install pyserial")
    sys.exit(1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_arduino_port() -> str | None:
    """Try to auto-detect the Arduino UNO R4 serial port."""
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = (p.description or "").lower()
        hw   = (p.hwid or "").lower()
        if "arduino" in desc or "uno" in desc or "2341" in hw:
            return p.device
    # Fallback: return first non-bluetooth port
    for p in ports:
        if "bluetooth" not in (p.description or "").lower():
            return p.device
    return None


def extract_payload(rec: dict) -> dict:
    """Pull the fields the display needs from a /recommendation/live response."""
    summary = rec.get("summary", {})
    advice  = rec.get("advice", {})

    opt_spd = summary.get("optimal_speed_now_mph", 0.0)
    cur_spd = summary.get("current_speed_mph", 0.0)
    opt_rpm = summary.get("estimated_rpm_at_optimal_speed", 0.0)
    eco     = int(summary.get("eco_score", 0))
    action  = summary.get("recommended_action", "maintain").replace("_", " ")

    # Location — pulled from context_used if present
    ctx = rec.get("context_used", {})
    lat = rec.get("lat") or ctx.get("lat") or 0.0
    lon = rec.get("lon") or ctx.get("lon") or 0.0

    payload = {
        "opt_spd": round(float(opt_spd), 1),
        "opt_rpm": int(float(opt_rpm)),
        "cur_spd": round(float(cur_spd), 1),
        "action":  action[:10],   # keep it short for display
        "eco":     eco,
    }
    if lat and lon:
        payload["lat"] = round(float(lat), 6)
        payload["lon"] = round(float(lon), 6)
    return payload


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backseat Driver Arduino Bridge")
    parser.add_argument("--port",    default=None,                   help="Serial port (e.g. /dev/cu.usbmodem1401 or COM3)")
    parser.add_argument("--baud",    default=115200, type=int,       help="Baud rate (default: 115200)")
    parser.add_argument("--backend", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--interval", default=1.0, type=float,       help="Poll interval in seconds (default: 1.0)")
    args = parser.parse_args()

    # Resolve port
    port = args.port or find_arduino_port()
    if not port:
        print("[bridge] ERROR: No Arduino found. Specify --port manually.")
        sys.exit(1)
    print(f"[bridge] Using port: {port} @ {args.baud} baud")

    # Open serial
    try:
        ser = serial.Serial(port, args.baud, timeout=1)
        time.sleep(2)   # Give Arduino time to reset after connection
        print(f"[bridge] Serial connected.")
    except serial.SerialException as e:
        print(f"[bridge] ERROR opening serial port: {e}")
        sys.exit(1)

    url = f"{args.backend}/recommendation/live"
    print(f"[bridge] Polling {url} every {args.interval}s")
    print("[bridge] Running — press Ctrl+C to stop.\n")

    consecutive_errors = 0

    while True:
        try:
            resp = requests.get(url, timeout=2.0)
            if resp.status_code == 200:
                rec     = resp.json()
                payload = extract_payload(rec)
                line    = json.dumps(payload) + "\n"
                ser.write(line.encode("utf-8"))
                print(f"[bridge] → {line.strip()}")
                consecutive_errors = 0
            else:
                print(f"[bridge] Backend returned {resp.status_code}")
                consecutive_errors += 1

        except requests.exceptions.ConnectionError:
            print(f"[bridge] Backend unreachable ({args.backend})")
            consecutive_errors += 1
        except requests.exceptions.Timeout:
            print("[bridge] Request timed out")
            consecutive_errors += 1
        except serial.SerialException as e:
            print(f"[bridge] Serial error: {e}")
            break

        if consecutive_errors >= 5:
            # Send a marker so the display knows data is stale
            print("[bridge] 5 consecutive errors — display will timeout.")

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[bridge] Stopped.")
