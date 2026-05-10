import { useState, useEffect, useRef } from 'react';
import { api } from './api';
import { Header } from './components/Header';
import { InputStatePanel } from './components/InputStatePanel';
import { LocationPanel } from './components/LocationPanel';
import { EventLog } from './components/EventLog';
import { RecommendationPanel } from './components/RecommendationPanel';
import { SpeedChart } from './components/SpeedChart';
import { RPMEcoChart } from './components/RPMEcoChart';
import { VehiclePanel } from './components/VehiclePanel';
import { VoicePanel } from './components/VoicePanel';
import { RawJsonPanel } from './components/RawJsonPanel';
import { PhoneTelemetryPanel } from './components/PhoneTelemetryPanel';
import { Car, Navigation } from 'lucide-react';
import { useLocationStreamer } from './hooks/useLocationStreamer';
import type { EventLogItem, RecommendationResponse, LocationInput, PerceptionInput, RoadContextInput, VehicleProfileInput, VoiceStatus } from './types';

export default function App() {
  const [apiStatus, setApiStatus] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(new Date());
  
  const [recommendation, setRecommendation] = useState<RecommendationResponse | null>(null);
  const [location, setLocation] = useState<LocationInput | null>(null);
  const [telemetry, setTelemetry] = useState<any | null>(null);
  const [perception, setPerception] = useState<PerceptionInput | null>(null);
  const [roadContext, setRoadContext] = useState<RoadContextInput | null>(null);
  const [vehicle, setVehicle] = useState<VehicleProfileInput | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  
  const [speedChartData, setSpeedChartData] = useState<any[]>([]);
  const [rpmChartData, setRpmChartData] = useState<any[]>([]);
  const [logs, setLogs] = useState<EventLogItem[]>([]);
  
  const prevRecAction = useRef<string | null>(null);
  const prevSafetyLevel = useRef<string | null>(null);
  const prevApiStatus = useRef<boolean>(false);
  const prevIsStreaming = useRef<boolean>(false);
  const prevRecReceived = useRef<boolean>(false);

  const [gpsEnabled, setGpsEnabled] = useState(false);
  const { isStreaming, permissionState, error } = useLocationStreamer(gpsEnabled);

  const addLog = (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
    setLogs(prev => {
      const newLog = { id: Math.random().toString(), timestamp: new Date(), message, type };
      return [newLog, ...prev].slice(0, 100);
    });
  };

  const refreshDashboard = async () => {
    const v = await api.getLatestVehicle();
    setVehicle(v);
  };

  useEffect(() => {
    if (isStreaming && !prevIsStreaming.current) {
      addLog("GPS stream started", "success");
      prevIsStreaming.current = true;
    } else if (!isStreaming && prevIsStreaming.current) {
      if (gpsEnabled) {
        // Just losing fix temporarily
      } else {
        addLog("GPS stream stopped", "info");
        prevIsStreaming.current = false;
      }
    }
    
    if (permissionState === 'denied') {
      addLog("GPS permission denied", "error");
    }
  }, [isStreaming, gpsEnabled, permissionState]);

  useEffect(() => {
    const pollData = async () => {
      try {
        const [health, rec, loc, tel, perc, ctx, veh, voice] = await Promise.all([
          api.checkHealth(),
          api.getLiveRecommendation(),
          api.getLatestLocation(),
          api.getLatestTelemetry(),
          api.getLatestPerception(),
          api.getLatestRoadContext(),
          api.getLatestVehicle(),
          api.getVoiceStatus()
        ]);

        const isOnline = health !== null;
        setApiStatus(isOnline);
        setLastUpdated(new Date());
        
        if (isOnline !== prevApiStatus.current) {
          addLog(isOnline ? "Backend API connected" : "Backend API offline", isOnline ? "success" : "error");
          prevApiStatus.current = isOnline;
        }

        if (rec) {
          if (!prevRecReceived.current) {
            addLog("Live recommendation connected", "success");
            prevRecReceived.current = true;
          }
          
          setRecommendation(rec);
          
          if (prevRecAction.current !== rec.summary.recommended_action) {
            addLog(`Action changed to ${rec.summary.recommended_action.replace(/_/g, ' ')}`, 'info');
            prevRecAction.current = rec.summary.recommended_action;
          }
          if (prevSafetyLevel.current !== rec.summary.safety_level) {
            addLog(`Safety level is now ${rec.summary.safety_level}`, rec.summary.safety_level === 'urgent' ? 'error' : 'warning');
            prevSafetyLevel.current = rec.summary.safety_level;
          }

          // Update charts
          const now = new Date().toLocaleTimeString();
          
          setSpeedChartData(prev => {
            const next = [...prev, {
              time: now,
              current_speed: rec.summary.current_speed_mph,
              optimal_speed: rec.summary.optimal_speed_now_mph,
              traffic_speed: ctx?.traffic_speed_mph || rec.summary.optimal_speed_now_mph
            }];
            return next.slice(-60);
          });
          
          setRpmChartData(prev => {
            const next = [...prev, {
              time: now,
              estimated_rpm: rec.summary.estimated_rpm_at_optimal_speed,
              eco_score: rec.summary.eco_score
            }];
            return next.slice(-60);
          });
        } else {
          setRecommendation(null);
          prevRecReceived.current = false;
        }

        if (loc) setLocation(loc);
        if (tel) setTelemetry(tel);
        if (perc) setPerception(perc);
        if (ctx) setRoadContext(ctx);
        if (veh) setVehicle(veh);
        if (voice) setVoiceStatus(voice);

      } catch (err) {
        setApiStatus(false);
        if (prevApiStatus.current !== false) {
          addLog("Backend API offline (fetch error)", "error");
          prevApiStatus.current = false;
        }
      }
    };

    pollData();
    const interval = setInterval(pollData, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col font-sans">
      <Header apiStatus={apiStatus} voiceStatus={voiceStatus} lastUpdated={lastUpdated} />
      
      <div className="flex-1 p-4 grid grid-cols-12 gap-4">
        {/* Left Column */}
        <div className="col-span-3 flex flex-col gap-4">
          <PhoneTelemetryPanel telemetry={telemetry} />
          <InputStatePanel title="Perception State" icon={<Car className="w-4 h-4" />} data={perception} />
          <EventLog logs={logs} />
        </div>

        {/* Middle Column */}
        <div className="col-span-6 flex flex-col gap-4">
          <RecommendationPanel data={recommendation} />
          <SpeedChart data={speedChartData} />
          <RPMEcoChart data={rpmChartData} />
        </div>

        {/* Right Column */}
        <div className="col-span-3 flex flex-col gap-4">
          <LocationPanel 
            location={location} 
            gpsEnabled={gpsEnabled}
            setGpsEnabled={setGpsEnabled}
            isStreaming={isStreaming}
            permissionState={permissionState}
            error={error}
          />
          <InputStatePanel title="Road Context" icon={<Navigation className="w-4 h-4" />} data={roadContext} />
          <VehiclePanel vehicle={vehicle} refreshDashboard={refreshDashboard} />
          <VoicePanel status={voiceStatus} voiceLine={recommendation?.advice?.voice_line} />
          <RawJsonPanel payloads={{
            recommendation,
            location,
            telemetry,
            perception,
            road_context: roadContext,
            vehicle,
            voice_status: voiceStatus
          }} />
        </div>
      </div>
    </div>
  );
}
