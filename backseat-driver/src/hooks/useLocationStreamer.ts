import { useState, useEffect, useRef } from 'react';
import { postLocationUpdate, geolocationPositionToBackendPayload } from '../api';
import type { LocationInput } from '../types';

export function useLocationStreamer(enabled: boolean) {
  const [isSupported, setIsSupported] = useState<boolean>(true);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [latestStreamedLocation, setLatestStreamedLocation] = useState<LocationInput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [permissionState, setPermissionState] = useState<"unknown" | "granted" | "denied" | "prompt">("unknown");
  
  const watchIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (!('geolocation' in navigator)) {
      setIsSupported(false);
      setError("Browser geolocation not supported");
      return;
    }
    
    if (navigator.permissions && navigator.permissions.query) {
      navigator.permissions.query({ name: 'geolocation' }).then((result) => {
        setPermissionState(result.state);
        result.onchange = () => {
          setPermissionState(result.state);
        };
      }).catch(() => {
        // Not all browsers support querying geolocation permissions
      });
    }
  }, []);

  useEffect(() => {
    if (!enabled || !isSupported) {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
        setIsStreaming(false);
      }
      return;
    }

    watchIdRef.current = navigator.geolocation.watchPosition(
      (position) => {
        setError(null);
        setIsStreaming(true);
        const payload = geolocationPositionToBackendPayload(position);
        
        postLocationUpdate(payload).then(res => {
          if (res.ok) {
            setLatestStreamedLocation(payload);
          }
        }).catch(err => {
          console.error("Failed to post location to backend:", err);
        });
      },
      (err) => {
        setIsStreaming(false);
        if (err.code === err.PERMISSION_DENIED) {
          setError("GPS permission denied");
          setPermissionState("denied");
        } else {
          setError(err.message);
        }
      },
      {
        enableHighAccuracy: true,
        maximumAge: 1000,
        timeout: 10000
      }
    );

    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
        setIsStreaming(false);
      }
    };
  }, [enabled, isSupported]);

  return {
    isSupported,
    isStreaming,
    latestStreamedLocation,
    error,
    permissionState
  };
}
