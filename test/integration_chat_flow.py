import pytest
import asyncio
import json
import base64
import websockets
from websockets.exceptions import ConnectionClosed

# We cannot easily mock the whole system here without docker compose, 
# but this file serves as the end-to-end integration test structure.
# Provide a proper mock gateway if needed or run against localhost:8000
GATEWAY_WS_URL = "ws://localhost:8000/ws"

@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires the full docker-compose stack to be running locally on port 8000")
async def test_integration_full_chat_flow():
    """测试从 Gateway 接入到最终收到文本与声音完整的流式通讯。"""
    
    async with websockets.connect(GATEWAY_WS_URL) as websocket:
        # 发送请求
        payload = {
            "action": "chat",
            "session_id": "integration_test_sys",
            "data": {
                "text": "大灰狼最怕什么？",
                "context": {"child_age": 4} # 注入环境变量
            },
            "config": {
                "llm_env": "local"
            }
        }
        await websocket.send(json.dumps(payload))
        
        # 接收响应 (至少应该收到 text_chunk, audio_chunk 和 response_complete)
        received_text_chunks = 0
        received_audio_chunks = 0
        response_completed = False
        full_text = ""
        
        try:
            while True:
                responseStr = await asyncio.wait_for(websocket.recv(), timeout=20.0)
                response = json.loads(responseStr)
                
                msg_type = response.get("type")
                if msg_type == "text_chunk":
                    received_text_chunks += 1
                    full_text += response["data"]["text"]
                elif msg_type == "audio_chunk":
                    received_audio_chunks += 1
                    audio = response["data"]["audio"]
                    assert len(audio) > 10 # ensure it's actual base64 audio
                elif msg_type == "response_complete":
                    response_completed = True
                    break
                    
        except asyncio.TimeoutError:
            pytest.fail("Integration test timed out waiting for stream")
            
        assert received_text_chunks > 0, "No text chunks received in stream"
        assert received_audio_chunks > 0, "No audio chunks received in stream"
        assert response_completed, "Stream did not properly complete"
        assert len(full_text) > 0, "Empty final text"
