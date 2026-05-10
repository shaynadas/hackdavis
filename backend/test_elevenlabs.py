import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def test_tts():
    import httpx
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = "EXAVITQu4vr4xnSDxMaL"
    model_id = os.getenv("ELEVENLABS_TTS_MODEL_ID", "eleven_flash_v2_5")
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    data = {"text": "Hello this is Sarah", "model_id": model_id}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)
        print(response.status_code)
        if response.status_code != 200:
            print(response.text)
        else:
            print("SUCCESS! Audio generated.")

if __name__ == "__main__":
    asyncio.run(test_tts())
