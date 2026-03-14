"""API测试脚本"""

import asyncio
import websockets
import json


async def test_chat():
    """测试对话接口"""
    uri = "ws://localhost:8000/ws"

    async with websockets.connect(uri) as ws:
        # 发送测试消息
        request = {
            "action": "chat",
            "data": {
                "text": "给我讲一个小兔子的故事",
                "session_id": "test_001",
                "context": {"child_age": 5},
            },
        }
        await ws.send(json.dumps(request))
        print(f"发送: {request}")

        # 接收响应
        while True:
            response = await ws.recv()
            data = json.loads(response)

            if data["type"] == "text_chunk":
                print(f"文本: {data['data']['text']}", end="", flush=True)

            elif data["type"] == "response_complete":
                print(f"\n完成! 延迟: {data['data']['latency_ms']}ms")
                break


if __name__ == "__main__":
    asyncio.run(test_chat())
