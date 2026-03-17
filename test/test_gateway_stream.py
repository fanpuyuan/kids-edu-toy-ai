import pytest
from fastapi.testclient import TestClient
import httpx
import json
import base64
from unittest.mock import AsyncMock, patch
from main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_gateway_chat_streaming():
    """测试 Gateway 能否将 Brain 服务传回的流式字符缓冲成一句话并一起发送"""
    
    # 我们打桩 AsyncClient 以免真的发起网络请求
    class MockResponse:
        async def aiter_lines(self):
            # 模拟 Brain 吐出单个字，并在中间加一个逗号触发一次刷写
            yield json.dumps({"type": "token", "content": "你"})
            yield json.dumps({"type": "token", "content": "好"})
            yield json.dumps({"type": "token", "content": "，"})  # 触发 Flush 1
            yield json.dumps({"type": "token", "content": "世"})
            yield json.dumps({"type": "token", "content": "界"})
            yield json.dumps({"type": "token", "content": "！"})  # 触发 Flush 2
            yield json.dumps({"type": "done", "content": ""})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    async def mock_stream(*args, **kwargs):
        return MockResponse()

    # 模拟 TTS 服务，使其始终返回 200 和一段虚构音频
    async def mock_tts_get(*args, **kwargs):
        class MockTTSRes:
            status_code = 200
            content = b"fake_audio_bytes"
        return MockTTSRes()

    with patch("httpx.AsyncClient.stream", side_effect=mock_stream), \
         patch("httpx.AsyncClient.get", side_effect=mock_tts_get):
         
        with client.websocket_connect("/ws") as websocket:
            websocket.send_json({
                "action": "chat",
                "session_id": "test_01",
                "data": {
                    "text": "测试流式",
                    "context": {"child_age": 8}
                }
            })
            
            # 期望收到第一次 flush: "你好，" (text)
            data1 = websocket.receive_json()
            assert data1["type"] == "text_chunk"
            assert data1["data"]["text"] == "你好，"
            
            # 接着期望收到对应的音频: "fake_audio_bytes" (audio)
            data2 = websocket.receive_json()
            assert data2["type"] == "audio_chunk"
            assert data2["data"]["audio"] == base64.b64encode(b"fake_audio_bytes").decode()
            
            # 接着收到第二次 flush: "世界！" (text)
            data3 = websocket.receive_json()
            assert data3["type"] == "text_chunk"
            assert data3["data"]["text"] == "世界！"
            
            # 第二句的音频
            data4 = websocket.receive_json()
            assert data4["type"] == "audio_chunk"
            
            # 最后是 complete
            data5 = websocket.receive_json()
            assert data5["type"] == "response_complete"
            assert data5["data"]["full_text"] == "你好，世界！"
