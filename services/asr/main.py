from fastapi import FastAPI, UploadFile, File, Form
import numpy as np
import io
import base64
from asr_service import ASRModule
from loguru import logger
import uvicorn

app = FastAPI(title="ASR Service")
asr = ASRModule()

@app.post("/transcribe")
async def transcribe(
    audio: str = Form(...), 
    is_final: bool = Form(False)
):
    """音频转写接口"""
    try:
        # 解码 base64 音频
        audio_data = base64.b64decode(audio)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        text = asr.transcribe(audio_array, is_final=is_final)
        return {"text": text}
    except Exception as e:
        logger.error(f"ASR error: {e}")
        return {"text": "", "error": str(e)}

@app.post("/reset")
async def reset():
    """重置 ASR 缓存"""
    asr.reset()
    return {"status": "ok"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
