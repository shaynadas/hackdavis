from models import (
    LocationInput, RoadContextInput, PerceptionInput, VehicleProfileInput,
    RecommendationRequest, TrafficState, LeadVehicleStatus, LeadVehicleDistance,
    CongestionLevel, TransmissionType
)

def get_mock_road_context() -> RoadContextInput:
    return RoadContextInput(
        speed_limit_mph=40,
        traffic_speed_mph=24,
        congestion_level=CongestionLevel.moderate,
        road_grade_percent=3.2,
        upcoming_stop_distance_m=250,
        incident_ahead=False
    )

def get_mock_perception() -> PerceptionInput:
    return PerceptionInput(
        traffic_state=TrafficState.clear,
        lead_vehicle_status=LeadVehicleStatus.none,
        lead_vehicle_distance=LeadVehicleDistance.far,
        stopped_vehicle_detected=False,
        hazard_detected=False,
        pedestrian_detected=False,
        cyclist_detected=False,
        possible_incident=False,
        confidence=1.0
    )

def get_mock_vehicle_profile() -> VehicleProfileInput:
    return VehicleProfileInput(
        year=2018,
        make="Audi",
        model="A4",
        trim="2.0T",
        transmission_type=TransmissionType.automatic,
        mass_kg=1600,
        tire_width=245,
        aspect_ratio=40,
        rim_in=18,
        final_drive_ratio=4.41,
        gear_ratios={
            "1": 3.69,
            "2": 2.15,
            "3": 1.41,
            "4": 1.03,
            "5": 0.79,
            "6": 0.63
        }
    )

def get_demo_recommendation_payload() -> RecommendationRequest:
    return RecommendationRequest(
        location=LocationInput(
            lat=38.5449,
            lon=-121.7405,
            speed_mph=38,
            heading_deg=84.2,
            accuracy_m=8
        ),
        road_context=get_mock_road_context(),
        perception=get_mock_perception(),
        vehicle_profile=get_mock_vehicle_profile()
    )

def get_mock_traffic() -> dict:
    return {
        "source": "mock",
        "speed_mph": 24,
        "congestion_level": "moderate",
        "incident_ahead": False
    }
