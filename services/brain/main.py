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

@app.post("/chat")
async def chat(request: BrainRequest):
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
            "llm_api_key": request.llm_api_key
        }
    }
    
    # 执行图
    try:
        final_state = await story_graph.ainvoke(initial_state)
        
        return {
            "response": final_state.get("response", "我不知道该说什么。"),
            "intent": final_state.get("intent", "chat"),
            "metadata": {"session_id": final_state.get("session_id", request.session_id)}
        }
    except Exception as e:
        logger.error(f"Brain Execution Error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "message": "大脑遇到了一点麻烦，请稍后刷新重试。"}
        )

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)
