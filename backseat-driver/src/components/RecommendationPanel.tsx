import { Zap, ShieldAlert, Navigation } from 'lucide-react';
import type { RecommendationResponse } from '../types';

export function RecommendationPanel({ data }: { data: RecommendationResponse | null }) {
  if (!data) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 flex flex-col items-center justify-center h-full">
        <ShieldAlert className="w-12 h-12 text-zinc-700 mb-3" />
        <p className="text-zinc-500 font-medium">Waiting for GPS data</p>
      </div>
    );
  }

  const { summary, advice } = data;
  
  let safetyColor = "text-green-400";
  let safetyBg = "bg-green-400/10 border-green-400/20";
  if (summary.safety_level === "caution") {
    safetyColor = "text-yellow-400";
    safetyBg = "bg-yellow-400/10 border-yellow-400/20";
  } else if (summary.safety_level === "urgent") {
    safetyColor = "text-red-400";
    safetyBg = "bg-red-400/10 border-red-400/20";
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-sm font-semibold text-zinc-400 flex items-center gap-2 uppercase tracking-wider">
          <Zap className="w-4 h-4" /> Live Recommendation
        </h2>
        
        <div className={`px-3 py-1 rounded-full border ${safetyBg} flex items-center gap-2`}>
          <ShieldAlert className={`w-4 h-4 ${safetyColor}`} />
          <span className={`text-xs font-bold uppercase tracking-wider ${safetyColor}`}>
            {summary.safety_level}
          </span>
        </div>
      </div>
      
      <div className="grid grid-cols-2 gap-6 mb-6 border-b border-zinc-800 pb-6">
        <div>
          <span className="text-xs text-zinc-500 uppercase tracking-wide block mb-1">Target Speed</span>
          <div className="flex items-baseline gap-2">
            <span className="text-5xl font-black text-slate-100">{summary.optimal_speed_now_mph}</span>
            <span className="text-xl text-zinc-500">mph</span>
          </div>
          <div className="text-sm font-mono text-zinc-400 mt-1">Band: {summary.recommended_speed_band_mph}</div>
        </div>
        
        <div>
          <span className="text-xs text-zinc-500 uppercase tracking-wide block mb-1">Target RPM</span>
          <div className="flex items-baseline gap-2">
            <span className="text-5xl font-black text-blue-400">{summary.estimated_rpm_at_optimal_speed}</span>
            <span className="text-xl text-zinc-500">rpm</span>
          </div>
          <div className="text-sm font-mono text-zinc-400 mt-1">Gear: {summary.recommended_gear}</div>
        </div>
      </div>
      
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-zinc-950 rounded p-4 border border-zinc-800">
          <span className="text-xs text-zinc-500 uppercase block mb-1">Action</span>
          <span className="text-lg font-bold text-slate-200 capitalize">{summary.recommended_action.replace(/_/g, ' ')}</span>
        </div>
        <div className="bg-zinc-950 rounded p-4 border border-zinc-800">
          <span className="text-xs text-zinc-500 uppercase block mb-1">Eco Score</span>
          <span className="text-lg font-bold text-green-400">{summary.eco_score} / 100</span>
        </div>
      </div>
      
      <div className="bg-blue-900/10 border border-blue-900/30 rounded p-4">
        <div className="flex items-start gap-3">
          <Navigation className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-blue-100 font-medium mb-1 leading-snug">"{advice.voice_line}"</p>
            <p className="text-xs text-blue-400/60 font-mono italic">Reason: {advice.reason}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
