import { Terminal } from 'lucide-react';
import type { EventLogItem } from '../types';

export function EventLog({ logs }: { logs: EventLogItem[] }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 flex flex-col h-[300px]">
      <h2 className="text-sm font-semibold text-zinc-400 flex items-center gap-2 uppercase tracking-wider mb-3">
        <Terminal className="w-4 h-4" /> Event Log
      </h2>
      
      <div className="flex-1 overflow-y-auto space-y-2 pr-2 custom-scrollbar">
        {logs.map(log => {
          let color = "text-zinc-400";
          if (log.type === 'error') color = "text-red-400";
          if (log.type === 'success') color = "text-green-400";
          if (log.type === 'warning') color = "text-yellow-400";
          
          return (
            <div key={log.id} className="text-xs font-mono border-b border-zinc-800/50 pb-1">
              <span className="text-zinc-600 mr-2">[{log.timestamp.toLocaleTimeString()}]</span>
              <span className={color}>{log.message}</span>
            </div>
          );
        })}
        {logs.length === 0 && (
          <div className="text-zinc-600 text-sm italic">Listening for events...</div>
        )}
      </div>
    </div>
  );
}
