export interface LocationInput {
  lat: number;
  lon: number;
  speed_mph: number;
  heading_deg?: number;
  accuracy_m?: number;
}

export interface RoadContextInput {
  speed_limit_mph: number;
  traffic_speed_mph?: number;
  congestion_level?: string;
  road_grade_percent?: number;
  upcoming_stop_distance_m?: number;
  incident_ahead?: boolean;
}

export interface PerceptionInput {
  traffic_state?: string;
  lead_vehicle_status?: string;
  lead_vehicle_distance?: string;
  stopped_vehicle_detected?: boolean;
  hazard_detected?: boolean;
  pedestrian_detected?: boolean;
  cyclist_detected?: boolean;
  possible_incident?: boolean;
  confidence?: number;
}

export interface VehicleProfileInput {
  year?: number;
  make?: string;
  model?: string;
  trim?: string;
  transmission_type?: string;
  mass_kg?: number;
  vin?: string;
  source?: string;
}

export interface RecommendationSummary {
  current_speed_mph: number;
  optimal_speed_now_mph: number;
  recommended_speed_delta_mph: number;
  recommended_action: string;
  recommended_speed_band_mph: string;
  recommended_gear?: number;
  estimated_rpm_at_optimal_speed?: number;
  target_rpm_range_at_optimal_speed?: string;
  estimated_current_rpm_range?: string;
  likely_current_gear?: number;
  gear_confidence?: number;
  eco_score: number;
  safety_level: string;
}

export interface AdviceOutput {
  voice_line: string;
  reason: string;
}

export interface RecommendationResponse {
  summary: RecommendationSummary;
  advice: AdviceOutput;
  rpm_speed_mapping: any;
  speed_rpm_candidates: any[];
  context_used: any;
  vehicle_used: any;
  debug: any;
}

export interface VoiceStatus {
  elevenlabs_configured: boolean;
  stt_configured: boolean;
  tts_configured: boolean;
  stt_model: string;
  tts_model: string;
  voice_id_present: boolean;
}

export interface VinCaptureResponse {
  success: boolean;
  session_id?: string;
  transcript?: string;
  normalized_vin?: string;
  vin_valid: boolean;
  vin_confidence?: number;
  needs_repeat: boolean;
  decoded_vehicle?: any;
  confirmation_text?: string;
  error?: string;
  speak_endpoint?: string;
}

export interface VinConfirmResponse {
  success: boolean;
  confirmed: boolean;
  vehicle_profile_saved: boolean;
  vehicle_profile?: any;
  message: string;
}

export interface YesNoVoiceResponse {
  success: boolean;
  transcript?: string;
  interpreted_answer?: boolean;
  confidence?: number;
  error?: string;
}

export interface EventLogItem {
  id: string;
  timestamp: Date;
  type: 'info' | 'warning' | 'success' | 'error';
  message: string;
}
