import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

export function RPMEcoChart({ data }: { data: any[] }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 h-[300px] flex flex-col">
      <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4">RPM & Eco Score</h2>
      <div className="flex-1 w-full h-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="time" hide />
            <YAxis yAxisId="left" stroke="#52525b" fontSize={12} tickLine={false} axisLine={false} />
            <YAxis yAxisId="right" orientation="right" stroke="#52525b" fontSize={12} tickLine={false} axisLine={false} domain={[0, 100]} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '6px' }}
              itemStyle={{ fontSize: '14px', fontWeight: 500 }}
              labelStyle={{ display: 'none' }}
            />
            <Legend iconType="circle" wrapperStyle={{ fontSize: '12px' }} />
            <Line yAxisId="left" type="monotone" dataKey="estimated_rpm" name="Est. RPM" stroke="#8b5cf6" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line yAxisId="right" type="monotone" dataKey="eco_score" name="Eco Score" stroke="#4ade80" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
