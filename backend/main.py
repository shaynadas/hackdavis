import json
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, Optional

from models import (
    RecommendationRequest, VINDecodeRequest, VINDecodeResponse,
    ElevationResponse, GradeRequest, GradeResponse, LocationInput,
    PerceptionInput, RoadContextInput, VoiceTranscriptResponse,
    SpeakRequest, VoiceRecommendationResponse, VehicleProfileInput,
    TypedVINRequest, VINCaptureResponse, VINConfirmRequest, VINConfirmResponse,
    YesNoVoiceResponse
)
from eco_optimizer import get_recommendation, model_to_dict
from mock_data import get_demo_recommendation_payload, get_mock_traffic, get_mock_perception, get_mock_road_context
from services.vin_service import decode_vin
from services.elevation_service import get_elevation, calculate_grade
from services.traffic_service import get_traffic_context, get_tomtom_traffic
from services.elevenlabs_service import (
    is_elevenlabs_stt_configured, is_elevenlabs_tts_configured,
    transcribe_audio_with_elevenlabs, extract_vin_from_text,
    extract_vehicle_identity_from_text, synthesize_speech_with_elevenlabs,
    normalize_vin_capture_text, validate_vin_candidate, interpret_yes_no
)

app = FastAPI(title="Eco-Driving Recommendation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory stores
latest_location: Optional[LocationInput] = None
latest_perception: Optional[PerceptionInput] = None
latest_road_context: Optional[RoadContextInput] = None
latest_vehicle_profile: Optional[VehicleProfileInput] = None
vin_capture_sessions: dict = {}

def parse_optional_json_form_field(value: Optional[str], fallback: Any) -> Any:
    """
    Safely parse optional JSON form strings.
    If value is missing or invalid, return fallback.
    """
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "eco-driving-optimizer"
    }

@app.post("/recommendation")
async def get_recommendation_endpoint(payload: RecommendationRequest):
    # VIN support inside recommendation
    if payload.vehicle_profile and payload.vehicle_profile.vin and not payload.vehicle_profile.make:
        vin_res = await decode_vin(payload.vehicle_profile.vin)
        if vin_res.get("success"):
            payload.vehicle_profile.year = vin_res.get("year")
            payload.vehicle_profile.make = vin_res.get("make")
            payload.vehicle_profile.model = vin_res.get("model")
            payload.vehicle_profile.trim = vin_res.get("trim")
    return get_recommendation(payload)

@app.get("/recommendation/demo")
def get_demo_recommendation():
    payload = get_demo_recommendation_payload()
    return get_recommendation(payload)

@app.get("/recommendation/live")
async def get_live_recommendation():
    if not latest_location:
        raise HTTPException(status_code=400, detail="No location data available. Stream GPS data to /location/update first.")
    
    payload = get_demo_recommendation_payload()
    payload.location = latest_location
    payload.perception = latest_perception or get_mock_perception()
    payload.road_context = latest_road_context or get_mock_road_context()
    if latest_vehicle_profile:
        payload.vehicle_profile = latest_vehicle_profile
    
    traffic = await get_traffic_context(latest_location.lat, latest_location.lon)
    if traffic.get("speed_mph") is not None:
        payload.road_context.traffic_speed_mph = traffic.get("speed_mph")
    if traffic.get("congestion_level") is not None:
        payload.road_context.congestion_level = traffic.get("congestion_level")
    if traffic.get("incident_ahead") is not None:
        payload.road_context.incident_ahead = traffic.get("incident_ahead")
        
    return get_recommendation(payload)

@app.post("/location/update")
def update_location(loc: LocationInput):
    global latest_location
    latest_location = loc
    return {"status": "ok", "message": "Location updated"}

@app.get("/location/latest")
def get_latest_location():
    if not latest_location:
        raise HTTPException(status_code=404, detail="No location data available")
    return latest_location

@app.post("/perception/update")
def update_perception(perc: PerceptionInput):
    global latest_perception
    latest_perception = perc
    return {"status": "ok", "message": "Perception updated"}

@app.get("/perception/latest")
def get_latest_perception():
    if not latest_perception:
        raise HTTPException(status_code=404, detail="No perception data available")
    return latest_perception

@app.post("/road-context/update")
def update_road_context(ctx: RoadContextInput):
    global latest_road_context
    latest_road_context = ctx
    return {"status": "ok", "message": "Road context updated"}

@app.get("/road-context/latest")
def get_latest_road_context():
    if not latest_road_context:
        raise HTTPException(status_code=404, detail="No road context data available")
    return latest_road_context

@app.get("/vehicle/latest")
def get_latest_vehicle():
    if not latest_vehicle_profile:
        raise HTTPException(status_code=404, detail="No vehicle profile available")
    return latest_vehicle_profile

