# Backseat Driver — 2-min Drive Simulator

This folder lets you feed the eco-driving optimizer a continuous, realistic
2-minute drive through downtown Davis, CA — without needing a phone, a real
GPS lock, or a webcam. It produces every input the program asks for:

| Input the optimizer wants                | Where it comes from in the timeline |
| ---------------------------------------- | ----------------------------------- |
| GPS lat, lon, speed, heading, accuracy   | `frame.location`                    |
| Lead-vehicle status + distance           | `frame.perception`                  |
| Pedestrian / hazard / stopped vehicle    | `frame.perception`                  |
| Speed limit + traffic speed + congestion | `frame.road_context`                |
| Road grade %                             | `frame.road_context`                |
| Upcoming stop distance + incident ahead  | `frame.road_context`                |
| Vehicle profile (gears, mass, tires)     | `meta.vehicle_profile`              |

There are three ways to use it:

1. **Standalone HTML map** — `drive_map.html`, opens locally, plays the drive
   on real OpenStreetMap tiles with a tactical overlay. No backend required.
2. **Live replay** — `replay_drive.py` POSTs each frame to the running FastAPI
   backend so the React dashboard shows the drive as if it were real.
3. **Inside the dashboard** — the React app's *Seed Demo Location* button
   reads `drive_timeline.json` and runs the same simulation directly inside
   the dashboard, including the new big tactical pip view that only appears
   after you click that button.

---

## 1. Generate the timeline

```bash
cd hackdavis/simulator
python3 generate_drive.py
```

That writes **`drive_timeline.json`** here, with 121 one-second frames
covering ~0.95 mi through downtown Davis:

```
3rd & B  →  3rd & D (stop sign / lead car braking)  →  3rd & F
        →  F & 1st (slight grade, moderate traffic)
        →  pedestrian event
        →  1st & B  (arrival)
```

The timeline already includes a 2018 Audi A4 vehicle profile in
`meta.vehicle_profile` that matches the backend's demo car.

> The React dashboard expects the JSON at `backseat-driver/public/drive_timeline.json`.
> Copy it once after generation:
> ```bash
> cp drive_timeline.json ../backseat-driver/public/drive_timeline.json
> ```

## 2. Open the standalone map

Serve this folder over HTTP (browsers won't `fetch()` from `file://`):

```bash
cd hackdavis/simulator
python3 -m http.server 8080
# then open http://localhost:8080/drive_map.html
```

You'll see:

* **Top-left:** OpenStreetMap of Davis with the route as a cyan polyline,
  driven trail in yellow, waypoint pins, and the car as a blue pip.
* **Right sidebar:** current speed, optimal speed, RPM at current/target
  gear, eco score, lead-vehicle distance bar, road context, perception
  flags, voice line, safety badge.

Add `?live=1` to also poll the running backend's `/recommendation/live` and
overlay the optimizer's actual response:

```
http://localhost:8080/drive_map.html?live=1
```

## 3. Replay against the running backend

Start the backend (and the React dashboard) the normal way:

```bash
cd hackdavis/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# in another shell
cd hackdavis/backseat-driver && npm run dev
```

Then in a third shell:

```bash
cd hackdavis/simulator
python3 replay_drive.py                  # 1× real time, polls /recommendation/live
python3 replay_drive.py --speed 4         # 4× faster
python3 replay_drive.py --loop            # loop forever for demos
python3 replay_drive.py --no-rec          # don't poll the optimizer
python3 replay_drive.py --base http://192.168.1.42:8000   # remote backend (Pi)
```

Each second the script POSTs:

* `POST /location/update`     — the GPS frame
* `POST /perception/update`   — the CV/perception summary
* `POST /road-context/update` — speed limit, traffic, grade, etc.

…and every two frames it `GET`s `/recommendation/live` and prints the
optimizer's reply inline.

## 4. Inside the React dashboard (Seed Demo Location)

If you'd rather drive the simulator from the dashboard itself:

1. Make sure `backseat-driver/public/drive_timeline.json` exists (see step 1).
2. Boot backend + frontend.
3. In the dashboard, click **Seed Demo Location** in the Location panel.
   * The button turns blue and reads *Stop Simulated Drive*.
   * A new full-width **Simulated Drive** panel appears below the main grid.
4. The simulator hook posts the same three endpoints once per second, so
   every other panel (recommendation, charts, speed, RPM, voice line) reacts
   live as if a phone were streaming GPS through Davis.

The new panel has two halves:

* **Left:** small route overview (the same SVG as `RouteOverview` — full path
  in cyan, driven trail in yellow, our car as a pulsing blue pip).
* **Right:** a much bigger zoomed-in tactical pip view (~60 m radius), with:
  * **Blue pip** — our simulated car (always in the bottom center)
  * **Grey rectangles** — other vehicles (lead car ahead, ambient traffic).
    The lead car's distance comes straight from
    `perception.lead_vehicle_distance_m`.
  * **Red dots** — pedestrians and hazards
  * **Red triangle** — incident ahead
  * Range rings at 10 / 30 / 50 m
  * Heading indicator
  * A live readout strip showing every input being fed to the optimizer

---

## Files

| File                     | Purpose                                                |
| ------------------------ | ------------------------------------------------------ |
| `generate_drive.py`      | Builds the timeline JSON from the route + speed plan.  |
| `drive_timeline.json`    | The generated 121-frame, 2-minute drive.               |
| `replay_drive.py`        | Replays the timeline against the FastAPI backend.      |
| `drive_map.html`         | Self-contained Leaflet visualization of the drive.     |
| `README.md`              | This file.                                             |

The timeline schema is documented inside `generate_drive.py` and mirrors
`backend/models.py` (`LocationInput`, `PerceptionInput`, `RoadContextInput`).

---

## Tweaking the drive

Open `generate_drive.py`:

* **Route:** edit `WAYPOINTS` (each entry is a real Davis intersection).
  Add or remove vertices and the integrator handles the rest.
* **Speed profile:** edit `build_speed_profile()` — there are clearly named
  phases (launch, cruise, braking, stop, accelerate, turn, grade, ped event,
  arrival). Each phase sets `profile[t]` for a slice of seconds.
* **Events:** `perception_for(t, frame)` and `road_context_for(t, frame)`
  control when lead vehicles brake, when pedestrians appear, when traffic
  congests, when the stop sign approaches, etc. They're plain `if`s on `t`.
* **Vehicle:** edit `VEHICLE_PROFILE` to match a different car.

Re-run `python3 generate_drive.py` after any change.
