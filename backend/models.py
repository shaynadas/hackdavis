from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

class TrafficState(str, Enum):
    clear = "clear"
    moderate = "moderate"
    slowing = "slowing"
    stopped = "stopped"

class LeadVehicleStatus(str, Enum):
    none = "none"
    moving = "moving"
    braking = "braking"
    stopped = "stopped"

class LeadVehicleDistance(str, Enum):
    far = "far"
    medium = "medium"
    close = "close"

class CongestionLevel(str, Enum):
    low = "low"
    moderate = "moderate"
    heavy = "heavy"

class RecommendedAction(str, Enum):
    maintain = "maintain"
    coast = "coast"
    slow_down = "slow_down"
    accelerate_gently = "accelerate_gently"
    urgent_slow_down = "urgent_slow_down"

class SafetyLevel(str, Enum):
    safe = "safe"
    caution = "caution"
    urgent = "urgent"

class TransmissionType(str, Enum):
    automatic = "automatic"
    manual = "manual"
    cvt = "cvt"
    unknown = "unknown"

class LocationInput(BaseModel):
    lat: float
    lon: float
    speed_mph: float
    heading_deg: Optional[float] = 0.0
    accuracy_m: Optional[float] = 0.0

class RoadContextInput(BaseModel):
    speed_limit_mph: float
    traffic_speed_mph: Optional[float] = None
    congestion_level: Optional[CongestionLevel] = CongestionLevel.low
    road_grade_percent: Optional[float] = 0.0
    upcoming_stop_distance_m: Optional[float] = None
    incident_ahead: Optional[bool] = False

class PerceptionInput(BaseModel):
    traffic_state: Optional[TrafficState] = TrafficState.clear
    lead_vehicle_status: Optional[LeadVehicleStatus] = LeadVehicleStatus.none
    lead_vehicle_distance: Optional[LeadVehicleDistance] = LeadVehicleDistance.far
    stopped_vehicle_detected: Optional[bool] = False
    hazard_detected: Optional[bool] = False
    pedestrian_detected: Optional[bool] = False
    cyclist_detected: Optional[bool] = False
    possible_incident: Optional[bool] = False
    confidence: Optional[float] = 1.0

class VehicleProfileInput(BaseModel):
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    transmission_type: Optional[TransmissionType] = TransmissionType.unknown
    mass_kg: Optional[float] = 1500
    tire_width: Optional[int] = 225
    aspect_ratio: Optional[int] = 50
    rim_in: Optional[int] = 17
    final_drive_ratio: Optional[float] = 3.7
    gear_ratios: Optional[Dict[str, float]] = None
    vin: Optional[str] = None

class RecommendationRequest(BaseModel):
    location: Optional[LocationInput] = None
    road_context: Optional[RoadContextInput] = None
    perception: Optional[PerceptionInput] = None
    vehicle_profile: Optional[VehicleProfileInput] = None

class RecommendationSummary(BaseModel):
    current_speed_mph: float
    optimal_speed_now_mph: float
    recommended_speed_delta_mph: float
    recommended_action: RecommendedAction
    recommended_speed_band_mph: str
    recommended_gear: Optional[int] = None
    estimated_rpm_at_optimal_speed: Optional[int] = None
    target_rpm_range_at_optimal_speed: Optional[str] = None
    estimated_current_rpm_range: Optional[str] = None
    likely_current_gear: Optional[int] = None
    gear_confidence: Optional[float] = None
    eco_score: int
    safety_level: SafetyLevel

class AdviceOutput(BaseModel):
    voice_line: str
    reason: str

class GearSpeedRange(BaseModel):
    gear: int
    speed_range_mph: str
    rpm_band: str

class RPMSpeedMapping(BaseModel):
    target_rpm_band: str
    speed_ranges_by_gear: List[GearSpeedRange]

class SpeedRPMCandidate(BaseModel):
    speed_mph: float
    best_gear: Optional[int] = None
    estimated_rpm: Optional[int] = None
    cost: float

class RecommendationResponse(BaseModel):
    summary: RecommendationSummary
    advice: AdviceOutput
    rpm_speed_mapping: RPMSpeedMapping
    speed_rpm_candidates: List[SpeedRPMCandidate]
    context_used: Dict[str, Any]
    vehicle_used: Dict[str, Any]
    debug: Dict[str, Any]

class VINDecodeRequest(BaseModel):
    vin: str

class VINDecodeResponse(BaseModel):
    success: bool
    source: str
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    error: Optional[str] = None

class CoordinateInput(BaseModel):
    lat: float
    lon: float

class ElevationResponse(BaseModel):
    elevation_m: float
    source: str
    error: Optional[str] = None

class GradeRequest(BaseModel):
    start: CoordinateInput
    end: CoordinateInput

class GradeResponse(BaseModel):
    grade_percent: float
    elevation_change_m: float
    horizontal_distance_m: float
    source: str
    error: Optional[str] = None
