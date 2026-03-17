"""Gateway Service - 负责 WebSocket 和服务编排"""

import asyncio
import json
import base64
import httpx
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, BackgroundTasks, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from typing import Optional

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

class MemoryUpdateRequest(BaseModel):
    layer: str
    content: str


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

# --- RAG / Memory Proxy Endpoints ---

@app.post("/upload_doc")
async def upload_doc(
    file: UploadFile = File(...),
    embedding_provider: str = Form("local"),
    embedding_api_key: Optional[str] = Form("")
):
    """Proxy file upload to RAG service"""
    logger.info(f"Proxying file upload to RAG: {file.filename}")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            content = await file.read()
            files = {"file": (file.filename, content, file.content_type)}
            data = {"embedding_provider": embedding_provider, "embedding_api_key": embedding_api_key}
            res = await client.post(f"{RAG_URL}/upload_doc", files=files, data=data)
            return res.json()
    except Exception as e:
        logger.error(f"Failed to proxy upload_doc: {e}")
        raise HTTPException(status_code=500, detail="RAG service unavailable")

@app.post("/clear_docs")
async def clear_docs(embedding_provider: str = "local", embedding_api_key: Optional[str] = None):
    """Proxy clear database command to RAG service"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(f"{RAG_URL}/clear_docs", params={"embedding_provider": embedding_provider, "embedding_api_key": embedding_api_key})
            return res.json()
    except Exception as e:
        logger.error(f"Failed to proxy clear_docs: {e}")
        raise HTTPException(status_code=500, detail="RAG service unavailable")

@app.get("/list_docs")
async def list_docs(embedding_provider: Optional[str] = None):
    """Proxy list documents command to RAG service"""
    logger.info(f"List docs request for provider: {embedding_provider}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {}
            if embedding_provider:
                params["embedding_provider"] = embedding_provider
            res = await client.get(f"{RAG_URL}/list_docs", params=params)
            data = res.json()
            logger.info(f"RAG returned {len(data.get('documents', []))} documents")
            return data
    except Exception as e:
        logger.error(f"Failed to proxy list_docs: {e}")
        raise HTTPException(status_code=500, detail="RAG service unavailable")

class DeleteDocRequest(BaseModel):
    doc_id: str

@app.post("/delete_doc")
async def delete_doc(request: DeleteDocRequest, embedding_provider: str = "local", embedding_api_key: Optional[str] = None):
    """Proxy delete document command to RAG service"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"{RAG_URL}/delete_doc", 
                json={
                    "doc_id": request.doc_id, 
                    "embedding_provider": embedding_provider,
                    "embedding_api_key": embedding_api_key
                }
            )
            return res.json()
    except Exception as e:
        logger.error(f"Failed to proxy delete_doc: {e}")
        raise HTTPException(status_code=500, detail="RAG service unavailable")

# --- Configuration Proxy Endpoints ---

@app.get("/config")
async def get_config():
    """Proxies config retrieval to RAG service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{RAG_URL}/config")
            return res.json()
    except Exception as e:
        logger.error(f"Failed to fetch config from RAG service: {e}")
        return {"status": "error", "message": "Failed to fetch config"}

@app.post("/config")
async def set_config(request: Request):
    """Proxies config saving to RAG service."""
    try:
        configs = await request.json()
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(f"{RAG_URL}/config", json=configs)
            return res.json()
    except Exception as e:
        logger.error(f"Failed to save config to RAG service: {e}")
        raise HTTPException(status_code=500, detail="Failed to save config")

# --- Memory Proxy Endpoints ---

@app.get("/memory/all")
async def get_all_context():
    """Proxy get all memory layers"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{RAG_URL}/memory/all")
            return res.json()
    except Exception as e:
        logger.error(f"Failed to proxy memory/all: {e}")
        raise HTTPException(status_code=500, detail="RAG service unavailable")

