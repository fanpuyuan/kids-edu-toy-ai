import asyncio
import json
from langchain_openai import ChatOpenAI

async def test():
    llm = ChatOpenAI(
        model="qwen3.5:0.8b",
        api_key="ollama-local",
        base_url="http://ollama:11434/v1",
        streaming=True
    ).with_config({"tags": ["generate_output"]})
    
    # We will just use the standard astream_events
    async for event in llm.astream_events("Hi, respond in 5 words", version="v1"):
        print("EVENT:", event["event"])
        print("TAGS:", event.get("tags"))
        if event["event"] == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            print("CHUNK CONTENT:", getattr(chunk, "content", None))

if __name__ == "__main__":
    asyncio.run(test())
