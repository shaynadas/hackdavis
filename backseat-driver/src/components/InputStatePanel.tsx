import type { ReactNode } from 'react';

interface InputStatePanelProps {
  title: string;
  icon: ReactNode;
  data: Record<string, any> | null;
}

export function InputStatePanel({ title, icon, data }: InputStatePanelProps) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-zinc-400 flex items-center gap-2 uppercase tracking-wider mb-3 border-b border-zinc-800 pb-2">
        {icon} {title}
      </h2>
      
      {data ? (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          {Object.entries(data).map(([key, value]) => {
            if (value === null || value === undefined) return null;
            
            // Format value
            let displayVal = String(value);
            let valClass = "text-zinc-200 font-mono text-sm";
            
            if (typeof value === 'boolean') {
              displayVal = value ? 'TRUE' : 'FALSE';
              valClass = value ? "text-red-400 font-bold font-mono text-sm" : "text-zinc-500 font-mono text-sm";
            }
            if (typeof value === 'number') {
              displayVal = Number.isInteger(value) ? displayVal : value.toFixed(2);
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
        <div className="text-zinc-600 text-sm italic">No data yet</div>
      )}
    </div>
  );
}
