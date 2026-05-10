import { useMemo } from 'react';
import { Radar, Square, AlertTriangle, Footprints, Car as CarIcon } from 'lucide-react';
import type { SimFrame, SimTimeline } from '../hooks/useSimulator';

interface SimulatedDriveMapProps {
  timeline: SimTimeline | null;
  frame: SimFrame | null;
  frameIdx: number;
  running: boolean;
  loadError: string | null;
  onStop: () => void;
}

/**
 * Big tactical "pip" view that activates when the user clicks Seed Demo
 * Location. Two stacked sub-views:
 *
 *   LEFT  — overview map: full route over downtown Davis, with the car's
 *           current position drawn as a pulsing blue pip on a polyline.
 *   RIGHT — zoomed-in tactical: car-centered ~60 m radius. Our simulated
 *           car is a blue pip in the middle, lead/ambient vehicles are grey
 *           pips placed by perception data, and pedestrians/hazards are red.
 */
export function SimulatedDriveMap({
  timeline,
  frame,
  frameIdx,
  running,
  loadError,
  onStop,
}: SimulatedDriveMapProps) {
  if (loadError) {
    return (
      <div className="bg-zinc-900 border border-red-900/60 rounded-lg p-6 text-red-300 text-sm">
        <div className="font-semibold mb-1">Simulator data not available</div>
        <div className="text-red-300/80">{loadError}</div>
      </div>
    );
  }

  if (!timeline || !frame) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 text-zinc-400 text-sm flex items-center gap-3">
        <div className="animate-pulse w-2 h-2 rounded-full bg-blue-400" />
        Loading simulator timeline…
      </div>
    );
  }

  const total = timeline.frames.length - 1;
  const pct = Math.min(100, (frameIdx / total) * 100);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3 border-b border-zinc-800 pb-2">
        <h2 className="text-sm font-semibold text-zinc-300 flex items-center gap-2 uppercase tracking-wider">
          <Radar className="w-4 h-4 text-blue-400" />
          Simulated Drive — Davis, CA · {timeline.meta.total_distance_mi} mi · 2 min
          <span
            className={`ml-3 inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full ${
              running ? 'bg-green-900/40 text-green-300' : 'bg-zinc-800 text-zinc-400'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                running ? 'bg-green-400 animate-pulse' : 'bg-zinc-500'
              }`}
            />
            {running ? 'PLAYING' : 'PAUSED'}
          </span>
        </h2>
        <div className="flex items-center gap-3">
          <div className="text-[11px] text-zinc-500 font-mono">
            t = {frame.t}s / {total}s
          </div>
          <button
            onClick={onStop}
            className="bg-red-600/20 hover:bg-red-600/30 text-red-300 border border-red-900/50 px-3 py-1 rounded text-xs flex items-center gap-1.5"
          >
            <Square className="w-3 h-3 fill-current" /> Stop simulation
          </button>
        </div>
      </div>

      {/* progress bar */}
      <div className="h-1 bg-zinc-800 rounded mb-4 overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-[width] duration-200"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Overview route map (small left half) */}
        <div className="col-span-5">
          <RouteOverview timeline={timeline} frame={frame} />
          <div className="text-[10px] text-zinc-500 mt-1 leading-relaxed">
            Route: 3rd&nbsp;St → F&nbsp;St → 1st&nbsp;St. Cyan line is the planned path,
            yellow is what the car has driven so far.
          </div>
        </div>

        {/* Zoomed-in tactical pip view (bigger right half) */}
        <div className="col-span-7">
          <TacticalView frame={frame} />
          <DriveInputs frame={frame} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview: project lat/lon onto a 320x180 canvas and draw the polyline
