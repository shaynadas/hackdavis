import { MapPin, Play, Square, Settings } from 'lucide-react';
import type { LocationInput } from '../types';
import { postLocationUpdate } from '../api';

interface LocationPanelProps {
  location: LocationInput | null;
  gpsEnabled: boolean;
  setGpsEnabled: (enabled: boolean) => void;
  isStreaming: boolean;
  permissionState: string;
  error: string | null;
}

export function LocationPanel({ 
  location, 
  gpsEnabled, 
  setGpsEnabled, 
  isStreaming, 
  permissionState, 
  error 
}: LocationPanelProps) {
  
  const handleDemoSeed = async () => {
    await postLocationUpdate({
      lat: 38.5449,
      lon: -121.7405,
      speed_mph: 0,
      heading_deg: 0,
      accuracy_m: 20
    });
  };

  let statusText = "Stopped";
  let statusColor = "text-zinc-500";
  
  if (error) {
    statusText = error;
    statusColor = "text-red-400";
  } else if (isStreaming) {
    statusText = "Active";
    statusColor = "text-green-400";
  } else if (gpsEnabled && permissionState === "prompt") {
    statusText = "Waiting for permission...";
    statusColor = "text-yellow-400";
  } else if (gpsEnabled && permissionState === "denied") {
    statusText = "Permission denied";
    statusColor = "text-red-400";
  } else if (gpsEnabled) {
    statusText = "Starting...";
    statusColor = "text-blue-400";
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 flex flex-col">
      <div className="flex items-center justify-between mb-3 border-b border-zinc-800 pb-2">
        <h2 className="text-sm font-semibold text-zinc-400 flex items-center gap-2 uppercase tracking-wider">
          <MapPin className="w-4 h-4" /> Location
        </h2>
        <span className={`text-xs font-mono ${statusColor}`}>{statusText}</span>
      </div>
      
      {location ? (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 mb-4">
          {Object.entries(location).map(([key, value]) => {
            if (value === null || value === undefined) return null;
            
            let displayVal = String(value);
            let valClass = "text-zinc-200 font-mono text-sm";
            
            if (typeof value === 'number') {
              displayVal = Number.isInteger(value) ? displayVal : value.toFixed(4);
              valClass = "text-blue-300 font-mono text-sm";
            }

            return (
              <div key={key} className="flex flex-col">
                <span className="text-[10px] text-zinc-500 uppercase">{key.replace(/_/g, ' ')}</span>
                <span className={valClass}>{displayVal}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-zinc-600 text-sm italic mb-4">Waiting for GPS data</div>
      )}
      
      <div className="mt-auto grid grid-cols-2 gap-2">
        {gpsEnabled ? (
          <button 
            onClick={() => setGpsEnabled(false)}
            className="col-span-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-900/50 py-1.5 rounded flex items-center justify-center gap-2 text-sm transition-colors"
          >
            <Square className="w-3.5 h-3.5 fill-current" /> Stop GPS Stream
          </button>
        ) : (
          <button 
            onClick={() => setGpsEnabled(true)}
            className="col-span-2 bg-green-600/20 hover:bg-green-600/30 text-green-400 border border-green-900/50 py-1.5 rounded flex items-center justify-center gap-2 text-sm transition-colors"
          >
            <Play className="w-3.5 h-3.5 fill-current" /> Start GPS Stream
          </button>
        )}
        
        <button 
          onClick={handleDemoSeed}
          className="col-span-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 py-1.5 rounded flex items-center justify-center gap-2 text-sm transition-colors"
        >
          <Settings className="w-3.5 h-3.5" /> Seed Demo Location
        </button>
      </div>
    </div>
  );
}
