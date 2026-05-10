import os
import re
import httpx
from typing import Optional

def is_elevenlabs_stt_configured() -> bool:
    return bool(os.getenv("ELEVENLABS_API_KEY"))

def is_elevenlabs_tts_configured() -> bool:
    return bool(os.getenv("ELEVENLABS_API_KEY")) and bool(os.getenv("ELEVENLABS_VOICE_ID"))

async def transcribe_audio_with_elevenlabs(file_bytes: bytes, filename: str, content_type: str) -> dict:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        return {
            "success": False, "source": "elevenlabs_stt",
            "transcript": None, "language_code": None,
            "raw": None, "error": "ELEVENLABS_API_KEY not configured"
        }
        
    url = "https://api.elevenlabs.io/v1/speech-to-text"
    model_id = os.getenv("ELEVENLABS_STT_MODEL_ID", "scribe_v2")
    
    headers = {
        "xi-api-key": api_key
    }
    
    files = {
        "file": (filename, file_bytes, content_type)
    }
    
    data = {
        "model_id": model_id,
        "language_code": "en",
        "tag_audio_events": "false",
        "no_verbatim": "true"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, data=data, files=files)
            response.raise_for_status()
            res_json = response.json()
            return {
                "success": True,
                "source": "elevenlabs_stt",
                "transcript": res_json.get("text"),
                "language_code": res_json.get("language_code", "en"),
                "raw": res_json,
                "error": None
            }
    except Exception as e:
        return {
            "success": False, "source": "elevenlabs_stt",
            "transcript": None, "language_code": None,
            "raw": None, "error": str(e)
        }

def normalize_spoken_vehicle_text(text: str) -> str:
    if not text:
        return ""
    text = text.upper()
    
    # Remove phrases
    phrases_to_remove = [
        "MY VIN IS", "THE VIN NUMBER IS", "VIN NUMBER IS",
        "VEHICLE IDENTIFICATION NUMBER IS", "VEHICLE IDENTIFICATION NUMBER",
        "VIN IS", "VIM IS", "VIN", "VIM"
    ]
    for p in phrases_to_remove:
        text = text.replace(p, "")
        
    # Replace spelled digits
    word_to_digit = {
        "ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3",
        "FOUR": "4", "FIVE": "5", "SIX": "6", "SEVEN": "7",
        "EIGHT": "8", "NINE": "9",
        "BEE": "B", "BE": "B", "SEE": "C", "SEA": "C",
        "JAY": "J", "KAY": "K", "WHY": "Y", "YOU": "U", "DOUBLE YOU": "W"
    }
    
    for word, replacement in word_to_digit.items():
        # simple word replacement to avoid partial matches
        text = re.sub(rf"\b{word}\b", replacement, text)
        
    # handle "OH" logic: typically "O" or "0". In VIN, O is invalid, so OH is almost always 0.
    text = re.sub(r"\bOH\b", "0", text)
    
    # Remove all punctuation and spaces
    text = re.sub(r"[^A-Z0-9]", "", text)
    
    return text

def extract_vin_from_text(text: str) -> dict:
    normalized = normalize_spoken_vehicle_text(text)
    
    # VIN rules: 17 chars, A-H, J-N, P, R-Z, 0-9
    vin_pattern = r"[A-HJ-NPR-Z0-9]{17}"
    matches = re.findall(vin_pattern, normalized)
    
    if not matches:
        # Try finding something close (17 chars but has I,O,Q)
        invalid_pattern = r"[A-Z0-9]{17}"
        invalid_matches = re.findall(invalid_pattern, normalized)
        if invalid_matches:
            # Has I, O, Q
            candidate = invalid_matches[0]
            candidate = candidate.replace("I", "1").replace("O", "0").replace("Q", "0")
            if re.match(vin_pattern, candidate):
                return {
                    "vin": candidate,
                    "confidence": 0.75,
                    "method": "regex_17_char_candidate",
                    "needs_confirmation": True
                }
        
        return {
            "vin": None,
            "confidence": 0.0,
            "method": "not_found",
            "needs_confirmation": True
        }
        
    if len(matches) == 1:
        return {
            "vin": matches[0],
            "confidence": 0.95,
            "method": "regex_17_char_exact",
            "needs_confirmation": False
        }
    else:
        return {
            "vin": matches[0],
            "confidence": 0.5,
            "method": "regex_17_char_multiple",
            "needs_confirmation": True
        }

