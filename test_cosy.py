import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer

print("SpeechSynthesizer type:", type(SpeechSynthesizer.call))
import inspect
print("Doc:", inspect.getdoc(SpeechSynthesizer.call))

# let's try calling it and see what it returns
# without a valid API key it will raise an error, but let's see the error type
import os
os.environ["NO_PROXY"] = "dashscope.aliyuncs.com,*aliyuncs.com"
os.environ["no_proxy"] = "dashscope.aliyuncs.com,*aliyuncs.com"
try:
    dashscope.api_key = "invalid-key"
    synth = SpeechSynthesizer(model="cosyvoice-v1", voice="longxiaochun")
    audio = synth.call("测试")
    print(type(audio), len(audio) if audio else 'None')
except Exception as e:
    import traceback
    traceback.print_exc()