@app.get("/memory/{layer}")
async def get_memory_layer(layer: str):
    """Proxy get specific memory layer"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{RAG_URL}/memory/{layer}")
            return res.json()
    except Exception as e:
        logger.error(f"Failed to proxy memory/{layer}: {e}")
        raise HTTPException(status_code=500, detail="RAG service unavailable")

@app.post("/memory/update")
async def update_memory_layer(request: MemoryUpdateRequest):
    """Proxy memory update"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(f"{RAG_URL}/memory/update", json={"layer": request.layer, "content": request.content})
            return res.json()
    except Exception as e:
        logger.error(f"Failed to proxy memory/update: {e}")
        raise HTTPException(status_code=500, detail="RAG service unavailable")


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
        # 增加超时时间到 60 秒，因为第一次加载新模型到显存通常需要 40-60 秒
        async with httpx.AsyncClient(timeout=60.0) as client:
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
    """处理文本逻辑: Brain -> TTS -> WebSocket (真实流式)"""
    text = data.get("text", "")
    context = data.get("context", {}) # Hardware context (e.g., child_age: 5)
    
    # 3. 调用 Brain Service (Stream)
    logger.info(f"发送到 Brain: {text}, context: {context}")
    try:
        brain_payload = {
            "input": text, 
            "session_id": session_id,
            "model": config.get("llm_model"),
            "temperature": config.get("llm_temp"),
            "llm_env": config.get("llm_env", "local"),
            "llm_api_key": config.get("llm_api_key", ""),
            "embedding_provider": config.get("embedding_provider", "local"),
            "embedding_api_key": config.get("embedding_api_key", ""),
            "context": context
        }
        
        # 使用流式客户端
        buffer = ""
        full_response = ""
        current_intent = "chat"
        
        # 为了不阻塞 LLM 文本流的读取，我们将 TTS 请求放入队列由后台任务处理
        tts_queue = asyncio.Queue()
        
        async def tts_worker():
            while True:
                text_chunk = await tts_queue.get()
                if text_chunk is None:
                    tts_queue.task_done()
                    break
                
                tts_params = {
                    "text": text_chunk,
                    "voice": config.get("tts_voice"),
                    "rate": config.get("tts_rate")
                }
                try:
                    # 使用较长的超时时间，TTS 合成可能较慢
                    tts_res = await client.get(f"{TTS_URL}/synthesize", params=tts_params, timeout=30.0)
                    if tts_res.status_code == 200:
                        audio_data = tts_res.content
                        await websocket.send_json({
                            "type": "audio_chunk",
                            "data": {"audio": base64.b64encode(audio_data).decode()}
                        })
                except Exception as tts_e:
                    logger.error(f"TTS Streaming Error for chunk '{text_chunk}': {tts_e}")
                finally:
                    tts_queue.task_done()

        # 启动 TTS 工作协程
        worker_task = asyncio.create_task(tts_worker())
        
        # 为了防止首次唤醒大模型（尤其 OLLAMA）长达十几秒甚至几分钟导致的超时，将 read timeout 设置为 None
        stream_timeout = httpx.Timeout(connect=20.0, read=None, write=None, pool=None)
        async with client.stream("POST", f"{BRAIN_URL}/chat_stream", json=brain_payload, timeout=stream_timeout) as brain_res:
            async for line in brain_res.aiter_lines():
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    evt_type = event.get("type")
                    content = event.get("content", "")
                    
                    if evt_type == "intent":
                        current_intent = content
                        logger.info(f"Brain 检测到意图: {current_intent}")
                    
                    elif evt_type == "token":
                        content = event.get("content", "")
                        
                        # 如果这段话之后出现了隐式分隔符 |||，我们完全跳过它以及之后的任何文字（也就是记忆标记过程）
                        if "|||" in full_response + content:
                            if "|||" not in full_response:
                                # 刚好在此次 token 中第一次碰到 |||，把 ||| 之前的部分加进缓冲并刷出
                                safe_part = (full_response + content).split("|||")[0].replace(full_response, "")
                                if safe_part:
                                    buffer += safe_part
                            # 置为静默，不再追加到发给前端的 buffer 中
                            full_response += content
                            continue
                            
                        full_response += content
                        buffer += content
                        
                        # 标点符号截断缓冲，生成一句话发给 TTS 和前端
                        if any(punc in buffer for punc in ["，", "。", "！", "？", "；", "\n", ",", ".", "!", "?", ";"]):
                            flush_text = buffer
                            buffer = ""
                            if flush_text.strip():
                                await websocket.send_json({"type": "text_chunk", "data": {"text": flush_text}})
                                # 将文本放入队列等待 TTS 合成
                                await tts_queue.put(flush_text.strip())
                    
                    elif evt_type == "done":
                        break
                    
                    elif evt_type == "error":
                        logger.error(f"Brain stream reported error: {content}")
                        await websocket.send_json({"type": "text_chunk", "data": {"text": " 哎呀，我的大脑出了一点小故障。"}})
                        break
                        
                except json.JSONDecodeError:
                    continue
        
        # 兜底处理：发送剩余缓冲区的内容
        if buffer.strip() and "|||" not in full_response:
            await websocket.send_json({"type": "text_chunk", "data": {"text": buffer}})
            await tts_queue.put(buffer.strip())
            
        # 等待所有 TTS 任务完成
        await tts_queue.put(None)
        await worker_task
                 
        # 从全量回复中剔除提供给前端可见的部分 (去除 ||| 后面的记忆指令)
        clean_full_text = full_response.split("|||")[0].strip()
        await websocket.send_json({"type": "response_complete", "data": {"full_text": clean_full_text}})
        
    except httpx.ReadTimeout:
         logger.error("Brain Service Request Timed Out.")
         await websocket.send_json({"type": "text_chunk", "data": {"text": " 大脑思考超时了，请稍后再试。"}})
         await websocket.send_json({"type": "response_complete", "data": {"full_text": " 大脑思考超时了，请稍后再试。"}})
    except Exception as e:
        logger.error(f"Brain Service Connection Error: {e}")
        error_msg = "哎呀，我的大脑断网了，请检查网络设置。"
        await websocket.send_json({"type": "text_chunk", "data": {"text": error_msg}})
        await websocket.send_json({"type": "response_complete", "data": {"full_text": error_msg}})

@app.get("/")
async def root():
    return {"status": "gateway_running"}

class QueryRequest(BaseModel):
    query: str
    top_k: int = 3
    embedding_provider: str = "local"
    embedding_api_key: Optional[str] = None

@app.post("/retrieve")
async def retrieve(request: QueryRequest):
    """Proxy retrieve command to RAG service"""
    logger.info(f"Proxying retrieval to RAG: {request.query}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(f"{RAG_URL}/retrieve", json=request.dict())
            return res.json()
    except Exception as e:
        logger.error(f"Failed to proxy retrieve: {e}")
        raise HTTPException(status_code=500, detail="RAG service unavailable")

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
