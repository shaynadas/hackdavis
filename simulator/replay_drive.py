"""
replay_drive.py
===============
Replays drive_timeline.json against the running FastAPI backend at 1 Hz so the
React dashboard sees a "live" car driving through downtown Davis. Each frame
fans out to:

    POST /location/update
    POST /perception/update
    POST /road-context/update

A vehicle profile is primed once at startup. Optionally polls
GET /recommendation/live every N seconds and prints the optimizer's response.

Usage:
    python3 replay_drive.py
    python3 replay_drive.py --base http://localhost:8000
    python3 replay_drive.py --speed 2          # play 2x faster
    python3 replay_drive.py --loop             # repeat forever
    python3 replay_drive.py --no-rec           # skip /recommendation/live polling
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict
from urllib import request, error

HERE = os.path.dirname(os.path.abspath(__file__))
TIMELINE_PATH = os.path.join(HERE, "drive_timeline.json")


# ---------------------------------------------------------------------------
# Tiny stdlib HTTP wrapper (no requests dep so this runs anywhere Python runs)
# ---------------------------------------------------------------------------

def http_post(url: str, payload: Dict[str, Any], timeout: float = 3.0) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return {"ok": True, "status": resp.status, "body": data}
    except error.HTTPError as e:
        return {"ok": False, "status": e.code, "body": e.read().decode("utf-8", "replace")}
    except (error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "status": 0, "body": str(e)}


def http_get(url: str, timeout: float = 3.0) -> Dict[str, Any]:
    try:
        with request.urlopen(url, timeout=timeout) as resp:
            return {"ok": True, "status": resp.status, "body": resp.read().decode("utf-8")}
    except error.HTTPError as e:
        return {"ok": False, "status": e.code, "body": e.read().decode("utf-8", "replace")}
    except (error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "status": 0, "body": str(e)}


# ---------------------------------------------------------------------------
# Frame -> backend payload helpers. Strip the extra numeric lead-distance
# field that the backend's PerceptionInput model rejects.
# ---------------------------------------------------------------------------

PERCEPTION_KEYS = {
    "traffic_state",
    "lead_vehicle_status",
    "lead_vehicle_distance",
    "stopped_vehicle_detected",
    "hazard_detected",
    "pedestrian_detected",
    "cyclist_detected",
    "possible_incident",
    "confidence",
}


def perception_for_backend(p: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in p.items() if k in PERCEPTION_KEYS}


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def play(base: str, speed: float, loop: bool, poll_rec: bool, rec_every: int):
    if not os.path.exists(TIMELINE_PATH):
        print(f"[!] {TIMELINE_PATH} not found. Run generate_drive.py first.", file=sys.stderr)
        sys.exit(1)

    with open(TIMELINE_PATH) as f:
        timeline = json.load(f)

    frames = timeline["frames"]
    vp = timeline["meta"]["vehicle_profile"]

    # Health check
    h = http_get(f"{base}/health", timeout=2.0)
    if not h["ok"]:
        print(f"[!] Backend not reachable at {base}/health: {h['body']}", file=sys.stderr)
        sys.exit(2)
    print(f"[+] Backend healthy at {base}")

    # Prime vehicle profile by running a dummy /recommendation request so the
    # optimizer has a known car. The backend doesn't expose a vehicle setter,
    # but get_recommendation accepts a vehicle_profile inline — for a "live"
    # stream we just rely on /recommendation/live falling back to the demo
    # vehicle, which already matches our timeline. We log it for clarity.
    print(f"[+] Vehicle in timeline: {vp.get('year')} {vp.get('make')} {vp.get('model')} "
          f"({vp.get('trim')})")

    print(f"[+] {len(frames)} frames, replay speed {speed}x, "
          f"polling /recommendation/live every {rec_every}s = {poll_rec}")

    iteration = 0
    while True:
        iteration += 1
        if loop:
            print(f"\n=== Loop {iteration} ===")
        t0 = time.time()
        for i, frame in enumerate(frames):
            target = t0 + (frame["t"] / speed)
            now = time.time()
            if target > now:
                time.sleep(target - now)

            loc_resp = http_post(f"{base}/location/update", frame["location"])
            perc_resp = http_post(
                f"{base}/perception/update", perception_for_backend(frame["perception"])
            )
            ctx_resp = http_post(f"{base}/road-context/update", frame["road_context"])

            ok_marks = "".join(
                "." if r["ok"] else "x" for r in (loc_resp, perc_resp, ctx_resp)
            )

            extras = ""
            if poll_rec and i % rec_every == 0:
                rec = http_get(f"{base}/recommendation/live", timeout=2.0)
                if rec["ok"]:
                    try:
                        rec_json = json.loads(rec["body"])
                        s = rec_json.get("summary", {})
                        a = rec_json.get("advice", {})
                        extras = (
                            f"  -> opt {s.get('optimal_speed_now_mph')} mph "
                            f"@ gear {s.get('recommended_gear')} "
                            f"({s.get('estimated_rpm_at_optimal_speed')} rpm)  "
                            f"[{s.get('safety_level')}]  "
                            f"{a.get('voice_line','')[:60]}"
                        )
                    except Exception:
                        extras = "  -> (rec parse error)"
                else:
                    extras = f"  -> rec error {rec['status']}"

            print(
                f"t={frame['t']:>3}s {ok_marks} "
                f"{frame['location']['speed_mph']:>5.1f} mph "
                f"hdg {frame['location']['heading_deg']:>5.1f}  "
                f"lead {frame['perception']['lead_vehicle_status']:<8} "
                f"{frame['perception']['lead_vehicle_distance_m']:>5.1f} m  "
                f"limit {int(frame['road_context']['speed_limit_mph']):>2}  "
                f"grd {frame['road_context']['road_grade_percent']:>4.1f}%  "
                f"cong {frame['road_context']['congestion_level']:<8}"
                f"{extras}"
            )
        if not loop:
            break
    print("[+] Replay complete.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000",
                    help="Backend base URL (default: http://localhost:8000)")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="Playback speed multiplier (default 1.0 = real time)")
    ap.add_argument("--loop", action="store_true", help="Loop forever")
    ap.add_argument("--no-rec", action="store_true",
                    help="Don't poll /recommendation/live")
    ap.add_argument("--rec-every", type=int, default=2,
                    help="Poll /recommendation/live every N frames (default 2)")
    args = ap.parse_args()

    play(
        base=args.base.rstrip("/"),
        speed=args.speed,
        loop=args.loop,
        poll_rec=not args.no_rec,
        rec_every=max(1, args.rec_every),
    )


if __name__ == "__main__":
    main()
