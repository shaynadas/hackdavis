import { useState } from 'react';
import { Mic, Volume2, Loader2 } from 'lucide-react';
import type { VoiceStatus } from '../types';
import { api } from '../api';

export function VoicePanel({ status, voiceLine }: { status: VoiceStatus | null, voiceLine?: string }) {
  const [isPlaying, setIsPlaying] = useState(false);

  const handleSpeak = async () => {
    if (!voiceLine || isPlaying) return;
    setIsPlaying(true);
    
    try {
      const blob = await api.speakText(voiceLine);
      if (blob) {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.onended = () => {
          URL.revokeObjectURL(url);
          setIsPlaying(false);
        };
        audio.play();
      } else {
        setIsPlaying(false);
      }
    } catch (e) {
      console.error(e);
      setIsPlaying(false);
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-zinc-400 flex items-center gap-2 uppercase tracking-wider mb-3 border-b border-zinc-800 pb-2">
        <Mic className="w-4 h-4" /> ElevenLabs Voice
      </h2>
      
      {!status ? (
        <div className="text-zinc-600 text-sm italic">Status unknown</div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 text-sm">
            <span className="text-zinc-500">API Key</span>
            <span className={status.elevenlabs_configured ? "text-green-400" : "text-red-400"}>
              {status.elevenlabs_configured ? "Configured" : "Missing"}
            </span>
            
            <span className="text-zinc-500">TTS Ready</span>
            <span className={status.tts_configured ? "text-green-400" : "text-red-400"}>
              {status.tts_configured ? "Yes" : "No"}
            </span>
            
            <span className="text-zinc-500">STT Ready</span>
            <span className={status.stt_configured ? "text-green-400" : "text-red-400"}>
              {status.stt_configured ? "Yes" : "No"}
            </span>
            
            <span className="text-zinc-500">TTS Model</span>
            <span className="text-zinc-300 font-mono text-xs">{status.tts_model}</span>
          </div>
          
          <button
            disabled={!status.tts_configured || !voiceLine || isPlaying}
            onClick={handleSpeak}
            className={`w-full py-2 rounded flex items-center justify-center gap-2 text-sm font-medium transition-colors ${
              !status.tts_configured || !voiceLine
                ? 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-500 text-white'
            }`}
          >
            {isPlaying ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Speaking...</>
            ) : (
              <><Volume2 className="w-4 h-4" /> Speak Current Advice</>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
