"""TTS语音合成模块"""

import edge_tts
from typing import AsyncIterator
from loguru import logger

class TTSModule:
    VOICES = {
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",
        "yunxi": "zh-CN-YunxiNeural",
        "yunyang": "zh-CN-YunyangNeural",
    }

    def __init__(self, voice: str = "xiaoxiao", rate: str = "+0%", pitch: str = "+10Hz"):
        self.voice = self.VOICES.get(voice, self.VOICES["xiaoxiao"])
        self.rate = rate
        self.pitch = pitch
        logger.info(f"TTS初始化: voice={self.voice}")

    async def synthesize(self, text: str, voice: str = None, rate: str = None) -> bytes:
        v = voice or self.voice
        r = rate or self.rate
        communicate = edge_tts.Communicate(
            text=text,
            voice=v,
            rate=r,
            pitch=self.pitch,
        )
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data

    async def synthesize_stream(self, text: str, voice: str = None, rate: str = None) -> AsyncIterator[bytes]:
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            pitch=self.pitch,
        )
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
