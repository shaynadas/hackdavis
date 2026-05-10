import { useState, useRef } from 'react';
import { Car, Mic, Loader2 } from 'lucide-react';
import type { VehicleProfileInput } from '../types';
import { api } from '../api';

export function VehiclePanel({ vehicle, refreshDashboard }: { vehicle: VehicleProfileInput | null, refreshDashboard: () => void }) {
  const [typedVin, setTypedVin] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [session, setSession] = useState<{ id: string, text: string, type: 'typed' | 'voice' } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<BlobPart[]>([]);

  const handleTypedSubmit = async () => {
    if (!typedVin) return;
    setIsLoading(true);
    const res = await api.vinTyped(typedVin);
    if (res?.success && res.session_id && res.confirmation_text) {
      setSession({ id: res.session_id, text: res.confirmation_text, type: 'typed' });
    } else {
      alert("Error: " + (res?.error || "Invalid VIN"));
    }
    setIsLoading(false);
  };

  const toggleRecording = async () => {
    if (isRecording) {
      mediaRecorder.current?.stop();
      setIsRecording(false);
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder.current = new MediaRecorder(stream);
        chunks.current = [];
        
        mediaRecorder.current.ondataavailable = e => chunks.current.push(e.data);
        mediaRecorder.current.onstop = async () => {
          setIsLoading(true);
          const blob = new Blob(chunks.current, { type: 'audio/wav' });
          const file = new File([blob], 'vin_audio.wav', { type: 'audio/wav' });
          
          const res = await api.transcribeVinAudio(file);
          if (res?.success && res.session_id && res.confirmation_text) {
            setSession({ id: res.session_id, text: res.confirmation_text, type: 'voice' });
            // Optionally auto-speak
            if (res.speak_endpoint) {
              const audioBlob = await api.speakText(res.confirmation_text);
              if (audioBlob) {
                const url = URL.createObjectURL(audioBlob);
                const audio = new Audio(url);
                audio.play();
              }
            }
          } else {
            alert("Error: " + (res?.error || "Could not capture VIN"));
          }
          setIsLoading(false);
          stream.getTracks().forEach(t => t.stop());
        };
        
        mediaRecorder.current.start();
        setIsRecording(true);
      } catch (err) {
        console.error(err);
        alert("Microphone access denied.");
      }
    }
  };

  const handleConfirm = async (confirmed: boolean) => {
    if (!session) return;
    setIsLoading(true);
    const res = await api.confirmVin(session.id, confirmed);
    if (res?.success && confirmed) {
      refreshDashboard();
    }
    setSession(null);
    setTypedVin('');
    setIsLoading(false);
  };

  const handleClear = async () => {
    setIsLoading(true);
    await api.clearLatestVehicle();
    refreshDashboard();
    setIsLoading(false);
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-3">
        <h2 className="text-sm font-semibold text-zinc-400 flex items-center gap-2 uppercase tracking-wider">
          <Car className="w-4 h-4" /> Vehicle Profile
        </h2>
        {vehicle && (
          <button onClick={handleClear} disabled={isLoading} className="text-xs text-red-400 hover:text-red-300">
            Clear
          </button>
        )}
      </div>

      {vehicle ? (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between"><span className="text-zinc-500">Year</span><span className="text-zinc-200">{vehicle.year || 'Unknown'}</span></div>
          <div className="flex justify-between"><span className="text-zinc-500">Make</span><span className="text-zinc-200">{vehicle.make || 'Unknown'}</span></div>
          <div className="flex justify-between"><span className="text-zinc-500">Model</span><span className="text-zinc-200">{vehicle.model || 'Unknown'}</span></div>
          <div className="flex justify-between"><span className="text-zinc-500">Trim</span><span className="text-zinc-200">{vehicle.trim || 'Unknown'}</span></div>
          {vehicle.vin && <div className="flex justify-between"><span className="text-zinc-500">VIN</span><span className="text-zinc-200 font-mono text-xs">{vehicle.vin}</span></div>}
          <div className="flex justify-between mt-2 pt-2 border-t border-zinc-800"><span className="text-zinc-500">Source</span><span className="text-blue-400 text-xs font-mono">{vehicle.source || 'api'}</span></div>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-zinc-500 italic mb-2">No vehicle set. Enter VIN to configure.</p>
          
          {!session ? (
            <>
              <div className="flex gap-2">
                <input 
                  type="text" 
                  placeholder="Type 17-char VIN" 
                  value={typedVin}
                  onChange={e => setTypedVin(e.target.value)}
                  className="flex-1 bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-sm text-zinc-200 focus:outline-none"
                />
                <button 
                  onClick={handleTypedSubmit}
                  disabled={isLoading || !typedVin}
                  className="bg-zinc-800 hover:bg-zinc-700 px-3 py-1 rounded text-sm text-white disabled:opacity-50"
                >
                  {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Send'}
                </button>
              </div>
              
              <div className="relative flex py-2 items-center">
                <div className="flex-grow border-t border-zinc-800"></div>
                <span className="flex-shrink-0 mx-2 text-zinc-600 text-xs">OR</span>
                <div className="flex-grow border-t border-zinc-800"></div>
              </div>
              
              <button 
                onClick={toggleRecording}
                disabled={isLoading}
                className={`w-full py-2 rounded flex items-center justify-center gap-2 text-sm font-medium transition-colors ${
                  isRecording ? 'bg-red-600/20 text-red-400 border border-red-900' : 'bg-zinc-800 hover:bg-zinc-700 text-white'
                }`}
              >
                {isRecording ? <><Mic className="w-4 h-4 animate-pulse" /> Recording... (Click to stop)</> : <><Mic className="w-4 h-4" /> Enter VIN by Voice</>}
              </button>
            </>
          ) : (
            <div className="bg-blue-900/10 border border-blue-900/30 rounded p-3 text-sm">
              <p className="text-blue-200 mb-3">{session.text}</p>
              <div className="flex gap-2">
                <button onClick={() => handleConfirm(true)} disabled={isLoading} className="flex-1 bg-green-600 hover:bg-green-500 text-white py-1.5 rounded">Yes</button>
                <button onClick={() => handleConfirm(false)} disabled={isLoading} className="flex-1 bg-red-600 hover:bg-red-500 text-white py-1.5 rounded">No</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
