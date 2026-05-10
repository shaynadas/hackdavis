import { useState, useEffect, useRef } from 'react';
import { Accelerometer, Gyroscope } from 'expo-sensors';
import * as Location from 'expo-location';

type Vector3 = { x: number; y: number; z: number };
type GPSData = { latitude: number; longitude: number; speed: number; heading: number };

export type TelemetryPacket = {
  timestamp: number;
  accel: Vector3 | null;
  gyro: Vector3 | null;
  gps: GPSData | null;
};

export function useTelemetryStreamer(serverUrl: string) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [latestPacket, setLatestPacket] = useState<TelemetryPacket | null>(null);
  const [statusMessage, setStatusMessage] = useState('Idle');

  const accelRef = useRef<Vector3 | null>(null);
  const gyroRef = useRef<Vector3 | null>(null);
  const gpsRef = useRef<GPSData | null>(null);
  
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const accelSubRef = useRef<any>(null);
  const gyroSubRef = useRef<any>(null);
  const locationSubRef = useRef<Location.LocationSubscription | null>(null);

  useEffect(() => {
    return () => {
      stopStreaming();
    };
  }, []);

  const startStreaming = async () => {
    if (isStreaming) return;
    
    setStatusMessage('Requesting permissions...');
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') {
      setStatusMessage('Permission to access location was denied');
      return;
    }

    setStatusMessage('Starting sensors...');
    
    // Set update intervals to ~10Hz (100ms)
    Accelerometer.setUpdateInterval(100);
    Gyroscope.setUpdateInterval(100);

    accelSubRef.current = Accelerometer.addListener(data => {
      accelRef.current = { x: data.x, y: data.y, z: data.z };
    });

    gyroSubRef.current = Gyroscope.addListener(data => {
      gyroRef.current = { x: data.x, y: data.y, z: data.z };
    });

    locationSubRef.current = await Location.watchPositionAsync(
      {
        accuracy: Location.Accuracy.High,
        timeInterval: 1000,
        distanceInterval: 1,
      },
      (loc) => {
        gpsRef.current = {
          latitude: loc.coords.latitude,
          longitude: loc.coords.longitude,
          speed: loc.coords.speed ?? 0,
          heading: loc.coords.heading ?? 0,
        };
      }
    );

    setIsStreaming(true);
    setStatusMessage('Streaming...');

    intervalRef.current = setInterval(sendTelemetry, 300); // 300ms interval
  };

  const stopStreaming = () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (accelSubRef.current) accelSubRef.current.remove();
    if (gyroSubRef.current) gyroSubRef.current.remove();
    if (locationSubRef.current) locationSubRef.current.remove();
    
    intervalRef.current = null;
    accelSubRef.current = null;
    gyroSubRef.current = null;
    locationSubRef.current = null;

    setIsStreaming(false);
    setStatusMessage('Stopped');
  };

  const sendTelemetry = async () => {
    const packet: TelemetryPacket = {
      timestamp: Date.now() / 1000,
      accel: accelRef.current,
      gyro: gyroRef.current,
      gps: gpsRef.current,
    };

    setLatestPacket(packet);

    try {
      // console.log(`Sending telemetry packet:`, packet);
      const response = await fetch(serverUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(packet),
      });

      if (response.ok) {
        setStatusMessage('Connected & Streaming (OK)');
      } else {
        console.warn(`Server returned ${response.status}`);
        setStatusMessage(`Error: Server returned ${response.status}`);
      }
    } catch (error: any) {
      console.error(`Network Error:`, error.message);
      setStatusMessage(`Network Error: ${error.message}`);
    }
  };

  return {
    isStreaming,
    latestPacket,
    statusMessage,
    startStreaming,
    stopStreaming,
  };
}
