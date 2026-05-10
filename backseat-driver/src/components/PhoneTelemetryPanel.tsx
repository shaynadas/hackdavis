import { useEffect, useRef } from 'react';
import { Smartphone } from 'lucide-react';

interface PhoneTelemetryPanelProps {
  telemetry: any | null;
}

export function PhoneTelemetryPanel({ telemetry }: PhoneTelemetryPanelProps) {
  const mapRef = useRef<any>(null);
  const markerRef = useRef<any>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);

  const isConnected = telemetry !== null;
  const lat = telemetry?.gps?.latitude ?? telemetry?.lat ?? null;
  const lon = telemetry?.gps?.longitude ?? telemetry?.lon ?? null;
  const hasGps = lat !== null && lon !== null;

  // Initialize Leaflet map once
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    // Dynamically load Leaflet CSS
    if (!document.getElementById('leaflet-css')) {
      const link = document.createElement('link');
      link.id = 'leaflet-css';
      link.rel = 'stylesheet';
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(link);
    }

    // Dynamically load Leaflet JS, then init map
    const initMap = () => {
      const L = (window as any).L;
      if (!L || !mapContainerRef.current) return;

      const defaultLat = 38.5449;
      const defaultLon = -121.7405;

      const map = L.map(mapContainerRef.current, {
        center: [defaultLat, defaultLon],
        zoom: 15,
        zoomControl: false,
        attributionControl: false,
      });

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

      // Custom pulsing marker icon
      const icon = L.divIcon({
        className: '',
        html: `
          <div style="position:relative;width:20px;height:20px;">
            <div style="position:absolute;inset:0;border-radius:50%;background:#3b82f6;opacity:0.3;animation:pulse 1.5s infinite;"></div>
            <div style="position:absolute;inset:4px;border-radius:50%;background:#3b82f6;border:2px solid white;"></div>
          </div>
        `,
        iconSize: [20, 20],
        iconAnchor: [10, 10],
      });

      const marker = L.marker([defaultLat, defaultLon], { icon }).addTo(map);
      mapRef.current = map;
      markerRef.current = marker;
    };

    if ((window as any).L) {
      initMap();
    } else {
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      script.onload = initMap;
      document.head.appendChild(script);
    }

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
        markerRef.current = null;
      }
    };
  }, []);

  // Update marker position when lat/lon changes
  useEffect(() => {
    if (!mapRef.current || !markerRef.current || !hasGps) return;
    const pos = [lat, lon];
    markerRef.current.setLatLng(pos);
    mapRef.current.setView(pos, mapRef.current.getZoom());
  }, [lat, lon, hasGps]);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <h2 className="text-sm font-semibold text-zinc-400 flex items-center gap-2 uppercase tracking-wider">
          <Smartphone className="w-4 h-4" />
          Phone
        </h2>
        <div className="flex items-center gap-2">
          {isConnected ? (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              <span className="text-xs text-green-400 font-mono">Connected</span>
            </>
          ) : (
            <>
              <span className="relative flex h-2 w-2">
                <span className="relative inline-flex rounded-full h-2 w-2 bg-zinc-600"></span>
              </span>
              <span className="text-xs text-zinc-500 font-mono">Waiting...</span>
            </>
          )}
        </div>
      </div>

      {/* Map */}
      <div className="relative" style={{ height: '220px' }}>
        <style>{`
          @keyframes pulse {
            0% { transform: scale(1); opacity: 0.3; }
            70% { transform: scale(2.5); opacity: 0; }
            100% { transform: scale(2.5); opacity: 0; }
          }
        `}</style>
        <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />
        {!hasGps && (
          <div className="absolute inset-0 flex items-center justify-center bg-zinc-900/70 text-zinc-500 text-sm">
            No GPS data yet
          </div>
        )}
      </div>

      {/* Coords footer */}
      {hasGps && (
        <div className="px-4 py-2 border-t border-zinc-800 flex justify-between text-xs font-mono text-zinc-500">
          <span>LAT <span className="text-blue-400">{lat.toFixed(5)}</span></span>
          <span>LON <span className="text-blue-400">{lon.toFixed(5)}</span></span>
        </div>
      )}
    </div>
  );
}