@app.delete("/vehicle/latest")
def clear_latest_vehicle():
    global latest_vehicle_profile
    latest_vehicle_profile = None
    return {"status": "ok", "message": "Vehicle profile cleared"}

@app.post("/vin/decode", response_model=VINDecodeResponse)
async def decode_vin_endpoint(payload: VINDecodeRequest):
    res = await decode_vin(payload.vin)
    return VINDecodeResponse(**res)

@app.get("/elevation", response_model=ElevationResponse)
async def get_elevation_endpoint(lat: float, lon: float):
    res = await get_elevation(lat, lon)
    return ElevationResponse(**res)

@app.post("/grade", response_model=GradeResponse)
async def calculate_grade_endpoint(payload: GradeRequest):
    res = await calculate_grade(payload.start, payload.end)
    return GradeResponse(**res)

@app.get("/traffic/mock")
def get_mock_traffic_endpoint():
    return get_mock_traffic()

@app.get("/traffic/tomtom")
async def get_tomtom_traffic_endpoint(lat: float, lon: float):
    return await get_tomtom_traffic(lat, lon)

@app.get("/voice/status")
def get_voice_status():
    import os
    return {
        "elevenlabs_configured": bool(os.getenv("ELEVENLABS_API_KEY")),
        "stt_configured": is_elevenlabs_stt_configured(),
        "tts_configured": is_elevenlabs_tts_configured(),
        "stt_model": os.getenv("ELEVENLABS_STT_MODEL_ID", "scribe_v2"),
        "tts_model": os.getenv("ELEVENLABS_TTS_MODEL_ID", "eleven_flash_v2_5"),
        "voice_id_present": bool(os.getenv("ELEVENLABS_VOICE_ID"))
    }

@app.post("/voice/transcribe-vin", response_model=VoiceTranscriptResponse)
async def transcribe_vin_audio(file: UploadFile = File(...)):
    if not is_elevenlabs_stt_configured():
        raise HTTPException(status_code=503, detail="ElevenLabs STT is not configured.")
        
    file_bytes = await file.read()
    stt_res = await transcribe_audio_with_elevenlabs(file_bytes, file.filename, file.content_type)
    
    if not stt_res.get("success"):
        return VoiceTranscriptResponse(success=False, source="elevenlabs_stt", error=stt_res.get("error"))
        
    transcript = stt_res.get("transcript", "")
    vin_data = extract_vin_from_text(transcript)
    
    vehicle_id = None
    if vin_data.get("vin"):
        vin_decode = await decode_vin(vin_data["vin"])
        if vin_decode.get("success"):
            vehicle_id = {
                "year": vin_decode.get("year"),
                "make": vin_decode.get("make"),
                "model": vin_decode.get("model"),
                "trim": vin_decode.get("trim")
            }
    else:
        vehicle_id = extract_vehicle_identity_from_text(transcript)
        
    return VoiceTranscriptResponse(
        success=True,
        source="elevenlabs_stt",
        transcript=transcript,
        extracted_vin=vin_data.get("vin"),
        vin_confidence=vin_data.get("confidence"),
        needs_confirmation=vin_data.get("needs_confirmation", False),
        vehicle_identity=vehicle_id
    )

@app.post("/voice/speak")
async def speak_text(payload: SpeakRequest):
    if not is_elevenlabs_tts_configured():
        raise HTTPException(status_code=503, detail="ElevenLabs TTS is not configured.")
        
    audio_bytes, content_type = await synthesize_speech_with_elevenlabs(payload.text)
    if not audio_bytes:
        raise HTTPException(status_code=503, detail="Failed to synthesize speech.")
        
    return Response(content=audio_bytes, media_type=content_type, headers={"Content-Disposition": "attachment; filename=advice.mp3"})

@app.post("/voice/speak-recommendation")
async def speak_recommendation(payload: RecommendationRequest):
    if not is_elevenlabs_tts_configured():
        raise HTTPException(status_code=503, detail="ElevenLabs TTS is not configured.")
        
    rec = get_recommendation(payload)
    voice_line = rec.get("advice", {}).get("voice_line", "")
    
    audio_bytes, content_type = await synthesize_speech_with_elevenlabs(voice_line)
    if not audio_bytes:
        raise HTTPException(status_code=503, detail="Failed to synthesize speech.")
        
    return Response(content=audio_bytes, media_type=content_type, headers={"Content-Disposition": "attachment; filename=recommendation.mp3"})

