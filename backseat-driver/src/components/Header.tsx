import { Activity, Wifi, WifiOff, Mic, Clock } from 'lucide-react';
import type { VoiceStatus } from '../types';

interface HeaderProps {
  apiStatus: boolean;
  voiceStatus: VoiceStatus | null;
  lastUpdated: Date;
}

export function Header({ apiStatus, voiceStatus, lastUpdated }: HeaderProps) {
  return (
    <header className="bg-zinc-900 border-b border-zinc-800 p-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <Activity className="text-blue-500 w-6 h-6" />
        <h1 className="text-xl font-bold text-slate-100">Backseat Driver</h1>
        <span className="px-2 py-0.5 rounded text-xs font-semibold bg-zinc-800 text-zinc-400 border border-zinc-700 ml-4">
          ADMIN / GOD VIEW
        </span>
      </div>
      
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          {apiStatus ? (
            <span className="flex items-center gap-1.5 text-sm text-green-400">
              <Wifi className="w-4 h-4" /> API Online
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-sm text-red-400">
              <WifiOff className="w-4 h-4" /> API Offline
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {voiceStatus?.elevenlabs_configured ? (
            <span className="flex items-center gap-1.5 text-sm text-green-400">
              <Mic className="w-4 h-4" /> Voice Ready
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-sm text-zinc-500">
              <Mic className="w-4 h-4" /> Voice Disabled
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-1.5 text-sm text-zinc-400 border-l border-zinc-800 pl-6">
          <Clock className="w-4 h-4" />
          {lastUpdated.toLocaleTimeString()}
        </div>
      </div>
    </header>
  );
}
