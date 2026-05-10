import { useState, useRef, useEffect } from 'react';
import { Camera, CameraOff, MonitorPlay } from 'lucide-react';

export function LiveVideoPanel() {
  const [streamUrl, setStreamUrl] = useState(import.meta.env.VITE_VIDEO_STREAM_URL || 'http://localhost:8001/video_feed');
  const [useWebcam, setUseWebcam] = useState(false);
  const [isAnnotated, setIsAnnotated] = useState(true);
  const [isImgError, setIsImgError] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  
  useEffect(() => {
    let stream: MediaStream | null = null;
    if (useWebcam) {
      navigator.mediaDevices.getUserMedia({ video: true })
        .then(s => {
          stream = s;
          if (videoRef.current) {
            videoRef.current.srcObject = s;
          }
        })
        .catch(err => {
          console.error("Webcam error:", err);
          setUseWebcam(false);
        });
    }
    
    return () => {
      if (stream) {
        stream.getTracks().forEach(t => t.stop());
      }
    };
  }, [useWebcam]);

  // Construct the final URL based on the toggle
  const finalStreamUrl = streamUrl.includes('?') 
    ? `${streamUrl.split('?')[0]}?type=${isAnnotated ? 'annotated' : 'smooth'}` 
    : `${streamUrl}?type=${isAnnotated ? 'annotated' : 'smooth'}`;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 flex flex-col h-[320px]">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-zinc-400 flex items-center gap-2 uppercase tracking-wider">
          <Camera className="w-4 h-4" /> Live Video
        </h2>
        <div className="flex gap-2">
          {!useWebcam && (
            <button 
              onClick={() => setIsAnnotated(!isAnnotated)}
              className="text-[10px] uppercase font-bold bg-zinc-800 hover:bg-zinc-700 px-2 py-1 rounded text-zinc-300"
            >
              {isAnnotated ? "Show Smooth Feed" : "Show Annotated Feed"}
            </button>
          )}
          <button 
            onClick={() => setUseWebcam(!useWebcam)}
            className="text-xs bg-zinc-800 hover:bg-zinc-700 px-2 py-1 rounded text-zinc-300"
          >
            {useWebcam ? "Network" : "Webcam"}
          </button>
        </div>
      </div>
      
      <div className="flex-1 bg-black rounded-md overflow-hidden relative flex items-center justify-center">
        {useWebcam ? (
          <video 
            ref={videoRef} 
            autoPlay 
            playsInline 
            muted 
            className="w-full h-full object-cover"
          />
        ) : (
          !isImgError ? (
            <img 
              src={finalStreamUrl} 
              alt="Live stream" 
              className="w-full h-full object-cover"
              onError={() => setIsImgError(true)}
            />
          ) : (
            <div className="flex flex-col items-center gap-2 text-zinc-600">
              <CameraOff className="w-8 h-8" />
              <span className="text-sm">No video stream connected</span>
            </div>
          )
        )}
      </div>
      
      {!useWebcam && (
        <div className="mt-3 flex items-center gap-2">
          <MonitorPlay className="w-4 h-4 text-zinc-500" />
          <input 
            type="text" 
            value={streamUrl}
            onChange={(e) => {
              setStreamUrl(e.target.value);
              setIsImgError(false);
            }}
            className="flex-1 bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-300 focus:outline-none focus:border-zinc-600"
            placeholder="Stream URL (e.g., http://pi:8001/video_feed)"
          />
        </div>
      )}
    </div>
  );
}
