import httpx
import asyncio

async def test_ollama():
    print("Testing connection to http://ollama:11434...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get("http://ollama:11434/")
            print(f"Base endpoint status: {res.status_code}")
            print(f"Response: {res.text}")
            
            print("\nTesting model list...")
            res = await client.get("http://ollama:11434/api/tags")
            print(f"Tags endpoint status: {res.status_code}")
            data = res.json()
            models = [m['name'] for m in data.get('models', [])]
            print(f"Available models: {models}")
            
            model = "qwen3.5:0.8b"
            if model not in models:
                # 兼容 :latest
                if f"{model}:latest" in models:
                    model = f"{model}:latest"
                    
            print(f"\nTesting generation with model: {model}...")
            payload = {
                "model": model,
                "prompt": "Hello",
                "stream": False
            }
            res = await client.post("http://ollama:11434/api/generate", json=payload, timeout=30.0)
            print(f"Generate status: {res.status_code}")
            print(f"Response: {res.json().get('response', 'No response field')}")
            
    except Exception as e:
        print(f"\n[ERROR] Connection failed: {type(e).__name__}: {str(e)}")

asyncio.run(test_ollama())