// ---------------------------------------------------------------------------
function RouteOverview({
  timeline,
  frame,
}: {
  timeline: SimTimeline;
  frame: SimFrame;
}) {
  const W = 320;
  const H = 180;
  const PAD = 14;

  const { points, drivenIndex, latRange, lonRange } = useMemo(() => {
    const lats = timeline.frames.map((f) => f.location.lat);
    const lons = timeline.frames.map((f) => f.location.lon);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);
    const dLat = Math.max(1e-6, maxLat - minLat);
    const dLon = Math.max(1e-6, maxLon - minLon);
    const project = (lat: number, lon: number) => {
      const x = PAD + ((lon - minLon) / dLon) * (W - 2 * PAD);
      // Y is inverted: higher lat -> top
      const y = PAD + (1 - (lat - minLat) / dLat) * (H - 2 * PAD);
      return [x, y] as const;
    };
    const pts = timeline.frames.map((f) => project(f.location.lat, f.location.lon));
    const idx = timeline.frames.findIndex((f) => f.t === frame.t);
    return {
      points: pts,
      drivenIndex: idx < 0 ? 0 : idx,
      latRange: [minLat, maxLat],
      lonRange: [minLon, maxLon],
    };
  }, [timeline, frame.t]);

  const polylineFull = points.map((p) => p.join(',')).join(' ');
  const polylineDriven = points
    .slice(0, drivenIndex + 1)
    .map((p) => p.join(','))
    .join(' ');
  const car = points[drivenIndex];

  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H}>
        <defs>
          <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#1f2129" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width={W} height={H} fill="#0a0a0c" />
        <rect width={W} height={H} fill="url(#grid)" />

        {/* full route */}
        <polyline
          points={polylineFull}
          fill="none"
          stroke="#4fd1c5"
          strokeWidth="2.5"
          strokeOpacity="0.55"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {/* driven trail */}
        <polyline
          points={polylineDriven}
          fill="none"
          stroke="#facc15"
          strokeWidth="3"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {/* waypoints */}
        {timeline.meta.waypoints.map((wp, i) => {
          const x =
            PAD +
            ((wp.lon - lonRange[0]) / Math.max(1e-6, lonRange[1] - lonRange[0])) *
              (W - 2 * PAD);
          const y =
            PAD +
            (1 -
              (wp.lat - latRange[0]) / Math.max(1e-6, latRange[1] - latRange[0])) *
              (H - 2 * PAD);
          return (
            <g key={i}>
              <circle cx={x} cy={y} r="2.2" fill="#94a3b8" />
              {(i === 0 || i === timeline.meta.waypoints.length - 1) && (
                <text x={x + 5} y={y + 3} fontSize="8" fill="#64748b">
                  {wp.name}
                </text>
              )}
            </g>
          );
        })}
        {/* car pip */}
        {car && (
          <g transform={`translate(${car[0]}, ${car[1]})`}>
            <circle r="9" fill="#3b82f6" fillOpacity="0.18" />
            <circle r="5" fill="#3b82f6" stroke="#fff" strokeWidth="1.2">
              <animate
                attributeName="r"
                values="5;6.5;5"
                dur="1.2s"
                repeatCount="indefinite"
              />
            </circle>
          </g>
        )}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tactical zoomed-in pip view (car-centered, ~60m radius).
// Lead vehicle distance comes straight from perception. Ambient cars are
// generated deterministically from the frame index so the view feels alive
// without flickering randomness between renders.
// ---------------------------------------------------------------------------
type Pip = {
  id: string;
  kind: 'us' | 'lead' | 'ambient' | 'hazard' | 'pedestrian' | 'stopped';
  // meters in car-frame: forward (+ ahead), right (+ to the right of the heading)
  forward: number;
  right: number;
  label?: string;
};

function generateAmbient(t: number, count: number): Pip[] {
  // Deterministic pseudo-random ambient cars seeded by the second-of-drive
  const out: Pip[] = [];
  let s = t * 9301 + 49297;
  const rand = () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
  for (let i = 0; i < count; i++) {
    const lane = (i % 3) - 1; // -1, 0, +1
    const right = lane * 4 + (rand() - 0.5) * 1.2; // ~3-4m lane width
    const forward = -45 + rand() * 90; // -45m..+45m
    out.push({
      id: `amb-${t}-${i}`,
      kind: 'ambient',
      forward,
      right,
    });
  }
  return out;
}

