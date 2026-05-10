import { useState, useEffect, useRef } from 'react';
import { API_BASE } from '../api';

// Each frame in drive_timeline.json
export interface SimFrame {
  t: number;
  road: string;
  location: {
    lat: number;
    lon: number;
    speed_mph: number;
    heading_deg: number;
    accuracy_m: number;
  };
  perception: {
    traffic_state: string;
    lead_vehicle_status: string;
    lead_vehicle_distance: string;
    lead_vehicle_distance_m: number;
    stopped_vehicle_detected: boolean;
    hazard_detected: boolean;
    pedestrian_detected: boolean;
    cyclist_detected: boolean;
    possible_incident: boolean;
    confidence: number;
  };
  road_context: {
    speed_limit_mph: number;
    traffic_speed_mph: number | null;
    congestion_level: string;
    road_grade_percent: number;
    upcoming_stop_distance_m: number | null;
    incident_ahead: boolean;
  };
}

export interface SimTimeline {
  meta: {
    city: string;
    duration_s: number;
    frame_rate_hz: number;
    frame_count: number;
    total_distance_m: number;
    total_distance_mi: number;
    waypoints: Array<{
      name: string;
      lat: number;
      lon: number;
      speed_limit_mph: number;
      road: string;
    }>;
    vehicle_profile: any;
  };
  frames: SimFrame[];
}

const PERCEPTION_KEYS: Array<keyof SimFrame['perception']> = [
  'traffic_state',
  'lead_vehicle_status',
  'lead_vehicle_distance',
  'stopped_vehicle_detected',
  'hazard_detected',
  'pedestrian_detected',
  'cyclist_detected',
  'possible_incident',
  'confidence',
];

function perceptionForBackend(p: SimFrame['perception']) {
  const out: Record<string, any> = {};
  PERCEPTION_KEYS.forEach((k) => {
    out[k as string] = p[k];
  });
  return out;
}

interface SimulatorOptions {
  active: boolean;
  speedMul?: number; // 1 = real time, 2 = 2x, etc.
  loop?: boolean;
  onFrame?: (frame: SimFrame, idx: number) => void;
  onEnd?: () => void;
}

/**
 * Loads /drive_timeline.json and, while `active` is true, walks through it
 * frame-by-frame. Each frame is POSTed to the backend's three update endpoints
 * (/location/update, /perception/update, /road-context/update) so the rest of
 * the dashboard reacts as if a real phone were streaming GPS.
 */
export function useSimulator({
  active,
  speedMul = 1,
  loop = false,
  onFrame,
  onEnd,
}: SimulatorOptions) {
  const [timeline, setTimeline] = useState<SimTimeline | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [frameIdx, setFrameIdx] = useState(0);
  const [running, setRunning] = useState(false);

  const rafRef = useRef<number | null>(null);
  const startWallRef = useRef<number>(0);
  const idxFloatRef = useRef<number>(0);

  // Lazy-load the timeline once
  useEffect(() => {
    let cancelled = false;
    fetch('/drive_timeline.json', { cache: 'no-store' })
      .then((r) => {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then((data: SimTimeline) => {
        if (!cancelled) setTimeline(data);
      })
      .catch((e) => {
        if (!cancelled) {
          setLoadError(
            'Could not load /drive_timeline.json. Generate it with `python3 simulator/generate_drive.py` and copy it to backseat-driver/public/.'
          );
          // eslint-disable-next-line no-console
          console.error('useSimulator: timeline load failed', e);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Drive the playback loop and POST each frame to the backend
  useEffect(() => {
    if (!active || !timeline) {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      setRunning(false);
      return;
    }

    setRunning(true);
    startWallRef.current = performance.now();
    idxFloatRef.current = 0;
    setFrameIdx(0);

    let lastPostedIdx = -1;

    let hasLoggedError = false;
    const postFrame = async (frame: SimFrame) => {
      try {
        const responses = await Promise.all([
          fetch(`${API_BASE}/location/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(frame.location),
          }),
          fetch(`${API_BASE}/perception/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(perceptionForBackend(frame.perception)),
          }),
          fetch(`${API_BASE}/road-context/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(frame.road_context),
          }),
        ]);

        // Check if all responses are OK
        const allOk = responses.every(r => r.ok);
        if (!allOk && !hasLoggedError) {
          console.warn('useSimulator: One or more POST requests failed', responses.map(r => r.status));
          hasLoggedError = true;
        }
      } catch (e) {
        // Backend may not be running — we still want the visual to play.
        if (!hasLoggedError) {
          console.warn('useSimulator: Failed to POST frame to backend', e);
          hasLoggedError = true;
        }
      }
    };

    const tick = (now: number) => {
      const elapsedS = ((now - startWallRef.current) / 1000) * speedMul;
      idxFloatRef.current = elapsedS;
      let i = Math.floor(elapsedS);
      if (i >= timeline.frames.length) {
        if (loop) {
          startWallRef.current = now;
          idxFloatRef.current = 0;
          i = 0;
          lastPostedIdx = -1;
        } else {
          setRunning(false);
          if (onEnd) onEnd();
          return;
        }
      }
      if (i !== frameIdx) setFrameIdx(i);
      const frame = timeline.frames[i];
      if (onFrame) onFrame(frame, i);
      if (i !== lastPostedIdx) {
        lastPostedIdx = i;
        // Fire and forget — don't block the animation loop on the network.
        postFrame(frame);
      }
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, timeline, speedMul, loop]);

  const currentFrame: SimFrame | null =
    timeline && timeline.frames[frameIdx] ? timeline.frames[frameIdx] : null;

  return {
    timeline,
    loadError,
    running,
    frameIdx,
    currentFrame,
  };
}
