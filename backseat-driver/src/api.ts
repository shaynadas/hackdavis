import type {
  RecommendationResponse,
  LocationInput,
  PerceptionInput,
  RoadContextInput,
  VehicleProfileInput,
  VoiceStatus,
  VinCaptureResponse,
  VinConfirmResponse,
  YesNoVoiceResponse
} from './types';

export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function safeGet<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url);

    if (res.status === 400 || res.status === 404) {
      return null;
    }

    if (!res.ok) {
      console.warn(`Unexpected API error: ${url}`, res.status);
      return null;
    }

    return await res.json();
  } catch {
    return null;
  }
}

async function fetchWithFallback<T>(endpoint: string, options?: RequestInit): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE}${endpoint}`, options);
    if (!response.ok) {
      return null;
    }
    return await response.json();
  } catch (error) {
    return null;
  }
}

export async function postLocationUpdate(location: {
  lat: number;
  lon: number;
  speed_mph: number;
  heading_deg?: number;
  accuracy_m?: number;
}) {
  return fetch(`${API_BASE}/location/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(location),
  });
}

export function geolocationPositionToBackendPayload(position: GeolocationPosition) {
  const { latitude, longitude, speed, heading, accuracy } = position.coords;

  return {
    lat: latitude,
    lon: longitude,
    speed_mph: speed == null ? 0 : speed * 2.23694,
    heading_deg: heading == null ? 0 : heading,
    accuracy_m: accuracy == null ? 0 : accuracy,
  };
}

export const api = {
  checkHealth: () => safeGet<{ status: string }>(`${API_BASE}/health`),
  
  getLiveRecommendation: () => safeGet<RecommendationResponse>(`${API_BASE}/recommendation/live`),
  
  getLatestLocation: () => safeGet<LocationInput>(`${API_BASE}/location/latest`),
  
  getLatestPerception: () => safeGet<PerceptionInput>(`${API_BASE}/perception/latest`),
  
  getLatestRoadContext: () => safeGet<RoadContextInput>(`${API_BASE}/road-context/latest`),
  
  getLatestVehicle: () => safeGet<VehicleProfileInput>(`${API_BASE}/vehicle/latest`),
  
  clearLatestVehicle: async (): Promise<boolean> => {
    const res = await fetchWithFallback<{ status: string }>('/vehicle/latest', { method: 'DELETE' });
    return res !== null;
  },
  
  getVoiceStatus: () => safeGet<VoiceStatus>(`${API_BASE}/voice/status`),
  
  vinTyped: (vin: string) => fetchWithFallback<VinCaptureResponse>('/vin/typed', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vin })
  }),
  
  transcribeVinAudio: async (file: File): Promise<VinCaptureResponse | null> => {
    const formData = new FormData();
    formData.append('file', file);
    return fetchWithFallback<VinCaptureResponse>('/voice/vin-capture-and-speak', {
      method: 'POST',
      body: formData
    });
  },
  
  confirmVin: (sessionId: string, confirmed: boolean) => fetchWithFallback<VinConfirmResponse>('/vin/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, confirmed })
  }),
  
  confirmVinByVoice: async (sessionId: string, file: File): Promise<YesNoVoiceResponse | null> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('session_id', sessionId);
    return fetchWithFallback<YesNoVoiceResponse>('/voice/confirm-vin', {
      method: 'POST',
      body: formData
    });
  },
  
  speakText: async (text: string): Promise<Blob | null> => {
    try {
      const response = await fetch(`${API_BASE}/voice/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      if (!response.ok) return null;
      return await response.blob();
    } catch {
      return null;
    }
  }
};
