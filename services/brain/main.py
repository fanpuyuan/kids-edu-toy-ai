from fastapi import FastAPI
from fastapi.responses import JSONResponse
from graph import story_graph
import uvicorn
from pydantic import BaseModel
from typing import List, Optional
from loguru import logger
import os

LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5:2b")

app = FastAPI(title="Brain Service (LangGraph)")

class BrainRequest(BaseModel):
    input: str
    session_id: str = "default"
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    history: List[dict] = []
    llm_env: Optional[str] = "local"
    llm_api_key: Optional[str] = ""
    embedding_provider: Optional[str] = "local"
    context: Optional[dict] = {}

from fastapi.responses import StreamingResponse
import json

@app.post("/chat_stream")
async def chat_stream(request: BrainRequest):
    """大脑对话接口"""
    # 初始化状态
    initial_state = {
        "input": request.input,
        "chat_history": [], # TODO: 处理历史转换
        "session_id": request.session_id,
        "intent": "",
        "context": "",
        "response": "",
        "config": {
            "model": request.model or LLM_MODEL,
            "temperature": request.temperature,
            "llm_env": request.llm_env,
            "llm_api_key": request.llm_api_key,
            "embedding_provider": request.embedding_provider
        }
    }
    
    # 执行图返回异步生成器
    async def generate_stream():
        try:
            in_generate_node = False
            # 使用 astream_events 捕获详细的生成事件
            async for event in story_graph.astream_events(initial_state, version="v1"):
                
                # 只有当你确信是带有特定标签的大模型在生成 token 并且带内容时才抛出
                if event["event"] == "on_chat_model_stream":
                    tags = event.get("tags", [])
                    if "generate_output" in tags:
                        chunk = event["data"]["chunk"]
                        if getattr(chunk, "content", None):
                            yield json.dumps({"type": "token", "content": chunk.content}) + "\n"
                
                # 捕获意图或者其它的元数据完成
                elif event["event"] == "on_chain_end" and event["name"] == "classify_intent":
                    intent_data = event["data"]["output"]
                    if intent_data and "intent" in intent_data:
                        yield json.dumps({"type": "intent", "content": intent_data["intent"]}) + "\n"

            yield json.dumps({"type": "done", "content": ""}) + "\n"
        except Exception as e:
            logger.error(f"Brain Execution Stream Error: {e}")
            yield json.dumps({"type": "error", "content": str(e)}) + "\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)
