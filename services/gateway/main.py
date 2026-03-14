"""Gateway Service - 负责 WebSocket 和服务编排"""

import asyncio
import json
import base64
import httpx
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, BackgroundTasks
from fastapi.responses import JSONResponse, Response
from loguru import logger
import os

app = FastAPI(title="Gateway Service")

# 存储模型拉取进度
pull_progress_store = {}

# 微服务地址配置 (从环境变量读取)
ASR_URL = os.getenv("ASR_URL", "http://asr-service:8001")
TTS_URL = os.getenv("TTS_URL", "http://tts-service:8002")
RAG_URL = os.getenv("RAG_URL", "http://rag-service:8003")
BRAIN_URL = os.getenv("BRAIN_URL", "http://brain-service:8004")

async def perform_pull(model_name: str):
    """后台运行，真正去连接 ollama 执行 pull 并解析进度流"""
    pull_progress_store[model_name] = {"status": "starting", "progress": 0.0, "total": 0, "completed": 0}
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            ollama_url = os.getenv("OLLAMA_HOST", "http://ollama:11434")
            logger.info(f"Connecting to {ollama_url}/api/pull for {model_name}")
            async with client.stream("POST", f"{ollama_url}/api/pull", json={"name": model_name}) as response:
                logger.info(f"Stream opened, HTTP status: {response.status_code}")
                async for line in response.aiter_lines():
                    if line:
                        try:
                            # logger.debug(f"Raw line: {line}")
                            data = json.loads(line)
                            status_text = data.get("status", "working")
                            completed = data.get("completed", 0)
                            total = data.get("total", 0)
                            
                            progress_pct = 0.0
                            if total > 0:
                                progress_pct = completed / total
                                
                            pull_progress_store[model_name] = {
                                "status": status_text,
                                "progress": progress_pct,
                                "completed": completed,
                                "total": total
                            }
                            if status_text == "success":
                                break
                        except json.JSONDecodeError:
                            continue
    except Exception as e:
        logger.error(f"Background pull failed for {model_name}: {e}")
        pull_progress_store[model_name] = {"status": f"error: {str(e)}", "progress": 0.0}

@app.post("/pull_model")
async def pull_model(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    model_name = data.get("model")
    logger.info(f"收到模型拉取请求: {model_name}")
    
    current_status = pull_progress_store.get(model_name, {}).get("status")
    if current_status not in ["success", "pulling manifest", "downloading digestname"] and "error" not in str(current_status):
        background_tasks.add_task(perform_pull, model_name)
        return {"status": "started", "message": f"开始拉取 {model_name}"}
    else:
        return {"status": "already_running", "message": f"模型 {model_name} 已经在处理中 (状态: {current_status})"}

@app.get("/pull_status/{model_name}")
async def get_pull_status(model_name: str):
    """获取指定模型的下载进度"""
    return pull_progress_store.get(model_name, {"status": "not_started", "progress": 0.0})

@app.get("/ollama_status")
async def ollama_status():
    """获取 Ollama 运行状态和模型列表"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            ollama_url = os.getenv("OLLAMA_HOST", "http://ollama:11434")
            res = await client.get(f"{ollama_url}/api/tags")
            return res.json()
    except Exception as e:
        logger.error(f"获取 Ollama 状态失败: {e}")
        return JSONResponse(status_code=500, content={"error": "无法连接到 Ollama 服务"})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("硬件玩具已连接")
    
    # 默认配置
    config = {
        "llm_model": "qwen3.5:2b",
        "llm_temp": 0.7,
        "tts_voice": "zh-CN-XiaoxiaoNeural",
        "tts_rate": "+0%"
    }
    
    try:
        # 增加超时时间到 120 秒，因为第一次加载新模型到显存通常需要 40-60 秒
        async with httpx.AsyncClient(timeout=120.0) as client:
            while True:
                message = await websocket.receive_text()
                request = json.loads(message)
                
                action = request.get("action")
                data = request.get("data", {})
                
                # 更新当前会话配置
                if "config" in request:
                    config.update(request["config"])
                    logger.info(f"更新会话配置: {config}")
                
                if action == "audio":
                    await handle_audio(websocket, data, client, session_id=request.get("session_id", "default"), config=config)
                elif action == "chat":
                    await handle_chat(websocket, data, client, session_id=request.get("session_id", "default"), config=config)
                elif action == "ping":
                    await websocket.send_json({"type": "pong"})
                    
    except WebSocketDisconnect:
        logger.info("客户端断开连接")
    except Exception as e:
        logger.error(f"Gateway Error: {e}")

async def handle_audio(websocket: WebSocket, data: dict, client: httpx.AsyncClient, session_id: str, config: dict):
    """处理语音输入: ASR -> Brain -> Gateway -> TTS"""
    audio_b64 = data.get("audio", "")
    
    # 1. 调用 ASR
    logger.info("调用 ASR 服务...")
    asr_res = await client.post(f"{ASR_URL}/transcribe", data={"audio": audio_b64, "is_final": True})
    text = asr_res.json().get("text", "")
    await websocket.send_json({"type": "asr_result", "data": {"text": text}})
    
    # 2. 调用 Brain / Chat 处理
    await handle_chat(websocket, {"text": text}, client, session_id=session_id, config=config)

async def handle_chat(websocket: WebSocket, data: dict, client: httpx.AsyncClient, session_id: str, config: dict):
    """处理文本逻辑: Brain -> TTS -> WebSocket"""
    text = data.get("text", "")
    
    # 3. 调用 Brain Service
    logger.info(f"发送到 Brain: {text}")
    try:
        brain_payload = {
            "input": text, 
            "session_id": session_id,
            "model": config.get("llm_model"),
            "temperature": config.get("llm_temp")
        }
        brain_res = await client.post(f"{BRAIN_URL}/chat", json=brain_payload)
        brain_data = brain_res.json()
        response_text = brain_data.get("response", "对不起，我现在有点忙，稍后再聊吧。")
        intent = brain_data.get("intent", "chat")
        logger.info(f"Brain 回复 (意图: {intent}): {response_text}")
    except Exception as e:
        logger.error(f"Brain Service Error: {e}")
        response_text = "哎呀，我的大脑断网了，请检查网络设置。"
    
    await websocket.send_json({"type": "text_chunk", "data": {"text": response_text}})
    
    # 4. 调用 TTS
    logger.info(f"调用 TTS 服务 (voice={config.get('tts_voice')})...")
    tts_params = {
        "text": response_text,
        "voice": config.get("tts_voice"),
        "rate": config.get("tts_rate")
    }
    tts_res = await client.get(f"{TTS_URL}/synthesize", params=tts_params)
    audio_data = tts_res.content
    
    await websocket.send_json({
        "type": "audio_chunk",
        "data": {"audio": base64.b64encode(audio_data).decode()}
    })
    
    await websocket.send_json({"type": "response_complete", "data": {"full_text": response_text}})

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
