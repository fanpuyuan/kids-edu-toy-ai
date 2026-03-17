import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://gateway:8000/ws"
    payload = {
        "action": "chat",
        "data": {
            "text": "Hello, this is a test from local.",
            "context": {"child_age": 5}
        },
        "config": {
            "llm_env": "local",
            "llm_model": "qwen3.5:0.8b",
            "temperature": 0.7,
            "tts_voice": "zh-CN-XiaoxiaoNeural"
        }
    }
    
    try:
        async with websockets.connect(uri) as ws:
            print("Connected to gateway.")
            await ws.send(json.dumps(payload))
            print("Sent payload.")
            
            while True:
                response = await ws.recv()
                data = json.loads(response)
                
                if data["type"] == "text_chunk":
                    print(f"CHUNK: {data['data']['text']}", end="", flush=True)
                elif data["type"] == "audio_chunk":
                    print("\n[Received Audio Chunk]")
                elif data["type"] == "response_complete":
                    print("\n[Response Complete]")
                    break
                elif data["type"] == "error":
                    print(f"\n[Error] {data['data']['message']}")
                    break
    except Exception as e:
        print(f"WS Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
