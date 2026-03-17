import asyncio
import os
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage

async def test_chat_ollama():
    print("Testing ChatOllama streaming...")
    host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    print(f"Host: {host}")
    
    # Force use of 0.8b which we know is downloaded
    model = ChatOllama(model="qwen3.5:0.8b", base_url=host, temperature=0.7, streaming=True)
    
    print("Sending message...")
    try:
        count = 0
        async for chunk in model.astream([HumanMessage(content="Hello!")]):
            print(f"Chunk string: {chunk.content}")
            count += 1
            if count > 5:
                # Stop after 5 chunks to save time
                break
        print("Done streaming!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_chat_ollama())