def extract_vehicle_identity_from_text(text: str) -> dict:
    if not text:
        return {"year": None, "make": None, "model": None, "trim": None, "confidence": 0.0}
    
    text_upper = text.upper()
    
    makes = ["AUDI", "BMW", "MERCEDES", "TOYOTA", "HONDA", "FORD", "CHEVY", "CHEVROLET", 
             "HYUNDAI", "KIA", "NISSAN", "TESLA", "VOLKSWAGEN", "SUBARU", "MAZDA", 
             "LEXUS", "ACURA", "JEEP", "DODGE", "RAM", "GMC"]
             
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text_upper)
    year = int(year_match.group(1)) if year_match else None
    
    found_make = None
    for make in makes:
        if make in text_upper:
            found_make = make.capitalize()
            break
            
    if year or found_make:
        return {
            "year": year,
            "make": found_make,
            "model": "Unknown", # Difficult to extract model perfectly without full list
            "trim": None,
            "confidence": 0.7 if (year and found_make) else 0.4
        }
        
    return {"year": None, "make": None, "model": None, "trim": None, "confidence": 0.0}

async def synthesize_speech_with_elevenlabs(text: str) -> tuple[Optional[bytes], Optional[str]]:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    
    if not api_key or not voice_id:
        return None, None
        
    model_id = os.getenv("ELEVENLABS_TTS_MODEL_ID", "eleven_flash_v2_5")
    output_format = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format={output_format}"
    
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text,
        "model_id": model_id
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.content, "audio/mpeg"
    except httpx.HTTPStatusError as e:
        print(f"ElevenLabs TTS Error: {e.response.status_code} - {e.response.text}")
        return None, None
    except Exception as e:
        print(f"ElevenLabs TTS Exception: {str(e)}")
        return None, None

def normalize_vin_capture_text(text: str) -> str:
    if not text:
        return ""
    text = text.upper()
    
    for w in ["VIN", "VIM", "NUMBER", "IS", "MY", "THE"]:
        text = re.sub(rf"\b{w}\b", "", text)
        
    word_to_digit = {
        "ZERO": "0", "OH": "0", "ONE": "1", "TWO": "2", "THREE": "3",
        "FOUR": "4", "FIVE": "5", "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9"
    }
    
    for word, replacement in word_to_digit.items():
        text = re.sub(rf"\b{word}\b", replacement, text)
        
    word_to_letter = {
        "BEE": "B", "BE": "B", "SEE": "C", "SEA": "C", "JAY": "J", "KAY": "K",
        "YOU": "U", "DOUBLE YOU": "W", "WHY": "Y", "ZEE": "Z"
    }
    
    for word, replacement in word_to_letter.items():
        text = re.sub(rf"\b{word}\b", replacement, text)
        
    text = re.sub(r"[^A-Z0-9]", "", text)
    return text

def validate_vin_candidate(vin: str) -> dict:
    if not vin:
        return {"vin": None, "valid": False, "confidence": 0.0, "error": "Empty VIN"}
    if len(vin) != 17:
        return {"vin": vin, "valid": False, "confidence": 0.0, "error": f"Length is {len(vin)}, expected 17"}
        
    if re.search(r"[IOQ]", vin):
        return {"vin": vin, "valid": False, "confidence": 0.0, "error": "Contains invalid characters (I, O, Q)"}
        
    if not re.match(r"^[A-HJ-NPR-Z0-9]{17}$", vin):
        return {"vin": vin, "valid": False, "confidence": 0.0, "error": "Contains invalid characters"}
        
    return {"vin": vin, "valid": True, "confidence": 0.95, "error": None}

def interpret_yes_no(text: str) -> dict:
    if not text:
        return {"answer": None, "confidence": 0.0, "transcript": text}
        
    text_upper = text.upper()
    positives = ["YES", "YEAH", "YEP", "CORRECT", "THAT IS CORRECT", "RIGHT", "CONFIRM"]
    negatives = ["NO", "NAH", "NOPE", "INCORRECT", "WRONG", "TRY AGAIN"]
    
    for p in positives:
        if p in text_upper:
            return {"answer": True, "confidence": 0.9, "transcript": text}
            
    for n in negatives:
        if n in text_upper:
            return {"answer": False, "confidence": 0.9, "transcript": text}
            
    return {"answer": None, "confidence": 0.0, "transcript": text}
