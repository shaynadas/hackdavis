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
import { useSimulator } from './hooks/useSimulator';
import { SimulatedDriveMap } from './components/SimulatedDriveMap';
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

  // Simulated 2-min Davis drive (toggled by the LocationPanel "Seed Demo Location" button)
  const [simulationActive, setSimulationActive] = useState(false);
  const prevPerceptionRef = useRef<any>(null);
  const prevRoadRef = useRef<any>(null);

  const sim = useSimulator({
    active: simulationActive,
    speedMul: 0.5,  // Slow down to 0.5x speed (2 seconds per frame instead of 1)
    loop: false,
    onFrame: (frame, idx) => {
      // Primary fix: Mirror frame data directly to dashboard state
      // This ensures the panels update even if backend POSTs fail

      // Update location state
      setLocation({
        lat: frame.location.lat,
        lon: frame.location.lon,
        speed_mph: frame.location.speed_mph,
        heading_deg: frame.location.heading_deg,
        accuracy_m: frame.location.accuracy_m,
      });

      // Update perception state (strip lead_vehicle_distance_m which is map-only)
      const perceptionData = {
        traffic_state: frame.perception.traffic_state,
        lead_vehicle_status: frame.perception.lead_vehicle_status,
        lead_vehicle_distance: frame.perception.lead_vehicle_distance,
        stopped_vehicle_detected: frame.perception.stopped_vehicle_detected,
        hazard_detected: frame.perception.hazard_detected,
        pedestrian_detected: frame.perception.pedestrian_detected,
        cyclist_detected: frame.perception.cyclist_detected,
        possible_incident: frame.perception.possible_incident,
        confidence: frame.perception.confidence,
      };
      setPerception(perceptionData);

      // Update road context state (convert null to undefined for TypeScript compatibility)
      setRoadContext({
        speed_limit_mph: frame.road_context.speed_limit_mph,
        traffic_speed_mph: frame.road_context.traffic_speed_mph ?? undefined,
        congestion_level: frame.road_context.congestion_level as any,
        road_grade_percent: frame.road_context.road_grade_percent,
        upcoming_stop_distance_m: frame.road_context.upcoming_stop_distance_m ?? undefined,
        incident_ahead: frame.road_context.incident_ahead,
      });

      // Log simulation phase changes to Event Log
      if (prevPerceptionRef.current) {
        const prev = prevPerceptionRef.current;
        if (frame.perception.pedestrian_detected && !prev.pedestrian_detected) {
          addLog('Simulator: Pedestrian detected ahead', 'warning');
        }
        if (frame.perception.lead_vehicle_status === 'stopped' && prev.lead_vehicle_status !== 'stopped') {
          addLog('Simulator: Lead vehicle stopped', 'warning');
        }
        if (frame.perception.lead_vehicle_status === 'braking' && prev.lead_vehicle_status === 'moving') {
          addLog('Simulator: Lead vehicle braking', 'info');
        }
      }

      if (prevRoadRef.current) {
        const prev = prevRoadRef.current;
        if (frame.road_context.upcoming_stop_distance_m && frame.road_context.upcoming_stop_distance_m < 5 &&
            (!prev.upcoming_stop_distance_m || prev.upcoming_stop_distance_m >= 5)) {
          addLog(`Simulator: Stopped at ${frame.road}`, 'info');
        }
      }

      // Special event logging for key waypoints
      if (idx === 0) {
        addLog('Simulator: Starting at 3rd & B', 'success');
      } else if (idx === 120) {
        addLog('Simulator: Arrived at 1st & B', 'success');
      }

      prevPerceptionRef.current = frame.perception;
      prevRoadRef.current = frame.road_context;

      // Trigger a recommendation request to update the recommendation panel
      api.postRecommendation({
        location: frame.location,
        perception: perceptionData,
        road_context: frame.road_context,
        vehicle_profile: null,
      }).then(rec => {
        if (rec) {
          setRecommendation(rec);

          // Update charts with simulation data
          const now = new Date().toLocaleTimeString();

          setSpeedChartData(prev => {
            const next = [...prev, {
              time: now,
              current_speed: rec.summary.current_speed_mph,
              optimal_speed: rec.summary.optimal_speed_now_mph,
              traffic_speed: frame.road_context.traffic_speed_mph || rec.summary.optimal_speed_now_mph
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
        }
      }).catch(() => {
        // Silent fail, backend may not be running
      });
    },
    onEnd: () => {
      setSimulationActive(false);
      addLog('Simulator: Drive completed', 'success');
    },
  });

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

        // Only update recommendation and charts if not in simulation mode
        // (simulation mode updates these directly in onFrame callback)
        if (!simulationActive) {
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

          // Don't overwrite location/perception/road context during simulation
          if (loc) setLocation(loc);
          if (perc) setPerception(perc);
          if (ctx) setRoadContext(ctx);
        }

        // Always update these regardless of simulation mode
        if (tel) setTelemetry(tel);
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
          <PhoneTelemetryPanel telemetry={simulationActive && location ? {
            gps: { latitude: location.lat, longitude: location.lon }
          } : telemetry} />
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
            simulationActive={simulationActive}
            onStartSimulation={() => {
              addLog('Simulated 2-min Davis drive started', 'success');
              setSimulationActive(true);
            }}
            onStopSimulation={() => {
              addLog('Simulated drive stopped', 'info');
              setSimulationActive(false);
            }}
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

      {/* Big simulated-drive tactical view — only renders after the user
          clicks "Seed Demo Location" in the LocationPanel. */}
      {simulationActive && (
        <div className="px-4 pb-4">
          <SimulatedDriveMap
            timeline={sim.timeline}
            frame={sim.currentFrame}
            frameIdx={sim.frameIdx}
            running={sim.running}
            loadError={sim.loadError}
            onStop={() => {
              addLog('Simulated drive stopped', 'info');
              setSimulationActive(false);
            }}
          />
        </div>
      )}
    </div>
  );
}