function TacticalView({ frame }: { frame: SimFrame }) {
  // Field of view in meters (forward x lateral)
  const RANGE_FWD = 60;
  const RANGE_LAT = 25;
  const W = 520;
  const H = 320;

  const xOfRight = (right: number) =>
    W / 2 + (right / RANGE_LAT) * (W / 2 - 16);
  const yOfForward = (forward: number) =>
    H - 36 - ((forward + 12) / (RANGE_FWD + 12)) * (H - 60);

  const pips: Pip[] = [];

  // Lead vehicle, placed by lead_vehicle_distance_m
  const leadDist = frame.perception.lead_vehicle_distance_m;
  if (
    frame.perception.lead_vehicle_status &&
    frame.perception.lead_vehicle_status !== 'none' &&
    leadDist != null
  ) {
    pips.push({
      id: 'lead',
      kind: frame.perception.lead_vehicle_status === 'stopped' ? 'stopped' : 'lead',
      forward: Math.min(RANGE_FWD - 2, Math.max(2, leadDist)),
      right: 0,
      label:
        frame.perception.lead_vehicle_status === 'braking'
          ? 'Lead · braking'
          : frame.perception.lead_vehicle_status === 'stopped'
          ? 'Lead · stopped'
          : `Lead · ${leadDist.toFixed(0)} m`,
    });
  }

  // Ambient cars
  pips.push(...generateAmbient(frame.t, 6));

  // Pedestrian crossing ahead
  if (frame.perception.pedestrian_detected) {
    pips.push({
      id: 'ped',
      kind: 'pedestrian',
      forward: 14,
      right: -3,
      label: 'Pedestrian',
    });
    pips.push({
      id: 'ped2',
      kind: 'pedestrian',
      forward: 14,
      right: 1.5,
    });
  }

  // Hazard (incident) ahead
  if (frame.road_context.incident_ahead || frame.perception.possible_incident) {
    pips.push({
      id: 'haz',
      kind: 'hazard',
      forward: 30,
      right: 5,
      label: 'Incident',
    });
  }

  // Stopped vehicle (separate from lead) — we already render the lead, so this
  // adds a roadside stopped car to make "stopped_vehicle_detected" visible.
  if (
    frame.perception.stopped_vehicle_detected &&
    frame.perception.lead_vehicle_status !== 'stopped'
  ) {
    pips.push({
      id: 'stop',
      kind: 'stopped',
      forward: 25,
      right: 7,
      label: 'Stopped veh',
    });
  }

  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-md overflow-hidden">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H}>
        <defs>
          <pattern
            id="tgrid"
            width="22"
            height="22"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 22 0 L 0 0 0 22"
              fill="none"
              stroke="#16181f"
              strokeWidth="0.6"
            />
          </pattern>
          <radialGradient id="halo" cx="50%" cy="55%" r="55%">
            <stop offset="0%" stopColor="#0c1424" stopOpacity="1" />
            <stop offset="100%" stopColor="#06080d" stopOpacity="1" />
          </radialGradient>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.5" />
          </filter>
        </defs>

        <rect width={W} height={H} fill="url(#halo)" />
        <rect width={W} height={H} fill="url(#tgrid)" />

        {/* Road: a vertical "lane" the car drives up */}
        <rect
          x={W / 2 - 32}
          y={0}
          width={64}
          height={H}
          fill="#11141a"
          stroke="#1f2129"
        />
        {/* Lane divider dashes */}
        <line
          x1={W / 2}
          y1={0}
          x2={W / 2}
          y2={H}
          stroke="#3a3d47"
          strokeWidth="1.2"
          strokeDasharray="6 8"
        />
        {/* Sidewalk hints */}
        <line
          x1={W / 2 - 33}
          y1={0}
          x2={W / 2 - 33}
          y2={H}
          stroke="#2a2d36"
          strokeWidth="2"
        />
        <line
          x1={W / 2 + 33}
          y1={0}
          x2={W / 2 + 33}
          y2={H}
          stroke="#2a2d36"
          strokeWidth="2"
        />

        {/* Range rings (10m, 30m, 50m) */}
        {[10, 30, 50].map((r) => {
          const yTop = yOfForward(r);
          return (
            <g key={r}>
              <line
                x1={16}
                y1={yTop}
                x2={W - 16}
                y2={yTop}
                stroke="#1d2029"
                strokeDasharray="2 6"
              />
              <text x={W - 22} y={yTop - 3} fontSize="9" fill="#475569" textAnchor="end">
                {r} m
              </text>
            </g>
          );
        })}

        {/* Heading indicator at top */}
        <text x={W / 2} y={16} fontSize="9" fill="#94a3b8" textAnchor="middle">
          ↑ heading {Math.round(frame.location.heading_deg)}°
        </text>

        {/* Pips */}
        {pips.map((p) => {
          const cx = xOfRight(p.right);
          const cy = yOfForward(p.forward);
          // Skip if outside view
          if (
            Math.abs(p.right) > RANGE_LAT ||
            p.forward > RANGE_FWD ||
            p.forward < -15
          )
            return null;
          if (p.kind === 'pedestrian') {
            return (
              <g key={p.id} transform={`translate(${cx},${cy})`}>
                <circle r="8" fill="#dc2626" fillOpacity="0.15" />
                <circle r="4" fill="#ef4444" stroke="#fecaca" strokeWidth="1" />
                {p.label && (
                  <text x="8" y="3" fontSize="9" fill="#fca5a5">
                    {p.label}
                  </text>
                )}
              </g>
            );
          }
          if (p.kind === 'hazard') {
            return (
              <g key={p.id} transform={`translate(${cx},${cy})`}>
                <polygon
                  points="0,-6 6,5 -6,5"
                  fill="#ef4444"
                  stroke="#fecaca"
                  strokeWidth="1"
                />
                {p.label && (
                  <text x="9" y="3" fontSize="9" fill="#fca5a5">
                    {p.label}
                  </text>
                )}
              </g>
            );
          }
          // Vehicle pip — rectangle for cars
          const fill =
            p.kind === 'lead'
              ? '#9ca3af'
              : p.kind === 'stopped'
              ? '#7c8a99'
              : '#6b7280';
          const stroke =
            p.kind === 'lead' ? '#d1d5db' : p.kind === 'stopped' ? '#cbd5e1' : '#9ca3af';
          return (
            <g key={p.id} transform={`translate(${cx},${cy})`}>
              <rect
                x="-4.5"
                y="-7"
                width="9"
                height="14"
                rx="2"
                fill={fill}
                stroke={stroke}
                strokeWidth="0.8"
              />
              {p.kind === 'lead' && (
                <line
                  x1="0"
                  y1="-12"
                  x2="0"
                  y2="-26"
                  stroke="#9ca3af"
                  strokeDasharray="2 3"
                />
              )}
              {p.label && (
                <text x="8" y="3" fontSize="9" fill="#cbd5e1">
                  {p.label}
                </text>
              )}
            </g>
          );
        })}

        {/* Our car pip — always centered horizontally, near the bottom */}
        <g transform={`translate(${W / 2}, ${H - 36})`}>
          <circle r="22" fill="#3b82f6" fillOpacity="0.18" filter="url(#glow)" />
          <rect
            x="-6"
            y="-9"
            width="12"
            height="18"
            rx="2.5"
            fill="#3b82f6"
            stroke="#dbeafe"
            strokeWidth="1.2"
          />
          <polygon points="0,-13 -4,-9 4,-9" fill="#dbeafe" />
          <text x="11" y="4" fontSize="10" fill="#bfdbfe" fontWeight="600">
            YOU · {frame.location.speed_mph.toFixed(0)} mph
          </text>
        </g>
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-4 text-[11px] text-zinc-400 px-3 py-2 border-t border-zinc-800 bg-zinc-950">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-sm bg-blue-500 border border-blue-200" />
          You (simulated)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-sm bg-zinc-500 border border-zinc-300" />
          Other vehicles
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-500" />
          Pedestrian / hazard
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 text-zinc-500">
          <CarIcon className="w-3 h-3" /> tactical view · ~60 m radius
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Strip showing the exact inputs being fed to the optimizer right now
// ---------------------------------------------------------------------------
function DriveInputs({ frame }: { frame: SimFrame }) {
  const items: Array<{ k: string; v: string; tone?: string }> = [
    { k: 'Speed', v: `${frame.location.speed_mph.toFixed(1)} mph` },
    { k: 'Heading', v: `${Math.round(frame.location.heading_deg)}°` },
    { k: 'Speed limit', v: `${frame.road_context.speed_limit_mph} mph` },
    { k: 'Traffic spd', v: `${frame.road_context.traffic_speed_mph ?? '—'} mph` },
    { k: 'Congestion', v: frame.road_context.congestion_level },
    { k: 'Grade', v: `${(frame.road_context.road_grade_percent || 0).toFixed(1)}%` },
    {
      k: 'Lead car',
      v: `${frame.perception.lead_vehicle_status} · ${frame.perception.lead_vehicle_distance_m.toFixed(
        0
      )} m`,
      tone:
        frame.perception.lead_vehicle_status === 'braking' ||
        frame.perception.lead_vehicle_status === 'stopped'
          ? 'warn'
          : undefined,
    },
    {
      k: 'Stop ahead',
      v:
        frame.road_context.upcoming_stop_distance_m == null
          ? '—'
          : `${frame.road_context.upcoming_stop_distance_m.toFixed(0)} m`,
    },
  ];

  return (
    <div className="grid grid-cols-4 gap-2 mt-3">
      {items.map((it) => (
        <div
          key={it.k}
          className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 flex flex-col"
        >
          <span className="text-[9px] uppercase tracking-wider text-zinc-500">
            {it.k}
          </span>
          <span
            className={`font-mono text-xs ${
              it.tone === 'warn' ? 'text-amber-300' : 'text-zinc-200'
            }`}
          >
            {it.v}
          </span>
        </div>
      ))}
      <div className="col-span-4 flex items-center gap-3 text-[11px] text-zinc-400 mt-1">
        {frame.perception.pedestrian_detected && (
          <span className="inline-flex items-center gap-1 text-red-300">
            <Footprints className="w-3 h-3" /> pedestrian detected
          </span>
        )}
        {(frame.road_context.incident_ahead ||
          frame.perception.possible_incident) && (
          <span className="inline-flex items-center gap-1 text-red-300">
            <AlertTriangle className="w-3 h-3" /> incident ahead
          </span>
        )}
        {frame.perception.traffic_state &&
          frame.perception.traffic_state !== 'clear' && (
            <span className="inline-flex items-center gap-1 text-amber-300">
              traffic: {frame.perception.traffic_state}
            </span>
          )}
      </div>
    </div>
  );
}