@app.post("/voice/recommendation-from-vin-audio", response_model=VoiceRecommendationResponse)
async def recommendation_from_vin_audio(
    file: UploadFile = File(...),
    location_json: Optional[str] = Form(None),
    road_context_json: Optional[str] = Form(None),
    perception_json: Optional[str] = Form(None)
):
    if not is_elevenlabs_stt_configured():
        raise HTTPException(status_code=503, detail="ElevenLabs STT is not configured.")
        
    file_bytes = await file.read()
    stt_res = await transcribe_audio_with_elevenlabs(file_bytes, file.filename, file.content_type)
    
    transcript = stt_res.get("transcript", "")
    vin_data = extract_vin_from_text(transcript)
    
    vehicle_id = None
    vp_input_dict = {}
    
    if vin_data.get("vin"):
        vp_input_dict["vin"] = vin_data["vin"]
        vin_decode = await decode_vin(vin_data["vin"])
        if vin_decode.get("success"):
            vehicle_id = {
                "year": vin_decode.get("year"),
                "make": vin_decode.get("make"),
                "model": vin_decode.get("model"),
                "trim": vin_decode.get("trim")
            }
            vp_input_dict.update(vehicle_id)
    else:
        vehicle_id = extract_vehicle_identity_from_text(transcript)
        if vehicle_id and vehicle_id.get("make"):
            vp_input_dict.update(vehicle_id)
            
    # Build payload
    loc = parse_optional_json_form_field(location_json, model_to_dict(latest_location) if latest_location else model_to_dict(get_demo_recommendation_payload().location))
    ctx = parse_optional_json_form_field(road_context_json, model_to_dict(latest_road_context) if latest_road_context else model_to_dict(get_demo_recommendation_payload().road_context))
    perc = parse_optional_json_form_field(perception_json, model_to_dict(latest_perception) if latest_perception else model_to_dict(get_demo_recommendation_payload().perception))
    
    payload = RecommendationRequest(
        location=loc,
        road_context=ctx,
        perception=perc,
        vehicle_profile=vp_input_dict
    )
    
    rec = get_recommendation(payload)
    voice_line = rec.get("advice", {}).get("voice_line", "")
    
    return VoiceRecommendationResponse(
        transcript=transcript,
        extracted_vin=vin_data.get("vin"),
        vin_confidence=vin_data.get("confidence"),
        vehicle_identity=vehicle_id,
        recommendation=rec,
        audio_available=is_elevenlabs_tts_configured(),
        warning=None,
        voice_line=voice_line,
        speak_endpoint="/voice/speak"
    )

@app.post("/voice/recommendation-from-vin-audio-with-speech", response_model=VoiceRecommendationResponse)
async def recommendation_from_vin_audio_with_speech(
    file: UploadFile = File(...),
    location_json: Optional[str] = Form(None),
    road_context_json: Optional[str] = Form(None),
    perception_json: Optional[str] = Form(None)
):
    return await recommendation_from_vin_audio(file, location_json, road_context_json, perception_json)

# ------------------------------------------------------------
# VIN CAPTURE ENDPOINTS
# ------------------------------------------------------------

@app.post("/vin/typed", response_model=VINCaptureResponse)
async def vin_typed_endpoint(payload: TypedVINRequest):
    vin = payload.vin.upper()
    val = validate_vin_candidate(vin)
    if not val.get("valid"):
        return VINCaptureResponse(
            success=False,
            normalized_vin=vin,
            vin_valid=False,
            needs_repeat=True,
            error=val.get("error")
        )
        
    vin_decode = await decode_vin(vin)
    decoded_vehicle = None
    confirmation_text = f"I received VIN {' '.join(vin)}. "
    if vin_decode.get("success") and vin_decode.get("make"):
        decoded_vehicle = {
            "year": vin_decode.get("year"),
            "make": vin_decode.get("make"),
            "model": vin_decode.get("model"),
            "trim": vin_decode.get("trim")
        }
        confirmation_text += f"This VIN matches with: {decoded_vehicle['year'] or ''} {decoded_vehicle['make']} {decoded_vehicle['model']}. Is this correct?"
    else:
        confirmation_text += "I could not decode the vehicle details. Is this VIN correct?"
        
    session_id = str(uuid.uuid4())
    vin_capture_sessions[session_id] = {
        "session_id": session_id,
        "transcript": vin,
        "normalized_vin": vin,
        "decoded_vehicle": decoded_vehicle,
        "confirmation_text": confirmation_text,
        "confirmed": None
    }
    
    return VINCaptureResponse(
        success=True,
        session_id=session_id,
        normalized_vin=vin,
        vin_valid=True,
        decoded_vehicle=decoded_vehicle,
        confirmation_text=confirmation_text
    )

