from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse, JSONResponse
from tts_service import TTSModule
import uvicorn
import base64
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="TTS Service")
tts = TTSModule()

@app.get("/synthesize")
async def synthesize(text: str, voice: str = None, rate: str = "+0%"):
    """语音合成接口"""
    logger.info(f"合成请求: {text[:20]}... (voice={voice}, rate={rate})")
    audio_data = await tts.synthesize(text, voice=voice, rate=rate)
    if not audio_data:
        return JSONResponse(status_code=500, content={"error": "TTS 失败"})
    
    return Response(content=audio_data, media_type="audio/mpeg")

@app.get("/synthesize_stream")
async def synthesize_stream(text: str):
    """流式合成接口"""
    return StreamingResponse(tts.synthesize_stream(text), media_type="audio/mpeg")

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
