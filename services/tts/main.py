from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse, JSONResponse
from tts_service import TTSModule
from cosyvoice_service import cosyvoice_service
import uvicorn
import base64
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="TTS Service")
tts = TTSModule()

@app.get("/synthesize")
async def synthesize(
    text: str, 
    voice: str = None, 
    rate: str = "+0%", 
    engine: str = "edge-tts", 
    cosyvoice_api_key: str = ""
):
    """语音合成接口"""
    logger.info(f"合成请求: {text[:20]}... (engine={engine}, voice={voice}, rate={rate})")
    
    try:
        if engine == "cosyvoice":
            audio_data = await cosyvoice_service.synthesize(text, voice_id=voice, api_key=cosyvoice_api_key)
        else:
            audio_data = await tts.synthesize(text, voice=voice, rate=rate)
            
        if not audio_data:
            return JSONResponse(status_code=500, content={"error": "音频生成为空"})
            
        return Response(content=audio_data, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"TTS生成失败 ({engine}): {e}")
        return JSONResponse(status_code=500, content={"error": f"TTS {engine} 失败: {str(e)}"})

from fastapi import UploadFile, File, Form
import tempfile
import os

@app.post("/clone_voice")
async def clone_voice(
    audio: UploadFile = File(...),
    api_key: str = Form(...)
):
    """声音克隆接口 (Zero-shot)"""
    logger.info(f"收到声音克隆请求: filename={audio.filename}, size={audio.size} bytes")
    try:
        # Read the audio bytes sent from the Gateway
        audio_bytes = await audio.read()
        
        # Save temp file for DashScope SDK requirement
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(audio_bytes)
            temp_path = temp_audio.name
            
        try:
            # Call the cloning implementation
            result = await cosyvoice_service.clone_voice(temp_path, api_key=api_key)
            return result
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        logger.error(f"Voice clone failed: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/synthesize_stream")
async def synthesize_stream(text: str):
    """流式合成接口"""
    return StreamingResponse(tts.synthesize_stream(text), media_type="audio/mpeg")

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
