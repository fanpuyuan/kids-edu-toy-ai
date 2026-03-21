import asyncio
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer
from loguru import logger

class CosyVoiceService:
    def __init__(self):
        # 默认模型和声音
        self.default_model = "cosyvoice-v1"
        self.default_voice = "longxiaochun"

    def _synthesize_sync(self, text: str, voice_id: str, api_key: str) -> bytes:
        """
        同步调用 DashScope 语音合成接口
        """
        if not api_key:
            raise ValueError("DashScope API Key is required for CosyVoice.")
            
        dashscope.api_key = api_key
        
        # 如果未传入特定的 voice_id，或者传入的是 Edge-TTS 的名字（带有 zh-CN-），都使用默认的 CosyVoice 声音
        if not voice_id or "zh-CN-" in voice_id:
            voice = self.default_voice
        else:
            voice = voice_id
        
        try:
            synthesizer = SpeechSynthesizer(
                model=self.default_model,
                voice=voice
            )
            
            result = synthesizer.call(text)
            
            audio_bytes = result.get_audio_data()
            if not audio_bytes:
                logger.error(f"CosyVoice 返回空的音频数据，可能是 API Key 无效或跨域网络被拦截。Result: {result}")
                return b""
                
            logger.info(f"CosyVoice 合成成功: {len(audio_bytes)} bytes")
            return audio_bytes
        except Exception as e:
            logger.error(f"CosyVoice SDK 调用崩溃: {e}. 请检查您的 API Key 是否由于欠费失效，或者您的电脑全局代理 (VPN) 是否意外拦截了 wss://dashscope.aliyuncs.com")
            return b""

    async def synthesize(self, text: str, voice_id: str, api_key: str) -> bytes:
        """
        异步封装:在线程池中执行同步的 DashScope API 调用，防止阻塞事件循环
        """
        return await asyncio.to_thread(self._synthesize_sync, text, voice_id, api_key)

    def _clone_voice_sync(self, audio_path: str, api_key: str) -> dict:
        """
        同步调用 DashScope 声音克隆 (Zero-shot) 的 Enrollment 接口
        """
        if not api_key:
            return {"status": "error", "message": "DashScope API Key is required."}
            
        dashscope.api_key = api_key
        
        try:
            from dashscope.audio.tts_v2 import VoiceEnrollmentService
            
            # 使用一个特定的 prefix 来标识是基于该项目克隆的声音
            prefix = "kids-edu-clone"
            
            # 建立 VoiceEnrollmentService 调用
            # 注意: target_model 是 cosyvoice-v1
            result = VoiceEnrollmentService.create_voice(
                prefix=prefix,
                target_model=self.default_model,
                url=audio_path  # Aliyun SDK 允许直接传本地绝对路径
            )
            
            # API 返回通常是一个 Result 对象
            # 正确克隆后会具有 voice_id 属性
            if result and hasattr(result, "voice_id") and result.voice_id:
                logger.info(f"声音成功克隆，获取到 Voice ID: {result.voice_id}")
                return {"status": "success", "voice_id": result.voice_id}
            else:
                logger.warning(f"声音克隆似乎失败，未获取到 voice_id. 完整返回: {result}")
                return {"status": "error", "message": f" 未获取到 Voice ID: {result}"}
                
        except Exception as e:
            logger.error(f"声音克隆发生异常: {e}")
            return {"status": "error", "message": str(e)}

    async def clone_voice(self, audio_path: str, api_key: str) -> dict:
        """
        异步封装: 发起声音克隆，不会阻塞事件循环
        """
        return await asyncio.to_thread(self._clone_voice_sync, audio_path, api_key)

cosyvoice_service = CosyVoiceService()
