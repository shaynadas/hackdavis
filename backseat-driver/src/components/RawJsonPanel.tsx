import { useState } from 'react';
import { Code } from 'lucide-react';

interface RawJsonPanelProps {
  payloads: Record<string, any | null>;
}

export function RawJsonPanel({ payloads }: RawJsonPanelProps) {
  const tabs = Object.keys(payloads);
  const [activeTab, setActiveTab] = useState(tabs[0]);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg flex flex-col h-[300px]">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800">
        <Code className="w-4 h-4 text-zinc-400" />
        <div className="flex gap-2 overflow-x-auto custom-scrollbar">
          {tabs.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`text-xs px-2 py-1 rounded whitespace-nowrap ${
                activeTab === tab ? 'bg-zinc-800 text-zinc-200 font-medium' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>
      
      <div className="flex-1 overflow-auto p-4 custom-scrollbar bg-zinc-950/50 rounded-b-lg">
        <pre className="text-[10px] text-zinc-400 font-mono">
          {payloads[activeTab] 
            ? JSON.stringify(payloads[activeTab], null, 2) 
            : 'null'}
        </pre>
      </div>
    </div>
  );
}
