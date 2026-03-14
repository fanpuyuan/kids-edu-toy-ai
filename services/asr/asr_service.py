"""ASR语音识别模块"""

import numpy as np
from funasr import AutoModel
from loguru import logger

class ASRModule:
    def __init__(self, model: str = "paraformer-zh-streaming", device: str = "cuda"):
        logger.info(f"加载ASR模型: {model}")
        try:
            self.model = AutoModel(
                model=model,
                vad_model="fsmn-vad",
                punc_model="ct-punc-c",
                device=device,
            )
        except Exception as e:
            logger.warning(f"CUDA 加载失败，尝试 CPU: {e}")
            self.model = AutoModel(
                model=model,
                vad_model="fsmn-vad",
                punc_model="ct-punc-c",
                device="cpu",
            )
        self.cache = {}
        logger.info("ASR模型加载完成")

    def transcribe(self, audio: np.ndarray, is_final: bool = False) -> str:
        result = self.model.generate(
            input=audio,
            cache=self.cache,
            is_final=is_final,
        )
        return result[0]["text"] if result else ""

    def reset(self):
        self.cache = {}
