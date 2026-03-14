import streamlit as st
import asyncio
import websockets
import json
import base64
import os
from st_audiorec import st_audiorec

# 页面配置
st.set_page_config(page_title="🧸 智能伴读玩具控制台", layout="centered")

st.title("🧸 智能伴读玩具 Demo界面")
st.markdown("模拟硬件玩具终端：录音 -> 发送 -> 接收文字与语音流")

# --- Ollama 管理实用工具 ---
with st.sidebar.expander("🛠️ Ollama 模型管理", expanded=True):
    st.info("💡 如果模型不存在，请在此拉取")
    
    # 刷新模型列表
    import requests
    try:
        status_res = requests.get("http://gateway:8000/ollama_status")
        if status_res.status_code == 200:
            models = [m["name"] for m in status_res.json().get("models", [])]
            st.session_state.available_models = models
            st.write(f"**已下载模型:** \n" + ", ".join(models) if models else "无")
        else:
            st.error("无法获取模型列表")
    except:
        st.warning("正在等待网关启动...")

    st.divider()
    pull_model_name = st.text_input("输入新模型名称 (如 qwen3.5:2b)", value="qwen3.5:2b")
    if st.button("📥 立即拉取模型"):
        try:
            pull_url = "http://gateway:8000/pull_model"
            res = requests.post(pull_url, json={"model": pull_model_name})
            if res.status_code == 200:
                st.success(res.json().get("message"))
                
                # --- 动态进度条 ---
                progress_container = st.empty()
                status_text = st.empty()
                import time
                
                while True:
                    try:
                        status_res = requests.get(f"http://gateway:8000/pull_status/{pull_model_name}", timeout=2)
                        if status_res.status_code == 200:
                            data = status_res.json()
                            state = data.get("status", "")
                            pct = data.get("progress", 0.0)
                            
                            if state == "success":
                                progress_container.progress(1.0)
                                status_text.success(f"下载完成！")
                                time.sleep(1)
                                st.rerun() # 强制刷新页面显示新模型
                                break
                            elif "error" in state.lower():
                                progress_container.empty()
                                status_text.error(f"下载失败: {state}")
                                break
                            elif state == "not_started":
                                time.sleep(1)
                                continue
                            else:
                                pct_clamped = max(0.0, min(1.0, float(pct)))
                                progress_container.progress(pct_clamped)
                                # 渲染友好文案
                                clean_state = state.replace('downloading digestname', '下载数据块').replace('pulling manifest', '获取清单')
                                status_text.info(f"正在拉取: {clean_state} ({int(pct_clamped*100)}%)")
                    except Exception as poll_e:
                        status_text.warning(f"获取进度时网络波动, 等待重试...")
                    
                    time.sleep(1)
            else:
                st.error(f"指令发送失败: {res.text}")
        except Exception as e:
            st.error(f"连接失败: {e}")

st.sidebar.divider()

# 配置后台 WebSocket 地址 (优先读取环境变量)
DEFAULT_WS = os.getenv("BACKEND_URL", "ws://localhost:8080/ws")
WS_URL = st.sidebar.text_input("后端 WebSocket 地址", value=DEFAULT_WS)

st.sidebar.divider()
st.sidebar.subheader("🧠 大脑配置 (LLM)")
llm_model = st.sidebar.selectbox("选择模型", ["qwen3.5:2b", "qwen3.5:0.8b", "llama3.1:8b"], index=0)
llm_temp = st.sidebar.slider("脑电波强度 (Temperature)", 0.0, 1.2, 0.7)

st.sidebar.divider()
st.sidebar.subheader("🔊 声音配置 (TTS)")
tts_voice = st.sidebar.selectbox("选择音色", [
    "zh-CN-XiaoxiaoNeural (女萌)", 
    "zh-CN-YunxiNeural (男活泼)", 
    "zh-CN-YunjianNeural (男稳重)",
    "zh-HK-HiuMaanNeural (粤语女)"
], index=0).split(" (")[0]
tts_rate = st.sidebar.select_slider("语速调节", options=["-50%", "-20%", "+0%", "+20%", "+50%"], value="+0%")

CHILD_AGE = st.sidebar.number_input("设置儿童年龄", min_value=1, max_value=12, value=5)

# 打包配置
current_config = {
    "llm_model": llm_model,
    "llm_temp": llm_temp,
    "tts_voice": tts_voice,
    "tts_rate": tts_rate
}

st.divider()

# 交互模式选择
tab1, tab2 = st.tabs(["🎤 语音模式", "⌨️ 文字模式"])

def send_chat_request(payload):
    # --- 安全校验：检查模型是否存在 ---
    req_model = current_config.get("llm_model")
    if "available_models" in st.session_state:
        # 兼容例如选择了 qwen3.5:2b，但 ollama list 是 qwen3.5:2b:latest 的情况
        exact_match = req_model in st.session_state.available_models
        latest_match = f"{req_model}:latest" in st.session_state.available_models
        if not (exact_match or latest_match):
            st.error(f"⚠️ 您选择的模型 `{req_model}` 尚未下载！请先在左侧「Ollama 模型管理」中拉取。")
            return
            
    # 将全局配置注入 payload
    payload["config"] = current_config
    
    # 准备与后端的通信协程
    async def communicate_with_backend():
        text_placeholder = st.empty()
        full_text = ""
        
        try:
            async with websockets.connect(WS_URL) as websocket:
                await websocket.send(json.dumps(payload))
                st.toast("已发送，等待 AI 思考...", icon="⏳")
                
                while True:
                    response_str = await websocket.recv()
                    response = json.loads(response_str)
                    
                    resp_type = response.get("type")
                    resp_data = response.get("data", {})
                    
                    if resp_type == "text_chunk":
                        chunk = resp_data.get("text", "")
                        full_text += chunk
                        text_placeholder.markdown(f"**AI回复:** \n\n {full_text} 🪄")
                        
                    elif resp_type == "audio_chunk":
                        audio_bytes = base64.b64decode(resp_data.get("audio", ""))
                        st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                        
                    elif resp_type == "response_complete":
                        st.success("回答完毕！")
                        break
                        
        except Exception as e:
            st.error(f"连接失败: {str(e)}")
            
    # 运行协程
    asyncio.run(communicate_with_backend())

with tab1:
    st.subheader("🎤 说点什么吧...")
    wav_audio_data = st_audiorec()

    if wav_audio_data is not None:
        st.audio(wav_audio_data, format='audio/wav')
        
        if st.button("🚀 (语音) 发送给 AI 大脑", use_container_width=True):
            audio_b64 = base64.b64encode(wav_audio_data).decode('utf-8')
            payload = {
                "action": "audio",
                "data": {
                    "audio": audio_b64,
                    "context": {"child_age": CHILD_AGE}
                }
            }
            send_chat_request(payload)

with tab2:
    st.subheader("⌨️ 打字输入")
    text_input = st.text_area("请输入对话内容", height=100)
    
    if st.button("🚀 (文字) 发送给 AI 大脑", use_container_width=True):
        if text_input.strip():
            payload = {
                "action": "chat",
                "data": {
                    "text": text_input.strip(),
                    "context": {"child_age": CHILD_AGE}
                }
            }
            send_chat_request(payload)
        else:
            st.warning("请输入有效文字！")
