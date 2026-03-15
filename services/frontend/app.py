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
llm_env_flag = st.sidebar.radio("运行环境", ["Local (Ollama)", "Cloud (API)"])

llm_api_key = ""
if llm_env_flag == "Cloud (API)":
    llm_api_key = st.sidebar.text_input("云端 API Key (必填)", type="password")
    model_options = ["deepseek-chat", "glm-4"]
else:
    model_options = ["qwen3.5:2b", "qwen3.5:0.8b", "llama3.1:8b"]

llm_model = st.sidebar.selectbox("选择模型", model_options, index=0)
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
    "llm_env": "cloud" if llm_env_flag == "Cloud (API)" else "local",
    "llm_api_key": llm_api_key,
    "llm_model": llm_model,
    "llm_temp": llm_temp,
    "tts_voice": tts_voice,
    "tts_rate": tts_rate
}

st.divider()

# 交互模式选择
tab1, tab2, tab3, tab4 = st.tabs(["🎤 语音助手", "⌨️ 文字聊天", "📚 知识库上传", "👨‍👩‍👧 记忆档案"])

def send_chat_request(payload):
    # --- 安全校验：检查模型是否存在 ---
    req_model = current_config.get("llm_model")
    if current_config.get("llm_env") == "local" and "available_models" in st.session_state:
        # 兼容例如选择了 qwen3.5:2b，但 ollama list 是 qwen3.5:2b:latest 的情况
        exact_match = req_model in st.session_state.available_models
        latest_match = f"{req_model}:latest" in st.session_state.available_models
        if not (exact_match or latest_match):
            st.error(f"⚠️ 您选择的模型 `{req_model}` 尚未下载！请先在左侧「Ollama 模型管理」中拉取。")
            return
    elif current_config.get("llm_env") == "cloud":
        if not current_config.get("llm_api_key").strip():
            st.error("⚠️ 若使用云端大模型，API Key 必须填写！")
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

with tab3:
    st.subheader("📚 专属知识库")
    st.markdown("上传故事、儿歌、百科知识，让玩具变得更聪明！")
    
    # ---------------- 核心：文件列表展示与管理 ----------------
    st.markdown("### 📂 已上传的文件")
    
    def fetch_documents():
        try:
            res = requests.get("http://gateway:8000/list_docs", timeout=5.0)
            if res.status_code == 200:
                return res.json().get("documents", [])
        except Exception as e:
            st.warning(f"无法获取文件列表: {e}")
        return []

    docs = fetch_documents()
    
    if not docs:
        st.info("当前知识库为空。")
    else:
        # 使用列布局来展示文件列表和删除按钮
        for doc in docs:
            col_name, col_status, col_time, col_del = st.columns([4, 2, 3, 1])
            with col_name:
                st.text(doc.get("filename", "Unknown"))
            with col_status:
                status = doc.get("status", "unknown")
                if status == "success":
                    st.success("已解析")
                elif status == "processing":
                    st.info("解析中...")
                else:
                    st.error("失败")
            with col_time:
                # 简单截断时间显示
                st.text(doc.get("upload_time", "")[:16].replace("T", " "))
            with col_del:
                # 点击删除按钮
                if st.button("❌", key=f"del_{doc['doc_id']}", help="删除此文件及知识"):
                    with st.spinner("删除中..."):
                        try:
                            # 调用 gateway 进行删除
                            del_res = requests.post(
                                "http://gateway:8000/delete_doc", 
                                json={"doc_id": doc["doc_id"]}
                            )
                            if del_res.status_code == 200:
                                st.success("已删除！")
                                st.rerun() # 刷新页面重新拉取列表
                            else:
                                st.error("删除失败。")
                        except Exception as e:
                            st.error(f"网络请求错误: {e}")
    
    st.markdown("---")
    st.markdown("### ☁️ 上传新文件")
    uploaded_file = st.file_uploader("支持格式：.txt, .md, .pdf, .docx", type=["txt", "md", "pdf", "docx"])
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 上传并解析", use_container_width=True):
            if uploaded_file is not None:
                with st.spinner("正在解析并存入知识库..."):
                    try:
                        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                        res = requests.post("http://gateway:8000/upload_doc", files=files)
                        if res.status_code == 200:
                            chunks = res.json().get('chunks_added', 0)
                            st.success(f"上传成功！生成了 {chunks} 个知识切片。")
                            st.rerun() # 刷新列表
                        else:
                            st.error(f"上传失败: {res.text}")
                    except Exception as e:
                        st.error(f"网络请求错误: {e}")
            else:
                st.warning("请先选择一个文件。")
                
    with col2:
        if st.button("⚠️ 危险: 强行清空全库", use_container_width=True):
            with st.spinner("由于清空接口升级，这可能导致 SQLite 数据不一致。推荐使用上方逐个删除功能。"):
                try:
                    res = requests.post("http://gateway:8000/clear_docs")
                    if res.status_code == 200:
                        st.success("ChromDB 和 BM25 已清空！(注意：SQLite 记录可能残留)")
                    else:
                        st.error("清空知识库失败。")
                except Exception as e:
                    st.error(f"网络请求错误: {e}")

with tab4:
    st.subheader("👨‍👩‍👧 家庭记忆档案")
    st.markdown("这里存储着玩具对小主人的记忆和人设。")
    
    layer_mapping = {
        "固定人设 (SYSTEM)": "SYSTEM",
        "家庭档案 (FAMILY)": "FAMILY",
        "近期记忆 (SNAPSHOT)": "SNAPSHOT"
    }
    
    selected_layer_label = st.selectbox("选择要编辑的记忆层", list(layer_mapping.keys()))
    layer_id = layer_mapping[selected_layer_label]
    
    # 动态加载内容
    if "memory_cache" not in st.session_state:
        st.session_state.memory_cache = {}
        
    try:
        res = requests.get(f"http://gateway:8000/memory/{layer_id}")
        if res.status_code == 200:
            current_content = res.json().get("content", "")
        else:
            current_content = "读取失败"
    except Exception as e:
        current_content = "网络异常"

    edited_content = st.text_area("编辑内容 (Markdown)", value=current_content, height=200)
    
    if st.button("💾 保存修改", use_container_width=True):
        try:
            res = requests.post(
                "http://gateway:8000/memory/update", 
                json={"layer": layer_id, "content": edited_content}
            )
            if res.status_code == 200:
                st.success(f"{layer_id} 记忆已更新！下次对话即生效。")
            else:
                st.error("保存失败。")
        except Exception as e:
            st.error(f"网络请求错误: {e}")

