import asyncio
from langchain_openai import ChatOpenAI

async def test():
    llm = ChatOpenAI(
        model="qwen3.5:0.8b",
        api_key="ollama-local",
        base_url="http://ollama:11434/v1",
        streaming=True
    )
    
    print("Sending prompt...")
    async for chunk in llm.astream("Hi, respond in 5 words"):
        print("CHUNK:", chunk.content)
    print("Done")

if __name__ == "__main__":
    asyncio.run(test())