@app.post("/voice/vin-capture", response_model=VINCaptureResponse)
async def vin_capture_voice_endpoint(file: UploadFile = File(...)):
    if not is_elevenlabs_stt_configured():
        raise HTTPException(status_code=503, detail="ElevenLabs STT is not configured.")
        
    file_bytes = await file.read()
    stt_res = await transcribe_audio_with_elevenlabs(file_bytes, file.filename, file.content_type)
    
    if not stt_res.get("success"):
        return VINCaptureResponse(success=False, error=stt_res.get("error"))
        
    transcript = stt_res.get("transcript", "")
    normalized_vin = normalize_vin_capture_text(transcript)
    
    val = validate_vin_candidate(normalized_vin)
    if not val.get("valid"):
        return VINCaptureResponse(
            success=False,
            transcript=transcript,
            normalized_vin=normalized_vin,
            vin_valid=False,
            needs_repeat=True,
            error=f"I heard something that resulted in {len(normalized_vin)} characters. " + val.get("error", "Please repeat the VIN.")
        )
        
    vin_decode = await decode_vin(normalized_vin)
    decoded_vehicle = None
    confirmation_text = f"I heard VIN {' '.join(normalized_vin)}. "
    if vin_decode.get("success") and vin_decode.get("make"):
        decoded_vehicle = {
            "year": vin_decode.get("year"),
            "make": vin_decode.get("make"),
            "model": vin_decode.get("model"),
            "trim": vin_decode.get("trim")
        }
        confirmation_text += f"This VIN matches with: {decoded_vehicle['year'] or ''} {decoded_vehicle['make']} {decoded_vehicle['model']}. Is this correct?"
    else:
        confirmation_text += "I could not decode the vehicle details. Is this VIN correct?"
        
    session_id = str(uuid.uuid4())
    vin_capture_sessions[session_id] = {
        "session_id": session_id,
        "transcript": transcript,
        "normalized_vin": normalized_vin,
        "decoded_vehicle": decoded_vehicle,
        "confirmation_text": confirmation_text,
        "confirmed": None
    }
    
    return VINCaptureResponse(
        success=True,
        session_id=session_id,
        transcript=transcript,
        normalized_vin=normalized_vin,
        vin_valid=True,
        vin_confidence=val.get("confidence"),
        decoded_vehicle=decoded_vehicle,
        confirmation_text=confirmation_text
    )

@app.post("/voice/vin-capture-and-speak")
async def vin_capture_and_speak_endpoint(file: UploadFile = File(...)):
    res = await vin_capture_voice_endpoint(file)
    res_dict = model_to_dict(res)
    res_dict["speak_endpoint"] = "/voice/speak"
    return res_dict

@app.post("/vin/confirm", response_model=VINConfirmResponse)
def confirm_vin_endpoint(payload: VINConfirmRequest):
    global latest_vehicle_profile
    
    session = vin_capture_sessions.get(payload.session_id)
    if not session:
        return VINConfirmResponse(
            success=False, confirmed=False, vehicle_profile_saved=False,
            message="Session not found."
        )
        
    session["confirmed"] = payload.confirmed
    
    if payload.confirmed:
        vp = VehicleProfileInput(vin=session["normalized_vin"])
        if session["decoded_vehicle"]:
            dv = session["decoded_vehicle"]
            vp.year = dv.get("year")
            vp.make = dv.get("make")
            vp.model = dv.get("model")
            vp.trim = dv.get("trim")
            
        latest_vehicle_profile = vp
        return VINConfirmResponse(
            success=True, confirmed=True, vehicle_profile_saved=True,
            vehicle_profile=model_to_dict(vp),
            message="Vehicle profile saved successfully."
        )
    else:
        return VINConfirmResponse(
            success=True, confirmed=False, vehicle_profile_saved=False,
            message="Okay, please repeat or type the VIN."
        )

@app.post("/voice/confirm-vin", response_model=YesNoVoiceResponse)
async def confirm_vin_voice_endpoint(session_id: str = Form(...), file: UploadFile = File(...)):
    if not is_elevenlabs_stt_configured():
        raise HTTPException(status_code=503, detail="ElevenLabs STT is not configured.")
        
    file_bytes = await file.read()
    stt_res = await transcribe_audio_with_elevenlabs(file_bytes, file.filename, file.content_type)
    
    if not stt_res.get("success"):
        return YesNoVoiceResponse(success=False, error=stt_res.get("error"))
        
    transcript = stt_res.get("transcript", "")
    yes_no = interpret_yes_no(transcript)
    
    answer = yes_no.get("answer")
    if answer is None:
        return YesNoVoiceResponse(
            success=False, transcript=transcript,
            error="I could not tell if you said yes or no."
        )
        
    # Call the logic from /vin/confirm
    req = VINConfirmRequest(session_id=session_id, confirmed=answer)
    confirm_res = confirm_vin_endpoint(req)
    
    return YesNoVoiceResponse(
        success=confirm_res.success,
        transcript=transcript,
        interpreted_answer=answer,
        confidence=yes_no.get("confidence")
    )
